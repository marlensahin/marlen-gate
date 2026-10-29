"""Marlen Kapı: Discord'u Türkiye'deki erişim engeline takılmadan açar.

Discord'u bu bilgisayarda çalışan küçük bir vekil (proxy) üzerinden açar. Vekil iki şey yapar:
1. Adresleri sağlayıcının DNS'i yerine şifreli DNS'ten (DoH) öğrenir. Sağlayıcının DNS'i
   discord.com için engel sayfasının adresini veriyor.
2. Her bağlantının ilk paketinde (TLS ClientHello) site adı açık yazılıdır; sağlayıcının DPI cihazı
   bağlantıyı bu adı görünce keser. Vekil bu paketi site adının ortasından iki TLS kaydına böler.
   Sunucu iki kaydı birleştirip normal okur, DPI ise adı tek parça göremez.
Şifreleme uçtan uca Discord ile kalır: vekil içeriği göremez, değiştirmez; yalnız aktarır.

Kullanım:
  pythonw kapi.py           vekili başlatır ve Discord'u vekille açar (masaüstü kısayolu bunu çalıştırır)
  python kapi.py --vekil    yalnız vekili başlatır (deneme için)
"""
import asyncio
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ADRES, PORT = '127.0.0.1', 18443
YERLI = f'http://{ADRES}:{PORT}'
DISCORD_SUNUCU = re.compile(r'([a-z0-9-]+\.)*(discord\.com|discordapp\.net|discordapp\.com)')
# Güncelleyiciye giden HTTPS istekleri de bu vekilin CONNECT tünelinden (DoH + bölme) geçer
ACICI = urllib.request.build_opener(urllib.request.ProxyHandler({'https': YERLI, 'http': YERLI}))
KLASOR = Path(__file__).resolve().parent
GUNLUK = KLASOR / 'kapi.log'
DOH = ('https://cloudflare-dns.com/dns-query?name={}&type=A', 'https://dns.google/resolve?name={}&type=A')
DISCORD = Path(os.environ.get('LOCALAPPDATA', '')) / 'Discord' / 'Update.exe'
PENCERESIZ = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

_dns: dict[str, tuple[str, float]] = {}


def yaz(satir: str) -> None:
    with GUNLUK.open('a', encoding='utf-8') as f:
        f.write(f'{time.strftime("%d.%m %H:%M:%S")} {satir}\n')


def ip_mi(ad: str) -> bool:
    try:
        ipaddress.ip_address(ad)
        return True
    except ValueError:
        return False


def coz(ad: str) -> str:
    """Adı şifreli DNS'ten çözer, cevabı TTL süresince önbellekte tutar."""
    kayit = _dns.get(ad)
    if kayit and kayit[1] > time.time():
        return kayit[0]
    for sablon in DOH:
        try:
            istek = urllib.request.Request(sablon.format(ad), headers={'accept': 'application/dns-json'})
            cevap = json.load(urllib.request.urlopen(istek, timeout=5))
            a = [x for x in cevap.get('Answer', []) if x.get('type') == 1]
            if a:
                ttl = max(60, min(int(a[-1].get('TTL', 300)), 3600))
                _dns[ad] = (a[-1]['data'], time.time() + ttl)
                return a[-1]['data']
        except Exception as e:  # bir DoH sunucusu düşerse sıradakini dene
            yaz(f'DoH hatası {ad}: {e}')
    return socket.gethostbyname(ad)  # son çare: sistemin DNS'i


def bol(kayit: bytes, ad: str) -> tuple[bytes, bytes]:
    """TLS ClientHello kaydını site adının ortasından iki ayrı TLS kaydına böler."""
    govde = kayit[5:]
    yer = govde.find(ad.encode())
    nokta = yer + len(ad) // 2 if yer > 0 else 1
    bas = kayit[:3]  # kayıt türü + TLS sürümü
    a, b = govde[:nokta], govde[nokta:]
    return bas + len(a).to_bytes(2, 'big') + a, bas + len(b).to_bytes(2, 'big') + b


async def aktar(okur: asyncio.StreamReader, yazar: asyncio.StreamWriter, sayac: list[int], i: int) -> None:
    try:
        while veri := await okur.read(65536):
            sayac[i] += len(veri)
            yazar.write(veri)
            await yazar.drain()
        if yazar.can_write_eof():
            yazar.write_eof()
    except (ConnectionError, OSError):
        pass


def hedef_adres(yol: str) -> str:
    """/_h/<sunucu>/<yol> -> https://<sunucu>/<yol>; geri kalan her şey -> updates.discord.com."""
    if yol.startswith('/_h/'):
        sunucu, _, kalan = yol[4:].partition('/')
        if not DISCORD_SUNUCU.fullmatch(sunucu):
            raise ValueError(f'izin verilmeyen sunucu: {sunucu}')
        return f'https://{sunucu}/{kalan}'
    return 'https://updates.discord.com' + yol


def yerellestir(govde: bytes) -> bytes:
    """Güncelleme listesindeki indirme adreslerini de bu vekilden geçecek şekilde yeniden yazar."""
    return re.sub(rb'https://([a-z0-9.-]+\.(?:discord\.com|discordapp\.net|discordapp\.com))/',
                  lambda m: YERLI.encode() + b'/_h/' + m.group(1) + b'/', govde)


async def ters_vekil(yontem: str, yol: str, istek: bytes, yazar: asyncio.StreamWriter) -> None:
    """Güncelleyicinin düz HTTP isteğini Discord'a bu vekilin CONNECT tüneli üzerinden HTTPS olarak iletir."""
    gecen = {}
    for satir in istek.decode('latin-1').split('\r\n')[1:]:
        anahtar, _, deger = satir.partition(':')
        if anahtar.strip().lower() in ('range', 'user-agent', 'accept', 'if-none-match', 'if-modified-since'):
            gecen[anahtar.strip()] = deger.strip()
    url = hedef_adres(yol)

    def ac():
        try:
            return ACICI.open(urllib.request.Request(url, headers=gecen, method=yontem), timeout=30)
        except urllib.error.HTTPError as e:
            return e

    cevap = await asyncio.to_thread(ac)
    durum = getattr(cevap, 'status', None) or cevap.code
    tur = cevap.headers.get('Content-Type', 'application/octet-stream')
    bas = f'HTTP/1.1 {durum} {cevap.reason}\r\nContent-Type: {tur}\r\n'
    if '/manifests/' in yol or 'json' in tur:
        govde = yerellestir(await asyncio.to_thread(cevap.read))
        yazar.write((bas + f'Content-Length: {len(govde)}\r\nConnection: close\r\n\r\n').encode() + govde)
        await yazar.drain()
        aktarilan = len(govde)
    else:
        for k in ('Content-Length', 'Content-Range', 'Accept-Ranges', 'ETag', 'Last-Modified'):
            if cevap.headers.get(k):
                bas += f'{k}: {cevap.headers[k]}\r\n'
        yazar.write((bas + 'Connection: close\r\n\r\n').encode())
        aktarilan = 0
        while parca := await asyncio.to_thread(cevap.read, 65536):
            aktarilan += len(parca)
            yazar.write(parca)
            await yazar.drain()
    cevap.close()
    yaz(f'güncelleme {yontem} {url[:90]} -> {durum} ({aktarilan} B)')


async def baglanti(okur: asyncio.StreamReader, yazar: asyncio.StreamWriter) -> None:
    u_yazar = None
    ad = '?'
    try:
        istek = await asyncio.wait_for(okur.readuntil(b'\r\n\r\n'), 15)
        yontem, hedef, _ = istek.split(b'\r\n', 1)[0].decode('latin-1').split(' ', 2)
        if yontem != 'CONNECT':
            if hedef.startswith('/'):  # Discord güncelleyicisinin düz HTTP isteği
                ad = hedef[:60]
                await ters_vekil(yontem, hedef, istek, yazar)
            else:
                yazar.write(b'HTTP/1.1 405 Method Not Allowed\r\nContent-Length: 0\r\n\r\n')
                await yazar.drain()
            return
        ad, _, port = hedef.rpartition(':')
        ad = ad.strip('[]')
        ip = ad if ip_mi(ad) else await asyncio.to_thread(coz, ad)
        u_okur, u_yazar = await asyncio.wait_for(asyncio.open_connection(ip, int(port)), 10)
        u_yazar.get_extra_info('socket').setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        yazar.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
        await yazar.drain()

        bas = await asyncio.wait_for(okur.readexactly(5), 30)
        if bas[0] == 0x16 and bas[1] == 0x03:  # TLS el sıkışması: site adını böl
            govde = await okur.readexactly(int.from_bytes(bas[3:5], 'big'))
            for parca in bol(bas + govde, ad):
                u_yazar.write(parca)
                await u_yazar.drain()
        else:
            u_yazar.write(bas)

        sayac = [0, 0]
        await asyncio.gather(aktar(okur, u_yazar, sayac, 0), aktar(u_okur, yazar, sayac, 1))
        yaz(f'{ad}:{port} kapandı ({sayac[0]} B gönderildi, {sayac[1]} B alındı)')
    except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, OSError, ValueError) as e:
        yaz(f'{ad} hata: {e.__class__.__name__} {e}')
    finally:
        for w in (yazar, u_yazar):
            if w:
                w.close()


def guncelleyiciyi_yonlendir() -> None:
    """Discord'un güncelleyicisi vekil ayarlarını dinlemeyen ayrı bir Rust modülü. Onu, Discord'un kendi
    ayar dosyasındaki NEW_UPDATE_ENDPOINT ile bu vekile yönlendiririz (Discord kapalıyken yazılmalı)."""
    ayar_yolu = Path(os.environ.get('APPDATA', '')) / 'discord' / 'settings.json'
    try:
        ayar = json.loads(ayar_yolu.read_text(encoding='utf-8')) if ayar_yolu.exists() else {}
    except ValueError:
        yaz('Discord settings.json okunamadı, dokunulmadı')
        return
    if ayar.get('NEW_UPDATE_ENDPOINT') == YERLI + '/':
        return
    yedek = ayar_yolu.with_name('settings.kapi-oncesi.json')
    if ayar_yolu.exists() and not yedek.exists():
        yedek.write_bytes(ayar_yolu.read_bytes())
    ayar['NEW_UPDATE_ENDPOINT'] = YERLI + '/'
    ayar_yolu.write_text(json.dumps(ayar, indent=2), encoding='utf-8')
    yaz('Discord güncelleyicisi vekile yönlendirildi')


def discord_ac(kapaliysa_ac: bool = True) -> None:
    """Discord'u vekille açar; vekilsiz açıksa kapatıp vekille yeniden açar."""
    if not DISCORD.exists():
        yaz(f'Discord bulunamadı: {DISCORD}')
        return
    komut = "(Get-CimInstance Win32_Process -Filter \"Name='Discord.exe'\").CommandLine -join ' '"
    calisan = subprocess.run(['powershell', '-NoProfile', '-Command', komut],
                             capture_output=True, text=True, creationflags=PENCERESIZ).stdout
    if '--proxy-server' in calisan or (not calisan.strip() and not kapaliysa_ac):
        return
    if calisan.strip():
        yaz('Discord vekilsiz açılmış (güncelleme sonrası ya da başlangıçtan), vekille yeniden açılıyor')
        subprocess.run(['taskkill', '/IM', 'Discord.exe', '/F'], capture_output=True, creationflags=PENCERESIZ)
        time.sleep(2)
    guncelleyiciyi_yonlendir()
    subprocess.Popen([str(DISCORD), '--processStart', 'Discord.exe', '--process-start-args', f'--proxy-server={YERLI}'],
                     creationflags=PENCERESIZ)
    yaz('Discord vekille açıldı')


def portu_tutan_biz_miyiz() -> bool:
    komut = (f"$p = (Get-NetTCPConnection -LocalAddress {ADRES} -LocalPort {PORT} -State Listen -ErrorAction "
             "SilentlyContinue | Select-Object -First 1).OwningProcess; "
             "if ($p) { (Get-CimInstance Win32_Process -Filter \"ProcessId=$p\").CommandLine }")
    satir = subprocess.run(['powershell', '-NoProfile', '-Command', komut],
                           capture_output=True, text=True, creationflags=PENCERESIZ).stdout
    return str(Path(__file__).resolve()).lower() in satir.lower()


async def ana(discord: bool) -> None:
    try:
        sunucu = await asyncio.start_server(baglanti, ADRES, PORT)
    except OSError:
        # Port doluysa dinleyenin gerçekten bu araç olduğunu doğrula: Discord'un güncelleyicisi bu porta
        # güveniyor, başka bir program portu kapmışsa Discord'u ona yönlendirme.
        if not await asyncio.to_thread(portu_tutan_biz_miyiz):
            yaz(f'{PORT} portunu başka bir program kullanıyor; güvenlik için Discord açılmadı')
            return
        sunucu = None  # vekil zaten çalışıyor; yalnız Discord'u aç
    else:
        GUNLUK.write_text('', encoding='utf-8')
        yaz(f'vekil {ADRES}:{PORT} üzerinde çalışıyor')
    if discord:
        await asyncio.to_thread(discord_ac)
    if sunucu:
        if discord:
            asyncio.create_task(bekci())
        async with sunucu:
            await sunucu.serve_forever()


async def bekci() -> None:
    """Discord bir güncellemeden sonra kendini vekilsiz yeniden başlatır; bunu yakalayıp düzeltir."""
    while True:
        await asyncio.sleep(15)
        await asyncio.to_thread(discord_ac, False)


if __name__ == '__main__':
    asyncio.run(ana(discord='--vekil' not in sys.argv))

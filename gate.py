"""Marlen Gate: Discord'u Türkiye'deki erişim engeline takılmadan açar.

Discord'u bu bilgisayarda çalışan küçük bir vekil (proxy) üzerinden açar. Vekil iki şey yapar:
1. Adresleri sağlayıcının DNS'i yerine şifreli DNS'ten (DoH) öğrenir. Sağlayıcının DNS'i
   discord.com için engel sayfasının adresini veriyor.
2. Her bağlantının ilk paketinde (TLS ClientHello) site adı açık yazılıdır; sağlayıcının DPI cihazı
   bağlantıyı bu adı görünce keser. Vekil bu paketi site adının ortasından iki TLS kaydına böler.
   Sunucu iki kaydı birleştirip normal okur, DPI ise adı tek parça göremez.
Şifreleme uçtan uca Discord ile kalır: vekil içeriği göremez, değiştirmez; yalnız aktarır.

Kullanım:
  Marlengate.exe  (ya da: pythonw gate.py)   vekili başlatır, Discord'u vekille açar; Discord kapanınca kendisi de kapanır
  --tarayici [adres]                          Chrome'u (yoksa Edge'i) vekille açar: mail doğrulama gibi discord.com sayfaları için
  --vekil                                     yalnız vekili başlatır (deneme için)
  --kaldir                                    Discord'un ayarını Gate'ten önceki haline döndürür, Başlat menüsü kısayollarını siler
İlk açılışta Başlat menüsüne "Marlen Gate" klasörü (Discord ve Tarayıcı kısayolları) eklenir.
"""
import asyncio
import base64
import ctypes
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ADRES, PORT = '127.0.0.1', int(os.environ.get('GATE_PORT', 18443))
YERLI = f'http://{ADRES}:{PORT}'
DISCORD_SUNUCU = re.compile(r'([a-z0-9-]+\.)*(discord\.com|discordapp\.net|discordapp\.com)')
# Güncelleyiciye giden HTTPS istekleri de bu vekilin CONNECT tünelinden (DoH + bölme) geçer
ACICI = urllib.request.build_opener(urllib.request.ProxyHandler({'https': YERLI, 'http': YERLI}))
# .exe olarak paketlenince __file__ her açılışta değişen geçici bir klasördedir; kimlik .exe'nin kendisidir
KIMLIK = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve()
VERI = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'MarlenGate'
GUNLUK = VERI / 'gate.log'
DOH = ('https://cloudflare-dns.com/dns-query?name={}&type=A', 'https://dns.google/resolve?name={}&type=A')
DISCORD = Path(os.environ.get('LOCALAPPDATA', '')) / 'Discord' / 'Update.exe'
AYAR = Path(os.environ.get('APPDATA', '')) / 'discord' / 'settings.json'
AYAR_YEDEK = AYAR.with_name('settings.kapi-oncesi.json')  # eski adıyla kalır: önceki sürümlerin yedeği
PENCERESIZ = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
BASLAT = Path(os.environ.get('APPDATA', '')) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Marlen Gate'
# Tarayıcı ayrı profille açılır: Chrome zaten açıksa yeni pencere eski sürecin ayarını alır ve --proxy-server yok sayılır
TARAYICI_PROFIL = VERI / 'tarayici'
TARAYICILAR = [Path(os.environ[k]) / yol for k, yol in (
    ('PROGRAMFILES', 'Google/Chrome/Application/chrome.exe'),
    ('PROGRAMFILES(X86)', 'Google/Chrome/Application/chrome.exe'),
    ('LOCALAPPDATA', 'Google/Chrome/Application/chrome.exe'),
    ('PROGRAMFILES(X86)', 'Microsoft/Edge/Application/msedge.exe'),
    ('PROGRAMFILES', 'Microsoft/Edge/Application/msedge.exe'),
) if k in os.environ]

_dns: dict[str, tuple[str, float]] = {}


def yaz(satir: str) -> None:
    VERI.mkdir(parents=True, exist_ok=True)
    with GUNLUK.open('a', encoding='utf-8') as f:
        f.write(f'{time.strftime("%d.%m %H:%M:%S")} {satir}\n')


def uyar(metin: str) -> None:
    """Konsolsuz çalışırken kullanıcıya hata göstermenin tek yolu: Windows ileti kutusu."""
    yaz(metin)
    try:
        ctypes.windll.user32.MessageBoxW(0, metin, 'Marlen Gate', 0x30)
    except (AttributeError, OSError):
        print(metin, file=sys.stderr)


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
    try:
        ayar = json.loads(AYAR.read_text(encoding='utf-8')) if AYAR.exists() else {}
    except ValueError:
        yaz('Discord settings.json okunamadı, dokunulmadı')
        return
    if ayar.get('NEW_UPDATE_ENDPOINT') == YERLI + '/':
        return
    if AYAR.exists() and not AYAR_YEDEK.exists():
        AYAR_YEDEK.write_bytes(AYAR.read_bytes())
    ayar['NEW_UPDATE_ENDPOINT'] = YERLI + '/'
    AYAR.parent.mkdir(parents=True, exist_ok=True)
    AYAR.write_text(json.dumps(ayar, indent=2), encoding='utf-8')
    yaz('Discord güncelleyicisi vekile yönlendirildi')


def yonlendirmeyi_kaldir() -> None:
    """Discord'un ayarından Gate'in güncelleyici yönlendirmesini çıkarır. Gate kapanırken de çağrılır:
    yönlendirme açık kalıp port boşalırsa güncelleyici, portu kapan herhangi bir programa güvenirdi."""
    if not AYAR.exists():
        return
    try:
        ayar = json.loads(AYAR.read_text(encoding='utf-8'))
    except ValueError:
        return
    if isinstance(ayar, dict) and ayar.get('NEW_UPDATE_ENDPOINT') == YERLI + '/':
        del ayar['NEW_UPDATE_ENDPOINT']
        AYAR.write_text(json.dumps(ayar, indent=2), encoding='utf-8')
        yaz('Discord güncelleyicisinin yönlendirmesi kaldırıldı')


def kaldir() -> None:
    yonlendirmeyi_kaldir()
    AYAR_YEDEK.unlink(missing_ok=True)
    shutil.rmtree(BASLAT, ignore_errors=True)
    uyar("Discord'un ayarı eski haline döndü, Başlat menüsü kısayolları silindi. Gate'i artık silebilirsin.")


def kisayollari_kur() -> None:
    """Başlat menüsüne Discord ve Tarayıcı kısayolları. Her açılışta yeniden yazılır: .exe taşınırsa
    kısayollar yeni yerini gösterir."""
    if getattr(sys, 'frozen', False):
        hedef, on_arg, simge = KIMLIK, '', KIMLIK
    else:
        hedef, on_arg, simge = Path(sys.executable).with_name('pythonw.exe'), f'"{KIMLIK}" ', KIMLIK.with_name('gate.ico')

    def q(metin: object) -> str:  # PowerShell tek tırnaklı metin
        return "'" + str(metin).replace("'", "''") + "'"

    BASLAT.mkdir(parents=True, exist_ok=True)
    # WScript.Shell dosya adını sistemin ANSI kod sayfasıyla yazar ("Tarayıcı" İngilizce Windows'ta "Tarayici" olur):
    # kısayol düz adla kaydedilip Unicode adına taşınır
    betik = '$s = New-Object -ComObject WScript.Shell; ' + ''.join(
        f'$k = $s.CreateShortcut({q(BASLAT / f"gate-{i}.lnk")}); $k.TargetPath = {q(hedef)}; $k.Arguments = {q(on_arg + arg)}; '
        f'$k.IconLocation = {q(f"{simge},0")}; $k.Description = {q(aciklama)}; $k.Save(); '
        f'Move-Item -LiteralPath {q(BASLAT / f"gate-{i}.lnk")} -Destination {q(BASLAT / ad)} -Force; '
        for i, (ad, arg, aciklama) in enumerate((
            ('Discord (Marlen Gate).lnk', '', "Discord'u Marlen Gate ile açar"),
            ('Tarayıcı (Marlen Gate).lnk', '--tarayici', "discord.com sayfalarını (mail doğrulama vb.) Marlen Gate ile açar"),
        )))
    # -EncodedCommand (UTF-16): komut satırından geçen Türkçe harfler (Tarayıcı, Şükrü gibi kullanıcı adları) bozulmasın
    kodlu = base64.b64encode(betik.encode('utf-16-le')).decode()
    subprocess.run(['powershell', '-NoProfile', '-EncodedCommand', kodlu], capture_output=True, creationflags=PENCERESIZ)


def tarayici_ac(adres: str) -> bool:
    """Chrome'u, yoksa Windows'la gelen Edge'i, Gate'in ayrı profiliyle ve vekille açar."""
    exe = next((p for p in TARAYICILAR if p.exists()), None)
    if exe is None:
        return False
    subprocess.Popen([str(exe), f'--user-data-dir={TARAYICI_PROFIL}', f'--proxy-server={YERLI}',
                      '--no-first-run', '--no-default-browser-check', adres])
    yaz(f'tarayıcı vekille açıldı: {exe.name}')
    return True


def tarayici_acik() -> bool:
    komut = "(Get-CimInstance Win32_Process -Filter \"Name='chrome.exe' or Name='msedge.exe'\").CommandLine -join ' '"
    calisan = subprocess.run(['powershell', '-NoProfile', '-Command', komut],
                             capture_output=True, text=True, creationflags=PENCERESIZ).stdout
    return str(TARAYICI_PROFIL).lower() in calisan.lower()


def discord_durumu() -> str:
    """'yok', 'vekilli' ya da 'vekilsiz'."""
    komut = "(Get-CimInstance Win32_Process -Filter \"Name='Discord.exe'\").CommandLine -join ' '"
    calisan = subprocess.run(['powershell', '-NoProfile', '-Command', komut],
                             capture_output=True, text=True, creationflags=PENCERESIZ).stdout
    if not calisan.strip():
        return 'yok'
    return 'vekilli' if '--proxy-server' in calisan else 'vekilsiz'


def discord_ac(kapaliysa_ac: bool = True) -> str:
    """Discord'u vekille açar; vekilsiz açıksa kapatıp vekille yeniden açar. Son durumu döner."""
    durum = discord_durumu()
    if durum == 'vekilli' or (durum == 'yok' and not kapaliysa_ac):
        return durum
    if durum == 'vekilsiz':
        yaz('Discord vekilsiz açılmış (güncelleme sonrası ya da başlangıçtan), vekille yeniden açılıyor')
        subprocess.run(['taskkill', '/IM', 'Discord.exe', '/F'], capture_output=True, creationflags=PENCERESIZ)
        time.sleep(2)
    guncelleyiciyi_yonlendir()
    subprocess.Popen([str(DISCORD), '--processStart', 'Discord.exe', '--process-start-args', f'--proxy-server={YERLI}'],
                     creationflags=PENCERESIZ)
    yaz('Discord vekille açıldı')
    return 'vekilli'


def portu_tutan_biz_miyiz() -> bool:
    komut = (f"$p = (Get-NetTCPConnection -LocalAddress {ADRES} -LocalPort {PORT} -State Listen -ErrorAction "
             "SilentlyContinue | Select-Object -First 1).OwningProcess; "
             "if ($p) { (Get-CimInstance Win32_Process -Filter \"ProcessId=$p\").CommandLine }")
    satir = subprocess.run(['powershell', '-NoProfile', '-Command', komut],
                           capture_output=True, text=True, creationflags=PENCERESIZ).stdout
    return str(KIMLIK).lower() in satir.lower()


async def bekci(sunucu: asyncio.base_events.Server, discord_acildi: bool) -> None:
    """Gate'i açık tutan iki şey var: vekille açılmış Discord ve Gate'in tarayıcısı.
    Discord bir güncellemeden sonra kendini vekilsiz yeniden başlatır; vekille açıldığını gördüysek düzeltiriz
    (kullanıcının Gate'siz açtığı Discord'a yalnız tarayıcı için açılmış Gate dokunmaz).
    İkisi de bir dakikadan uzun süre kapalı kalırsa Gate de kapanır."""
    yok_sayisi = 0
    while True:
        await asyncio.sleep(15)
        durum = await asyncio.to_thread(discord_durumu)
        discord_acildi = discord_acildi or durum == 'vekilli'
        if discord_acildi and durum == 'vekilsiz':
            durum = await asyncio.to_thread(discord_ac, False)
        tarayici = await asyncio.to_thread(tarayici_acik)
        yok_sayisi = yok_sayisi + 1 if durum == 'yok' and not tarayici else 0
        if yok_sayisi >= 4:
            yaz('Discord ve tarayıcı kapandı, Gate de kapanıyor')
            await asyncio.to_thread(yonlendirmeyi_kaldir)  # Discord kapalı; bir sonraki açılışta yeniden yazılır
            sunucu.close()
            return


async def ana(mod: str, adres: str = 'https://discord.com/app') -> None:
    """mod: 'discord' (varsayılan), 'tarayici' ya da 'vekil'."""
    if mod == 'discord' and not DISCORD.exists():
        uyar(f'Discord bulunamadı ({DISCORD}).\nÖnce Discord\'u kur, sonra Gate\'i yeniden aç.')
        return
    try:
        sunucu = await asyncio.start_server(baglanti, ADRES, PORT)
    except OSError:
        # Port doluysa dinleyenin gerçekten bu araç olduğunu doğrula: Discord'un güncelleyicisi bu porta
        # güveniyor, başka bir program portu kapmışsa Discord'u ona yönlendirme.
        if not await asyncio.to_thread(portu_tutan_biz_miyiz):
            uyar(f'{PORT} numaralı portu başka bir program kullanıyor; güvenlik için açılmadı.')
            return
        sunucu = None  # Gate zaten çalışıyor; yalnız Discord'u ya da tarayıcıyı aç
    else:
        VERI.mkdir(parents=True, exist_ok=True)
        GUNLUK.write_text('', encoding='utf-8')
        yaz(f'vekil {ADRES}:{PORT} üzerinde çalışıyor')
    if mod == 'discord':
        await asyncio.to_thread(discord_ac)
    elif mod == 'tarayici' and not await asyncio.to_thread(tarayici_ac, adres):
        uyar('Chrome ya da Edge bulunamadı.')
        if sunucu is None:
            return
    if mod != 'vekil':
        await asyncio.to_thread(kisayollari_kur)
    if sunucu:
        if mod != 'vekil':
            asyncio.create_task(bekci(sunucu, discord_acildi=mod == 'discord'))
        async with sunucu:
            try:
                await sunucu.serve_forever()
            except asyncio.CancelledError:
                pass


if __name__ == '__main__':
    if '--kaldir' in sys.argv:
        kaldir()
    elif '--tarayici' in sys.argv:
        sonraki = sys.argv[sys.argv.index('--tarayici') + 1:]
        asyncio.run(ana('tarayici', *[a for a in sonraki[:1] if a.startswith(('https://', 'http://'))]))
    else:
        asyncio.run(ana('vekil' if '--vekil' in sys.argv else 'discord'))

# Marlen Kapı

Discord'u Türkiye'deki erişim engeline takılmadan açan küçük, açık kaynak bir Windows aracı.
VPN değildir, internet trafiğinin geri kalanına dokunmaz; yalnız Discord'u kendi üzerinden geçirir.

> Discord, Inc. ile bir bağlantısı yoktur. Kullanım sorumluluğu kullanıcıya aittir.

## Kullanım

1. [Releases](../../releases) sayfasından `MarlenKapi.exe` dosyasını indir.
2. Çift tıkla. Kapı arka planda açılır ve Discord'u kendi üzerinden başlatır.
3. Discord'u bundan sonra hep `MarlenKapi.exe` ile aç. Discord tamamen kapanınca Kapı da bir dakika içinde kendiliğinden kapanır.

Windows "bilinmeyen yayımcı" uyarısı gösterirse **Ek bilgi > Yine de çalıştır**'a bas. Dosya imzalı değil;
kaynak kodu bu depoda, istersen `.exe` yerine doğrudan Python ile de çalıştırabilirsin (aşağıda).

Discord açılmadan önce kapalıysa sorun yok. Açıksa Kapı onu kapatıp kendi üzerinden yeniden açar.

## Nasıl çalışıyor

Engel iki katmanda:

1. **DNS:** Sağlayıcının DNS sunucusu `discord.com` için gerçek adres yerine engel sayfasının adresini veriyor.
   Kapı adresleri şifreli DNS'ten (Cloudflare ve Google DoH) öğrenir.
2. **SNI / DPI:** Her HTTPS bağlantısının ilk paketinde (TLS ClientHello) gidilen sitenin adı açık yazılıdır.
   Sağlayıcının DPI cihazı bu adı görünce bağlantıyı keser. Kapı bu paketi, site adının tam ortasından
   **iki ayrı TLS kaydına** böler. Discord'un sunucusu iki kaydı birleştirip normal okur; DPI cihazı adı tek
   parça göremez. (Aynı paketi yalnız TCP'de bölmek işe yaramıyor, cihaz TCP parçalarını birleştiriyor.)

Kapı bilgisayarında `127.0.0.1:18443` adresinde dinleyen küçük bir vekildir (proxy). Discord'u
`--proxy-server` ile bu vekile bağlar. Bağlantılar uçtan uca şifreli kalır: Kapı içeriği göremez ve değiştirmez,
yalnız aktarır. Hiçbir veri toplamaz, hiçbir yere göndermez; tek dış istek DNS sorgularıdır.

**Discord'un güncelleyicisi:** Discord'un güncelleme modülü vekil ayarını dinlemeyen ayrı bir programdır.
Kapı bu yüzden Discord'un kendi ayar dosyasına (`%APPDATA%\discord\settings.json`) `NEW_UPDATE_ENDPOINT`
ekleyerek güncelleyiciyi de kendine yönlendirir. Güncelleme dosyalarını Discord'un sunucularından şifreli
bağlantıyla çeker; indirilen her dosyayı Discord yine kendi sha256 kontrolüyle doğrular. Kapı kapanırken bu
satırı geri siler, Discord'u bir sonraki açışında yeniden ekler.

## Kaldırma

Discord'u Kapı'sız kullanmaya dönmek için önce `MarlenKapi.exe --kaldir` çalıştır (Discord'un ayarını eski
haline döndürür), sonra `.exe` dosyasını sil. Günlük dosyası `%LOCALAPPDATA%\MarlenKapi` klasöründedir.

## Python ile çalıştırma

Python 3.11+ yeterli, ek paket gerekmez:

```
pythonw kapi.py           # Kapı + Discord
python kapi.py --vekil    # yalnız vekil (deneme)
python kapi.py --kaldir   # Discord ayarını geri al
```

`.exe` dosyasını kendin üretmek için: `pip install pyinstaller` ve
`pyinstaller --onefile --noconsole --name MarlenKapi --icon kapi.ico kapi.py`.

## Bilinen sınırlar

- Türk Telekom bağlantısında denendi. Başka sağlayıcılar farklı yöntemle engelliyor olabilir; çalışmazsa
  sağlayıcını yazarak bir [Issue](../../issues) aç.
- Yalnız Windows ve Discord'un normal sürümü (PTB/Canary değil).
- Sesli sohbet (UDP) Kapı'dan geçmez, doğrudan gider; şu an engellenmediği için çalışır.

---

## English

Marlen Kapı is a tiny open-source Windows helper that opens Discord despite the access block in Turkey.
It is not a VPN: it runs a local proxy on `127.0.0.1:18443`, resolves Discord hosts over DNS-over-HTTPS and
splits the TLS ClientHello into two TLS records right in the middle of the SNI hostname, which the ISP's DPI
fails to reassemble. Traffic stays end-to-end encrypted. Discord's Rust updater ignores proxy settings, so Kapı
points it at itself through `NEW_UPDATE_ENDPOINT` in Discord's `settings.json` (revert with `--kaldir`).
Not affiliated with Discord, Inc. MIT licensed.

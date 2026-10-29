# Marlen Gate

Discord'u Türkiye'deki erişim engeline takılmadan açan küçük, açık kaynak bir Windows aracı.
VPN değildir, internet trafiğinin geri kalanına dokunmaz; yalnız Discord'u kendi üzerinden geçirir.

> Discord, Inc. ile bir bağlantısı yoktur. Kullanım sorumluluğu kullanıcıya aittir.

## Kullanım

1. [Releases](../../releases) sayfasından `Marlengate.exe` dosyasını indir.
2. Çift tıkla. Gate arka planda açılır ve Discord'u kendi üzerinden başlatır.
   Discord kurulu değilse Gate sorar: **Evet** dersen Discord'un resmi kurulum dosyasını kendi üzerinden indirir
   (Discord'un indirme sayfası da engelli), dosyanın Discord Inc. imzalı olduğunu doğrular ve kurar.
3. Discord'u bundan sonra hep `Marlengate.exe` ile ya da Başlat menüsündeki **Marlen Gate > Discord** ile aç.
   Discord tamamen kapanınca Gate de bir dakika içinde kendiliğinden kapanır.

**discord.com sayfaları (mail doğrulama, şifre sıfırlama, geliştirici sayfası):** Başlat menüsünden
**Marlen Gate > Tarayıcı**'yı aç ve bağlantıyı o pencereye yapıştır. Chrome'u (yoksa Windows'la gelen Edge'i)
Gate üzerinden, normal tarayıcından ayrı bir profille açar; pencereyi kapatınca Gate de kapanır.

Windows "bilinmeyen yayımcı" uyarısı gösterirse **Ek bilgi > Yine de çalıştır**'a bas. Dosya imzalı değil;
kaynak kodu bu depoda, istersen `.exe` yerine doğrudan Python ile de çalıştırabilirsin (aşağıda).

Discord açılmadan önce kapalıysa sorun yok. Açıksa Gate onu kapatıp kendi üzerinden yeniden açar.

## Nasıl çalışıyor

Engel iki katmanda:

1. **DNS:** Sağlayıcının DNS sunucusu `discord.com` için gerçek adres yerine engel sayfasının adresini veriyor.
   Gate adresleri şifreli DNS'ten (Cloudflare ve Google DoH) öğrenir.
2. **SNI / DPI:** Her HTTPS bağlantısının ilk paketinde (TLS ClientHello) gidilen sitenin adı açık yazılıdır.
   Sağlayıcının DPI cihazı bu adı görünce bağlantıyı keser. Gate bu paketi, site adının tam ortasından
   **iki ayrı TLS kaydına** böler. Discord'un sunucusu iki kaydı birleştirip normal okur; DPI cihazı adı tek
   parça göremez. (Aynı paketi yalnız TCP'de bölmek işe yaramıyor, cihaz TCP parçalarını birleştiriyor.)

Gate bilgisayarında `127.0.0.1:18443` adresinde dinleyen küçük bir vekildir (proxy). Discord'u
`--proxy-server` ile bu vekile bağlar. Bağlantılar uçtan uca şifreli kalır: Gate içeriği göremez ve değiştirmez,
yalnız aktarır. Hiçbir veri toplamaz, hiçbir yere göndermez; tek dış istek DNS sorgularıdır.

**Discord'un güncelleyicisi:** Discord'un güncelleme modülü vekil ayarını dinlemeyen ayrı bir programdır.
Gate bu yüzden Discord'un kendi ayar dosyasına (`%APPDATA%\discord\settings.json`) `NEW_UPDATE_ENDPOINT`
ekleyerek güncelleyiciyi de kendine yönlendirir. Güncelleme dosyalarını Discord'un sunucularından şifreli
bağlantıyla çeker; indirilen her dosyayı Discord yine kendi sha256 kontrolüyle doğrular. Gate kapanırken bu
satırı geri siler, Discord'u bir sonraki açışında yeniden ekler.

## Kaldırma

Discord'u Gate'siz kullanmaya dönmek için önce `Marlengate.exe --kaldir` çalıştır (Discord'un ayarını eski
haline döndürür, Başlat menüsü kısayollarını siler), sonra `.exe` dosyasını sil. Günlük dosyası ve tarayıcı
profili `%LOCALAPPDATA%\MarlenGate` klasöründedir.

## Python ile çalıştırma

Python 3.11+ yeterli, ek paket gerekmez:

```
pythonw gate.py           # Gate + Discord
pythonw gate.py --tarayici [adres]   # Gate + tarayıcı (discord.com sayfaları için)
python gate.py --vekil    # yalnız vekil (deneme)
python gate.py --kaldir   # Discord ayarını geri al
```

`.exe` dosyasını kendin üretmek için: `pip install pyinstaller` ve
`pyinstaller --onefile --noconsole --name Marlengate --icon gate.ico gate.py`.
Sürümlerdeki `.exe` dosyaları GitHub Actions'ta bu depodaki koddan derlenir ([derle.yml](.github/workflows/derle.yml)).

## Bilinen sınırlar

- Türk Telekom bağlantısında denendi. Başka sağlayıcılar farklı yöntemle engelliyor olabilir; çalışmazsa
  sağlayıcını yazarak bir [Issue](../../issues) aç.
- Yalnız Windows ve Discord'un normal sürümü (PTB/Canary değil).
- Sesli sohbet (UDP) Gate'ten geçmez, doğrudan gider; şu an engellenmediği için çalışır.

## Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by
[SignPath Foundation](https://signpath.org/). *(Başvuru aşamasında; onaylanana kadar sürümler imzasızdır.
Application pending; releases are unsigned until approved.)*

- Committers and reviewers: [Marlen](https://github.com/marlensahin)
- Approvers: [Marlen](https://github.com/marlensahin)

Her sürüm bu depodaki kaynak koddan GitHub Actions ile derlenir ve imzalanmadan önce elle onaylanır.
Every release is built from this repository by GitHub Actions and manually approved before signing.

**Gizlilik / Privacy:** Gate veri toplamaz ve hiçbir yere göndermez. Kendi yaptığı tek dış istek, Discord
sunucu adlarının şifreli DNS sorgusudur ([Cloudflare 1.1.1.1](https://developers.cloudflare.com/1.1.1.1/privacy/public-dns-resolver/),
[Google Public DNS](https://developers.google.com/speed/public-dns/privacy)); Discord trafiği uçtan uca
şifreli olarak Discord'a aktarılır. Gate collects no data; its only own outbound requests are DNS-over-HTTPS
lookups of Discord hostnames to the resolvers above.

**Sistem değişikliği / System change:** Gate, Discord'un `%APPDATA%\discord\settings.json` dosyasına
`NEW_UPDATE_ENDPOINT` satırını ekler ve kapanırken siler; Başlat menüsüne "Marlen Gate" klasörü ekler.
`Marlengate.exe --kaldir` her ikisini de geri alır.

---

## English

Marlen Gate is a tiny open-source Windows helper that opens Discord despite the access block in Turkey.
It is not a VPN: it runs a local proxy on `127.0.0.1:18443`, resolves Discord hosts over DNS-over-HTTPS and
splits the TLS ClientHello into two TLS records right in the middle of the SNI hostname, which the ISP's DPI
fails to reassemble. Traffic stays end-to-end encrypted. Discord's Rust updater ignores proxy settings, so Gate
points it at itself through `NEW_UPDATE_ENDPOINT` in Discord's `settings.json` (revert with `--kaldir`).
`--tarayici` opens Chrome (or Edge) through the same proxy with a separate profile, for discord.com pages such as
email verification; on first run Gate adds "Discord" and "Tarayıcı" shortcuts to a "Marlen Gate" Start menu folder.
If Discord is not installed, Gate asks, then downloads the official installer through the proxy (Discord's download
page is blocked too), verifies its Authenticode signature is Discord Inc.'s and runs it.
Not affiliated with Discord, Inc. MIT licensed.

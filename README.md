# Insomnia

Bilgisayarı belirlediğin süre boyunca uyanık tutan küçük bir Windows programı.
Süre dolunca istersen bilgisayarı kapatır, yeniden başlatır ya da hazırda bekletir.

Sürüm: 1.2.0

## Ne yapar

- **Süre:** 15 dk, 30 dk, 1 sa, 2 sa, süresiz (∞) ya da 1–1440 dakika arası özel süre.
- **Süre bitince:** bir şey yapma, bilgisayarı kapat, yeniden başlat, hazırda beklet.
- **Sesli uyarı:** süre dolunca iki kısa bip.
- **Ekranı kapat:** düğmeyle ya da oturum başlarken; ikisinde de 10 saniyelik, vazgeçilebilir geri sayım.
- **Tepsi simgesi (saatin yanı):** ay simgesi. Hazırken gri; çalışırken altın ve çevresinde kalan süreyi gösteren halka; son dakikalarda bitiş işleminin rengi.
  Menüsünde hızlı başlatma, durdurma, Windows açılışında çalıştırma, dil ve çıkış var.
- **Diller:** Türkçe, İngilizce, Almanca, Fransızca, İspanyolca.

## Bilmen gereken davranışlar

- Kapatma, yeniden başlatma ve hazırda bekletmeden önce **60 saniyelik uyarı** çıkar; pencere öne gelir, ekran
  kapalıysa açılır. "Vazgeç"e basılırsa işlem yapılmaz.
- Kapatma ve yeniden başlatma açık programları zorla kapatır (`shutdown /f`); kaydedilmemiş işler kaybolur.
- **Bitiş işlemi hatırlanmaz.** Program her açılışta "Bir şey yapma" ile başlar.
- **Tepsiden hızlı başlatma** yalnız uyanık tutar; bitişte hiçbir işlem yapmaz.
- Oturum sürerken bilgisayar elle uyutulursa oturum **bitiş işlemi yapılmadan** durur.
- Pencereyi kapatmak (×) programı kapatmaz, tepsiye gizler. Çıkış tepsi menüsündedir.
- **Ayarlar (dişli):** programın nerede görüneceği (saatin yanı + görev çubuğu, yalnız saatin yanı, yalnız görev çubuğu), dil ve Windows açılışında çalıştırma. "Yalnız görev çubuğunda" seçiliyken tepsi simgesi yoktur; × oturum sürerken pencereyi küçültür, boştayken programı kapatır.
- Windows kapanırken ya da oturum kapatılırken program kapanmayı engellemez.
- Ayarlar `%APPDATA%\Insomnia\settings.json` dosyasında durur.

## Çalıştırma

```
pip install -r requirements.txt
python main.py           # pencereyle
python main.py --tray    # yalnız tepsi simgesiyle
```

Windows 10/11 ve Microsoft Edge WebView2 gerekir (Windows 11'de hazır gelir).

## Dışarıdan yönetme (kumanda kapısı)

Program açıkken başka programlar onu yönetebilir. Ulanzi D200 eklentisi bunu kullanır
(bu depoda `ulanzi` klasöründe; kurulumu oradaki README anlatır).

Komut satırından:

```
Insomnia.exe --baslat 60                    # 60 dakikalık oturum (0 = süresiz); program kapalıysa tepside açar
Insomnia.exe --baslat 60 --islem shutdown   # bitince kapat (restart, hibernate)
Insomnia.exe --durdur
Insomnia.exe --ekran-kapat
```

Programdan: `%LOCALAPPDATA%\Insomnia\kumanda.json` dosyasında kapı numarası (`port`) ve
anahtar (`token`) yazar. Sunucu yalnız 127.0.0.1'i dinler; her istek anahtarı
`X-Insomnia-Anahtar` başlığında taşımalıdır. Tarayıcıdan gelen istekler (Origin başlığı
olanlar) reddedilir.

- `GET /durum` oturum durumunu verir.
- `POST /komut` gövdesi `{"komut": "..."}`: `start` (`minutes`, `infinite`, `action`), `stop`,
  `cancel` (uyarıda vazgeç), `act_now` (uyarıda beklemeden yap), `adjust` (`seconds`; çalışan
  oturuma süre ekler ya da çıkarır), `set_action` (`action`; çalışan oturumun bitişini
  değiştirir), `screen_off`, `cancel_screen_off`, `show`.

## Derleme

```
python build.py
```

`dist\Insomnia.exe` oluşur (tek dosya). Sürüm numarası `insomnia/__init__.py` içindeki `__version__` değeridir.

## Sınama

```
python -m unittest discover -s tests
```

Deneme sırasında bilgisayarın gerçekten kapanmaması için:

```
set INSOMNIA_DRY_RUN=1
```

Bu değişken varken kapatma, yeniden başlatma, hazırda bekletme ve ekran kapatma yapılmaz.

## Dosyalar

| Dosya | İş |
| --- | --- |
| `main.py` | Başlatıcı; tek kopya denetimi |
| `insomnia/app.py` | Pencere, tepsi ve zamanlayıcıyı bağlar; arayüzün çağırdığı işlemler |
| `insomnia/engine.py` | Oturum zamanlayıcısı (tek iş parçacığı) |
| `insomnia/remote.py` | Kumanda kapısı ve komut satırı istemcisi |
| `ulanzi/` | Ulanzi D200 eklentisi (Node.js); programdan bağımsız kurulur |
| `insomnia/power.py` | Uyanık tutma, ekran, kapatma işlemleri |
| `insomnia/settings.py` | Ayar dosyası |
| `insomnia/startup.py` | Windows açılışında çalıştırma kaydı |
| `insomnia/single_instance.py` | İkinci kopya açılınca ilkinin penceresini gösterme |
| `insomnia/tray.py`, `insomnia/icons.py` | Tepsi simgesi, menüsü ve ay çizimi |
| `insomnia/i18n.py` | Beş dilde metinler |
| `insomnia/ui/index.html` | Arayüz (HTML, CSS, JavaScript tek dosyada) |
| `tests/` | Zamanlayıcı, ayar ve çeviri sınamaları |
| `build.py` | exe derleme |

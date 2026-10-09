# Oyun Çeviri Aracı (Japonca / Korece / İngilizce → Türkçe)

Metin tabanlı oyunlarda ve görsel romanlarda ekrandaki **Japonca, Korece ya da İngilizce**
yazıyı Türkçeye çevirip orijinal yazının üstüne çizen, **tamamen offline** çalışan bir Windows
masaüstü uygulaması. Çıkış dili her zaman Türkçedir; kaynak dil oyuna göre seçilir.

- Çeviri: NLLB-200 (distilled 1.3B ya da 600M), CTranslate2, int8, **yalnızca CPU**
- OCR: Windows dahili OCR (varsayılan) ya da PaddleOCR (isteğe bağlı)
- Overlay: PyQt6, çerçevesiz, her zaman üstte, tıklamaları oyuna geçirir, ekran yakalamaya girmez

## Kurulum

Gerekenler: Windows 10 (2004 ve sonrası) / 11, **Python 3.11** (64 bit), internet (yalnızca kurulumda).

```powershell
py -3.11 setup.py
```

`setup.py` şunları yapar:

1. Proje içinde `venv` oluşturur, bağımlılıkları kurar.
2. Sistem RAM'ini ölçer: 12 GB ve üstüyse NLLB 1.3B, altındaysa NLLB 600M seçer
   (`--model 600M` ile elle seçilebilir).
3. Modeli Hugging Face'ten indirir, CTranslate2 int8 biçimine dönüştürür
   (`models/nllb-<boyut>-ct2-int8/`), ham modeli siler. Dönüşüm için geçici olarak CPU'luk
   `torch` ve `transformers` kurulur; uygulama çalışırken bunlar kullanılmaz.
4. Noto Sans fontunu `assets/` altına indirir.
5. Seçimi `settings.json` dosyasına yazar.
6. Windows OCR'ın Japonca, Korece ve İngilizce desteğini kontrol eder; eksik olan için
   çalıştırmanız gereken komutu yazar.

PaddleOCR'ı da kurmak için (isteğe bağlı, ~1 GB; üç dilin modelleri `models/paddle/<dil>/`
altına iner, bağlantı koparsa 5 kez yeniden denenir):

```powershell
py -3.11 setup.py --paddle
```

Sonra `settings.json` içinde `"ocr_engine": "paddle"` yapın.

**Japonca için Sugoi (önerilir):** NLLB'nin Japoncası zayıf. Sugoi Japonca→İngilizce modelini
kurarsanız Japonca metin önce Sugoi ile İngilizceye, sonra NLLB ile Türkçeye çevrilir; anlam,
isimler ve hitaplar (senpai, -chan) çok daha doğru çıkar. Tamamen yerelde çalışır, kayıt tutmaz.

```powershell
py -3.11 setup.py --sugoi
```

Lisans: NTT JParaCrawl, **yalnızca araştırma amaçlı kullanım, ticari kullanım yasak**;
indirmek şartları kabul etmek sayılır (`models/sugoi-v4-ja-en-ct2/LICENSE`). Model yoksa
uygulama uyarır ve NLLB ile devam eder. Kapatmak için `settings.json` → `"ja_model": "nllb"`.

Makinenizde Python 3.11 yoksa python.org'dan kurabilir ya da yönetici yetkisi gerektirmeyen
şu yolu kullanabilirsiniz: `pip install --user uv`, `python -m uv python install 3.11`,
sonra o Python ile `setup.py`'yi çalıştırın.

### Windows OCR dil paketleri

Serbest konum modunda, oyunun dili için gereklidir. Yoksa uygulama açılışta uyarır.
**Yönetici** PowerShell'de yalnızca ihtiyacınız olanı çalıştırın:

```powershell
Add-WindowsCapability -Online -Name "Language.OCR~~~ja-JP~0.0.1.0"   # Japonca
Add-WindowsCapability -Online -Name "Language.OCR~~~ko-KR~0.0.1.0"   # Korece
Add-WindowsCapability -Online -Name "Language.OCR~~~en-US~0.0.1.0"   # İngilizce
```

## İlk çalıştırma

Proje klasöründeki **`baslat.bat`** dosyasına çift tıklayın. Ya da PowerShell'de, **proje
klasörüne geçtikten sonra**:

```powershell
cd "<proje klasörü>"
venv\Scripts\python.exe -m src.app
```

1. Oyunu **önce** açın, sonra uygulamayı başlatıp açık pencerelerin listesinden oyunu seçin.
2. **Oyunun dilini** seçin: Japonca, Korece ya da İngilizce. Çeviri her zaman Türkçeye yapılır.
   Seçilen dilde olmayan metinler atlanır (ör. Japonca oyunda ekrandaki "HP 100" çevrilmez;
   İngilizce oyunda başka programda kopyaladığınız Japonca metin çevrilmez).
3. Modu seçin (varsayılan: Serbest konum):
   - **Sabit kutu**: diyalog kutusu hep aynı yerdeyse. Metin panodan gelir (Textractor).
     OCR ve ekran yakalama çalışmaz.
   - **Serbest konum**: yazılar ekranın farklı yerlerinde çıkıyorsa. Ekran yakalanır, OCR yapılır,
     her yazı bloğunun üstüne çeviri çizilir.
4. `Ctrl+Alt+E` ile düzenleme moduna girip sabit kutunun yerini/boyutunu ya da serbest modda
   taranacak alanı ayarlayın. Mod, dil ve kutu/alan, pencere başlığına göre profil olarak
   kaydedilir; aynı oyunu tekrar seçince otomatik gelir.

Hazır olunca ekranın üst ortasında bildirim çıkar; başlatan terminale de durum satırları yazılır
(ör. `[çeviri] Ekran değişti, OCR: 2 Japonca blok (61 ms)`). Metnin kendisi yazılmaz.

Seçim penceresini atlamak için:
`venv\Scripts\python.exe -m src.app --window "Oyun Başlığı" --mode free --lang ko`

## Resim modu (bilgisayardaki resimler)

Seçim ekranında **Klasör aç...** ya da **Resim aç...** düğmesine basın (önce resimlerdeki dili
seçin). Bir resim seçerseniz bulunduğu klasördeki diğer resimler de sırayla gezilebilir. Bir
klasörü `baslat.bat` üstüne sürükleyip bırakmak ya da görüntüleyici penceresine resim/klasör
sürüklemek de olur.

- OCR ekrandan değil, resim dosyasından tam çözünürlükte yapılır; resmin her yerindeki farklı
  boyutlardaki yazılar ayrı ayrı bulunup üstlerine çevirileri çizilir.
- Siz bir resme bakarken sıradaki resimler arka planda çevrilir; tıklayınca çoğunlukla hazır açılır.
- Çeviriler ve okunan metin diske yazılmaz, yalnızca bellekte tutulur. (Dosya seçme penceresi
  Windows'un kendisidir; Windows her uygulamada olduğu gibi son açılan dosya adlarını kendi
  listesinde tutar.)

| Tuş | İş |
|---|---|
| Sol tık / sağ ok / Boşluk / tekerlek aşağı | Sonraki resim |
| Sağ tık / sol ok / tekerlek yukarı | Önceki resim |
| Home / End | İlk / son resim |
| O | Orijinal ↔ çeviri |
| F (F11) / Esc | Tam ekran / çık |
| S | Ayarlar (yazı tipi, punto, opaklık...) |

**Manga / dikey yazı:** Japonca resimlerde, `py -3.11 setup.py --paddle --manga` ile kurulduysa
otomatik olarak **manga OCR** kullanılır: yazı bölgeleri PaddleOCR'ın tespit kısmıyla bulunur,
aynı balondaki sütunlar birleştirilir, her balon manga-ocr (kha-white/manga-ocr-base, Apache-2.0)
ile okunur. Dikey yazıyı doğru sırayla okur, furigana'yı görmezden gelir. Sayfa başına birkaç
saniye sürer (siz okurken sonraki sayfalar arka planda hazırlanır). Eğik ya da süslü yazılar
(efekt sesleri) hâlâ hatalı okunabilir. İsimler için sözlük kullanın (ör. `"イルカ": "Iruka"`;
yoksa "yunus" diye çevrilir).

### Oyunu çerçevesiz pencere modunda açın

Overlay, oyunun **üstünde** ayrı bir pencere olarak çizilir. Tam ekran (exclusive fullscreen)
oyunlarda overlay görünmez ve ekran yakalama siyah kare alabilir. Oyunu **pencere** ya da
**çerçevesiz pencere (borderless windowed)** modunda çalıştırın.

## Textractor bağlama (sabit kutu modu)

1. [Textractor](https://github.com/Artikash/Textractor/releases)'ı indirip açın
   (oyunla aynı bit genişliğindeki sürüm: x86 ya da x64).
2. Oyunu başlatın. Textractor'da **Attach to game** ile oyunun sürecini seçin.
3. Açılır listeden diyalog metnini taşıyan iş parçacığını (thread) seçin; yeni replik geldikçe
   o satırda oyunun metni görünmelidir.
4. **Extensions** penceresinde **Copy to Clipboard** eklentisinin listede olduğundan emin olun
   (yoksa sağ tık → Add extension → `Copy to Clipboard.xdll`).
5. Bu uygulamayı sabit kutu modunda, oyunun dilini seçerek başlatın. Panoya o dilde metin
   geldikçe kutuda Türkçesi çıkar.

## Kısayollar

| Kısayol | İş |
|---|---|
| Ctrl+Alt+T | Overlay'i gizle/göster (gizliyken yakalama/çeviri durur) |
| Ctrl+Alt+R | O anki ekranı zorla yeniden çevir |
| Ctrl+Alt+E | Düzenleme modu (kutu/bölge taşı, boyutlandır); tekrar basınca kaydeder |
| Ctrl+Alt+M | Mod değiştir (sabit kutu ↔ serbest konum) |
| Ctrl+Alt+D | Debug göstergesi (yakalama, OCR, çeviri, çizim, toplam süre) |
| Ctrl+Alt+S | **Ayarlar**: yazı tipi, punto, kalın, yazı rengi, kutu opaklığı, tıklayınca silme, Japonca çeviri yöntemi (değişiklik ekrana anında yansır) |
| Ctrl+Alt+Q | Çıkış |

**Sahne ilerletme:** Serbest konum modunda oyunun içine sol tıkladığınızda ya da oyun öndeyken
Enter / Boşluk'a bastığınızda eski çeviri kutuları hemen kalkar; yeni yazı belirip durulunca yeni
çeviri gelir. Böylece aynı yerde çıkan yeni replik eski çevirinin altında kalmaz. Kapatmak için
`settings.json` → `"clear_on_click": false`.

Kısayollar `settings.json` → `hotkeys` altından değiştirilebilir (ör. `"Ctrl+Shift+F9"`).

**Öneri (yazılar hep aynı yerde çıkıyorsa):** serbest konum modunda `Ctrl+Alt+E` ile taranacak
alanı diyalog kutusunun etrafına çizin. Arka plan taranmaz; desenli ya da hareketli arka planda
OCR'ın sahte "yazı" okuması biter ve tarama hızlanır.

Düzenleme modunda:
- Sabit kutu: kutuyu sürükleyerek taşıyın, sağ alt köşedeki tutamaçtan boyutlandırın.
- Serbest konum: taranacak dikdörtgeni fareyle çizin; sağ tık sınırı kaldırır (tüm pencere taranır).

## Sözlük

Proje klasöründe `dictionary.json` (UTF-8):

```json
{
  "田中": "Tanaka",
  "桜井美咲": "Sakurai Misaki"
}
```

Anahtar her dilde olabilir (ör. Korece `"민수": "Minsu"`, İngilizce `"Senpai": "Senpai"`).
Çeviriden önce kaynak metindeki anahtarlar Latin harfli karşılıklarıyla değiştirilir
(uzun anahtar önce). Çıktıda bir düzeltme yapılmaz. Dosya değişince uygulama yeniden yükler ve
çeviri önbelleğini temizler.

## Ayarlar (`settings.json`)

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `model`, `model_dir` | setup.py yazar | Kullanılan NLLB modeli |
| `threads` | 0 | CPU iş parçacığı; 0 = çekirdek sayısının yarısı |
| `beam_size` | 2 | Çeviri ışın genişliği |
| `ja_model` | `"sugoi"` | Japonca: `"sugoi"` (Sugoi ja→en + NLLB en→tr; model yoksa NLLB) ya da `"nllb"` |
| `sugoi_compute` | `"float32"` | Sugoi hassasiyeti; `int8` bu modelde çeviriyi bozuyor |
| `pivot` | false | Kaynak→İngilizce→Türkçe iki adım (İngilizce oyunlarda etkisiz) |
| `ocr_engine` | `"windows"` | `"windows"` ya da `"paddle"` |
| `capture_fps` | 5 | Serbest modda saniyedeki yakalama |
| `diff_pixel_threshold`, `diff_min_pixels` | 30, 6 | Değişim eşiği (küçültülmüş gri karede) |
| `stable_ms` | 400 | Görüntü bu kadar sabit kalınca OCR çalışır |
| `confirm_ms` | 350 | Yazı hâlâ akıyorsa bu kadar sonra yeniden okunur; metin iki okumada aynı çıkmadan çevrilmez |
| `max_wait_ms` | 500 | Ekran hiç durulmasa da (hareketli sahne) en geç bu sürede bir OCR çalışır |
| `clear_on_click` | true | Serbest modda oyuna tıklayınca / Enter / Boşluk'ta çeviriyi sil |
| `font_max_px`, `font_min_px` | 28, 12 | Metin sığdırma punto sınırları |
| `hotkeys` | yukarıdaki tablo | Kısayollar |
| `profiles` | {} | Pencere başlığına göre mod, dil (`ja`/`ko`/`en`), kutu ve tarama alanı |

## Gizlilik

- Uygulama çalışırken hiçbir ağ çağrısı yapmaz; `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`,
  `HF_HUB_DISABLE_TELEMETRY` başlangıçta ayarlanır.
- Yakalanan görüntü, OCR çıktısı, kaynak metin ve çeviri yalnızca bellekte tutulur. Log dosyası yoktur.
- Diske yazılan tek şey `settings.json` (ve sizin yazdığınız `dictionary.json`).

## Testler

```powershell
venv\Scripts\python.exe -m pytest -v tests
```

- Birim testleri: önbellek, sözlük, cümle bölme, blok birleştirme, metin sığdırma, değişim tespiti.
- OCR testleri: Japonca, Korece ve İngilizce metni görüntüye çizip Windows OCR'dan ve
  PaddleOCR'dan geçirir (dil paketi / model yoksa atlanır).
- Uçtan uca testler (`tests/test_e2e.py`): `tools/fake_game.py` açılır, uygulama ağ erişimi
  kapalı halde (`tests/offline_launcher.py`) başlatılır. Fare imlecini, klavyeyi ve panoyu
  kullanır; çalışırken bilgisayara dokunmayın. Panodaki içeriğiniz değişir.
- Benchmark: `venv\Scripts\python.exe tools\benchmark.py [cumleler.txt] [--lang ja|ko|en]`

## Varsayımlar

- **Python 3.11**: geliştirme makinesinde yalnızca 3.12 vardı; 3.11, `uv` ile kullanıcı klasörüne
  (yönetici yetkisi olmadan) kuruldu ve venv onunla oluşturuldu.
- **RAM eşiği**: Windows 16 GB'lık makineyi ~15.7 GB, 12 GB'lık makineyi ~11.8 GB raporlar.
  "12 GB ve üstü" kuralını bozmamak için eşik 11.5 GB alındı.
- **Model dönüşümü** için `transformers<5` ve CPU'luk `torch` kurulum sırasında venv'e eklenir.
  Uygulama bunları import etmez; tokenizasyon doğrudan `sentencepiece` ile yapılır
  (kaynak: `[jpn_Jpan] + parçalar + </s>`, hedef öneki `tur_Latn`).
- **Çeviri ayarları**: `beam_size=2`, `repetition_penalty=1.1`, `max_decoding_length=256`;
  CPU iş parçacığı çekirdeklerin yarısı (oyuna pay kalsın).
- **Değişim eşiği**: "ortalama fark" tek bir harfin belirdiğini kaçırdığı için eşik, küçültülmüş
  (1/2) gri karede belirgin değişen piksel sayısı olarak tanımlandı.
- **İlk kare**: serbest mod başlarken ilk sabit kare de bir kez OCR'a gider.
- **Eski/yeni blok eşleştirme (5.2.4)**: her OCR sonrasında overlay o anki blokların tamamıyla
  değiştirilir. Yazı akmaya devam ettiyse (yeni metin eskisiyle başlıyorsa) eski çeviri böylece
  yenisiyle değişir; değişmeyen bloklar önbellekten gelir, yeniden çevrilmez. Ekrandan kalkan
  yazının kutusu da kalkar.
- **Sabit kutu rengi**: bu modda ekran yakalanmadığı için kenar rengi ölçülemez; kutu koyu gri
  (#18181C) ve yazı beyazdır.
- **Varsayılan sabit kutu**: profil yoksa pencerenin alt %24'ü, yanlardan %5 içeride.
- **Pano metni**: satır sonları kaldırılarak tek metin olarak çevrilir.
- **Dikey yazı**: bir satır kutusunun yüksekliği genişliğinin 2 katından fazlaysa dikey sayılır;
  dikey sütunlar sağdan sola birleştirilir. Türkçe çeviri yatay yazılır; dar sütuna sığmayacağı
  için kutu, sütunun ortasına hizalı en az 160 px genişliğe açılır.
- **Windows OCR küçük görüntüler**: 400 px'ten kısa yakalamalar OCR'dan önce 2 kat büyütülür.
- **Pencere kapanınca**: bildirim çıkar, overlay gizlenir, aynı başlıklı pencere yeniden
  açılırsa otomatik bağlanılır.
- **Mimari**: Win32 ctypes yardımcıları (pencere listesi, DPI, click-through, kısayol)
  `src/winapi.py` içinde toplandı; hem `capture` hem `overlay` kullanıyor.
- **ASCII dışı klasör yolları**: sentencepiece ve Paddle, "Masaüstü" gibi Türkçe karakterli
  mutlak yolları açamıyor. sentencepiece modeli bayt olarak, Paddle modelleri proje köküne
  göreli yolla yüklenir; proje istenen klasörde kalabilir.
- **OCR motoru** serbest moda geçilir geçilmez yüklenir (ilk karede değil). PaddleOCR'ın
  açılışı ~15-20 s sürer; bu sürede çıkan replikler çevrilmez.
- **Seçim penceresi** kendi sürecinin pencerelerini ve araç pencerelerini listelemez.
- **Korece / İngilizce** (SPEC'te yalnızca Japonca vardı; kullanıcı isteğiyle eklendi): dil
  oyun profiliyle seçilir, otomatik algılanmaz. Böylece OCR doğru dil motoruyla çalışır ve başka
  programlarda panoya kopyalanan farklı dildeki metinler (ör. bir link) çeviriyi tetiklemez.
  Korece/İngilizce cümleler `. ! ? …` ve ardından gelen boşluktan bölünür (`3.5` bölünmez);
  satırlar boşlukla birleştirilir; dikey yazı yalnızca Japoncada aranır. Metnin tamamını tek
  parça çevirmek NLLB'de cümle atlattığı için cümle cümle bölme korundu.
- **Sugoi float32**: Sugoi int8'e sıkıştırılınca soruları düz cümleye çeviriyor ("Where are you
  going?" yerine "I don't know where you're going") ve isim uyduruyordu (先輩 → "Aoi"). float32
  doğru çeviriyor; cümle başına ~190 ms (int8 ~30 ms). Sugoi'nin “ ” tırnakları ve ♪ işaretleri
  NLLB'de "⁇" çıktığı için İngilizce adımda sadeleştirilir.
- **Altyazı tiresi**: NLLB kısa cümlelerin başına "- " ekleyebiliyor; çıktının başındaki "- "
  silinir (içerik değiştirilmez, "-5" gibi sayılar korunur).
- **Hareketli sahneler**: SPEC 5.2'deki "400 ms sabit kalınca OCR" kuralı, arka planı ya da
  efekti sürekli hareket eden sahnelerde OCR'ı hiç çalıştırmıyordu (eski çeviri ekranda kalıyordu).
  Ekran durulmasa da en geç `max_wait_ms` (0.5 s) sonra OCR çalışır; yarım metni metin düzeyindeki doğrulama engeller.
- **Yarım metni çevirmeme**: yazı harf harf akarken (özellikle duraksayarak) piksel kuralı yarım
  metni OCR'a sokuyor, aynı replik için 2-3 farklı çeviri görünüyordu. Artık bir blok ancak art
  arda iki OCR okumasında aynı metinle görülünce çevrilir; metin uzuyorsa `confirm_ms` sonra
  yeniden okunur. Metin uzamadığı halde okuma her seferinde biraz farklıysa (OCR gürültüsü)
  4 turdan sonra son okuma kabul edilir. Bedeli: çeviri ~0.5 s geç gelir.
- **Tıklayınca silme** (kullanıcı isteği): tıklama, `GetAsyncKeyState` ile 25 ms'de bir yoklanır;
  yalnızca imlecin altındaki pencere oyunsa (fare) ya da oyun öndeyse (Enter/Boşluk) sayılır.
  Tıklamadan önce başlamış bir OCR'ın sonucu atılır, eski çeviri geri gelmez.
- **Varsayılan mod serbest konum**: Textractor gerektirmeden çalıştığı için. Seçilen mod ve dil
  açılışta profile kaydedilir.
- **Uçtan uca testler için** uygulamada gizli `--test-report` seçeneği var: stdout'a yalnızca
  kutu koordinatları ve süreleri basar (metin içeriği basılmaz, diske yazılmaz).

## Bilinen sınırlar

- Kaynak dil oyun başına seçilir; aynı ekranda karışık dilleri (ör. Japonca diyalog + İngilizce
  menü) birlikte çevirmez. Yalnızca seçilen dil çevrilir.

- **Tek monitör**: ilk sürümde yalnızca birincil monitör desteklenir; oyun penceresi başka
  monitördeyse ya da monitörler arası farklı ölçekleme varsa koordinatlar kayabilir.
- Exclusive fullscreen oyunlarda overlay görünmez (bkz. çerçevesiz pencere uyarısı).
- `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` Windows 10 2004 ve sonrası gerektirir.
  Daha eski sürümde overlay kendi çıktısını OCR'a sokabilir.
- Windows OCR basit, tek sütunlu dikey yazıyı testte okudu; karmaşık dikey düzenlerde
  (çok sütunlu, furigana'lı) zayıf kalabilir, o durumda PaddleOCR önerilir.
- PaddleOCR CPU'da Windows OCR'dan ~8 kat yavaş (kare başına ~0.5 s, Windows OCR ~0.06 s).
- Proje OneDrive klasöründeyse `models/` (~1.4 GB, Paddle ile ~1.6 GB) ve `venv/` de eşitlenmeye
  çalışılır. İsterseniz proje klasörünü OneDrive dışına taşıyın ya da bu klasörleri eşitlemeden
  hariç tutun.
- Hook metni ile OCR blokları eşleştirilmez; LLM backend'i, çoklu monitör, konuşmacı tespiti yoktur.
- NLLB bağlam kullanmaz; her replik bağımsız çevrilir. Özne düşmüş cümlelerde çeviri tahmindir.

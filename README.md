# Japonca → Türkçe Oyun Çeviri Aracı

Japonca metin tabanlı oyunlarda ve görsel romanlarda ekrandaki yazıyı Türkçeye çevirip
orijinal yazının üstüne çizen, **tamamen offline** çalışan bir Windows masaüstü uygulaması.

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
6. Windows OCR'ın Japonca desteğini kontrol eder; yoksa çalıştırmanız gereken komutu yazar.

PaddleOCR'ı da kurmak için (isteğe bağlı, ~1 GB):

```powershell
py -3.11 setup.py --paddle
```

Sonra `settings.json` içinde `"ocr_engine": "paddle"` yapın.

Makinenizde Python 3.11 yoksa python.org'dan kurabilir ya da yönetici yetkisi gerektirmeyen
şu yolu kullanabilirsiniz: `pip install --user uv`, `python -m uv python install 3.11`,
sonra o Python ile `setup.py`'yi çalıştırın.

### Windows OCR Japonca dil paketi

Serbest konum modu için gereklidir. Yoksa uygulama açılışta uyarır. **Yönetici** PowerShell'de:

```powershell
Add-WindowsCapability -Online -Name "Language.OCR~~~ja-JP~0.0.1.0"
```

## İlk çalıştırma

```powershell
venv\Scripts\python.exe -m src.app
```

1. Açık pencerelerin listesinden oyunu seçin.
2. Modu seçin:
   - **Sabit kutu**: diyalog kutusu hep aynı yerdeyse. Metin panodan gelir (Textractor).
     OCR ve ekran yakalama çalışmaz.
   - **Serbest konum**: yazılar ekranın farklı yerlerinde çıkıyorsa. Ekran yakalanır, OCR yapılır,
     her yazı bloğunun üstüne çeviri çizilir.
3. `Ctrl+Alt+E` ile düzenleme moduna girip sabit kutunun yerini/boyutunu ya da serbest modda
   taranacak alanı ayarlayın. Ayar, pencere başlığına göre profil olarak kaydedilir.

Seçim penceresini atlamak için: `venv\Scripts\python.exe -m src.app --window "Oyun Başlığı" --mode free`

### Oyunu çerçevesiz pencere modunda açın

Overlay, oyunun **üstünde** ayrı bir pencere olarak çizilir. Tam ekran (exclusive fullscreen)
oyunlarda overlay görünmez ve ekran yakalama siyah kare alabilir. Oyunu **pencere** ya da
**çerçevesiz pencere (borderless windowed)** modunda çalıştırın.

## Textractor bağlama (sabit kutu modu)

1. [Textractor](https://github.com/Artikash/Textractor/releases)'ı indirip açın
   (oyunla aynı bit genişliğindeki sürüm: x86 ya da x64).
2. Oyunu başlatın. Textractor'da **Attach to game** ile oyunun sürecini seçin.
3. Açılır listeden diyalog metnini taşıyan iş parçacığını (thread) seçin; yeni replik geldikçe
   o satırda Japonca metin görünmelidir.
4. **Extensions** penceresinde **Copy to Clipboard** eklentisinin listede olduğundan emin olun
   (yoksa sağ tık → Add extension → `Copy to Clipboard.xdll`).
5. Bu uygulamayı sabit kutu modunda başlatın. Panoya Japonca metin geldikçe kutuda Türkçesi çıkar.

## Kısayollar

| Kısayol | İş |
|---|---|
| Ctrl+Alt+T | Overlay'i gizle/göster (gizliyken yakalama/çeviri durur) |
| Ctrl+Alt+R | O anki ekranı zorla yeniden çevir |
| Ctrl+Alt+E | Düzenleme modu (kutu/bölge taşı, boyutlandır); tekrar basınca kaydeder |
| Ctrl+Alt+M | Mod değiştir (sabit kutu ↔ serbest konum) |
| Ctrl+Alt+D | Debug göstergesi (yakalama, OCR, çeviri, çizim, toplam süre) |
| Ctrl+Alt+Q | Çıkış |

Kısayollar `settings.json` → `hotkeys` altından değiştirilebilir (ör. `"Ctrl+Shift+F9"`).

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

Çeviriden önce kaynak metindeki Japonca anahtarlar Latin harfli karşılıklarıyla değiştirilir
(uzun anahtar önce). Çıktıda bir düzeltme yapılmaz. Dosya değişince uygulama yeniden yükler ve
çeviri önbelleğini temizler.

## Ayarlar (`settings.json`)

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `model`, `model_dir` | setup.py yazar | Kullanılan NLLB modeli |
| `threads` | 0 | CPU iş parçacığı; 0 = çekirdek sayısının yarısı |
| `beam_size` | 2 | Çeviri ışın genişliği |
| `pivot` | false | Japonca→İngilizce→Türkçe iki adım |
| `ocr_engine` | `"windows"` | `"windows"` ya da `"paddle"` |
| `capture_fps` | 5 | Serbest modda saniyedeki yakalama |
| `diff_pixel_threshold`, `diff_min_pixels` | 30, 6 | Değişim eşiği (küçültülmüş gri karede) |
| `stable_ms` | 400 | Görüntü bu kadar sabit kalınca OCR çalışır |
| `font_max_px`, `font_min_px` | 28, 12 | Metin sığdırma punto sınırları |
| `hotkeys` | yukarıdaki tablo | Kısayollar |
| `profiles` | {} | Pencere başlığına göre mod, kutu ve tarama alanı |

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
- OCR testi: Japonca metni görüntüye çizip Windows OCR'dan geçirir (dil paketi yoksa atlanır).
- Uçtan uca testler (`tests/test_e2e.py`): `tools/fake_game.py` açılır, uygulama ağ erişimi
  kapalı halde (`tests/offline_launcher.py`) başlatılır. Fare imlecini, klavyeyi ve panoyu
  kullanır; çalışırken bilgisayara dokunmayın. Panodaki içeriğiniz değişir.
- Benchmark: `venv\Scripts\python.exe tools\benchmark.py [cumleler.txt]`

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
- **Uçtan uca testler için** uygulamada gizli `--test-report` seçeneği var: stdout'a yalnızca
  kutu koordinatları ve süreleri basar (metin içeriği basılmaz, diske yazılmaz).

## Bilinen sınırlar

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

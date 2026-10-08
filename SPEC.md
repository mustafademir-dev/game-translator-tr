# Local Japonca→Türkçe Oyun Çeviri Aracı — Yapım Talimatı

Bu dosya Claude Code için yazıldı. Kullanıcı başında değil: soru sorma, belirsiz kalan yerde en basit çalışan seçeneği uygula ve verdiğin kararı README'nin "Varsayımlar" bölümüne yaz. Her aşama bitince testleri çalıştır, geçince commit at, sonraki aşamaya geç.

## 1. Ne yapılıyor

Japonca metin tabanlı oyunlarda ve görsel romanlarda ekrandaki yazıyı otomatik algılayıp Türkçeye çeviren, çeviriyi orijinal yazının tam üstüne çizen bir Windows masaüstü uygulaması. Tek kullanıcı, tek bilgisayar, kişisel kullanım.

## 2. Değişmez kurallar

1. **Tamamen offline.** Ağ erişimi yalnızca `setup.py` içinde, model indirmek için. Uygulama çalışırken hiçbir ağ çağrısı yapılmaz. Uygulama başlarken şu ortam değişkenlerini kendisi ayarlar: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`. Kullanılan her kütüphanenin otomatik indirme ve telemetri davranışını kapat.
2. **Kullanıcı metni diske yazılmaz.** Yakalanan görüntü, OCR çıktısı, kaynak metin ve çeviri yalnızca bellekte tutulur. Log dosyası yok. Hata mesajlarına metin içeriği konmaz. Diske yazılan tek şey ayar dosyası ve kullanıcının kendi yazdığı sözlük.
3. **Uygulama seviyesinde içerik filtresi yok.** Metin içeriğine göre atlama, yumuşatma ya da uyarı ekleme yapılmaz.
4. **Native Windows Python.** WSL kullanılmaz (pano, overlay ve oyun Windows tarafında). Python 3.11, proje içinde `venv`.
5. **Sistem ayarına dokunma.** Windows özelliği kurma, yönetici yetkisi isteyen komut çalıştırma yok. Gerekiyorsa komutu README'ye ve kurulum çıktısına yaz, kullanıcı kendisi çalıştırır.
6. **Kapsam dışına çıkma.** Aşağıda yazmayan özellik ekleme. Sade tut.

## 3. Donanım varsayımı

Windows 10/11 laptop, 4 GB VRAM'li GPU, RAM miktarı bilinmiyor. Bu yüzden:

- Çeviri ve OCR **CPU'da** çalışır. GPU'ya hiç dokunulmaz (oyun kullanıyor).
- `setup.py` sistem RAM'ini ölçer: 12 GB ve üstüyse NLLB 1.3B, altındaysa NLLB 600M kurar. Seçim ayar dosyasına yazılır.

## 4. Teknoloji seçimleri (kesin)

| Parça | Seçim | Not |
|---|---|---|
| Çeviri | `facebook/nllb-200-distilled-1.3B` (veya 600M), CTranslate2, int8, CPU | Kaynak `jpn_Jpan`, hedef `tur_Latn` |
| Ekran yakalama | `mss` | Hibrit GPU'lu laptoplarda dxcam sorun çıkarıyor; saniyede 5 kare yeterli |
| OCR (varsayılan) | Windows dahili OCR (`winsdk` / WinRT `Windows.Media.Ocr`), Japonca | Dil paketi kontrolü zorunlu, bkz. 6.3 |
| OCR (alternatif) | PaddleOCR Japonca | Aynı arayüzün arkasında, isteğe bağlı kurulum (`setup.py --paddle`) |
| Overlay | PyQt6 | Çerçevesiz, her zaman üstte, click-through |
| Kısayollar | Win32 `RegisterHotKey` (ctypes) | Ek kütüphane yok |
| Ayarlar | JSON, uygulama klasöründe | Pencere başlığına göre profil |

## 5. Mimari

```
src/
  translate/   backend arayüzü, NLLB backend'i, cache, sözlük
  capture/     pencere seçimi, yakalama, değişim tespiti
  ocr/         motor arayüzü, Windows OCR, PaddleOCR, blok birleştirme
  overlay/     PyQt6 pencere, metin sığdırma, click-through
  app.py       modları ve kısayolları bağlayan ana döngü
  config.py    ayar ve profil okuma/yazma
tools/
  benchmark.py
  fake_game.py
tests/
setup.py
README.md
```

Kurallar:

- Çeviri ve OCR arayüz thread'inde çalışmaz. Ayrı worker thread, sonuç sinyalle gelir.
- Overlay yalnızca içerik değiştiğinde ya da pencere taşındığında yeniden çizilir.
- Uygulama per-monitor DPI aware (v2) olarak başlar. Tüm koordinatlar fiziksel pikseldir; yakalama, OCR ve çizim aynı koordinat sistemini kullanır. İlk sürümde tek monitör desteklenir, README'de belirt.

### 5.1 Çeviri modülü

```python
class TranslationBackend(Protocol):
    def translate(self, text: str, context: list[str] = []) -> str: ...
```

- `context` parametresi şimdilik kullanılmaz (NLLB yok sayar), ileride LLM backend'i için arayüzde durur.
- `pivot` ayarı: açıksa aynı modelle Japonca→İngilizce→Türkçe iki adım. Varsayılan kapalı.
- Cache: bellekte, anahtar kaynak metin. Sözlük ya da pivot ayarı değişince temizlenir. En fazla 2000 kayıt.
- Sözlük: `dictionary.json`, `{"田中": "Tanaka"}` biçiminde. Çeviriden önce kaynak metinde Japonca anahtar Latin harfli karşılığıyla değiştirilir (uzun anahtar önce). Çeviriden sonra karşılık çıktıda yoksa hiçbir düzeltme yapma, olduğu gibi bırak.
- Uzun metin cümle sonlarından (。！？) bölünüp parça parça çevrilir.

### 5.2 Değişim tespiti ve stabilizasyon (serbest konum modu)

1. Taranan bölge saniyede 5 kez yakalanır, küçültülmüş gri kopyası bir öncekiyle karşılaştırılır.
2. Fark eşiğin altındaysa hiçbir şey yapılmaz. OCR ve çeviri sıfır yük.
3. Fark eşiğin üstündeyse sayaç başlar. Görüntü 400 ms sabit kalınca OCR bir kere çalışır.
4. Yeni OCR bloğunun metni, aynı konumdaki eski bloğun metniyle başlıyorsa (yazı akmaya devam etmiş) eski çeviri yenisiyle değiştirilir.
5. Eşikler ayar dosyasından değiştirilebilir.

### 5.3 OCR modülü

```python
@dataclass
class TextBlock:
    text: str
    x: int; y: int; w: int; h: int
    vertical: bool

class OcrEngine(Protocol):
    def recognize(self, image) -> list[TextBlock]: ...
```

- Aynı paragrafa ait yakın satırlar tek blokta birleştirilir.
- Japonca karakter içermeyen bloklar atılır.
- Dikey yazıda görüntüyü döndürme. Dikey yazıyı motorun kendisi okur; Windows OCR okuyamıyorsa bu PaddleOCR'ın işidir.

### 5.4 Overlay

- Tek bir şeffaf pencere, oyun penceresinin üstünü kaplar, oyun taşınınca takip eder.
- Normal modda tıklamalar oyuna geçer (`WS_EX_TRANSPARENT | WS_EX_LAYERED`).
- Pencere ekran yakalamadan hariç tutulur: `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)`. Yoksa uygulama kendi çıktısını OCR'a sokar.
- Her blok için: bölgenin kenar piksellerinin ortalama rengiyle opak kutu, üstüne Türkçe metin. Yazı rengi arka plana göre siyah ya da beyaz seçilir.
- Metin sığdırma: en büyük punto ile dene, satır kır, sığmazsa küçült, alt sınırın (12 px) altına düşerse kutuyu aşağı doğru genişlet.
- Font: Noto Sans, proje içinde `assets/` altında gelir. Sistem fontuna güvenme.

## 6. Modlar

### 6.1 Sabit kutu modu

Diyalog kutusu hep aynı yerdeyse. OCR ve ekran yakalama çalışmaz.

- Uygulama panoyu dinler. Japonca karakter içeren yeni metin gelince çevirir.
- Kullanıcı düzenleme modunda overlay kutusunu diyalog kutusunun üstüne sürükleyip boyutlandırır, konum profile kaydedilir.
- Metin kaynağı Textractor'ın panoya kopyalama eklentisidir. Bunu kullanıcı kurar; README'de adımları yaz.

### 6.2 Serbest konum modu

Yazılar ekranın farklı yerlerinde çıkıyorsa. Akış: yakala → değişim tespiti → OCR → çevir → her bloğun üstüne çiz.

- Kullanıcı isterse düzenleme modunda taranacak alanı dikdörtgenle sınırlar. Sınır yoksa tüm oyun penceresi taranır.

### 6.3 OCR dil paketi kontrolü

Açılışta Windows OCR'ın Japonca desteği kontrol edilir. Yoksa uygulama çökmeden ekranda bildirim gösterir ve şu komutu verir (kullanıcı yönetici PowerShell'de kendisi çalıştırır):

```
Add-WindowsCapability -Online -Name "Language.OCR~~~ja-JP~0.0.1.0"
```

## 7. Kullanım

- Açılışta açık pencerelerin listesi gösterilir, kullanıcı oyunu seçer, modu seçer.
- Kısayollar (ayar dosyasından değiştirilebilir):

| Kısayol | İş |
|---|---|
| Ctrl+Alt+T | Overlay'i gizle/göster |
| Ctrl+Alt+R | O anki ekranı zorla yeniden çevir |
| Ctrl+Alt+E | Düzenleme modu (kutu/bölge taşı, boyutlandır) |
| Ctrl+Alt+M | Mod değiştir |
| Ctrl+Alt+D | Debug göstergesi (aşama süreleri) |
| Ctrl+Alt+Q | Çıkış |

- Debug göstergesi son işlemin sürelerini ekranda gösterir (yakalama, OCR, çeviri, çizim, toplam). Yalnızca bellekte.
- Hata durumları (model bulunamadı, OCR dil paketi yok, oyun penceresi kapandı) sessizce geçilmez, ekranda kısa bildirim çıkar.

## 8. Yapım aşamaları

### Aşama 1 — Çeviri çekirdeği

- `setup.py`: venv bağımlılıkları, RAM ölçümü, model indirme, CTranslate2 int8 dönüşümü, font indirme.
- Çeviri modülü, cache, sözlük.
- `tools/benchmark.py`: bir metin dosyasındaki cümleleri hem doğrudan hem pivot modda çevirir; her cümle için iki çeviriyi ve süreleri yan yana ekrana basar, sonda medyan ve p95 süre.
- `tools/benchmark_sentences.txt`: 30 adet görsel roman tarzı Japonca replik yaz (kısa, uzun, soru, hitaplı, isimli, özne düşmüş). Kullanıcı sonra kendi cümleleriyle değiştirecek.
- **Bitti ölçütü:** benchmark çalışıyor; 20-100 karakterlik cümlede medyan süre 1 saniyenin altında. Değilse 600M modele düş ve README'ye yaz.

### Aşama 2 — Sabit kutu modu

- Pano dinleme, overlay, click-through, düzenleme modu, profil kaydı, kısayollar.
- **Bitti ölçütü:** panoya Japonca metin kopyalanınca çeviri kutuda çıkıyor; normal modda kutunun altındaki pencereye tıklanabiliyor.

### Aşama 3 — Serbest konum modu

- Yakalama, değişim tespiti, stabilizasyon, Windows OCR, blok birleştirme, koordinata çizim, ekran yakalamadan hariç tutma, DPI.
- PaddleOCR motoru arayüzün arkasında, isteğe bağlı.
- **Bitti ölçütü:** `fake_game.py` ile uçtan uca test geçiyor (bkz. 9).

### Aşama 4 — Toparlama

- Debug göstergesi, hata bildirimleri, README.
- README içeriği: kurulum, ilk çalıştırma, Textractor bağlama adımları, oyunu çerçevesiz pencere modunda açma uyarısı, kısayollar, sözlük biçimi, varsayımlar, bilinen sınırlar.

Şimdilik **yapılmayacaklar:** hook metni ile OCR bloklarını eşleştirme, LLM backend'i, çoklu monitör, konuşmacı tespiti.

## 9. Kullanıcı olmadan test

Gerçek oyun yok, kullanıcı başında değil. Bu yüzden:

- `tools/fake_game.py`: sahte oyun penceresi. PyQt6 ile bir pencere açar, arka plana düz olmayan bir görsel koyar, her birkaç saniyede bir rastgele konumda Japonca bir replik gösterir. Seçenekler: harf harf yazma efekti, dikey yazı, farklı puntolar.
- Birim testleri: cache, sözlük, cümle bölme, blok birleştirme, metin sığdırma, değişim tespiti.
- OCR testi: Japonca metni bir görüntüye çiz, OCR'dan geçir, karakter benzerliğini ölç. Windows OCR dil paketi yoksa bu test atlanır ve rapora yazılır.
- Uçtan uca test: `fake_game.py` açılır, uygulama ona bağlanır; bilinen bir replik gösterildikten sonra overlay'de o konumda bir çeviri kutusu oluştuğu doğrulanır.
- Offline testi: uygulama `socket` çağrıları yamalanmış halde (her bağlantı denemesi hata fırlatır) başlatılır; çeviri ve OCR yine çalışmalı.

## 10. Bitince bırakılacak rapor

`RAPOR.md`: hangi aşamalar bitti, hangi testler geçti/atlandı, benchmark sonuçları (doğrudan ve pivot, süreler), kullanıcının elle yapması gerekenler (OCR dil paketi, Textractor), karşılaşılan sorunlar ve verilen kararlar.

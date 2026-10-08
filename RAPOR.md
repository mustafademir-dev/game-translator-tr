# Yapım Raporu

Tarih: 2026-10-08 · Makine: Windows 11, 15.7 GB RAM, 16 mantıksal çekirdek, RTX 3050 4 GB (kullanılmadı),
1920×1080 %125 ölçek, tek monitör.

## Aşamalar

| Aşama | Durum | Commit |
|---|---|---|
| 1 — Çeviri çekirdeği | Bitti, ölçüt geçti | `Aşama 1: çeviri çekirdeği …` |
| 2 — Sabit kutu modu | Bitti, ölçüt geçti | `Aşama 2: sabit kutu modu …` |
| 3 — Serbest konum modu | Bitti, ölçüt geçti | `Aşama 3: serbest konum modu …` |
| 4 — Toparlama | Bitti | `Aşama 4: toparlama …` |

Kurulan model: RAM 15.7 GB olduğu için **NLLB-200 distilled 1.3B** (int8, 1.4 GB). Süre ölçütünü
geçtiği için 600M'e düşmeye gerek kalmadı.

## Testler

Son durum: **52 geçti, 0 atlandı, 0 başarısız** (`venv\Scripts\python.exe -m pytest tests`,
art arda 3+ çalıştırmada kararlı).

| Dosya | Kapsam | Sonuç |
|---|---|---|
| `test_translate.py` (17) | önbellek (LRU, 2000 sınırı, sözlük/pivot değişince temizlenme), sözlük (uzun anahtar önce, çıktıya dokunmama), cümle bölme | geçti |
| `test_ocr_merge.py` (6) | satır→paragraf birleştirme, aynı satırın parçaları, dikey sütunlar, Japonca olmayanı atma | geçti |
| `test_fit.py` (5) | punto küçültme, satır kırma, alt sınırda aşağı uzama, Türkçe glifler | geçti |
| `test_change.py` (7) | değişim tespiti, 400 ms stabilizasyon, harf harf yazma, gürültü eşiği, kenar rengi | geçti |
| `test_ocr_windows.py` (6) | Japonca metni görüntüye çiz → Windows OCR → benzerlik | geçti (3 örnekte benzerlik **1.00**) |
| `test_ocr_paddle.py` (2) | PaddleOCR yatay + dikey | geçti (yatay **1.00**, dikey **0.92**) |
| `test_app_errors.py` (3) | model yok / OCR dil paketi yok bildirimleri | geçti |
| `test_e2e.py` (6) | uçtan uca, aşağıda | geçti |

Uçtan uca testler (gerçek masaüstünde, uygulama `socket` yamalı başlatılarak):

- **Serbest konum** (normal ve harf harf yazma): `fake_game.py` bilinen repliği gösterir, overlay'de
  o konumda çeviri kutusu oluşur; overlay `WS_EX_TRANSPARENT|WS_EX_LAYERED` ve
  `WDA_EXCLUDEFROMCAPTURE` (0x11) taşır; 3 s boyunca kutu sayısı sabit kalır (kendi çıktısını OCR'a sokmuyor).
- **Sabit kutu**: panoya Japonca kopyalanır → kutuda çeviri çıkar → kutunun ortasına gerçek fare
  tıklaması gönderilir → tıklama alttaki sahte oyuna ±2 px içinde ulaşır.
- **Düzenleme modu**: Ctrl+Alt+E → click-through kalkar → kutu fareyle 300 px taşınır → Ctrl+Alt+E →
  profil `settings.json`'a yazılır → Ctrl+Alt+Q ile temiz çıkış.
- **Pencere kapanınca**: bildirim çıkar, uygulama çökmez.
- **Offline**: çeviri + Windows OCR + PaddleOCR, tüm soket bağlantıları hata fırlatırken çalışır;
  **bağlantı denemesi sayısı 0**.

Ek uzun deneme (rastgele konum/punto, 30-55 s, sonuçlar yalnızca ekranda):

| Senaryo | İsabet | Replikten kutuya gecikme | Aşama medyanları (yakalama / OCR / çeviri / çizim / toplam) |
|---|---|---|---|
| Windows OCR, normal | 6/6 | 0.5–1.4 s | 20 / 58 / 543 / 1.6 / 683 ms |
| Windows OCR, harf harf | 6/6 | 0.5–1.4 s | 19 / 58 / 558 / 1.8 / 677 ms |
| Windows OCR, dikey | 6/6 | 0.6–1.5 s | — |
| PaddleOCR, normal | açılıştaki ~20 s'den sonra 8/8 | 0.6–1.5 s | 21 / 471 / 312 / 1.6 / 737 ms |

Gecikmeye 400 ms stabilizasyon ve 200 ms yakalama aralığı dahildir.

## Benchmark (`tools/benchmark.py`, 30 replik, 1.3B, int8, 8 CPU iş parçacığı)

| | Medyan | p95 |
|---|---|---|
| Doğrudan (ja→tr), tümü | 467 ms | 777 ms |
| Pivot (ja→en→tr), tümü | 908 ms | 1621 ms |
| Doğrudan, 20–100 karakter (15 cümle) | **470 ms** | 681 ms → ölçüt (< 1 s) **geçti** |

Örnekler (doğrudan | pivot):

- 田中さん、今日は学校に来ないんですか？ → *Tanaka Bey, bugün okula gelmeyecek misiniz?* | *Bay Tanaka, bugün okula gelmeyecek misiniz?*
- 放課後、屋上に来てください。どうしても伝えたいことがあるんです。 → *Okul bittikten sonra çatıya gel. Sana söylemek istediğim bir şey var.* | *Okuldan sonra lütfen çatıya gelin. Sana söylemem gereken bir şey var.*
- ごめんなさい、私のせいで、みんなに迷惑をかけてしまって…… → *Özür dilerim.* (eksik) | *Sizi rahatsız ettiğim için özür dilerim.*
- 美咲ちゃん、一緒にお祭りに行かない？ → *Meryem Bey, partiye gelmek ister misin?* (isim bozuk) | *Miki, neden benimle partiye gelmiyorsun?*
- 桜井、そこにいるのは分かってるんだぞ。 → *Sakura, orada olduğunu biliyorum.* (isim bozuk)

Gözlem: doğrudan mod 2 kat hızlı ve çoğu replikte yeterli. Pivot bazen daha eksiksiz
(ör. 「ごめんなさい…」) ama bazen anlamı kaydırıyor (「お祭り」→ parti, 「わかった」). Varsayılan
**kapalı** bırakıldı. Kişi adları NLLB'nin zayıf noktası; `dictionary.json` ile çözülmesi önerilir
(ör. `{"美咲": "Misaki", "桜井": "Sakurai"}`).

## Kullanıcının elle yapması gerekenler

1. **Windows OCR Japonca dil paketi**: bu makinede **zaten kurulu** (`ja` tanıyıcısı mevcut).
   Başka bir makinede yoksa yönetici PowerShell'de:
   `Add-WindowsCapability -Online -Name "Language.OCR~~~ja-JP~0.0.1.0"`
2. **Textractor** (sabit kutu modu için): kurulumu ve oyuna bağlama README'de, "Copy to Clipboard"
   eklentisi açık olmalı.
3. Oyunu **pencere / çerçevesiz pencere** modunda çalıştırmak.
4. İsteğe bağlı: kişi adları için `dictionary.json` yazmak; PaddleOCR'ı kullanmak isterse
   `settings.json` → `"ocr_engine": "paddle"` (bu makinede kurulu).
5. İsteğe bağlı: proje OneDrive'da; `models/` ve `venv/` (~birkaç GB) eşitlemeden hariç tutulabilir.

## Karşılaşılan sorunlar ve verilen kararlar

- **Python 3.11 yoktu** (yalnızca 3.12). Yönetici yetkisi istemeyen yol seçildi: `pip install --user uv`
  → `uv python install 3.11` (kullanıcı klasörüne). venv bununla kuruldu.
- **"Masaüstü" yolu**: sentencepiece ve Paddle ASCII dışı mutlak yolları açamıyor. sentencepiece
  modeli bayt olarak, Paddle modelleri proje köküne göreli yolla yükleniyor. CTranslate2'de sorun yok.
- **Font indirmesi** ilk denemede ağ hatasıyla yarım kaldı ve yarım dosya bırakmıştı. İndirme artık
  `.part` dosyasına yapılıp başarıda yeniden adlandırılıyor, 5 kez deneniyor.
- **asyncio** Windows'ta kendi içinde yerel soket çifti açıyor; offline testinde (tüm bağlantılar
  yasak) bu da engellenir. Windows OCR'ın async çağrısı asyncio'suz, durum yoklamasıyla bekleniyor.
- **Değişim eşiği**: ortalama piksel farkı tek bir harfin belirmesini kaçırıyordu; eşik
  "belirgin değişen piksel sayısı" olarak tanımlandı (`diff_pixel_threshold`, `diff_min_pixels`).
- **Windows OCR** Japonca karakterleri boşlukla ayırıyor ve bir satırı 、 işaretinden bölebiliyor;
  boşluklar Japonca karakterler arasında kaldırılıyor, aynı satırdaki parçalar birleştiriliyor.
- **DPI**: süreç per-monitor v2 aware başlıyor ve Qt'nin kendi ölçeklemesi kapatılıyor
  (`QT_ENABLE_HIGHDPI_SCALING=0`); %125 ölçekli ekranda Qt geometrisi ile Win32 fiziksel
  koordinatlarının birebir eşleştiği doğrulandı.
- **Paddle + CTranslate2 DLL çakışması**: Paddle önce yüklenirse `import ctranslate2` WinError 127
  veriyor. Uygulamada çeviri modeli her zaman önce yüklendiği için sorun yok; testlerde de bu sıra sabitlendi.
- **PaddleOCR açılışı ~15-20 s**: motor ilk karede değil, serbest moda geçilir geçilmez yükleniyor.
- **Dikey yazı**: çeviri kutusu dar sütuna sığmadığından en az 160 px genişliğe açılıyor.
- **Sabit kutu rengi**: bu modda ekran yakalanmadığı için koyu gri sabit renk kullanıldı.
- **Test için** uygulamaya gizli `--test-report` bayrağı eklendi (yalnızca koordinat/süre, metin yok,
  diske yazılmaz); sahte oyuna testte başka pencere örtmesin diye `--topmost` eklendi.
- PaddleOCR 3.x yerine **2.9.1 + paddlepaddle 2.6.2** seçildi: model klasörü verilerek tamamen
  offline çalıştırılabiliyor (3.x çalışırken model kaynak kontrolü yapıyor).
- Ayrıntılı varsayım listesi README'nin "Varsayımlar" bölümünde.

## Bilinen eksikler / sonraki adımlar

- Gerçek bir oyunla ve gerçek Textractor çıktısıyla denenmedi (kullanıcı yoktu); sahte oyun ve pano
  benzetimiyle test edildi.
- Tek monitör; çoklu monitör ve monitörler arası farklı ölçek desteklenmiyor.
- Kişi adı çevirileri zayıf; sözlük gerektirir.

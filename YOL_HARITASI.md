# Yol Haritası

Uygulamanın bugünkü kapsamı ve eklenebilecek özellikler. Kurulum ve kullanım için `README.md`,
yapım ve test sonuçları için `RAPOR.md`.

## Bugünkü kapsam (2026-10-08, Korece/İngilizce eklendi)

### Diller

Kaynak: **Japonca, Korece, İngilizce** (oyun profiline göre seçilir). Hedef: her zaman **Türkçe**.
NLLB 200 dili desteklediği için başka bir kaynak dil eklemek çoğunlukla `src/translate/text.py`
içindeki `LANGS` tablosuna bir satır ve o dilin OCR paketi demektir (ör. Çince için Windows OCR
Çince paketi ya da PaddleOCR `ch` modeli).

### İki çalışma modu

| Mod | Ne zaman kullanılır | Metin nereden gelir |
|---|---|---|
| Sabit kutu | Diyalog kutusu hep aynı yerdeyse (çoğu görsel roman) | Textractor → pano |
| Serbest konum | Yazılar ekranın farklı yerlerinde çıkıyorsa | Ekran yakalama + OCR |

### Özellikler

- Otomatik ve sürekli çeviri: yeni metin gelince kendiliğinden çevirir; harf harf yazılan metinde
  yazı bitene kadar bekler (0.4 s sabitlik).
- Overlay: oyunun üstünde durur, tıklamaları oyuna geçirir, pencere taşınınca peşinden gider,
  ekran yakalamaya girmez. Kutu rengi arka plana, yazı rengi okunurluğa göre seçilir.
- Metin sığdırma: yazı küçülür, alt sınırda kutu aşağı uzar.
- Düzenleme modu: sabit kutuyu taşı/boyutlandır, serbest modda taranacak alanı sınırla;
  oyuna göre profil kaydı.
- Sözlük (`dictionary.json`): isim ve terim sabitleme.
- İki OCR motoru: Windows OCR (hızlı, varsayılan), PaddleOCR (yavaş, dikey yazıda güçlü).
- Pivot çeviri (ja→en→tr), varsayılan kapalı.
- Kısayollar: gizle/göster, zorla yeniden çevir, düzenleme, mod değiştir, debug, çıkış.
- Debug göstergesi: yakalama / OCR / çeviri / çizim / toplam süre.
- Hata bildirimleri: model yok, OCR dil paketi yok, oyun penceresi kapandı.
- Gizlilik: tamamen offline; görüntü, metin ve çeviri yalnızca bellekte; log dosyası yok.
- İçerik filtresi yok.

### Ölçülen hız (Windows OCR, NLLB 1.3B int8, bu makine)

Yazı ekrana gelince çeviri kutusu 0.5–1.5 s içinde çıkıyor. Bunun ~550 ms'si çeviri.

### Sınırlar

- NLLB bağlam bilmiyor; özne düşmüş cümlelerde ve kişi adlarında hata yapabiliyor.
- Tek monitör.
- Exclusive fullscreen oyunlarda overlay görünmüyor.
- Gerçek bir oyunla henüz denenmedi.

## Eklenebilecekler (öncelik sırasıyla)

| # | Özellik | Ne kazandırır | Zorluk | Not |
|---|---|---|---|---|
| 1 | LLM ile çeviri (yerel Qwen/Gemma 4B ya da Claude API) | En büyük kalite artışı: bağlam, önceki replikler, doğru isim ve hitap | Orta | `TranslationBackend.translate(text, context)` arayüzü hazır. Yerel modelde 4 GB VRAM oyunla paylaşılır; CPU'da yavaş olabilir. API seçilirse "tamamen offline" kuralı bilinçli olarak gevşetilmeli. |
| 2 | Çeviri geçmişi paneli | Kaçırılan replikleri geri okuma | Kolay | Yalnızca bellekte tutulmalı (gizlilik kuralı). |
| 3 | Orijinali gösterme | Kısayolla Japonca metin ya da okunuş (furigana/romaji); öğrenmeye de yarar | Kolay–orta | Okunuş için offline bir kütüphane gerekir (ör. pykakasi). |
| 4 | Konuşmacı tespiti | "Misaki: …" ayrımı; LLM çevirisini de iyileştirir | Orta | SPEC'te ertelenenlerde. |
| 5 | Hook metni ile OCR bloklarını eşleştirme | Textractor'ın kusursuz metni serbest moddaki konuma; OCR hatası kalmaz | Orta–zor | SPEC'te ertelenenlerde. |
| 6 | Çoklu monitör | Oyun ikinci ekrandayken doğru koordinatlar | Orta | SPEC'te ertelenenlerde. |
| 7 | Ayar penceresi | `settings.json`'u elle düzenlemeden ayar yapma | Kolay | |
| 8 | Sözlüğe hızlı ekleme | Yanlış çevrilen ismi kısayolla anında sözlüğe ekleme | Kolay | |
| 9 | Sesli okuma | Çeviriyi Türkçe seslendirme (Windows yerel sesleri, offline) | Kolay–orta | |
| 10 | Kaynak dili otomatik algılama | Aynı ekranda karışık diller (Japonca diyalog + İngilizce menü) | Orta | Her karede birden çok OCR motoru çalışır; yük artar. |
| 11 | Çince kaynak | Çince oyunlar | Kolay–orta | Windows OCR Çince paketi ya da PaddleOCR `ch` modeli gerekir. |

## Öneri

1. Önce uygulamayı gerçek bir oyunda birkaç gün kullan ve en çok neyin rahatsız ettiğini not et:
   çeviri kalitesi mi, kaçan replikler mi, isimler mi, gecikme mi?
2. Çeviri kalitesi öndeyse **1 (LLM çevirisi)** ile başla.
3. Kaçan replikler öndeyse **2 (geçmiş paneli)**, isimler öndeyse **8 (hızlı sözlük ekleme)**.

import numpy as np

from src.capture import ChangeDetector, edge_color, small_gray, text_color_for


def frame(val=0, box=None):
    img = np.zeros((200, 300, 4), np.uint8)
    img[:, :, :3] = val
    if box:
        x, y, w, h = box
        img[y:y + h, x:x + w, :3] = 255
    return small_gray(img)


def feed_seq(det, frames_times):
    return [det.feed(f, t) for f, t in frames_times]


def test_first_stable_frame_fires_once():
    d = ChangeDetector(stable_ms=400)
    out = feed_seq(d, [(frame(), t) for t in (0, 200, 400, 600, 800)])
    assert out == [False, False, True, False, False]


def test_no_change_no_work():
    d = ChangeDetector(stable_ms=400)
    feed_seq(d, [(frame(), t) for t in (0, 200, 400)])
    assert not any(feed_seq(d, [(frame(), t) for t in range(600, 5000, 200)]))


def test_waits_until_stable():
    d = ChangeDetector(stable_ms=400)
    feed_seq(d, [(frame(), t) for t in (0, 200, 400)])
    # Harf harf yazma: her karede değişiyor -> OCR yok
    seq = [(frame(box=(10, 10, 10 * i, 20)), 600 + 200 * i) for i in range(1, 6)]
    assert not any(feed_seq(d, seq))
    # Son değişim t=1600'de; 400 ms sabit kalınca (t=2000) tek bir kez
    last = frame(box=(10, 10, 50, 20))
    out = feed_seq(d, [(last, 1800), (last, 2000), (last, 2200), (last, 2400)])
    assert out == [False, True, False, False]


def test_small_noise_below_threshold_ignored():
    d = ChangeDetector(pixel_threshold=30, min_pixels=6, stable_ms=400)
    feed_seq(d, [(frame(100), t) for t in (0, 200, 400)])
    assert not any(feed_seq(d, [(frame(110), t) for t in (600, 800, 1000, 1200)]))


def test_single_character_change_detected():
    d = ChangeDetector(stable_ms=400)
    feed_seq(d, [(frame(), t) for t in (0, 200, 400)])
    ch = frame(box=(100, 100, 8, 8))  # ~16 küçük piksel
    assert feed_seq(d, [(ch, 600), (ch, 800), (ch, 1000)]) == [False, False, True]


def test_reset_fires_again():
    d = ChangeDetector(stable_ms=400)
    feed_seq(d, [(frame(), t) for t in (0, 200, 400)])
    d.reset()
    assert feed_seq(d, [(frame(), t) for t in (600, 800, 1000)]) == [False, False, True]


def test_edge_color_and_text_color():
    img = np.zeros((100, 100, 4), np.uint8)
    img[:, :, 0] = 200  # B
    img[:, :, 1] = 100  # G
    img[:, :, 2] = 50   # R
    img[40:60, 40:60, :3] = 255  # ortadaki yazı kenar rengini etkilemez
    assert edge_color(img, 30, 30, 40, 40) == (50, 100, 200)
    assert text_color_for((250, 250, 240)) == (0, 0, 0)
    assert text_color_for((20, 20, 40)) == (255, 255, 255)


def test_continuous_animation_still_fires_every_max_wait():
    """Ekran hiç durulmasa da (hareketli arka plan) OCR en geç max_wait_ms'de bir çalışmalı."""
    d = ChangeDetector(stable_ms=400, max_wait_ms=1500)
    seq = [(frame(box=(0, 0, 10 + (i % 20) * 10, 20)), i * 200) for i in range(1, 21)]  # 200..4000 ms
    fired = [t for (f, t), out in zip(seq, feed_seq(d, seq)) if out]
    assert fired == [1800, 3600]  # ilk kare 200 ms: 200+1500 sonrası ilk kare; sonra 2000+1500


def test_reset_rearms_after_click():
    """Tıklama sonrası reset: ekran değişmese bile bir kez daha OCR çalışır."""
    d = ChangeDetector(stable_ms=400)
    feed_seq(d, [(frame(), t) for t in (0, 200, 400)])
    assert not any(feed_seq(d, [(frame(), t) for t in (600, 800)]))
    d.reset()
    assert feed_seq(d, [(frame(), t) for t in (1000, 1200, 1400)]) == [False, False, True]

"""Sahte oyun penceresi: düz olmayan arka plan üstünde rastgele konumda replikler
(Japonca, Korece ya da İngilizce: --lang).

Kullanım:
    venv\\Scripts\\python.exe tools\\fake_game.py [--lang ja|ko|en] [--typewriter] [--vertical] [--sizes 22,28,36]
        [--interval 4] [--line N] [--pos X,Y] [--seed S] [--title "Fake Game"] [--blank]
        [--at X,Y] [--topmost]

Her replik tamamen göründüğünde stdout'a JSON basar (test için):
    {"event": "line", "index": i, "rect": [x, y, w, h]}   # ekran fiziksel pikseli
Tıklamalar da raporlanır: {"event": "click", "x": .., "y": ..}
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

import ctypes  # noqa: E402

try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except (AttributeError, OSError):
    pass

from PyQt6.QtCore import QPoint, QRect, Qt, QTimer  # noqa: E402
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPen  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

LINES_JA = [
    "田中さん、今日は学校に来ないんですか？",
    "もう遅いから、早く帰ったほうがいいよ。",
    "ちょっと待って！",
    "お兄ちゃん、朝ごはんできたよ！",
    "この町には、昔から不思議な言い伝えがあるらしい。",
    "大丈夫、心配しないで。",
    "放課後、屋上に来てください。",
    "知らない天井だ。",
]
LINES_KO = [
    "다나카 씨, 오늘 학교에 안 와요?",
    "벌써 늦었으니까 빨리 집에 가는 게 좋아.",
    "잠깐만 기다려!",
    "오빠, 아침 다 됐어!",
    "이 마을에는 옛날부터 이상한 전설이 있대.",
    "괜찮아, 걱정하지 마.",
    "방과 후에 옥상으로 와 주세요.",
    "모르는 천장이다.",
]
LINES_EN = [
    "Tanaka, aren't you coming to school today?",
    "It's getting late, you should head home.",
    "Wait a moment!",
    "Big brother, breakfast is ready!",
    "This town has had a strange legend for ages.",
    "It's okay, don't worry.",
    "Please come to the rooftop after school.",
    "An unfamiliar ceiling.",
]
LINES_BY_LANG = {"ja": LINES_JA, "ko": LINES_KO, "en": LINES_EN}
FONTS = {"ja": "Yu Gothic UI", "ko": "Malgun Gothic", "en": "Segoe UI"}


class FakeGame(QWidget):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.setWindowTitle(args.title)
        self.resize(1280, 720)
        self.rng = random.Random(args.seed)
        self.sizes = [int(s) for s in args.sizes.split(",")]
        self.text = ""
        self.shown = 0
        self.pos = QPoint(100, 100)
        self.size_px = self.sizes[0]
        self.index = 0
        self.type_timer = QTimer(self, interval=args.type_ms, timeout=self._type_step)
        self.next_timer = QTimer(self, interval=int(args.interval * 1000), timeout=self.next_line)
        # Gerçek oyunlardaki hareket: sürekli kayan arka plan nesnesi ve yanıp sönen "devam" oku.
        self.frame = 0
        self.blink_on = True
        if args.animate or args.behind:
            QTimer(self, interval=50, timeout=self._anim_step).start()
        if args.blink:
            QTimer(self, interval=500, timeout=self._blink_step).start()

    def _anim_step(self):
        self.frame += 1
        self.update()

    def _blink_step(self):
        self.blink_on = not self.blink_on
        self.update()

    def start(self):
        if not self.args.blank:
            self.next_line()
            if self.args.line is None and not self.args.click_advance:
                self.next_timer.start()

    def _font(self) -> QFont:
        f = QFont(FONTS[self.args.lang])
        f.setPixelSize(self.size_px)
        f.setBold(True)
        return f

    def _text_rect(self) -> QRect:
        fm = QFontMetrics(self._font())
        if self.args.vertical:
            w = fm.horizontalAdvance("国") + 8
            h = fm.height() * len(self.text) + 8
        else:
            w = fm.horizontalAdvance(self.text) + 16
            h = fm.height() + 8
        return QRect(self.pos.x(), self.pos.y(), w, h)

    def next_line(self):
        lines = LINES_BY_LANG[self.args.lang]
        self.index = self.args.line if self.args.line is not None else self.rng.randrange(len(lines))
        self.text = lines[self.index]
        self.size_px = self.rng.choice(self.sizes)
        r = self._text_rect()
        if self.args.pos:
            x, y = (int(v) for v in self.args.pos.split(","))
        else:
            x = self.rng.randint(20, max(20, self.width() - r.width() - 20))
            y = self.rng.randint(20, max(20, self.height() - r.height() - 20))
        self.pos = QPoint(x, y)
        print(json.dumps({"event": "line_start", "index": self.index}), flush=True)
        if self.args.typewriter:
            self.shown = 0
            self.type_timer.start()
        else:
            self.shown = len(self.text)
            self._report()
        self.update()

    def _type_step(self):
        self.shown += 1
        self.update()
        # Gerçek oyunlardaki gibi noktalamada duraksama.
        if (self.args.pause_ms and self.shown < len(self.text)
                and self.text[self.shown - 1] in ("、", "。", ",")):
            self.type_timer.stop()
            QTimer.singleShot(self.args.pause_ms, self._resume_typing)
            return
        if self.shown >= len(self.text):
            self.type_timer.stop()
            self._report()

    def _report(self):
        r = self._text_rect()
        tl = self.mapToGlobal(r.topLeft())
        import time as _t
        print(json.dumps({"event": "line", "index": self.index, "t": round(_t.perf_counter(), 3),
                          "rect": [tl.x(), tl.y(), r.width(), r.height()]}), flush=True)

    def paintEvent(self, _):
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0, QColor(70, 110, 160))
        g.setColorAt(1, QColor(190, 140, 90))
        p.fillRect(self.rect(), g)
        rng = random.Random(1)  # sabit "manzara": daireler ve çizgiler
        p.setPen(Qt.PenStyle.NoPen)
        for _ in range(25):
            p.setBrush(QColor(rng.randrange(256), rng.randrange(256), rng.randrange(256), 90))
            s = rng.randint(40, 220)
            p.drawEllipse(rng.randrange(self.width()), rng.randrange(self.height()), s, s)
        p.setPen(QPen(QColor(255, 255, 255, 60), 3))
        for i in range(0, self.width(), 90):
            p.drawLine(i, self.height(), i + 200, 0)
        if self.args.animate:  # ekranda sürekli dolaşan bulut
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, 120))
            x = (self.frame * 6) % (self.width() + 300) - 300
            p.drawEllipse(x, 40, 300, 120)
        if self.args.behind:  # yazının arkasında sağa sola yürüyen "karakter"
            r = self._text_rect()
            span = max(1, r.width() + 200)
            cx = r.x() - 100 + abs((self.frame * 9) % (2 * span) - span)
            cy = r.y() + r.height() // 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(240, 200, 170))
            p.drawEllipse(cx - 30, cy - 110, 60, 60)  # kafa
            p.setBrush(QColor(200, 60, 80))
            p.drawRoundedRect(cx - 45, cy - 50, 90, 140, 20, 20)  # gövde
            p.setPen(QPen(QColor(240, 200, 170), 14))
            swing = 25 if (self.frame // 4) % 2 else -25
            p.drawLine(cx - 40, cy - 30, cx - 80, cy + swing)  # kollar
            p.drawLine(cx + 40, cy - 30, cx + 80, cy - swing)
        if self.text:
            r = self._text_rect()
            p.fillRect(r, QColor(10, 10, 30, 140 if self.args.behind else 210))
            p.setFont(self._font())
            p.setPen(QColor(255, 255, 255))
            fm = QFontMetrics(self._font())
            vis = self.text[: self.shown]
            if self.args.vertical:
                for i, ch in enumerate(vis):
                    p.drawText(r.x() + 4, r.y() + 4 + fm.ascent() + i * fm.height(), ch)
            else:
                p.drawText(r.x() + 8, r.y() + 4 + fm.ascent(), vis)
            if self.args.blink and self.blink_on and self.shown >= len(self.text):
                p.setPen(QColor(255, 220, 120))
                p.drawText(r.right() - 4, r.bottom() + fm.ascent(), "▼")
        p.end()

    def mousePressEvent(self, e):
        g = e.globalPosition().toPoint()
        print(json.dumps({"event": "click", "x": g.x(), "y": g.y()}), flush=True)
        if self.args.click_advance:
            self._advance()

    def _resume_typing(self):
        if self.shown < len(self.text):
            self.type_timer.start()

    def keyPressEvent(self, e):
        if self.args.click_advance and e.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return):
            self._advance()

    def _advance(self):
        """Görsel roman gibi: yazı akarken tıklayınca yazının tamamı gelir; bitmişse sıradaki
        replik (aynı yerde)."""
        if self.args.typewriter and self.shown < len(self.text):
            self.type_timer.stop()
            self.shown = len(self.text)
            self.update()
            self._report()
            return
        lines = LINES_BY_LANG[self.args.lang]
        self.args.line = ((self.args.line or 0) + 1) % len(lines)
        self.next_line()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="Fake Game")
    ap.add_argument("--typewriter", action="store_true", help="harf harf yazma efekti")
    ap.add_argument("--type-ms", type=int, default=60, help="harf başına ms (yazma efekti)")
    ap.add_argument("--pause-ms", type=int, default=0, help="、。, işaretlerinde duraksama (ms)")
    ap.add_argument("--lang", choices=sorted(LINES_BY_LANG), default="ja", help="replik dili")
    ap.add_argument("--vertical", action="store_true", help="dikey yazı (yalnızca Japonca)")
    ap.add_argument("--sizes", default="22,28,36", help="punto listesi (px)")
    ap.add_argument("--interval", type=float, default=4.0, help="replikler arası saniye")
    ap.add_argument("--line", type=int, help="yalnızca bu replik (test)")
    ap.add_argument("--pos", help="sabit konum X,Y (test)")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--blank", action="store_true", help="yazı gösterme (tıklama testi)")
    ap.add_argument("--animate", action="store_true", help="sürekli hareket eden arka plan")
    ap.add_argument("--behind", action="store_true",
                    help="yazının tam arkasında hareket eden karakter, yarı saydam metin paneli")
    ap.add_argument("--click-advance", action="store_true",
                    help="replik yalnızca tıklayınca / Boşluk / Enter ile ilerler (--pos ile aynı yerde)")
    ap.add_argument("--blink", action="store_true", help="replik sonunda yanıp sönen ▼ oku")
    ap.add_argument("--at", help="pencere konumu X,Y")
    ap.add_argument("--topmost", action="store_true", help="her zaman üstte (test: başka pencere örtmesin)")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    app = QApplication(sys.argv[:1])
    w = FakeGame(args)
    if args.topmost:
        w.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    if args.at:
        x, y = (int(v) for v in args.at.split(","))
        w.move(x, y)
    w.show()
    QTimer.singleShot(300, w.start)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

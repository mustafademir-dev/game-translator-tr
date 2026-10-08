"""Sahte oyun penceresi: düz olmayan arka plan üstünde rastgele konumda Japonca replikler.

Kullanım:
    venv\\Scripts\\python.exe tools\\fake_game.py [--typewriter] [--vertical] [--sizes 22,28,36]
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

LINES = [
    "田中さん、今日は学校に来ないんですか？",
    "もう遅いから、早く帰ったほうがいいよ。",
    "ちょっと待って！",
    "お兄ちゃん、朝ごはんできたよ！",
    "この町には、昔から不思議な言い伝えがあるらしい。",
    "大丈夫、心配しないで。",
    "放課後、屋上に来てください。",
    "知らない天井だ。",
]
JP_FONT = "Yu Gothic UI"


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
        self.type_timer = QTimer(self, interval=60, timeout=self._type_step)
        self.next_timer = QTimer(self, interval=int(args.interval * 1000), timeout=self.next_line)

    def start(self):
        if not self.args.blank:
            self.next_line()
            if self.args.line is None:
                self.next_timer.start()

    def _font(self) -> QFont:
        f = QFont(JP_FONT)
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
        self.index = self.args.line if self.args.line is not None else self.rng.randrange(len(LINES))
        self.text = LINES[self.index]
        self.size_px = self.rng.choice(self.sizes)
        r = self._text_rect()
        if self.args.pos:
            x, y = (int(v) for v in self.args.pos.split(","))
        else:
            x = self.rng.randint(20, max(20, self.width() - r.width() - 20))
            y = self.rng.randint(20, max(20, self.height() - r.height() - 20))
        self.pos = QPoint(x, y)
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
        if self.shown >= len(self.text):
            self.type_timer.stop()
            self._report()

    def _report(self):
        r = self._text_rect()
        tl = self.mapToGlobal(r.topLeft())
        print(json.dumps({"event": "line", "index": self.index,
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
        if self.text:
            r = self._text_rect()
            p.fillRect(r, QColor(10, 10, 30, 210))
            p.setFont(self._font())
            p.setPen(QColor(255, 255, 255))
            fm = QFontMetrics(self._font())
            vis = self.text[: self.shown]
            if self.args.vertical:
                for i, ch in enumerate(vis):
                    p.drawText(r.x() + 4, r.y() + 4 + fm.ascent() + i * fm.height(), ch)
            else:
                p.drawText(r.x() + 8, r.y() + 4 + fm.ascent(), vis)
        p.end()

    def mousePressEvent(self, e):
        g = e.globalPosition().toPoint()
        print(json.dumps({"event": "click", "x": g.x(), "y": g.y()}), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="Fake Game")
    ap.add_argument("--typewriter", action="store_true", help="harf harf yazma efekti")
    ap.add_argument("--vertical", action="store_true", help="dikey yazı")
    ap.add_argument("--sizes", default="22,28,36", help="punto listesi (px)")
    ap.add_argument("--interval", type=float, default=4.0, help="replikler arası saniye")
    ap.add_argument("--line", type=int, help="yalnızca bu replik (test)")
    ap.add_argument("--pos", help="sabit konum X,Y (test)")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--blank", action="store_true", help="yazı gösterme (tıklama testi)")
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

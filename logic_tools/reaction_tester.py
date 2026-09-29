# -*- coding: utf-8 -*-
import sys
import random
import time
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame)
from PySide6.QtCore import Qt, QTimer

class ReactionTester(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LOGIC · Reaction Speed")
        self.setFixedSize(480, 580)
        self.setStyleSheet("QWidget { background-color: #1e1e2e; color: #cdd6f4; font-family: 'Segoe UI'; }")
        self.state = "START"
        self.start_time = 0.0
        self.times = []
        self.build_ui()

    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)

        title = QLabel("REACTION SPEED")
        title.setStyleSheet("color: #6c7086; font-size: 13px; letter-spacing: 3px; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.stat = {}
        for key, lab in [("last","Last"),("avg","Avg"),("best","Best"),("runs","Runs")]:
            card = QFrame()
            card.setStyleSheet("QFrame { background-color: #181825; border-radius: 14px; }")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(6,10,6,10)
            t = QLabel(lab); t.setStyleSheet("color:#6c7086; font-size:11px;"); t.setAlignment(Qt.AlignCenter)
            v = QLabel("--"); v.setStyleSheet("color:#cdd6f4; font-size:20px; font-weight:bold;"); v.setAlignment(Qt.AlignCenter)
            cl.addWidget(t); cl.addWidget(v)
            self.stat[key] = v
            stats.addWidget(card)
        root.addLayout(stats)

        self.area = QLabel("Click to Start")
        self.area.setAlignment(Qt.AlignCenter)
        self.area.setMinimumHeight(380)
        self.paint_area("Click to Start", "#313244", "#cdd6f4")
        self.area.mousePressEvent = self.on_click
        root.addWidget(self.area)

        hint = QLabel("Wait for green. Don't jump early.")
        hint.setStyleSheet("color:#45475a; font-size:12px;")
        hint.setAlignment(Qt.AlignCenter)
        root.addWidget(hint)

    def paint_area(self, text, bg, fg):
        self.area.setText(text)
        self.area.setStyleSheet(f"QLabel {{ background-color:{bg}; border-radius:22px; color:{fg}; font-size:28px; font-weight:bold; }}")

    def on_click(self, event):
        if self.state == "START":
            self.state = "WAITING"
            self.paint_area("Wait for Green...", "#f38ba8", "#11111b")
            QTimer.singleShot(int(random.uniform(2,5)*1000), self.go)
        elif self.state == "WAITING":
            self.state = "START"
            self.paint_area("Too early!\nClick to Start", "#1e1e2e", "#f38ba8")
        elif self.state == "READY":
            rt = (time.time()-self.start_time)*1000
            self.times.append(rt)
            self.state = "START"
            self.paint_area(f"{rt:.0f} ms\nClick to Start", "#1e1e2e", "#a6e3a1")
            print(f"REACTION TIME: {rt:.2f}")
            self.refresh()

    def go(self):
        if self.state == "WAITING":
            self.state = "READY"
            self.paint_area("CLICK NOW!", "#a6e3a1", "#11111b")
            self.start_time = time.time()

    def refresh(self):
        self.stat["last"].setText(f"{self.times[-1]:.0f}")
        self.stat["avg"].setText(f"{sum(self.times)/len(self.times):.0f}")
        self.stat["best"].setText(f"{min(self.times):.0f}")
        self.stat["runs"].setText(str(len(self.times)))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = ReactionTester()
    w.show()
    ret = app.exec()
    print("Reaction Speed Tester closed.")
    sys.exit(ret)

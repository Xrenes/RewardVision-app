"""RewardVision — one button.

Press **Start**. It watches the whole screen and, whenever one of the
bundled Hazmob buttons is showing, clicks it: ``Watch`` on the Free Wall,
``CLAIM NOW!`` on the reward popup, ``Continue playing`` on the ad. No
order, no timers — a button appears, it gets clicked. Press **Stop**, or
**F9** from anywhere, to end it.

The button images live in ``examples/hazmob/`` and are bundled into the
build. Drop more PNGs there (tight crops, one per button) to have it
click those too.

Run from the project root:

    python app.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# DPI-aware before Qt starts, so screen coordinates are physical pixels.
try:  # pragma: no cover - platform specific
    import ctypes

    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from core.capture import CaptureEngine, virtual_desktop_bounds
from core.detector import detect_template
from core.paths import resource_path

APP_NAME = "RewardVision"

BUTTON_DIR = "examples/hazmob"     # where the bundled button PNGs live
MATCH_THRESHOLD = 0.83             # tight button crops match high; keep others out
SCAN_INTERVAL_S = 0.35            # gap between screen scans
BUTTON_COOLDOWN_S = 4.0          # per-button quiet time after a click


def _load_bgr(path: Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    return np.ascontiguousarray(rgb[:, :, ::-1])


def _button_paths() -> list[Path]:
    folder = resource_path(*BUTTON_DIR.split("/"))
    return sorted(folder.glob("*.png"))


# ---------------------------------------------------------------------------
# The worker: scan the screen, click any button that is on it
# ---------------------------------------------------------------------------


class Watcher(QThread):
    progress = Signal(str)
    finished_ok = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._running = False

    def stop(self) -> None:
        self._running = False

    def _sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(min(0.1, max(0.0, end - time.monotonic())))

    def run(self) -> None:  # noqa: D401
        self._running = True

        paths = _button_paths()
        if not paths:
            self.finished_ok.emit(
                f"No button images found in {BUTTON_DIR}. Nothing to do."
            )
            return
        try:
            buttons = [(p.stem, _load_bgr(p)) for p in paths]
        except Exception as exc:  # noqa: BLE001
            self.finished_ok.emit(f"Bad button image: {exc}")
            return

        try:
            from pynput.mouse import Button, Controller

            mouse = Controller()
        except Exception as exc:  # noqa: BLE001
            self.finished_ok.emit(f"Mouse control unavailable: {exc}")
            return

        try:
            engine = CaptureEngine(region=virtual_desktop_bounds())
        except Exception as exc:  # noqa: BLE001
            self.finished_ok.emit(f"Screen capture failed: {exc}")
            return

        next_ok: dict[str, float] = {name: 0.0 for name, _ in buttons}
        clicks = 0
        self.progress.emit(
            "Watching the screen… open Hazmob's Free Wall. Stop or F9 to end."
        )

        try:
            while self._running:
                now = time.monotonic()
                frame = engine.capture_frame()
                acted = False
                for name, tpl in buttons:
                    if not self._running:
                        break
                    if now < next_ok[name]:
                        continue
                    det = detect_template(frame.image, tpl, MATCH_THRESHOLD)
                    if not det.found:
                        continue
                    cx = frame.region["left"] + det.x + det.width // 2
                    cy = frame.region["top"] + det.y + det.height // 2
                    mouse.position = (cx, cy)
                    time.sleep(0.05)
                    mouse.click(Button.left, 1)
                    clicks += 1
                    next_ok[name] = time.monotonic() + BUTTON_COOLDOWN_S
                    self.progress.emit(f"Clicked '{name}'  ·  {clicks} total")
                    acted = True
                    time.sleep(0.35)  # let the screen begin to change
                    break  # rescan from the top
                if not acted:
                    self._sleep(SCAN_INTERVAL_S)
            self.finished_ok.emit(f"Stopped. {clicks} click(s) this run.")
        finally:
            engine.close()


# ---------------------------------------------------------------------------
# The window: a label and one button
# ---------------------------------------------------------------------------


class Window(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle(APP_NAME)
        self.resize(360, 200)

        self._watcher: Watcher | None = None
        self._hotkey = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        root.addWidget(title)

        self._button = QPushButton("Start")
        self._button.setObjectName("Primary")
        self._button.setMinimumHeight(48)
        self._button.clicked.connect(self._toggle)
        root.addWidget(self._button)

        n = len(_button_paths())
        self._status = QLabel(
            f"{n} button(s) loaded.  Press Start."
            if n
            else f"No buttons found in {BUTTON_DIR}."
        )
        self._status.setObjectName("Status")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        root.addStretch(1)

        hint = QLabel("F9 stops it from anywhere.")
        hint.setObjectName("Status")
        root.addWidget(hint)

        self._install_hotkey()

    def _toggle(self) -> None:
        if self._watcher is None:
            self._start()
        else:
            self._stop()

    def _start(self) -> None:
        self._watcher = Watcher()
        self._watcher.progress.connect(self._status.setText)
        self._watcher.finished_ok.connect(self._on_finished)
        self._button.setText("Stop")
        self._button.setObjectName("Danger")
        self._repolish(self._button)
        self._watcher.start()

    def _stop(self) -> None:
        if self._watcher:
            self._watcher.stop()
            self._status.setText("Stopping…")

    def _on_finished(self, message: str) -> None:
        self._status.setText(message)
        if self._watcher:
            self._watcher.wait(2000)
        self._watcher = None
        self._button.setText("Start")
        self._button.setObjectName("Primary")
        self._repolish(self._button)

    @staticmethod
    def _repolish(w: QWidget) -> None:
        w.style().unpolish(w)
        w.style().polish(w)

    def _install_hotkey(self) -> None:
        try:
            from pynput import keyboard
        except Exception:  # noqa: BLE001
            return

        def _on_press(key) -> None:
            if key == keyboard.Key.f9:
                from PySide6.QtCore import QTimer

                QTimer.singleShot(0, self._stop)

        try:
            self._hotkey = keyboard.Listener(on_press=_on_press)
            self._hotkey.daemon = True
            self._hotkey.start()
        except Exception:  # noqa: BLE001
            self._hotkey = None

    def closeEvent(self, e) -> None:  # noqa: N802
        if self._watcher:
            self._watcher.stop()
            self._watcher.wait(2000)
        if self._hotkey is not None:
            try:
                self._hotkey.stop()
            except Exception:  # noqa: BLE001
                pass
        super().closeEvent(e)


def main() -> int:
    from ui.theme import build_qss

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(build_qss())
    win = Window()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

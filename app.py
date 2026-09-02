"""RewardVision — minimal screenshot-and-click automation.

One window. Pick a folder. Each step is a full-screen screenshot plus one
click position (always a left click). Run watches the screen for each
step's screenshot in order and clicks when it appears; it goes through the
list once and stops.

Steps are stored in the chosen folder as PNG files named

    001_x1240_y560.png

— the number sets the order, the ``x`` / ``y`` are the click position in
screen pixels. That's the whole format; the folder is self-contained.

Run from the project root:

    python app.py
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

# Be DPI-aware before Qt starts so screen coordinates are physical pixels
# and match what the capture / click layers use.
try:  # pragma: no cover - platform specific
    import ctypes

    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:  # noqa: BLE001
    pass

import numpy as np
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.capture import CaptureEngine, virtual_desktop_bounds
from core.detector import detect_template

APP_NAME = "RewardVision"
MATCH_THRESHOLD = 0.80
STEP_TIMEOUT_S = 20.0
POLL_INTERVAL_S = 0.4
_FILENAME_RE = re.compile(r"^(\d+)_x(-?\d+)_y(-?\d+)\.png$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Step storage
# ---------------------------------------------------------------------------


class Step:
    def __init__(self, path: Path, order: int, x: int, y: int) -> None:
        self.path = path
        self.order = order
        self.x = x
        self.y = y

    @property
    def label(self) -> str:
        return f"{self.order:03d}   click ({self.x}, {self.y})"


def load_steps(folder: Path) -> list[Step]:
    steps: list[Step] = []
    for p in sorted(folder.glob("*.png")):
        m = _FILENAME_RE.match(p.name)
        if m:
            steps.append(Step(p, int(m.group(1)), int(m.group(2)), int(m.group(3))))
    steps.sort(key=lambda s: s.order)
    return steps


def next_order(folder: Path) -> int:
    existing = [s.order for s in load_steps(folder)]
    return (max(existing) + 1) if existing else 1


def save_step(folder: Path, image_bgr: np.ndarray, x: int, y: int) -> Path:
    order = next_order(folder)
    path = folder / f"{order:03d}_x{x}_y{y}.png"
    from PIL import Image

    rgb = np.ascontiguousarray(image_bgr[:, :, ::-1])
    Image.fromarray(rgb, "RGB").save(path, "PNG")
    return path


def renumber(folder: Path) -> None:
    """Close gaps after a delete so orders stay 1..N."""
    steps = load_steps(folder)
    for i, s in enumerate(steps, start=1):
        want = folder / f"{i:03d}_x{s.x}_y{s.y}.png"
        if want != s.path:
            s.path.rename(want)


# ---------------------------------------------------------------------------
# Screenshot + click-point capture overlay
# ---------------------------------------------------------------------------


class CaptureOverlay(QWidget):
    """Shows the just-taken screenshot full screen; a click picks the point."""

    picked = Signal(int, int)   # screen x, y
    cancelled = Signal()

    def __init__(self, image_bgr: np.ndarray, bounds: dict) -> None:
        super().__init__()
        self._img = image_bgr
        self._bounds = bounds
        h, w = image_bgr.shape[:2]
        rgb = np.ascontiguousarray(image_bgr[:, :, ::-1])
        self._pixmap = QPixmap.fromImage(
            QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        )
        self._src = (w, h)
        self._done = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        dpr = self._dpr()
        self.setGeometry(
            int(bounds["left"] / dpr), int(bounds["top"] / dpr),
            int(bounds["width"] / dpr), int(bounds["height"] / dpr),
        )

    @staticmethod
    def _dpr() -> float:
        s = QGuiApplication.primaryScreen()
        return float(s.devicePixelRatio()) if s else 1.0

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._done or e.button() != Qt.MouseButton.LeftButton:
            return
        self._done = True
        dpr = self._dpr()
        x = self._bounds["left"] + int(round(e.position().x() * dpr))
        y = self._bounds["top"] + int(round(e.position().y() * dpr))
        self.picked.emit(x, y)
        self.close()

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape and not self._done:
            self._done = True
            self.cancelled.emit()
            self.close()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 60))
        p.setPen(QColor("#F4F7FB"))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                   "\nClick where the mouse should click   ·   Esc to cancel")


# ---------------------------------------------------------------------------
# Runner thread
# ---------------------------------------------------------------------------


class Runner(QThread):
    progress = Signal(str)
    finished_ok = Signal(str)

    def __init__(self, steps: list[Step]) -> None:
        super().__init__()
        self._steps = steps
        self._running = False

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:  # noqa: D401
        self._running = True
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

        try:
            for i, step in enumerate(self._steps, start=1):
                if not self._running:
                    self.finished_ok.emit("Stopped.")
                    return
                try:
                    template = _load_bgr(step.path)
                except Exception as exc:  # noqa: BLE001
                    self.finished_ok.emit(f"Step {i}: bad image ({exc})")
                    return

                self.progress.emit(f"Waiting for step {i}/{len(self._steps)}…")
                deadline = time.monotonic() + STEP_TIMEOUT_S
                seen = False
                while self._running and time.monotonic() < deadline:
                    frame = engine.capture_frame()
                    if detect_template(frame.image, template, MATCH_THRESHOLD).found:
                        seen = True
                        break
                    time.sleep(POLL_INTERVAL_S)

                if not self._running:
                    self.finished_ok.emit("Stopped.")
                    return
                if not seen:
                    self.finished_ok.emit(
                        f"Step {i} not found on screen after {STEP_TIMEOUT_S:.0f}s — stopped."
                    )
                    return

                mouse.position = (step.x, step.y)
                time.sleep(0.05)
                mouse.click(Button.left, 1)
                self.progress.emit(f"Clicked step {i}/{len(self._steps)} at ({step.x}, {step.y})")
                time.sleep(0.3)

            self.finished_ok.emit("Done — all steps completed.")
        finally:
            engine.close()


def _load_bgr(path: Path) -> np.ndarray:
    from PIL import Image

    with Image.open(path) as im:
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint8)
    return np.ascontiguousarray(rgb[:, :, ::-1])


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class Window(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Root")
        self.setWindowTitle(APP_NAME)
        self.resize(540, 520)
        self._folder: Path | None = None
        self._runner: Runner | None = None
        self._overlay: CaptureOverlay | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        # folder row
        frow = QHBoxLayout()
        self._folder_label = QLabel("No folder selected")
        self._folder_label.setObjectName("FolderPath")
        browse = QPushButton("Choose Folder…")
        browse.clicked.connect(self._choose_folder)
        frow.addWidget(self._folder_label, stretch=1)
        frow.addWidget(browse)
        root.addLayout(frow)

        # step list
        self._list = QListWidget()
        self._list.setIconSize(self._list.iconSize().__class__(120, 68))
        self._list.setSpacing(2)
        root.addWidget(self._list, stretch=1)

        # step buttons
        srow = QHBoxLayout()
        self._add_btn = QPushButton("Add Step")
        self._add_btn.clicked.connect(self._add_step)
        self._del_btn = QPushButton("Delete Step")
        self._del_btn.clicked.connect(self._delete_step)
        srow.addWidget(self._add_btn)
        srow.addWidget(self._del_btn)
        srow.addStretch(1)
        root.addLayout(srow)

        # run row
        rrow = QHBoxLayout()
        self._run_btn = QPushButton("Run")
        self._run_btn.setObjectName("Primary")
        self._run_btn.clicked.connect(self._run)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("Danger")
        self._stop_btn.clicked.connect(self._stop)
        self._stop_btn.setEnabled(False)
        rrow.addWidget(self._run_btn)
        rrow.addWidget(self._stop_btn)
        rrow.addStretch(1)
        root.addLayout(rrow)

        self._status = QLabel("Choose a folder to begin.")
        self._status.setObjectName("Status")
        root.addWidget(self._status)

        self._set_controls(folder_ready=False)

    # -- folder -----------------------------------------------------------

    def _choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Automation folder")
        if not chosen:
            return
        self._folder = Path(chosen)
        self._folder_label.setObjectName("FolderPathSet")
        self._folder_label.style().unpolish(self._folder_label)
        self._folder_label.style().polish(self._folder_label)
        self._folder_label.setText(str(self._folder))
        self._reload()
        self._set_controls(folder_ready=True)
        self._status.setText(f"{self._list.count()} step(s) loaded.")

    def _reload(self) -> None:
        self._list.clear()
        if not self._folder:
            return
        for step in load_steps(self._folder):
            item = QListWidgetItem(step.label)
            pix = QPixmap(str(step.path))
            if not pix.isNull():
                item.setIcon(pix.scaled(120, 68, Qt.AspectRatioMode.KeepAspectRatio,
                                        Qt.TransformationMode.SmoothTransformation))
            item.setData(Qt.ItemDataRole.UserRole, str(step.path))
            self._list.addItem(item)

    # -- steps ----------------------------------------------------------

    def _add_step(self) -> None:
        if not self._folder:
            return
        # Minimise the app first so it is not in the screenshot, then wait a
        # moment for the window to actually leave the screen before grabbing.
        self._status.setText("Minimising… taking screenshot")
        self.showMinimized()
        from PySide6.QtCore import QTimer

        QTimer.singleShot(350, self._capture_after_minimise)

    def _capture_after_minimise(self) -> None:
        try:
            bounds = virtual_desktop_bounds()
            with CaptureEngine(region=bounds) as eng:
                image = eng.capture_frame().image
        except Exception as exc:  # noqa: BLE001
            self.showNormal()
            self.raise_()
            QMessageBox.warning(self, APP_NAME, f"Screenshot failed:\n{exc}")
            return

        overlay = CaptureOverlay(image, bounds)
        self._overlay = overlay

        def _restore() -> None:
            self._overlay = None
            self.showNormal()
            self.raise_()
            self.activateWindow()

        def _picked(x: int, y: int) -> None:
            _restore()
            try:
                save_step(self._folder, image, x, y)
            except Exception as exc:  # noqa: BLE001
                QMessageBox.warning(self, APP_NAME, f"Could not save step:\n{exc}")
                return
            self._reload()
            self._status.setText(f"Step added: click ({x}, {y}). {self._list.count()} total.")

        def _cancelled() -> None:
            _restore()
            self._status.setText("Step cancelled.")

        overlay.picked.connect(_picked)
        overlay.cancelled.connect(_cancelled)
        overlay.showFullScreen()
        overlay.raise_()
        overlay.activateWindow()
        overlay.setFocus()

    def _delete_step(self) -> None:
        if not self._folder:
            return
        item = self._list.currentItem()
        if item is None:
            return
        path = Path(item.data(Qt.ItemDataRole.UserRole))
        if QMessageBox.question(self, APP_NAME, f"Delete {path.name}?") \
                != QMessageBox.StandardButton.Yes:
            return
        try:
            path.unlink()
        except OSError:
            pass
        renumber(self._folder)
        self._reload()
        self._status.setText(f"{self._list.count()} step(s).")

    # -- run ------------------------------------------------------------

    def _run(self) -> None:
        if not self._folder:
            return
        steps = load_steps(self._folder)
        if not steps:
            QMessageBox.information(self, APP_NAME, "No steps to run. Add one first.")
            return
        self._runner = Runner(steps)
        self._runner.progress.connect(self._status.setText)
        self._runner.finished_ok.connect(self._on_finished)
        self._set_running(True)
        self._runner.start()

    def _stop(self) -> None:
        if self._runner:
            self._runner.stop()
            self._status.setText("Stopping…")

    def _on_finished(self, message: str) -> None:
        self._status.setText(message)
        if self._runner:
            self._runner.wait(2000)
        self._runner = None
        self._set_running(False)

    # -- control state -------------------------------------------------

    def _set_controls(self, *, folder_ready: bool) -> None:
        for b in (self._add_btn, self._del_btn, self._run_btn):
            b.setEnabled(folder_ready)

    def _set_running(self, running: bool) -> None:
        self._run_btn.setEnabled(not running and self._folder is not None)
        self._add_btn.setEnabled(not running and self._folder is not None)
        self._del_btn.setEnabled(not running and self._folder is not None)
        self._stop_btn.setEnabled(running)

    def closeEvent(self, e) -> None:  # noqa: N802
        if self._runner:
            self._runner.stop()
            self._runner.wait(2000)
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

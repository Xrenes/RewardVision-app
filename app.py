"""RewardVision — minimal screenshot-and-click automation.

One window. Pick a folder. Each step is a full-screen screenshot plus one
click position (always a left click). Run watches the screen for each
step's screenshot in order and clicks when it appears.

By default it goes through the list once and stops. Tick **Repeat** and it
loops forever, waiting the given number of seconds between passes — the
intent behind the name: leave it collecting a game's timed rewards.

Steps are stored in the chosen folder as PNG files named

    001_x1240_y560.png        # required: click screen (1240, 560)
    003_x0980_y430_opt.png    # "_opt": skip this step if not found in time

— the number sets the order, the ``x`` / ``y`` are the click position in
screen pixels, and a trailing ``_opt`` marks the step optional (a missing
optional step is skipped instead of aborting the pass; use it for the
"Continue" button of an ad that only appears sometimes). When a step is
found, the click lands on the *centre of the match* if that is close to
the recorded point, otherwise on the recorded point itself.

Press **F9** at any time — even with the game focused — to stop.

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
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.capture import CaptureEngine, virtual_desktop_bounds
from core.detector import detect_template

APP_NAME = "RewardVision"
MATCH_THRESHOLD = 0.80
STEP_TIMEOUT_S = 20.0
POLL_INTERVAL_S = 0.4
# How far the centre of a match may sit from the recorded click point and
# still be trusted (screen pixels). Beyond this we fall back to the
# recorded point — the template probably matched something incidental.
CLICK_SNAP_PX = 220
_FILENAME_RE = re.compile(
    r"^(\d+)_x(-?\d+)_y(-?\d+)(_opt)?\.png$", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Step storage
# ---------------------------------------------------------------------------


class Step:
    def __init__(
        self, path: Path, order: int, x: int, y: int, optional: bool = False
    ) -> None:
        self.path = path
        self.order = order
        self.x = x
        self.y = y
        self.optional = optional

    @property
    def label(self) -> str:
        tag = "  ·  optional" if self.optional else ""
        return f"{self.order:03d}   click ({self.x}, {self.y}){tag}"


def load_steps(folder: Path) -> list[Step]:
    steps: list[Step] = []
    for p in sorted(folder.glob("*.png")):
        m = _FILENAME_RE.match(p.name)
        if m:
            steps.append(
                Step(
                    p,
                    int(m.group(1)),
                    int(m.group(2)),
                    int(m.group(3)),
                    optional=bool(m.group(4)),
                )
            )
    steps.sort(key=lambda s: s.order)
    return steps


def next_order(folder: Path) -> int:
    existing = [s.order for s in load_steps(folder)]
    return (max(existing) + 1) if existing else 1


def save_step(folder: Path, image_bgr: np.ndarray, x: int, y: int) -> Path:
    order = next_order(folder)
    path = folder / _step_filename(order, x, y, optional=False)
    from PIL import Image

    rgb = np.ascontiguousarray(image_bgr[:, :, ::-1])
    Image.fromarray(rgb, "RGB").save(path, "PNG")
    return path


def _step_filename(order: int, x: int, y: int, optional: bool) -> str:
    return f"{order:03d}_x{x}_y{y}{'_opt' if optional else ''}.png"


def renumber(folder: Path) -> None:
    """Close gaps after a delete so orders stay 1..N."""
    steps = load_steps(folder)
    for i, s in enumerate(steps, start=1):
        want = folder / _step_filename(i, s.x, s.y, s.optional)
        if want != s.path:
            s.path.rename(want)


def set_step_optional(step: Step, optional: bool) -> Path:
    """Rename a step's PNG to add or drop the ``_opt`` marker."""
    want = step.path.with_name(
        _step_filename(step.order, step.x, step.y, optional)
    )
    if want != step.path:
        step.path.rename(want)
    return want


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

    def __init__(
        self, steps: list[Step], *, repeat: bool = False, wait_s: int = 120
    ) -> None:
        super().__init__()
        self._steps = steps
        self._repeat = repeat
        self._wait_s = max(0, int(wait_s))
        self._running = False

    def stop(self) -> None:
        self._running = False

    # -- helpers ---------------------------------------------------------

    def _sleep_interruptible(self, seconds: float) -> None:
        """Sleep in short slices so Stop / F9 takes effect promptly."""
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(min(0.2, end - time.monotonic()))

    def _click_point(self, step: Step, det) -> tuple[int, int]:
        """Where to actually click: the match centre when it is near the
        recorded point, otherwise the recorded point."""
        cx = det.x + det.width // 2
        cy = det.y + det.height // 2
        if abs(cx - step.x) <= CLICK_SNAP_PX and abs(cy - step.y) <= CLICK_SNAP_PX:
            return cx, cy
        return step.x, step.y

    def _run_one_pass(self, engine, mouse, Button) -> str | None:
        """Execute every step once. Return an error string to abort the
        whole run, or None to carry on (loop or finish normally)."""
        total = len(self._steps)
        for i, step in enumerate(self._steps, start=1):
            if not self._running:
                return None
            try:
                template = _load_bgr(step.path)
            except Exception as exc:  # noqa: BLE001
                return f"Step {i}: bad image ({exc})"

            kind = "optional " if step.optional else ""
            self.progress.emit(f"Waiting for {kind}step {i}/{total}…")
            deadline = time.monotonic() + STEP_TIMEOUT_S
            det = None
            while self._running and time.monotonic() < deadline:
                frame = engine.capture_frame()
                d = detect_template(frame.image, template, MATCH_THRESHOLD)
                if d.found:
                    det = d
                    break
                time.sleep(POLL_INTERVAL_S)

            if not self._running:
                return None
            if det is None:
                if step.optional:
                    self.progress.emit(f"Step {i}/{total} not shown — skipped.")
                    continue
                return (
                    f"Step {i} not found on screen after "
                    f"{STEP_TIMEOUT_S:.0f}s — stopped."
                )

            x, y = self._click_point(step, det)
            mouse.position = (x, y)
            time.sleep(0.05)
            mouse.click(Button.left, 1)
            self.progress.emit(f"Clicked step {i}/{total} at ({x}, {y})")
            time.sleep(0.3)
        return None

    # -- thread body ---------------------------------------------------

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

        cycles = 0
        try:
            while self._running:
                err = self._run_one_pass(engine, mouse, Button)
                if err is not None:
                    self.finished_ok.emit(err)
                    return
                if not self._running:
                    self.finished_ok.emit(
                        f"Stopped after {cycles} full cycle(s)."
                        if cycles
                        else "Stopped."
                    )
                    return
                cycles += 1
                if not self._repeat:
                    self.finished_ok.emit("Done — all steps completed.")
                    return
                mins = self._wait_s / 60
                self.progress.emit(
                    f"Cycle {cycles} done. Waiting {self._wait_s}s "
                    f"(~{mins:.1f} min) before the next…"
                )
                self._sleep_interruptible(self._wait_s)
            self.finished_ok.emit(
                f"Stopped after {cycles} full cycle(s)."
                if cycles
                else "Stopped."
            )
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
        self._hotkey = None  # pynput keyboard listener, if available

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
        self._opt_btn = QPushButton("Toggle Optional")
        self._opt_btn.clicked.connect(self._toggle_optional)
        srow.addWidget(self._add_btn)
        srow.addWidget(self._del_btn)
        srow.addWidget(self._opt_btn)
        srow.addStretch(1)
        root.addLayout(srow)

        # loop options row
        lrow = QHBoxLayout()
        self._repeat_cb = QCheckBox("Repeat")
        self._repeat_cb.toggled.connect(self._on_repeat_toggled)
        self._wait_label = QLabel("wait")
        self._wait_label.setObjectName("Status")
        self._wait_spin = QSpinBox()
        self._wait_spin.setRange(0, 24 * 60 * 60)
        self._wait_spin.setValue(120)
        self._wait_spin.setSuffix(" s")
        self._wait_spin.setSingleStep(10)
        self._wait_spin.setEnabled(False)
        lrow.addWidget(self._repeat_cb)
        lrow.addWidget(self._wait_label)
        lrow.addWidget(self._wait_spin)
        lrow.addStretch(1)
        root.addLayout(lrow)

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

        self._status = QLabel("Choose a folder to begin.  ·  F9 stops from anywhere.")
        self._status.setObjectName("Status")
        root.addWidget(self._status)

        self._set_controls(folder_ready=False)
        self._install_hotkey()

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

    def _toggle_optional(self) -> None:
        """Flip the selected step between required and optional (``_opt``)."""
        if not self._folder:
            return
        item = self._list.currentItem()
        if item is None:
            self._status.setText("Select a step first.")
            return
        sel = Path(item.data(Qt.ItemDataRole.UserRole))
        steps = load_steps(self._folder)
        step = next((s for s in steps if s.path == sel), None)
        if step is None:
            return
        try:
            set_step_optional(step, not step.optional)
        except OSError as exc:
            QMessageBox.warning(self, APP_NAME, f"Could not rename step:\n{exc}")
            return
        self._reload()
        now = "optional" if not step.optional else "required"
        self._status.setText(f"Step {step.order:03d} is now {now}.")

    # -- loop options -------------------------------------------------

    def _on_repeat_toggled(self, on: bool) -> None:
        self._wait_spin.setEnabled(on and self._runner is None)
        if on:
            self._status.setText(
                "Repeat on — after the last step it waits, then runs again. "
                "F9 or Stop to end."
            )

    # -- global hotkey ----------------------------------------------

    def _install_hotkey(self) -> None:
        """Listen for F9 process-wide so the run can be stopped even when
        the game window has focus. Best-effort: if pynput's listener will
        not start, the on-screen Stop button still works."""
        try:
            from pynput import keyboard
        except Exception:  # noqa: BLE001
            return

        def _on_press(key) -> None:
            if key == keyboard.Key.f9:
                # Called from the listener thread; hop to the GUI thread.
                from PySide6.QtCore import QTimer

                QTimer.singleShot(0, self._stop)

        try:
            self._hotkey = keyboard.Listener(on_press=_on_press)
            self._hotkey.daemon = True
            self._hotkey.start()
        except Exception:  # noqa: BLE001
            self._hotkey = None

    # -- run ------------------------------------------------------------

    def _run(self) -> None:
        if not self._folder:
            return
        steps = load_steps(self._folder)
        if not steps:
            QMessageBox.information(self, APP_NAME, "No steps to run. Add one first.")
            return
        self._runner = Runner(
            steps,
            repeat=self._repeat_cb.isChecked(),
            wait_s=self._wait_spin.value(),
        )
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
        for b in (self._add_btn, self._del_btn, self._opt_btn, self._run_btn):
            b.setEnabled(folder_ready)

    def _set_running(self, running: bool) -> None:
        ready = self._folder is not None
        self._run_btn.setEnabled(not running and ready)
        self._add_btn.setEnabled(not running and ready)
        self._del_btn.setEnabled(not running and ready)
        self._opt_btn.setEnabled(not running and ready)
        self._repeat_cb.setEnabled(not running)
        self._wait_spin.setEnabled(
            not running and self._repeat_cb.isChecked()
        )
        self._stop_btn.setEnabled(running)

    def closeEvent(self, e) -> None:  # noqa: N802
        if self._runner:
            self._runner.stop()
            self._runner.wait(2000)
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

"""Screen capture engine (spec section 23).

A thin, Qt-free wrapper around :mod:`mss`. It enumerates monitors, holds a
target region in virtual-desktop coordinates, and returns frames as
BGR ``numpy`` arrays. Threading and signalling live in
:mod:`core.capture_worker`; this module is synchronous and testable on its
own.

MSS is **not thread-safe** and its handles are expensive to recreate, so
each :class:`CaptureEngine` owns one :class:`mss.mss` instance and callers
must not share an engine across threads. The worker creates its engine
inside ``run()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

try:  # mss is a hard dependency from Phase 3 on; keep the import error clear.
    import mss
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "python-mss is required for screen capture. Run "
        "`pip install -r requirements.txt`."
    ) from exc


Region = dict[str, int]  # keys: left, top, width, height (virtual-desktop px)


@dataclass(frozen=True)
class MonitorInfo:
    """Geometry of one monitor in virtual-desktop coordinates.

    ``index`` matches the MSS convention: index 0 is the virtual bounding
    box of every monitor, index 1..N are the physical monitors.
    """

    index: int
    left: int
    top: int
    width: int
    height: int
    primary: bool

    @property
    def region(self) -> Region:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class Frame:
    """One captured image plus the region it came from.

    Attributes:
        image: ``(H, W, 3)`` uint8 array in BGR order, C-contiguous.
        region: The virtual-desktop rectangle the image covers. Add
            ``region['left']`` / ``region['top']`` to an in-image point to
            get an absolute screen coordinate (used by the action engine).
    """

    image: np.ndarray
    region: Region

    @property
    def width(self) -> int:
        return self.image.shape[1]

    @property
    def height(self) -> int:
        return self.image.shape[0]

    def to_screen(self, x: int, y: int) -> tuple[int, int]:
        """Convert an in-image point to an absolute screen coordinate."""
        return self.region["left"] + int(x), self.region["top"] + int(y)


def _clamp_region(region: Region, bounds: MonitorInfo) -> Region:
    """Clip ``region`` so it lies fully inside ``bounds``.

    Width/height are pinned to at least 1px; the origin is moved inward
    before the size is trimmed so a request that is merely off-position
    still yields a usable rectangle.
    """
    left = int(region.get("left", bounds.left))
    top = int(region.get("top", bounds.top))
    width = max(1, int(region.get("width", bounds.width)))
    height = max(1, int(region.get("height", bounds.height)))

    left = min(max(left, bounds.left), bounds.left + bounds.width - 1)
    top = min(max(top, bounds.top), bounds.top + bounds.height - 1)
    width = min(width, bounds.left + bounds.width - left)
    height = min(height, bounds.top + bounds.height - top)
    return {"left": left, "top": top, "width": width, "height": height}


class CaptureEngine:
    """Synchronous monitor / region grabber."""

    def __init__(self, monitor: int = 1, region: Region | None = None) -> None:
        self._sct = mss.mss()
        self._monitors = self._enumerate()
        self._monitor_index = self._valid_index(monitor)
        self._region: Region | None = None
        self.set_region(region)

    # -- setup ----------------------------------------------------------------

    def _enumerate(self) -> list[MonitorInfo]:
        infos: list[MonitorInfo] = []
        raw = self._sct.monitors  # [0] = virtual bbox, [1..] = physical
        for i, m in enumerate(raw):
            infos.append(
                MonitorInfo(
                    index=i,
                    left=int(m["left"]),
                    top=int(m["top"]),
                    width=int(m["width"]),
                    height=int(m["height"]),
                    # MSS has no primary flag; the physical monitor whose
                    # origin is (0, 0) is Windows' primary.
                    primary=(i >= 1 and m["left"] == 0 and m["top"] == 0),
                )
            )
        return infos

    def _valid_index(self, index: int) -> int:
        physical = [m.index for m in self._monitors if m.index >= 1]
        if index in physical:
            return index
        return physical[0] if physical else 0

    def get_monitors(self) -> list[MonitorInfo]:
        """Return the physical monitors (excludes the virtual bounding box)."""
        return [m for m in self._monitors if m.index >= 1]

    def virtual_desktop(self) -> MonitorInfo:
        """The bounding box of every monitor (MSS index 0).

        Used by the region-selector overlay so its geometry and the stored
        region share one coordinate system.
        """
        return self._monitors[0]

    def current_monitor(self) -> MonitorInfo:
        return self._monitors[self._monitor_index]

    def set_monitor(self, index: int) -> None:
        self._monitor_index = self._valid_index(index)
        # Re-clamp any existing region against the new monitor.
        self.set_region(self._region)

    def set_region(self, region: Region | None) -> None:
        """Set the capture rectangle. ``None`` captures the whole monitor."""
        mon = self.current_monitor()
        if region is None:
            self._region = mon.region
        else:
            self._region = _clamp_region(region, mon)

    @property
    def region(self) -> Region:
        assert self._region is not None
        return dict(self._region)

    # -- capture ------------------------------------------------------------

    def capture_frame(self) -> Frame:
        """Grab one frame of the current region as a BGR array."""
        region = self.region
        raw = self._sct.grab(region)  # BGRA bytes
        # np.asarray on an mss ScreenShot yields (H, W, 4) BGRA.
        bgra = np.asarray(raw, dtype=np.uint8)
        bgr = np.ascontiguousarray(bgra[:, :, :3])  # drop alpha -> BGR
        return Frame(image=bgr, region=region)

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:  # noqa: BLE001 - closing must never raise
            pass

    def __enter__(self) -> "CaptureEngine":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def virtual_desktop_bounds() -> Region:
    """Return the all-monitors bounding box as a region dict.

    A convenience wrapper that opens and closes its own MSS handle, for
    callers (the region-selector overlay) that only need the geometry.
    """
    with CaptureEngine() as eng:
        return eng.virtual_desktop().region

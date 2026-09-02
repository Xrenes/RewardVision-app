"""Template-matching detection engine (spec sections 4, 6, 26).

Given a captured frame and one or more template images, report whether a
template is present and where. Uses OpenCV ``matchTemplate`` with
``TM_CCOEFF_NORMED`` (score 0..1). Optional grayscale and multi-scale
matching mirror the settings in spec section 33.

Everything here is synchronous and Qt-free; the automation controller
(Phase 8) drives it from a worker thread.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from services.logger import get_logger

log = get_logger()

# Scales tried when multi-scale matching is enabled. 1.0 first so an exact
# match wins ties.
_MULTI_SCALES: tuple[float, ...] = (1.0, 0.9, 1.1, 0.8, 1.2, 0.75, 1.33)


@dataclass(frozen=True)
class Detection:
    """Result of matching one template against one frame.

    Coordinates are in frame pixels: ``(x, y)`` is the top-left of the
    matched box, ``center`` its middle. When ``found`` is False the box
    fields still carry the best (sub-threshold) match for calibration.
    """

    found: bool
    confidence: float
    x: int
    y: int
    width: int
    height: int
    scale: float = 1.0

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2

    def as_dict(self) -> dict:
        return {
            "found": self.found,
            "confidence": round(self.confidence, 4),
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "scale": self.scale,
        }


def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _match_once(
    frame: np.ndarray, template: np.ndarray
) -> tuple[float, int, int, int, int]:
    """Return (score, x, y, w, h) for the single best location."""
    th, tw = template.shape[:2]
    fh, fw = frame.shape[:2]
    if th > fh or tw > fw:
        return -1.0, 0, 0, tw, th
    result = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    _min_v, max_v, _min_l, max_l = cv2.minMaxLoc(result)
    return float(max_v), int(max_l[0]), int(max_l[1]), tw, th


def detect_template(
    frame: np.ndarray,
    template: np.ndarray,
    threshold: float,
    *,
    grayscale: bool = False,
    multi_scale: bool = False,
) -> Detection:
    """Locate ``template`` in ``frame``.

    Args:
        frame: ``(H, W, 3)`` BGR (or ``(H, W)`` gray) uint8 array.
        template: template image in the same colour convention.
        threshold: minimum ``TM_CCOEFF_NORMED`` score to count as found.
        grayscale: match on luminance only (faster, lighting-tolerant).
        multi_scale: also try the template resized by a set of factors.

    Returns:
        A :class:`Detection`. Always returns the best candidate found, with
        ``found`` set according to ``threshold``.
    """
    if frame is None or template is None or frame.size == 0 or template.size == 0:
        return Detection(False, 0.0, 0, 0, 0, 0)

    f = _to_gray(frame) if grayscale else frame
    t0 = _to_gray(template) if grayscale else template

    scales = _MULTI_SCALES if multi_scale else (1.0,)
    best: tuple[float, int, int, int, int, float] = (-1.0, 0, 0, 0, 0, 1.0)

    for scale in scales:
        if scale == 1.0:
            t = t0
        else:
            new_w = max(1, int(round(t0.shape[1] * scale)))
            new_h = max(1, int(round(t0.shape[0] * scale)))
            interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
            t = cv2.resize(t0, (new_w, new_h), interpolation=interp)

        score, x, y, w, h = _match_once(f, t)
        if score > best[0]:
            best = (score, x, y, w, h, scale)
            if score >= threshold and scale == 1.0:
                break  # exact-scale hit, no need to search further

    score, x, y, w, h, scale = best
    score = max(0.0, score)
    return Detection(
        found=score >= threshold,
        confidence=score,
        x=x,
        y=y,
        width=w,
        height=h,
        scale=scale,
    )


class Detector:
    """Reusable matcher bound to detection settings.

    Holds per-target template arrays so the automation loop does not reload
    PNGs every frame. ``detect(target_id, frame)`` returns the best
    :class:`Detection` across that target's templates (Mode C, spec 5).
    """

    def __init__(self, *, grayscale: bool = False, multi_scale: bool = False) -> None:
        self.grayscale = grayscale
        self.multi_scale = multi_scale
        self._templates: dict[str, list[np.ndarray]] = {}

    def set_templates(self, target_id: str, templates: list[np.ndarray]) -> None:
        self._templates[target_id] = [t for t in templates if t is not None and t.size]

    def remove(self, target_id: str) -> None:
        self._templates.pop(target_id, None)

    def clear(self) -> None:
        self._templates.clear()

    def has(self, target_id: str) -> bool:
        return bool(self._templates.get(target_id))

    def detect(
        self, target_id: str, frame: np.ndarray, threshold: float
    ) -> Detection:
        best = Detection(False, 0.0, 0, 0, 0, 0)
        for tpl in self._templates.get(target_id, []):
            d = detect_template(
                frame,
                tpl,
                threshold,
                grayscale=self.grayscale,
                multi_scale=self.multi_scale,
            )
            if d.confidence > best.confidence:
                best = d
        return best

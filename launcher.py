"""Frozen-app entry point with a user-visible crash report."""

from __future__ import annotations

import os
import traceback
from pathlib import Path


def _report_fatal_error() -> None:
    details = traceback.format_exc()
    data_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "RewardVision"
    log_path = data_dir / "crash.log"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        log_path.write_text(details, encoding="utf-8")
    except OSError:
        pass

    message = (
        "RewardVision could not start.\n\n"
        f"A diagnostic report was saved to:\n{log_path}\n\n"
        f"Error: {details.splitlines()[-1] if details else 'Unknown error'}"
    )
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "RewardVision", 0x10)
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    try:
        from app import main

        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001
        _report_fatal_error()
        raise SystemExit(1)

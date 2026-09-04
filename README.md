# RewardVision

[Website](https://xrenes.github.io/rewardvision/) · [Download for Windows](https://github.com/Xrenes/rewardvision/releases/latest/download/RewardVision.msi)

One button. Press **Start** and RewardVision watches the whole screen; when
one of its bundled buttons is showing, it clicks it — `Watch` on Hazmob's
Free Wall, `CLAIM NOW!` on the reward popup, `Continue playing` on the ad.
No order, no timers: a button appears, it gets clicked. Press **Stop**, or
**F9** from anywhere, to end it.

## How it works

The button images live in [`examples/hazmob/`](examples/hazmob/) and are
bundled into the build. Each scan (~3×/sec) the app looks for every button
image on screen via OpenCV template matching; a match at ≥ 0.83 confidence
is left-clicked on the **centre of the match** (so a button that moves
between screen positions is still hit), then that button is ignored for a
few seconds so one screen transition is not clicked repeatedly.

To teach it another button — a different ad's continue button, say — drop
a tight PNG crop of just that button into `examples/hazmob/`.

## Requirements

- Windows 10 / 11, Python 3.12+
- `pip install -r requirements.txt`
- Buttons are captured at **1920×1080**. Other resolutions need re-cropped
  button images at that size.
- Keep the game window visible and unobscured while it runs — matching
  reads screen pixels.

## Run

```
python app.py
```

## Build the Windows installer

Install the WiX CLI and run the build script. It produces a self-contained,
per-user 64-bit MSI at `release/RewardVision.msi` with the button images
bundled in.

```powershell
dotnet tool install --global wix
.\build.ps1
```

## Notes

- The click is a real mouse move + left click, so your cursor is taken for
  the instant of each click.
- `core/` holds just the screen-capture (`mss`) and template-match
  (`opencv`) helpers; `app.py` is the window and the scan loop.
- The window uses the dark theme in `ui/theme.py`.

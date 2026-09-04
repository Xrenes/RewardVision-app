# RewardVision

[Website](https://xrenes.github.io/rewardvision/) · [Download for Windows](https://github.com/Xrenes/rewardvision/releases/latest/download/RewardVision.msi)

A tiny screenshot-and-click automator. One window.

1. **Choose Folder** — where the steps live.
2. **Add Step** — the window hides, a full-screen screenshot is taken, you
   click where the mouse should click. Repeat for each screen in order.
3. **Run** — for each step, RewardVision watches the screen until that
   step's screenshot appears, then moves the mouse there and left-clicks.
   By default it goes through the list once and stops.
4. **Repeat** (checkbox) — loop the list forever, waiting the given number
   of seconds between passes. Made for a game that hands out a reward on a
   fixed timer: record the "claim" screens once, set the wait, walk away.

**Stop** aborts. So does **F9**, from anywhere — even with the game focused.

Every click is a left click. That's the whole feature set.

## Step format

Each step is one PNG in the folder, named `NNN_x<X>_y<Y>.png`, optionally
with an `_opt` suffix:

```
001_x1240_y560.png       # step 1, click at screen (1240, 560)
002_x0980_y430.png       # step 2, click at (980, 430)
003_x0600_y700_opt.png   # step 3, OPTIONAL — skipped if not found in time
```

The number sets the order; X/Y is the click position in screen pixels.
`_opt` marks a step optional: if its screenshot does not appear within the
per-step timeout the pass carries on instead of aborting — use it for a
button that only shows up sometimes (an ad's "Continue"). Toggle it on a
selected step with **Toggle Optional**.

When a step is found, the click lands on the centre of the matched region
if that is within ~220 px of the recorded point, otherwise on the recorded
point — so a button that drifts a little is still hit squarely.

Delete a PNG (or use **Delete Step**) to remove a step — the rest renumber.

## Requirements

- Windows 10 / 11, Python 3.12+
- `pip install -r requirements.txt`

## Run

```
python app.py
```

## Build the Windows installer

Install the WiX CLI and run the build script. It produces a self-contained,
per-user 64-bit MSI at `release/RewardVision.msi`.

```powershell
dotnet tool install --global wix
.\build.ps1
```

The window uses the dark glassmorphic theme (`ui/theme.py`).

```
```

## Notes

- Match threshold 0.80, per-step wait 20 s. A required step not found by
  then stops the run; an `_opt` step is skipped.
- The screenshot is the whole desktop, so a step matches when that screen
  is showing. Keep screens visually distinct, and keep the game window
  un-minimised and unobscured while it runs.
- The run does a real mouse move + click, so your cursor is "taken" during
  a pass. In **Repeat** mode the wait between passes leaves it free.
- `core/` holds just the screen-capture (`mss`) and template-match
  (`opencv`) helpers; `app.py` is everything else.

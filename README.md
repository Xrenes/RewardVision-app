# RewardVision

[Website](https://xrenes.github.io/rewardvision/) · [Download for Windows](https://github.com/Xrenes/rewardvision/releases/latest/download/RewardVision-Setup.exe)

A tiny screenshot-and-click automator. One window.

1. **Choose Folder** — where the steps live.
2. **Add Step** — the window hides, a full-screen screenshot is taken, you
   click where the mouse should click. Repeat for each screen in order.
3. **Run** — for each step, RewardVision watches the screen until that
   step's screenshot appears, then moves the mouse there and left-clicks.
   It goes through the list once and stops. **Stop** aborts.

Every click is a left click. That's the whole feature set.

## Step format

Each step is one PNG in the folder, named `NNN_x<X>_y<Y>.png`:

```
001_x1240_y560.png   # step 1, click at screen (1240, 560)
002_x0980_y430.png   # step 2, click at (980, 430)
```

The number sets the order; X/Y is the click position in screen pixels.
Delete a PNG (or use **Delete Step**) to remove a step — the rest renumber.

## Requirements

- Windows 10 / 11, Python 3.12+
- `pip install -r requirements.txt`

## Run

```
python app.py
```

The window uses the dark glassmorphic theme (`ui/theme.py`).

```
```

## Notes

- Match threshold 0.80, per-step wait 20 s, then it stops with a message.
- The screenshot is the whole desktop, so a step matches when that screen
  is showing. Keep screens visually distinct.
- `core/` holds just the screen-capture (`mss`) and template-match
  (`opencv`) helpers; `app.py` is everything else.

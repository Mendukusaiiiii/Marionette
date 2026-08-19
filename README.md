# Marionette Macro Recorder & Player

A lightweight desktop tool using Tkinter GUI for recording mouse and keyboard
actions with timing and replaying them later. Think of it as a basic
macro recorder for automating repetitive clicking and typing tasks.

## Features

- **Record** mouse moves, clicks, scrolls, and keystrokes anywhere on
  screen.
- **Playback** recorded macros at adjustable speed and repeat count.
- **Save / Load** macros as JSON files so you can reuse them later.
- **Global hotkeys** to start / stop recording and playback without needing
  to click back into the app window.
- **Live cursor position readout** so you can see exactly what coordinates
  will be captured.
- Safe by default: Save / Load are greyed out while recording or playback is
  active, so you can't overwrite a macro mid-action.
- Press **Esc** at any time to immediately stop recording.

## Requirements

- Python 3.8+
- [`pynput`](https://pypi.org/project/pynput/)

Install the dependency:

```bash
pip install pynput
```

## Usage

Run the app:

```bash
python Marionette.py
```

1. Click **Start Recording** (or press the record hotkey, default `<f9>`)
   to begin capturing mouse and keyboard activity.
2. Perform the actions you want recorded.
3. Press **Esc**, or click **Stop Recording**, to finish.
4. Click **Play** (or the play hotkey, default `<f10>`) to replay the
   macro. Set **Repeat** and **Speed** first if you want it to run
   multiple times or faster/slower than recorded.
5. Use **Save Macro** / **Load Macro** to store a macro to disk as
   JSON and bring it back later.

### Hotkeys

Hotkeys use [`pynput`'s `GlobalHotKeys` format](https://pynput.readthedocs.io/en/latest/keyboard.html#global-hotkeys),
example: `<F keys>, <Combo> + <Keys>, <Number keys>`. You can change them in the **Assign
Hotkeys** panel.

## Macro file format

Macros are saved as a JSON array of timestamped events.

## Notes

- Playback controls your **real** mouse and keyboard, don't touch them
  while a macro is playing.
- On Windows, the app declares itself DPI-aware at startup so recorded
  cursor coordinates line up correctly on multi-monitor or mixed-DPI-scale
  setups.
- Mouse-move events are throttled during recording (one every ~50ms) to
  keep macro files a reasonable size; clicks, scrolls, and key presses are
  always captured in full.

## Disclaimer

This tool automates real mouse and keyboard input on your system. Use it
responsibly and only with applications where automated input is
appropriate (don't use it to violate a service's terms of use).

© Mendukusai. All rights reserved.

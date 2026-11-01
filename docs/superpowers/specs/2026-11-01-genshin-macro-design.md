# Genshin Macro – Design

Date: 2026-11-01

## Intent

A small Windows desktop app that runs beside Genshin Impact and lets the
player store a list of named macros, each bound to a global hotkey. Two
kinds of macro exist: a **key spammer** (e.g. press F repeatedly to skip
story dialogue) and a **recorded combo** (the player performs a real
attack rotation once with keyboard and mouse buttons, the app records it
and can replay it later with the same rhythm). All replayed timing is
randomised by a user-set amount to look less mechanical.

The owner wants this because repetitive actions (skipping cutscenes,
running the same combo in domains) are boring; they do not want pathing,
screen reading, or any automation beyond replaying what they did
themselves.

## Goals

- Store many macros, each with: name, kind, hotkey, kind-specific settings.
- Key spammer: one key, one interval (ms). Runs until stopped.
- Recorded combo: records key down/up, left-mouse down/up, right-mouse
  down/up with timestamps; replays them. Per-macro toggle: run once, or
  loop until stopped.
- Global hotkey per macro: press while the game has focus to start, press
  again to stop. Only one macro runs at a time; starting another stops
  the running one.
- One **global** randomisation setting (ms) that applies to every macro.
  Every inter-event delay on playback gets `+ uniform(0, R)` added, where
  `R` is that global value. Key hold durations in a recorded combo also
  receive `+ uniform(0, R/3)` (builder may tune the divisor; intent is
  "hold time varies a little, gaps vary more"). Spammer interval gets
  `+ uniform(0, R)`. Default R = 100 ms. Minimum 0.
- Persist everything to a JSON file next to the executable; load on start,
  save on every change.
- Works with Genshin Impact specifically: input must be delivered in a way
  the game accepts (see Constraints).
- Ships as a single `.exe`, no Python install needed on the target PC.

## Non-goals

- No mouse movement or cursor position recording/replay.
- No pathing, pixel detection, screen reading, or game-memory access.
- No per-macro randomisation settings (global only, owner decision).
- No cloud sync, no multi-profile per game, no scripting language.
- No Linux/macOS support.

## Anti-goals (would make it a failure even if it "works")

- Inputs replayed with identical timing every run. Randomisation is
  mandatory, not optional.
- Hotkeys that fire while the user is typing the hotkey into the app's own
  settings UI, or the recording capturing its own stop-hotkey as part of
  the combo.
- Stuck keys: if playback is stopped or the app closes mid-macro, every key
  and mouse button that was pressed by the macro must be released.
- Requiring the user to "run as admin" manually and silently failing when
  they forget.

## Constraints

- **Platform:** Windows 10/11 only.
- **Language/stack (my call):** Python 3.11+, `tkinter` for the UI (ships
  with Python, keeps the exe small), `pynput` for *listening* to global
  keyboard/mouse events (recording and hotkeys), and direct `ctypes`
  calls to Win32 `SendInput` for *sending* input. Packaged with
  PyInstaller (`--onefile --noconsole --uac-admin`).
- **Input delivery:** Genshin uses DirectInput-style raw input. Sending
  must use `SendInput` with `KEYEVENTF_SCANCODE` (hardware scan codes, not
  virtual-key codes) for keyboard, and `MOUSEEVENTF_LEFTDOWN/UP`,
  `RIGHTDOWN/UP` for mouse buttons. Extended keys (arrows, right
  ctrl/alt, Insert/Delete/Home/End/PgUp/PgDn, numpad Enter, etc.) need the
  `KEYEVENTF_EXTENDEDKEY` flag.
- **Privilege:** Genshin runs elevated, so the app must run elevated too or
  the game ignores synthetic input. The exe requests elevation via its
  manifest (`--uac-admin`). When run from source without elevation, the
  app should detect this and re-launch itself elevated (ShellExecute
  `runas`), or at least show a clear warning.
- **Not an anti-cheat bypass.** The app does nothing to hide itself,
  inject into the game, or touch game memory. The timing jitter is the
  only "anti-detection" measure, and the owner has been told macro use
  carries account risk under the game's ToS.

## Behaviour details decided in conversation

### Macro list / UI

Single window. Left: list of macros (name, hotkey, kind). Right: editor
for the selected macro. Bottom or top bar: global settings (randomisation
ms) and a status line showing "Idle" / "Recording…" / "Running: <name>".

Editor fields:
- Name (text)
- Hotkey (press-to-capture field: click it, press a key, it shows the key)
- Kind: Spammer | Recorded
- Spammer: key (press-to-capture), interval ms
- Recorded: Record / Stop button, event count and duration shown, Loop
  checkbox
- Buttons: Add macro, Delete macro, Duplicate (optional)

### Recording

- Starts on "Record" button click. The user alt-tabs into the game and
  performs the combo. Stops when the user presses the macro's own hotkey
  or clicks Stop in the app. (My call: pressing the macro's hotkey while
  recording stops the recording; that key event is **not** stored.)
- Record: key down, key up (with scan code + extended flag), mouse left
  down/up, mouse right down/up. Store `(t_ms_since_start, type, code)`.
- Ignore: mouse move, scroll, middle/X buttons, and the app's own hotkeys.
- Time is taken from a monotonic clock.

### Playback

- Runs on a background thread. Walks the event list; before each event
  sleeps `(delay_to_next_event + uniform(0, R))`. Key hold time receives
  the smaller jitter described in Goals.
- Loop mode: after the last event, a gap equal to the average inter-event
  gap of the recording plus jitter, then restart (builder may choose a
  simpler constant such as 200 ms + jitter).
- Stop: hotkey pressed again, Stop button, another macro started, or app
  closing. On stop, release every key/button this run has pressed.
- Spammer: loop of `key down, sleep(hold + jitter), key up, sleep(interval
  + jitter)`, where hold is a short constant (my call: 40 ms) plus jitter.

### Hotkeys

- Global, via pynput keyboard listener. A hotkey is a single key (no
  modifier combos needed; builder may add modifier support if cheap).
- Hotkeys are suppressed (not acted on) while the app window has keyboard
  focus and a "press-to-capture" field is active.
- The same key cannot be assigned to two macros; the UI must refuse it.

### Persistence

`macros.json` next to the exe (or next to the script when run from
source):

```json
{
  "version": 1,
  "random_ms": 100,
  "macros": [
    {"id": "...", "name": "Skip story", "hotkey": "f8", "kind": "spam",
     "key": "f", "interval_ms": 80},
    {"id": "...", "name": "Combo Raiden", "hotkey": "f9", "kind": "recorded",
     "loop": true,
     "events": [{"t": 0, "type": "key_down", "code": 18, "ext": false}, ...]}
  ]
}
```

Keys are stored as scan codes plus a human label for display.

## Left to the builder

- Exact widget layout and styling (keep it plain tkinter).
- How to map pynput key events to scan codes (pynput exposes `vk`;
  `MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)` is the obvious route).
- Whether to debounce hotkey presses.
- Test strategy: the timing/jitter logic, the event model, and the
  JSON round-trip should be unit-testable without Windows input; the
  SendInput and pynput layers can be thin and tested manually in-game.
- Project layout, build script for PyInstaller.

## Additional calls (added after builder check)

These are my calls, not owner decisions; cheap to change if wrong.

- **Ignore our own input.** Tag every `SendInput` call with a magic
  `dwExtraInfo` value and drop those events in the pynput listeners. This
  means a spammer key or a recorded combo may legitimately contain another
  macro's hotkey without triggering it; only duplicate hotkeys are refused.
- **Hotkeys inert while the app is foreground.** Not just in capture
  fields. Hotkey presses are passed through to the game, not swallowed.
  Trigger on key-down only, once per physical press (ignore auto-repeat).
- **Recording boundaries.** Ignore events while the app window is
  foreground (so the Alt+Tab into the game is not recorded); t=0 starts at
  the first kept event; drop orphan key-ups and trailing never-released
  key-downs; collapse Windows auto-repeat key-downs so a held key is one
  down + one up.
- **Jitter split.** Delay before any `*_down` event gets `uniform(0, R)`;
  delay before any `*_up` event gets `uniform(0, R/3)`. Spammer hold uses
  the `R/3` variant.
- **Safety stop.** Playback stops automatically if the foreground window
  changes from the one that was foreground when playback started, so a
  looping macro never sprays keys into another app.
- **Single instance** via a named mutex.

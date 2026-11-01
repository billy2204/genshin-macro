# Genshin Macro Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Windows tkinter app that stores hotkey-bound macros (key spammer / recorded keyboard+mouse-button combo), replays them into Genshin Impact via SendInput scan codes with global timing jitter, and persists them to `macros.json`.

**Architecture:** Pure, testable core (model, timing, recorder, hotkeys, player) with injected clock/sleep/rng/output and no Win32 imports. Thin Win32 edge (`winput.py` for SendInput and foreground/elevation, `listeners.py` for pynput hooks). `controller.py` wires core to edge and exposes a small API the tkinter `ui.py` calls; UI-thread marshalling via a `queue.Queue` drained with `after()`.

**Tech Stack:** Python 3.10+, tkinter, pynput (listening), ctypes/Win32 SendInput (sending), pytest, PyInstaller.

**Spec:** `docs/superpowers/specs/2026-11-01-genshin-macro-design.md`

## Global Constraints

- Windows 10/11 only; Python 3.10+ (machine has 3.10.0; spec's 3.11 floor relaxed).
- Keyboard output uses `SendInput` with `KEYEVENTF_SCANCODE`; extended keys add `KEYEVENTF_EXTENDEDKEY`. Mouse uses `MOUSEEVENTF_{LEFT,RIGHT}{DOWN,UP}`.
- Every `SendInput` call tags `dwExtraInfo = 0x47534D43` (magic); listeners drop events carrying it.
- Jitter: delay before any `*_down` event `+= uniform(0, R)`; delay before any `*_up` event `+= uniform(0, R/3)`. Spammer: hold `40 + uniform(0, R/3)`, gap `interval + uniform(0, R)`. Loop gap `200 + uniform(0, R)`. Default `R = 100`, min 0.
- Only one macro runs at a time; starting another stops the running one. Stop releases every key/button pressed by that run.
- Hotkeys: single key, trigger on key-down once per physical press, inert while app window is foreground, never swallowed. Duplicate hotkeys refused.
- Persistence: `macros.json` next to exe (or project root from source), saved on every change.
- No mouse movement, no pathing, no screen reading, no game memory.
- Core modules (`model`, `timing`, `recorder`, `hotkeys`, `player`) must not import `ctypes`, `pynput`, or `tkinter`.

## Review Focus

1. A recorded combo that ends with a key still held when Stop is clicked (Alt+Tab back to app) → the trailing down is dropped, no stuck key on replay. (Task 3)
2. User holds a key for 1 s while recording → Windows auto-repeat produces dozens of key-downs; stored as a single down/up pair. (Task 3)
3. Playback of a looping macro while the user Alt+Tabs to Discord → playback stops within one event and releases held keys. (Task 5)
4. `macros.json` missing, empty, or corrupt → app starts with defaults instead of crashing. (Task 1)
5. User presses a hotkey while another macro is running → running one stops, new one starts; pressing the running macro's own hotkey stops it. (Task 5/6)

---

### Task 1: Model and persistence

**Files:**
- Create: `genshin_macro/__init__.py`, `genshin_macro/model.py`, `requirements.txt`, `pytest.ini`, `.gitignore`
- Test: `tests/test_model.py`

**Interfaces:**
- `KeyRef(scan: int, ext: bool, label: str)` dataclass; `to_dict()`, `KeyRef.from_dict()`.
- `InputEvent(t: int, type: str, code: int | str, ext: bool = False)`; `type` in `{"key_down","key_up","mouse_down","mouse_up"}`; mouse `code` in `{"left","right"}`.
- `SpamMacro(id, name, hotkey: KeyRef | None = None, key: KeyRef | None = None, interval_ms: int = 80)`; class attr `kind = "spam"`.
- `RecordedMacro(id, name, hotkey: KeyRef | None = None, loop: bool = False, events: list[InputEvent] = [])`; `kind = "recorded"`.
- `Macro = SpamMacro | RecordedMacro`; `macro_from_dict(d) -> Macro` (unknown kind → `ValueError`); each macro has `to_dict()`.
- `Config(random_ms: int = 100, macros: list[Macro] = [])`; `to_dict()`, `Config.from_dict(d)` (clamps `random_ms >= 0`), `Config.load(path: Path) -> Config` (missing/invalid → `Config()`), `save(path)` atomic (temp + `os.replace`).
- `new_id() -> str` uuid4 hex.

- [ ] Step 1: Write failing tests in `tests/test_model.py`: `test_config_roundtrip`, `test_load_missing_file_returns_default`, `test_load_corrupt_file_returns_default`, `test_macro_from_dict_unknown_kind_raises`, `test_random_ms_clamped_non_negative`.
- [ ] Step 2: `pytest tests/test_model.py -v` → FAIL (ImportError).
- [ ] Step 3: Implement `model.py`. `requirements.txt`: `pynput==1.7.7`, `pyinstaller>=6`, `pytest`. `pytest.ini`: `testpaths = tests`. `.gitignore`: `__pycache__/ build/ dist/ *.spec macros.json .pytest_cache/`.
- [ ] Step 4: PASS.
- [ ] Step 5: `git init`; commit `feat: macro model and json persistence`.

### Task 2: Timing / jitter

**Files:** Create `genshin_macro/timing.py`; Test `tests/test_timing.py`

**Interfaces:**
- `jitter_for(event_type: str, random_ms: int, rng) -> float`: `rng.uniform(0, R)` for `*_down`, `rng.uniform(0, R/3)` for `*_up`.
- `schedule(events, random_ms, rng) -> list[tuple[float, InputEvent]]`: `(sleep_ms_before, event)`; base = `events[i].t - events[i-1].t` (0 for first) + `jitter_for`.
- `spam_hold_ms(random_ms, rng) = 40 + uniform(0, R/3)`; `spam_gap_ms(interval_ms, random_ms, rng) = interval + uniform(0, R)`; `loop_gap_ms(random_ms, rng) = 200 + uniform(0, R)`.

- [ ] Step 1: Tests: `test_schedule_zero_random_preserves_gaps` (t=0,100,250, R=0 → `[0,100,150]`); `test_down_jitter_within_R_and_up_within_R_over_3` (500 samples, R=90); `test_spam_and_loop_formulas` with stub rng whose `uniform(a,b)` returns `b`: `spam_hold_ms(90)==70`, `spam_gap_ms(80,90)==170`, `loop_gap_ms(90)==290`.
- [ ] Step 2–5: FAIL → implement → PASS → commit `feat: timing jitter`.

### Task 3: Recorder (pure)

**Files:** Create `genshin_macro/recorder.py`; Test `tests/test_recorder.py`

**Interfaces:**
- `Recorder(clock: Callable[[], float], is_app_foreground: Callable[[], bool])`; `start()`, `feed(type: str, code, ext: bool) -> None`, `stop() -> list[InputEvent]`, `recording: bool`, `event_count: int`. `clock` returns seconds; output `t` is int ms relative to first kept event.
- Rules: ignore feed when not recording or `is_app_foreground()`; ignore `*_down` for a `(code, ext)` already held; ignore `*_up` with no held down; on `stop()`, drop trailing downs never released.

- [ ] Step 1: Tests: `test_basic_sequence_relative_times` (down A @1.000, up A @1.250 → `[(0,key_down),(250,key_up)]`), `test_ignores_events_while_app_foreground`, `test_collapses_auto_repeat` (5 downs + up → 2 events), `test_drops_orphan_up_and_trailing_down`, `test_mouse_buttons_recorded`, `test_feed_ignored_when_not_recording`.
- [ ] Step 2–5: FAIL → implement → PASS → commit `feat: recorder`.

### Task 4: Hotkey manager (pure)

**Files:** Create `genshin_macro/hotkeys.py`; Test `tests/test_hotkeys.py`

**Interfaces:**
- `HotkeyManager(is_app_foreground)`; `bind(scan, ext, cb)`, `unbind(scan, ext)`, `clear()`, `on_key(scan, ext, down) -> None`, `is_bound(scan, ext) -> bool`.
- Fire `cb` on down only if not already held; track held; clear on up; inert (track but no fire) when `is_app_foreground()`.

- [ ] Step 1: Tests: `test_fires_once_per_physical_press`, `test_inert_when_app_foreground`, `test_unbound_key_ignored`, `test_rebind_replaces_callback`.
- [ ] Step 2–5: FAIL → implement → PASS → commit `feat: hotkey manager`.

### Task 5: Player

**Files:** Create `genshin_macro/player.py`; Test `tests/test_player.py`

**Interfaces:**
- `class Output(Protocol)`: `key_down(scan, ext)`, `key_up(scan, ext)`, `mouse_down(button)`, `mouse_up(button)`.
- `run_macro(macro, output, stop: threading.Event, random_ms: int, rng, sleep: Callable[[float], None], still_foreground: Callable[[], bool]) -> None`: synchronous; `sleep` takes ms; checks `stop.is_set()` / `still_foreground()` before every sleep and event; on exit releases everything pressed this run in reverse order.
- `Player(output, get_random_ms, foreground_hwnd, on_state, sleep=<real ms sleep>, rng=None)`: `start(macro)` (stops current, captures hwnd0, `still_foreground = foreground_hwnd() == hwnd0`), `stop()` (set event, join ≤1 s), `running_id`, `toggle(macro)`. Calls `on_state(id)` on start and `on_state(None)` when the thread finishes.
- Spam: `key_down, sleep(spam_hold), key_up, sleep(spam_gap)` loop. Recorded: walk `schedule`; loop → `sleep(loop_gap)` then repeat.

- [ ] Step 1: Tests with `FakeOutput` and list-recording fake `sleep`: `test_recorded_once_emits_all_events_in_order`, `test_stop_releases_held_keys`, `test_foreground_change_stops_and_releases`, `test_spam_emits_down_up_pairs_until_stop`, `test_loop_repeats`, `test_player_toggle_same_id_stops`.
- [ ] Step 2–5: FAIL → implement → PASS → commit `feat: player`.

### Task 6: Controller

**Files:** Create `genshin_macro/controller.py`; Test `tests/test_controller.py`

**Interfaces:**
- `Controller(config, save: Callable[[Config], None], recorder, hotkeys, player, events: queue.Queue, label_for=lambda s,e: f"SC{s}")`.
- `macros`, `get(id)`, `add_spam() -> SpamMacro`, `add_recorded() -> RecordedMacro` (name `"Macro N"`), `delete(id)`, `update(id, **fields)` (duplicate hotkey → `ValueError`; `interval_ms >= 1`), `set_random_ms(int)`, `random_ms`.
- `start_recording(id)`, `stop_recording()` (stores events, saves), `recording_id`.
- `on_key(scan, ext, down)`, `on_mouse(button, down)` from listener thread: if capture pending and key down → `capture_cb(KeyRef)`, clear, return; if recording → `recorder.feed`; keys always → `hotkeys.on_key`.
- `begin_capture(cb)`, `cancel_capture()`.
- Hotkey for macro X: `recording_id == X` → `stop_recording()`; else `player.toggle(X)`.
- `rebind_all()` after add/delete/update. Pushes `("state", id|None)` and `("recording", id|None)` to `events`.

- [ ] Step 1: Tests with real Recorder/HotkeyManager and a `FakePlayer`: `test_duplicate_hotkey_rejected`, `test_hotkey_toggles_player`, `test_hotkey_during_recording_stops_recording_not_player`, `test_capture_takes_next_key_and_skips_hotkey`, `test_save_called_on_update`.
- [ ] Step 2–5: FAIL → implement → PASS → commit `feat: controller`.

### Task 7: Win32 output + listeners (edge)

**Files:** Create `genshin_macro/winput.py`, `genshin_macro/listeners.py`, `tools/smoke_send.py`; Test `tests/test_winput_pure.py`

**Interfaces:**
- `winput.MAGIC = 0x47534D43`; `Win32Output` (SendInput with `KEYEVENTF_SCANCODE=0x0008`, `KEYEVENTF_EXTENDEDKEY=0x0001`, `KEYEVENTF_KEYUP=0x0002`; mouse `0x0002/0x0004/0x0008/0x0010`); `foreground_hwnd() -> int`; `label_for(scan, ext) -> str` via `GetKeyNameTextW((scan << 16) | (ext << 24))`, fallback `f"SC{scan}"`; `is_admin()`; `relaunch_as_admin()` (ShellExecuteW runas, then exit); `acquire_single_instance(name) -> bool` (CreateMutexW, ERROR_ALREADY_EXISTS=183).
- `listeners.start_listeners(controller) -> (keyboard.Listener, mouse.Listener)`: keyboard `win32_event_filter(msg, data)`: skip `data.dwExtraInfo == MAGIC`; down if `msg in (0x100, 0x104)`, up if `msg in (0x101, 0x105)`; `ext = bool(data.flags & 1)`; `controller.on_key(data.scanCode, ext, down)`. Mouse: `0x201/0x202` left, `0x204/0x205` right; `controller.on_mouse(button, down)`. Never suppress.

- [ ] Step 1: Test `label_for(0x3E, False)` non-empty; `Win32Output` has the four methods (skip off Windows).
- [ ] Step 2: Implement. Step 3: `tools/smoke_send.py` sends F into Notepad after 3 s. Step 4: commit `feat: win32 output and pynput listeners`.

### Task 8: tkinter UI + app entry + build

**Files:** Create `genshin_macro/ui.py`, `genshin_macro/app.py`, `main.py`, `build.bat`, `README.md`

- `ui.App(tk.Tk)`: left Listbox `"<name>  [<hotkey>]  (<kind>)"`; right editor (Name Entry; Hotkey capture Button, "Nhấn phím…" while capturing; Kind radios; Spam: key capture + interval Spinbox 1–5000; Recorded: Ghi/Dừng button, `"<n> sự kiện, <d> ms"`, Checkbutton "Lặp lại"); toolbar `Thêm Spam`, `Thêm Ghi`, `Xóa`; bottom: `Random ms` Spinbox 0–2000, status `Sẵn sàng` / `Đang ghi: <name>` / `Đang chạy: <name>`. Drain queue every 50 ms. App hwnd via `GetAncestor(root.winfo_id(), 2)`.
- `app.main()`: `is_admin()` else relaunch; single instance else messagebox + exit; config path next to exe (frozen) or project root; wire everything; on close stop player, stop listeners, save.
- `build.bat`: `pyinstaller --onefile --noconsole --uac-admin --name GenshinMacro main.py`.

- [ ] Step 1: Implement. Step 2: Run `python main.py`, verify in Notepad: spam F8→f, recorded replay, Alt+Tab stops. Step 3: build exe. Step 4: README (Vietnamese). Step 5: commit `feat: tkinter ui, app entry, build script`.

"""tkinter UI. All controller calls happen on the Tk thread; listener-thread
events reach the UI through the queue drained in `_poll`."""
from __future__ import annotations

import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from . import updater
from .controller import MOUSE_LABELS, Controller
from .model import KeyRef, RecordedMacro, SpamMacro

POLL_MS = 50
COLOR_IDLE, COLOR_REC, COLOR_RUN = "#2a7", "#c33", "#27c"
KIND_KEY = "Phím"
ACTION_DOWN, ACTION_UP = "Nhấn", "Nhả"
FILETYPES = [("Macro JSON", "*.json"), ("Tất cả", "*.*")]


def _download_name(url: str) -> str:
    """Local file name for a downloaded update: keep 'Setup' in the name so the
    installer path is chosen, otherwise a plain exe name."""
    base = url.rsplit("/", 1)[-1].split("?")[0]
    return base if base.lower().endswith(".exe") else "GenshinMacro_new.exe"


class Overlay(tk.Toplevel):
    """Small always-on-top, borderless status window shown over the game. Draggable."""

    def __init__(self, master: tk.Tk, on_created: Optional[Callable[[int], None]] = None):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.85)
        except tk.TclError:
            pass
        self.configure(bg="#111")
        self.label = tk.Label(self, text="", fg="#ddd", bg="#111", font=("Segoe UI", 11, "bold"), padx=10, pady=4)
        self.label.pack()
        self.geometry("+20+20")
        self._drag = (0, 0)
        for w in (self, self.label):
            w.bind("<ButtonPress-1>", self._start_drag)
            w.bind("<B1-Motion>", self._do_drag)
        self.update_idletasks()
        if on_created is not None:
            try:
                on_created(int(self.winfo_id()))
            except Exception:
                pass

    def _start_drag(self, ev) -> None:
        self._drag = (ev.x_root - self.winfo_x(), ev.y_root - self.winfo_y())

    def _do_drag(self, ev) -> None:
        self.geometry(f"+{ev.x_root - self._drag[0]}+{ev.y_root - self._drag[1]}")

    def set_status(self, text: str, color: str) -> None:
        self.label.config(text=text, fg=color)


class App(tk.Tk):
    def __init__(
        self,
        controller: Controller,
        events: queue.Queue,
        on_overlay_created: Optional[Callable[[int], None]] = None,
        update_url: str = "",
        on_update_url_change: Callable[[str], None] = lambda u: None,
    ):
        super().__init__()
        self.ctl = controller
        self.events = events
        self._on_overlay_created = on_overlay_created
        self.update_url = update_url
        self._on_update_url_change = on_update_url_change
        self.title(f"Genshin Macro v{updater.APP_VERSION}")
        self.minsize(860, 600)
        self._selected: Optional[str] = None
        self._capturing: Optional[ttk.Button] = None
        self._ids: list[str] = []
        self._ev_key: Optional[KeyRef] = None  # key chosen in the event editor
        self.overlay: Optional[Overlay] = None
        self._build()
        self._refresh_list()
        if self.ctl.overlay:
            self._show_overlay()
        self._update_status()
        self.after(POLL_MS, self._poll)

    # ---- layout ------------------------------------------------------------
    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        bar = ttk.Frame(self, padding=(8, 8, 8, 0))
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(bar, text="Thêm Spam", command=self._add_spam).pack(side="left")
        ttk.Button(bar, text="Thêm Ghi", command=self._add_recorded).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Xóa", command=self._delete).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text="Nhập Razer…", command=self._import_razer_dialog).pack(side="left", padx=(6, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(bar, text="Mở file…", command=self._open_dialog).pack(side="left")
        ttk.Button(bar, text="Lưu thành…", command=self._save_as_dialog).pack(side="left", padx=(6, 0))
        self.path_lbl = ttk.Label(bar, text="", foreground="#666")
        self.path_lbl.pack(side="left", padx=(10, 0))
        self._refresh_path_label()
        upd = ttk.Button(bar, text="Cập nhật", command=self._update_now)
        upd.pack(side="right")
        upd.bind("<Button-3>", lambda ev: self._update_dialog())  # right-click: advanced (URL / local exe)

        left = ttk.Frame(self, padding=8)
        left.grid(row=1, column=0, sticky="nsw")
        self.listbox = tk.Listbox(left, width=34, exportselection=False, activestyle="none")
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        self.editor = ttk.Frame(self, padding=8)
        self.editor.grid(row=1, column=1, sticky="nsew")
        self.editor.columnconfigure(1, weight=1)
        self._build_editor()

        bottom = ttk.Frame(self, padding=8)
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Label(bottom, text="Random ms:").pack(side="left")
        self.random_var = tk.IntVar(value=self.ctl.random_ms)
        sp = ttk.Spinbox(bottom, from_=0, to=2000, width=6, textvariable=self.random_var, command=self._random_changed)
        sp.pack(side="left", padx=(4, 12))
        sp.bind("<FocusOut>", lambda e: self._random_changed())
        sp.bind("<Return>", lambda e: self._random_changed())

        ttk.Label(bottom, text="Phím Ghi:").pack(side="left")
        rh = self.ctl.record_hotkey
        self.record_btn = ttk.Button(bottom, text=rh.label if rh else "(chưa có)", command=lambda: self._capture("record"))
        self.record_btn.pack(side="left", padx=(4, 12))
        self.record_btn.bind("<Button-3>", lambda ev: self._set_record_hotkey(None))

        self.overlay_var = tk.BooleanVar(value=self.ctl.overlay)
        ttk.Checkbutton(bottom, text="Overlay", variable=self.overlay_var, command=self._overlay_changed).pack(side="left", padx=(0, 12))

        self.status = ttk.Label(bottom, text="Sẵn sàng", foreground=COLOR_IDLE)
        self.status.pack(side="left")

    def _build_editor(self) -> None:
        e = self.editor
        r = 0
        ttk.Label(e, text="Tên:").grid(row=r, column=0, sticky="w", pady=2)
        self.name_var = tk.StringVar()
        name = ttk.Entry(e, textvariable=self.name_var)
        name.grid(row=r, column=1, sticky="ew", pady=2)
        name.bind("<FocusOut>", lambda ev: self._commit_name())
        name.bind("<Return>", lambda ev: self._commit_name())
        r += 1
        ttk.Label(e, text="Phím tắt:").grid(row=r, column=0, sticky="w", pady=2)
        self.hotkey_btn = ttk.Button(e, text="(chưa có)", command=lambda: self._capture("hotkey"))
        self.hotkey_btn.grid(row=r, column=1, sticky="w", pady=2)
        self.hotkey_btn.bind("<Button-3>", lambda ev: self._set_field("hotkey", None))
        r += 1
        ttk.Label(e, text="Kiểu:").grid(row=r, column=0, sticky="w", pady=2)
        self.kind_lbl = ttk.Label(e, text="")
        self.kind_lbl.grid(row=r, column=1, sticky="w", pady=2)
        r += 1
        ttk.Separator(e).grid(row=r, column=0, columnspan=2, sticky="ew", pady=8)
        r += 1

        # ---- spam section ----
        self.spam_frame = ttk.Frame(e)
        self.spam_frame.grid(row=r, column=0, columnspan=2, sticky="ew")
        self.spam_frame.columnconfigure(1, weight=1)
        ttk.Label(self.spam_frame, text="Phím spam:").grid(row=0, column=0, sticky="w", pady=2)
        self.key_btn = ttk.Button(self.spam_frame, text="(chưa có)", command=lambda: self._capture("key"))
        self.key_btn.grid(row=0, column=1, sticky="w", pady=2)
        ttk.Label(self.spam_frame, text="Khoảng cách (ms):").grid(row=1, column=0, sticky="w", pady=2)
        self.interval_var = tk.IntVar(value=80)
        iv = ttk.Spinbox(self.spam_frame, from_=1, to=5000, width=7, textvariable=self.interval_var, command=self._commit_interval)
        iv.grid(row=1, column=1, sticky="w", pady=2)
        iv.bind("<FocusOut>", lambda ev: self._commit_interval())
        iv.bind("<Return>", lambda ev: self._commit_interval())

        # ---- recorded section ----
        self.rec_frame = ttk.Frame(e)
        self.rec_frame.grid(row=r, column=0, columnspan=2, sticky="nsew")
        e.rowconfigure(r, weight=1)
        rf = self.rec_frame
        rf.columnconfigure(0, weight=1)
        rf.rowconfigure(3, weight=1)

        top = ttk.Frame(rf)
        top.grid(row=0, column=0, sticky="ew")
        self.rec_btn = ttk.Button(top, text="● Ghi", command=self._toggle_record)
        self.rec_btn.pack(side="left")
        self.rec_info = ttk.Label(top, text="0 sự kiện, 0 ms")
        self.rec_info.pack(side="left", padx=8)
        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Lặp lại đến khi dừng", variable=self.loop_var, command=self._commit_loop).pack(side="left", padx=8)

        ign = ttk.LabelFrame(rf, text="Phím bỏ qua (không ghi)", padding=4)
        ign.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.ignore_list = tk.Listbox(ign, height=3, width=22, exportselection=False, activestyle="none")
        self.ignore_list.pack(side="left")
        ign_btns = ttk.Frame(ign)
        ign_btns.pack(side="left", padx=8, anchor="n")
        self.ignore_add_btn = ttk.Button(ign_btns, text="+ Thêm phím", command=lambda: self._capture("ignore"))
        self.ignore_add_btn.pack(fill="x")
        ttk.Button(ign_btns, text="− Bỏ phím đã chọn", command=self._remove_ignore).pack(fill="x", pady=(4, 0))
        ttk.Label(ign, text="Mặc định W A S D.\nPhím trong danh sách này\nkhông bao giờ bị ghi.", foreground="#666", justify="left").pack(side="left", padx=8)

        hdr = ttk.Frame(rf)
        hdr.grid(row=2, column=0, sticky="ew", pady=(8, 2))
        ttk.Label(hdr, text="Thao tác đã ghi (chọn một dòng để sửa). Chờ = thời gian từ thao tác trước.").pack(side="left")
        self.total_lbl = ttk.Label(hdr, text="Tổng: 0 ms", font=("Segoe UI", 9, "bold"))
        self.total_lbl.pack(side="right")
        tree_box = ttk.Frame(rf)
        tree_box.grid(row=3, column=0, sticky="nsew")
        tree_box.columnconfigure(0, weight=1)
        tree_box.rowconfigure(0, weight=1)
        self.event_tree = ttk.Treeview(tree_box, columns=("t", "action", "key"), show="headings", height=8, selectmode="browse")
        self.event_tree.heading("t", text="Chờ (ms)")
        self.event_tree.heading("action", text="Hành động")
        self.event_tree.heading("key", text="Phím / Chuột")
        self.event_tree.column("t", width=110, anchor="e")
        self.event_tree.column("action", width=90, anchor="center")
        self.event_tree.column("key", width=160, anchor="w")
        self.event_tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(tree_box, orient="vertical", command=self.event_tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.event_tree.configure(yscrollcommand=sb.set)
        self.event_tree.bind("<<TreeviewSelect>>", self._on_event_select)

        edit = ttk.Frame(rf)
        edit.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(edit, text="Chờ (ms):").pack(side="left")
        self.ev_t_var = tk.IntVar(value=0)
        ttk.Spinbox(edit, from_=0, to=3_600_000, width=8, textvariable=self.ev_t_var).pack(side="left", padx=(2, 8))
        self.ev_action_var = tk.StringVar(value=ACTION_DOWN)
        ttk.Combobox(edit, textvariable=self.ev_action_var, values=[ACTION_DOWN, ACTION_UP], width=6, state="readonly").pack(side="left", padx=(0, 8))
        self.ev_kind_var = tk.StringVar(value=KIND_KEY)
        kind_cb = ttk.Combobox(edit, textvariable=self.ev_kind_var, values=[KIND_KEY, MOUSE_LABELS["left"], MOUSE_LABELS["right"]], width=10, state="readonly")
        kind_cb.pack(side="left", padx=(0, 4))
        kind_cb.bind("<<ComboboxSelected>>", lambda ev: self._sync_ev_key_btn())
        self.ev_key_btn = ttk.Button(edit, text="(phím)", command=lambda: self._capture("evkey"))
        self.ev_key_btn.pack(side="left", padx=(0, 8))
        ttk.Button(edit, text="Áp dụng", command=self._apply_event).pack(side="left")
        ttk.Button(edit, text="Xóa event", command=self._delete_event).pack(side="left", padx=(6, 0))
        r += 1
        ttk.Label(
            e,
            text=(
                "Bấm phím tắt khi đang trong game để chạy / dừng macro. "
                "Ghi: chọn macro kiểu Ghi, bấm phím Ghi để bắt đầu, bấm lại để dừng."
            ),
            foreground="#666",
            justify="left",
            wraplength=560,
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self._show_kind(None)

    # ---- list ----------------------------------------------------------------
    def _refresh_list(self) -> None:
        self.listbox.delete(0, "end")
        ids = []
        for m in self.ctl.macros:
            hk = m.hotkey.label if m.hotkey else "—"
            kind = "Spam" if isinstance(m, SpamMacro) else "Ghi"
            self.listbox.insert("end", f"{m.name}   [{hk}]   ({kind})")
            ids.append(m.id)
        self._ids = ids
        if self._selected in ids:
            self.listbox.selection_set(ids.index(self._selected))
        else:
            self._selected = ids[0] if ids else None
            if ids:
                self.listbox.selection_set(0)
        self.ctl.selected_id = self._selected
        self._load_editor()

    def _on_select(self, _ev=None) -> None:
        sel = self.listbox.curselection()
        self._selected = self._ids[sel[0]] if sel else None
        self.ctl.selected_id = self._selected
        self._load_editor()

    def _current(self):
        try:
            return self.ctl.get(self._selected) if self._selected else None
        except KeyError:
            return None

    def _load_editor(self) -> None:
        m = self._current()
        if m is None:
            self.name_var.set("")
            self.hotkey_btn.config(text="(chưa có)")
            self._show_kind(None)
            return
        self.name_var.set(m.name)
        self.hotkey_btn.config(text=m.hotkey.label if m.hotkey else "(chưa có)")
        if isinstance(m, SpamMacro):
            self.kind_lbl.config(text="Spam phím")
            self.key_btn.config(text=m.key.label if m.key else "(chưa có)")
            self.interval_var.set(m.interval_ms)
            self._show_kind("spam")
        else:
            self.kind_lbl.config(text="Ghi thao tác")
            self.loop_var.set(m.loop)
            self.rec_info.config(text=f"{len(m.events)} sự kiện, {m.duration_ms} ms")
            self.rec_btn.config(text="■ Dừng ghi" if self.ctl.recording_id == m.id else "● Ghi")
            self._fill_ignore(m)
            self._fill_events(m)
            self._show_kind("recorded")

    def _fill_ignore(self, m: RecordedMacro) -> None:
        self.ignore_list.delete(0, "end")
        for k in m.ignore_keys:
            self.ignore_list.insert("end", k.label)

    def _fill_events(self, m: RecordedMacro, keep_index: Optional[int] = None) -> None:
        self.event_tree.delete(*self.event_tree.get_children())
        delays = self.ctl.event_delays(m.id)
        for i, ev in enumerate(m.events):
            _, action, label = self.ctl.describe_event(ev)
            self.event_tree.insert("", "end", iid=str(i), values=(str(delays[i]), action, label))
        self.total_lbl.config(text=f"Tổng: {m.duration_ms} ms")
        self.rec_info.config(text=f"{len(m.events)} sự kiện, {m.duration_ms} ms")
        if keep_index is not None and 0 <= keep_index < len(m.events):
            self.event_tree.selection_set(str(keep_index))
            self.event_tree.see(str(keep_index))

    def _show_kind(self, kind: Optional[str]) -> None:
        self.spam_frame.grid_remove()
        self.rec_frame.grid_remove()
        if kind == "spam":
            self.spam_frame.grid()
        elif kind == "recorded":
            self.rec_frame.grid()
        self.hotkey_btn.config(state="normal" if kind else "disabled")

    # ---- macro actions -------------------------------------------------------
    def _add_spam(self) -> None:
        self._selected = self.ctl.add_spam().id
        self._refresh_list()

    def _add_recorded(self) -> None:
        self._selected = self.ctl.add_recorded().id
        self._refresh_list()

    def _delete(self) -> None:
        m = self._current()
        if m and messagebox.askyesno("Xóa macro", f"Xóa '{m.name}'?"):
            self.ctl.delete(m.id)
            self._selected = None
            self._refresh_list()

    def _set_field(self, field: str, value) -> None:
        if not self._selected:
            return
        try:
            self.ctl.update(self._selected, **{field: value})
        except ValueError as ex:
            messagebox.showerror("Lỗi", str(ex))
        self._refresh_list()

    def _set_record_hotkey(self, ref: Optional[KeyRef]) -> None:
        try:
            self.ctl.set_record_hotkey(ref)
        except ValueError as ex:
            messagebox.showerror("Lỗi", str(ex))
        rh = self.ctl.record_hotkey
        self.record_btn.config(text=rh.label if rh else "(chưa có)")

    def _commit_name(self) -> None:
        m = self._current()
        if m and self.name_var.get().strip() and m.name != self.name_var.get().strip():
            self._set_field("name", self.name_var.get().strip())

    def _commit_interval(self) -> None:
        m = self._current()
        if isinstance(m, SpamMacro):
            try:
                v = int(self.interval_var.get())
            except (tk.TclError, ValueError):
                return
            if v != m.interval_ms:
                self._set_field("interval_ms", v)

    def _commit_loop(self) -> None:
        m = self._current()
        if isinstance(m, RecordedMacro):
            self._set_field("loop", bool(self.loop_var.get()))

    def _random_changed(self) -> None:
        try:
            v = int(self.random_var.get())
        except (tk.TclError, ValueError):
            return
        if v != self.ctl.random_ms:
            self.ctl.set_random_ms(v)

    # ---- ignore keys -----------------------------------------------------------
    def _remove_ignore(self) -> None:
        m = self._current()
        sel = self.ignore_list.curselection()
        if isinstance(m, RecordedMacro) and sel:
            self.ctl.remove_ignore_key(m.id, sel[0])
            self._fill_ignore(self.ctl.get(m.id))

    # ---- event editing ---------------------------------------------------------
    def _selected_event_index(self) -> Optional[int]:
        sel = self.event_tree.selection()
        return int(sel[0]) if sel else None

    def _on_event_select(self, _ev=None) -> None:
        m = self._current()
        i = self._selected_event_index()
        if not isinstance(m, RecordedMacro) or i is None or i >= len(m.events):
            return
        ev = m.events[i]
        self.ev_t_var.set(self.ctl.event_delays(m.id)[i])
        self.ev_action_var.set(ACTION_DOWN if ev.type.endswith("_down") else ACTION_UP)
        if ev.type.startswith("mouse"):
            self.ev_kind_var.set(MOUSE_LABELS.get(str(ev.code), MOUSE_LABELS["left"]))
            self._ev_key = None
        else:
            self.ev_kind_var.set(KIND_KEY)
            self._ev_key = KeyRef(int(ev.code), bool(ev.ext), self.ctl.describe_event(ev)[2])
        self._sync_ev_key_btn()

    def _sync_ev_key_btn(self) -> None:
        if self.ev_kind_var.get() == KIND_KEY:
            self.ev_key_btn.config(state="normal", text=self._ev_key.label if self._ev_key else "(phím)")
        else:
            self.ev_key_btn.config(state="disabled", text="—")

    def _apply_event(self) -> None:
        m = self._current()
        i = self._selected_event_index()
        if not isinstance(m, RecordedMacro) or i is None:
            return
        try:
            delay = int(self.ev_t_var.get())
        except (tk.TclError, ValueError):
            messagebox.showerror("Lỗi", "Thời gian chờ phải là số ms")
            return
        down = self.ev_action_var.get() == ACTION_DOWN
        kind = self.ev_kind_var.get()
        try:
            if kind == KIND_KEY:
                if self._ev_key is None:
                    messagebox.showerror("Lỗi", "Chưa chọn phím")
                    return
                self.ctl.update_event(m.id, i, type="key_down" if down else "key_up", code=self._ev_key.scan, ext=self._ev_key.ext)
            else:
                button = "left" if kind == MOUSE_LABELS["left"] else "right"
                self.ctl.update_event(m.id, i, type="mouse_down" if down else "mouse_up", code=button)
            self.ctl.set_event_delay(m.id, i, delay)
        except (ValueError, IndexError) as ex:
            messagebox.showerror("Lỗi", str(ex))
            return
        self._fill_events(self.ctl.get(m.id), keep_index=i)

    def _delete_event(self) -> None:
        m = self._current()
        i = self._selected_event_index()
        if not isinstance(m, RecordedMacro) or i is None:
            return
        self.ctl.delete_event(m.id, i)
        self._fill_events(self.ctl.get(m.id), keep_index=min(i, len(self.ctl.get(m.id).events) - 1))

    # ---- razer import ----------------------------------------------------------------
    def _import_razer_dialog(self) -> None:
        p = filedialog.askopenfilename(title="Chọn file macro Razer (.xml)", filetypes=[("Razer macro XML", "*.xml"), ("Tất cả", "*.*")])
        if p:
            self._import_razer_path(Path(p))

    def _import_razer_path(self, path: Path) -> None:
        try:
            m = self.ctl.import_razer(path)
        except (OSError, ValueError) as ex:
            messagebox.showerror("Nhập Razer", f"Không nhập được: {ex}")
            return
        self._selected = m.id
        self._refresh_list()

    # ---- file path ---------------------------------------------------------------
    def _refresh_path_label(self) -> None:
        self.path_lbl.config(text=f"File: {self.ctl.path}" if self.ctl.path else "")

    def _save_as_dialog(self) -> None:
        initial = self.ctl.path
        p = filedialog.asksaveasfilename(
            title="Lưu file macro",
            defaultextension=".json",
            filetypes=FILETYPES,
            initialdir=str(initial.parent) if initial else None,
            initialfile=initial.name if initial else "macros.json",
        )
        if p:
            self._save_as_path(Path(p))

    def _save_as_path(self, path: Path) -> None:
        try:
            self.ctl.save_as(path)
        except OSError as ex:
            messagebox.showerror("Lỗi", f"Không lưu được: {ex}")
        self._refresh_path_label()

    def _open_dialog(self) -> None:
        initial = self.ctl.path
        p = filedialog.askopenfilename(
            title="Mở file macro",
            filetypes=FILETYPES,
            initialdir=str(initial.parent) if initial else None,
        )
        if p:
            self._open_path(Path(p))

    def _open_path(self, path: Path) -> None:
        try:
            self.ctl.load_from(path)
        except ValueError as ex:
            messagebox.showerror("Lỗi", str(ex))
            return
        self._reload_all()

    def _reload_all(self) -> None:
        self._selected = None
        self.random_var.set(self.ctl.random_ms)
        rh = self.ctl.record_hotkey
        self.record_btn.config(text=rh.label if rh else "(chưa có)")
        self.overlay_var.set(self.ctl.overlay)
        self._refresh_path_label()
        self._refresh_list()
        self._update_status()

    # ---- update ---------------------------------------------------------------------
    def _update_now(self) -> None:
        """One click: check manifest, download, swap exe, relaunch. No questions asked."""
        if not self.update_url:
            self._update_dialog()
            return
        self._set_status_text("Đang kiểm tra cập nhật…")
        try:
            found = updater.check_for_update(self.update_url)
        except Exception as ex:
            self._update_status()
            messagebox.showerror("Cập nhật", f"Không kiểm tra được bản mới: {ex}")
            self._update_dialog()
            return
        if found is None:
            self._update_status()
            messagebox.showinfo("Cập nhật", f"Bạn đang dùng bản mới nhất (v{updater.APP_VERSION}).")
            return
        version, dl = found
        self._set_status_text(f"Đang tải bản v{version}…")
        import tempfile

        dest = Path(tempfile.gettempdir()) / _download_name(dl)
        try:
            updater.download(dl, dest)
        except Exception as ex:
            self._update_status()
            messagebox.showerror("Cập nhật", f"Tải thất bại: {ex}")
            return
        self._set_status_text("Đang cài bản mới, app sẽ tự mở lại…")
        self._install_exe(dest, confirm=False)

    def _set_status_text(self, text: str) -> None:
        self.status.config(text=text, foreground=COLOR_RUN)
        self.status.update_idletasks()

    def _update_dialog(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Cập nhật app")
        dlg.transient(self)
        dlg.resizable(False, False)
        frm = ttk.Frame(dlg, padding=12)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"Phiên bản hiện tại: v{updater.APP_VERSION}").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frm, text="Nguồn cập nhật (manifest.json):").grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 2))
        url_var = tk.StringVar(value=self.update_url)
        ttk.Entry(frm, textvariable=url_var, width=64).grid(row=2, column=0, columnspan=2, sticky="ew")
        status = ttk.Label(frm, text="", foreground="#666", wraplength=420, justify="left")
        status.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        def check() -> None:
            url = url_var.get().strip()
            if url != self.update_url:
                self.update_url = url
                self._on_update_url_change(url)
            if not url:
                status.config(text="Chưa có nguồn cập nhật.")
                return
            status.config(text="Đang kiểm tra…")
            dlg.update_idletasks()
            try:
                found = updater.check_for_update(url)
            except Exception as ex:
                status.config(text=f"Không kiểm tra được: {ex}")
                return
            if found is None:
                status.config(text="Bạn đang dùng bản mới nhất.")
                return
            version, dl = found
            status.config(text=f"Có bản v{version}, đang tải…")
            dlg.update_idletasks()
            self._install_from_url(dl, status)

        def pick_file() -> None:
            p = filedialog.askopenfilename(title="Chọn file GenshinMacroSetup.exe hoặc GenshinMacro.exe mới", filetypes=[("Exe", "*.exe")], parent=dlg)
            if p:
                self._install_exe(Path(p))

        ttk.Button(frm, text="Kiểm tra online", command=check).grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Button(frm, text="Chọn file .exe…", command=pick_file).grid(row=3, column=1, sticky="w", pady=(8, 0), padx=(8, 0))

    def _install_from_url(self, url: str, status: ttk.Label) -> None:
        import tempfile

        status.config(text="Đang tải…")
        status.update_idletasks()
        dest = Path(tempfile.gettempdir()) / _download_name(url)
        try:
            updater.download(url, dest)
        except Exception as ex:
            status.config(text=f"Tải thất bại: {ex}")
            return
        self._install_exe(dest, confirm=False)

    def _install_exe(self, new_exe: Path, confirm: bool = True) -> None:
        if updater.current_exe() is None:
            messagebox.showinfo("Cập nhật", "Đang chạy từ mã nguồn, không tự thay được. Hãy chạy từ file .exe.")
            return
        if confirm and not messagebox.askyesno("Cập nhật", "App sẽ tắt, cài bản mới và mở lại. Tiếp tục?"):
            return
        self.ctl.stop_all()
        updater.install_downloaded(new_exe)

    # ---- overlay -------------------------------------------------------------------
    def _overlay_changed(self) -> None:
        on = bool(self.overlay_var.get())
        self.ctl.set_overlay(on)
        if on:
            self._show_overlay()
        else:
            self._hide_overlay()

    def _show_overlay(self) -> None:
        if self.overlay is None:
            self.overlay = Overlay(self, self._on_overlay_created)
            self._update_status()

    def _hide_overlay(self) -> None:
        if self.overlay is not None:
            self.overlay.destroy()
            self.overlay = None

    # ---- key capture -----------------------------------------------------------------
    def _capture_button(self, field: str) -> ttk.Button:
        return {
            "hotkey": self.hotkey_btn,
            "key": self.key_btn,
            "record": self.record_btn,
            "ignore": self.ignore_add_btn,
            "evkey": self.ev_key_btn,
        }[field]

    def _capture(self, field: str) -> None:
        btn = self._capture_button(field)
        if field != "record" and not self._selected:
            return
        if self._capturing is not None:
            self.ctl.cancel_capture()
            self._capturing = None
            self._restore_capture_buttons()
            return
        self._capturing = btn
        btn.config(text="Nhấn phím…")
        self.ctl.begin_capture(lambda ref: self.events.put(("captured", field, ref)))

    def _restore_capture_buttons(self) -> None:
        self._load_editor()
        rh = self.ctl.record_hotkey
        self.record_btn.config(text=rh.label if rh else "(chưa có)")
        self.ignore_add_btn.config(text="+ Thêm phím")
        self._sync_ev_key_btn()

    def _toggle_record(self) -> None:
        m = self._current()
        if not isinstance(m, RecordedMacro):
            return
        if self.ctl.recording_id == m.id:
            self.ctl.stop_recording()
        else:
            self.ctl.start_recording(m.id)
        self._load_editor()
        self._update_status()

    # ---- queue from listener thread ------------------------------------------
    def _poll(self) -> None:
        try:
            while True:
                self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll)

    def _handle(self, item) -> None:
        kind = item[0]
        if kind == "captured":
            _, field, ref = item
            self._capturing = None
            if field == "record":
                self._set_record_hotkey(ref)
            elif field == "ignore":
                m = self._current()
                if isinstance(m, RecordedMacro):
                    self.ctl.add_ignore_key(m.id, ref)
                    self._fill_ignore(self.ctl.get(m.id))
                self.ignore_add_btn.config(text="+ Thêm phím")
            elif field == "evkey":
                self._ev_key = ref
                self.ev_kind_var.set(KIND_KEY)
                self._sync_ev_key_btn()
            else:
                self._set_field(field, ref)
        elif kind == "reload":
            self._reload_all()
        elif kind in ("state", "recording"):
            self._update_status()
            self._load_editor()

    def _update_status(self) -> None:
        rid, pid = self.ctl.recording_id, self.ctl.running_id
        text, color, ov = "Sẵn sàng", COLOR_IDLE, "Sẵn sàng"
        try:
            if rid:
                name = self.ctl.get(rid).name
                text, color, ov = f"Đang ghi: {name}", COLOR_REC, f"● GHI: {name}"
            elif pid:
                name = self.ctl.get(pid).name
                text, color, ov = f"Đang chạy: {name}", COLOR_RUN, f"▶ {name}"
        except KeyError:
            pass
        self.status.config(text=text, foreground=color)
        if self.overlay is not None:
            self.overlay.set_status(ov, color if color != COLOR_IDLE else "#ddd")

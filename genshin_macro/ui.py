"""tkinter UI. All controller calls happen on the Tk thread; listener-thread
events reach the UI through the queue drained in `_poll`."""
from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

from .controller import Controller
from .model import KeyRef, RecordedMacro, SpamMacro

POLL_MS = 50
COLOR_IDLE, COLOR_REC, COLOR_RUN = "#2a7", "#c33", "#27c"


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
    ):
        super().__init__()
        self.ctl = controller
        self.events = events
        self._on_overlay_created = on_overlay_created
        self.title("Genshin Macro")
        self.minsize(720, 460)
        self._selected: Optional[str] = None
        self._capturing: Optional[ttk.Button] = None
        self._ids: list[str] = []
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

        # spam section
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

        # recorded section
        self.rec_frame = ttk.Frame(e)
        self.rec_frame.grid(row=r, column=0, columnspan=2, sticky="nsew")
        e.rowconfigure(r, weight=1)
        self.rec_frame.columnconfigure(0, weight=1)
        self.rec_frame.rowconfigure(2, weight=1)
        top = ttk.Frame(self.rec_frame)
        top.grid(row=0, column=0, sticky="ew")
        self.rec_btn = ttk.Button(top, text="● Ghi", command=self._toggle_record)
        self.rec_btn.pack(side="left")
        self.rec_info = ttk.Label(top, text="0 sự kiện, 0 ms")
        self.rec_info.pack(side="left", padx=8)
        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Lặp lại đến khi dừng", variable=self.loop_var, command=self._commit_loop).pack(side="left", padx=8)
        ttk.Label(self.rec_frame, text="Thao tác đã ghi:").grid(row=1, column=0, sticky="w", pady=(8, 2))
        tree_box = ttk.Frame(self.rec_frame)
        tree_box.grid(row=2, column=0, sticky="nsew")
        tree_box.columnconfigure(0, weight=1)
        tree_box.rowconfigure(0, weight=1)
        self.event_tree = ttk.Treeview(tree_box, columns=("t", "action", "key"), show="headings", height=10)
        self.event_tree.heading("t", text="Thời gian (ms)")
        self.event_tree.heading("action", text="Hành động")
        self.event_tree.heading("key", text="Phím / Chuột")
        self.event_tree.column("t", width=110, anchor="e")
        self.event_tree.column("action", width=90, anchor="center")
        self.event_tree.column("key", width=160, anchor="w")
        self.event_tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(tree_box, orient="vertical", command=self.event_tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.event_tree.configure(yscrollcommand=sb.set)
        r += 1
        ttk.Label(
            e,
            text=(
                "Bấm phím tắt khi đang trong game để chạy / dừng macro.\n"
                "Ghi: chọn macro kiểu Ghi, bấm phím Ghi (hoặc nút ● Ghi) để bắt đầu, bấm lại để dừng.\n"
                "Phím tắt của chính macro đó cũng dừng ghi."
            ),
            foreground="#666",
            justify="left",
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
            self._fill_events(m)
            self._show_kind("recorded")

    def _fill_events(self, m: RecordedMacro) -> None:
        self.event_tree.delete(*self.event_tree.get_children())
        for ev in m.events:
            t, action, label = self.ctl.describe_event(ev)
            self.event_tree.insert("", "end", values=(str(t), action, label))

    def _show_kind(self, kind: Optional[str]) -> None:
        self.spam_frame.grid_remove()
        self.rec_frame.grid_remove()
        if kind == "spam":
            self.spam_frame.grid()
        elif kind == "recorded":
            self.rec_frame.grid()
        self.hotkey_btn.config(state="normal" if kind else "disabled")

    # ---- actions -------------------------------------------------------------
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

    def _capture(self, field: str) -> None:
        btn = {"hotkey": self.hotkey_btn, "key": self.key_btn, "record": self.record_btn}[field]
        if field != "record" and not self._selected:
            return
        if self._capturing is not None:
            self.ctl.cancel_capture()
            self._capturing = None
            self._load_editor()
            rh = self.ctl.record_hotkey
            self.record_btn.config(text=rh.label if rh else "(chưa có)")
            return
        self._capturing = btn
        btn.config(text="Nhấn phím…")
        self.ctl.begin_capture(lambda ref: self.events.put(("captured", field, ref)))

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
            else:
                self._set_field(field, ref)
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

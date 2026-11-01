"""tkinter UI. All controller calls happen on the Tk thread; listener-thread
events reach the UI through the queue drained in `_poll`."""
from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

from .controller import Controller
from .model import KeyRef, RecordedMacro, SpamMacro

POLL_MS = 50


class App(tk.Tk):
    def __init__(self, controller: Controller, events: queue.Queue):
        super().__init__()
        self.ctl = controller
        self.events = events
        self.title("Genshin Macro")
        self.minsize(640, 400)
        self._selected: Optional[str] = None
        self._capturing: Optional[tk.Button] = None
        self._build()
        self._refresh_list()
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
        self.status = ttk.Label(bottom, text="Sẵn sàng", foreground="#2a7")
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
        self.rec_frame.grid(row=r, column=0, columnspan=2, sticky="ew")
        self.rec_btn = ttk.Button(self.rec_frame, text="● Ghi", command=self._toggle_record)
        self.rec_btn.grid(row=0, column=0, sticky="w", pady=2)
        self.rec_info = ttk.Label(self.rec_frame, text="0 sự kiện, 0 ms")
        self.rec_info.grid(row=0, column=1, sticky="w", padx=8)
        self.loop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.rec_frame, text="Lặp lại đến khi dừng", variable=self.loop_var, command=self._commit_loop).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=2
        )
        r += 1
        ttk.Label(
            e,
            text="Bấm phím tắt khi đang trong game để chạy / dừng.\nKhi đang ghi, bấm phím tắt của macro đó để dừng ghi.",
            foreground="#666",
            justify="left",
        ).grid(row=r + 1, column=0, columnspan=2, sticky="w", pady=(16, 0))
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
        self._load_editor()

    def _on_select(self, _ev=None) -> None:
        sel = self.listbox.curselection()
        self._selected = self._ids[sel[0]] if sel else None
        self._load_editor()

    def _current(self):
        return self.ctl.get(self._selected) if self._selected else None

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
            self._show_kind("recorded")

    def _show_kind(self, kind: Optional[str]) -> None:
        self.spam_frame.grid_remove()
        self.rec_frame.grid_remove()
        if kind == "spam":
            self.spam_frame.grid()
        elif kind == "recorded":
            self.rec_frame.grid()
        state = "normal" if kind else "disabled"
        for w in (self.hotkey_btn,):
            w.config(state=state)

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

    def _capture(self, field: str) -> None:
        if not self._selected:
            return
        btn = self.hotkey_btn if field == "hotkey" else self.key_btn
        if self._capturing is not None:
            self.ctl.cancel_capture()
            self._load_editor()
            self._capturing = None
            return
        self._capturing = btn
        btn.config(text="Nhấn phím…")

        def got(ref: KeyRef) -> None:
            self.events.put(("captured", field, ref))

        self.ctl.begin_capture(got)

    def _toggle_record(self) -> None:
        m = self._current()
        if not isinstance(m, RecordedMacro):
            return
        if self.ctl.recording_id == m.id:
            self.ctl.stop_recording()
        else:
            self.ctl.start_recording(m.id)
            messagebox.showinfo(
                "Đang ghi",
                f"Chuyển sang game và đánh combo.\nBấm phím tắt của macro ({m.hotkey.label if m.hotkey else 'chưa đặt'}) "
                "hoặc quay lại đây bấm Dừng ghi để kết thúc.",
            )
        self._load_editor()

    # ---- queue from listener thread ------------------------------------------
    def _poll(self) -> None:
        try:
            while True:
                item = self.events.get_nowait()
                self._handle(item)
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll)

    def _handle(self, item) -> None:
        kind = item[0]
        if kind == "captured":
            _, field, ref = item
            self._capturing = None
            self._set_field(field, ref)
        elif kind in ("state", "recording"):
            self._update_status()
            self._load_editor()

    def _update_status(self) -> None:
        rid, pid = self.ctl.recording_id, self.ctl.running_id
        if rid:
            self.status.config(text=f"Đang ghi: {self.ctl.get(rid).name}", foreground="#c33")
        elif pid:
            try:
                self.status.config(text=f"Đang chạy: {self.ctl.get(pid).name}", foreground="#27c")
            except KeyError:
                self.status.config(text="Sẵn sàng", foreground="#2a7")
        else:
            self.status.config(text="Sẵn sàng", foreground="#2a7")

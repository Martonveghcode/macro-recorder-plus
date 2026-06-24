from __future__ import annotations

import queue
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .model import Macro, MacroEvent, utc_now_iso
from .player import MacroPlayer
from .recorder import MacroRecorder, RecorderUnavailable
from .storage import load_macro, save_macro


IGNORED_HOTKEYS = {"Key.f8", "Key.f9"}


class MacroRecorderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Macro Recorder +")
        self.root.geometry("980x650")
        self.root.minsize(780, 520)

        self.macro = Macro(name="Untitled macro")
        self.current_file: Path | None = None
        self.recorder: MacroRecorder | None = None
        self.player = MacroPlayer(
            on_status=lambda message: self.root.after(0, self.set_status, message),
            on_event=lambda event, index, total: self.root.after(0, self._set_playback_progress, index, total),
            on_done=lambda completed: self.root.after(0, self._playback_finished, completed),
        )
        self.event_queue: queue.Queue[MacroEvent] = queue.Queue()
        self.global_hotkeys = None
        self.is_recording = False
        self._countdown_after: str | None = None
        self._countdown_remaining = 0
        self._record_append_offset = 0.0

        self.record_moves_var = tk.BooleanVar(value=True)
        self.countdown_var = tk.IntVar(value=3)
        self.loops_var = tk.IntVar(value=1)
        self.speed_var = tk.DoubleVar(value=1.0)
        self.status_var = tk.StringVar(value="Ready")
        self.summary_var = tk.StringVar(value="0 events, 0.00s")
        self.progress_var = tk.StringVar(value="")

        self._build_ui()
        self._bind_shortcuts()
        self._start_global_hotkeys()
        self._refresh_event_table()
        self._poll_events()

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.configure("Toolbar.TButton", padding=(12, 7))
        style.configure("Status.TLabel", padding=(10, 5))

        root_frame = ttk.Frame(self.root, padding=12)
        root_frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        toolbar = ttk.Frame(root_frame)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(10, weight=1)

        self.record_button = ttk.Button(toolbar, text="Record", style="Toolbar.TButton", command=self.toggle_recording)
        self.record_button.grid(row=0, column=0, padx=(0, 6))
        self.stop_button = ttk.Button(toolbar, text="Stop", style="Toolbar.TButton", command=self.stop_active, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=6)
        self.play_button = ttk.Button(toolbar, text="Play", style="Toolbar.TButton", command=self.play_macro)
        self.play_button.grid(row=0, column=2, padx=6)
        ttk.Button(toolbar, text="Save", style="Toolbar.TButton", command=self.save_macro).grid(row=0, column=3, padx=6)
        ttk.Button(toolbar, text="Load", style="Toolbar.TButton", command=self.load_macro).grid(row=0, column=4, padx=6)
        ttk.Button(toolbar, text="Delete", style="Toolbar.TButton", command=self.delete_selected).grid(row=0, column=5, padx=6)
        ttk.Button(toolbar, text="Clear", style="Toolbar.TButton", command=self.clear_macro).grid(row=0, column=6, padx=6)

        controls = ttk.Frame(root_frame, padding=(0, 12, 0, 8))
        controls.grid(row=1, column=0, sticky="ew")
        for column in range(12):
            controls.columnconfigure(column, weight=0)
        controls.columnconfigure(11, weight=1)

        ttk.Checkbutton(controls, text="Pointer movement", variable=self.record_moves_var).grid(row=0, column=0, padx=(0, 18))
        ttk.Label(controls, text="Countdown").grid(row=0, column=1, sticky="w")
        ttk.Spinbox(controls, from_=0, to=30, width=5, textvariable=self.countdown_var).grid(row=0, column=2, padx=(6, 18))
        ttk.Label(controls, text="Loops").grid(row=0, column=3, sticky="w")
        ttk.Spinbox(controls, from_=1, to=999, width=5, textvariable=self.loops_var).grid(row=0, column=4, padx=(6, 18))
        ttk.Label(controls, text="Speed").grid(row=0, column=5, sticky="w")
        speed = ttk.Scale(controls, from_=0.25, to=4.0, variable=self.speed_var, command=lambda _: self._update_summary())
        speed.grid(row=0, column=6, sticky="ew", padx=(6, 8))
        controls.columnconfigure(6, weight=1)
        self.speed_label = ttk.Label(controls, width=7)
        self.speed_label.grid(row=0, column=7, padx=(0, 18))
        ttk.Label(controls, textvariable=self.summary_var).grid(row=0, column=8, sticky="e")

        table_frame = ttk.Frame(root_frame)
        table_frame.grid(row=2, column=0, sticky="nsew")
        root_frame.rowconfigure(2, weight=1)
        root_frame.columnconfigure(0, weight=1)

        columns = ("index", "time", "device", "action", "details")
        self.event_table = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")
        headings = {
            "index": "#",
            "time": "Time",
            "device": "Device",
            "action": "Action",
            "details": "Details",
        }
        widths = {"index": 52, "time": 90, "device": 110, "action": 110, "details": 520}
        anchors = {"index": "e", "time": "e", "device": "w", "action": "w", "details": "w"}
        for column in columns:
            self.event_table.heading(column, text=headings[column])
            self.event_table.column(column, width=widths[column], anchor=anchors[column], stretch=column == "details")

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.event_table.yview)
        self.event_table.configure(yscrollcommand=y_scroll.set)
        self.event_table.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        status_bar = ttk.Frame(root_frame)
        status_bar.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        status_bar.columnconfigure(0, weight=1)
        ttk.Label(status_bar, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(status_bar, textvariable=self.progress_var, style="Status.TLabel").grid(row=0, column=1, sticky="e")

        self._update_controls()

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-r>", lambda _: self.toggle_recording())
        self.root.bind("<space>", lambda _: self.play_macro())
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _start_global_hotkeys(self) -> None:
        try:
            from pynput import keyboard

            self.global_hotkeys = keyboard.GlobalHotKeys(
                {
                    "<f8>": lambda: self.root.after(0, self.toggle_recording),
                    "<f9>": lambda: self.root.after(0, self.stop_active),
                }
            )
            self.global_hotkeys.start()
        except Exception as exc:
            self.set_status(f"Global hotkeys unavailable: {exc}")

    def toggle_recording(self) -> None:
        if self.is_recording:
            self.stop_recording()
            return
        self.start_recording()

    def start_recording(self) -> None:
        if self.player.running:
            self.player.stop()
        if self._countdown_after is not None:
            return

        self._record_append_offset = 0.0
        if self.macro.events:
            choice = messagebox.askyesnocancel("Existing macro", "Append to the current macro?")
            if choice is None:
                return
            if choice:
                self._record_append_offset = self.macro.duration + 0.1
            else:
                self.macro.clear()
                self._refresh_event_table()

        self._countdown_remaining = max(0, int(self.countdown_var.get()))
        self._run_record_countdown()

    def _run_record_countdown(self) -> None:
        if self._countdown_remaining <= 0:
            self._countdown_after = None
            self._begin_recording()
            return

        self.set_status(f"Recording starts in {self._countdown_remaining}")
        self._countdown_remaining -= 1
        self._countdown_after = self.root.after(1000, self._run_record_countdown)
        self._update_controls()

    def _begin_recording(self) -> None:
        def queue_event(event: MacroEvent) -> None:
            if self._record_append_offset:
                event = replace(event, time=event.time + self._record_append_offset)
            self.event_queue.put(event)

        self.recorder = MacroRecorder(
            on_event=queue_event,
            record_mouse_moves=self.record_moves_var.get(),
            ignored_keys=IGNORED_HOTKEYS,
        )
        try:
            self.recorder.start()
        except RecorderUnavailable as exc:
            self.recorder = None
            self.set_status(str(exc))
            messagebox.showerror("Recording unavailable", str(exc))
            self._update_controls()
            return

        self.is_recording = True
        self.progress_var.set("")
        self.set_status("Recording")
        self._update_controls()

    def stop_recording(self) -> None:
        if not self.is_recording:
            return
        if self.recorder is not None:
            self.recorder.stop()
        self.recorder = None
        self.is_recording = False
        self.macro.updated_at = utc_now_iso()
        self.set_status("Recording stopped")
        self._update_controls()

    def play_macro(self) -> None:
        if self._countdown_after is not None:
            return
        if self.player.running:
            self.player.stop()
            return
        if self.is_recording:
            self.stop_recording()
        if not self.macro.events:
            self.set_status("Nothing to play")
            return

        self._countdown_remaining = max(0, int(self.countdown_var.get()))
        self._run_play_countdown()

    def _run_play_countdown(self) -> None:
        if self._countdown_remaining <= 0:
            self._countdown_after = None
            self.progress_var.set("")
            self.player.play(
                self.macro,
                speed=float(self.speed_var.get()),
                loops=int(self.loops_var.get()),
            )
            self.set_status("Playing")
            self._update_controls()
            return

        self.set_status(f"Playback starts in {self._countdown_remaining}")
        self._countdown_remaining -= 1
        self._countdown_after = self.root.after(1000, self._run_play_countdown)
        self._update_controls()

    def stop_active(self) -> None:
        if self._countdown_after is not None:
            self.root.after_cancel(self._countdown_after)
            self._countdown_after = None
            self.set_status("Canceled")
        if self.is_recording:
            self.stop_recording()
        if self.player.running:
            self.player.stop()
            self.set_status("Stopping playback")
        self._update_controls()

    def save_macro(self) -> None:
        if not self.macro.events:
            self.set_status("Nothing to save")
            return
        initial = self.current_file.name if self.current_file else "macro.mrplus"
        path = filedialog.asksaveasfilename(
            defaultextension=".mrplus",
            filetypes=[("Macro Recorder +", "*.mrplus"), ("JSON", "*.json"), ("All files", "*.*")],
            initialfile=initial,
        )
        if not path:
            return
        self.macro.name = Path(path).stem
        self.current_file = save_macro(self.macro, path)
        self.set_status(f"Saved {self.current_file.name}")
        self._update_summary()

    def load_macro(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Macro Recorder +", "*.mrplus"), ("JSON", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            self.macro = load_macro(path)
        except Exception as exc:
            messagebox.showerror("Load failed", str(exc))
            self.set_status("Load failed")
            return
        self.current_file = Path(path)
        self._refresh_event_table()
        self.set_status(f"Loaded {self.current_file.name}")

    def delete_selected(self) -> None:
        selected = self.event_table.selection()
        if not selected:
            return
        indexes = {int(item_id) for item_id in selected}
        self.macro.remove_indexes(indexes)
        self._refresh_event_table()
        self.set_status(f"Deleted {len(indexes)} event(s)")

    def clear_macro(self) -> None:
        if not self.macro.events:
            return
        if not messagebox.askyesno("Clear macro", "Clear all events?"):
            return
        self.macro.clear()
        self.current_file = None
        self._refresh_event_table()
        self.set_status("Cleared")

    def _poll_events(self) -> None:
        changed = False
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                break
            self.macro.add_event(event)
            changed = True
        if changed:
            self._refresh_event_table(select_last=True)
        self.root.after(100, self._poll_events)

    def _refresh_event_table(self, *, select_last: bool = False) -> None:
        self.event_table.delete(*self.event_table.get_children())
        for index, event in enumerate(self.macro.events):
            self.event_table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    index + 1,
                    f"{event.time:.3f}",
                    event.device,
                    event.action,
                    describe_event(event),
                ),
            )
        if select_last and self.macro.events:
            last = str(len(self.macro.events) - 1)
            self.event_table.selection_set(last)
            self.event_table.see(last)
        self._update_summary()

    def _update_summary(self) -> None:
        self.speed_label.configure(text=f"{float(self.speed_var.get()):.2f}x")
        self.summary_var.set(f"{len(self.macro.events)} events, {self.macro.duration:.2f}s")

    def _update_controls(self) -> None:
        busy = self.is_recording or self.player.running or self._countdown_after is not None
        self.record_button.configure(text="Stop recording" if self.is_recording else "Record")
        self.stop_button.configure(state="normal" if busy else "disabled")
        self.play_button.configure(text="Stop playback" if self.player.running else "Play")
        self._update_summary()

    def _set_playback_progress(self, index: int, total: int) -> None:
        self.progress_var.set(f"{index}/{total}")

    def _playback_finished(self, completed: bool) -> None:
        self.progress_var.set("")
        if not completed and self.status_var.get() == "Playing":
            self.set_status("Playback stopped")
        self._update_controls()

    def set_status(self, message: str) -> None:
        self.status_var.set(message)

    def close(self) -> None:
        self.stop_active()
        if self.global_hotkeys is not None:
            self.global_hotkeys.stop()
        self.root.destroy()


def describe_event(event: MacroEvent) -> str:
    if event.device == "keyboard":
        return event.key or ""
    if event.action == "move":
        return f"x={event.x}, y={event.y}"
    if event.action in {"press", "release"}:
        return f"{event.button or ''} at x={event.x}, y={event.y}"
    if event.action == "scroll":
        return f"dx={event.dx}, dy={event.dy} at x={event.x}, y={event.y}"
    return ""


def main() -> None:
    root = tk.Tk()
    MacroRecorderApp(root)
    root.mainloop()

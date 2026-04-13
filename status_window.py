"""Tkinter status + log viewer, opened from the system tray."""
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING
import logger

if TYPE_CHECKING:
    from config import Config


class StatusWindow:
    def __init__(self, parent: tk.Tk, get_config):
        """
        parent     : the hidden root Tk window from main.py
        get_config : callable that returns the current Config object
        """
        self._parent = parent
        self._get_config = get_config
        self._win: tk.Toplevel | None = None

    # ------------------------------------------------------------------ public

    def toggle(self) -> None:
        """Open window if closed, bring to front if open."""
        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._win.focus_force()
        else:
            self._build()

    # ----------------------------------------------------------------- private

    def _build(self) -> None:
        win = tk.Toplevel(self._parent)
        win.title("Sleeper — Status & Logs")
        win.geometry("700x420")
        win.configure(bg="#1e1e2e")
        win.resizable(True, True)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        self._win = win

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._log_tab(nb)
        self._config_tab(nb)

    # ---------- Log tab

    def _log_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb, bg="#1e1e2e")
        nb.add(frame, text="Today's Log")

        box = tk.Text(frame, bg="#13131f", fg="#c8d3f5",
                      font=("Consolas", 9), state="disabled",
                      relief="flat", wrap="none")
        sb_y = tk.Scrollbar(frame, orient="vertical", command=box.yview)
        sb_x = tk.Scrollbar(frame, orient="horizontal", command=box.xview)
        box.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)

        sb_y.pack(side="right", fill="y")
        sb_x.pack(side="bottom", fill="x")
        box.pack(fill="both", expand=True)

        self._log_box = box
        self._refresh_log()

    def _refresh_log(self) -> None:
        if not (self._win and self._win.winfo_exists()):
            return
        records = logger.read_today()
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        for r in records:
            ts = r.get("ts", "")
            ev = r.get("event", "")
            det = r.get("details", {})
            det_str = "  " + "  ".join(f"{k}={v}" for k, v in det.items()) if det else ""
            color_tag = _event_color(ev)
            line = f"{ts}  [{ev}]{det_str}\n"
            self._log_box.insert("end", line, color_tag)
        self._log_box.configure(state="disabled")
        self._log_box.see("end")
        # Color tags
        self._log_box.tag_configure("violation", foreground="#ff6b6b")
        self._log_box.tag_configure("override",  foreground="#c8a0ff")
        self._log_box.tag_configure("info",      foreground="#9ece6a")
        self._log_box.tag_configure("default",   foreground="#c8d3f5")
        # Schedule next refresh
        self._win.after(5000, self._refresh_log)

    # ---------- Config tab

    def _config_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb, bg="#1e1e2e")
        nb.add(frame, text="Config")

        box = tk.Text(frame, bg="#13131f", fg="#c8d3f5",
                      font=("Consolas", 9), state="disabled",
                      relief="flat", wrap="none")
        sb = tk.Scrollbar(frame, orient="vertical", command=box.yview)
        sb.pack(side="right", fill="y")
        box.pack(fill="both", expand=True)

        cfg = self._get_config()
        lines = []
        lines.append(f"check_interval      : {cfg.check_interval}s")
        lines.append(f"log_dir             : {cfg.log_dir}")
        lines.append(f"override_max_minutes: {cfg.override_max_minutes}")
        lines.append("")
        for w in cfg.time_windows:
            lines.append(f"[{w.name}]")
            lines.append(f"  {w.start_time.strftime('%H:%M')} – {w.end_time.strftime('%H:%M')}")
            lines.append(f"  mode: {w.mode}  force_kill: {w.force_kill}")
            lines.append(f"  apps: {', '.join(w.app_list)}")
            lines.append("")

        box.configure(state="normal")
        box.insert("end", "\n".join(lines))
        box.configure(state="disabled")


def _event_color(event: str) -> str:
    if event in ("violation", "force_killed"):
        return "violation"
    if "override" in event:
        return "override"
    if event in ("app_start", "config_reloaded", "guardian_restarted"):
        return "info"
    return "default"

"""Tkinter status/log viewer, analytics, and config editor — opened from tray."""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Callable, Optional
import threading
import yaml

import logger
from config import ConfigManager, TimeWindow, Config, _parse as _parse_config

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"

# ── palette ──────────────────────────────────────────────────────────────────
BG      = "#1e1e2e"
BG2     = "#13131f"
BG3     = "#2d2d44"
FG      = "#c8d3f5"
ACC     = "#7c5cbf"
RED     = "#ff6b6b"
GREEN   = "#9ece6a"
PURPLE  = "#c8a0ff"
FONT    = ("Segoe UI", 10)
MONO    = ("Consolas", 9)


# ── helpers ───────────────────────────────────────────────────────────────────

def _style_ttk(style: ttk.Style) -> None:
    style.theme_use("clam")
    style.configure("TNotebook",        background=BG,  borderwidth=0)
    style.configure("TNotebook.Tab",    background=BG3, foreground=FG,
                    padding=[10, 4])
    style.map("TNotebook.Tab",          background=[("selected", ACC)])
    style.configure("Treeview",         background=BG2, foreground=FG,
                    fieldbackground=BG2, rowheight=22, borderwidth=0)
    style.configure("Treeview.Heading", background=BG3, foreground=FG,
                    font=(*FONT, "bold"))
    style.map("Treeview",               background=[("selected", ACC)])
    style.configure("TScrollbar",       background=BG3, troughcolor=BG2,
                    bordercolor=BG, arrowcolor=FG)


def _lbl(parent, text, **kw) -> tk.Label:
    return tk.Label(parent, text=text, bg=kw.pop("bg", BG), fg=kw.pop("fg", FG),
                    font=kw.pop("font", FONT), **kw)


def _btn(parent, text, cmd, **kw) -> tk.Button:
    return tk.Button(parent, text=text, command=cmd,
                     bg=kw.pop("bg", ACC), fg=kw.pop("fg", "white"),
                     relief="flat", font=(*FONT, "bold"),
                     activebackground="#9a7adf", activeforeground="white",
                     cursor="hand2", **kw)


def _entry(parent, var, width=30) -> tk.Entry:
    return tk.Entry(parent, textvariable=var, width=width,
                    bg=BG3, fg=FG, insertbackground=FG,
                    relief="flat", font=FONT)


# ─────────────────────────────────────────────────────────────────────────────

class StatusWindow:
    def __init__(self, parent: tk.Tk, get_config: Callable[[], Config]):
        self._parent = parent
        self._get_config = get_config
        self._win: Optional[tk.Toplevel] = None
        self._cfg_mgr: Optional[ConfigManager] = None  # lazily created for editor

    # ── public ────────────────────────────────────────────────────────────────

    def toggle(self) -> None:
        if self._win and self._win.winfo_exists():
            self._win.lift()
            self._win.focus_force()
        else:
            self._build()

    # ── window skeleton ───────────────────────────────────────────────────────

    def _build(self) -> None:
        win = tk.Toplevel(self._parent)
        win.title("Sleeper — Status & Logs")
        win.geometry("880x560")
        win.configure(bg=BG)
        win.resizable(True, True)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        self._win = win

        style = ttk.Style(win)
        _style_ttk(style)

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_log_tab(nb)
        self._build_analytics_tab(nb)
        self._build_config_tab(nb)

    # ── Log tab ───────────────────────────────────────────────────────────────

    def _build_log_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="Today's Log")

        # toolbar
        bar = tk.Frame(frame, bg=BG)
        bar.pack(fill="x", padx=6, pady=(6, 2))
        _lbl(bar, "Filter:").pack(side="left")
        self._log_filter = tk.StringVar()
        tk.Entry(bar, textvariable=self._log_filter, width=20,
                 bg=BG3, fg=FG, insertbackground=FG, relief="flat",
                 font=FONT).pack(side="left", padx=4)
        _btn(bar, "Refresh", self._refresh_log, bg=BG3, fg=FG).pack(side="left", padx=4)

        # treeview
        cols = ("time", "event", "details")
        tv = ttk.Treeview(frame, columns=cols, show="headings", selectmode="browse")
        tv.heading("time",    text="Time")
        tv.heading("event",   text="Event")
        tv.heading("details", text="Details")
        tv.column("time",    width=140, minwidth=100, stretch=False)
        tv.column("event",   width=160, minwidth=100, stretch=False)
        tv.column("details", width=500, minwidth=200)

        tv.tag_configure("violation", foreground=RED)
        tv.tag_configure("override",  foreground=PURPLE)
        tv.tag_configure("info",      foreground=GREEN)

        sb = tk.Scrollbar(frame, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tv.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        self._log_tv = tv
        self._log_filter.trace_add("write", lambda *_: self._refresh_log())
        self._refresh_log()

    def _refresh_log(self) -> None:
        if not (self._win and self._win.winfo_exists()):
            return
        records = logger.read_today()
        filt = self._log_filter.get().strip().lower() if hasattr(self, "_log_filter") else ""
        self._log_tv.delete(*self._log_tv.get_children())
        for r in records:
            ev   = r.get("event", "")
            ts   = r.get("ts", "")
            det  = r.get("details", {})
            det_str = "  ".join(f"{k}={v}" for k, v in det.items()) if det else ""
            if filt and filt not in ev.lower() and filt not in det_str.lower():
                continue
            tag = _event_tag(ev)
            self._log_tv.insert("", "end", values=(ts, ev, det_str), tags=(tag,))
        # scroll to bottom
        children = self._log_tv.get_children()
        if children:
            self._log_tv.see(children[-1])
        self._win.after(5000, self._refresh_log)

    # ── Analytics tab ─────────────────────────────────────────────────────────

    def _build_analytics_tab(self, nb: ttk.Notebook) -> None:
        try:
            import matplotlib
            matplotlib.use("TkAgg")
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        except ImportError:
            frame = tk.Frame(nb, bg=BG)
            nb.add(frame, text="Analytics")
            _lbl(frame, "matplotlib not installed. Run: pip install matplotlib",
                 fg=RED).pack(pady=20)
            return

        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="Analytics")

        # date range toolbar
        bar = tk.Frame(frame, bg=BG)
        bar.pack(fill="x", padx=8, pady=(8, 4))
        _lbl(bar, "From:").pack(side="left")
        self._an_from = tk.StringVar(value=(date.today() - timedelta(days=6)).isoformat())
        _entry(bar, self._an_from, width=12).pack(side="left", padx=4)
        _lbl(bar, "To:").pack(side="left")
        self._an_to = tk.StringVar(value=date.today().isoformat())
        _entry(bar, self._an_to, width=12).pack(side="left", padx=4)
        _btn(bar, "Load", lambda: self._reload_analytics(fig, canvas), bg=ACC).pack(side="left", padx=6)

        # figure with 2 subplots
        fig = Figure(figsize=(8, 4), dpi=96, facecolor=BG)
        self._an_axes = fig.subplots(1, 2)
        for ax in self._an_axes:
            ax.set_facecolor(BG2)
            for spine in ax.spines.values():
                spine.set_edgecolor(BG3)

        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.get_tk_widget().configure(bg=BG)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._an_fig = fig
        self._an_canvas = canvas
        self._reload_analytics(fig, canvas)

    def _reload_analytics(self, fig, canvas) -> None:
        from collections import Counter
        records = logger.read_range(self._an_from.get(), self._an_to.get())
        violations = [r for r in records if r.get("event") == "violation"]

        ax_hour, ax_app = self._an_axes
        ax_hour.clear()
        ax_app.clear()
        for ax in (ax_hour, ax_app):
            ax.set_facecolor(BG2)
            for spine in ax.spines.values():
                spine.set_edgecolor(BG3)
            ax.tick_params(colors=FG, labelsize=8)
            ax.title.set_color(FG)

        # chart 1: violations by hour
        hours = [0] * 24
        for v in violations:
            try:
                h = int(v["ts"][11:13])
                hours[h] += 1
            except Exception:
                pass
        ax_hour.bar(range(24), hours, color=RED, alpha=0.8, width=0.8)
        ax_hour.set_title("Violations by Hour")
        ax_hour.set_xlabel("Hour", color=FG)
        ax_hour.set_ylabel("Count", color=FG)
        ax_hour.set_xticks(range(0, 24, 3))

        # chart 2: top 10 violating apps
        apps = Counter(v.get("details", {}).get("app", "?") for v in violations)
        if apps:
            labels, counts = zip(*apps.most_common(10))
            y_pos = range(len(labels))
            ax_app.barh(list(y_pos), list(counts), color=PURPLE, alpha=0.8)
            ax_app.set_yticks(list(y_pos))
            ax_app.set_yticklabels(list(labels), fontsize=8)
            ax_app.invert_yaxis()
        ax_app.set_title("Top Violating Apps")
        ax_app.set_xlabel("Count", color=FG)

        fig.tight_layout(pad=1.5)
        canvas.draw()

    # ── Config Editor tab ─────────────────────────────────────────────────────

    def _build_config_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="Config Editor")

        # ── general settings ──────────────────────────────────────────────────
        gen = tk.LabelFrame(frame, text="General", bg=BG, fg=FG, font=FONT,
                            relief="groove", bd=1)
        gen.pack(fill="x", padx=10, pady=(8, 4))

        def _row(parent, label, var, row):
            _lbl(parent, label).grid(row=row, column=0, sticky="w", padx=8, pady=3)
            _entry(parent, var, width=20).grid(row=row, column=1, sticky="w", padx=8)

        cfg = self._get_config()
        self._ce_interval    = tk.StringVar(value=str(cfg.check_interval))
        self._ce_override    = tk.StringVar(value=str(cfg.override_max_minutes))
        self._ce_logdir      = tk.StringVar(value=cfg.log_dir)

        _row(gen, "check_interval (s):",    self._ce_interval, 0)
        _row(gen, "override_max_minutes:",  self._ce_override, 1)
        _row(gen, "log_dir:",               self._ce_logdir,   2)

        # ── time windows ──────────────────────────────────────────────────────
        wf = tk.LabelFrame(frame, text="Time Windows", bg=BG, fg=FG, font=FONT,
                           relief="groove", bd=1)
        wf.pack(fill="both", expand=True, padx=10, pady=4)

        wcols = ("name", "start", "end", "mode", "force_kill", "apps")
        self._ce_tv = ttk.Treeview(wf, columns=wcols, show="headings",
                                   selectmode="browse", height=6)
        for col, w in zip(wcols, (120, 60, 60, 80, 70, 300)):
            self._ce_tv.heading(col, text=col)
            self._ce_tv.column(col, width=w, minwidth=40)
        wsb = tk.Scrollbar(wf, orient="vertical", command=self._ce_tv.yview)
        self._ce_tv.configure(yscrollcommand=wsb.set)
        wsb.pack(side="right", fill="y")
        self._ce_tv.pack(fill="both", expand=True, padx=4, pady=4)

        wbtn = tk.Frame(wf, bg=BG)
        wbtn.pack(fill="x", padx=4, pady=(0, 4))
        _btn(wbtn, "Add",    self._ce_add_window).pack(side="left", padx=4)
        _btn(wbtn, "Edit",   self._ce_edit_window).pack(side="left", padx=4)
        _btn(wbtn, "Delete", self._ce_del_window, bg="#6b2d2d").pack(side="left", padx=4)

        self._ce_windows: list[TimeWindow] = list(cfg.time_windows)
        self._ce_refresh_tv()

        # ── save button ───────────────────────────────────────────────────────
        _btn(frame, "💾  Save Config", self._ce_save, bg="#2d6b3a").pack(pady=6)

    def _ce_refresh_tv(self) -> None:
        self._ce_tv.delete(*self._ce_tv.get_children())
        for w in self._ce_windows:
            self._ce_tv.insert("", "end", values=(
                w.name,
                w.start_time.strftime("%H:%M"),
                w.end_time.strftime("%H:%M"),
                w.mode,
                str(w.force_kill),
                ", ".join(w.app_list),
            ))

    def _ce_add_window(self) -> None:
        self._ce_window_dialog(None)

    def _ce_edit_window(self) -> None:
        sel = self._ce_tv.selection()
        if not sel:
            messagebox.showinfo("Select a window", "Select a row first.", parent=self._win)
            return
        idx = self._ce_tv.index(sel[0])
        self._ce_window_dialog(idx)

    def _ce_del_window(self) -> None:
        sel = self._ce_tv.selection()
        if not sel:
            return
        idx = self._ce_tv.index(sel[0])
        del self._ce_windows[idx]
        self._ce_refresh_tv()

    def _ce_window_dialog(self, idx: Optional[int]) -> None:
        """Add/Edit dialog for a TimeWindow."""
        editing = idx is not None
        w = self._ce_windows[idx] if editing else None

        dlg = tk.Toplevel(self._win)
        dlg.title("Edit Window" if editing else "Add Window")
        dlg.geometry("420x400")
        dlg.configure(bg=BG)
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)

        def row(lbl, var, r):
            _lbl(dlg, lbl).grid(row=r, column=0, sticky="w", padx=12, pady=4)
            _entry(dlg, var, width=28).grid(row=r, column=1, sticky="w", padx=8)

        v_name  = tk.StringVar(value=w.name if w else "")
        v_start = tk.StringVar(value=w.start_time.strftime("%H:%M") if w else "00:00")
        v_end   = tk.StringVar(value=w.end_time.strftime("%H:%M") if w else "08:00")
        v_mode  = tk.StringVar(value=w.mode if w else "whitelist")
        v_fk    = tk.BooleanVar(value=w.force_kill if w else False)
        v_apps  = tk.StringVar(value=", ".join(w.app_list) if w else "")

        row("Name:",        v_name,  0)
        row("Start (HH:MM):", v_start, 1)
        row("End (HH:MM):", v_end,   2)

        _lbl(dlg, "Mode:").grid(row=3, column=0, sticky="w", padx=12, pady=4)
        mf = tk.Frame(dlg, bg=BG)
        mf.grid(row=3, column=1, sticky="w", padx=8)
        for m in ("whitelist", "blacklist"):
            tk.Radiobutton(mf, text=m, variable=v_mode, value=m,
                           bg=BG, fg=FG, selectcolor=BG3,
                           activebackground=BG).pack(side="left", padx=6)

        tk.Checkbutton(dlg, text="force_kill (blacklist only)", variable=v_fk,
                       bg=BG, fg=FG, selectcolor=BG3,
                       activebackground=BG).grid(row=4, column=0, columnspan=2,
                                                 sticky="w", padx=12, pady=4)

        _lbl(dlg, "Apps (comma-separated .exe):").grid(
            row=5, column=0, columnspan=2, sticky="w", padx=12, pady=(8, 2))
        apps_text = tk.Text(dlg, width=46, height=6, bg=BG3, fg=FG,
                            insertbackground=FG, relief="flat", font=FONT)
        apps_text.grid(row=6, column=0, columnspan=2, padx=12, pady=4)
        apps_text.insert("1.0", v_apps.get())

        err = _lbl(dlg, "", fg=RED)
        err.grid(row=7, column=0, columnspan=2)

        def confirm():
            from datetime import time as dtime
            name = v_name.get().strip()
            if not name:
                err.config(text="Name required."); return
            try:
                s = dtime.fromisoformat(v_start.get().strip())
                e = dtime.fromisoformat(v_end.get().strip())
            except ValueError:
                err.config(text="Invalid time (HH:MM)."); return
            apps_raw = apps_text.get("1.0", "end").strip()
            apps = [a.strip() for a in apps_raw.replace("\n", ",").split(",") if a.strip()]
            tw = TimeWindow(name=name, start_time=s, end_time=e,
                            mode=v_mode.get(), app_list=apps, force_kill=v_fk.get())
            if editing:
                self._ce_windows[idx] = tw
            else:
                self._ce_windows.append(tw)
            self._ce_refresh_tv()
            dlg.destroy()

        _btn(dlg, "OK", confirm).grid(row=8, column=0, columnspan=2, pady=8)

    def _ce_save(self) -> None:
        try:
            interval = float(self._ce_interval.get())
            override = int(self._ce_override.get())
            logdir   = self._ce_logdir.get().strip()
        except ValueError:
            messagebox.showerror("Invalid", "check_interval must be a number.", parent=self._win)
            return

        data = {
            "check_interval":       interval,
            "override_max_minutes": override,
            "log_dir":              logdir,
            "time_windows": [
                {
                    "name":       w.name,
                    "start_time": w.start_time.strftime("%H:%M"),
                    "end_time":   w.end_time.strftime("%H:%M"),
                    "mode":       w.mode,
                    "force_kill": w.force_kill,
                    "app_list":   w.app_list,
                }
                for w in self._ce_windows
            ],
        }

        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                f.write("# Sleeper configuration\n"
                        "# Saved by Config Editor — changes auto-reload.\n\n")
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True,
                          sort_keys=False)
            messagebox.showinfo("Saved", "config.yaml saved.\nChanges will auto-reload.",
                                parent=self._win)
        except Exception as ex:
            messagebox.showerror("Error", str(ex), parent=self._win)


# ── module-level helpers ──────────────────────────────────────────────────────

def _event_tag(event: str) -> str:
    if event in ("violation", "force_killed"):
        return "violation"
    if "override" in event:
        return "override"
    if event in ("app_start", "config_reloaded", "guardian_restarted"):
        return "info"
    return ""

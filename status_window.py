"""Tkinter status/log viewer, analytics, and config viewer — opened from tray."""
import tkinter as tk
from tkinter import ttk
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

import logger
from config import Config

BASE_DIR = Path(__file__).resolve().parent

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

    # ── Config Viewer tab (read-only) ─────────────────────────────────────────

    def _build_config_tab(self, nb: ttk.Notebook) -> None:
        frame = tk.Frame(nb, bg=BG)
        nb.add(frame, text="Config")

        # general settings — read-only labels
        gen = tk.LabelFrame(frame, text="General", bg=BG, fg=FG, font=FONT,
                            relief="groove", bd=1)
        gen.pack(fill="x", padx=10, pady=(8, 4))

        cfg = self._get_config()
        rows = [
            ("check_interval (s):",    str(cfg.check_interval)),
            ("override_max_minutes:",  str(cfg.override_max_minutes)),
            ("log_dir:",               cfg.log_dir),
        ]
        for r, (label, val) in enumerate(rows):
            _lbl(gen, label).grid(row=r, column=0, sticky="w", padx=8, pady=3)
            _lbl(gen, val, fg=PURPLE).grid(row=r, column=1, sticky="w", padx=8)

        # time windows — read-only treeview
        wf = tk.LabelFrame(frame, text="Time Windows", bg=BG, fg=FG, font=FONT,
                           relief="groove", bd=1)
        wf.pack(fill="both", expand=True, padx=10, pady=4)

        wcols = ("name", "start", "end", "mode", "force_kill", "apps")
        tv = ttk.Treeview(wf, columns=wcols, show="headings",
                          selectmode="none", height=6)
        for col, w in zip(wcols, (120, 60, 60, 80, 70, 300)):
            tv.heading(col, text=col)
            tv.column(col, width=w, minwidth=40)
        wsb = tk.Scrollbar(wf, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=wsb.set)
        wsb.pack(side="right", fill="y")
        tv.pack(fill="both", expand=True, padx=4, pady=4)

        for w in cfg.time_windows:
            tv.insert("", "end", values=(
                w.name,
                w.start_time.strftime("%H:%M"),
                w.end_time.strftime("%H:%M"),
                w.mode,
                str(w.force_kill),
                ", ".join(w.app_list),
            ))

        _lbl(frame, "Edit config.yaml directly — changes auto-reload.",
             fg="#888899", font=("Segoe UI", 9, "italic")).pack(pady=(2, 6))


# ── module-level helpers ──────────────────────────────────────────────────────

def _event_tag(event: str) -> str:
    if event in ("violation", "force_killed"):
        return "violation"
    if "override" in event:
        return "override"
    if event in ("app_start", "config_reloaded", "guardian_restarted"):
        return "info"
    return ""

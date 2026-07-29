"""Lightweight hover tooltips for Tkinter widgets.

Tkinter has no built-in tooltip widget. This is the standard bind-on-Enter/
Leave-a-borderless-Toplevel pattern, kept deliberately small: DOT's GUI has
~25 parameters across several panels and every one needs a plain-language
explanation a first-time user can find without leaving the app.
"""

from __future__ import annotations

import tkinter as tk


class Tooltip:
    """Shows ``text`` in a small popup while the mouse hovers over ``widget``."""

    _DELAY_MS = 400

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self._tipwindow: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: tk.Event | None = None) -> None:
        self._cancel_scheduled()
        self._after_id = self.widget.after(self._DELAY_MS, self._show)

    def _cancel_scheduled(self) -> None:
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        if self._tipwindow is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tipwindow = tk.Toplevel(self.widget)
        tipwindow.wm_overrideredirect(True)
        tipwindow.wm_geometry(f"+{x}+{y}")
        # Best-effort "always on top of this app" hint; harmless if unsupported.
        try:
            tipwindow.wm_attributes("-topmost", True)
        except tk.TclError:
            pass
        label = tk.Label(
            tipwindow,
            text=self.text,
            justify="left",
            background="#ffffe0",
            foreground="#222222",
            relief="solid",
            borderwidth=1,
            wraplength=360,
            font=("TkDefaultFont", 9),
        )
        label.pack(ipadx=6, ipady=3)
        self._tipwindow = tipwindow

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel_scheduled()
        if self._tipwindow is not None:
            self._tipwindow.destroy()
            self._tipwindow = None


def attach_tooltip(widget: tk.Widget, text: str) -> Tooltip:
    """Attach a hover tooltip to ``widget`` and return the handle (kept alive by the caller)."""

    return Tooltip(widget, text)

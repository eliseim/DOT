from __future__ import annotations

import tkinter as tk

import pytest

from dot.gui.tooltip import Tooltip, attach_tooltip


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no display available for Tkinter: {exc}")
    window.withdraw()
    yield window
    window.destroy()


def test_attach_tooltip_returns_a_tooltip_bound_to_the_widget(root: tk.Tk) -> None:
    label = tk.Label(root, text="Aperture radius")

    tooltip = attach_tooltip(label, "Radius of the clear bore, in mm.")

    assert isinstance(tooltip, Tooltip)
    assert tooltip.widget is label
    assert tooltip.text == "Radius of the clear bore, in mm."


def test_tooltip_show_creates_a_toplevel_with_the_text(root: tk.Tk) -> None:
    label = tk.Label(root, text="Aperture radius")
    label.pack()
    root.update()
    tooltip = Tooltip(label, "Radius of the clear bore, in mm.")

    tooltip._show()

    assert tooltip._tipwindow is not None
    children = tooltip._tipwindow.winfo_children()
    assert any(isinstance(child, tk.Label) and child.cget("text") == tooltip.text for child in children)

    tooltip._hide()
    assert tooltip._tipwindow is None


def test_tooltip_hide_without_a_shown_window_does_not_raise(root: tk.Tk) -> None:
    label = tk.Label(root, text="Aperture radius")
    tooltip = Tooltip(label, "some text")

    tooltip._hide()  # no window was ever shown -- must be a no-op, not an error

    assert tooltip._tipwindow is None


def test_tooltip_with_empty_text_never_shows_a_window(root: tk.Tk) -> None:
    label = tk.Label(root, text="Aperture radius")
    tooltip = Tooltip(label, "")

    tooltip._show()

    assert tooltip._tipwindow is None


def test_tooltip_show_is_idempotent_while_already_shown(root: tk.Tk) -> None:
    label = tk.Label(root, text="Aperture radius")
    label.pack()
    root.update()
    tooltip = Tooltip(label, "text")

    tooltip._show()
    first_window = tooltip._tipwindow
    tooltip._show()

    assert tooltip._tipwindow is first_window
    tooltip._hide()

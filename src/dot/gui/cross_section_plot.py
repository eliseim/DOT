"""Matplotlib cross-section rendering for one-quadrant dipole designs."""

from __future__ import annotations

from dataclasses import dataclass

from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Polygon

from dot.geometry import DipoleDesign, Point


@dataclass(frozen=True, slots=True)
class MirroredTurnPolygon:
    """A turn polygon after applying one DOT dipole mirror image."""

    corners: tuple[Point, Point, Point, Point]
    current_a: float


def mirrored_turn_polygons(design: DipoleDesign) -> tuple[MirroredTurnPolygon, ...]:
    """Return every turn mirrored with ``dipole_mirror_sources`` signs.

    The geometry/current orbit is ``(x, y, I)``, ``(-x, y, -I)``,
    ``(-x, -y, -I)``, and ``(x, -y, I)``, matching
    ``dot.physics.field.dipole_mirror_sources`` exactly.
    """

    mirrored: list[MirroredTurnPolygon] = []
    for turn in design.all_turns():
        for x_sign, y_sign, current_sign in (
            (1.0, 1.0, 1.0),
            (-1.0, 1.0, -1.0),
            (-1.0, -1.0, -1.0),
            (1.0, -1.0, 1.0),
        ):
            mirrored.append(
                MirroredTurnPolygon(
                    corners=tuple((x_sign * x, y_sign * y) for x, y in turn.corners),
                    current_a=current_sign * turn.current_a,
                )
            )
    return tuple(mirrored)


def cross_section_figure(design: DipoleDesign) -> Figure:
    """Return a matplotlib figure showing the full mirrored coil cross-section."""

    figure = Figure(figsize=(6.0, 6.0), dpi=100)
    axes = figure.add_subplot(111)
    draw_cross_section(axes, design)
    figure.tight_layout()
    return figure


def draw_cross_section(
    axes: Axes,
    design: DipoleDesign,
    *,
    title: str = "Dipole cross-section",
) -> None:
    """Draw a full mirrored coil into an existing Matplotlib axes."""

    axes.set_aspect("equal", adjustable="box")
    axes.set_xlabel("x [mm]")
    axes.set_ylabel("y [mm]")
    axes.set_title(title)

    aperture = Circle(
        (0.0, 0.0),
        radius=design.aperture_radius_mm,
        fill=False,
        linestyle="--",
        linewidth=1.2,
        edgecolor="#3f4752",
    )
    axes.add_patch(aperture)

    for polygon in mirrored_turn_polygons(design):
        facecolor = "#3b82f6" if polygon.current_a >= 0.0 else "#ef4444"
        axes.add_patch(
            Polygon(
                polygon.corners,
                closed=True,
                facecolor=facecolor,
                edgecolor="#111827",
                linewidth=0.7,
                alpha=0.78,
            )
        )

    extent = _plot_extent(design)
    axes.set_xlim(-extent, extent)
    axes.set_ylim(-extent, extent)
    axes.grid(True, color="#e5e7eb", linewidth=0.6)


def plot_cross_section(design: DipoleDesign) -> Figure:
    """Alias for callers that prefer a verb-style plotting function name."""

    return cross_section_figure(design)


def _plot_extent(design: DipoleDesign) -> float:
    values = [design.aperture_radius_mm]
    for turn in design.all_turns():
        values.extend(max(abs(x), abs(y)) for x, y in turn.corners)
    return max(values, default=1.0) * 1.15

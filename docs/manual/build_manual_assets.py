"""Generate reproducible diagrams for the DOT technical and user manual."""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Arc, Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle


ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).resolve().parent / "assets"

NAVY = "#17365d"
BLUE = "#2f75b5"
CYAN = "#5b9bd5"
GREEN = "#2e8b57"
ORANGE = "#d97706"
RED = "#c0392b"
PURPLE = "#7030a0"
LIGHT = "#eef4fb"
GRID = "#d9e2f3"
TEXT = "#1f2937"


def _save(fig: plt.Figure, name: str) -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    fig.savefig(ASSETS / name, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _box(ax, xy, width, height, text, *, color=BLUE, fill=LIGHT, fontsize=9):
    x, y = xy
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.025",
        linewidth=1.4,
        edgecolor=color,
        facecolor=fill,
    )
    ax.add_patch(patch)
    ax.text(x + width / 2, y + height / 2, text, ha="center", va="center", fontsize=fontsize, color=TEXT)
    return patch


def _arrow(ax, start, end, *, color=NAVY, style="-|>", lw=1.5):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle=style, mutation_scale=12, color=color, lw=lw))


def workflow_diagram() -> None:
    fig, ax = plt.subplots(figsize=(11.2, 5.7))
    ax.set_xlim(0, 11.2)
    ax.set_ylim(0, 5.7)
    ax.axis("off")
    ax.text(0.15, 5.42, "DOT end-to-end workflow", fontsize=16, fontweight="bold", color=NAVY)

    boxes = [
        (0.2, 3.62, 1.72, 1.05, "Designer inputs\nfield, aperture, gaps,\nconductors, targets"),
        (2.18, 3.62, 1.72, 1.05, "Resolve conductors\ngeometry, insulation,\ncritical-current fit"),
        (4.16, 3.62, 1.72, 1.05, "Build search space\nfixed midplane anchors,\nmixed-variable genome"),
        (6.14, 3.62, 1.72, 1.05, "NSGA-II loop\nsample, repair, check,\nevaluate, survive"),
        (8.12, 3.62, 1.72, 1.05, "Final verification\ngeometry, field, current,\nharmonics, margins"),
        (10.10, 3.62, 0.90, 1.05, "Certified\nPareto\narchive"),
    ]
    for x, y, w, h, label in boxes:
        _box(ax, (x, y), w, h, label, fontsize=8.5)
    for left, right in zip(boxes, boxes[1:]):
        _arrow(ax, (left[0] + left[2], left[1] + left[3] / 2), (right[0], right[1] + right[3] / 2))

    _box(ax, (5.88, 1.00), 2.25, 1.12, "Live campaign feedback\nselected design, ETA,\nmargin, residual harmonics, turns", color=GREEN, fill="#edf7f0", fontsize=8.5)
    _arrow(ax, (7.0, 3.62), (7.0, 2.12), color=GREEN)
    _box(ax, (8.55, 1.00), 2.28, 1.12, "Saved engineering artifacts\nsummary sheets, geometry CSV,\nJSON archives, Pareto plot", color=PURPLE, fill="#f5effa", fontsize=8.5)
    _arrow(ax, (9.0, 3.62), (9.55, 2.12), color=PURPLE)
    ax.text(
        0.2,
        0.30,
        "The optimizer never receives a reference coil layout. It receives only the declared design space and requirements.",
        fontsize=9,
        color=TEXT,
    )
    _save(fig, "workflow.png")


def geometry_convention_diagram() -> None:
    fig, ax = plt.subplots(figsize=(9.2, 6.0))
    ax.set_aspect("equal")
    ax.set_xlim(-4, 85)
    ax.set_ylim(-9, 65)
    ax.axis("off")
    ax.text(-1, 61, "Quadrant geometry and angle convention", fontsize=15, fontweight="bold", color=NAVY)
    aperture = 22
    ax.add_patch(Circle((0, 0), aperture, fill=False, ls="--", lw=1.4, ec="#6b7280"))
    ax.plot([0, 82], [0, 0], color="#111827", lw=1.2)
    ax.plot([0, 0], [0, 57], color="#111827", lw=1.2)
    ax.text(74, -4.5, "midplane (+x)", fontsize=9)
    ax.text(2.8, 53, "pole axis (+y)", fontsize=9, rotation=90, va="top")
    ax.text(5, 8, "clear aperture", fontsize=9, color="#6b7280")

    phi = math.radians(31)
    radius = 36
    anchor = (radius * math.cos(phi), radius * math.sin(phi))
    alpha = math.radians(48)
    h, w = 5.0, 18.0
    eh = (math.cos(alpha), math.sin(alpha))
    ew = (-math.sin(alpha), math.cos(alpha))
    corners = [
        (anchor[0] - w / 2 * ew[0], anchor[1] - w / 2 * ew[1]),
        (anchor[0] + w / 2 * ew[0], anchor[1] + w / 2 * ew[1]),
        (anchor[0] + w / 2 * ew[0] + h * eh[0], anchor[1] + w / 2 * ew[1] + h * eh[1]),
        (anchor[0] - w / 2 * ew[0] + h * eh[0], anchor[1] - w / 2 * ew[1] + h * eh[1]),
    ]
    ax.add_patch(Polygon(corners, closed=True, fc="#f8a5a5", ec=RED, lw=1.4))
    ax.scatter(*anchor, s=25, color=RED, zorder=5)
    ax.plot([0, anchor[0]], [0, anchor[1]], color=BLUE, lw=1.5)
    ax.text(anchor[0] / 2 + 1, anchor[1] / 2 - 2, "R", color=BLUE, fontsize=11, fontweight="bold")
    ax.add_patch(Arc((0, 0), 24, 24, theta1=0, theta2=31, color=BLUE, lw=1.5))
    ax.text(12.5, 3.1, "phi", color=BLUE, fontsize=11, fontweight="bold")
    ax.arrow(anchor[0], anchor[1], 12 * eh[0], 12 * eh[1], width=0.14, head_width=1.3, color=GREEN, length_includes_head=True)
    ax.text(anchor[0] + 10 * eh[0] + 1, anchor[1] + 10 * eh[1], "height axis", color=GREEN, fontsize=9)
    ax.add_patch(Arc(anchor, 16, 16, theta1=0, theta2=48, color=GREEN, lw=1.4))
    ax.text(anchor[0] + 8.8, anchor[1] + 2.0, "alpha", color=GREEN, fontsize=10, fontweight="bold")
    ax.text(46, 9, "phi = 0 deg at midplane\nphi -> 90 deg at pole\nalpha = absolute cable-frame angle", fontsize=10, color=TEXT, bbox=dict(boxstyle="round,pad=0.4", fc=LIGHT, ec=BLUE))
    _save(fig, "geometry_convention.png")


def constraints_diagram() -> None:
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.0, 5.7))
    for ax in (ax1, ax2):
        ax.set_aspect("equal")
        ax.axis("off")
    ax1.set_xlim(-3, 82)
    ax1.set_ylim(-4, 70)
    ax2.set_xlim(-3, 82)
    ax2.set_ylim(-4, 70)
    ax1.set_title("Clearances and polygon checks", fontsize=13, color=NAVY, fontweight="bold")
    ax2.set_title("Two conservative nesting half-planes", fontsize=13, color=NAVY, fontweight="bold")

    aperture = 20
    for ax in (ax1, ax2):
        ax.add_patch(Circle((0, 0), aperture, fill=False, ls="--", ec="#6b7280"))
        ax.plot([0, 80], [0, 0], color="#111827", lw=1)
        ax.plot([0, 0], [0, 67], color="#111827", lw=1)

    def turn(ax, x, y, angle, color):
        patch = Rectangle((x, y), 18, 5, angle=angle, fc=color, ec="#374151", lw=1.0)
        ax.add_patch(patch)
        return patch

    turn(ax1, 23, 2.5, 0, "#f8a5a5")
    turn(ax1, 23, 9.5, 3, "#f8a5a5")
    turn(ax1, 36, 29, 24, "#f8a5a5")
    turn(ax1, 50, 40, 36, "#f8a5a5")
    turn(ax1, 45, 4.5, 0, "#9ec5f8")
    turn(ax1, 46, 12.0, 4, "#9ec5f8")
    turn(ax1, 56, 31, 28, "#9ec5f8")
    ax1.annotate("midplane gap", xy=(26, 1), xytext=(25, -1.5), ha="center", fontsize=8, arrowprops=dict(arrowstyle="<->", color=ORANGE))
    ax1.annotate("inter-layer spacing", xy=(43, 10), xytext=(61, 17), fontsize=8, color=GREEN, arrowprops=dict(arrowstyle="->", color=GREEN))
    ax1.annotate("closest inter-block distance", xy=(43, 25), xytext=(48, 57), fontsize=8, color=PURPLE, arrowprops=dict(arrowstyle="->", color=PURPLE))
    ax1.annotate("pole-axis distance proxy", xy=(7, 53), xytext=(22, 63), fontsize=8, color=RED, arrowprops=dict(arrowstyle="<->", color=RED))
    ax1.text(4, 8, "aperture\nclearance", fontsize=8, color="#6b7280")
    ax1.text(10, 68, "All checks use insulated convex turn polygons.", fontsize=8.5, color=TEXT)

    inner = Polygon([(25, 28), (34, 34), (45, 51), (36, 46)], closed=True, fc="#f8a5a5", ec=RED, lw=1.2)
    outer1 = Polygon([(43, 20), (54, 25), (65, 39), (53, 35)], closed=True, fc="#9ec5f8", ec=BLUE, lw=1.2)
    outer2 = Polygon([(50, 42), (60, 47), (68, 58), (57, 53)], closed=True, fc="#9ec5f8", ec=BLUE, lw=1.2)
    ax2.add_patch(inner)
    ax2.add_patch(outer1)
    ax2.add_patch(outer2)
    ax2.plot([5, 73], [14, 61], ls="--", lw=1.4, color=GREEN)
    ax2.plot([6, 75], [16, 55], ls=(0, (3, 3)), lw=1.4, color=PURPLE)
    ax2.text(37, 60, "prolonged pole-side edge", fontsize=8, color=GREEN, rotation=34)
    ax2.text(34, 8, "prolonged lower edge", fontsize=8, color=PURPLE, rotation=29)
    ax2.text(6, 64, "Every outer-layer vertex must remain\non the same side as the origin.", fontsize=8.5, color=TEXT)
    _save(fig, "geometry_constraints.png")


def nsga2_diagram() -> None:
    fig, ax = plt.subplots(figsize=(11.5, 7.0))
    ax.set_xlim(0, 11.5)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.text(0.2, 6.65, "DOT's constrained, topology-aware NSGA-II generation", fontsize=15, fontweight="bold", color=NAVY)

    steps = [
        (0.4, 5.05, 2.0, 0.8, "Parent population\nmixed genomes"),
        (3.05, 5.05, 2.0, 0.8, "Selection + variation\nUX, SBX, mutations"),
        (5.70, 5.05, 2.0, 0.8, "Ordered repair chain\nstructure -> exact checks"),
        (8.35, 5.05, 2.35, 0.8, "Evaluate candidates\ngeometry -> current -> physics"),
        (8.35, 2.90, 2.35, 0.8, "Combine parents + offspring\nconstraint-aware ranking"),
        (5.70, 2.90, 2.0, 0.8, "Non-dominated fronts\nrank 0, rank 1, ..."),
        (3.05, 2.90, 2.0, 0.8, "Crowding distance +\ntopology-family quotas"),
        (0.4, 2.90, 2.0, 0.8, "Next population\nelitist survival"),
    ]
    colors = [BLUE, BLUE, ORANGE, GREEN, GREEN, PURPLE, PURPLE, BLUE]
    fills = [LIGHT, LIGHT, "#fff4e6", "#edf7f0", "#edf7f0", "#f5effa", "#f5effa", LIGHT]
    for item, color, fill in zip(steps, colors, fills, strict=True):
        _box(ax, (item[0], item[1]), item[2], item[3], item[4], color=color, fill=fill, fontsize=8.7)
    for a, b in zip(steps[:4], steps[1:4]):
        _arrow(ax, (a[0] + a[2], a[1] + 0.4), (b[0], b[1] + 0.4))
    _arrow(ax, (9.52, 5.05), (9.52, 3.70))
    for a, b in zip(steps[4:7], steps[5:8]):
        _arrow(ax, (a[0], a[1] + 0.4), (b[0] + b[2], b[1] + 0.4))
    _arrow(ax, (1.4, 2.90), (1.4, 1.75))
    _arrow(ax, (1.4, 1.75), (1.4, 5.05))

    ax.text(0.45, 1.40, "Objective 1", fontsize=9, fontweight="bold", color=NAVY)
    ax.text(0.45, 1.08, "minimize worst |b_n - target_n|", fontsize=9, color=TEXT)
    ax.text(3.80, 1.40, "Objective 2", fontsize=9, fontweight="bold", color=NAVY)
    ax.text(3.80, 1.08, "maximize minimum load-line margin", fontsize=9, color=TEXT)
    ax.text(7.10, 1.40, "Hard search constraints", fontsize=9, fontweight="bold", color=NAVY)
    ax.text(7.10, 1.08, "geometry, turn budgets, current cap", fontsize=9, color=TEXT)
    ax.text(0.45, 0.42, "Final acceptance thresholds are re-applied during final verification; the live best is one selected view of the population.", fontsize=8.8, color=TEXT)
    _save(fig, "nsga2_flow.png")


def conductor_chain_diagram() -> None:
    fig, ax = plt.subplots(figsize=(11.0, 4.0))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 4)
    ax.axis("off")
    ax.text(0.2, 3.63, "Conductor catalogue resolution and load-line calculation", fontsize=15, fontweight="bold", color=NAVY)
    labels = [
        "Selected conductor",
        "Cable geometry\n+ strand count\n+ degradation",
        "Strand diameter\n+ Cu/non-Cu",
        "Insulation\nradial + azimuthal",
        "Filament link\n-> critical fit",
    ]
    xs = [0.25, 2.30, 4.40, 6.45, 8.50]
    for x, label in zip(xs, labels, strict=True):
        _box(ax, (x, 2.22), 1.70, 0.86, label, fontsize=8.4)
    for x1, x2 in zip(xs, xs[1:]):
        _arrow(ax, (x1 + 1.70, 2.65), (x2, 2.65))
    _box(ax, (1.00, 0.55), 2.30, 0.86, "Peak field / current slope\nfrom the candidate coil", color=GREEN, fill="#edf7f0", fontsize=8.5)
    _box(ax, (4.35, 0.55), 2.30, 0.86, "Solve I = Ic(k I, T)\nby bounded bisection", color=ORANGE, fill="#fff4e6", fontsize=8.5)
    _box(ax, (7.70, 0.55), 2.30, 0.86, "Margin = 100(1 - Iop/Iss)\nper layer and per block", color=PURPLE, fill="#f5effa", fontsize=8.5)
    _arrow(ax, (2.15, 2.22), (2.15, 1.41), color=GREEN)
    _arrow(ax, (3.30, 0.98), (4.35, 0.98), color=ORANGE)
    _arrow(ax, (6.65, 0.98), (7.70, 0.98), color=PURPLE)
    _arrow(ax, (9.35, 2.22), (5.50, 1.41), color=ORANGE)
    _save(fig, "conductor_chain.png")


def pareto_diagram() -> None:
    fig, ax = plt.subplots(figsize=(8.7, 5.6))
    turns = [86, 82, 78, 77, 74, 72, 70, 69, 67, 65, 62, 60]
    harmonics = [1.1, 1.6, 2.1, 2.8, 3.6, 4.7, 5.9, 7.2, 8.9, 11.0, 13.8, 17.0]
    margins = [17, 19, 21, 23, 25, 27, 29, 31, 33, 35, 37, 39]
    scatter = ax.scatter(harmonics, margins, c=turns, s=72, cmap="viridis_r", edgecolor="white", linewidth=0.8)
    ax.plot(harmonics, margins, color="#9ca3af", lw=1.0, zorder=0)
    ax.axvline(5, color=RED, ls="--", lw=1.2, label="harmonic limit")
    ax.axhline(25, color=GREEN, ls="--", lw=1.2, label="margin target")
    ax.fill_betweenx([25, 41], 0, 5, color="#dff2e5", alpha=0.6)
    ax.text(0.4, 39.3, "acceptance box", color=GREEN, fontsize=9, fontweight="bold")
    ax.set_xlabel("Worst requested harmonic residual [units]")
    ax.set_ylabel("Minimum load-line margin [%]")
    ax.set_title("How to read the final Pareto frontier", color=NAVY, fontweight="bold")
    ax.grid(True, color=GRID, lw=0.7)
    ax.legend(loc="lower right")
    cbar = fig.colorbar(scatter, ax=ax, pad=0.02)
    cbar.set_label("Total turns (tie-break information)")
    ax.annotate("non-dominated trade-off", xy=(5.9, 29), xytext=(10.5, 25), arrowprops=dict(arrowstyle="->", color=PURPLE), color=PURPLE, fontsize=9)
    fig.tight_layout()
    _save(fig, "pareto_frontier_explained.png")


def gui_diagram() -> None:
    fig, ax = plt.subplots(figsize=(12.2, 6.7))
    ax.set_xlim(0, 12.2)
    ax.set_ylim(0, 6.7)
    ax.axis("off")
    ax.add_patch(Rectangle((0.15, 0.15), 11.9, 6.35, fc="#f7f7f7", ec="#6b7280", lw=1.1))
    ax.add_patch(Rectangle((0.15, 6.12), 11.9, 0.38, fc="#e8edf4", ec="#6b7280", lw=0.8))
    ax.text(0.40, 6.31, "DOT - Dipole Optimization Tool", va="center", fontsize=10, color=NAVY, fontweight="bold")
    _box(ax, (0.35, 5.57), 1.35, 0.35, "Load Configuration", fontsize=7.5)
    _box(ax, (1.82, 5.57), 1.35, 0.35, "Save Configuration", fontsize=7.5)
    ax.add_patch(Rectangle((0.35, 0.42), 3.15, 4.98, fc="white", ec="#9ca3af"))
    ax.text(0.55, 5.10, "Scrollable campaign parameters", fontsize=9, fontweight="bold", color=NAVY)
    groups = ["Campaign", "Magnet Physics", "Per-Layer Topology", "Geometry / Manufacturability", "Acceptance Targets", "NSGA-II Parameters", "Run Controls"]
    y = 4.67
    for group in groups:
        ax.add_patch(Rectangle((0.55, y), 2.60, 0.38, fc=LIGHT, ec="#b7c9e2"))
        ax.text(0.67, y + 0.19, group, va="center", fontsize=7.3, color=TEXT)
        y -= 0.56
    ax.add_patch(Rectangle((3.58, 0.42), 0.10, 4.98, fc="#cbd5e1", ec="#94a3b8"))
    ax.text(3.63, 2.91, "drag", rotation=90, ha="center", va="center", fontsize=7, color="#475569")

    ax.add_patch(Rectangle((3.82, 4.72), 7.95, 0.68, fc="white", ec="#9ca3af"))
    ax.text(4.02, 5.16, "Results summary and Open Results Folder", fontsize=8.2, fontweight="bold", color=NAVY)
    ax.text(4.02, 4.90, "Block Geometry | Electromagnetic Results", fontsize=7.5, color=TEXT)
    ax.add_patch(Rectangle((3.82, 0.42), 4.78, 4.12, fc="white", ec="#9ca3af"))
    ax.text(4.02, 4.27, "Live best cross-section", fontsize=9, fontweight="bold", color=NAVY)
    ax.add_patch(Circle((6.12, 2.30), 0.70, fill=False, ls="--", ec="#6b7280"))
    for angle, radius, color in [(5, 1.0, "#f58b8b"), (28, 1.35, "#f58b8b"), (52, 1.62, "#7fb0ed")]:
        x = 6.12 + radius * math.cos(math.radians(angle))
        y0 = 2.30 + radius * math.sin(math.radians(angle))
        ax.add_patch(Rectangle((x, y0), 1.10, 0.22, angle=angle, fc=color, ec="#374151", lw=0.6))
    ax.add_patch(Rectangle((8.78, 0.42), 2.99, 4.12, fc="white", ec="#9ca3af"))
    ax.text(8.98, 4.27, "Live convergence", fontsize=9, fontweight="bold", color=NAVY)
    labels = [("Margin [%]", GREEN), ("Worst residual", RED), ("Total turns", BLUE)]
    yy = [3.30, 2.15, 1.00]
    for (label, color), y0 in zip(labels, yy, strict=True):
        ax.plot([9.15, 11.45], [y0, y0], color="#d1d5db", lw=0.6)
        ax.plot([9.15, 11.45], [y0 - 0.55, y0 - 0.55], color="#d1d5db", lw=0.6)
        xs = [9.20, 9.65, 10.15, 10.70, 11.35]
        vals = [y0 - 0.42, y0 - 0.30, y0 - 0.35, y0 - 0.15, y0 - 0.08]
        ax.plot(xs, vals, color=color, lw=1.4)
        ax.text(9.00, y0 + 0.10, label, fontsize=6.8, color=TEXT)
    ax.text(0.38, 0.22, "Left: define the campaign. Right: inspect the best current design, detailed tables, and three generation trends.", fontsize=8.2, color=TEXT)
    _save(fig, "gui_overview.png")


def main() -> None:
    workflow_diagram()
    geometry_convention_diagram()
    constraints_diagram()
    nsga2_diagram()
    conductor_chain_diagram()
    pareto_diagram()
    gui_diagram()
    print(f"Wrote manual assets to {ASSETS}")


if __name__ == "__main__":
    main()

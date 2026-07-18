"""Tkinter target-synthesis application for DOT."""

from __future__ import annotations

import math
import os
import queue
import re
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from dot.acceleration import jit_status, recommended_process_workers
from dot.conductors import conservative_maximum_current_advice, parse_cadata_text
from dot.conductors.cadata import ConductorResolution, resolve_conductor
from dot.geometry import CableSpec, TurnPolygon, midplane_anchors_from_gaps
from dot.geometry.constraints import first_layer_pole_turn_clearance_mm
from dot.optimize import LayerConductorData, LayerTopology, Topology
from dot.optimize.problem import FeasibilitySettings, MarginEvaluationExclusion, OptimizationTargets
from dot.physics import field_at, place_line_current_sources
from dot.results import (
    best_candidate_index,
    block_geometry_rows,
    export_campaign_results,
    export_no_candidate_result,
    inter_block_clearance_rows,
)

from .campaign_runner import CampaignEvent, CampaignRunner
from .config_io import load_config, save_config
from .cross_section_plot import cross_section_figure
from .generation_archive import save_generation_snapshot
from .progress_tracking import format_duration
from .tooltip import attach_tooltip

# task 0057: plain-language help text for every parameter a user can type
# into this GUI, shown as a hover tooltip on its label. Grounded in DOT's
# native angle convention (phi_deg=0 at the midplane / phi_deg=90 at the pole)
# so the tooltip text
# doesn't just restate the field name.
PARAMETER_HELP: dict[str, str] = {
    "campaign_name": (
        "A label for this run, used to name saved output files (config, results). "
        "Purely descriptive -- has no effect on the physics or the search."
    ),
    "output_dir": (
        "Root folder where DOT creates one timestamped directory per campaign. It contains "
        "generation cross-section snapshots, final Pareto JSON, the best-candidate PNG, and a "
        "per-block geometry CSV table."
    ),
    "target_field_t": (
        "The magnetic flux density at the center of the aperture (bore) the coil must "
        "produce, in Tesla. DOT scales every block's current by one global factor to hit "
        "this value exactly (no-iron design: field is exactly linear in current)."
    ),
    "aperture_radius_mm": (
        "Radius (mm) of the clear bore -- the empty circular region at the magnet's center "
        "where the beam pipe goes. Every layer's inner radius must clear this plus its own "
        "geometric clearances."
    ),
    "reference_radius_mm": (
        "Radius (mm) at which normalized multipoles are specified. This is not the bore "
        "radius. A common accelerator-magnet convention is two-thirds of the aperture "
        "radius; the LHC MB uses 17 mm for its 28 mm aperture radius."
    ),
    "max_harmonic_order": (
        "Highest normal harmonic included in target synthesis. DOT controls the allowed "
        "odd dipole terms b3, b5, ... through this order; use at least 11 for accelerator "
        "dipole design."
    ),
    "n_layers": (
        "Number of radial coil layers (1-4). Each layer is one radial shell of stacked "
        "conductor blocks; a real hybrid design typically uses a higher-field conductor "
        "grade in the inner layers and a cheaper, lower-field grade in the outer layers."
    ),
    "temperature_k": (
        "Operating temperature (K) used for the critical-current / load-line-margin "
        "calculation. Typically 1.9K (superfluid helium) for Nb3Sn/NbTi accelerator magnets."
    ),
    "layer_cadata_path": (
        "Path to a .cadata file with this layer's conductor's strand/cable/critical-"
        "current-fit parameters. Required to compute load-line margin for this layer."
    ),
    "layer_conductor_name": (
        "The conductor's name as it appears in the selected .cadata file (e.g. 'CTH_HF'). "
        "Must match an entry in that file exactly."
    ),
    "layer_n_blocks": (
        "Maximum number of azimuthal blocks the search may use in this layer. Each block is "
        "a group of turns sharing one tilt angle, separated by wedges from its neighbors. "
        "More blocks give the search more freedom to shape the field and cancel unwanted "
        "harmonics, at the cost of a larger search space."
    ),
    "layer_min_blocks": (
        "Minimum active block count retained in this layer. Use at least two when wedge "
        "degrees of freedom are required for harmonic cancellation."
    ),
    "layer_turn_min": "Lower bound on how many turns of cable a single block in this layer may hold.",
    "layer_turn_max": "Upper bound on how many turns of cable a single block in this layer may hold.",
    "layer_inner_radius_mm": (
        "Fixed inner radius R (mm) for this whole layer. DOT does not optimize it. Choose "
        "successive layer radii to establish the desired radial spacing."
    ),
    "layer_phi_min_deg": (
        "Lower phi bound (degrees): phi=0deg is the midplane and phi=90deg is "
        "the pole. Smaller phi is closer to the midplane."
    ),
    "layer_phi_max_deg": (
        "Upper phi bound (degrees): phi=0deg is the midplane and phi=90deg is "
        "the pole. Larger phi is closer to the pole."
    ),
    "layer_alpha_min_deg": (
        "Internal lower search bound for the cable tilt of blocks after the user-fixed first block."
    ),
    "layer_alpha_max_deg": (
        "Internal upper search bound for the cable tilt of blocks after the user-fixed first block."
    ),
    "layer_first_block_phi_deg": (
        "Fixed phi of this layer's first (midplane) block: 0deg is the midplane and "
        "90deg is the pole. DOT keeps this value fixed and optimizes only its turns."
    ),
    "layer_first_block_alpha_deg": (
        "Fixed alpha of this layer's first (midplane) block. DOT keeps this cable-frame "
        "orientation fixed and optimizes only the block's number of turns."
    ),
    "layer_radial_gap_mm": (
        "Physical radial gap from the outer x-coordinate of the previous layer's first "
        "insulated turn. Layer 1 is fixed directly on the aperture and ignores this value."
    ),
    "layer_azimuthal_gap_mm": (
        "One-sided midplane gap in mm. DOT derives the first-block angle as "
        "atan(azimuthal gap / R); its alpha is fixed to zero."
    ),
    "layer_min_inter_block_gap_mm": (
        "Required minimum Euclidean distance (mm) between the closest points of every "
        "pair of conductor blocks in this layer. DOT checks the real insulated turn "
        "polygons, not an angular approximation; use this to reserve room for wedges or "
        "additional insulation."
    ),
    "min_gap_mm": (
        "Minimum physical clearance (mm) every turn must keep from the horizontal midplane "
        "(y=0) -- the gap between the two mirrored coil halves. A real, small manufacturing/"
        "insulation clearance, not a design safety margin."
    ),
    "min_layer_clearance_mm": (
        "Minimum radial clearance (mm) required between adjacent layers, accounting for "
        "structural and insulation material between radial shells."
    ),
    "min_inter_block_gap_mm": (
        "Legacy all-layer inter-block clearance. New GUI configurations store one explicit "
        "closest-point requirement per layer."
    ),
    "min_pole_turn_radius_mm": (
        "Layer 1 only: minimum distance (mm) from the pole symmetry axis to the closest "
        "point of any insulated cable polygon. In DOT's straight-block 2D model this is a "
        "conservative pole-turn bend-radius proxy, not a full curved-centerline calculation."
    ),
    "geometry_tolerance_mm": (
        "Numerical geometry tolerance (mm) used only to classify near-contact. It does not "
        "replace an engineering clearance requirement."
    ),
    "max_harmonic": (
        "Field-quality acceptance target: the largest allowed residual between each normal "
        "multipole and its Advanced-tab target (in units of 1e-4 of the main dipole field), "
        "evaluated at the reference radius "
        "(2/3 of the aperture radius). Lower is purer field; accelerator magnets typically "
        "target a few units."
    ),
    "harmonic_target": (
        "Desired no-iron normal harmonic in units. DOT minimizes abs(bn - target). Use a "
        "non-zero value to pre-compensate a known iron-yoke contribution; for example, if "
        "the yoke adds +3 units to b3, request b3 = -3 here."
    ),
    "min_margin": (
        "Acceptance target for the SMALLEST load-line margin found across all layers/"
        "conductors -- how far the operating current sits below each conductor's critical "
        "(quench) current, as a percentage. DOT models the coil WITHOUT iron, so this "
        "should be set conservatively (e.g. 25%) to leave headroom for the field increase "
        "iron adds in a real, later design step."
    ),
    "max_current_a": (
        "Upper bound (A) on the single global operating current DOT may use to reach the "
        "target bore field. A tighter cap forces the search to use more turns per ampere to "
        "reach the same field."
    ),
    "current_advice": (
        "Layer-1 conductor-based upper bound obtained by assuming the bore field is the "
        "Layer-1 peak field. It uses the linked fit and cadata Cu/non-Cu value. The real "
        "peak field is higher, so the actual usable current should be lower. The editable "
        "maximum-current field is never overwritten."
    ),
    "pop_size": (
        "Number of candidate designs evaluated per generation in the NSGA-II search. Larger "
        "populations explore more designs per generation, at a roughly proportional cost in "
        "time per generation."
    ),
    "n_gen": (
        "Number of generations the search runs. More generations give the search more time "
        "to refine candidates toward the acceptance targets, at a proportional time cost."
    ),
    "seed": (
        "Random seed for the search. Leave blank for a different random outcome each run; "
        "set a fixed integer for a reproducible run (same seed + same inputs = same result)."
    ),
    "pareto_search": (
        "Keep harmonic quality and load-line margin as simultaneous Pareto objectives during "
        "the global search, and apply the requested limits only during fixed-fidelity final "
        "certification. Recommended for new magnets because it preserves both trade-off branches."
    ),
    "parallel_evaluations": (
        "Optional process parallelism for independent candidate physics evaluations. DOT leaves "
        "one logical CPU free and uses at most four workers. It is off by default for maximum "
        "hardware compatibility; enable it for larger populations after comparing one short run."
    ),
}


DEFAULT_MAX_CURRENT_A = 13000.0
# Broad enough to include the published CTH-14T block inclinations. Geometry,
# not an undocumented phi/alpha correlation, decides feasibility.
DEFAULT_ALPHA_MIN_DEG = -15.0
DEFAULT_ALPHA_MAX_DEG = 75.0
DEFAULT_CAMPAIGN_NAME = "dot-campaign"
DEFAULT_OUTPUT_DIR = str(Path.cwd())

# The names deliberately describe intent instead of promising a fixed runtime:
# one evaluation can range from milliseconds to seconds as layers and blocks
# are added.  Custom preserves expert control without making population and
# generation counts the first decision a new user has to make.
NSGA2_PRESETS: dict[str, tuple[int, int] | None] = {
    "Quick exploration": (64, 40),
    "Design search (recommended)": (160, 100),
    "Intensive search": (300, 200),
    "Custom": None,
}
DEFAULT_NSGA2_PRESET = "Design search (recommended)"

DEFAULT_STATE: dict[str, Any] = {
    "geometry_angle_convention": "native-midplane-zero",
    "campaign_name": DEFAULT_CAMPAIGN_NAME,
    "output_dir": DEFAULT_OUTPUT_DIR,
    "target_bore_field_t": 0.02,
    "aperture_radius_mm": 8.0,
    "n_layers": 1,
    "temperature_k": 0.0,
    "reference_radius_mm": 5.3333333333,
    "max_harmonic_order": 11,
    "acceptance": {
        "max_harmonic_units": 5.0,
        "min_margin_percent": 10.0,
        "max_current_a": DEFAULT_MAX_CURRENT_A,
        "harmonic_targets": {},
    },
    "nsga2": {
        "preset": DEFAULT_NSGA2_PRESET,
        "pop_size": NSGA2_PRESETS[DEFAULT_NSGA2_PRESET][0],
        "n_gen": NSGA2_PRESETS[DEFAULT_NSGA2_PRESET][1],
        "seed": 7,
        "pareto_search": True,
        "parallel_evaluations": False,
    },
    "feasibility": {
        "min_gap_mm": 0.0,
        "min_layer_clearance_mm": 0.0,
        "min_inter_block_gap_mm": 0.1,
        "min_pole_turn_radius_mm": 10.0,
        "enforce_layer_nesting": True,
        "geometry_tolerance_mm": 0.005,
    },
    "layers": [
        {
            "cadata_path": "",
            "conductor_name": "",
            "n_blocks": 2,
            "min_blocks": 1,
            "turn_min": 1,
            "turn_max": 20,
            "radial_gap_mm": 0.5,
            "azimuthal_gap_mm": 0.15,
            "phi_min_deg": 0.0,
            "phi_max_deg": 90.0,
            "alpha_min_deg": DEFAULT_ALPHA_MIN_DEG,
            "alpha_max_deg": DEFAULT_ALPHA_MAX_DEG,
            "min_inter_block_gap_mm": 0.1,
        }
    ],
}


class App(tk.Tk):
    """Graphical interface for the Dipole Optimization Tool."""

    def __init__(self) -> None:
        super().__init__()
        self.title("DOT - Dipole Optimization Tool")
        self.geometry("1560x860")
        self.minsize(980, 700)

        self.runner = CampaignRunner()
        self.layer_vars: list[dict[str, tk.StringVar]] = []
        self.feasibility_settings = dict(DEFAULT_STATE["feasibility"])
        self.plot_canvas: FigureCanvasTkAgg | None = None

        self.campaign_name_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.target_field_var = tk.StringVar()
        self.aperture_var = tk.StringVar()
        self.reference_radius_var = tk.StringVar()
        self.max_harmonic_order_var = tk.StringVar()
        self.n_layers_var = tk.IntVar()
        self.temperature_var = tk.StringVar()
        self.min_gap_var = tk.StringVar()
        self.min_layer_clearance_var = tk.StringVar()
        self.min_inter_block_gap_var = tk.StringVar()
        self.min_pole_turn_radius_var = tk.StringVar()
        self.geometry_tolerance_var = tk.StringVar()
        self.enforce_layer_nesting_var = tk.BooleanVar(value=True)
        self.max_harmonic_var = tk.StringVar()
        self.min_margin_var = tk.StringVar()
        self.max_current_var = tk.StringVar()
        self.harmonic_target_vars: dict[int, tk.StringVar] = {}
        self.harmonic_targets_frame: ttk.Frame | None = None
        self.current_advice_var = tk.StringVar(value="Advice: select a Layer 1 conductor")
        self.search_preset_var = tk.StringVar(value=DEFAULT_NSGA2_PRESET)
        self.pop_size_var = tk.StringVar()
        self.n_gen_var = tk.StringVar()
        self.seed_var = tk.StringVar()
        self.pareto_search_var = tk.BooleanVar(value=True)
        self.parallel_evaluations_var = tk.BooleanVar(value=False)
        self.progress_var = tk.StringVar(value="Idle")
        self.result_var = tk.StringVar(value="No campaign has been run.")
        self.result_location_var = tk.StringVar(value="Results folder: --")
        # task 0056: live progress dashboard.
        self.elapsed_var = tk.StringVar(value="Elapsed: --:--")
        self.eta_var = tk.StringVar(value="ETA: --:--")
        self.best_summary_var = tk.StringVar(value="Best so far: --")
        self.conv_canvas: FigureCanvasTkAgg | None = None
        self.conv_fig = None
        self.conv_ax_margin = None
        self.conv_ax_harmonic = None
        self.conv_ax_turns = None
        self.conv_line_margin = None
        self.conv_line_harmonic = None
        self.conv_line_total_turns = None
        self.conv_margin_target_line = None
        self.conv_harmonic_target_line = None
        self.progress_bar: ttk.Progressbar | None = None
        self.main_paned_window: tk.PanedWindow | None = None
        self.controls_canvas: tk.Canvas | None = None
        self.block_tree: ttk.Treeview | None = None
        self.electromagnetic_tree: ttk.Treeview | None = None
        self._run_dir: Path | None = None
        self._conductor_labels: tuple[str, ...] = ()
        self._saved_generations: set[int] = set()
        self._campaign_started_at: float | None = None
        self._eta_at_event: float | None = None
        self._eta_event_time: float | None = None
        self._last_targets: OptimizationTargets | None = None

        self._build()
        self._apply_state(DEFAULT_STATE)

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=10)
        outer.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(outer)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(toolbar, text="Load Configuration", command=self._load_config).grid(
            row=0, column=0, padx=(0, 4)
        )
        ttk.Button(toolbar, text="Save Configuration", command=self._save_config).grid(
            row=0, column=1
        )

        controls_background = ttk.Style(self).lookup("TFrame", "background") or self.cget(
            "background"
        )
        main_paned_window = tk.PanedWindow(
            outer,
            orient=tk.HORIZONTAL,
            borderwidth=0,
            relief="flat",
            background=controls_background,
            sashwidth=9,
            sashrelief="raised",
            sashcursor="sb_h_double_arrow",
            showhandle=True,
            handlesize=14,
            handlepad=24,
            opaqueresize=True,
        )
        main_paned_window.grid(row=1, column=0, sticky="nsew")
        self.main_paned_window = main_paned_window

        controls_panel = ttk.Frame(main_paned_window, padding=(0, 0, 6, 0))
        controls_panel.columnconfigure(0, weight=1)
        controls_panel.rowconfigure(0, weight=1)

        controls_canvas = tk.Canvas(
            controls_panel,
            width=520,
            highlightthickness=0,
            borderwidth=0,
            background=controls_background,
        )
        controls_scroll = ttk.Scrollbar(
            controls_panel,
            orient="vertical",
            command=controls_canvas.yview,
        )
        controls_canvas.configure(yscrollcommand=controls_scroll.set)
        controls_canvas.grid(row=0, column=0, sticky="nsew")
        controls_scroll.grid(row=0, column=1, sticky="ns")

        controls = ttk.Frame(controls_canvas)
        controls.columnconfigure(0, weight=1)
        controls_window = controls_canvas.create_window(
            (0, 0),
            window=controls,
            anchor="nw",
        )
        controls.bind(
            "<Configure>",
            lambda _event: controls_canvas.configure(scrollregion=controls_canvas.bbox("all")),
        )
        controls_canvas.bind(
            "<Configure>",
            lambda event: controls_canvas.itemconfigure(
                controls_window,
                width=event.width,
            ),
        )
        self.controls_canvas = controls_canvas
        self.bind_all("<MouseWheel>", self._scroll_controls, add="+")
        self.bind_all("<Button-4>", self._scroll_controls, add="+")
        self.bind_all("<Button-5>", self._scroll_controls, add="+")
        output = ttk.Frame(main_paned_window, padding=(6, 0, 0, 0))
        output.columnconfigure(0, weight=1)
        output.columnconfigure(1, weight=1)
        output.rowconfigure(2, weight=1)
        main_paned_window.add(
            controls_panel,
            minsize=340,
            width=520,
            stretch="never",
        )
        main_paned_window.add(
            output,
            minsize=520,
            stretch="always",
        )

        self._build_campaign(controls)
        self._build_physics(controls)
        self._build_layers(controls)
        self._build_geometry(controls)
        self._build_acceptance(controls)
        self._build_nsga(controls)
        self._build_run_controls(controls)
        self._build_output(output)

    def _scroll_controls(self, event: tk.Event) -> str | None:
        """Scroll the parameter column when the pointer is over that column."""

        canvas = self.controls_canvas
        if canvas is None:
            return None
        x_root = int(getattr(event, "x_root", -1))
        y_root = int(getattr(event, "y_root", -1))
        if not (
            canvas.winfo_rootx() <= x_root < canvas.winfo_rootx() + canvas.winfo_width()
            and canvas.winfo_rooty() <= y_root < canvas.winfo_rooty() + canvas.winfo_height()
        ):
            return None
        units = _mousewheel_scroll_units(
            int(getattr(event, "delta", 0)),
            getattr(event, "num", None),
        )
        if units == 0:
            return None
        canvas.yview_scroll(units, "units")
        return "break"

    def _build_campaign(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Campaign", padding=8)
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(1, weight=1)
        self._entry(frame, "Campaign name", self.campaign_name_var, 0, "campaign_name")
        output_dir_label = ttk.Label(frame, text="Output directory")
        output_dir_label.grid(row=1, column=0, sticky="w", pady=2, padx=(0, 8))
        attach_tooltip(output_dir_label, PARAMETER_HELP["output_dir"])
        ttk.Entry(frame, textvariable=self.output_dir_var, width=18).grid(
            row=1,
            column=1,
            sticky="ew",
            pady=2,
            padx=(0, 4),
        )
        ttk.Button(frame, text="Browse", command=self._browse_output_dir).grid(
            row=1, column=2, sticky="ew", pady=2
        )

    def _build_physics(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Magnet Physics", padding=8)
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self._entry(frame, "Target bore field [T]", self.target_field_var, 0, "target_field_t")
        self._entry(frame, "Aperture radius [mm]", self.aperture_var, 1, "aperture_radius_mm")
        self._entry(
            frame, "Reference radius [mm]", self.reference_radius_var, 2, "reference_radius_mm"
        )
        self._entry(
            frame, "Max harmonic order", self.max_harmonic_order_var, 3, "max_harmonic_order"
        )
        layers_label = ttk.Label(frame, text="Layers")
        layers_label.grid(row=4, column=0, sticky="w", pady=2)
        attach_tooltip(layers_label, PARAMETER_HELP["n_layers"])
        layers = ttk.Spinbox(
            frame,
            from_=1,
            to=4,
            textvariable=self.n_layers_var,
            width=8,
            command=self._sync_layer_rows,
        )
        layers.grid(row=4, column=1, sticky="ew", pady=2)
        self.n_layers_var.trace_add("write", lambda *_: self._sync_layer_rows())
        self._entry(frame, "Temperature [K]", self.temperature_var, 5, "temperature_k")

    def _build_layers(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Per-Layer Topology", padding=8)
        frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.layers_frame = frame

    def _build_geometry(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Geometry / Manufacturability", padding=8)
        frame.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self._entry(
            frame,
            "Layer 1 min pole-turn radius [mm]",
            self.min_pole_turn_radius_var,
            0,
            "min_pole_turn_radius_mm",
        )
        self._entry(
            frame,
            "Numerical tolerance [mm]",
            self.geometry_tolerance_var,
            1,
            "geometry_tolerance_mm",
        )
        ttk.Checkbutton(
            frame,
            text="Enforce layer nesting",
            variable=self.enforce_layer_nesting_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=2)

    def _build_acceptance(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Acceptance Targets", padding=8)
        frame.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(0, weight=1)
        notebook = ttk.Notebook(frame)
        notebook.grid(row=0, column=0, sticky="ew")
        basic = ttk.Frame(notebook, padding=6)
        advanced = ttk.Frame(notebook, padding=6)
        basic.columnconfigure(1, weight=1)
        advanced.columnconfigure(0, weight=1)
        notebook.add(basic, text="General")
        notebook.add(advanced, text="Advanced harmonics")

        self._entry(
            basic,
            "Max harmonic residual [1e-4]",
            self.max_harmonic_var,
            0,
            "max_harmonic",
        )
        self._entry(basic, "Min load-line margin [%]", self.min_margin_var, 1, "min_margin")
        self._entry(basic, "Max current [A]", self.max_current_var, 2, "max_current_a")
        advice_label = ttk.Label(
            basic,
            textvariable=self.current_advice_var,
            wraplength=330,
            justify="left",
        )
        advice_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 2))
        attach_tooltip(advice_label, PARAMETER_HELP["current_advice"])
        ttk.Button(
            basic,
            text="Refresh current advice",
            command=self._update_current_advice,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 2))

        ttk.Label(
            advanced,
            text=(
                "Optional no-iron targets. DOT minimizes |bn - target|. Example: set b3 = -3 "
                "to pre-compensate a known +3-unit iron-yoke contribution."
            ),
            wraplength=410,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))
        harmonic_targets_frame = ttk.Frame(advanced)
        harmonic_targets_frame.grid(row=1, column=0, sticky="ew")
        harmonic_targets_frame.columnconfigure(1, weight=1)
        self.harmonic_targets_frame = harmonic_targets_frame
        self.max_harmonic_order_var.trace_add(
            "write", lambda *_args: self._sync_harmonic_target_rows()
        )
        self._sync_harmonic_target_rows()

    def _sync_harmonic_target_rows(self) -> None:
        frame = self.__dict__.get("harmonic_targets_frame")
        if frame is None:
            return
        try:
            max_order = int(self.max_harmonic_order_var.get())
        except (tk.TclError, ValueError):
            max_order = 11
        max_order = max(3, max_order)
        for child in frame.winfo_children():
            child.destroy()
        for row_index, order in enumerate(_allowed_normal_orders(max_order)):
            variable = self.harmonic_target_vars.setdefault(order, tk.StringVar(value="0.0"))
            label = ttk.Label(frame, text=f"b{order} target [units]")
            label.grid(row=row_index, column=0, sticky="w", pady=2, padx=(0, 8))
            attach_tooltip(label, PARAMETER_HELP["harmonic_target"])
            ttk.Entry(frame, textvariable=variable, width=18).grid(
                row=row_index,
                column=1,
                sticky="ew",
                pady=2,
            )

    def _build_nsga(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="NSGA-II Parameters", padding=8)
        frame.grid(row=5, column=0, sticky="ew", pady=(0, 8))
        preset_label = ttk.Label(frame, text="Search effort")
        preset_label.grid(row=0, column=0, sticky="w", pady=2, padx=(0, 8))
        preset = ttk.Combobox(
            frame,
            textvariable=self.search_preset_var,
            values=tuple(NSGA2_PRESETS),
            state="readonly",
            width=25,
        )
        preset.grid(row=0, column=1, sticky="ew", pady=2)
        preset.bind("<<ComboboxSelected>>", self._on_search_preset)
        self.pop_size_entry = self._entry(
            frame, "Population size", self.pop_size_var, 1, "pop_size"
        )
        self.n_gen_entry = self._entry(frame, "Generations", self.n_gen_var, 2, "n_gen")
        self._entry(frame, "Seed", self.seed_var, 3, "seed")
        pareto = ttk.Checkbutton(
            frame,
            text="Pareto search (recommended)",
            variable=self.pareto_search_var,
        )
        pareto.grid(row=4, column=0, columnspan=2, sticky="w", pady=(3, 0))
        attach_tooltip(pareto, PARAMETER_HELP["pareto_search"])
        worker_count = recommended_process_workers()
        parallel = ttk.Checkbutton(
            frame,
            text=f"Parallel candidate evaluation (auto: {worker_count} workers)",
            variable=self.parallel_evaluations_var,
            state="normal" if worker_count > 1 else "disabled",
        )
        parallel.grid(row=5, column=0, columnspan=2, sticky="w", pady=(3, 0))
        attach_tooltip(parallel, PARAMETER_HELP["parallel_evaluations"])

    def _on_search_preset(self, _event: tk.Event | None = None) -> None:
        self._apply_search_preset()

    def _apply_search_preset(self) -> None:
        name = self.search_preset_var.get()
        values = NSGA2_PRESETS.get(name)
        if name not in NSGA2_PRESETS:
            name = "Custom"
            self.search_preset_var.set(name)
            values = None
        if values is not None:
            self.pop_size_var.set(str(values[0]))
            self.n_gen_var.set(str(values[1]))
        entry_state = "normal" if values is None else "disabled"
        for entry_name in ("pop_size_entry", "n_gen_entry"):
            # ``__dict__`` also keeps the method testable on a headless App
            # shell without triggering tk.Tk's delegating ``__getattr__``.
            entry = self.__dict__.get(entry_name)
            if entry is not None:
                entry.configure(state=entry_state)

    def _build_run_controls(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Run Controls", padding=8)
        frame.grid(row=6, column=0, sticky="ew", pady=(0, 8))
        frame.columnconfigure(0, weight=1)
        buttons = ttk.Frame(frame)
        buttons.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.run_button = ttk.Button(buttons, text="Run Campaign", command=self._run_campaign)
        self.run_button.grid(row=0, column=0, padx=(0, 4))
        self.stop_button = ttk.Button(
            buttons, text="Stop", command=self._request_stop, state="disabled"
        )
        self.stop_button.grid(row=0, column=1, padx=(0, 4))
        ttk.Button(buttons, text="How to use?", command=self._show_help).grid(row=0, column=2)
        self.progress_bar = ttk.Progressbar(frame, mode="determinate", maximum=1, value=0)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        ttk.Label(frame, textvariable=self.progress_var).grid(
            row=2, column=0, sticky="w", pady=(2, 2)
        )
        # task 0056: elapsed/ETA readout, next to the progress bar's text.
        timing_row = ttk.Frame(frame)
        timing_row.grid(row=3, column=0, sticky="w", pady=(0, 2))
        ttk.Label(timing_row, textvariable=self.elapsed_var).grid(
            row=0, column=0, sticky="w", padx=(0, 12)
        )
        ttk.Label(timing_row, textvariable=self.eta_var).grid(row=0, column=1, sticky="w")
        ttk.Label(frame, textvariable=self.best_summary_var, wraplength=460, justify="left").grid(
            row=4, column=0, sticky="w", pady=(0, 4)
        )
        self.log = tk.Text(frame, width=54, height=10, wrap="word", state="disabled")
        self.log.grid(row=5, column=0, sticky="ew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.log.yview)
        scroll.grid(row=5, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

    def _build_output(self, parent: ttk.Frame) -> None:
        results = ttk.LabelFrame(parent, text="Results", padding=8)
        results.grid(row=0, column=0, columnspan=2, sticky="ew")
        results.columnconfigure(0, weight=1)
        ttk.Label(results, textvariable=self.result_var, justify="left").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(results, textvariable=self.result_location_var, justify="left").grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )
        ttk.Button(results, text="Open Results Folder", command=self._open_results_folder).grid(
            row=0, column=1, rowspan=2, sticky="e", padx=(8, 0)
        )

        self._build_result_tables(parent)

        plot = ttk.LabelFrame(parent, text="Cross-Section Plot (best candidate, live)", padding=8)
        plot.grid(row=2, column=0, sticky="nsew", pady=(8, 0), padx=(0, 4))
        plot.columnconfigure(0, weight=1)
        plot.rowconfigure(0, weight=1)
        self.plot_frame = plot

        self._build_convergence_panel(parent)

    def _build_result_tables(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        geometry_tab = ttk.Frame(notebook, padding=4)
        electromagnetic_tab = ttk.Frame(notebook, padding=4)
        notebook.add(geometry_tab, text="Block Geometry")
        notebook.add(electromagnetic_tab, text="Electromagnetic Results")
        geometry_tab.columnconfigure(0, weight=1)
        electromagnetic_tab.columnconfigure(0, weight=1)

        block_columns = (
            "layer",
            "block",
            "conductor",
            "radius",
            "turns",
            "phi",
            "alpha",
        )
        block_tree = ttk.Treeview(
            geometry_tab,
            columns=block_columns,
            show="headings",
            height=6,
        )
        headings = {
            "layer": "Layer",
            "block": "Block",
            "conductor": "Conductor",
            "radius": "R [mm]",
            "turns": "Turns",
            "phi": "phi [deg]",
            "alpha": "alpha [deg]",
        }
        for column in block_columns:
            block_tree.heading(column, text=headings[column])
            block_tree.column(
                column, width=105 if "alpha" in column or "phi" in column else 75, anchor="center"
            )
        block_tree.grid(row=0, column=0, sticky="ew")
        block_scroll = ttk.Scrollbar(geometry_tab, orient="vertical", command=block_tree.yview)
        block_scroll.grid(row=0, column=1, sticky="ns")
        block_tree.configure(yscrollcommand=block_scroll.set)
        self.block_tree = block_tree

        electromagnetic_tree = ttk.Treeview(
            electromagnetic_tab,
            columns=("category", "quantity", "value"),
            show="headings",
            height=6,
        )
        electromagnetic_tree.heading("category", text="Category")
        electromagnetic_tree.heading("quantity", text="Quantity")
        electromagnetic_tree.heading("value", text="Value")
        electromagnetic_tree.column("category", width=120, anchor="w")
        electromagnetic_tree.column("quantity", width=210, anchor="w")
        electromagnetic_tree.column("value", width=170, anchor="e")
        electromagnetic_tree.grid(row=0, column=0, sticky="ew")
        em_scroll = ttk.Scrollbar(
            electromagnetic_tab,
            orient="vertical",
            command=electromagnetic_tree.yview,
        )
        em_scroll.grid(row=0, column=1, sticky="ns")
        electromagnetic_tree.configure(yscrollcommand=em_scroll.set)
        self.electromagnetic_tree = electromagnetic_tree

    def _build_convergence_panel(self, parent: ttk.Frame) -> None:
        """Show margin, harmonics, and best-design turn counts by generation."""

        conv = ttk.LabelFrame(parent, text="Live Convergence", padding=8)
        conv.grid(row=2, column=1, sticky="nsew", pady=(8, 0), padx=(4, 0))
        conv.columnconfigure(0, weight=1)
        conv.rowconfigure(0, weight=1)

        from matplotlib.figure import Figure

        fig = Figure(figsize=(5.2, 6.0), dpi=96)
        ax_margin = fig.add_subplot(311)
        ax_harmonic = fig.add_subplot(312, sharex=ax_margin)
        ax_turns = fig.add_subplot(313, sharex=ax_margin)
        ax_margin.set_ylabel("Margin [%]")
        ax_margin.set_title("Convergence (best so far)")
        ax_harmonic.set_ylabel("Worst |bn-target|\n[units]")
        ax_turns.set_ylabel("Turns")
        ax_turns.set_xlabel("Generation")
        for axes in (ax_margin, ax_harmonic, ax_turns):
            axes.grid(True, color="#e5e7eb", linewidth=0.6)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=conv)
        canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        self.conv_fig = fig
        self.conv_ax_margin = ax_margin
        self.conv_ax_harmonic = ax_harmonic
        self.conv_ax_turns = ax_turns
        self.conv_canvas = canvas

    def _entry(
        self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int, help_key: str = ""
    ) -> ttk.Entry:
        label_widget = ttk.Label(parent, text=label)
        label_widget.grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
        if help_key:
            attach_tooltip(label_widget, PARAMETER_HELP.get(help_key, ""))
        entry = ttk.Entry(parent, textvariable=variable, width=18)
        entry.grid(row=row, column=1, sticky="ew", pady=2)
        return entry

    def _sync_layer_rows(self) -> None:
        try:
            n_layers = self._clamped_layer_count()
        except (tk.TclError, ValueError):
            return
        while len(self.layer_vars) < n_layers:
            self.layer_vars.append(self._default_layer_vars(len(self.layer_vars)))
        self.layer_vars = self.layer_vars[:n_layers]
        for child in self.layers_frame.winfo_children():
            child.destroy()
        for index, variables in enumerate(self.layer_vars):
            self._layer_row(index, variables)

    def _default_layer_vars(self, index: int) -> dict[str, tk.StringVar]:
        state = DEFAULT_STATE["layers"][0]
        variables = {
            "cadata_path": tk.StringVar(value=""),
            "conductor_name": tk.StringVar(value=str(state["conductor_name"])),
            "n_blocks": tk.StringVar(value=str(state["n_blocks"])),
            "min_blocks": tk.StringVar(value=str(state["min_blocks"])),
            "turn_min": tk.StringVar(value=str(state["turn_min"])),
            "turn_max": tk.StringVar(value=str(state["turn_max"])),
            "azimuthal_gap_mm": tk.StringVar(value=str(state["azimuthal_gap_mm"])),
            "phi_min_deg": tk.StringVar(value=str(state["phi_min_deg"])),
            "phi_max_deg": tk.StringVar(value=str(state["phi_max_deg"])),
            "alpha_min_deg": tk.StringVar(value=str(state["alpha_min_deg"])),
            "alpha_max_deg": tk.StringVar(value=str(state["alpha_max_deg"])),
            "min_inter_block_gap_mm": tk.StringVar(value=str(state["min_inter_block_gap_mm"])),
        }
        if index > 0:
            variables["radial_gap_mm"] = tk.StringVar(value=str(state["radial_gap_mm"]))
        return variables

    def _layer_row(self, index: int, variables: dict[str, tk.StringVar]) -> None:
        variables.setdefault("conductor_name", tk.StringVar(value=""))
        frame = ttk.Frame(self.layers_frame)
        frame.grid(row=index, column=0, sticky="ew", pady=(0, 8))
        cadata_label = ttk.Label(frame, text=f"Layer {index + 1}")
        cadata_label.grid(row=0, column=0, sticky="w")
        attach_tooltip(cadata_label, PARAMETER_HELP["layer_cadata_path"])
        ttk.Entry(frame, textvariable=variables["cadata_path"], width=32).grid(
            row=0, column=1, columnspan=4, sticky="ew", padx=4
        )
        ttk.Button(frame, text="Browse", command=lambda i=index: self._browse_cadata(i)).grid(
            row=0, column=5
        )
        conductor_label = ttk.Label(frame, text="Conductor name")
        conductor_label.grid(row=1, column=0, sticky="w", padx=(0, 4))
        attach_tooltip(conductor_label, PARAMETER_HELP["layer_conductor_name"])
        ttk.Entry(frame, textvariable=variables["conductor_name"], width=18).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(0, 4)
        )
        clearance_label = ttk.Label(frame, text="Min block clearance [mm]")
        clearance_label.grid(row=1, column=3, sticky="e", padx=(8, 4))
        attach_tooltip(
            clearance_label,
            PARAMETER_HELP["layer_min_inter_block_gap_mm"],
        )
        ttk.Entry(
            frame,
            textvariable=variables["min_inter_block_gap_mm"],
            width=8,
        ).grid(row=1, column=4, sticky="w", padx=(0, 4))
        labels = [
            ("Max blocks", "n_blocks"),
            ("Min blocks", "min_blocks"),
            ("Turns min", "turn_min"),
            ("Turns max", "turn_max"),
        ]
        if index > 0:
            labels.append(("Radial gap [mm]", "radial_gap_mm"))
        labels.append(("Azimuthal gap [mm]", "azimuthal_gap_mm"))
        for column, (label, key) in enumerate(labels):
            label_widget = ttk.Label(frame, text=label)
            label_widget.grid(row=2, column=column, sticky="w", padx=(0, 4))
            attach_tooltip(label_widget, PARAMETER_HELP.get(f"layer_{key}", ""))
            ttk.Entry(frame, textvariable=variables[key], width=8).grid(
                row=3, column=column, sticky="ew", padx=(0, 4)
            )

    def _update_current_advice(self) -> None:
        """Refresh the non-binding Layer-1 current recommendation."""

        if not self.layer_vars:
            self.current_advice_var.set("Advice: add Layer 1 conductor data")
            return
        layer = self.layer_vars[0]
        path = Path(layer["cadata_path"].get().strip())
        if not path.is_file():
            self.current_advice_var.set("Advice: select a valid Layer 1 .cadata file")
            return
        try:
            text = path.read_text(encoding="utf-8")
            conductor_name = layer["conductor_name"].get().strip()
            if not conductor_name:
                names = tuple(parse_cadata_text(text).conductors)
                if len(names) != 1:
                    raise ValueError("select the Layer 1 conductor name")
                conductor_name = names[0]
            resolution = resolve_conductor(text, conductor_name)
            data = _resolved_conductor_data(resolution)
            advice = conservative_maximum_current_advice(
                data.remfit,
                data.strand,
                data.cable,
                temperature_k=float(self.temperature_var.get()),
                bore_field_t=float(self.target_field_var.get()),
                desired_margin_percent=float(self.min_margin_var.get()),
            )
        except (OSError, KeyError, ValueError, tk.TclError) as exc:
            self.current_advice_var.set(f"Advice unavailable: {exc}")
            return
        self.current_advice_var.set(
            f"Layer 1 {conductor_name} / {resolution.remfit_name}: "
            "current advice <= "
            f"{advice.maximum_current_a:.0f} A "
            f"(assumed Bpeak={advice.assumed_peak_field_t:.4g} T; "
            f"short-sample field={advice.short_sample_field_t:.4g} T; "
            f"Cu/non-Cu={advice.cu_to_non_cu_ratio:.4g}; "
            f"Jc,non-Cu={advice.critical_current_density_a_per_mm2:.4g} A/mm^2; "
            f"cable non-Cu area={advice.cable_non_copper_area_mm2:.4g} mm^2; "
            f"degradation={advice.cable_degradation_percent:.4g}%)."
        )

    def _browse_cadata(self, index: int) -> None:
        path = filedialog.askopenfilename(
            title="Select .cadata file",
            filetypes=(("Cable data", "*.cadata"), ("All files", "*.*")),
        )
        if path:
            self.layer_vars[index]["cadata_path"].set(path)
            if index == 0:
                self._update_current_advice()

    def _browse_output_dir(self) -> None:
        initial_dir = self.output_dir_var.get().strip()
        options: dict[str, str] = {"title": "Select output directory"}
        if initial_dir:
            options["initialdir"] = initial_dir
        path = filedialog.askdirectory(**options)
        if path:
            self.output_dir_var.set(path)

    def _clamped_layer_count(self) -> int:
        return max(1, min(4, int(self.n_layers_var.get())))

    def _run_campaign(self) -> None:
        try:
            topology, targets, feasibility = self._campaign_inputs()
            state = self._state()
            pop_size = int(self.pop_size_var.get())
            n_gen = int(self.n_gen_var.get())
            seed_text = self.seed_var.get().strip()
            seed = int(seed_text) if seed_text else None
            parallel_enabled = bool(self.parallel_evaluations_var.get())
            n_workers = recommended_process_workers() if parallel_enabled else None
            self._run_dir = _new_run_directory(
                Path(str(state["output_dir"]).strip() or Path.cwd()),
                str(state["campaign_name"]),
            )
            save_config(state, self._run_dir / "campaign.json")
        except (OSError, ValueError, tk.TclError) as exc:
            messagebox.showerror("Invalid campaign inputs", str(exc))
            return

        max_harmonic_units = float(state["acceptance"]["max_harmonic_units"])
        if max_harmonic_units > 20.0:
            self._append_log(
                "Warning: the maximum harmonic target is "
                f"{max_harmonic_units:g} units. Accelerator-dipole campaigns normally "
                "use a few units (for example, 5); verify that this loose limit is intentional."
            )

        self._conductor_labels = tuple(
            str(layer.get("conductor_name", "")) for layer in state["layers"]
        )
        self._last_targets = targets
        self._saved_generations.clear()
        self._campaign_started_at = time.monotonic()
        self._eta_at_event = None
        self._eta_event_time = None
        self.elapsed_var.set("Elapsed: 00:00")
        self.eta_var.set("ETA: --:--")
        self.best_summary_var.set("Best so far: waiting for generation 1")
        self.result_location_var.set(f"Results folder: {self._run_dir}")
        if self.progress_bar is not None:
            self.progress_bar.configure(maximum=n_gen, value=0)
        self._clear_result_tables()
        self._append_log(f"Starting campaign. Results: {self._run_dir}")
        self._append_log(jit_status() + ".")
        self._append_log(
            f"Candidate evaluation: {n_workers} worker processes."
            if n_workers is not None and n_workers > 1
            else "Candidate evaluation: one process (parallel option off)."
        )
        self.progress_var.set("Running")
        self.result_var.set("Campaign running...")
        self.run_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.runner.start(
            topology=topology,
            targets=targets,
            feasibility=feasibility,
            pop_size=pop_size,
            n_gen=n_gen,
            seed=seed,
            n_workers=n_workers,
        )
        self.after(100, self._poll_runner)

    def _request_stop(self) -> None:
        self.runner.request_stop()

    def _show_help(self) -> None:
        """Workflow overview for a first-time user (task 0057).

        Hover any parameter's label for its specific definition; this
        dialog is the "what order do I fill things in, and what happens
        when I click Run" overview tooltips don't cover on their own.
        """

        messagebox.showinfo(
            "How to use DOT - Dipole Optimization Tool",
            "DOT searches for a superconducting dipole coil cross-section that hits your "
            "target field, field-quality, and load-line-margin targets.\n\n"
            "1. Magnet Physics: set the target bore field, aperture radius, layer count, "
            "and operating temperature.\n\n"
            "2. Per-Layer Topology: for EACH layer, point at a .cadata file with the "
            "conductor's properties; set radial and azimuthal gaps, maximum blocks, turn "
            "bounds, and block clearance. DOT derives the midplane R/phi anchor, fixes "
            "alpha=0 there, chooses its turns, and synthesizes every later block.\n\n"
            "3. Geometry / Acceptance Targets: set Layer 1's pole-turn radius proxy and the field-quality/"
            "margin/current targets a candidate must meet to be accepted. In Advanced harmonics, "
            "you can assign a signed no-iron target to each bn; for example b3=-3 compensates a "
            "known +3-unit yoke contribution. The general harmonic limit applies to |bn-target|.\n\n"
            "4. NSGA-II Parameters: population size and generation count control how "
            "thoroughly the search explores (bigger = more thorough, slower). Optional "
            "parallel candidate evaluation uses several processes; leave it off if the "
            "computer is memory-constrained.\n\n"
            "5. Click 'Run Campaign'. The Cross-Section Plot and Live Convergence chart "
            "update every generation; Elapsed/ETA estimate remaining time. When the run "
            "finishes, the Results panel shows the best candidate found (or the closest "
            "trade-off if nothing fully met your targets).\n\n"
            "Hover any parameter's label (wait briefly) to see what it means and how to "
            "set it. The upper 'Save Configuration' / 'Load Configuration' buttons let "
            "you keep or reuse a setup.",
        )

    def _poll_runner(self) -> None:
        while True:
            try:
                event = self.runner.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)
        self._update_live_clock()
        if self.runner.is_running:
            self.after(200, self._poll_runner)
        else:
            self.run_button.configure(state="normal")
            self.stop_button.configure(state="disabled")

    def _handle_event(self, event: CampaignEvent) -> None:
        self._append_log(event.message)
        if event.kind == "progress":
            if event.generation is not None and event.total_generations is not None:
                self.progress_var.set(f"Generation {event.generation}/{event.total_generations}")
                if self.progress_bar is not None:
                    self.progress_bar.configure(
                        maximum=event.total_generations,
                        value=event.generation,
                    )
            else:
                self.progress_var.set(event.message)
        elif event.kind == "generation":
            # task 0052: live best-candidate-per-generation view (dd parity).
            if event.generation is not None and event.total_generations is not None:
                status = f"Generation {event.generation}/{event.total_generations} (running)"
                if event.margin_percent is not None:
                    status += f" -- best margin so far: {event.margin_percent:.2f}%"
                self.progress_var.set(status)
                if self.progress_bar is not None:
                    self.progress_bar.configure(
                        maximum=event.total_generations,
                        value=event.generation,
                    )
            if event.design is not None:
                self._draw_plot(event.design)
                self._populate_block_table(event.design)
                self._populate_live_electromagnetic_table(event)
                self._archive_generation(event)
            # task 0056: live progress dashboard (ETA/elapsed + convergence chart).
            self.elapsed_var.set(f"Elapsed: {format_duration(event.elapsed_seconds)}")
            self.eta_var.set(f"ETA: {format_duration(event.eta_seconds)}")
            self._eta_at_event = event.eta_seconds
            self._eta_event_time = time.monotonic()
            summary_parts = []
            if event.margin_percent is not None:
                summary_parts.append(f"margin {event.margin_percent:.2f}%")
            if event.harmonic_units is not None:
                summary_parts.append(f"harmonic residual {event.harmonic_units:.2f} units")
            if event.design is not None:
                total_turns = sum(
                    block.n_turns
                    for layer in event.design.layers
                    for block in layer.blocks
                )
                summary_parts.append(f"{total_turns} turns")
            self.best_summary_var.set(
                "Best so far: " + (", ".join(summary_parts) if summary_parts else "--")
            )
            self._update_convergence_panel(event.history)
        elif event.kind == "error":
            self.progress_var.set("Failed")
            self.result_var.set(event.message)
            self._campaign_started_at = None
            messagebox.showerror("Campaign failed", event.message)
        elif event.kind == "cancelled":
            self.progress_var.set("Stopped")
            self.result_var.set(
                "Campaign stopped after the active generation. Saved generation snapshots remain available."
            )
            self._campaign_started_at = None
        elif event.kind == "result" and event.result is not None:
            self.progress_var.set("NSGA-II finished")
            if self.progress_bar is not None:
                self.progress_bar.configure(value=self.progress_bar.cget("maximum"))
            self._show_result(event.result)
            self._campaign_started_at = None

    def _show_result(self, result) -> None:  # noqa: ANN001
        output_dir = self._run_dir
        if not result.candidates:
            self.result_var.set(
                "No certified candidate met every target. See the saved near-feasible archive "
                "and generation snapshots."
            )
            if output_dir is not None:
                archive = export_no_candidate_result(
                    output_dir,
                    result,
                    campaign_name=self.campaign_name_var.get(),
                    reference_radius_mm=float(self.reference_radius_var.get()),
                    conductor_labels=self._conductor_labels,
                    max_harmonic_units=float(self.max_harmonic_var.get()),
                    min_margin_percent=float(self.min_margin_var.get()),
                )
                self.result_location_var.set(f"Results folder: {output_dir}")
                self._append_log(f"Saved diagnostic archive: {archive}")
                self._append_log(
                    f"Saved final Pareto frontier: {output_dir / 'final_pareto_frontier.png'}"
                )
                shortlist = output_dir / "best_topology_designs" / "manifest.json"
                if shortlist.exists():
                    self._append_log(f"Saved uncertified topology shortlist: {shortlist}")
            return
        best_index = best_candidate_index(
            result,
            max_harmonic_units=float(self.max_harmonic_var.get()),
            min_margin_percent=float(self.min_margin_var.get()),
        )
        candidate = result.candidates[best_index]
        achieved_field = _center_by(candidate.design)
        harmonic_units = candidate.objectives[0]
        margin_percent = -candidate.objectives[1]
        current_a = _operating_current(candidate.design)
        clearances = inter_block_clearance_rows(candidate.design)
        minimum_clearance = min(
            (row.closest_distance_mm for row in clearances),
            default=None,
        )
        pole_turn_clearance = first_layer_pole_turn_clearance_mm(candidate.design)
        meets_targets = harmonic_units <= float(
            self.max_harmonic_var.get()
        ) and margin_percent >= float(self.min_margin_var.get())
        self.result_var.set(
            "\n".join(
                (
                    f"Achieved bore field: {achieved_field:.6g} T",
                    f"Max |harmonic residual|: {harmonic_units:.6g} units of 1e-4",
                    f"Load-line margin: {margin_percent:.6g} %",
                    f"Operating current: {current_a:.6g} A",
                    "Minimum inter-block clearance: "
                    + (
                        "not applicable"
                        if minimum_clearance is None
                        else f"{minimum_clearance:.6g} mm"
                    ),
                    "Layer 1 pole-turn clearance: "
                    + (
                        "not applicable"
                        if pole_turn_clearance is None
                        else f"{pole_turn_clearance:.6g} mm"
                    ),
                    f"Acceptance: {'meets targets' if meets_targets else 'does not meet targets'}",
                    *_margin_exclusion_lines(result),
                )
            )
        )
        for line in _margin_exclusion_lines(result):
            self._append_log(line)
        self._draw_plot(candidate.design)
        self._populate_block_table(candidate.design)
        self._populate_final_electromagnetic_table(candidate, meets_targets)
        if output_dir is not None:
            artifacts = export_campaign_results(
                output_dir,
                result,
                best_index=best_index,
                campaign_name=self.campaign_name_var.get(),
                reference_radius_mm=float(self.reference_radius_var.get()),
                conductor_labels=self._conductor_labels,
                max_harmonic_units=float(self.max_harmonic_var.get()),
                min_margin_percent=float(self.min_margin_var.get()),
            )
            self.result_location_var.set(f"Results folder: {output_dir}")
            self._append_log(f"Saved final cross-section: {artifacts.cross_section_png}")
            self._append_log(f"Saved best-design summary sheet: {artifacts.summary_png}")
            self._append_log(f"Saved block geometry table: {artifacts.block_table_csv}")
            self._append_log(f"Saved Pareto archive: {artifacts.pareto_json}")
            self._append_log(f"Saved final Pareto frontier: {artifacts.pareto_frontier_png}")
            self._append_log(
                "Saved flat best-per-topology design folder: "
                f"{artifacts.selected_designs_dir}"
            )

    def _clear_result_tables(self) -> None:
        for tree in (self.block_tree, self.electromagnetic_tree):
            if tree is not None:
                tree.delete(*tree.get_children())

    def _populate_block_table(self, design) -> None:  # noqa: ANN001
        if self.block_tree is None:
            return
        self.block_tree.delete(*self.block_tree.get_children())
        for row in block_geometry_rows(design, self._conductor_labels):
            self.block_tree.insert(
                "",
                "end",
                values=(
                    row.layer,
                    row.roxie_block,
                    row.conductor,
                    f"{row.radius_mm:.6g}",
                    row.n_turns,
                    f"{row.phi_deg:.6g}",
                    f"{row.alpha_deg:.6g}",
                ),
            )

    def _populate_live_electromagnetic_table(self, event: CampaignEvent) -> None:
        if event.design is None:
            return
        rows = [
            ("Live search", "Bore field [T]", f"{abs(_center_by(event.design)):.6g}"),
            (
                "Live search",
                "Operating current [A]",
                f"{abs(_operating_current(event.design)):.6g}",
            ),
            (
                "Live search",
                "Worst harmonic residual [units]",
                "--" if event.harmonic_units is None else f"{event.harmonic_units:.6g}",
            ),
            (
                "Live search",
                "Minimum margin [%]",
                "--" if event.margin_percent is None else f"{event.margin_percent:.6g}",
            ),
        ]
        target_by_order = (
            dict(self._last_targets.harmonic_targets)
            if self._last_targets is not None
            else {}
        )
        rows.extend(
            (
                "Live harmonic",
                f"b{order}: actual / target / residual [units]",
                f"{normal:.6g} / {target_by_order.get(order, 0.0):.6g} / "
                f"{normal - target_by_order.get(order, 0.0):.6g} (a{order}={skew:.3g})",
            )
            for order, normal, skew in event.harmonics
            if order >= 3 and order % 2 == 1
        )
        rows.extend(
            (
                "Live load line",
                f"Block {record.roxie_block}: Bpeak / Iss / margin",
                f"{record.peak_field_t:.6g} T / {record.short_sample_current_a:.6g} A / "
                f"{record.margin_percent:.6g}%",
            )
            for record in event.margin_by_block
        )
        rows.extend(
            (
                "Geometry",
                f"Layer {row.layer}, blocks {row.block_a}-{row.block_b}",
                f"{row.closest_distance_mm:.6g} mm",
            )
            for row in inter_block_clearance_rows(event.design)
        )
        pole_clearance = first_layer_pole_turn_clearance_mm(event.design)
        if pole_clearance is not None:
            rows.append(
                (
                    "Geometry",
                    "Layer 1 pole-turn closest distance",
                    f"{pole_clearance:.6g} mm",
                )
            )
        self._replace_electromagnetic_rows(rows)

    def _populate_final_electromagnetic_table(self, candidate, meets_targets: bool) -> None:  # noqa: ANN001
        rows = [
            ("Certified", "Acceptance", "PASS" if meets_targets else "FAIL"),
            ("Certified", "Bore field [T]", f"{abs(_center_by(candidate.design)):.9g}"),
            (
                "Certified",
                "Operating current [A]",
                f"{abs(candidate.operating_current_a or _operating_current(candidate.design)):.9g}",
            ),
            (
                "Certified",
                "Worst harmonic residual [units]",
                f"{candidate.objectives[0]:.9g}",
            ),
            ("Certified", "Minimum margin [%]", f"{-candidate.objectives[1]:.9g}"),
        ]
        target_by_order = dict(candidate.harmonic_targets)
        rows.extend(
            (
                "Harmonic",
                f"b{order}: actual / target / residual [units]",
                f"{normal:.9g} / {target_by_order.get(order, 0.0):.9g} / "
                f"{normal - target_by_order.get(order, 0.0):.9g} (a{order}={skew:.3g})",
            )
            for order, normal, skew in candidate.harmonics
            if order >= 3 and order % 2 == 1
        )
        rows.extend(
            (
                "Load line",
                f"Layer {record.layer_index + 1}: Bpeak / Iss / margin",
                f"{record.peak_field_t:.6g} T / {record.short_sample_current_a:.6g} A / "
                f"{record.margin_percent:.6g}%",
            )
            for record in candidate.margin_by_layer
        )
        rows.extend(
            (
                "Block load line",
                f"Block {record.roxie_block}: Bpeak / Iss / margin",
                f"{record.peak_field_t:.6g} T / {record.short_sample_current_a:.6g} A / "
                f"{record.margin_percent:.6g}%",
            )
            for record in candidate.margin_by_block
        )
        rows.extend(
            (
                "Geometry",
                f"Layer {row.layer}, blocks {row.block_a}-{row.block_b}",
                f"closest clearance {row.closest_distance_mm:.9g} mm",
            )
            for row in inter_block_clearance_rows(candidate.design)
        )
        pole_clearance = first_layer_pole_turn_clearance_mm(candidate.design)
        if pole_clearance is not None:
            rows.append(
                (
                    "Geometry",
                    "Layer 1 pole-turn closest distance",
                    f"{pole_clearance:.9g} mm",
                )
            )
        self._replace_electromagnetic_rows(rows)

    def _replace_electromagnetic_rows(self, rows: list[tuple[str, str, str]]) -> None:
        if self.electromagnetic_tree is None:
            return
        self.electromagnetic_tree.delete(*self.electromagnetic_tree.get_children())
        for row in rows:
            self.electromagnetic_tree.insert("", "end", values=row)

    def _archive_generation(self, event: CampaignEvent) -> None:
        if (
            self._run_dir is None
            or event.design is None
            or event.generation is None
            or event.total_generations is None
            or event.generation in self._saved_generations
        ):
            return
        try:
            destination = save_generation_snapshot(
                self._run_dir / "generations",
                event.generation,
                event.total_generations,
                event.design,
                event.harmonic_units,
                event.margin_percent,
                abs(_operating_current(event.design)),
                block_margin_records=event.margin_by_block,
                harmonics=event.harmonics,
                harmonic_targets=(
                    self._last_targets.harmonic_targets
                    if self._last_targets is not None
                    else ()
                ),
                cable_labels=self._conductor_labels,
            )
        except (OSError, ValueError) as exc:
            self._append_log(f"Could not save generation {event.generation}: {exc}")
            return
        self._saved_generations.add(event.generation)
        self._append_log(f"Saved generation {event.generation}: {destination.name}")

    def _update_live_clock(self) -> None:
        if self._campaign_started_at is None:
            return
        now = time.monotonic()
        self.elapsed_var.set(f"Elapsed: {format_duration(now - self._campaign_started_at)}")
        if self._eta_at_event is not None and self._eta_event_time is not None:
            remaining = max(0.0, self._eta_at_event - (now - self._eta_event_time))
            self.eta_var.set(f"ETA: {format_duration(remaining)}")

    def _open_results_folder(self) -> None:
        path = self._run_dir
        if path is None:
            raw = self.output_dir_var.get().strip()
            path = Path(raw) if raw else Path.cwd()
        if not path.exists():
            messagebox.showinfo("Results folder", f"Folder does not exist yet:\n{path}")
            return
        opener = getattr(os, "startfile", None)
        if opener is None:
            messagebox.showinfo("Results folder", str(path))
            return
        try:
            opener(str(path))
        except OSError as exc:
            messagebox.showerror("Could not open results folder", str(exc))

    def _draw_plot(self, design) -> None:  # noqa: ANN001
        if self.plot_canvas is not None:
            self.plot_canvas.get_tk_widget().destroy()
        figure = cross_section_figure(design)
        self.plot_canvas = FigureCanvasTkAgg(figure, master=self.plot_frame)
        self.plot_canvas.draw()
        self.plot_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    def _update_convergence_panel(self, history: tuple) -> None:
        """Redraw margin, harmonic-residual, and total-turn trends."""

        if self.conv_ax_margin is None or not history:
            return

        generations = [record.generation for record in history]
        margins = [record.margin_percent for record in history]
        harmonics = [record.harmonic_units for record in history]
        total_turns = [record.total_turns for record in history]

        def _xy(values: list) -> tuple[list[int], list[float]]:
            pts = [(g, v) for g, v in zip(generations, values, strict=True) if v is not None]
            if not pts:
                return [], []
            xs, ys = zip(*pts)
            return list(xs), list(ys)

        margin_x, margin_y = _xy(margins)
        harmonic_x, harmonic_y = _xy(harmonics)
        total_turn_x, total_turn_y = _xy(total_turns)

        if self.conv_line_margin is None:
            (self.conv_line_margin,) = self.conv_ax_margin.plot(
                [], [], "-", color="#2980B9", linewidth=1.6
            )
            (self.conv_line_harmonic,) = self.conv_ax_harmonic.plot(
                [], [], "-", color="#C0392B", linewidth=1.6
            )
            (self.conv_line_total_turns,) = self.conv_ax_turns.plot(
                [], [], "-o", color="#111827", linewidth=1.8, markersize=3
            )
            try:
                margin_target = float(self.min_margin_var.get())
                self.conv_margin_target_line = self.conv_ax_margin.axhline(
                    margin_target, color="#888888", linestyle="--", linewidth=0.9, label="target"
                )
                self.conv_ax_margin.legend(fontsize=7, loc="lower right")
            except (tk.TclError, ValueError):
                self.conv_margin_target_line = None
            try:
                harmonic_target = float(self.max_harmonic_var.get())
                self.conv_harmonic_target_line = self.conv_ax_harmonic.axhline(
                    harmonic_target, color="#888888", linestyle="--", linewidth=0.9, label="limit"
                )
                self.conv_ax_harmonic.legend(fontsize=7, loc="upper right")
            except (tk.TclError, ValueError):
                self.conv_harmonic_target_line = None

        self.conv_line_margin.set_data(margin_x, margin_y)
        self.conv_line_harmonic.set_data(harmonic_x, harmonic_y)
        self.conv_line_total_turns.set_data(total_turn_x, total_turn_y)

        for ax in (self.conv_ax_margin, self.conv_ax_harmonic, self.conv_ax_turns):
            ax.relim()
            ax.autoscale_view()
        self.conv_ax_turns.yaxis.get_major_locator().set_params(integer=True)
        self.conv_canvas.draw_idle()

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"{message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _campaign_inputs(self) -> tuple[Topology, OptimizationTargets, FeasibilitySettings]:
        state = self._state()
        aperture = float(state["aperture_radius_mm"])
        cables: dict[str, CableSpec] = {}
        cable_ids: list[str] = []
        conductor_data: list[LayerConductorData | None] = []
        margin_exclusions: list[MarginEvaluationExclusion] = []
        for index, layer in enumerate(state["layers"]):
            cadata_path = str(layer["cadata_path"]).strip()
            path = Path(cadata_path) if cadata_path else None
            if path is None or not path.is_file():
                raise ValueError(f"Please select a .cadata file for Layer {index + 1}")
            text = path.read_text(encoding="utf-8")
            conductor_name = str(layer.get("conductor_name", "")).strip()
            cable_id = f"layer-{index + 1}"
            cable_ids.append(cable_id)
            if not conductor_name:
                records = parse_cadata_text(text)
                names = tuple(records.conductors)
                if len(names) != 1:
                    raise ValueError(
                        f"Layer {index + 1}: select an explicit CONDUCTOR name; "
                        f"catalogue contains {len(names)} conductors"
                    )
                conductor_name = names[0]
            resolution = resolve_conductor(text, conductor_name)
            if resolution.status == "not_found":
                raise ValueError(resolution.message)
            cables[cable_id] = resolution.cable_spec()
            if resolution.status == "unsupported_fit_type":
                conductor_data.append(None)
                reason = resolution.message
                margin_exclusions.append(
                    MarginEvaluationExclusion(layer_index=index, reason=reason)
                )
                self._append_log_if_ready(
                    f"Margin evaluation excluded for Layer {index + 1}: {reason}"
                )
            else:
                conductor_data.append(_resolved_conductor_data(resolution))
        anchors = midplane_anchors_from_gaps(
            aperture,
            tuple(cables[cable_id] for cable_id in cable_ids),
            tuple(float(layer["azimuthal_gap_mm"]) for layer in state["layers"]),
            tuple(float(layer["radial_gap_mm"]) for layer in state["layers"][1:]),
        )
        layer_topologies: list[LayerTopology] = []
        for index, (layer, cable_id, anchor) in enumerate(
            zip(state["layers"], cable_ids, anchors, strict=True)
        ):
            fixed_radius, first_block_phi, first_block_alpha = anchor
            layer_topologies.append(
                LayerTopology(
                    cable_id=cable_id,
                    n_blocks=int(layer["n_blocks"]),
                    min_blocks=int(layer.get("min_blocks", 1)),
                    inner_radius_bounds_mm=(fixed_radius, fixed_radius),
                    phi_bounds_deg=(float(layer["phi_min_deg"]), float(layer["phi_max_deg"])),
                    n_turns_bounds=(int(layer["turn_min"]), int(layer["turn_max"])),
                    alpha_bounds_deg=(float(layer["alpha_min_deg"]), float(layer["alpha_max_deg"])),
                    inner_radius_mm=fixed_radius,
                    first_block_phi_deg=first_block_phi,
                    first_block_alpha_deg=first_block_alpha,
                )
            )

        topology = Topology(
            aperture_radius_mm=aperture,
            layers=tuple(layer_topologies),
            cables=cables,
        )
        targets = OptimizationTargets(
            target_bore_field_t=float(state["target_bore_field_t"]),
            r_ref_mm=float(state["reference_radius_mm"]),
            max_order=int(state["max_harmonic_order"]),
            harmonic_orders=_allowed_normal_orders(int(state["max_harmonic_order"])),
            harmonic_targets=tuple(
                (order, target)
                for order, target in _state_harmonic_targets(state).items()
            ),
            cadata_by_layer=tuple(conductor_data),
            temperature_k=float(state["temperature_k"]),
            max_harmonic_units=float(state["acceptance"]["max_harmonic_units"]),
            min_margin_percent=float(state["acceptance"]["min_margin_percent"]),
            max_current_a=state["acceptance"].get("max_current_a"),
            pareto_search=bool(state["nsga2"].get("pareto_search", True)),
            excluded_margin_layers=tuple(margin_exclusions),
        )
        feasibility = FeasibilitySettings(
            min_gap_mm=0.0,
            max_angle_deg=None,
            min_layer_clearance_mm=0.0,
            min_pole_gap_mm=None,
            min_pole_turn_radius_mm=_optional_nonnegative_float(
                state["feasibility"].get("min_pole_turn_radius_mm")
            ),
            min_inter_block_gap_mm=tuple(
                _nonnegative_float(
                    layer["min_inter_block_gap_mm"],
                    f"Layer {index + 1} minimum block clearance",
                )
                for index, layer in enumerate(state["layers"])
            ),
            enforce_layer_nesting=bool(state["feasibility"].get("enforce_layer_nesting", True)),
            geometry_tolerance_mm=float(state["feasibility"].get("geometry_tolerance_mm", 0.005)),
        )
        return topology, targets, feasibility

    def _state(self) -> dict[str, Any]:
        n_layers = self._clamped_layer_count()
        parallel_var = self.__dict__.get("parallel_evaluations_var")
        harmonic_target_vars = self.__dict__.get("harmonic_target_vars", {})
        max_harmonic_order = int(self.max_harmonic_order_var.get())
        return {
            "geometry_angle_convention": "native-midplane-zero",
            "campaign_name": self.campaign_name_var.get(),
            "output_dir": self.output_dir_var.get(),
            "target_bore_field_t": float(self.target_field_var.get()),
            "aperture_radius_mm": float(self.aperture_var.get()),
            "reference_radius_mm": float(self.reference_radius_var.get()),
            "max_harmonic_order": max_harmonic_order,
            "n_layers": n_layers,
            "temperature_k": float(self.temperature_var.get()),
            "acceptance": {
                "max_harmonic_units": float(self.max_harmonic_var.get()),
                "min_margin_percent": float(self.min_margin_var.get()),
                "max_current_a": _optional_float(self.max_current_var.get()),
                "harmonic_targets": {
                    str(order): float(harmonic_target_vars[order].get())
                    for order in _allowed_normal_orders(max_harmonic_order)
                    if order in harmonic_target_vars
                },
            },
            "nsga2": {
                "preset": self.search_preset_var.get(),
                "pop_size": int(self.pop_size_var.get()),
                "n_gen": int(self.n_gen_var.get()),
                "seed": int(self.seed_var.get()) if self.seed_var.get().strip() else None,
                "pareto_search": bool(self.pareto_search_var.get()),
                "parallel_evaluations": bool(parallel_var.get()) if parallel_var else False,
            },
            "feasibility": {
                **self.feasibility_settings,
                "min_gap_mm": 0.0,
                "min_layer_clearance_mm": 0.0,
                "min_inter_block_gap_mm": tuple(
                    _nonnegative_float(
                        variables["min_inter_block_gap_mm"].get(),
                        f"Layer {index + 1} minimum block clearance",
                    )
                    for index, variables in enumerate(self.layer_vars[:n_layers])
                ),
                "min_pole_turn_radius_mm": _optional_float(self.min_pole_turn_radius_var.get()),
                "enforce_layer_nesting": bool(self.enforce_layer_nesting_var.get()),
                "geometry_tolerance_mm": float(self.geometry_tolerance_var.get()),
            },
            "layers": [
                {
                    key: _coerce_var_value(key, variable.get())
                    for key, variable in variables.items()
                    if not (index == 0 and key == "radial_gap_mm")
                }
                for index, variables in enumerate(self.layer_vars[:n_layers])
            ],
        }

    def _apply_state(self, state: dict[str, Any]) -> None:
        state = _migrate_angle_convention(state)
        state = _migrate_layer_gap_controls(state)
        self.feasibility_settings = {
            **DEFAULT_STATE["feasibility"],
            **state.get("feasibility", {}),
        }
        self.feasibility_settings.pop("max_angle_deg", None)
        self.feasibility_settings.pop("min_pole_gap_mm", None)
        self.campaign_name_var.set(str(state.get("campaign_name", DEFAULT_STATE["campaign_name"])))
        self.output_dir_var.set(str(state.get("output_dir", DEFAULT_STATE["output_dir"])))
        self.target_field_var.set(str(state["target_bore_field_t"]))
        self.aperture_var.set(str(state["aperture_radius_mm"]))
        self.reference_radius_var.set(
            str(
                state.get(
                    "reference_radius_mm",
                    _two_thirds_reference_radius(float(state["aperture_radius_mm"])),
                )
            )
        )
        self.max_harmonic_order_var.set(str(state.get("max_harmonic_order", 11)))
        self.n_layers_var.set(int(state["n_layers"]))
        self.temperature_var.set(str(state["temperature_k"]))
        self.min_gap_var.set(str(self.feasibility_settings["min_gap_mm"]))
        self.min_layer_clearance_var.set(str(self.feasibility_settings["min_layer_clearance_mm"]))
        self.min_inter_block_gap_var.set(
            _optional_float_text(
                _layerwise_feasibility_value(
                    self.feasibility_settings.get("min_inter_block_gap_mm"),
                    0,
                )
            )
        )
        self.min_pole_turn_radius_var.set(
            _optional_float_text(
                state.get("feasibility", {}).get(
                    "min_pole_turn_radius_mm",
                    state.get("feasibility", {}).get("min_pole_gap_mm", 10.0),
                )
            )
        )
        self.geometry_tolerance_var.set(
            str(self.feasibility_settings.get("geometry_tolerance_mm", 0.005))
        )
        self.enforce_layer_nesting_var.set(
            bool(self.feasibility_settings.get("enforce_layer_nesting", True))
        )
        self.max_harmonic_var.set(str(state["acceptance"]["max_harmonic_units"]))
        self.min_margin_var.set(str(state["acceptance"]["min_margin_percent"]))
        self.max_current_var.set(
            _optional_float_text(state["acceptance"].get("max_current_a", DEFAULT_MAX_CURRENT_A))
        )
        self._sync_harmonic_target_rows()
        configured_harmonic_targets = _state_harmonic_targets(state)
        harmonic_target_vars = self.__dict__.get("harmonic_target_vars", {})
        for order in _allowed_normal_orders(int(self.max_harmonic_order_var.get())):
            variable = harmonic_target_vars.get(order)
            if variable is not None:
                variable.set(str(configured_harmonic_targets.get(order, 0.0)))
        nsga2 = {**DEFAULT_STATE["nsga2"], **state.get("nsga2", {})}
        preset_name = str(nsga2.get("preset", ""))
        if preset_name not in NSGA2_PRESETS:
            requested = (int(nsga2["pop_size"]), int(nsga2["n_gen"]))
            preset_name = next(
                (name for name, values in NSGA2_PRESETS.items() if values == requested),
                "Custom",
            )
        elif NSGA2_PRESETS[preset_name] is not None and NSGA2_PRESETS[preset_name] != (
            int(nsga2["pop_size"]),
            int(nsga2["n_gen"]),
        ):
            preset_name = "Custom"
        self.search_preset_var.set(preset_name)
        self.pop_size_var.set(str(nsga2["pop_size"]))
        self.n_gen_var.set(str(nsga2["n_gen"]))
        self._apply_search_preset()
        self.seed_var.set("" if nsga2.get("seed") is None else str(nsga2["seed"]))
        self.pareto_search_var.set(bool(nsga2.get("pareto_search", True)))
        parallel_var = self.__dict__.get("parallel_evaluations_var")
        if parallel_var is not None:
            parallel_var.set(bool(nsga2.get("parallel_evaluations", False)))
        self.layer_vars = []
        for index, layer in enumerate(state["layers"]):
            merged_layer = {**DEFAULT_STATE["layers"][0], **layer}
            if index > 0:
                merged_layer["radial_gap_mm"] = float(merged_layer["radial_gap_mm"])
            if "min_inter_block_gap_mm" not in layer:
                merged_layer["min_inter_block_gap_mm"] = _layerwise_feasibility_value(
                    self.feasibility_settings.get("min_inter_block_gap_mm"),
                    index,
                )
            variables = {
                key: tk.StringVar(value=str(merged_layer[key]))
                for key in DEFAULT_STATE["layers"][0]
                if not (index == 0 and key == "radial_gap_mm")
            }
            self.layer_vars.append(variables)
        self._sync_layer_rows()
        self._update_current_advice()

    def _save_config(self) -> None:
        state = self._state()
        options: dict[str, Any] = {
            "title": "Save DOT GUI config",
            "defaultextension": ".json",
            "filetypes": (("JSON", "*.json"), ("All files", "*.*")),
            "initialfile": f"{_config_basename(state['campaign_name'])}.json",
        }
        output_dir = str(state["output_dir"]).strip()
        if output_dir:
            options["initialdir"] = output_dir
        path = filedialog.asksaveasfilename(**options)
        if path:
            save_config(state, path)
            self._append_log(f"Saved config: {path}")

    def _load_config(self) -> None:
        path = filedialog.askopenfilename(
            title="Load DOT GUI config",
            filetypes=(("JSON", "*.json"), ("All files", "*.*")),
        )
        if path:
            self._apply_state(load_config(path))
            self._append_log(f"Loaded config: {path}")

    def _append_log_if_ready(self, message: str) -> None:
        if "log" in self.__dict__:
            self._append_log(message)


def _coerce_var_value(key: str, value: str) -> str | int | float:
    if key in {"cadata_path", "conductor_name"}:
        return value
    if key in {"n_blocks", "min_blocks", "turn_min", "turn_max"}:
        return int(value)
    return float(value)


def _config_basename(campaign_name: Any) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", str(campaign_name).strip()).strip(".-")
    return safe or DEFAULT_CAMPAIGN_NAME


def _optional_float(value: str) -> float | None:
    text = value.strip()
    if not text:
        return None
    return float(text)


def _optional_float_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _resolved_conductor_data(resolution: ConductorResolution) -> LayerConductorData:
    if resolution.strand is None or resolution.cable is None or resolution.remfit is None:
        raise ValueError(
            f"CONDUCTOR record {resolution.conductor_name!r} did not resolve to margin data"
        )
    return LayerConductorData(
        strand=resolution.strand, cable=resolution.cable, remfit=resolution.remfit
    )


def _cable_spec_from_cadata_text(
    text: str,
    cable_name: str | None = None,
    *,
    conductor_name: str | None = None,
) -> CableSpec:
    records = parse_cadata_text(text)
    if conductor_name is None:
        matching = tuple(
            name
            for name, conductor in records.conductors.items()
            if cable_name is None or conductor.cable_name == cable_name
        )
        if len(matching) != 1:
            raise ValueError(
                "an explicit CONDUCTOR name is required unless exactly one linked conductor matches"
            )
        conductor_name = matching[0]
    resolution = resolve_conductor(text, conductor_name)
    if resolution.status == "not_found":
        raise ValueError(resolution.message)
    if cable_name is not None and resolution.conductor is not None:
        if resolution.conductor.cable_name != cable_name:
            raise ValueError(
                f"CONDUCTOR row {conductor_name!r} references CABLE "
                f"{resolution.conductor.cable_name!r}, not {cable_name!r}"
            )
    return resolution.cable_spec()


def _margin_exclusion_lines(result) -> tuple[str, ...]:  # noqa: ANN001
    return tuple(
        f"Margin skipped for Layer {exclusion.layer_index + 1}: {exclusion.reason}"
        for exclusion in getattr(result, "excluded_margin_layers", ())
    )


def _center_by(design) -> float:  # noqa: ANN001
    sources = tuple(
        source for turn in design.all_turns() for source in place_line_current_sources(turn)
    )
    _, by_t = field_at(sources, 0.0, 0.0)
    return by_t


def _operating_current(design) -> float:  # noqa: ANN001
    for layer in design.layers:
        for block in layer.blocks:
            return block.current_a
    return 0.0


def _r_ref_from_aperture(aperture_radius_mm: float) -> float:
    return _two_thirds_reference_radius(aperture_radius_mm)


def _two_thirds_reference_radius(aperture_radius_mm: float) -> float:
    return (2.0 / 3.0) * aperture_radius_mm


def _allowed_normal_orders(max_order: int) -> tuple[int, ...]:
    if max_order < 3:
        raise ValueError("max_harmonic_order must be at least 3")
    return tuple(range(3, max_order + 1, 2))


def _optional_nonnegative_float(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    number = float(value)
    if number < 0.0:
        raise ValueError("optional geometry gaps must be non-negative")
    return None if number == 0.0 else number


def _nonnegative_float(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return number


def _layerwise_feasibility_value(value: Any, layer_index: int) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (list, tuple)):
        if not value:
            return 0.0
        if layer_index >= len(value):
            raise ValueError("inter-block clearance list must contain one value per layer")
        return float(value[layer_index])
    return float(value)


def _migrate_angle_convention(state: dict[str, Any]) -> dict[str, Any]:
    """Convert pre-v2 GUI states into DOT's midplane-zero native angles."""

    convention = state.get("geometry_angle_convention")
    if convention in {"native-midplane-zero", "roxie"}:
        return {**state, "geometry_angle_convention": "native-midplane-zero"}
    if convention not in {None, "dot-pole-zero"}:
        raise ValueError(f"unsupported geometry_angle_convention: {convention!r}")

    migrated = {**state, "geometry_angle_convention": "native-midplane-zero"}
    migrated_layers: list[dict[str, Any]] = []
    for layer in state.get("layers", []):
        converted = dict(layer)
        old_phi_min = float(layer.get("phi_min_deg", 0.0))
        old_phi_max = float(layer.get("phi_max_deg", 90.0))
        old_alpha_min = float(layer.get("alpha_min_deg", -75.0))
        old_alpha_max = float(layer.get("alpha_max_deg", 15.0))
        converted["phi_min_deg"] = 90.0 - old_phi_max
        converted["phi_max_deg"] = 90.0 - old_phi_min
        converted["alpha_min_deg"] = -old_alpha_max
        converted["alpha_max_deg"] = -old_alpha_min
        if "first_block_phi_deg" in layer:
            converted["first_block_phi_deg"] = 90.0 - float(layer["first_block_phi_deg"])
        if "first_block_alpha_deg" in layer:
            converted["first_block_alpha_deg"] = -float(layer["first_block_alpha_deg"])
        migrated_layers.append(converted)
    migrated["layers"] = migrated_layers
    return migrated


def _migrate_layer_gap_controls(state: dict[str, Any]) -> dict[str, Any]:
    """Convert fixed first-block anchors from older GUI files into gaps.

    With a valid cadata path the radial conversion is geometry-exact: it
    subtracts the outer x coordinate of the previous layer's insulated first
    turn.  A missing catalogue already makes the campaign unrunnable, so the
    migration retains the documented 0.5 mm default in that case rather than
    inventing a cable thickness.
    """

    layers = tuple(dict(layer) for layer in state.get("layers", ()))
    if not layers:
        return state
    migrated = dict(state)
    converted_layers: list[dict[str, Any]] = []
    legacy_radii: list[float | None] = []
    legacy_phis: list[float | None] = []
    legacy_cables: list[CableSpec | None] = []
    aperture = float(state.get("aperture_radius_mm", 0.0))

    for index, layer in enumerate(layers):
        converted = dict(layer)
        legacy_radius = _legacy_anchor_radius(layer, aperture, index)
        legacy_phi = _legacy_anchor_phi(layer)
        cable = _legacy_layer_cable(layer)
        legacy_radii.append(legacy_radius)
        legacy_phis.append(legacy_phi)
        legacy_cables.append(cable)

        if "azimuthal_gap_mm" not in converted:
            if legacy_radius is not None and legacy_phi is not None:
                converted["azimuthal_gap_mm"] = max(
                    0.0,
                    legacy_radius * math.tan(math.radians(legacy_phi)),
                )
            else:
                converted["azimuthal_gap_mm"] = DEFAULT_STATE["layers"][0][
                    "azimuthal_gap_mm"
                ]

        if index == 0:
            converted["radial_gap_mm"] = 0.0
        elif "radial_gap_mm" not in converted:
            previous_radius = legacy_radii[index - 1]
            previous_phi = legacy_phis[index - 1]
            previous_cable = legacy_cables[index - 1]
            if (
                legacy_radius is not None
                and previous_radius is not None
                and previous_phi is not None
                and previous_cable is not None
            ):
                previous_turn = TurnPolygon.from_parameters(
                    inner_radius_mm=previous_radius,
                    phi_deg=previous_phi,
                    alpha_deg=0.0,
                    cable=previous_cable,
                    current_a=1.0,
                )
                converted["radial_gap_mm"] = max(
                    0.0,
                    legacy_radius - max(x for x, _y in previous_turn.corners),
                )
            else:
                converted["radial_gap_mm"] = DEFAULT_STATE["layers"][0]["radial_gap_mm"]

        for obsolete in (
            "inner_radius_mm",
            "inner_radius_min_mm",
            "inner_radius_max_mm",
            "first_block_phi_deg",
            "first_block_alpha_deg",
        ):
            converted.pop(obsolete, None)
        converted_layers.append(converted)

    migrated["layers"] = converted_layers
    return migrated


def _legacy_anchor_radius(layer: dict[str, Any], aperture: float, index: int) -> float | None:
    for key in ("inner_radius_mm", "inner_radius_min_mm"):
        value = layer.get(key)
        if value is not None and str(value).strip() != "":
            return float(value)
    return aperture if index == 0 and aperture > 0.0 else None


def _legacy_anchor_phi(layer: dict[str, Any]) -> float | None:
    value = layer.get("first_block_phi_deg")
    if value is not None and str(value).strip() != "":
        return float(value)
    return None


def _legacy_layer_cable(layer: dict[str, Any]) -> CableSpec | None:
    path_text = str(layer.get("cadata_path", "")).strip()
    conductor_name = str(layer.get("conductor_name", "")).strip()
    if not path_text or not conductor_name:
        return None
    path = Path(path_text)
    if not path.is_file():
        return None
    try:
        resolution = resolve_conductor(path.read_text(encoding="utf-8"), conductor_name)
        return resolution.cable_spec()
    except (OSError, KeyError, ValueError):
        return None


def _float_or_default(value: str, default: float) -> float:
    try:
        return float(value)
    except ValueError:
        return default


def _state_harmonic_targets(state: dict[str, Any]) -> dict[int, float]:
    """Return validated odd-normal target values from a GUI state document."""

    raw = state.get("acceptance", {}).get("harmonic_targets", {})
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("acceptance.harmonic_targets must be an object")
    allowed = set(_allowed_normal_orders(int(state.get("max_harmonic_order", 11))))
    parsed: dict[int, float] = {}
    for raw_order, raw_target in raw.items():
        text = str(raw_order).strip().lower()
        if text.startswith("b"):
            text = text[1:]
        try:
            order = int(text)
        except ValueError as exc:
            raise ValueError(f"Invalid harmonic target key {raw_order!r}") from exc
        target = float(raw_target)
        if order not in allowed or not math.isfinite(target):
            raise ValueError(
                f"Harmonic target b{order} must be an allowed odd order with a finite value"
            )
        if order in parsed:
            raise ValueError(f"Duplicate target for b{order}")
        parsed[order] = target
    return dict(sorted(parsed.items()))


def _mousewheel_scroll_units(delta: int, button_number: int | None = None) -> int:
    """Normalize Windows/macOS wheel deltas and X11 wheel buttons."""

    if button_number == 4:
        return -1
    if button_number == 5:
        return 1
    if delta == 0:
        return 0
    magnitude = max(1, int(round(abs(delta) / 120.0)))
    return -magnitude if delta > 0 else magnitude


def _new_run_directory(
    output_root: Path,
    campaign_name: str,
    *,
    timestamp: str | None = None,
) -> Path:
    """Create a collision-safe directory for one GUI campaign run."""

    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = timestamp or datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    stem = f"{_config_basename(campaign_name)}-{timestamp}"
    candidate = output_root / stem
    suffix = 2
    while candidate.exists():
        candidate = output_root / f"{stem}-{suffix}"
        suffix += 1
    candidate.mkdir()
    return candidate


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

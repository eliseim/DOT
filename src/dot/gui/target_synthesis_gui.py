"""Tkinter target-synthesis application for DOT."""

from __future__ import annotations

import math
import queue
import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from dot.conductors import CadataRecords, parse_cadata_text
from dot.conductors.cadata import ConductorResolution, resolve_conductor
from dot.geometry import CableSpec
from dot.optimize import LayerConductorData, LayerTopology, Topology
from dot.optimize.objectives import field_quality_objective
from dot.optimize.problem import FeasibilitySettings, MarginEvaluationExclusion, OptimizationTargets
from dot.physics import field_at, place_line_current_sources

from .campaign_runner import CampaignEvent, CampaignRunner
from .config_io import load_config, save_config
from .cross_section_plot import cross_section_figure

DEFAULT_STATE: dict[str, Any] = {
    "target_bore_field_t": 0.02,
    "aperture_radius_mm": 8.0,
    "n_layers": 1,
    "temperature_k": 0.0,
    "acceptance": {
        "max_harmonic_units": 1000.0,
        "min_margin_percent": 10.0,
    },
    "nsga2": {
        "pop_size": 8,
        "n_gen": 3,
        "seed": 7,
    },
    "feasibility": {
        "min_gap_mm": 0.1,
        "max_angle_deg": 80.0,
        "min_layer_clearance_mm": 0.1,
    },
    "layers": [
        {
            "cadata_path": "",
            "conductor_name": "",
            "n_blocks": 2,
            "turn_min": 1,
            "turn_max": 1,
            "inner_radius_min_mm": 20.0,
            "inner_radius_max_mm": 22.0,
            "phi_min_deg": 10.0,
            "phi_max_deg": 70.0,
        }
    ],
}


class App(tk.Tk):
    """DOT target synthesis GUI."""

    def __init__(self) -> None:
        super().__init__()
        self.title("DOT Target Synthesis")
        self.geometry("1180x820")
        self.minsize(980, 700)

        self.runner = CampaignRunner()
        self.layer_vars: list[dict[str, tk.StringVar]] = []
        self.feasibility_settings = dict(DEFAULT_STATE["feasibility"])
        self.plot_canvas: FigureCanvasTkAgg | None = None

        self.target_field_var = tk.StringVar()
        self.aperture_var = tk.StringVar()
        self.n_layers_var = tk.IntVar()
        self.temperature_var = tk.StringVar()
        self.max_harmonic_var = tk.StringVar()
        self.min_margin_var = tk.StringVar()
        self.pop_size_var = tk.StringVar()
        self.n_gen_var = tk.StringVar()
        self.seed_var = tk.StringVar()
        self.progress_var = tk.StringVar(value="Idle")
        self.result_var = tk.StringVar(value="No campaign has been run.")

        self._build()
        self._apply_state(DEFAULT_STATE)

    def _build(self) -> None:
        outer = ttk.Frame(self, padding=10)
        outer.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        controls = ttk.Frame(outer)
        controls.grid(row=0, column=0, sticky="nsw", padx=(0, 10))
        output = ttk.Frame(outer)
        output.grid(row=0, column=1, sticky="nsew")
        output.columnconfigure(0, weight=1)
        output.rowconfigure(2, weight=1)

        self._build_physics(controls)
        self._build_layers(controls)
        self._build_acceptance(controls)
        self._build_nsga(controls)
        self._build_run_controls(controls)
        self._build_output(output)

    def _build_physics(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Magnet Physics", padding=8)
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._entry(frame, "Target bore field [T]", self.target_field_var, 0)
        self._entry(frame, "Aperture radius [mm]", self.aperture_var, 1)
        ttk.Label(frame, text="Layers").grid(row=2, column=0, sticky="w", pady=2)
        layers = ttk.Spinbox(
            frame,
            from_=1,
            to=4,
            textvariable=self.n_layers_var,
            width=8,
            command=self._sync_layer_rows,
        )
        layers.grid(row=2, column=1, sticky="ew", pady=2)
        self.n_layers_var.trace_add("write", lambda *_: self._sync_layer_rows())
        self._entry(frame, "Temperature [K]", self.temperature_var, 3)

    def _build_layers(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Per-Layer Topology", padding=8)
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.layers_frame = frame

    def _build_acceptance(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Acceptance Targets", padding=8)
        frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self._entry(frame, "Max |harmonic| [1e-4]", self.max_harmonic_var, 0)
        self._entry(frame, "Min load-line margin [%]", self.min_margin_var, 1)

    def _build_nsga(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="NSGA-II Parameters", padding=8)
        frame.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        self._entry(frame, "Population size", self.pop_size_var, 0)
        self._entry(frame, "Generations", self.n_gen_var, 1)
        self._entry(frame, "Seed", self.seed_var, 2)

    def _build_run_controls(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Run Controls", padding=8)
        frame.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        buttons = ttk.Frame(frame)
        buttons.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.run_button = ttk.Button(buttons, text="Run Campaign", command=self._run_campaign)
        self.run_button.grid(row=0, column=0, padx=(0, 4))
        self.stop_button = ttk.Button(buttons, text="Stop", command=self._request_stop, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=(0, 4))
        ttk.Button(buttons, text="Save Config", command=self._save_config).grid(row=0, column=2, padx=(0, 4))
        ttk.Button(buttons, text="Load Config", command=self._load_config).grid(row=0, column=3)
        ttk.Label(frame, textvariable=self.progress_var).grid(row=1, column=0, sticky="w", pady=(8, 2))
        self.log = tk.Text(frame, width=54, height=10, wrap="word", state="disabled")
        self.log.grid(row=2, column=0, sticky="ew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.log.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

    def _build_output(self, parent: ttk.Frame) -> None:
        results = ttk.LabelFrame(parent, text="Results", padding=8)
        results.grid(row=0, column=0, sticky="ew")
        ttk.Label(results, textvariable=self.result_var, justify="left").grid(row=0, column=0, sticky="w")

        plot = ttk.LabelFrame(parent, text="Cross-Section Plot", padding=8)
        plot.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        plot.columnconfigure(0, weight=1)
        plot.rowconfigure(0, weight=1)
        self.plot_frame = plot

    def _entry(self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))
        ttk.Entry(parent, textvariable=variable, width=18).grid(row=row, column=1, sticky="ew", pady=2)

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
        aperture = _float_or_default(self.aperture_var.get(), 8.0)
        radius_min = aperture + 12.0 + index * 4.0
        state = DEFAULT_STATE["layers"][0]
        return {
            "cadata_path": tk.StringVar(value=""),
            "conductor_name": tk.StringVar(value=str(state["conductor_name"])),
            "n_blocks": tk.StringVar(value=str(state["n_blocks"])),
            "turn_min": tk.StringVar(value=str(state["turn_min"])),
            "turn_max": tk.StringVar(value=str(state["turn_max"])),
            "inner_radius_min_mm": tk.StringVar(value=f"{radius_min:.3g}"),
            "inner_radius_max_mm": tk.StringVar(value=f"{radius_min + 2.0:.3g}"),
            "phi_min_deg": tk.StringVar(value=str(state["phi_min_deg"])),
            "phi_max_deg": tk.StringVar(value=str(state["phi_max_deg"])),
        }

    def _layer_row(self, index: int, variables: dict[str, tk.StringVar]) -> None:
        variables.setdefault("conductor_name", tk.StringVar(value=""))
        frame = ttk.Frame(self.layers_frame)
        frame.grid(row=index, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(frame, text=f"Layer {index + 1}").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=variables["cadata_path"], width=32).grid(
            row=0, column=1, columnspan=4, sticky="ew", padx=4
        )
        ttk.Button(frame, text="Browse", command=lambda i=index: self._browse_cadata(i)).grid(row=0, column=5)
        ttk.Label(frame, text="Conductor name").grid(row=1, column=0, sticky="w", padx=(0, 4))
        ttk.Entry(frame, textvariable=variables["conductor_name"], width=18).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(0, 4)
        )
        labels = [
            ("Blocks", "n_blocks"),
            ("Turns min", "turn_min"),
            ("Turns max", "turn_max"),
            ("R min", "inner_radius_min_mm"),
            ("R max", "inner_radius_max_mm"),
            ("Phi min", "phi_min_deg"),
            ("Phi max", "phi_max_deg"),
        ]
        for column, (label, key) in enumerate(labels):
            ttk.Label(frame, text=label).grid(row=2, column=column, sticky="w", padx=(0, 4))
            ttk.Entry(frame, textvariable=variables[key], width=8).grid(row=3, column=column, sticky="ew", padx=(0, 4))

    def _browse_cadata(self, index: int) -> None:
        path = filedialog.askopenfilename(
            title="Select .cadata file",
            filetypes=(("ROXIE cadata", "*.cadata"), ("All files", "*.*")),
        )
        if path:
            self.layer_vars[index]["cadata_path"].set(path)

    def _clamped_layer_count(self) -> int:
        return max(1, min(4, int(self.n_layers_var.get())))

    def _run_campaign(self) -> None:
        try:
            topology, targets, feasibility = self._campaign_inputs()
            pop_size = int(self.pop_size_var.get())
            n_gen = int(self.n_gen_var.get())
            seed_text = self.seed_var.get().strip()
            seed = int(seed_text) if seed_text else None
        except (OSError, ValueError, tk.TclError) as exc:
            messagebox.showerror("Invalid campaign inputs", str(exc))
            return

        self._append_log("Starting campaign.")
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
        )
        self.after(100, self._poll_runner)

    def _request_stop(self) -> None:
        self.runner.request_stop()

    def _poll_runner(self) -> None:
        while True:
            try:
                event = self.runner.events.get_nowait()
            except queue.Empty:
                break
            self._handle_event(event)
        if self.runner.is_running:
            self.after(100, self._poll_runner)
        else:
            self.run_button.configure(state="normal")
            self.stop_button.configure(state="disabled")

    def _handle_event(self, event: CampaignEvent) -> None:
        self._append_log(event.message)
        if event.kind == "progress":
            if event.generation is not None and event.total_generations is not None:
                self.progress_var.set(f"Generation {event.generation}/{event.total_generations}")
            else:
                self.progress_var.set(event.message)
        elif event.kind == "error":
            self.progress_var.set("Failed")
            self.result_var.set(event.message)
            messagebox.showerror("Campaign failed", event.message)
        elif event.kind == "result" and event.result is not None:
            self.progress_var.set("Finished")
            self._show_result(event.result)

    def _show_result(self, result) -> None:  # noqa: ANN001
        if not result.candidates:
            self.result_var.set("No feasible candidates returned.")
            return
        candidate = _best_candidate(
            result,
            max_harmonic_units=float(self.max_harmonic_var.get()),
            min_margin_percent=float(self.min_margin_var.get()),
        )
        achieved_field = _center_by(candidate.design)
        harmonic_units = field_quality_objective(candidate.design, _r_ref(candidate.design), 4) * 1.0e4
        margin_percent = -candidate.objectives[1]
        current_a = _operating_current(candidate.design)
        meets_targets = (
            harmonic_units <= float(self.max_harmonic_var.get())
            and margin_percent >= float(self.min_margin_var.get())
        )
        self.result_var.set(
            "\n".join(
                (
                    f"Achieved bore field: {achieved_field:.6g} T",
                    f"Max |harmonic|: {harmonic_units:.6g} units of 1e-4",
                    f"Load-line margin: {margin_percent:.6g} %",
                    f"Operating current: {current_a:.6g} A",
                    f"Acceptance: {'meets targets' if meets_targets else 'does not meet targets'}",
                    *_margin_exclusion_lines(result),
                )
            )
        )
        for line in _margin_exclusion_lines(result):
            self._append_log(line)
        self._draw_plot(candidate.design)

    def _draw_plot(self, design) -> None:  # noqa: ANN001
        if self.plot_canvas is not None:
            self.plot_canvas.get_tk_widget().destroy()
        figure = cross_section_figure(design)
        self.plot_canvas = FigureCanvasTkAgg(figure, master=self.plot_frame)
        self.plot_canvas.draw()
        self.plot_canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"{message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _campaign_inputs(self) -> tuple[Topology, OptimizationTargets, FeasibilitySettings]:
        state = self._state()
        aperture = float(state["aperture_radius_mm"])
        cables: dict[str, CableSpec] = {}
        layer_topologies: list[LayerTopology] = []
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
            if conductor_name:
                resolution = resolve_conductor(text, conductor_name)
                if resolution.status == "not_found":
                    raise ValueError(resolution.message)
                if resolution.status == "unsupported_fit_type":
                    if resolution.conductor is None:
                        raise ValueError(resolution.message)
                    cables[cable_id] = _cable_spec_from_cadata_text(text, resolution.conductor.cable_name)
                    conductor_data.append(None)
                    reason = resolution.message
                    margin_exclusions.append(MarginEvaluationExclusion(layer_index=index, reason=reason))
                    self._append_log_if_ready(f"Margin evaluation excluded for Layer {index + 1}: {reason}")
                else:
                    cables[cable_id] = _cable_spec_from_cadata_text(text, _resolved_cable_name(resolution))
                    conductor_data.append(_resolved_conductor_data(resolution))
            else:
                records = parse_cadata_text(text, first_supported_remfit=True)
                cables[cable_id] = _cable_spec_from_cadata_text(text)
                conductor_data.append(_first_conductor_data(records))
            layer_topologies.append(
                LayerTopology(
                    cable_id=cable_id,
                    n_blocks=int(layer["n_blocks"]),
                    inner_radius_bounds_mm=(
                        float(layer["inner_radius_min_mm"]),
                        float(layer["inner_radius_max_mm"]),
                    ),
                    phi_bounds_deg=(float(layer["phi_min_deg"]), float(layer["phi_max_deg"])),
                    n_turns_bounds=(int(layer["turn_min"]), int(layer["turn_max"])),
                )
            )

        topology = Topology(
            aperture_radius_mm=aperture,
            layers=tuple(layer_topologies),
            cables=cables,
        )
        targets = OptimizationTargets(
            target_bore_field_t=float(state["target_bore_field_t"]),
            r_ref_mm=_r_ref_from_aperture(aperture),
            max_order=4,
            cadata_by_layer=tuple(conductor_data),
            temperature_k=float(state["temperature_k"]),
            max_harmonic_units=float(state["acceptance"]["max_harmonic_units"]),
            min_margin_percent=float(state["acceptance"]["min_margin_percent"]),
            excluded_margin_layers=tuple(margin_exclusions),
        )
        feasibility = FeasibilitySettings(
            min_gap_mm=float(state["feasibility"]["min_gap_mm"]),
            max_angle_deg=float(state["feasibility"]["max_angle_deg"]),
            min_layer_clearance_mm=float(state["feasibility"]["min_layer_clearance_mm"]),
        )
        return topology, targets, feasibility

    def _state(self) -> dict[str, Any]:
        n_layers = self._clamped_layer_count()
        return {
            "target_bore_field_t": float(self.target_field_var.get()),
            "aperture_radius_mm": float(self.aperture_var.get()),
            "n_layers": n_layers,
            "temperature_k": float(self.temperature_var.get()),
            "acceptance": {
                "max_harmonic_units": float(self.max_harmonic_var.get()),
                "min_margin_percent": float(self.min_margin_var.get()),
            },
            "nsga2": {
                "pop_size": int(self.pop_size_var.get()),
                "n_gen": int(self.n_gen_var.get()),
                "seed": int(self.seed_var.get()) if self.seed_var.get().strip() else None,
            },
            "feasibility": dict(self.feasibility_settings),
            "layers": [
                {
                    key: _coerce_var_value(key, variable.get())
                    for key, variable in variables.items()
                }
                for variables in self.layer_vars[:n_layers]
            ],
        }

    def _apply_state(self, state: dict[str, Any]) -> None:
        self.feasibility_settings = dict(state.get("feasibility", DEFAULT_STATE["feasibility"]))
        self.target_field_var.set(str(state["target_bore_field_t"]))
        self.aperture_var.set(str(state["aperture_radius_mm"]))
        self.n_layers_var.set(int(state["n_layers"]))
        self.temperature_var.set(str(state["temperature_k"]))
        self.max_harmonic_var.set(str(state["acceptance"]["max_harmonic_units"]))
        self.min_margin_var.set(str(state["acceptance"]["min_margin_percent"]))
        self.pop_size_var.set(str(state["nsga2"]["pop_size"]))
        self.n_gen_var.set(str(state["nsga2"]["n_gen"]))
        self.seed_var.set("" if state["nsga2"].get("seed") is None else str(state["nsga2"]["seed"]))
        self.layer_vars = []
        for layer in state["layers"]:
            merged_layer = {**DEFAULT_STATE["layers"][0], **layer}
            self.layer_vars.append({key: tk.StringVar(value=str(value)) for key, value in merged_layer.items()})
        self._sync_layer_rows()

    def _save_config(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save DOT GUI config",
            defaultextension=".json",
            filetypes=(("JSON", "*.json"), ("All files", "*.*")),
        )
        if path:
            save_config(self._state(), path)
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
    if key in {"n_blocks", "turn_min", "turn_max"}:
        return int(value)
    return float(value)


def _first_conductor_data(records: CadataRecords) -> LayerConductorData:
    try:
        strand = next(iter(records.strands.values()))
        cable = next(iter(records.cables.values()))
        remfit = next(iter(records.remfits.values()))
    except StopIteration as exc:
        raise ValueError(".cadata file must contain STRAND, CABLE, and REMFIT records") from exc
    return LayerConductorData(strand=strand, cable=cable, remfit=remfit)


def _resolved_conductor_data(resolution: ConductorResolution) -> LayerConductorData:
    if resolution.strand is None or resolution.cable is None or resolution.remfit is None:
        raise ValueError(f"CONDUCTOR record {resolution.conductor_name!r} did not resolve to margin data")
    return LayerConductorData(strand=resolution.strand, cable=resolution.cable, remfit=resolution.remfit)


def _resolved_cable_name(resolution: ConductorResolution) -> str:
    if resolution.conductor is None:
        raise ValueError(f"CONDUCTOR record {resolution.conductor_name!r} did not resolve to cable data")
    return resolution.conductor.cable_name


def _cable_spec_from_cadata_text(text: str, cable_name: str | None = None) -> CableSpec:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^\s*CABLE\s+(\d+)\s*$", line)
        if match is None:
            continue
        count = int(match.group(1))
        for row in lines[index + 1 : index + 1 + count]:
            tokens = re.findall(r"'[^']*'|\S+", row.strip())
            if len(tokens) >= 5 and (cable_name is None or tokens[1] == cable_name):
                height = float(tokens[2])
                width_inner = float(tokens[3])
                width_outer = float(tokens[4])
                return CableSpec(
                    width_mm=(width_inner + width_outer) / 2.0,
                    height_mm=height,
                    insulation_thickness_mm=0.0,
                )
    if cable_name is not None:
        raise ValueError(f".cadata file must contain CABLE row {cable_name!r} with dimensions")
    raise ValueError(".cadata file must contain at least one CABLE row with dimensions")


def _margin_exclusion_lines(result) -> tuple[str, ...]:  # noqa: ANN001
    return tuple(
        f"Margin skipped for Layer {exclusion.layer_index + 1}: {exclusion.reason}"
        for exclusion in getattr(result, "excluded_margin_layers", ())
    )


def _best_candidate(result, *, max_harmonic_units: float, min_margin_percent: float):  # noqa: ANN001, ANN201
    harmonic_limit = max_harmonic_units / 1.0e4
    margin_limit = min_margin_percent

    def score(candidate) -> float:  # noqa: ANN001
        harmonic = candidate.objectives[0]
        margin = -candidate.objectives[1]
        harmonic_score = harmonic / harmonic_limit if harmonic_limit > 0.0 else harmonic
        margin_score = margin_limit / margin if margin > 0.0 else math.inf
        return harmonic_score + margin_score

    return min(result.candidates, key=score)


def _center_by(design) -> float:  # noqa: ANN001
    sources = tuple(source for turn in design.all_turns() for source in place_line_current_sources(turn))
    _, by_t = field_at(sources, 0.0, 0.0)
    return by_t


def _operating_current(design) -> float:  # noqa: ANN001
    for layer in design.layers:
        for block in layer.blocks:
            return block.current_a
    return 0.0


def _r_ref(design) -> float:  # noqa: ANN001
    return _r_ref_from_aperture(design.aperture_radius_mm)


def _r_ref_from_aperture(aperture_radius_mm: float) -> float:
    return 0.625 * aperture_radius_mm


def _float_or_default(value: str, default: float) -> float:
    try:
        return float(value)
    except ValueError:
        return default


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

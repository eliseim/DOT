from __future__ import annotations

import copy
import math
import tkinter as tk
from pathlib import Path

import numpy as np
import pytest
from matplotlib.figure import Figure

from dot.conductors import resolve_conductor
from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.gui import target_synthesis_gui
from dot.gui.campaign_runner import CampaignEvent
from dot.gui.progress_tracking import GenerationRecord
from dot.optimize import LayerConductorData
from dot.optimize.problem import OptimizationTargets
from dot.optimize.runner import ParetoCandidate, ParetoResult

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CTH_CADATA = REPOSITORY_ROOT / "campaign" / "dot_cables.cadata"


class FakeVar:
    def __init__(self, value="") -> None:  # noqa: ANN001
        self.value = value

    def get(self):  # noqa: ANN201
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value

    def set(self, value) -> None:  # noqa: ANN001
        self.value = value


class FakeEntry:
    def __init__(self) -> None:
        self.state = None

    def configure(self, *, state) -> None:  # noqa: ANN001
        self.state = state


class FakeCanvas:
    def __init__(self) -> None:
        self.draws = 0

    def draw_idle(self) -> None:
        self.draws += 1


class FakeWidget:
    def __init__(self) -> None:
        self.options = {}

    def configure(self, **options) -> None:  # noqa: ANN003
        self.options.update(options)


def test_state_migrates_legacy_angle_and_gap_controls(monkeypatch) -> None:  # noqa: ANN001
    app = _app_shell()
    loaded_state = copy.deepcopy(target_synthesis_gui.DEFAULT_STATE)
    loaded_state.pop("geometry_angle_convention")
    loaded_state["feasibility"] = {
        "min_gap_mm": 0.25,
        "max_angle_deg": (65.0,),
        "min_layer_clearance_mm": 0.5,
    }
    loaded_state["feasibility"]["min_pole_gap_mm"] = 7.5
    loaded_state["layers"][0].pop("radial_gap_mm")
    loaded_state["layers"][0].pop("azimuthal_gap_mm")
    loaded_state["layers"][0]["inner_radius_mm"] = 20.0
    loaded_state["layers"][0]["first_block_phi_deg"] = 89.0
    loaded_state["layers"][0]["first_block_alpha_deg"] = 0.0
    loaded_state["layers"][0]["alpha_min_deg"] = -75.0
    loaded_state["layers"][0]["alpha_max_deg"] = 15.0

    monkeypatch.setattr(target_synthesis_gui.tk, "StringVar", FakeVar)
    monkeypatch.setattr(target_synthesis_gui.App, "_sync_layer_rows", lambda self: None)

    target_synthesis_gui.App._apply_state(app, loaded_state)

    migrated = target_synthesis_gui.App._state(app)
    assert migrated["feasibility"]["min_gap_mm"] == 0.0
    assert migrated["feasibility"]["min_layer_clearance_mm"] == 0.0
    assert "max_angle_deg" not in migrated["feasibility"]
    assert migrated["feasibility"]["min_pole_turn_radius_mm"] == pytest.approx(7.5)
    assert "radial_gap_mm" not in migrated["layers"][0]
    assert migrated["layers"][0]["azimuthal_gap_mm"] == pytest.approx(
        20.0 * math.tan(math.radians(1.0))
    )
    assert "inner_radius_mm" not in migrated["layers"][0]
    assert "first_block_phi_deg" not in migrated["layers"][0]
    assert migrated["layers"][0]["alpha_min_deg"] == pytest.approx(-15.0)
    assert migrated["layers"][0]["alpha_max_deg"] == pytest.approx(75.0)


def test_apply_state_defaults_missing_campaign_fields(monkeypatch) -> None:  # noqa: ANN001
    app = _app_shell()
    loaded_state = copy.deepcopy(target_synthesis_gui.DEFAULT_STATE)
    loaded_state.pop("campaign_name")
    loaded_state.pop("output_dir")

    monkeypatch.setattr(target_synthesis_gui.tk, "StringVar", FakeVar)
    monkeypatch.setattr(target_synthesis_gui.App, "_sync_layer_rows", lambda self: None)

    target_synthesis_gui.App._apply_state(app, loaded_state)
    state = target_synthesis_gui.App._state(app)

    assert state["campaign_name"] == target_synthesis_gui.DEFAULT_STATE["campaign_name"]
    assert state["output_dir"] == target_synthesis_gui.DEFAULT_STATE["output_dir"]


def test_state_uses_physical_layer_gaps_and_current_defaults() -> None:
    app = _app_shell()
    app.n_layers_var.set(3)
    app.layer_vars = [_layer_vars(index) for index in range(3)]
    app.layer_vars[1]["min_inter_block_gap_mm"].set("0.5")
    app.layer_vars[2]["min_inter_block_gap_mm"].set("1.0")
    app.layer_vars[1]["radial_gap_mm"].set("0.5")
    app.layer_vars[1]["azimuthal_gap_mm"].set("0.2")
    app.parallel_evaluations_var.set(True)
    app.prefer_radial_design_var.set(True)

    state = target_synthesis_gui.App._state(app)

    assert state["acceptance"]["max_current_a"] == pytest.approx(13000.0)
    assert state["acceptance"]["min_current_a"] is None
    assert state["feasibility"]["min_gap_mm"] == 0.0
    assert state["feasibility"]["min_layer_clearance_mm"] == 0.0
    assert state["feasibility"]["min_inter_block_gap_mm"] == pytest.approx((0.1, 0.5, 1.0))
    assert "max_angle_deg" not in state["feasibility"]
    assert state["layers"][1]["radial_gap_mm"] == pytest.approx(0.5)
    assert "radial_gap_mm" not in state["layers"][0]
    assert state["layers"][1]["azimuthal_gap_mm"] == pytest.approx(0.2)
    assert state["layers"][0]["alpha_min_deg"] == pytest.approx(-15.0)
    assert state["layers"][0]["alpha_max_deg"] == pytest.approx(75.0)
    assert state["nsga2"]["parallel_evaluations"] is True
    assert state["nsga2"]["prefer_radial_design"] is True


def test_gui_state_uses_equal_current_bounds_to_request_fixed_current() -> None:
    app = _app_shell()
    app.min_current_var.set("12238")
    app.max_current_var.set("12238")

    state = target_synthesis_gui.App._state(app)

    assert state["acceptance"]["min_current_a"] == pytest.approx(12238.0)
    assert state["acceptance"]["max_current_a"] == pytest.approx(12238.0)


def test_gui_defaults_to_accelerator_field_quality_target() -> None:
    assert target_synthesis_gui.DEFAULT_STATE["acceptance"]["max_harmonic_units"] == pytest.approx(
        5.0
    )


def test_gui_enables_parallel_and_radial_search_by_default() -> None:
    assert target_synthesis_gui.DEFAULT_STATE["nsga2"]["parallel_evaluations"] is True
    assert target_synthesis_gui.DEFAULT_STATE["nsga2"]["prefer_radial_design"] is True


def test_cadata_conductor_drop_down_uses_exact_catalogue_names() -> None:
    cadata = Path(__file__).resolve().parents[2] / "campaign" / "dot_cables.cadata"

    assert target_synthesis_gui._cadata_conductor_names(str(cadata)) == (
        "YELLONOU",
        "YELLONIN",
        "XF145_HFM",
        "T1",
        "T2",
        "CTH_HF",
        "CTH_LF",
    )


def test_gui_state_persists_signed_per_harmonic_targets() -> None:
    app = _app_shell()
    app.harmonic_target_vars[3].set("-3.0")
    app.harmonic_target_vars[5].set("1.25")

    state = target_synthesis_gui.App._state(app)

    assert state["acceptance"]["harmonic_targets"]["3"] == pytest.approx(-3.0)
    assert state["acceptance"]["harmonic_targets"]["5"] == pytest.approx(1.25)
    assert target_synthesis_gui._state_harmonic_targets(state) == {
        3: -3.0,
        5: 1.25,
        7: 0.0,
        9: 0.0,
        11: 0.0,
    }


def test_nsga_presets_set_effort_and_custom_unlocks_entries() -> None:
    app = _app_shell()
    app.pop_size_entry = FakeEntry()
    app.n_gen_entry = FakeEntry()

    app.search_preset_var.set("Quick exploration")
    target_synthesis_gui.App._apply_search_preset(app)
    assert (int(app.pop_size_var.get()), int(app.n_gen_var.get())) == (160, 80)
    assert app.pop_size_entry.state == "disabled"
    assert app.n_gen_entry.state == "disabled"

    app.search_preset_var.set("Custom")
    target_synthesis_gui.App._apply_search_preset(app)
    assert app.pop_size_entry.state == "normal"
    assert app.n_gen_entry.state == "normal"


def test_layer_topology_controls_use_requested_order_and_labels() -> None:
    assert target_synthesis_gui.LAYER_TOPOLOGY_FIELDS == (
        ("Min blocks", "min_blocks"),
        ("Max blocks", "n_blocks"),
        ("Min Turns", "turn_min"),
        ("Max Turns", "turn_max"),
    )


def test_finished_campaign_preserves_every_user_input(monkeypatch) -> None:  # noqa: ANN001
    app = _app_shell()
    app.campaign_name_var.set("persistent-user-campaign")
    app.output_dir_var.set("C:/user/output")
    app.target_field_var.set("12.4")
    app.aperture_var.set("25.0")
    app.auto_reference_radius_var.set(False)
    app.reference_radius_var.set("16.5")
    app.temperature_var.set("1.9")
    app.min_current_var.set("12238")
    app.max_current_var.set("12238")
    app.n_layers_var.set(2)
    app.layer_vars = [_layer_vars(0), _layer_vars(1)]
    app.layer_vars[0]["min_blocks"].set("3")
    app.layer_vars[0]["n_blocks"].set("4")
    app.layer_vars[0]["turn_min"].set("2")
    app.layer_vars[0]["turn_max"].set("25")
    app.layer_vars[1]["radial_gap_mm"].set("0.75")
    app.search_preset_var.set("Custom")
    app.pop_size_var.set("320")
    app.n_gen_var.set("175")
    app.seed_var.set("91")
    app.parallel_evaluations_var.set(True)
    before = target_synthesis_gui.App._state(app)

    app.progress_var = FakeVar("Running")
    app.result_var = FakeVar("")
    app.result_location_var = FakeVar("")
    app.progress_bar = None
    app._campaign_started_at = 1.0
    app._run_dir = None
    app._conductor_labels = ()
    monkeypatch.setattr(target_synthesis_gui.App, "_append_log", lambda self, message: None)
    monkeypatch.setattr(target_synthesis_gui.App, "_draw_plot", lambda self, design: None)
    monkeypatch.setattr(
        target_synthesis_gui.App,
        "_populate_block_table",
        lambda self, design: None,
    )
    monkeypatch.setattr(
        target_synthesis_gui.App,
        "_populate_final_electromagnetic_table",
        lambda self, candidate, meets_targets: None,
    )

    target_synthesis_gui.App._handle_event(
        app,
        CampaignEvent(
            kind="result",
            message="campaign finished",
            result=_certified_gui_result(),
        ),
    )

    assert target_synthesis_gui.App._state(app) == before
    assert app.progress_var.get() == "NSGA-II finished"


def test_reference_radius_defaults_to_rounded_two_thirds_and_remains_editable() -> None:
    app = _app_shell()
    app.reference_radius_entry = FakeEntry()

    app.aperture_var.set("25.0")
    target_synthesis_gui.App._sync_reference_radius(app)
    assert app.reference_radius_var.get() == "16.667"
    assert app.reference_radius_entry.state == "readonly"

    app.auto_reference_radius_var.set(False)
    app.reference_radius_var.set("17.0")
    app.aperture_var.set("28.0")
    target_synthesis_gui.App._sync_reference_radius(app)
    assert app.reference_radius_var.get() == "17.0"
    assert app.reference_radius_entry.state == "normal"
    assert target_synthesis_gui.App._state(app)["auto_reference_radius"] is False


def test_legacy_custom_reference_radius_is_preserved(monkeypatch) -> None:  # noqa: ANN001
    app = _app_shell()
    loaded_state = copy.deepcopy(target_synthesis_gui.DEFAULT_STATE)
    loaded_state.pop("auto_reference_radius")
    loaded_state["aperture_radius_mm"] = 28.0
    loaded_state["reference_radius_mm"] = 17.0

    monkeypatch.setattr(target_synthesis_gui.tk, "StringVar", FakeVar)
    monkeypatch.setattr(target_synthesis_gui.App, "_sync_layer_rows", lambda self: None)

    target_synthesis_gui.App._apply_state(app, loaded_state)

    assert app.auto_reference_radius_var.get() is False
    assert float(app.reference_radius_var.get()) == pytest.approx(17.0)


def test_screen_aware_initial_layout_protects_controls_and_live_plots() -> None:
    assert target_synthesis_gui._initial_window_size(1366, 768) == (1286, 688)
    assert target_synthesis_gui._initial_window_size(1920, 1080) == (1680, 1000)
    assert target_synthesis_gui._initial_controls_width(1286) == 476
    assert 700 <= 1286 - target_synthesis_gui._initial_controls_width(1286)
    assert target_synthesis_gui._initial_controls_width(1680) == 620
    assert 1000 <= 1680 - target_synthesis_gui._initial_controls_width(1680)


def test_current_advice_uses_only_linked_layer_one_fit_and_cu_non_cu() -> None:
    app = _app_shell()
    cadata = Path(__file__).resolve().parents[2] / "campaign" / "dot_cables.cadata"
    app.layer_vars = [_layer_vars(0), _layer_vars(1)]
    for layer in app.layer_vars:
        layer["cadata_path"].set(str(cadata))
    app.layer_vars[0]["conductor_name"].set("CTH_HF")
    app.layer_vars[1]["conductor_name"].set("CTH_LF")
    app.temperature_var.set("1.9")
    app.target_field_var.set("12.4")
    app.min_margin_var.set("25.0")

    target_synthesis_gui.App._update_current_advice(app)

    text = app.current_advice_var.get()
    assert "Layer 1 CTH_HF / HFM1" in text
    assert "13768 A" in text
    assert "Cu/non-Cu=0.9" in text
    assert "CTH_LF" not in text


def test_saved_gui_state_has_no_pre_run_refinement_flags() -> None:
    state = target_synthesis_gui.App._state(_app_shell())

    assert "refinement" not in state


def test_mousewheel_scroll_units_supports_windows_and_x11() -> None:
    assert target_synthesis_gui._mousewheel_scroll_units(120) == -1
    assert target_synthesis_gui._mousewheel_scroll_units(-240) == 2
    assert target_synthesis_gui._mousewheel_scroll_units(0, 4) == -1
    assert target_synthesis_gui._mousewheel_scroll_units(0, 5) == 1
    assert target_synthesis_gui._mousewheel_scroll_units(0) == 0


def test_convergence_panel_plots_only_total_turn_count() -> None:
    app = target_synthesis_gui.App.__new__(target_synthesis_gui.App)
    figure = Figure()
    app.conv_ax_margin = figure.add_subplot(311)
    app.conv_ax_harmonic = figure.add_subplot(312)
    app.conv_ax_turns = figure.add_subplot(313)
    app.conv_line_margin = None
    app.conv_line_harmonic = None
    app.conv_line_total_turns = None
    app.conv_margin_target_line = None
    app.conv_harmonic_target_line = None
    app.min_margin_var = FakeVar("25")
    app.max_harmonic_var = FakeVar("5")
    app.conv_canvas = FakeCanvas()
    history = (
        GenerationRecord(1, 2, 1.0, 20.0, 8.0, 4, 35),
        GenerationRecord(2, 2, 2.0, 25.0, 4.0, 3, 32),
    )

    target_synthesis_gui.App._update_convergence_panel(app, history)

    assert list(app.conv_line_total_turns.get_ydata()) == [35, 32]
    assert app.conv_ax_turns.get_legend_handles_labels()[1] == []
    assert app.conv_canvas.draws == 1


def test_new_campaign_replaces_previous_history_and_uses_new_target_snapshot() -> None:
    app = target_synthesis_gui.App.__new__(target_synthesis_gui.App)
    figure = Figure()
    app.conv_ax_margin = figure.add_subplot(311)
    app.conv_ax_harmonic = figure.add_subplot(312)
    app.conv_ax_turns = figure.add_subplot(313)
    app.conv_line_margin = None
    app.conv_line_harmonic = None
    app.conv_line_total_turns = None
    app.conv_margin_target_line = None
    app.conv_harmonic_target_line = None
    app.min_margin_var = FakeVar("25")
    app.max_harmonic_var = FakeVar("5")
    app.conv_canvas = FakeCanvas()

    previous_history = (GenerationRecord(1, 2, 1.0, 22.0, 7.0, 4, 35),)
    target_synthesis_gui.App._update_convergence_panel(app, previous_history)
    previous_margin_line = app.conv_line_margin

    # The validated target object is the immutable snapshot captured by the
    # Start Campaign click. Deliberately leave different values in the form to
    # prove reset does not accidentally reuse either the prior run or a later edit.
    app.min_margin_var.set("99")
    app.max_harmonic_var.set("88")
    new_targets = OptimizationTargets(
        target_bore_field_t=12.4,
        r_ref_mm=16.667,
        max_order=11,
        cadata_by_layer=(_supported_conductor_data(),),
        temperature_k=1.9,
        max_harmonic_units=3.0,
        min_margin_percent=30.0,
    )
    target_synthesis_gui.App._reset_convergence_panel(app, new_targets)

    assert previous_margin_line not in app.conv_ax_margin.lines
    assert list(app.conv_line_margin.get_xdata()) == []
    assert list(app.conv_line_margin.get_ydata()) == []
    assert list(app.conv_margin_target_line.get_ydata()) == [30.0, 30.0]
    assert list(app.conv_harmonic_target_line.get_ydata()) == [3.0, 3.0]

    new_history = (GenerationRecord(1, 2, 1.0, 28.0, 2.5, 4, 31),)
    target_synthesis_gui.App._update_convergence_panel(app, new_history)
    assert list(app.conv_line_margin.get_ydata()) == [28.0]
    assert list(app.conv_line_harmonic.get_ydata()) == [2.5]
    assert list(app.conv_line_total_turns.get_ydata()) == [31]


def test_start_campaign_resets_dashboard_with_validated_current_targets(
    monkeypatch, tmp_path
) -> None:  # noqa: ANN001
    app = _app_shell()
    targets = OptimizationTargets(
        target_bore_field_t=12.4,
        r_ref_mm=16.667,
        max_order=11,
        cadata_by_layer=(_supported_conductor_data(),),
        temperature_k=1.9,
        max_harmonic_units=4.0,
        min_margin_percent=31.0,
    )
    topology = object()
    feasibility = object()
    state = target_synthesis_gui.App._state(app)
    state["acceptance"]["max_harmonic_units"] = 4.0
    app._campaign_inputs = lambda: (topology, targets, feasibility)
    app._state = lambda: state

    resets = []
    starts = []
    app._reset_live_dashboard = resets.append
    app._clear_result_tables = lambda: None
    app._append_log = lambda _message: None
    app.elapsed_var = FakeVar()
    app.eta_var = FakeVar()
    app.best_summary_var = FakeVar()
    app.result_location_var = FakeVar()
    app.progress_var = FakeVar()
    app.result_var = FakeVar()
    app.progress_bar = FakeWidget()
    app.run_button = FakeWidget()
    app.stop_button = FakeWidget()
    app._saved_generations = {99}
    app.runner = type("FakeRunner", (), {"start": lambda _self, **kwargs: starts.append(kwargs)})()
    app._poll_runner = lambda: None
    app.after = lambda _delay, _callback: None

    monkeypatch.setattr(target_synthesis_gui, "_new_run_directory", lambda *_args: tmp_path)
    monkeypatch.setattr(target_synthesis_gui, "save_config", lambda *_args: None)
    monkeypatch.setattr(target_synthesis_gui, "_snapshot_run_inputs", lambda *_args: None)

    target_synthesis_gui.App._run_campaign(app)

    assert resets == [targets]
    assert starts[0]["targets"] is targets
    assert starts[0]["topology"] is topology
    assert starts[0]["feasibility"] is feasibility
    assert app._saved_generations == set()
    assert app.progress_bar.options == {"maximum": int(app.n_gen_var.get()), "value": 0}
    assert app.run_button.options["state"] == "disabled"
    assert app.stop_button.options["state"] == "normal"
    assert app._active_run_state == state
    assert app._active_run_state is not state


def test_finished_result_uses_start_snapshot_not_later_form_edits() -> None:
    app = _app_shell()
    snapshot = target_synthesis_gui.App._state(app)
    snapshot["campaign_name"] = "started-campaign"
    snapshot["reference_radius_mm"] = 5.333
    snapshot["acceptance"]["max_harmonic_units"] = 5.0
    snapshot["acceptance"]["min_margin_percent"] = 25.0
    app._active_run_state = snapshot
    app.campaign_name_var.set("edited-during-run")
    app.reference_radius_var.set("99")
    app.max_harmonic_var.set("999")
    app.min_margin_var.set("0")

    assert target_synthesis_gui.App._active_result_context(app) == (
        "started-campaign",
        5.333,
        5.0,
        25.0,
    )


def test_gui_run_manifest_snapshots_conductor_files_and_runtime(tmp_path) -> None:
    cadata = tmp_path / "test.cadata"
    cadata.write_text("CONDUCTOR TEST\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    state = copy.deepcopy(target_synthesis_gui.DEFAULT_STATE)
    state["n_layers"] = 1
    state["layers"][0]["cadata_path"] = str(cadata)
    state["layers"][0]["conductor_name"] = "TEST"

    targets = target_synthesis_gui.OptimizationTargets(
        target_bore_field_t=0.02,
        r_ref_mm=5.333,
        max_order=11,
        cadata_by_layer=(_supported_conductor_data(),),
        temperature_k=1.9,
    )
    manifest_path = target_synthesis_gui._snapshot_run_inputs(run_dir, state, targets)
    manifest = target_synthesis_gui.json.loads(manifest_path.read_text(encoding="utf-8"))

    snapshot = run_dir / manifest["inputs"][0]["snapshot"]
    assert snapshot.read_text(encoding="utf-8") == "CONDUCTOR TEST\n"
    assert len(manifest["inputs"][0]["sha256"]) == 64
    assert manifest["dot_version"] == "1.1.1"
    assert manifest["packages"]["numpy"]
    assert manifest["search_fidelity"]["bore_quadrature"] == "gauss-legendre"
    assert manifest["certification_fidelity"]["bore_quadrature"] == "midpoint"


def test_close_during_campaign_requests_stop_before_destroy(monkeypatch) -> None:  # noqa: ANN001
    app = target_synthesis_gui.App.__new__(target_synthesis_gui.App)
    actions = []

    class Runner:
        is_running = True

        def request_stop(self) -> None:
            actions.append("stop")
            self.is_running = False

        def join(self, timeout=None) -> None:  # noqa: ANN001
            actions.append(("join", timeout))

    app.runner = Runner()
    app.progress_var = FakeVar()
    app.run_button = FakeWidget()
    app.stop_button = FakeWidget()
    app.destroy = lambda: actions.append("destroy")
    app.after = lambda _delay, callback: callback()
    monkeypatch.setattr(target_synthesis_gui.messagebox, "askyesno", lambda *_args: True)

    target_synthesis_gui.App._on_close(app)

    assert actions == ["stop", ("join", 0.0), "destroy"]


@pytest.mark.parametrize("raw_n_layers", [0, -2])
def test_state_clamps_layer_count_to_match_visible_rows(raw_n_layers: int) -> None:
    app = _app_shell()
    app.n_layers_var.set(raw_n_layers)
    app.layer_vars = [_layer_vars(index) for index in range(2)]

    state = target_synthesis_gui.App._state(app)

    assert state["n_layers"] == 1
    assert len(state["layers"]) == 1


def test_save_config_defaults_to_campaign_output_dir(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    app = _app_shell()
    app.campaign_name_var.set("CTH Study 01")
    app.output_dir_var.set(str(tmp_path))
    captured = {}

    def fake_asksaveasfilename(**options):  # noqa: ANN001, ANN202
        captured.update(options)
        return ""

    monkeypatch.setattr(
        target_synthesis_gui.filedialog, "asksaveasfilename", fake_asksaveasfilename
    )

    target_synthesis_gui.App._save_config(app)

    assert captured["initialdir"] == str(tmp_path)
    assert captured["initialfile"] == "CTH-Study-01.json"


def test_new_run_directory_is_named_and_collision_safe(tmp_path) -> None:  # noqa: ANN001
    first = target_synthesis_gui._new_run_directory(
        tmp_path,
        "LHC MB study",
        timestamp="20260714-150000",
    )
    second = target_synthesis_gui._new_run_directory(
        tmp_path,
        "LHC MB study",
        timestamp="20260714-150000",
    )

    assert first.name == "LHC-MB-study-20260714-150000"
    assert second.name == "LHC-MB-study-20260714-150000-2"
    assert first.is_dir() and second.is_dir()


def test_run_campaign_shows_validation_dialog_for_tclerror(monkeypatch) -> None:  # noqa: ANN001
    app = target_synthesis_gui.App.__new__(target_synthesis_gui.App)
    dialogs = []

    app._campaign_inputs = lambda: (_ for _ in ()).throw(tk.TclError("invalid integer"))
    monkeypatch.setattr(
        target_synthesis_gui.messagebox,
        "showerror",
        lambda title, message: dialogs.append((title, message)),
    )

    target_synthesis_gui.App._run_campaign(app)

    assert dialogs == [("Invalid campaign inputs", "invalid integer")]


@pytest.mark.parametrize("cadata_path", ["", "missing.cadata"])
def test_campaign_inputs_requires_existing_cadata_file(cadata_path: str) -> None:
    app = target_synthesis_gui.App.__new__(target_synthesis_gui.App)
    state = copy.deepcopy(target_synthesis_gui.DEFAULT_STATE)
    state["layers"][0]["cadata_path"] = cadata_path
    app._state = lambda: state

    with pytest.raises(ValueError, match=r"Please select a \.cadata file for Layer 1"):
        target_synthesis_gui.App._campaign_inputs(app)


def test_campaign_inputs_requires_linked_conductor_instead_of_mixing_first_records(
    tmp_path,
) -> None:  # noqa: ANN001
    cadata_path = tmp_path / "mixed.cadata"
    cadata_path.write_text(
        """
REMFIT 2
  1 NB3SNA 5         3.5E+10           28           18            0            0            0            0            0            0            0            0 'PIT strand fit poor'
 11 FIT1   1           3E+09          9.2         0.57          0.9         2.32        27.04         14.5            0            0            0            0 'LHC NBTI'
STRAND 1
  3 STR01            1.065          1.6    70          1.9           10       1433.3       500.34 'MB INNER'
CABLE 1
 12 CABLE01           15.1        1.736        2.064    28          115            5 'MB INNER LAYER'
""",
        encoding="utf-8",
    )
    app = target_synthesis_gui.App.__new__(target_synthesis_gui.App)
    state = copy.deepcopy(target_synthesis_gui.DEFAULT_STATE)
    state["layers"][0]["cadata_path"] = str(cadata_path)
    app._state = lambda: state

    with pytest.raises(ValueError, match="select a supported CONDUCTOR"):
        target_synthesis_gui.App._campaign_inputs(app)


def test_dropdown_filters_and_campaign_rejects_unsupported_conductor_fit(tmp_path) -> None:  # noqa: ANN001
    cadata_path = tmp_path / "named.cadata"
    cadata_path.write_text(
        """
REMFIT 2
  1 BADFIT 3           1           1            1            1            1            1            1            0            0            0            0 'unsupported'
  2 FIT1   1        3E+09         9.2         0.57          0.9         2.32        27.04         14.5          0            0            0            0 'LHC NBTI'
STRAND 2
  1 BADSTR           0.85          0.9   150          4.4        13.54         2087          161 'HF'
  2 GOODSTR         1.065          1.2    70          1.9           10       1433.3       500.34 'LF'
CABLE 2
  1 BADCABLE          18.0          1.0          3.0    40          109            5 'HF cable'
  2 GOODCABLE         16.0          4.0          6.0    30          123            5 'LF cable'
INSUL 1
  1 INS                 0.1          0.1 'insulation'
FILAMENT 2
  1 FILHF                 6            0 BADFIT BADFIT 'unsupported filament'
  2 FILLF                 6            0 FIT1   FIT1   'supported filament'
CONDUCTOR 2
  1 HF 1 BADCABLE  BADSTR  FILHF INS OSTA QUENCH 1.9 'unsupported conductor'
  2 LF 1 GOODCABLE GOODSTR FILLF INS TRANS QUENCH 1.9 'supported conductor'
""",
        encoding="utf-8",
    )
    app = target_synthesis_gui.App.__new__(target_synthesis_gui.App)
    state = copy.deepcopy(target_synthesis_gui.DEFAULT_STATE)
    state["n_layers"] = 2
    state["layers"] = [copy.deepcopy(state["layers"][0]), copy.deepcopy(state["layers"][0])]
    state["layers"][0]["cadata_path"] = str(cadata_path)
    state["layers"][0]["conductor_name"] = "HF"
    state["layers"][1]["cadata_path"] = str(cadata_path)
    state["layers"][1]["conductor_name"] = "LF"
    state["layers"][1]["radial_gap_mm"] = 0.5
    state["layers"][1]["azimuthal_gap_mm"] = 0.2
    state["layers"][1]["min_blocks"] = 2
    state["layers"][1]["alpha_min_deg"] = -5.0
    state["layers"][1]["alpha_max_deg"] = 65.0
    state["layers"][1]["min_inter_block_gap_mm"] = 0.75
    state["acceptance"]["min_current_a"] = 12345.0
    state["acceptance"]["max_current_a"] = 12345.0
    app._state = lambda: state

    assert target_synthesis_gui._cadata_conductor_names(str(cadata_path)) == ("LF",)
    selector_app = target_synthesis_gui.App.__new__(target_synthesis_gui.App)
    selector_app.layer_vars = [
        {
            "cadata_path": FakeVar(str(cadata_path)),
            "conductor_name": FakeVar("HF"),
        }
    ]
    selector_app.conductor_widgets = [FakeWidget()]
    selector_app._update_current_advice = lambda: None
    target_synthesis_gui.App._refresh_conductor_selector(selector_app, 0)
    assert selector_app.conductor_widgets[0].options == {
        "values": ("LF",),
        "state": "readonly",
    }
    assert selector_app.layer_vars[0]["conductor_name"].get() == ""

    with pytest.raises(
        ValueError,
        match=r"Layer 1: CONDUCTOR 'HF' is not usable: unsupported REMFIT type 3",
    ):
        target_synthesis_gui.App._campaign_inputs(app)

    state["layers"][0]["conductor_name"] = "LF"
    topology, targets, feasibility = target_synthesis_gui.App._campaign_inputs(app)

    assert topology.cables["layer-1"].width_mm == pytest.approx(5.0)
    assert topology.cables["layer-2"].width_mm == pytest.approx(5.0)
    assert topology.cables["layer-1"].width_inner_mm == pytest.approx(4.0)
    assert topology.cables["layer-1"].width_outer_mm == pytest.approx(6.0)
    assert topology.cables["layer-2"].width_inner_mm == pytest.approx(4.0)
    assert topology.cables["layer-2"].width_outer_mm == pytest.approx(6.0)
    assert topology.layers[0].alpha_bounds_deg == pytest.approx((-15.0, 75.0))
    assert topology.layers[1].alpha_bounds_deg == pytest.approx((-5.0, 65.0))
    assert targets.max_current_a == pytest.approx(12345.0)
    assert targets.min_current_a == pytest.approx(12345.0)
    assert targets.fixed_current_a == pytest.approx(12345.0)
    assert feasibility.max_angle_deg is None
    expected = target_synthesis_gui.midplane_anchors_from_gaps(
        state["aperture_radius_mm"],
        (topology.cables["layer-1"], topology.cables["layer-2"]),
        (state["layers"][0]["azimuthal_gap_mm"], 0.2),
        (0.0, 0.5),
    )[1]
    assert topology.layers[1].inner_radius_mm == pytest.approx(expected[0])
    assert topology.layers[1].first_block_phi_deg == pytest.approx(expected[1])
    assert topology.layers[1].first_block_alpha_deg == pytest.approx(0.0)
    assert topology.layers[1].min_blocks == 2
    assert feasibility.min_layer_clearance_mm == pytest.approx(0.0)
    assert feasibility.min_inter_block_gap_mm == pytest.approx((0.1, 0.75))
    assert targets.cadata_by_layer[0].strand.diameter_mm == pytest.approx(1.065)
    assert targets.cadata_by_layer[1].strand.diameter_mm == pytest.approx(1.065)


def test_cable_spec_from_bundled_cth_cadata_reads_keystone_and_insulation() -> None:
    text = CTH_CADATA.read_text(encoding="utf-8")

    hf = target_synthesis_gui._cable_spec_from_cadata_text(
        text,
        "CXF150HT5",
        conductor_name="CTH_HF",
    )
    lf = target_synthesis_gui._cable_spec_from_cadata_text(
        text,
        "CTH_CERN",
        conductor_name="CTH_LF",
    )

    assert hf.width_inner_mm == pytest.approx(1.53)
    assert hf.width_outer_mm == pytest.approx(1.658)
    assert hf.insulation_radial_mm == pytest.approx(0.145)
    assert hf.insulation_azimuthal_mm == pytest.approx(0.145)
    assert lf.width_inner_mm == pytest.approx(1.736)
    assert lf.width_outer_mm == pytest.approx(2.084)
    assert lf.insulation_radial_mm == pytest.approx(0.145)
    assert lf.insulation_azimuthal_mm == pytest.approx(0.145)


def test_cable_spec_rejects_headerless_legacy_rows_instead_of_dropping_insulation() -> None:
    text = """
1 INSULATED 0.15 0.15
1 CABLE_A 15.1 1.736 2.064 28 115 5
1 CONDUCTOR_A 1 CABLE_A STRAND_A FILAMENT_A INSULATED NONE NONE 1.9
"""

    with pytest.raises(ValueError, match="CONDUCTOR record 'CONDUCTOR_A' not found"):
        target_synthesis_gui._cable_spec_from_cadata_text(
            text,
            "CABLE_A",
            conductor_name="CONDUCTOR_A",
        )


def _certified_gui_result() -> ParetoResult:
    cable = CableSpec(width_mm=1.0, height_mm=1.0, insulation_thickness_mm=0.0)
    design = DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            Layer(
                inner_radius_mm=12.0,
                blocks=(
                    Block(
                        phi_deg=20.0,
                        alpha_deg=0.0,
                        n_turns=2,
                        cable=cable,
                        inner_radius_mm=12.0,
                        current_a=500.0,
                    ),
                ),
            ),
        ),
    )
    candidate = ParetoCandidate(
        genome=np.asarray([1.0]),
        design=design,
        objectives=(1.0, -25.0),
        harmonics=((3, 1.0, 0.0),),
        operating_current_a=500.0,
        certified=True,
    )
    return ParetoResult(candidates=(candidate,))


def _app_shell():
    app = target_synthesis_gui.App.__new__(target_synthesis_gui.App)
    app.campaign_name_var = FakeVar(target_synthesis_gui.DEFAULT_STATE["campaign_name"])
    app.output_dir_var = FakeVar(target_synthesis_gui.DEFAULT_STATE["output_dir"])
    app.target_field_var = FakeVar("0.02")
    app.aperture_var = FakeVar("8.0")
    app.reference_radius_var = FakeVar(
        str(target_synthesis_gui.DEFAULT_STATE["reference_radius_mm"])
    )
    app.auto_reference_radius_var = FakeVar(
        target_synthesis_gui.DEFAULT_STATE["auto_reference_radius"]
    )
    app.max_harmonic_order_var = FakeVar(
        str(target_synthesis_gui.DEFAULT_STATE["max_harmonic_order"])
    )
    app.n_layers_var = FakeVar(1)
    app.temperature_var = FakeVar("1.9")
    app.min_gap_var = FakeVar(str(target_synthesis_gui.DEFAULT_STATE["feasibility"]["min_gap_mm"]))
    app.min_layer_clearance_var = FakeVar(
        str(target_synthesis_gui.DEFAULT_STATE["feasibility"]["min_layer_clearance_mm"])
    )
    app.min_inter_block_gap_var = FakeVar(
        str(target_synthesis_gui.DEFAULT_STATE["feasibility"]["min_inter_block_gap_mm"])
    )
    app.min_pole_turn_radius_var = FakeVar(
        str(target_synthesis_gui.DEFAULT_STATE["feasibility"]["min_pole_turn_radius_mm"])
    )
    app.geometry_tolerance_var = FakeVar(
        str(target_synthesis_gui.DEFAULT_STATE["feasibility"]["geometry_tolerance_mm"])
    )
    app.enforce_layer_nesting_var = FakeVar(
        target_synthesis_gui.DEFAULT_STATE["feasibility"]["enforce_layer_nesting"]
    )
    app.max_harmonic_var = FakeVar("1000.0")
    app.min_margin_var = FakeVar("10.0")
    app.min_current_var = FakeVar("")
    app.max_current_var = FakeVar("13000.0")
    app.harmonic_target_vars = {
        order: FakeVar("0.0")
        for order in target_synthesis_gui._allowed_normal_orders(
            int(app.max_harmonic_order_var.get())
        )
    }
    app.current_advice_var = FakeVar("")
    app.search_preset_var = FakeVar(target_synthesis_gui.DEFAULT_NSGA2_PRESET)
    app.pop_size_var = FakeVar(str(target_synthesis_gui.DEFAULT_STATE["nsga2"]["pop_size"]))
    app.n_gen_var = FakeVar(str(target_synthesis_gui.DEFAULT_STATE["nsga2"]["n_gen"]))
    app.seed_var = FakeVar("7")
    app.parallel_evaluations_var = FakeVar(False)
    app.prefer_radial_design_var = FakeVar(False)
    app.feasibility_settings = dict(target_synthesis_gui.DEFAULT_STATE["feasibility"])
    app.layer_vars = [_layer_vars(0)]
    return app


def _layer_vars(index: int) -> dict[str, FakeVar]:
    layer = copy.deepcopy(target_synthesis_gui.DEFAULT_STATE["layers"][0])
    layer["cadata_path"] = f"layer-{index + 1}.cadata"
    if index == 0:
        layer.pop("radial_gap_mm")
    return {key: FakeVar(str(value)) for key, value in layer.items()}


def _supported_conductor_data() -> LayerConductorData:
    resolution = resolve_conductor(
        CTH_CADATA.read_text(encoding="utf-8"),
        "CTH_HF",
    )
    return target_synthesis_gui._resolved_conductor_data(resolution)

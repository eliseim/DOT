from __future__ import annotations

import copy
import tkinter as tk

import pytest

from dot.gui import target_synthesis_gui


class FakeVar:
    def __init__(self, value="") -> None:  # noqa: ANN001
        self.value = value

    def get(self):  # noqa: ANN201
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value

    def set(self, value) -> None:  # noqa: ANN001
        self.value = value


def test_state_round_trips_loaded_feasibility(monkeypatch) -> None:  # noqa: ANN001
    app = _app_shell()
    loaded_state = copy.deepcopy(target_synthesis_gui.DEFAULT_STATE)
    loaded_state["feasibility"] = {
        "min_gap_mm": 0.25,
        "max_angle_deg": (65.0,),
        "min_layer_clearance_mm": 0.5,
    }
    loaded_state["layers"][0]["max_angle_deg"] = 65.0

    monkeypatch.setattr(target_synthesis_gui.tk, "StringVar", FakeVar)
    monkeypatch.setattr(target_synthesis_gui.App, "_sync_layer_rows", lambda self: None)

    target_synthesis_gui.App._apply_state(app, loaded_state)

    assert target_synthesis_gui.App._state(app)["feasibility"] == loaded_state["feasibility"]


def test_state_uses_per_layer_angle_and_current_defaults() -> None:
    app = _app_shell()
    app.n_layers_var.set(3)
    app.layer_vars = [_layer_vars(index) for index in range(3)]

    state = target_synthesis_gui.App._state(app)

    assert state["acceptance"]["max_current_a"] == pytest.approx(13000.0)
    assert state["feasibility"]["max_angle_deg"] == (80.0, 85.0, 85.0)


@pytest.mark.parametrize("raw_n_layers", [0, -2])
def test_state_clamps_layer_count_to_match_visible_rows(raw_n_layers: int) -> None:
    app = _app_shell()
    app.n_layers_var.set(raw_n_layers)
    app.layer_vars = [_layer_vars(index) for index in range(2)]

    state = target_synthesis_gui.App._state(app)

    assert state["n_layers"] == 1
    assert len(state["layers"]) == 1


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


def test_campaign_inputs_uses_first_supported_remfit(tmp_path) -> None:  # noqa: ANN001
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

    topology, targets, _ = target_synthesis_gui.App._campaign_inputs(app)

    assert topology.cables["layer-1"].width_mm == pytest.approx(1.9)
    assert targets.cadata_by_layer[0].remfit.c1 == 3.0e9


def test_campaign_inputs_resolves_named_conductors_and_excludes_unsupported(tmp_path) -> None:  # noqa: ANN001
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
CONDUCTOR 2
  1 HF 1 BADCABLE  BADSTR  FILHF INS OSTA BADFIT 1.9 'unsupported conductor'
  2 LF 1 GOODCABLE GOODSTR FILLF INS TRANS FIT1   1.9 'supported conductor'
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
    state["layers"][1]["inner_radius_min_mm"] = 24.0
    state["layers"][1]["inner_radius_max_mm"] = 26.0
    state["layers"][1]["max_angle_deg"] = 85.0
    state["acceptance"]["max_current_a"] = 12345.0
    app._state = lambda: state

    topology, targets, feasibility = target_synthesis_gui.App._campaign_inputs(app)

    assert topology.cables["layer-1"].width_mm == pytest.approx(2.0)
    assert topology.cables["layer-2"].width_mm == pytest.approx(5.0)
    assert targets.max_current_a == pytest.approx(12345.0)
    assert feasibility.max_angle_deg == (80.0, 85.0)
    assert targets.cadata_by_layer[0] is None
    assert targets.cadata_by_layer[1] is not None
    assert targets.cadata_by_layer[1].strand.diameter_mm == pytest.approx(1.065)
    assert [(item.layer_index, item.reason) for item in targets.excluded_margin_layers] == [
        (0, "unsupported REMFIT type 3 for 'BADFIT'; only type 1 is supported")
    ]


def _app_shell():
    app = target_synthesis_gui.App.__new__(target_synthesis_gui.App)
    app.target_field_var = FakeVar("0.02")
    app.aperture_var = FakeVar("8.0")
    app.n_layers_var = FakeVar(1)
    app.temperature_var = FakeVar("0.0")
    app.max_harmonic_var = FakeVar("1000.0")
    app.min_margin_var = FakeVar("10.0")
    app.max_current_var = FakeVar("13000.0")
    app.pop_size_var = FakeVar("8")
    app.n_gen_var = FakeVar("3")
    app.seed_var = FakeVar("7")
    app.feasibility_settings = dict(target_synthesis_gui.DEFAULT_STATE["feasibility"])
    app.layer_vars = [_layer_vars(0)]
    return app


def _layer_vars(index: int) -> dict[str, FakeVar]:
    layer = copy.deepcopy(target_synthesis_gui.DEFAULT_STATE["layers"][0])
    layer["cadata_path"] = f"layer-{index + 1}.cadata"
    layer["max_angle_deg"] = target_synthesis_gui._default_max_angle_deg(index)
    return {key: FakeVar(str(value)) for key, value in layer.items()}

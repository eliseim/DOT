from __future__ import annotations

import json
from pathlib import Path

import pytest

from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.gui.generation_archive import save_generation_snapshot
from dot.optimize.objectives import (
    CERTIFICATION_FIDELITY,
    BlockMarginRecord,
    LayerMarginRecord,
)


def _design() -> DipoleDesign:
    cable = CableSpec(width_mm=1.0, height_mm=1.0, insulation_thickness_mm=0.0)
    return DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            Layer(
                inner_radius_mm=10.0,
                blocks=(
                    Block(
                        phi_deg=75.0,
                        alpha_deg=0.0,
                        n_turns=2,
                        cable=cable,
                        inner_radius_mm=10.0,
                        current_a=500.0,
                    ),
                ),
            ),
        ),
    )


def test_save_generation_snapshot_writes_png_and_characteristics_json(tmp_path: Path) -> None:
    design = _design()
    records = (
        LayerMarginRecord(
            layer_index=0,
            peak_field_t=8.5,
            operating_current_a=500.0,
            short_sample_current_a=650.0,
            margin_percent=23.08,
        ),
    )

    json_path = save_generation_snapshot(
        tmp_path,
        generation=3,
        total_generations=10,
        design=design,
        harmonic_units=4.2,
        margin_percent=23.08,
        operating_current_a=500.0,
        margin_records=records,
        block_margin_records=(
            BlockMarginRecord(0, 0, 1, 8.5, 500.0, 650.0, 23.08),
        ),
        harmonics=((1, 10000.0, 0.0), (3, -4.2, 0.0), (5, 1.2, 0.0)),
        harmonic_targets=((3, -3.0),),
        cable_labels=("HF",),
        evaluation_fidelity=CERTIFICATION_FIDELITY,
    )

    png_path = tmp_path / "gen_0003.png"
    assert json_path == tmp_path / "gen_0003.json"
    assert png_path.exists()
    assert png_path.stat().st_size > 0

    snapshot_text = json_path.read_text()
    assert "roxie" not in snapshot_text.lower()
    characteristics = json.loads(snapshot_text)
    assert characteristics["schema_version"] == 3
    assert characteristics["evaluation_fidelity"] == {
        "name": "certify-v1",
        "bore_filaments_per_axis": 12,
        "peak_filaments_per_axis": 80,
        "bore_quadrature": "midpoint",
    }
    assert characteristics["generation"] == 3
    assert characteristics["total_generations"] == 10
    assert characteristics["harmonic_units"] == 4.2
    assert characteristics["harmonic_residual_units"] == 4.2
    assert characteristics["harmonic_targets"] == {"b3": -3.0}
    assert characteristics["margin_percent"] == 23.08
    assert characteristics["total_turns"] == 2
    assert characteristics["first_layer_pole_turn_clearance_mm"] == 0.0
    assert characteristics["limiting_layer"] == 0
    assert characteristics["per_layer_margin"] == [
        {
            "cable": "HF",
            "layer_index": 0,
            "peak_field_t": 8.5,
            "operating_current_a": 500.0,
            "short_sample_current_a": 650.0,
            "margin_percent": 23.08,
        }
    ]
    b3, b5 = characteristics["harmonics"]
    assert b3 == {
        "order": 3,
        "normal_units": -4.2,
        "target_normal_units": -3.0,
        "normal_residual_units": b3["normal_residual_units"],
        "skew_units": 0.0,
    }
    assert b3["normal_residual_units"] == pytest.approx(-1.2)
    assert b5 == {
        "order": 5,
        "normal_units": 1.2,
        "target_normal_units": 0.0,
        "normal_residual_units": 1.2,
        "skew_units": 0.0,
    }
    assert characteristics["per_block_margin"][0]["block"] == 1
    assert characteristics["per_block_margin"][0]["conductor"] == "HF"
    assert characteristics["blocks"] == [
        {
            "block": 1,
            "layer": 1,
            "block_in_layer": 1,
            "conductor": "HF",
            "radius_mm": 10.0,
            "n_turns": 2,
            "phi_deg": 75.0,
            "alpha_deg": 0.0,
            "current_a": 500.0,
        },
    ]
    assert characteristics["inter_block_clearances"] == []


def test_save_generation_snapshot_without_margin_records_still_writes_files(tmp_path: Path) -> None:
    design = _design()

    json_path = save_generation_snapshot(
        tmp_path,
        generation=1,
        total_generations=5,
        design=design,
        harmonic_units=100.0,
        margin_percent=-10.0,
        operating_current_a=500.0,
    )

    characteristics = json.loads(json_path.read_text())
    assert characteristics["evaluation_fidelity"] is None
    assert characteristics["limiting_layer"] is None
    assert characteristics["per_layer_margin"] == []

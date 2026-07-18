from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from dot.campaign import load_campaign
from dot.geometry import Block, DipoleDesign, Layer
from dot.geometry.constraints import (
    check_feasibility,
    first_layer_pole_turn_clearance_mm,
    inter_block_clearances,
)
from dot.optimize.runner import ParetoCandidate, _certify_candidate


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "benchmarks" / "lhc_mb_no_iron"


def test_blind_lhc_result_passes_full_certification() -> None:
    campaign = load_campaign(BENCHMARK / "blind_target.json")
    result = json.loads(
        (BENCHMARK / "certified_blind_result.json").read_text(encoding="utf-8")
    )
    layers = []
    for layer_index, row in enumerate(result["layers"]):
        radius = float(row["inner_radius_mm"])
        cable = campaign.topology.cables[
            campaign.topology.layers[layer_index].cable_id
        ]
        blocks = tuple(
            Block(
                phi_deg=float(block["phi_deg"]),
                alpha_deg=float(block["alpha_deg"]),
                n_turns=int(block["turns"]),
                cable=cable,
                inner_radius_mm=radius,
                current_a=1.0,
            )
            for block in row["blocks"]
        )
        layers.append(Layer(inner_radius_mm=radius, blocks=blocks))
    design = DipoleDesign(
        aperture_radius_mm=campaign.topology.aperture_radius_mm,
        layers=tuple(layers),
    )

    certified = _certify_candidate(
        ParetoCandidate(np.empty(0), design, (0.0, 0.0)),
        campaign.topology,
        campaign.targets,
        campaign.feasibility,
    )

    assert certified is not None
    assert certified.certified
    assert certified.operating_current_a is not None
    assert certified.operating_current_a > 10000.0
    assert max(abs(row[1]) for row in certified.harmonics if row[0] in {3, 5, 7, 9, 11}) <= 5.0
    assert min(row.margin_percent for row in certified.margin_by_layer) >= 25.0

    clearances = inter_block_clearances(certified.design)
    outer_gap = min(
        row.distance_mm for row in clearances if row.layer_index == 1
    )
    assert outer_gap == pytest.approx(0.1895476856217131)
    assert first_layer_pole_turn_clearance_mm(certified.design) == pytest.approx(
        5.106890032561411
    )

    stricter_outer_gap = check_feasibility(
        certified.design,
        aperture_radius_mm=campaign.topology.aperture_radius_mm,
        min_gap_mm=campaign.feasibility.min_gap_mm,
        max_angle_deg=campaign.feasibility.max_angle_deg,
        min_layer_clearance_mm=campaign.feasibility.min_layer_clearance_mm,
        min_pole_gap_mm=campaign.feasibility.min_pole_gap_mm,
        min_inter_block_gap_mm=(0.1, 0.5),
        enforce_layer_nesting=campaign.feasibility.enforce_layer_nesting,
        geometry_tolerance_mm=campaign.feasibility.geometry_tolerance_mm,
    )
    assert any(
        violation.constraint_name == "inter_block_gap"
        and violation.layer_index == 1
        for violation in stricter_outer_gap.violations
    )

    stricter_pole_radius = check_feasibility(
        certified.design,
        aperture_radius_mm=campaign.topology.aperture_radius_mm,
        min_gap_mm=0.0,
        min_pole_turn_radius_mm=10.0,
    )
    assert any(
        violation.constraint_name == "first_layer_pole_turn_radius"
        for violation in stricter_pole_radius.violations
    )

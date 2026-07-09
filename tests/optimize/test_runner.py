from __future__ import annotations

import pytest

from dot.conductors import CableRecord, StrandRecord, Type1FitCoefficients
from dot.geometry import CableSpec
from dot.optimize import (
    LayerConductorData,
    LayerTopology,
    Topology,
    field_quality_objective,
    load_line_margin_objective,
)
from dot.optimize.problem import FeasibilitySettings, MarginEvaluationExclusion, OptimizationTargets
from dot.optimize.runner import run_campaign


def test_run_campaign_returns_feasible_candidates_with_consistent_objectives() -> None:
    topology = _topology()
    targets = _targets()
    result = run_campaign(
        topology,
        targets,
        _feasibility(),
        pop_size=8,
        n_gen=3,
        seed=7,
    )

    assert result.candidates
    candidate = result.candidates[0]
    field_quality = field_quality_objective(
        candidate.design,
        targets.r_ref_mm,
        targets.max_order,
    )
    margin = load_line_margin_objective(
        candidate.design,
        cable_specs_by_layer=(candidate.design.layers[0].blocks[0].cable,),
        cadata_by_layer=targets.cadata_by_layer,
        temperature_k=targets.temperature_k,
    )

    assert candidate.objectives[0] == pytest.approx(field_quality, rel=1.0e-12)
    assert candidate.objectives[1] == pytest.approx(-margin, rel=1.0e-12)


def test_run_campaign_excludes_unsupported_layers_from_margin_result() -> None:
    topology = _four_layer_topology()
    targets = OptimizationTargets(
        target_bore_field_t=0.01,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(None, None, conductor_data(), conductor_data()),
        temperature_k=0.0,
        excluded_margin_layers=(
            MarginEvaluationExclusion(layer_index=0, reason="unsupported REMFIT type 3 for 'NB3SNMP'"),
            MarginEvaluationExclusion(layer_index=1, reason="unsupported REMFIT type 3 for 'NB3SNMP'"),
        ),
    )

    result = run_campaign(
        topology,
        targets,
        _feasibility(),
        pop_size=8,
        n_gen=2,
        seed=7,
    )

    assert result.candidates
    assert [(item.layer_index, item.reason) for item in result.excluded_margin_layers] == [
        (0, "unsupported REMFIT type 3 for 'NB3SNMP'"),
        (1, "unsupported REMFIT type 3 for 'NB3SNMP'"),
    ]


def _topology() -> Topology:
    cable = CableSpec(width_mm=0.1, height_mm=0.1, insulation_thickness_mm=0.0)
    return Topology(
        aperture_radius_mm=8.0,
        layers=(
            LayerTopology(
                cable_id="inner",
                n_blocks=2,
                inner_radius_bounds_mm=(20.0, 22.0),
                phi_bounds_deg=(10.0, 70.0),
                n_turns_bounds=(1, 1),
            ),
        ),
        cables={"inner": cable},
    )


def _four_layer_topology() -> Topology:
    cable = CableSpec(width_mm=0.1, height_mm=0.1, insulation_thickness_mm=0.0)
    layers = tuple(
        LayerTopology(
            cable_id=f"layer-{index}",
            n_blocks=1,
            inner_radius_bounds_mm=(20.0 + index * 4.0, 20.5 + index * 4.0),
            phi_bounds_deg=(10.0 + index * 15.0, 15.0 + index * 15.0),
            n_turns_bounds=(1, 1),
        )
        for index in range(4)
    )
    return Topology(
        aperture_radius_mm=8.0,
        layers=layers,
        cables={f"layer-{index}": cable for index in range(4)},
    )


def _targets() -> OptimizationTargets:
    return OptimizationTargets(
        target_bore_field_t=0.01,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(conductor_data(),),
        temperature_k=0.0,
    )


def _feasibility() -> FeasibilitySettings:
    return FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=80.0)


def conductor_data() -> LayerConductorData:
    strand = StrandRecord(diameter_mm=1.0, cu_to_sc_ratio=0.0)
    cable = CableRecord(n_strands=1, degradation_percent=0.0)
    remfit = Type1FitCoefficients(
        c1=10.0 * 5000.0 / (3.141592653589793 * 1.0**2 / 4.0 * 1.0e-6),
        c2=10.0,
        c3=1.0,
        c4=1.0,
        c5=1.0,
        c6=1.0,
        c7=10.0,
    )
    return LayerConductorData(strand=strand, cable=cable, remfit=remfit)

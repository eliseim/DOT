from pathlib import Path

import pytest

from dot.campaign import load_campaign
from dot.conductors import Type11FitCoefficients


def test_falcond_blind_campaign_preserves_reported_conductor_chain() -> None:
    root = Path(__file__).resolve().parents[2]
    campaign = load_campaign(root / "benchmarks" / "falcond_no_iron" / "blind_target.json")

    assert campaign.name == "falcond-blind-no-iron"
    assert campaign.topology.aperture_radius_mm == pytest.approx(25.0)
    assert campaign.targets.target_bore_field_t == pytest.approx(12.0)
    assert campaign.targets.min_margin_percent == pytest.approx(20.0)
    assert campaign.feasibility.max_angle_deg is None
    assert campaign.feasibility.min_pole_turn_radius_mm == pytest.approx(10.0)
    assert [layer.inner_radius_mm for layer in campaign.topology.layers] == pytest.approx(
        [25.0, 47.21955001214964]
    )
    first = campaign.targets.cadata_by_layer[0]
    assert first.cable.height_mm == pytest.approx(21.420)
    assert first.cable.width_inner_mm == pytest.approx(1.797)
    assert first.cable.width_outer_mm == pytest.approx(1.989)
    assert first.strand.diameter_mm == pytest.approx(1.0)
    assert first.strand.cu_to_sc_ratio == pytest.approx(0.885)
    assert isinstance(first.remfit, Type11FitCoefficients)
    assert (
        first.remfit.c0,
        first.remfit.bc20_t,
        first.remfit.tc0_k,
        first.remfit.alpha,
        first.remfit.v,
        first.remfit.p,
        first.remfit.q,
    ) == pytest.approx(
        (2.14276e11, 29.38, 16.0, 0.96, 1.52, 0.5, 2.0)
    )
    assert campaign.raw["provenance"]["layout_knowledge_used"] is False

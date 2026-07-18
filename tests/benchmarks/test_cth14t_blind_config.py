from pathlib import Path

import pytest

from dot.campaign import load_campaign
from dot.conductors import Type1FitCoefficients, Type11FitCoefficients


def test_cth14t_blind_campaign_uses_requirements_not_reference_layout() -> None:
    root = Path(__file__).resolve().parents[2]
    campaign = load_campaign(root / "benchmarks" / "cth14t_no_iron" / "blind_target.json")

    assert campaign.name == "cth-14t-blind-no-iron"
    assert campaign.topology.aperture_radius_mm == pytest.approx(25.0)
    assert campaign.targets.target_bore_field_t == pytest.approx(12.4)
    assert campaign.targets.min_margin_percent == pytest.approx(25.0)
    assert campaign.targets.max_harmonic_units == pytest.approx(5.0)
    assert campaign.targets.harmonic_orders == (3, 5, 7, 9, 11)
    assert campaign.feasibility.max_angle_deg is None
    assert campaign.feasibility.min_pole_turn_radius_mm == pytest.approx(10.0)
    assert [layer.inner_radius_mm for layer in campaign.topology.layers] == pytest.approx(
        [25.0, 44.15255001214963, 63.30529521593481, 80.26511750643057]
    )
    assert all(layer.first_block_phi_deg is not None for layer in campaign.topology.layers)
    assert all(layer.first_block_alpha_deg == 0.0 for layer in campaign.topology.layers)
    assert [type(layer.remfit) for layer in campaign.targets.cadata_by_layer] == [
        Type11FitCoefficients,
        Type11FitCoefficients,
        Type1FitCoefficients,
        Type1FitCoefficients,
    ]
    assert campaign.raw["provenance"]["layout_knowledge_used"] is False

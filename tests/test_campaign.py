from __future__ import annotations

import json
from pathlib import Path

import pytest

from dot.campaign import _harmonic_targets, load_campaign, result_document
from dot.cli import main
from dot.optimize.runner import ParetoResult


SAMPLE_CONFIG = Path("tests/fixtures/7T_NbTi_headless.json")


def test_sample_campaign_resolves_linked_inner_and_outer_conductors() -> None:
    campaign = load_campaign(SAMPLE_CONFIG)

    assert campaign.topology.aperture_radius_mm == pytest.approx(28.0)
    assert campaign.targets.target_bore_field_t == pytest.approx(7.0)
    assert campaign.targets.r_ref_mm == pytest.approx(18.667)
    assert campaign.targets.harmonic_orders == (3, 5, 7, 9, 11)
    assert campaign.targets.max_harmonic_units == pytest.approx(5.0)
    assert campaign.targets.min_margin_percent == pytest.approx(25.0)
    assert campaign.targets.search_fidelity.bore_quadrature == "gauss-legendre"
    assert campaign.targets.certification_fidelity.bore_quadrature == "midpoint"
    assert not hasattr(campaign, "refinement")
    assert campaign.feasibility.min_inter_block_gap_mm == pytest.approx((0.5, 1.0))
    assert campaign.feasibility.max_angle_deg is None
    assert campaign.feasibility.min_pole_turn_radius_mm == pytest.approx(7.0)
    assert [layer.inner_radius_mm for layer in campaign.topology.layers] == pytest.approx(
        [28.0, 43.889598222933635]
    )
    assert [layer.first_block_phi_deg for layer in campaign.topology.layers] == pytest.approx(
        [0.3069387397092032, 0.1958170913649932]
    )
    assert [layer.first_block_alpha_deg for layer in campaign.topology.layers] == pytest.approx(
        [0.0, 0.0]
    )
    inner, outer = campaign.targets.cadata_by_layer
    assert inner is not None and outer is not None
    assert inner.cable.n_strands == 28
    assert inner.strand.diameter_mm == pytest.approx(1.065)
    assert outer.cable.n_strands == 36
    assert outer.strand.diameter_mm == pytest.approx(0.825)
    inner_geometry = campaign.topology.cables[campaign.topology.layers[0].cable_id]
    outer_geometry = campaign.topology.cables[campaign.topology.layers[1].cable_id]
    assert inner_geometry.height_mm == pytest.approx(15.1)
    assert inner_geometry.width_inner_mm == pytest.approx(1.736)
    assert inner_geometry.insulation_azimuthal_mm == pytest.approx(0.145)
    assert outer_geometry.width_outer_mm == pytest.approx(1.598)
    assert outer_geometry.insulation_radial_mm == pytest.approx(0.15)


def test_headless_campaign_harmonic_targets_accept_b_prefix_and_signed_values() -> None:
    assert _harmonic_targets({"b3": -3.0, "5": 1.25}, (3, 5, 7)) == (
        (3, -3.0),
        (5, 1.25),
    )

    with pytest.raises(ValueError, match="not listed in acceptance.harmonic_orders"):
        _harmonic_targets({"b9": -3.0}, (3, 5, 7))


def test_sample_input_contains_only_user_gaps_not_wedge_layout() -> None:
    raw = json.loads(SAMPLE_CONFIG.read_text(encoding="utf-8"))

    assert raw["geometry_angle_convention"] == "native-midplane-zero"
    for index, layer in enumerate(raw["layers"]):
        assert layer["azimuthal_gap_mm"] == pytest.approx(0.15)
        if index:
            assert layer["radial_gap_mm"] == pytest.approx(0.5)
        else:
            assert "radial_gap_mm" not in layer
        assert "inner_radius_mm" not in layer
        assert "first_block_phi_deg" not in layer
        assert "first_block_alpha_deg" not in layer
        assert "blocks" not in layer
        assert "block_angles" not in layer
        assert "turn_allocation" not in layer
    assert raw["provenance"]["layout_knowledge_used"] is False
    assert "max_pole_angle_deg" not in raw["geometry"]


def test_campaign_rejects_nonzero_layer_one_radial_gap(tmp_path: Path) -> None:
    raw = _portable_sample_config()
    raw["layers"][0]["radial_gap_mm"] = 0.5
    config = tmp_path / "invalid-first-gap.json"
    config.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="Layer 1 R is the aperture radius"):
        load_campaign(config)


def test_campaign_rejects_removed_refinement_stage(tmp_path: Path) -> None:
    raw = _portable_sample_config()
    raw["optimization"]["refinement"] = {"enabled": True}
    config = tmp_path / "removed-refinement.json"
    config.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="optimization.refinement has been removed"):
        load_campaign(config)


def test_campaign_accepts_optional_radial_preference(tmp_path: Path) -> None:
    raw = _portable_sample_config()
    raw["optimization"]["prefer_radial_design"] = True
    config = tmp_path / "radial-preference.json"
    config.write_text(json.dumps(raw), encoding="utf-8")

    campaign = load_campaign(config)

    assert campaign.targets.prefer_radial_design is True


def test_campaign_accepts_minimum_and_equal_fixed_current_bounds(tmp_path: Path) -> None:
    raw = _portable_sample_config()
    raw["acceptance"]["min_current_a"] = 11850.0
    raw["acceptance"]["max_current_a"] = 11850.0
    config = tmp_path / "fixed-current.json"
    config.write_text(json.dumps(raw), encoding="utf-8")

    campaign = load_campaign(config)

    assert campaign.targets.min_current_a == pytest.approx(11850.0)
    assert campaign.targets.max_current_a == pytest.approx(11850.0)
    assert campaign.targets.fixed_current_a == pytest.approx(11850.0)


def test_campaign_rejects_minimum_current_above_maximum(tmp_path: Path) -> None:
    raw = _portable_sample_config()
    raw["acceptance"]["min_current_a"] = 13001.0
    raw["acceptance"]["max_current_a"] = 13000.0
    config = tmp_path / "invalid-current-range.json"
    config.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="min_current_a must not exceed max_current_a"):
        load_campaign(config)


def test_campaign_rejects_string_booleans(tmp_path: Path) -> None:
    raw = _portable_sample_config()
    raw["geometry"]["enforce_layer_nesting"] = "false"
    config = tmp_path / "invalid-enforce-layer-nesting.json"
    config.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="JSON boolean"):
        load_campaign(config)


def test_cli_validate_checks_campaign_without_optimization(capsys) -> None:  # noqa: ANN001
    exit_code = main(["validate", str(SAMPLE_CONFIG)])

    assert exit_code == 0
    assert "YELLON" not in capsys.readouterr().err


def _portable_sample_config() -> dict:
    raw = json.loads(SAMPLE_CONFIG.read_text(encoding="utf-8"))
    for layer in raw["layers"]:
        layer["cadata"] = str((SAMPLE_CONFIG.parent / layer["cadata"]).resolve())
    return raw


def test_cli_gui_opens_interactive_application(monkeypatch) -> None:  # noqa: ANN001
    launches = []
    monkeypatch.setattr(
        "dot.gui.target_synthesis_gui.main",
        lambda: launches.append("gui"),
    )

    assert main(["gui"]) == 0
    assert launches == ["gui"]


def test_cli_uses_single_internal_search_policy(
    tmp_path,
    monkeypatch,
) -> None:  # noqa: ANN001
    captured = {}

    def fake_run_campaign(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        captured.update(kwargs)
        return ParetoResult(candidates=())

    monkeypatch.setattr("dot.cli.run_campaign", fake_run_campaign)

    assert (
        main(
            [
                "optimize",
                str(SAMPLE_CONFIG),
                "--quick",
                "--output",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert "topology_survival" not in captured
    assert "adaptive_offspring" not in captured


def test_cli_rejects_nonempty_output_directory_before_running(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:  # noqa: ANN001
    (tmp_path / "stale-result.json").write_text("{}", encoding="utf-8")
    runs = []
    monkeypatch.setattr("dot.cli.run_campaign", lambda *args, **kwargs: runs.append(args))

    with pytest.raises(SystemExit, match="2"):
        main(
            [
                "optimize",
                str(SAMPLE_CONFIG),
                "--quick",
                "--output",
                str(tmp_path),
            ]
        )

    assert runs == []
    assert "output directory must be empty" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--population", "0"),
        ("--generations", "-1"),
        ("--workers", "0"),
    ],
)
def test_cli_rejects_nonpositive_numeric_overrides(
    tmp_path,
    option: str,
    value: str,
    capsys,
) -> None:  # noqa: ANN001
    with pytest.raises(SystemExit, match="2"):
        main(
            [
                "optimize",
                str(SAMPLE_CONFIG),
                "--output",
                str(tmp_path),
                option,
                value,
            ]
        )

    assert "must be a positive integer" in capsys.readouterr().err


def test_result_document_marks_quick_empty_archive_honestly() -> None:
    campaign = load_campaign(SAMPLE_CONFIG)

    document = result_document(campaign, ParetoResult(candidates=()), quick=True)

    assert document["quick_run"] is True
    assert document["candidate_count"] == 0
    assert document["certification_fidelity"] == {
        "name": "certify-v1",
        "bore_filaments_per_axis": 12,
        "peak_filaments_per_axis": 80,
        "bore_quadrature": "midpoint",
    }
    assert {row["role"] for row in document["inputs"]} == {"campaign", "cadata"}
    assert all(len(row["sha256"]) == 64 for row in document["inputs"])
    assert document["software"]["dot_version"] == "1.1.1"
    assert document["software"]["packages"]["numpy"]


def test_cli_quick_run_reports_progress_and_saves_generation_artifacts(
    tmp_path,
    capsys,
) -> None:  # noqa: ANN001
    exit_code = main(
        [
            "optimize",
            str(SAMPLE_CONFIG),
            "--quick",
            "--output",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "roxie" not in output.lower()
    assert "generation 1/3" in output
    assert "ETA" in output
    assert (tmp_path / "pareto.json").exists()
    assert (tmp_path / "pareto_candidates.json").exists()
    generation_dir = tmp_path / "seed_7" / "generations"
    assert len(tuple(generation_dir.glob("gen_*.png"))) == 3
    assert len(tuple(generation_dir.glob("gen_*.json"))) == 3
    for snapshot_path in generation_dir.glob("gen_*.json"):
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        first_blocks = {
            row["layer"]: row for row in snapshot["blocks"] if row["block_in_layer"] == 1
        }
        assert first_blocks[1]["radius_mm"] == pytest.approx(28.0)
        assert first_blocks[1]["phi_deg"] == pytest.approx(0.3069387397092032)
        assert first_blocks[1]["alpha_deg"] == pytest.approx(0.0)
        assert first_blocks[2]["radius_mm"] == pytest.approx(43.889598222933635)
        assert first_blocks[2]["phi_deg"] == pytest.approx(0.1958170913649932)
        assert first_blocks[2]["alpha_deg"] == pytest.approx(0.0)

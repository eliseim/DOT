from __future__ import annotations

import csv
import json
from dataclasses import replace

import numpy as np
import pytest
from matplotlib import image as mpimg

from dot.geometry import (
    Block,
    CableSpec,
    DipoleDesign,
    Layer,
    radialized_block_alpha_deg,
)
from dot.optimize.objectives import BlockMarginRecord, LayerMarginRecord
from dot.optimize.runner import ParetoCandidate, ParetoResult
from dot.results import (
    block_geometry_rows,
    best_candidate_index,
    candidate_document,
    diverse_candidate_indices,
    export_campaign_results,
    export_no_candidate_result,
    inter_block_clearance_rows,
    candidate_summary_figure,
    selection_candidates,
    _pareto_frontier_figure,
)


def _candidate() -> ParetoCandidate:
    cable = CableSpec(width_mm=1.0, height_mm=2.0)
    design = DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            Layer(
                inner_radius_mm=10.0,
                blocks=(
                    Block(10.0, 0.0, 2, cable, 10.0, 500.0),
                    Block(55.0, 20.0, 1, cable, 10.0, 500.0),
                ),
            ),
        ),
    )
    return ParetoCandidate(
        genome=np.empty(0),
        design=design,
        objectives=(4.2, -25.0),
        harmonics=((1, 10000.0, 0.0), (3, -4.2, 0.0)),
        margin_by_layer=(LayerMarginRecord(0, 7.4, 500.0, 666.666, 25.0),),
        margin_by_block=(
            BlockMarginRecord(0, 0, 1, 7.4, 500.0, 666.666, 25.0),
            BlockMarginRecord(0, 1, 2, 7.0, 500.0, 700.0, 28.5714286),
        ),
        operating_current_a=500.0,
        certified=True,
    )


def test_block_geometry_rows_use_native_angles() -> None:
    rows = block_geometry_rows(_candidate().design, ("CABLE-A",))

    assert len(rows) == 2
    assert rows[0].phi_deg == pytest.approx(10.0)
    assert rows[1].phi_deg == pytest.approx(55.0)
    assert rows[1].alpha_deg == pytest.approx(20.0)
    assert rows[1].conductor == "CABLE-A"


def test_inter_block_clearance_rows_use_designer_facing_indices() -> None:
    rows = inter_block_clearance_rows(_candidate().design)

    assert len(rows) == 1
    assert (rows[0].layer, rows[0].block_a, rows[0].block_b) == (1, 1, 2)
    assert rows[0].closest_turn_a >= 1
    assert rows[0].closest_turn_b >= 1
    assert rows[0].closest_distance_mm > 0.0


def test_candidate_document_contains_geometry_harmonics_and_margin() -> None:
    document = candidate_document(
        _candidate(),
        campaign_name="test",
        reference_radius_mm=5.0,
        conductor_labels=("CABLE-A",),
    )

    assert document["certified"] is True
    assert document["operating_current_a"] == pytest.approx(500.0)
    assert document["minimum_margin_percent"] == pytest.approx(25.0)
    assert document["harmonics"][1]["normal_units"] == pytest.approx(-4.2)
    assert document["margins_by_block"][1]["block"] == 2
    assert document["margins_by_block"][1]["margin_percent"] == pytest.approx(28.5714286)
    assert document["blocks"][1]["phi_deg"] == pytest.approx(55.0)
    assert document["blocks"][1]["block"] == 2
    assert document["blocks"][1]["block_in_layer"] == 2
    assert document["inter_block_clearances"][0]["layer"] == 1
    assert document["first_layer_pole_turn_clearance_mm"] > 0.0
    assert "roxie" not in json.dumps(document).lower()


def test_candidate_document_reports_actual_target_and_residual_harmonics() -> None:
    candidate = replace(
        _candidate(),
        objectives=(1.2, -25.0),
        harmonic_targets=((3, -3.0),),
    )

    document = candidate_document(
        candidate,
        campaign_name="iron-compensation",
        reference_radius_mm=5.0,
    )

    assert document["worst_harmonic_residual_units"] == pytest.approx(1.2)
    assert document["harmonic_targets"] == {"b3": -3.0}
    assert document["harmonics"][1]["normal_units"] == pytest.approx(-4.2)
    assert document["harmonics"][1]["target_normal_units"] == pytest.approx(-3.0)
    assert document["harmonics"][1]["normal_residual_units"] == pytest.approx(-1.2)


def test_best_candidate_index_prefers_target_box_over_one_extreme() -> None:
    balanced = _candidate()
    low_harmonic_zero_margin = ParetoCandidate(
        np.empty(0),
        balanced.design,
        (0.1, -1.0),
    )
    result = ParetoResult(candidates=(low_harmonic_zero_margin, balanced))

    assert (
        best_candidate_index(
            result,
            max_harmonic_units=5.0,
            min_margin_percent=25.0,
        )
        == 1
    )


def test_best_candidate_index_prefers_fewer_turns_then_fewer_blocks_on_em_ties() -> None:
    base = _candidate()
    cable = base.design.layers[0].blocks[0].cable
    fewer_turns = replace(
        base,
        design=DipoleDesign(
            aperture_radius_mm=8.0,
            layers=(
                Layer(
                    inner_radius_mm=10.0,
                    blocks=(Block(10.0, 0.0, 2, cable, 10.0, 500.0),),
                ),
            ),
        ),
    )
    same_turns_more_blocks = replace(
        base,
        design=DipoleDesign(
            aperture_radius_mm=8.0,
            layers=(
                Layer(
                    inner_radius_mm=10.0,
                    blocks=(
                        Block(10.0, 0.0, 1, cable, 10.0, 500.0),
                        Block(50.0, 0.0, 1, cable, 10.0, 500.0),
                    ),
                ),
            ),
        ),
    )
    result = ParetoResult(candidates=(base, same_turns_more_blocks, fewer_turns))

    assert (
        best_candidate_index(
            result,
            max_harmonic_units=5.0,
            min_margin_percent=25.0,
        )
        == 2
    )


def test_final_selection_prefers_radiality_after_targets_are_met() -> None:
    electromagnetic_best = replace(_candidate(), objectives=(1.0, -30.0))
    layer = electromagnetic_best.design.layers[0]
    free_block = layer.blocks[1]
    radial_block = replace(
        free_block,
        alpha_deg=radialized_block_alpha_deg(free_block, (-20.0, 80.0)),
    )
    radial_target_met = replace(
        electromagnetic_best,
        design=replace(
            electromagnetic_best.design,
            layers=(replace(layer, blocks=(layer.blocks[0], radial_block)),),
        ),
        objectives=(4.0, -25.0),
    )
    result = ParetoResult(
        candidates=(electromagnetic_best,),
        radial_archive=(radial_target_met,),
    )

    assert len(selection_candidates(result)) == 2
    assert (
        best_candidate_index(
            result,
            max_harmonic_units=5.0,
            min_margin_percent=25.0,
        )
        == 1
    )


def test_diverse_shortlist_keeps_only_best_design_per_topology() -> None:
    base = _candidate()
    cable = base.design.layers[0].blocks[0].cable

    def with_blocks(count: int, harmonic: float) -> ParetoCandidate:
        blocks = tuple(
            Block(10.0 + 15.0 * index, 0.0, 1, cable, 10.0, 500.0) for index in range(count)
        )
        return replace(
            base,
            design=DipoleDesign(8.0, (Layer(10.0, blocks),)),
            objectives=(harmonic, -25.0),
        )

    candidates = (
        with_blocks(1, 1.0),
        with_blocks(1, 2.0),
        with_blocks(2, 2.5),
        with_blocks(2, 3.0),
        with_blocks(3, 4.0),
    )
    selected = diverse_candidate_indices(
        candidates,
        max_designs=5,
        max_harmonic_units=5.0,
        min_margin_percent=25.0,
    )

    selected_families = [len(candidates[index].design.layers[0].blocks) for index in selected]
    assert selected_families == [1, 2, 3]
    assert selected == (0, 2, 4)


def test_export_campaign_results_writes_designer_artifacts(tmp_path) -> None:  # noqa: ANN001
    result = ParetoResult(candidates=(_candidate(),))

    artifacts = export_campaign_results(
        tmp_path,
        result,
        best_index=0,
        campaign_name="test",
        reference_radius_mm=5.0,
        conductor_labels=("CABLE-A",),
    )

    assert artifacts.cross_section_png.stat().st_size > 0
    assert artifacts.summary_png.stat().st_size > 0
    assert artifacts.pareto_frontier_png.stat().st_size > 0
    assert artifacts.best_candidate_json.exists()
    assert artifacts.pareto_json.exists()
    assert artifacts.shortlist_manifest_json.exists()
    assert artifacts.selected_designs_dir.is_dir()
    best = json.loads(artifacts.best_candidate_json.read_text(encoding="utf-8"))
    assert best["blocks"][0]["conductor"] == "CABLE-A"
    with artifacts.block_table_csv.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[1]["block"] == "2"
    assert rows[1]["block_in_layer"] == "2"
    assert float(rows[1]["alpha_deg"]) == pytest.approx(20.0)
    shortlist = json.loads(artifacts.shortlist_manifest_json.read_text(encoding="utf-8"))
    assert shortlist["design_count"] == 1
    assert artifacts.selected_designs_dir.name == "best_topology_designs"
    assert not any(path.is_dir() for path in artifacts.selected_designs_dir.iterdir())
    selected = shortlist["designs"][0]
    assert (artifacts.selected_designs_dir / selected["candidate_json"]).exists()
    assert (artifacts.selected_designs_dir / selected["geometry_csv"]).exists()
    summary_image = artifacts.selected_designs_dir / selected["summary_image"]
    assert summary_image.stat().st_size > 0
    pixels = mpimg.imread(summary_image)
    assert pixels.shape[1] > pixels.shape[0]


def test_export_accepts_certified_radial_archive_without_final_em_front(
    tmp_path,
) -> None:  # noqa: ANN001
    result = ParetoResult(candidates=(), radial_archive=(_candidate(),))

    best_index = best_candidate_index(
        result,
        max_harmonic_units=5.0,
        min_margin_percent=25.0,
    )
    artifacts = export_campaign_results(
        tmp_path,
        result,
        best_index=best_index,
        campaign_name="radial-only",
        reference_radius_mm=5.0,
    )

    document = json.loads(artifacts.pareto_json.read_text(encoding="utf-8"))
    assert document["candidate_count"] == 1
    assert document["electromagnetic_pareto_candidate_count"] == 0
    assert document["radial_archive_candidate_count"] == 1


def test_final_pareto_figure_contains_only_data_and_axis_labels() -> None:
    result = ParetoResult(candidates=(_candidate(),))

    figure = _pareto_frontier_figure(
        result,
        max_harmonic_units=5.0,
        min_margin_percent=25.0,
    )
    axes = figure.axes[0]

    assert axes.get_title() == ""
    assert axes.get_legend() is None
    assert axes.get_xlabel() == "Worst harmonic residual [units]"
    assert axes.get_ylabel() == "Minimum load-line margin [%]"
    assert len(axes.lines) == 1
    assert figure.axes[1].get_ylabel() == "Total turns"
    assert tuple(figure.axes[1].get_yticks()) == (3.0,)


def test_export_no_candidate_result_is_explicit(tmp_path) -> None:  # noqa: ANN001
    destination = export_no_candidate_result(
        tmp_path,
        ParetoResult(candidates=()),
        campaign_name="empty",
    )

    document = json.loads(destination.read_text(encoding="utf-8"))
    assert document["candidate_count"] == 0
    assert document["best_candidate_index"] is None
    assert document["candidates"] == []
    assert (tmp_path / "final_pareto_frontier.png").stat().st_size > 0


def test_no_candidate_export_shortlists_uncertified_search_front(tmp_path) -> None:  # noqa: ANN001
    search_candidate = replace(_candidate(), certified=False)
    export_no_candidate_result(
        tmp_path,
        ParetoResult(candidates=(), search_front=(search_candidate,)),
        campaign_name="near-miss",
        reference_radius_mm=5.0,
    )

    manifest = json.loads(
        (tmp_path / "best_topology_designs" / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["source"] == "uncertified_search_front"
    assert manifest["design_count"] == 1
    assert manifest["designs"][0]["certified"] is False


def test_uncertified_summary_image_title_omits_search_design_warning() -> None:
    figure = candidate_summary_figure(
        replace(_candidate(), certified=False),
        campaign_name="near-miss",
        reference_radius_mm=5.0,
    )

    title = figure._suptitle.get_text()
    assert "UNCERTIFIED SEARCH DESIGN" not in title
    assert "near-miss" in title

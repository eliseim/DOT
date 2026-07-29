"""Designer-facing result tables and persistent campaign artifacts."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from matplotlib.figure import Figure

from dot.geometry import DipoleDesign
from dot.geometry.constraints import (
    first_layer_pole_turn_clearance_mm,
    inter_block_clearances,
)
from dot.optimize.runner import ParetoCandidate, ParetoResult
from dot.physics import field_at, place_line_current_sources


@dataclass(frozen=True, slots=True)
class BlockGeometryRow:
    """One block using the native ROXIE/CTH angular convention."""

    layer: int
    block: int
    roxie_block: int
    conductor: str
    radius_mm: float
    n_turns: int
    phi_deg: float
    alpha_deg: float
    current_a: float

    @property
    def phi_roxie_deg(self) -> float:
        """Compatibility alias; DOT now stores ROXIE phi directly."""

        return self.phi_deg

    @property
    def alpha_roxie_deg(self) -> float:
        """Compatibility alias; DOT now stores ROXIE alpha directly."""

        return self.alpha_deg

    @property
    def phi_dot_deg(self) -> float:
        """Compatibility alias for pre-v2 callers."""

        return self.phi_deg

    @property
    def alpha_dot_deg(self) -> float:
        """Compatibility alias for pre-v2 callers."""

        return self.alpha_deg


@dataclass(frozen=True, slots=True)
class InterBlockClearanceRow:
    """Designer-facing closest-point clearance for one block pair."""

    layer: int
    block_a: int
    block_b: int
    closest_turn_a: int
    closest_turn_b: int
    closest_distance_mm: float


@dataclass(frozen=True, slots=True)
class ResultArtifacts:
    """Paths written for one completed GUI campaign."""

    best_candidate_json: Path
    block_table_csv: Path
    cross_section_png: Path
    summary_png: Path
    pareto_json: Path
    pareto_frontier_png: Path
    shortlist_manifest_json: Path
    selected_designs_dir: Path


def best_candidate_index(
    result: ParetoResult,
    *,
    max_harmonic_units: float | None,
    min_margin_percent: float | None,
) -> int:
    """Select a balanced, target-aware representative of a Pareto archive."""

    if not result.candidates:
        raise ValueError("cannot select a best candidate from an empty archive")
    harmonic_limit = max_harmonic_units or 1.0
    margin_target = min_margin_percent or 1.0

    def score(index: int) -> tuple[float, float, int, int]:
        return _candidate_score(result.candidates[index], harmonic_limit, margin_target)

    return min(range(len(result.candidates)), key=score)


def diverse_candidate_indices(
    candidates: Sequence[ParetoCandidate],
    *,
    max_designs: int = 10,
    max_harmonic_units: float | None,
    min_margin_percent: float | None,
) -> tuple[int, ...]:
    """Select the best candidate from each topology family, quality-ranked."""

    if max_designs <= 0 or not candidates:
        return ()
    harmonic_limit = max_harmonic_units or 1.0
    margin_target = min_margin_percent or 1.0
    grouped: dict[tuple[int, ...], list[int]] = {}
    for index, candidate in enumerate(candidates):
        grouped.setdefault(_topology_signature(candidate.design), []).append(index)
    for indices in grouped.values():
        indices.sort(
            key=lambda index: _candidate_score(
                candidates[index], harmonic_limit, margin_target
            )
        )
    family_order = sorted(
        grouped,
        key=lambda family: _candidate_score(
            candidates[grouped[family][0]], harmonic_limit, margin_target
        ),
    )
    return tuple(grouped[family][0] for family in family_order[:max_designs])


def block_geometry_rows(
    design: DipoleDesign,
    conductor_labels: tuple[str, ...] = (),
) -> tuple[BlockGeometryRow, ...]:
    """Return the exact per-block table required to recreate the coil layout.

    ``phi`` is measured from the midplane toward the pole and ``alpha`` is
    the absolute cable-frame angle.
    """

    rows: list[BlockGeometryRow] = []
    roxie_block = 1
    for layer_index, layer in enumerate(design.layers, start=1):
        conductor = (
            conductor_labels[layer_index - 1] if layer_index <= len(conductor_labels) else ""
        )
        for block_index, block in enumerate(layer.blocks, start=1):
            rows.append(
                BlockGeometryRow(
                    layer=layer_index,
                    block=block_index,
                    roxie_block=roxie_block,
                    conductor=conductor,
                    radius_mm=layer.inner_radius_mm,
                    n_turns=block.n_turns,
                    phi_deg=_clean_float(block.phi_deg),
                    alpha_deg=_clean_float(block.alpha_deg),
                    current_a=abs(block.current_a),
                )
            )
            roxie_block += 1
    return tuple(rows)


def block_geometry_record(row: BlockGeometryRow) -> dict[str, Any]:
    """Return a neutral, designer-facing geometry record."""

    return {
        "block": row.roxie_block,
        "layer": row.layer,
        "block_in_layer": row.block,
        "conductor": row.conductor,
        "radius_mm": row.radius_mm,
        "n_turns": row.n_turns,
        "phi_deg": row.phi_deg,
        "alpha_deg": row.alpha_deg,
        "current_a": row.current_a,
    }


def inter_block_clearance_rows(
    design: DipoleDesign,
) -> tuple[InterBlockClearanceRow, ...]:
    """Return exact insulated-polygon clearances using one-based design indices."""

    return tuple(
        InterBlockClearanceRow(
            layer=row.layer_index + 1,
            block_a=row.block_index + 1,
            block_b=row.other_block_index + 1,
            closest_turn_a=row.turn_index + 1,
            closest_turn_b=row.other_turn_index + 1,
            closest_distance_mm=row.distance_mm,
        )
        for row in inter_block_clearances(design)
    )


def candidate_document(
    candidate: ParetoCandidate,
    *,
    campaign_name: str,
    reference_radius_mm: float,
    conductor_labels: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Serialize one candidate with physics and reproducible block geometry."""

    operating_current = (
        candidate.operating_current_a
        if candidate.operating_current_a is not None
        else _operating_current(candidate.design)
    )
    minimum_margin = (
        min(row.margin_percent for row in candidate.margin_by_layer)
        if candidate.margin_by_layer
        else -candidate.objectives[1]
    )
    target_by_order = dict(candidate.harmonic_targets)
    return {
        "schema_version": 3,
        "campaign": campaign_name,
        "certified": candidate.certified,
        "harmonic_convention": "CERN/European units: 1e-4 of main normal dipole",
        "geometry_conventions": {
            "phi": "0 deg at midplane, increasing toward pole",
            "alpha": "absolute cable-frame angle",
        },
        "reference_radius_mm": reference_radius_mm,
        "bore_field_t": _center_field_t(candidate.design),
        "operating_current_a": operating_current,
        # Backward-compatible alias retained; the objective is now explicitly
        # the worst residual from the requested per-harmonic target.
        "worst_harmonic_units": candidate.objectives[0],
        "worst_harmonic_residual_units": candidate.objectives[0],
        "harmonic_targets": {
            f"b{order}": target for order, target in candidate.harmonic_targets
        },
        "minimum_margin_percent": minimum_margin,
        "topology_family": _topology_family(candidate.design),
        "total_turns": _total_turns(candidate.design),
        "total_blocks": _total_blocks(candidate.design),
        "first_layer_pole_turn_clearance_mm": first_layer_pole_turn_clearance_mm(candidate.design),
        "harmonics": [
            {
                "order": order,
                "normal_units": normal,
                "target_normal_units": target_by_order.get(order, 0.0),
                "normal_residual_units": normal - target_by_order.get(order, 0.0),
                "skew_units": skew,
            }
            for order, normal, skew in candidate.harmonics
        ],
        "margins_by_layer": [
            {
                "layer": row.layer_index + 1,
                "conductor": (
                    conductor_labels[row.layer_index]
                    if row.layer_index < len(conductor_labels)
                    else ""
                ),
                "peak_field_t": row.peak_field_t,
                "operating_current_a": row.operating_current_a,
                "short_sample_current_a": row.short_sample_current_a,
                "margin_percent": row.margin_percent,
            }
            for row in candidate.margin_by_layer
        ],
        "margins_by_block": [
            {
                "block": row.roxie_block,
                "layer": row.layer_index + 1,
                "block_in_layer": row.block_index + 1,
                "conductor": (
                    conductor_labels[row.layer_index]
                    if row.layer_index < len(conductor_labels)
                    else ""
                ),
                "peak_field_t": row.peak_field_t,
                "operating_current_a": row.operating_current_a,
                "short_sample_current_a": row.short_sample_current_a,
                "margin_percent": row.margin_percent,
            }
            for row in candidate.margin_by_block
        ],
        "blocks": [
            block_geometry_record(row)
            for row in block_geometry_rows(candidate.design, conductor_labels)
        ],
        "inter_block_clearances": [
            asdict(row) for row in inter_block_clearance_rows(candidate.design)
        ],
    }


def export_campaign_results(
    output_dir: Path,
    result: ParetoResult,
    *,
    best_index: int,
    campaign_name: str,
    reference_radius_mm: float,
    conductor_labels: tuple[str, ...] = (),
    max_harmonic_units: float | None = None,
    min_margin_percent: float | None = None,
) -> ResultArtifacts:
    """Write the final cross-section, block table, and Pareto archive."""

    if not result.candidates:
        raise ValueError("cannot export an empty certified candidate archive")
    if best_index < 0 or best_index >= len(result.candidates):
        raise IndexError("best_index is outside the candidate archive")
    output_dir.mkdir(parents=True, exist_ok=True)
    best = result.candidates[best_index]
    documents = [
        candidate_document(
            candidate,
            campaign_name=campaign_name,
            reference_radius_mm=reference_radius_mm,
            conductor_labels=conductor_labels,
        )
        for candidate in result.candidates
    ]

    best_json = output_dir / "best_candidate.json"
    best_json.write_text(json.dumps(documents[best_index], indent=2) + "\n", encoding="utf-8")
    pareto_json = output_dir / "pareto_candidates.json"
    pareto_json.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "campaign": campaign_name,
                "best_candidate_index": best_index,
                "candidate_count": len(documents),
                "candidates": documents,
                "shortlisted_candidate_indices": list(
                    diverse_candidate_indices(
                        result.candidates,
                        max_designs=10,
                        max_harmonic_units=max_harmonic_units,
                        min_margin_percent=min_margin_percent,
                    )
                ),
                "near_feasible": _near_feasible_documents(result, conductor_labels),
                "search_front": _search_front_documents(result, conductor_labels),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    block_csv = output_dir / "best_candidate_geometry.csv"
    rows = block_geometry_rows(best.design, conductor_labels)
    with block_csv.open("w", encoding="utf-8", newline="") as stream:
        csv_rows = tuple(block_geometry_record(row) for row in rows)
        writer = csv.DictWriter(stream, fieldnames=tuple(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)

    from dot.gui.cross_section_plot import cross_section_figure

    cross_section_png = output_dir / "best_candidate_cross_section.png"
    figure = cross_section_figure(best.design)
    figure.savefig(cross_section_png, dpi=160)
    summary_png = output_dir / "best_candidate_summary.png"
    candidate_summary_figure(
        best,
        campaign_name=campaign_name,
        reference_radius_mm=reference_radius_mm,
        conductor_labels=conductor_labels,
        heading="Best certified design",
    ).savefig(summary_png, dpi=180)
    pareto_frontier_png = output_dir / "final_pareto_frontier.png"
    _pareto_frontier_figure(
        result,
        max_harmonic_units=max_harmonic_units,
        min_margin_percent=min_margin_percent,
    ).savefig(pareto_frontier_png, dpi=180)
    shortlist_manifest, selected_designs_dir = _export_design_shortlist(
        output_dir,
        result.candidates,
        campaign_name=campaign_name,
        reference_radius_mm=reference_radius_mm,
        conductor_labels=conductor_labels,
        max_harmonic_units=max_harmonic_units,
        min_margin_percent=min_margin_percent,
        source="certified_pareto_archive",
    )
    return ResultArtifacts(
        best_candidate_json=best_json,
        block_table_csv=block_csv,
        cross_section_png=cross_section_png,
        summary_png=summary_png,
        pareto_json=pareto_json,
        pareto_frontier_png=pareto_frontier_png,
        shortlist_manifest_json=shortlist_manifest,
        selected_designs_dir=selected_designs_dir,
    )


def export_no_candidate_result(
    output_dir: Path,
    result: ParetoResult,
    *,
    campaign_name: str,
    reference_radius_mm: float | None = None,
    conductor_labels: tuple[str, ...] = (),
    max_harmonic_units: float | None = None,
    min_margin_percent: float | None = None,
) -> Path:
    """Persist an honest empty result plus closest-candidate diagnostics."""

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "pareto_candidates.json"
    destination.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "campaign": campaign_name,
                "best_candidate_index": None,
                "candidate_count": 0,
                "candidates": [],
                "near_feasible": _near_feasible_documents(result, conductor_labels),
                "search_front": _search_front_documents(result, conductor_labels),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _pareto_frontier_figure(
        result,
        max_harmonic_units=max_harmonic_units,
        min_margin_percent=min_margin_percent,
    ).savefig(output_dir / "final_pareto_frontier.png", dpi=180)
    if result.search_front:
        _export_design_shortlist(
            output_dir,
            result.search_front,
            campaign_name=campaign_name,
            reference_radius_mm=reference_radius_mm or 0.0,
            conductor_labels=conductor_labels,
            max_harmonic_units=max_harmonic_units,
            min_margin_percent=min_margin_percent,
            source="uncertified_search_front",
        )
    return destination


def _export_design_shortlist(
    output_dir: Path,
    candidates: Sequence[ParetoCandidate],
    *,
    campaign_name: str,
    reference_radius_mm: float,
    conductor_labels: tuple[str, ...],
    max_harmonic_units: float | None,
    min_margin_percent: float | None,
    source: str,
    max_designs: int = 10,
) -> tuple[Path, Path]:
    """Write one flat folder of best-per-topology engineering design sheets."""

    selected = diverse_candidate_indices(
        candidates,
        max_designs=max_designs,
        max_harmonic_units=max_harmonic_units,
        min_margin_percent=min_margin_percent,
    )
    selected_dir = output_dir / "best_topology_designs"
    selected_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, Any]] = []

    for rank, candidate_index in enumerate(selected, start=1):
        candidate = candidates[candidate_index]
        family = _topology_family(candidate.design)
        basename = f"design_{rank:02d}_{family.replace(':', '_')}"
        document = candidate_document(
            candidate,
            campaign_name=campaign_name,
            reference_radius_mm=reference_radius_mm,
            conductor_labels=conductor_labels,
        )
        document.update(
            {
                "shortlist_rank": rank,
                "source_candidate_index": candidate_index,
                "shortlist_source": source,
            }
        )
        candidate_json = selected_dir / f"{basename}.json"
        candidate_json.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        block_csv = selected_dir / f"{basename}_geometry.csv"
        rows = block_geometry_rows(candidate.design, conductor_labels)
        with block_csv.open("w", encoding="utf-8", newline="") as stream:
            csv_rows = tuple(block_geometry_record(row) for row in rows)
            writer = csv.DictWriter(stream, fieldnames=tuple(csv_rows[0]))
            writer.writeheader()
            writer.writerows(csv_rows)
        summary_image = selected_dir / f"{basename}_summary.png"
        candidate_summary_figure(
            candidate,
            campaign_name=campaign_name,
            reference_radius_mm=reference_radius_mm,
            conductor_labels=conductor_labels,
            heading=f"Topology design {rank:02d}",
        ).savefig(summary_image, dpi=180)
        manifest_rows.append(
            {
                "rank": rank,
                "source_candidate_index": candidate_index,
                "certified": candidate.certified,
                "topology_family": family,
                "blocks_per_layer": list(_topology_signature(candidate.design)),
                "total_blocks": _total_blocks(candidate.design),
                "total_turns": _total_turns(candidate.design),
                "worst_harmonic_units": candidate.objectives[0],
                "worst_harmonic_residual_units": candidate.objectives[0],
                "harmonic_targets": {
                    f"b{order}": target for order, target in candidate.harmonic_targets
                },
                "minimum_margin_percent": -candidate.objectives[1],
                "operating_current_a": (
                    candidate.operating_current_a
                    if candidate.operating_current_a is not None
                    else _operating_current(candidate.design)
                ),
                "summary_image": summary_image.name,
                "candidate_json": candidate_json.name,
                "geometry_csv": block_csv.name,
            }
        )
    manifest = selected_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "campaign": campaign_name,
                "source": source,
                "selection_policy": (
                    "best target-ranked representative from each blocks-per-layer topology "
                    "family; up to 10 distinct topologies"
                ),
                "design_count": len(manifest_rows),
                "designs": manifest_rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest, selected_dir


def candidate_summary_figure(
    candidate: ParetoCandidate,
    *,
    campaign_name: str,
    reference_radius_mm: float,
    conductor_labels: tuple[str, ...] = (),
    heading: str = "Candidate design",
) -> Figure:
    """Create one printable sheet with geometry and electromagnetic tables."""

    from dot.gui.cross_section_plot import draw_cross_section

    document = candidate_document(
        candidate,
        campaign_name=campaign_name,
        reference_radius_mm=reference_radius_mm,
        conductor_labels=conductor_labels,
    )
    family = str(document["topology_family"])
    title_parts = [heading, campaign_name, family]
    if candidate.certified:
        title_parts.append("CERTIFIED")
    figure = Figure(figsize=(15.5, 11.0), constrained_layout=True)
    grid = figure.add_gridspec(
        2,
        2,
        height_ratios=(1.75, 1.0),
        width_ratios=(1.08, 0.92),
    )
    cross_section_axes = figure.add_subplot(grid[0, 0])
    electromagnetic_axes = figure.add_subplot(grid[0, 1])
    geometry_axes = figure.add_subplot(grid[1, :])

    figure.suptitle(
        " — ".join(title_parts),
        fontsize=15,
        fontweight="bold",
    )
    draw_cross_section(
        cross_section_axes,
        candidate.design,
        title=(
            f"Cross-section | {document['total_turns']} turns, "
            f"{document['total_blocks']} blocks"
        ),
    )

    electromagnetic_rows = _electromagnetic_summary_rows(document)
    _draw_engineering_table(
        electromagnetic_axes,
        title=f"Electromagnetic results (Rref = {reference_radius_mm:g} mm)",
        columns=("Quantity", "Value"),
        rows=electromagnetic_rows,
        column_widths=(0.62, 0.38),
    )

    geometry_rows = [
        (
            str(row["block"]),
            str(row["layer"]),
            str(row["conductor"] or "—"),
            f"{row['radius_mm']:.6g}",
            str(row["n_turns"]),
            f"{row['phi_deg']:.6g}",
            f"{row['alpha_deg']:.6g}",
        )
        for row in document["blocks"]
    ]
    _draw_engineering_table(
        geometry_axes,
        title="Block geometry",
        columns=(
            "Block",
            "Layer",
            "Conductor",
            "R [mm]",
            "Turns",
            "phi [deg]",
            "alpha [deg]",
        ),
        rows=geometry_rows,
        column_widths=(0.11, 0.08, 0.22, 0.14, 0.10, 0.16, 0.16),
    )
    return figure


def _electromagnetic_summary_rows(document: dict[str, Any]) -> list[tuple[str, str]]:
    rows = [
        ("Bore field", f"{document['bore_field_t']:.6g} T"),
        ("Operating current", f"{document['operating_current_a']:.6g} A"),
        ("Minimum load-line margin", f"{document['minimum_margin_percent']:.6g} %"),
        (
            "Worst harmonic target residual",
            f"{document['worst_harmonic_residual_units']:.6g} units",
        ),
        ("Total turns / blocks", f"{document['total_turns']} / {document['total_blocks']}"),
    ]
    rows.extend(
        (
            f"b{row['order']} actual / target / residual",
            f"{row['normal_units']:.5g} / {row['target_normal_units']:.5g} / "
            f"{row['normal_residual_units']:.5g} units",
        )
        for row in document["harmonics"]
        if row["order"] > 1
    )
    margin_rows = document["margins_by_block"]
    if margin_rows:
        rows.extend(
            (
                f"Block {row['block']} margin / Bpeak",
                f"{row['margin_percent']:.4g} % / {row['peak_field_t']:.5g} T",
            )
            for row in margin_rows
        )
    else:
        rows.extend(
            (
                f"Layer {row['layer']} margin / Bpeak",
                f"{row['margin_percent']:.4g} % / {row['peak_field_t']:.5g} T",
            )
            for row in document["margins_by_layer"]
        )
    return rows


def _draw_engineering_table(
    axes,  # noqa: ANN001
    *,
    title: str,
    columns: tuple[str, ...],
    rows: Sequence[tuple[str, ...]],
    column_widths: tuple[float, ...],
) -> None:
    axes.set_axis_off()
    axes.set_title(title, fontsize=11, fontweight="bold", pad=8)
    table = axes.table(
        cellText=rows,
        colLabels=columns,
        colWidths=column_widths,
        cellLoc="center",
        loc="center",
        bbox=(0.0, 0.0, 1.0, 0.96),
    )
    table.auto_set_font_size(False)
    table.set_fontsize(max(6.4, min(9.2, 145.0 / max(1, len(rows)))))
    for (row_index, _column_index), cell in table.get_celld().items():
        cell.set_edgecolor("#9ca3af")
        cell.set_linewidth(0.5)
        if row_index == 0:
            cell.set_facecolor("#dbeafe")
            cell.set_text_props(fontweight="bold", color="#111827")
        elif row_index % 2 == 0:
            cell.set_facecolor("#f3f4f6")


def _near_feasible_documents(
    result: ParetoResult,
    conductor_labels: tuple[str, ...],
) -> list[dict[str, Any]]:
    return [
        {
            "max_normalized_violation": item.max_violation,
            "normalized_violations": dict(item.normalized_violations),
            "search_objectives": {
                "worst_harmonic_units": item.search_objectives[0],
                "worst_harmonic_residual_units": item.search_objectives[0],
                "minimum_margin_percent": -item.search_objectives[1],
            },
            "harmonic_targets": {
                f"b{order}": target for order, target in item.harmonic_targets
            },
            "blocks": [
                block_geometry_record(row)
                for row in block_geometry_rows(item.design, conductor_labels)
            ],
        }
        for item in result.near_feasible
    ]


def _search_front_documents(
    result: ParetoResult,
    conductor_labels: tuple[str, ...],
) -> list[dict[str, Any]]:
    return [
        {
            "worst_harmonic_units": candidate.objectives[0],
            "worst_harmonic_residual_units": candidate.objectives[0],
            "harmonic_targets": {
                f"b{order}": target for order, target in candidate.harmonic_targets
            },
            "minimum_margin_percent": -candidate.objectives[1],
            "total_turns": _total_turns(candidate.design),
            "blocks": [
                block_geometry_record(row)
                for row in block_geometry_rows(candidate.design, conductor_labels)
            ],
        }
        for candidate in result.search_front
    ]


def _pareto_frontier_figure(
    result: ParetoResult,
    *,
    max_harmonic_units: float | None,
    min_margin_percent: float | None,
) -> Figure:
    """Plot the final harmonic-margin trade-off, colored by total turns."""

    points = list(result.search_front)
    if not points:
        points = list(result.candidates)
    if not points:
        points = [
            ParetoCandidate(
                genome=item.genome,
                design=item.design,
                objectives=item.search_objectives,
            )
            for item in result.near_feasible
        ]

    figure = Figure(figsize=(8.4, 5.4), constrained_layout=True)
    axes = figure.add_subplot(111)
    if points:
        points.sort(key=lambda candidate: candidate.objectives[0])
        harmonic = [candidate.objectives[0] for candidate in points]
        margin = [-candidate.objectives[1] for candidate in points]
        turns = [_total_turns(candidate.design) for candidate in points]
        axes.plot(harmonic, margin, color="#718096", linewidth=1.0, alpha=0.65, zorder=1)
        scatter = axes.scatter(
            harmonic,
            margin,
            c=turns,
            cmap="viridis_r",
            s=52,
            edgecolors="#1a202c",
            linewidths=0.45,
            zorder=2,
        )
        colorbar = figure.colorbar(scatter, ax=axes)
        colorbar.set_label("Total turns (lower is better)")
        if result.candidates:
            axes.scatter(
                [candidate.objectives[0] for candidate in result.candidates],
                [-candidate.objectives[1] for candidate in result.candidates],
                facecolors="none",
                edgecolors="#111827",
                linewidths=1.5,
                s=95,
                label="Certified target-feasible",
                zorder=3,
            )
    else:
        axes.text(
            0.5,
            0.5,
            "No finite hard-feasible final-search points were available",
            ha="center",
            va="center",
            transform=axes.transAxes,
        )

    if max_harmonic_units is not None:
        axes.axvline(
            max_harmonic_units,
            color="#c53030",
            linestyle="--",
            linewidth=1.1,
            label="Harmonic target",
        )
    if min_margin_percent is not None:
        axes.axhline(
            min_margin_percent,
            color="#2f855a",
            linestyle="--",
            linewidth=1.1,
            label="Margin target",
        )
    axes.set_title("Final harmonic-residual / margin Pareto frontier")
    axes.set_xlabel("Worst |normal harmonic - target| [units at reference radius]")
    axes.set_ylabel("Minimum load-line margin [%]")
    axes.grid(True, alpha=0.25)
    handles, labels = axes.get_legend_handles_labels()
    if handles:
        axes.legend(handles, labels, loc="best")
    return figure


def _total_turns(design: DipoleDesign) -> int:
    return sum(block.n_turns for layer in design.layers for block in layer.blocks)


def _total_blocks(design: DipoleDesign) -> int:
    return sum(len(layer.blocks) for layer in design.layers)


def _topology_signature(design: DipoleDesign) -> tuple[int, ...]:
    return tuple(len(layer.blocks) for layer in design.layers)


def _topology_family(design: DipoleDesign) -> str:
    return "blocks:" + "-".join(str(count) for count in _topology_signature(design))


def _candidate_score(
    candidate: ParetoCandidate,
    harmonic_limit: float,
    margin_target: float,
) -> tuple[float, float, int, int]:
    harmonic = candidate.objectives[0]
    margin = -candidate.objectives[1]
    harmonic_ratio = harmonic / harmonic_limit
    margin_ratio = margin / margin_target
    violation = max(0.0, harmonic_ratio - 1.0) + max(0.0, 1.0 - margin_ratio)
    tradeoff = harmonic_ratio + 1.0 / max(margin_ratio, 1.0e-12)
    return (
        violation,
        tradeoff,
        _total_turns(candidate.design),
        _total_blocks(candidate.design),
    )


def _operating_current(design: DipoleDesign) -> float:
    currents = {
        round(abs(block.current_a), 12) for layer in design.layers for block in layer.blocks
    }
    if not currents:
        return 0.0
    if len(currents) != 1:
        raise ValueError("candidate blocks do not carry one series operating current")
    return currents.pop()


def _center_field_t(design: DipoleDesign) -> float:
    sources = tuple(
        source for turn in design.all_turns() for source in place_line_current_sources(turn)
    )
    _bx_t, by_t = field_at(sources, 0.0, 0.0)
    return abs(by_t)


def _clean_float(value: float) -> float:
    rounded = round(value, 12)
    return 0.0 if rounded == 0.0 else rounded

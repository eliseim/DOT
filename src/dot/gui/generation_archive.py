"""Persist per-generation best-candidate snapshots to disk (task 0053).

The live GUI view (task 0052) shows the current best candidate while a
campaign runs, but nothing survives after the process exits or between
generations -- there was no way to go back and inspect how a campaign's best
candidate evolved. ``save_generation_snapshot`` writes one cross-section PNG
plus one characteristics JSON per generation into an output directory, so a
campaign's full search history can be reviewed after the fact.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from dot.geometry import DipoleDesign
from dot.geometry.constraints import first_layer_pole_turn_clearance_mm
from dot.optimize.objectives import BlockMarginRecord, LayerMarginRecord
from dot.results import block_geometry_rows, inter_block_clearance_rows

from .cross_section_plot import cross_section_figure


def save_generation_snapshot(
    output_dir: Path,
    generation: int,
    total_generations: int,
    design: DipoleDesign,
    harmonic_units: float | None,
    margin_percent: float | None,
    operating_current_a: float,
    margin_records: tuple[LayerMarginRecord, ...] = (),
    block_margin_records: tuple[BlockMarginRecord, ...] = (),
    harmonics: tuple[tuple[int, float, float], ...] = (),
    harmonic_targets: tuple[tuple[int, float], ...] = (),
    cable_labels: tuple[str, ...] = (),
) -> Path:
    """Save one generation's best-candidate cross-section PNG and characteristics JSON.

    Returns the path to the written JSON file. ``cable_labels[i]`` (if given)
    annotates layer ``i`` in the per-layer margin breakdown, matching the
    campaign script convention (task 0051).
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"gen_{generation:04d}"

    figure = cross_section_figure(design)
    figure.savefig(output_dir / f"{stem}.png", dpi=110)

    total_turns = sum(block.n_turns for layer in design.layers for block in layer.blocks)
    limiting_layer_index = (
        min(margin_records, key=lambda record: record.margin_percent).layer_index
        if margin_records
        else (
            min(block_margin_records, key=lambda record: record.margin_percent).layer_index
            if block_margin_records
            else None
        )
    )
    target_by_order = dict(harmonic_targets)
    characteristics = {
        "generation": generation,
        "total_generations": total_generations,
        "harmonic_units": harmonic_units,
        "harmonic_residual_units": harmonic_units,
        "harmonic_targets": {
            f"b{order}": target for order, target in harmonic_targets
        },
        "margin_percent": margin_percent,
        "operating_current_a": operating_current_a,
        "total_turns": total_turns,
        "first_layer_pole_turn_clearance_mm": first_layer_pole_turn_clearance_mm(
            design
        ),
        "limiting_layer": limiting_layer_index,
        "per_layer_margin": [
            {
                "cable": cable_labels[record.layer_index] if record.layer_index < len(cable_labels) else None,
                **asdict(record),
            }
            for record in margin_records
        ],
        "harmonics": [
            {
                "order": order,
                "normal_units": normal,
                "target_normal_units": target_by_order.get(order, 0.0),
                "normal_residual_units": normal - target_by_order.get(order, 0.0),
                "skew_units": skew,
            }
            for order, normal, skew in harmonics
            if order >= 3 and order % 2 == 1
        ],
        "per_block_margin": [
            {
                "conductor": (
                    cable_labels[record.layer_index]
                    if record.layer_index < len(cable_labels)
                    else None
                ),
                **asdict(record),
            }
            for record in block_margin_records
        ],
        "blocks": [asdict(row) for row in block_geometry_rows(design, cable_labels)],
        "inter_block_clearances": [
            asdict(row) for row in inter_block_clearance_rows(design)
        ],
    }
    json_path = output_dir / f"{stem}.json"
    json_path.write_text(json.dumps(characteristics, indent=2))
    return json_path

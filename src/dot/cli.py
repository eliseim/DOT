"""Command-line interface for reproducible DOT campaigns."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dot.campaign import load_campaign, result_document
from dot.gui.generation_archive import save_generation_snapshot
from dot.gui.progress_tracking import CampaignProgressTracker, format_duration
from dot.optimize.runner import ParetoResult, merge_pareto_results, run_campaign
from dot.results import (
    best_candidate_index,
    export_campaign_results,
    export_no_candidate_result,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dot", description="2D no-iron dipole target synthesis")
    subparsers = parser.add_subparsers(dest="command", required=True)
    optimize = subparsers.add_parser("optimize", help="run a versioned JSON campaign")
    optimize.add_argument("config", type=Path)
    optimize.add_argument("--output", type=Path, required=True)
    optimize.add_argument("--population", type=int, help="override configured population")
    optimize.add_argument("--generations", type=int, help="override configured generations")
    optimize.add_argument("--seed", type=int, action="append", help="override seeds; repeat for multiple")
    optimize.add_argument("--workers", type=int, help="override configured worker count")
    optimize.add_argument(
        "--quick",
        action="store_true",
        help="pipeline smoke test only: cap population/generations and use the first seed",
    )
    validate = subparsers.add_parser("validate", help="validate a campaign without running it")
    validate.add_argument("config", type=Path)
    subparsers.add_parser("gui", help="open the interactive DOT campaign designer")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "gui":
        from dot.gui.target_synthesis_gui import main as gui_main

        gui_main()
        return 0
    campaign = load_campaign(args.config)
    if args.command == "validate":
        print(
            f"valid campaign {campaign.name!r}: {len(campaign.topology.layers)} layers, "
            f"orders {campaign.targets.harmonic_orders}, seeds {campaign.run.seeds}"
        )
        return 0

    for option_name, value in (
        ("--population", args.population),
        ("--generations", args.generations),
        ("--workers", args.workers),
    ):
        if value is not None and value < 1:
            parser.error(f"{option_name} must be a positive integer")

    configured_population = (
        args.population if args.population is not None else campaign.run.population
    )
    configured_generations = (
        args.generations if args.generations is not None else campaign.run.generations
    )
    configured_seeds = tuple(args.seed) if args.seed else campaign.run.seeds
    population = min(configured_population, 12) if args.quick else configured_population
    generations = min(configured_generations, 3) if args.quick else configured_generations
    seeds = configured_seeds[:1] if args.quick else configured_seeds
    configured_workers = args.workers if args.workers is not None else campaign.run.workers
    workers = 1 if args.quick else min(configured_workers, _worker_limit())
    try:
        _prepare_output_directory(args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    conductor_labels = tuple(str(row["conductor"]) for row in campaign.raw["layers"])
    results: list[ParetoResult] = []
    for seed_index, seed in enumerate(seeds, start=1):
        print(
            f"running seed {seed} ({seed_index}/{len(seeds)}): "
            f"population={population}, generations={generations}",
            flush=True,
        )
        tracker = CampaignProgressTracker(total_generations=generations)
        tracker.start()
        generation_dir = args.output / f"seed_{seed}" / "generations"

        def _on_generation(
            generation,  # noqa: ANN001
            total_generations,  # noqa: ANN001
            design,  # noqa: ANN001
            margin_percent,  # noqa: ANN001
            harmonic_units,  # noqa: ANN001
            family_count,  # noqa: ANN001
        ) -> None:
            tracker.record(generation, margin_percent, harmonic_units, family_count)
            metrics = []
            if harmonic_units is not None:
                metrics.append(f"|b|={harmonic_units:.3g} units")
            if margin_percent is not None:
                metrics.append(f"margin={margin_percent:.3g}%")
            if family_count is not None:
                metrics.append(f"families={family_count}")
            print(
                f"  generation {generation}/{total_generations} "
                f"({100.0 * generation / total_generations:5.1f}%)  "
                f"elapsed {format_duration(tracker.elapsed_seconds)}  "
                f"ETA {format_duration(tracker.eta_seconds)}  "
                + "  ".join(metrics),
                flush=True,
            )
            if design is None:
                return
            try:
                save_generation_snapshot(
                    generation_dir,
                    generation,
                    total_generations,
                    design,
                    harmonic_units,
                    margin_percent,
                    _design_current(design),
                    cable_labels=conductor_labels,
                )
            except (OSError, ValueError) as exc:
                print(f"  warning: could not save generation snapshot: {exc}", flush=True)

        result = run_campaign(
            campaign.topology,
            campaign.targets,
            campaign.feasibility,
            pop_size=population,
            n_gen=generations,
            seed=seed,
            n_workers=workers,
            on_generation=_on_generation,
        )
        print(f"seed {seed}: {len(result.candidates)} certified Pareto candidates")
        if not result.candidates and result.near_feasible:
            closest = result.near_feasible[0]
            active = ", ".join(
                f"{name}={value:.3g}"
                for name, value in closest.normalized_violations
                if value > 0.0
            )
            print(f"seed {seed}: closest search candidate violations: {active or 'certification only'}")
        results.append(result)
    merged = merge_pareto_results(
        results,
        campaign.topology,
        campaign.targets,
        campaign.feasibility,
    )
    destination = args.output / "pareto.json"
    document = result_document(campaign, merged, quick=args.quick)
    document["executed_run"] = {
        "population": population,
        "generations": generations,
        "seeds": seeds,
        "workers": workers,
    }
    destination.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    if merged.candidates:
        representative_index = best_candidate_index(
            merged,
            max_harmonic_units=campaign.targets.max_harmonic_units,
            min_margin_percent=campaign.targets.min_margin_percent,
        )
        artifacts = export_campaign_results(
            args.output,
            merged,
            best_index=representative_index,
            campaign_name=campaign.name,
            reference_radius_mm=campaign.targets.r_ref_mm,
            conductor_labels=conductor_labels,
            max_harmonic_units=campaign.targets.max_harmonic_units,
            min_margin_percent=campaign.targets.min_margin_percent,
        )
        print(f"best cross-section: {artifacts.cross_section_png}")
        print(f"Block geometry table: {artifacts.block_table_csv}")
        print(f"Pareto frontier: {artifacts.pareto_frontier_png}")
        print(f"topology-diverse shortlist: {artifacts.shortlist_manifest_json}")
    else:
        export_no_candidate_result(
            args.output,
            merged,
            campaign_name=campaign.name,
            reference_radius_mm=campaign.targets.r_ref_mm,
            conductor_labels=conductor_labels,
            max_harmonic_units=campaign.targets.max_harmonic_units,
            min_margin_percent=campaign.targets.min_margin_percent,
        )
    print(f"wrote {destination} ({len(merged.candidates)} certified candidates)")
    return 0 if merged.candidates or args.quick else 2


def _design_current(design) -> float:  # noqa: ANN001
    for layer in design.layers:
        for block in layer.blocks:
            return abs(block.current_a)
    return 0.0


def _worker_limit() -> int:
    hardware_limit = max(1, os.cpu_count() or 1)
    return min(hardware_limit, 61) if os.name == "nt" else hardware_limit


def _prepare_output_directory(output: Path) -> None:
    """Create a new run directory or reject a path containing stale artifacts."""

    if output.exists():
        if not output.is_dir():
            raise ValueError(f"output path is not a directory: {output}")
        if any(output.iterdir()):
            raise ValueError(
                f"output directory must be empty so results cannot mix with an earlier run: {output}"
            )
        return
    output.mkdir(parents=True)


if __name__ == "__main__":
    raise SystemExit(main())

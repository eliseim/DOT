"""Repeatable end-to-end acceleration benchmark for a short DOT search.

This intentionally exercises sampling, repair, geometry, field/margin
physics, NSGA-II, and certification. It is a throughput benchmark, not a
convergence campaign.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from dot.campaign import load_campaign
from dot.optimize.runner import run_campaign

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--population", type=int, default=24)
    parser.add_argument("--generations", type=int, default=4)
    parser.add_argument("--seed", type=int, default=17)
    args = parser.parse_args()

    campaign = load_campaign(ROOT / "tests/fixtures/7T_NbTi_headless.json")
    started = time.perf_counter()
    result = run_campaign(
        campaign.topology,
        campaign.targets,
        campaign.feasibility,
        pop_size=args.population,
        n_gen=args.generations,
        seed=args.seed,
        n_workers=args.workers if args.workers > 1 else None,
    )
    elapsed = time.perf_counter() - started
    print(
        f"workers={args.workers} population={args.population} "
        f"generations={args.generations} seconds={elapsed:.6f} "
        f"certified={len(result.candidates)} search_front={len(result.search_front)}"
    )
    print("objectives=", [candidate.objectives for candidate in result.search_front])


if __name__ == "__main__":
    main()

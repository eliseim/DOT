"""Topology-family diversity preservation for NSGA-II survival.

Plain rank-and-crowding selection can let one decoded phenotype (active-
block pattern per layer) dominate the population before structurally
different candidates get a fair shot at reaching feasibility -- a
plausible contributor to a campaign getting stuck near, but never at, a
feasible result. Ports dipole_designer's own topology-family survival
mechanism: cap how many survivors may share a family each generation, and
guarantee a floor of distinct families survive by seeding one
representative per missing family before the normal rank/crowding fill.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from pymoo.core.population import Population
from pymoo.core.survival import split_by_feasibility
from pymoo.operators.survival.rank_and_crowding.classes import RankAndCrowding
from pymoo.util import default_random_state
from pymoo.util.randomized_argsort import randomized_argsort

from dot.geometry import DipoleDesign

if TYPE_CHECKING:
    from .genome import Topology


def topology_family(design: DipoleDesign) -> str:
    """Fingerprint a decoded design's phenotype by active-block count per layer.

    DOT's counterpart to dipole_designer's ``fingerprint_mode="blocks"``
    (the turn-count-inclusive ``"blocks_turns"`` mode is not ported: turn
    counts change continuously during search, so including them would
    fragment families far more than the block pattern that actually
    defines a topology's structural identity).
    """

    return "blocks:" + ",".join(str(len(layer.blocks)) for layer in design.layers)


@dataclass(frozen=True, slots=True)
class TopologySurvivalConfig:
    """Settings for :class:`TopologyAwareRankAndCrowding`."""

    enabled: bool = False
    max_survivors_per_family: int | None = None
    min_families: int = 4


def recommended_topology_survival_config(
    topology: Topology,
    pop_size: int,
) -> TopologySurvivalConfig:
    """Return DOT's population-scaled topology-diversity policy.

    The same policy is shared by GUI and command-line campaigns so equivalent
    inputs cannot silently use different NSGA-II survival behavior.
    """

    possible_families = math.prod(
        layer.n_blocks - layer.min_blocks + 1 for layer in topology.layers
    )
    family_floor = min(
        possible_families,
        pop_size,
        max(4, min(32, pop_size // 4)),
    )
    if possible_families <= 1 or family_floor <= 1:
        return TopologySurvivalConfig(enabled=False)
    return TopologySurvivalConfig(
        enabled=True,
        min_families=family_floor,
        max_survivors_per_family=max(1, math.ceil(pop_size / family_floor)),
    )


class TopologyAwareRankAndCrowding(RankAndCrowding):
    """Rank-and-crowding survival with a per-generation topology-family quota.

    Behaves exactly like pymoo's ``RankAndCrowding`` when
    ``config.enabled`` is ``False`` (the default), so it is a safe drop-in
    ``survival=`` for :func:`dot.optimize.runner._mixed_variable_nsga2`.
    When enabled: build the same rank/crowding-ordered candidate list the
    base class would fill survivors from, then fill it in two passes --
    first seed one representative of each not-yet-seen family (up to
    ``min_families``) so a family floor survives regardless of its
    individuals' crowding rank, then fill the remaining slots in
    rank/crowding order while respecting ``max_survivors_per_family``.
    If those quota-respecting passes can't fill every slot (too few
    distinct families, or per-family caps too tight for the population
    size), fall back to an unquota'd fill from the same ordered candidate
    list so ``n_survive`` is always met.
    """

    def __init__(self, config: TopologySurvivalConfig, nds=None, crowding_func: str = "cd") -> None:
        super().__init__(nds=nds, crowding_func=crowding_func)
        self.config = config

    @default_random_state
    def do(
        self,
        problem,
        pop,
        *args,
        n_survive=None,
        random_state=None,
        return_indices=False,
        **kwargs,
    ):  # noqa: ANN001, ANN003
        """Preserve topology families without weakening constraint precedence.

        Pymoo normally removes infeasible individuals before calling ``_do``.
        That keeps feasible designs first, but used to bypass DOT's topology
        quota during the common all-infeasible early generations.  Select the
        feasible pool first and then apply the same family-aware policy to the
        constraint-violation-ordered infeasible remainder.
        """

        if not self.config.enabled:
            return super().do(
                problem,
                pop,
                *args,
                n_survive=n_survive,
                random_state=random_state,
                return_indices=return_indices,
                **kwargs,
            )
        if len(pop) == 0:
            return [] if return_indices else pop

        n_survive = min(len(pop), len(pop) if n_survive is None else n_survive)
        families = pop.get("topology_family")
        if families is None:
            return super().do(
                problem,
                pop,
                *args,
                n_survive=n_survive,
                random_state=random_state,
                return_indices=return_indices,
                **kwargs,
            )

        selected_indices: list[int] = []
        family_counts: dict[str, int] = {}
        if problem is not None and problem.has_constraints():
            feasible, infeasible = split_by_feasibility(pop, sort_infeas_by_cv=True)
            if len(feasible):
                feasible_survivors = self._do(
                    problem,
                    pop[feasible],
                    *args,
                    n_survive=min(len(feasible), n_survive),
                    random_state=random_state,
                    **kwargs,
                )
                original_index = {
                    individual: int(index) for index, individual in enumerate(pop)
                }
                selected_indices.extend(
                    original_index[individual] for individual in feasible_survivors
                )
                for index in selected_indices:
                    family = str(families[index])
                    family_counts[family] = family_counts.get(family, 0) + 1

            remaining = n_survive - len(selected_indices)
            if remaining > 0:
                selected_indices.extend(
                    self._quota_fill(
                        [int(index) for index in infeasible],
                        families,
                        remaining,
                        initial_family_counts=family_counts,
                    )
                )
        else:
            selected_indices = self._do(
                problem,
                pop,
                *args,
                n_survive=n_survive,
                random_state=random_state,
                **kwargs,
            )
            if return_indices:
                original_index = {
                    individual: int(index) for index, individual in enumerate(pop)
                }
                return [original_index[individual] for individual in selected_indices]
            return selected_indices

        if return_indices:
            return selected_indices
        return pop[selected_indices] if selected_indices else Population()

    def _do(self, problem, pop, *args, random_state=None, n_survive=None, **kwargs):  # noqa: ANN001, ANN003
        if not self.config.enabled:
            return super()._do(problem, pop, *args, random_state=random_state, n_survive=n_survive, **kwargs)

        families = pop.get("topology_family")
        if families is None:
            # topology_family wasn't attached during evaluation -- degrade
            # to plain rank-and-crowding rather than crash.
            return super()._do(problem, pop, *args, random_state=random_state, n_survive=n_survive, **kwargs)

        F = pop.get("F").astype(float, copy=False)
        # Unlike the base class, do NOT pass n_stop_if_ranked=n_survive here:
        # that truncates sorting once enough individuals are ranked to cover
        # n_survive, which can leave a minority family's individual (sitting
        # in a worse front) never ranked at all -- the quota mechanism below
        # can only preserve diversity among individuals it can see.
        fronts = self.nds.do(F)

        ordered_indices: list[int] = []
        for k, front in enumerate(fronts):
            crowding_of_front = self.crowding_func.do(F[front, :], n_remove=0)
            order = randomized_argsort(
                crowding_of_front, order="descending", method="numpy", random_state=random_state
            )
            for j, i in zip(order, np.asarray(front)[order], strict=True):
                pop[i].set("rank", k)
                pop[i].set("crowding", crowding_of_front[j])
                ordered_indices.append(int(i))

        survivors = self._quota_fill(ordered_indices, families, n_survive)
        return pop[survivors]

    def _quota_fill(
        self,
        ordered_indices: list[int],
        families: np.ndarray,
        n_survive: int,
        *,
        initial_family_counts: dict[str, int] | None = None,
    ) -> list[int]:
        survivors: list[int] = []
        family_counts = dict(initial_family_counts or {})
        seen_families = set(family_counts)

        # Pass 1: one representative per not-yet-seen family, best-ranked
        # first, up to min_families -- guarantees the diversity floor.
        for i in ordered_indices:
            if len(survivors) >= n_survive or len(seen_families) >= self.config.min_families:
                break
            family = str(families[i])
            if family in seen_families:
                continue
            survivors.append(i)
            seen_families.add(family)
            family_counts[family] = family_counts.get(family, 0) + 1

        # Pass 2: normal rank/crowding fill, respecting the per-family cap.
        survivors_set = set(survivors)
        cap = self.config.max_survivors_per_family
        for i in ordered_indices:
            if len(survivors) >= n_survive:
                break
            if i in survivors_set:
                continue
            family = str(families[i])
            if cap is not None and family_counts.get(family, 0) >= cap:
                continue
            survivors.append(i)
            survivors_set.add(i)
            family_counts[family] = family_counts.get(family, 0) + 1

        # Fallback: quotas left slots unfilled (too few families, or caps
        # too tight for this population size) -- fill unquota'd from the
        # same ordered candidates so n_survive is always met.
        if len(survivors) < n_survive:
            for i in ordered_indices:
                if len(survivors) >= n_survive:
                    break
                if i in survivors_set:
                    continue
                survivors.append(i)
                survivors_set.add(i)

        return survivors[:n_survive]

from __future__ import annotations

import queue

import pytest

from dot.conductors import CableRecord, StrandRecord, Type1FitCoefficients
from dot.geometry import CableSpec
from dot.gui.campaign_runner import (
    CampaignEvent,
    CampaignRunner,
    _gui_topology_survival_config,
)
from dot.optimize import LayerConductorData, LayerTopology, Topology
from dot.optimize.problem import FeasibilitySettings, OptimizationTargets
from dot.optimize.runner import ParetoResult, run_campaign


def test_campaign_runner_returns_progress_and_same_result_as_direct_call() -> None:
    topology = _topology()
    targets = _targets()
    feasibility = _feasibility()
    runner = CampaignRunner()

    events = runner.start(
        topology=topology,
        targets=targets,
        feasibility=feasibility,
        pop_size=8,
        n_gen=3,
        seed=7,
    )
    runner.join(timeout=20.0)

    collected = _drain(events)
    direct = run_campaign(
        topology,
        targets,
        feasibility,
        pop_size=8,
        n_gen=3,
        seed=7,
        topology_survival=_gui_topology_survival_config(topology, 8),
        adaptive_offspring=True,
    )
    result_events = [event for event in collected if event.kind == "result"]

    assert [event.kind for event in collected].count("progress") >= 2
    assert result_events
    assert [
        candidate.objectives for candidate in result_events[-1].result.candidates
    ] == pytest.approx([candidate.objectives for candidate in direct.candidates])

    # task 0052: live per-generation best-candidate events (dd-parity GUI feature).
    generation_events = [event for event in collected if event.kind == "generation"]
    assert len(generation_events) == 3
    assert [event.generation for event in generation_events] == [1, 2, 3]
    assert all(event.total_generations == 3 for event in generation_events)

    # task 0056: live progress dashboard -- ETA/elapsed/history wiring.
    assert generation_events[0].elapsed_seconds is not None
    assert generation_events[0].elapsed_seconds >= 0.0
    # The tracker starts before generation 1, so the first generation already
    # supplies one duration for the ETA.
    assert generation_events[0].eta_seconds is not None
    assert generation_events[1].eta_seconds is not None
    assert generation_events[1].eta_seconds >= 0.0
    # history is the tracker's full, growing history -- the LAST event's
    # history must contain all 3 generations, in order.
    assert [record.generation for record in generation_events[-1].history] == [1, 2, 3]
    assert all(record.total_turns is not None for record in generation_events[-1].history)
    assert all(event.harmonics for event in generation_events if event.design is not None)
    assert all(event.margin_by_block for event in generation_events if event.design is not None)
    assert all(
        event.margin_by_block[0].roxie_block == 1
        for event in generation_events
        if event.margin_by_block
    )


def test_gui_enables_population_scaled_topology_preservation() -> None:
    topology = _topology()

    config = _gui_topology_survival_config(topology, 8)

    assert config.enabled is True
    assert config.min_families == 2
    assert config.max_survivors_per_family == 4


def test_cth_sized_gui_campaign_preserves_32_topology_families() -> None:
    cable = CableSpec(width_mm=1.5, height_mm=18.0, insulation_thickness_mm=0.1)
    block_limits = (4, 4, 3, 2)
    topology = Topology(
        aperture_radius_mm=25.0,
        layers=tuple(
            LayerTopology(
                cable_id="c",
                n_blocks=n_blocks,
                inner_radius_bounds_mm=(25.0 + 20.0 * index,) * 2,
                phi_bounds_deg=(0.0, 90.0),
                n_turns_bounds=(2, 25),
            )
            for index, n_blocks in enumerate(block_limits)
        ),
        cables={"c": cable},
    )

    config = _gui_topology_survival_config(topology, 250)

    assert config.enabled is True
    assert config.min_families == 32
    assert config.max_survivors_per_family == 8


def test_request_stop_reports_generation_boundary_cancellation() -> None:
    runner = CampaignRunner()

    runner.request_stop()

    event = runner.events.get_nowait()
    assert event.kind == "progress"
    assert "after the current generation" in event.message


def test_campaign_runner_forwards_optional_process_count(monkeypatch) -> None:  # noqa: ANN001
    import dot.gui.campaign_runner as campaign_runner_module

    captured = {}

    def fake_run_campaign(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        captured["n_workers"] = kwargs.get("n_workers")
        return ParetoResult(candidates=())

    monkeypatch.setattr(campaign_runner_module, "run_campaign", fake_run_campaign)
    runner = CampaignRunner()
    runner.start(
        topology=_topology(),
        targets=_targets(),
        feasibility=_feasibility(),
        pop_size=8,
        n_gen=2,
        seed=7,
        n_workers=3,
    )
    runner.join(timeout=5.0)

    assert captured["n_workers"] == 3


def _drain(events: queue.Queue[CampaignEvent]) -> list[CampaignEvent]:
    drained = []
    while True:
        try:
            drained.append(events.get_nowait())
        except queue.Empty:
            return drained


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


def _targets() -> OptimizationTargets:
    return OptimizationTargets(
        target_bore_field_t=0.01,
        r_ref_mm=5.0,
        max_order=4,
        cadata_by_layer=(_conductor_data(),),
        temperature_k=0.0,
    )


def _feasibility() -> FeasibilitySettings:
    return FeasibilitySettings(min_gap_mm=0.1, max_angle_deg=80.0)


def _conductor_data() -> LayerConductorData:
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

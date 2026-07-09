from __future__ import annotations

import queue

import pytest

from dot.conductors import CableRecord, StrandRecord, Type1FitCoefficients
from dot.geometry import CableSpec
from dot.gui.campaign_runner import CampaignEvent, CampaignRunner
from dot.optimize import LayerConductorData, LayerTopology, Topology
from dot.optimize.problem import FeasibilitySettings, OptimizationTargets
from dot.optimize.runner import run_campaign


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
    direct = run_campaign(topology, targets, feasibility, pop_size=8, n_gen=3, seed=7)
    result_events = [event for event in collected if event.kind == "result"]

    assert [event.kind for event in collected].count("progress") >= 2
    assert result_events
    assert [candidate.objectives for candidate in result_events[-1].result.candidates] == pytest.approx(
        [candidate.objectives for candidate in direct.candidates]
    )


def test_request_stop_reports_nonblocking_limitation() -> None:
    runner = CampaignRunner()

    runner.request_stop()

    event = runner.events.get_nowait()
    assert event.kind == "progress"
    assert "will finish in the background" in event.message


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

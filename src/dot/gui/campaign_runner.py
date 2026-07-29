"""Threaded campaign execution for the Tkinter GUI."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from dot.geometry import DipoleDesign
from dot.optimize.genome import Topology
from dot.optimize.objectives import (
    BlockMarginRecord,
    EvaluationFidelity,
    LayerMarginRecord,
    harmonic_table,
    load_line_margin_by_block_detail,
)
from dot.optimize.problem import FeasibilitySettings, OptimizationTargets
from dot.optimize.runner import CampaignCancelled, ParetoResult, run_campaign
from dot.optimize.topology_survival import (
    TopologySurvivalConfig,
    recommended_topology_survival_config,
)

from .progress_tracking import CampaignProgressTracker, GenerationRecord


@dataclass(frozen=True, slots=True)
class CampaignEvent:
    """Message sent from the worker thread to the GUI event queue."""

    kind: str
    message: str
    generation: int | None = None
    total_generations: int | None = None
    result: ParetoResult | None = None
    error: BaseException | None = None
    # Live per-generation best-candidate view (kind="generation").
    design: DipoleDesign | None = None
    margin_percent: float | None = None
    # Live progress dashboard: harmonic signal plus best-design turn history
    # for the convergence chart, and the tracker's full history + ETA for the
    # elapsed/ETA/progress-bar readout. ``history`` is the SAME list object
    # every "generation" event this run, growing in place, so a listener can
    # just re-read it rather than reassembling it event-by-event.
    harmonic_units: float | None = None
    topology_family_count: int | None = None
    elapsed_seconds: float | None = None
    eta_seconds: float | None = None
    history: tuple[GenerationRecord, ...] = ()
    harmonics: tuple[tuple[int, float, float], ...] = ()
    margin_by_layer: tuple[LayerMarginRecord, ...] = ()
    margin_by_block: tuple[BlockMarginRecord, ...] = ()
    evaluation_fidelity: EvaluationFidelity | None = None


class CampaignRunner:
    """Run ``run_campaign`` on a worker thread and publish queue events."""

    def __init__(self) -> None:
        self.events: queue.Queue[CampaignEvent] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_requested = threading.Event()
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    def start(
        self,
        *,
        topology: Topology,
        targets: OptimizationTargets,
        feasibility: FeasibilitySettings,
        pop_size: int,
        n_gen: int,
        seed: int | None,
        n_workers: int | None = None,
    ) -> queue.Queue[CampaignEvent]:
        """Start NSGA-II only and return the event queue for polling."""

        with self._lock:
            if self.is_running:
                raise RuntimeError("campaign is already running")
            self._clear_events()
            self._stop_requested.clear()
            self._thread = threading.Thread(
                target=self._run,
                kwargs={
                    "topology": topology,
                    "targets": targets,
                    "feasibility": feasibility,
                    "pop_size": pop_size,
                    "n_gen": n_gen,
                    "seed": seed,
                    "n_workers": n_workers,
                },
                daemon=True,
                name="dot-campaign-runner",
            )
            self._thread.start()
        return self.events

    def request_stop(self) -> None:
        """Request a cooperative stop after the active generation."""

        self._stop_requested.set()
        self.events.put(
            CampaignEvent(
                kind="progress",
                message="Stop requested; campaign will stop after the current generation.",
            )
        )

    def join(self, timeout: float | None = None) -> None:
        """Wait for the worker thread, if one has been started."""

        thread = self._thread
        if thread is not None:
            thread.join(timeout)

    def _run(
        self,
        *,
        topology: Topology,
        targets: OptimizationTargets,
        feasibility: FeasibilitySettings,
        pop_size: int,
        n_gen: int,
        seed: int | None,
        n_workers: int | None = None,
    ) -> None:
        self.events.put(
            CampaignEvent(
                kind="progress",
                message=f"generation 0/{n_gen} evaluated",
                generation=0,
                total_generations=n_gen,
            )
        )

        tracker = CampaignProgressTracker(total_generations=n_gen)
        tracker.start()

        def _on_generation(
            generation, total_generations, design, margin_percent, harmonic_units, family_count
        ):  # noqa: ANN001
            harmonics: tuple[tuple[int, float, float], ...] = ()
            margin_by_layer: tuple[LayerMarginRecord, ...] = ()
            margin_by_block: tuple[BlockMarginRecord, ...] = ()
            displayed_margin_percent: float | None = None
            displayed_harmonic_units: float | None = None
            evaluation_fidelity: EvaluationFidelity | None = None
            if (
                design is not None
                and margin_percent is not None
                and harmonic_units is not None
            ):
                evaluation_fidelity = targets.certification_fidelity
                try:
                    harmonics = harmonic_table(
                        design,
                        targets.r_ref_mm,
                        targets.max_order,
                        targets.certification_fidelity,
                    )
                    displayed_harmonic_units = _worst_harmonic_residual(
                        harmonics,
                        targets,
                    )
                except (KeyError, ValueError, ZeroDivisionError):
                    harmonics = ()
                    displayed_harmonic_units = None
                try:
                    margin_by_block = load_line_margin_by_block_detail(
                        design,
                        targets.cadata_by_layer,
                        targets.temperature_k,
                        fidelity=targets.certification_fidelity,
                    )
                    margin_by_layer = _layer_margins_from_blocks(margin_by_block)
                    if margin_by_layer:
                        displayed_margin_percent = min(
                            record.margin_percent for record in margin_by_layer
                        )
                except (KeyError, ValueError, ZeroDivisionError):
                    margin_by_layer = ()
                    margin_by_block = ()
                    displayed_margin_percent = None
            total_turns = (
                sum(
                    block.n_turns
                    for layer in design.layers
                    for block in layer.blocks
                )
                if design is not None
                else None
            )
            # Include the requested per-block/per-harmonic diagnostic cost in
            # elapsed time and ETA; otherwise the first ETA is systematically
            # optimistic and every callback is charged to the next generation.
            tracker.record(
                generation,
                displayed_margin_percent,
                displayed_harmonic_units,
                family_count,
                total_turns=total_turns,
            )
            if displayed_margin_percent is not None:
                message = (
                    f"generation {generation}/{total_generations}: selected candidate "
                    f"margin {displayed_margin_percent:.2f}%"
                )
                if displayed_harmonic_units is not None:
                    message += (
                        ", harmonic residual "
                        f"{displayed_harmonic_units:.2f} units"
                    )
                else:
                    message += ", harmonic diagnostic unavailable"
            elif displayed_harmonic_units is not None:
                message = (
                    f"generation {generation}/{total_generations}: selected candidate "
                    "harmonic residual "
                    f"{displayed_harmonic_units:.2f} units, margin diagnostic unavailable"
                )
            elif design is not None:
                message = (
                    f"generation {generation}/{total_generations}: selected geometry "
                    "has no physical results available yet"
                )
            else:
                message = (
                    f"generation {generation}/{total_generations}: "
                    "no physical candidate yet"
                )
            self.events.put(
                CampaignEvent(
                    kind="generation",
                    message=message,
                    generation=generation,
                    total_generations=total_generations,
                    design=design,
                    margin_percent=displayed_margin_percent,
                    harmonic_units=displayed_harmonic_units,
                    topology_family_count=family_count,
                    elapsed_seconds=tracker.elapsed_seconds,
                    eta_seconds=tracker.eta_seconds,
                    history=tuple(tracker.history),
                    harmonics=harmonics,
                    margin_by_layer=margin_by_layer,
                    margin_by_block=margin_by_block,
                    evaluation_fidelity=evaluation_fidelity,
                )
            )

        try:
            topology_survival = _gui_topology_survival_config(topology, pop_size)
            if topology_survival.enabled:
                self.events.put(
                    CampaignEvent(
                        kind="progress",
                        message=(
                            "Topology preservation enabled: target at least "
                            f"{topology_survival.min_families} active-block families "
                            "when available; "
                            "feasibility-aware offspring regeneration enabled."
                        ),
                    )
                )
            result = run_campaign(
                topology,
                targets,
                feasibility,
                pop_size=pop_size,
                n_gen=n_gen,
                seed=seed,
                on_generation=_on_generation,
                should_stop=self._stop_requested.is_set,
                n_workers=n_workers,
            )
        except CampaignCancelled as exc:
            self.events.put(CampaignEvent(kind="cancelled", message=str(exc)))
            return
        except Exception as exc:  # pragma: no cover - defensive handoff to GUI.
            message = str(exc)
            if n_workers is not None and n_workers > 1:
                message += (
                    " Parallel candidate evaluation was enabled; retry with that option "
                    "off if this hardware or security policy blocks worker processes."
                )
            self.events.put(CampaignEvent(kind="error", message=message, error=exc))
            return

        if self._stop_requested.is_set():
            self.events.put(
                CampaignEvent(
                    kind="progress",
                    message="Stop request noted after optimizer returned.",
                    generation=n_gen,
                    total_generations=n_gen,
                )
            )
        self.events.put(CampaignEvent(kind="progress", message="NSGA-II optimization complete."))
        self.events.put(CampaignEvent(kind="result", message="NSGA-II campaign finished", result=result))

    def _clear_events(self) -> None:
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                return


def _gui_topology_survival_config(
    topology: Topology,
    pop_size: int,
) -> TopologySurvivalConfig:
    """Backward-compatible GUI alias for the shared campaign policy."""

    return recommended_topology_survival_config(topology, pop_size)


def _worst_harmonic_residual(
    harmonics: tuple[tuple[int, float, float], ...],
    targets: OptimizationTargets,
) -> float:
    """Reduce an already evaluated harmonic table using campaign semantics."""

    target_by_order = dict(targets.harmonic_targets)
    if targets.harmonic_orders:
        wanted = set(targets.harmonic_orders)
        values = [
            abs(normal - target_by_order.get(order, 0.0))
            for order, normal, _skew in harmonics
            if order in wanted
        ]
    else:
        values = [
            value
            for order, normal, skew in harmonics
            if order >= 2
            for value in (abs(normal), abs(skew))
        ]
    if not values:
        raise ValueError("harmonic table contains no requested orders")
    return max(values)


def _layer_margins_from_blocks(
    records: tuple[BlockMarginRecord, ...],
) -> tuple[LayerMarginRecord, ...]:
    """Derive per-layer limiting records without repeating the peak-field solve."""

    limiting_by_layer: dict[int, BlockMarginRecord] = {}
    for record in records:
        current = limiting_by_layer.get(record.layer_index)
        if current is None or record.margin_percent < current.margin_percent:
            limiting_by_layer[record.layer_index] = record
    return tuple(
        LayerMarginRecord(
            layer_index=record.layer_index,
            peak_field_t=record.peak_field_t,
            operating_current_a=record.operating_current_a,
            short_sample_current_a=record.short_sample_current_a,
            margin_percent=record.margin_percent,
        )
        for _layer_index, record in sorted(limiting_by_layer.items())
    )

"""Threaded campaign execution for the Tkinter GUI."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass

from dot.optimize.genome import Topology
from dot.optimize.problem import FeasibilitySettings, OptimizationTargets
from dot.optimize.runner import ParetoResult, run_campaign


@dataclass(frozen=True, slots=True)
class CampaignEvent:
    """Message sent from the worker thread to the GUI event queue."""

    kind: str
    message: str
    generation: int | None = None
    total_generations: int | None = None
    result: ParetoResult | None = None
    error: BaseException | None = None


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
    ) -> queue.Queue[CampaignEvent]:
        """Start a campaign and return the event queue for polling."""

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
                },
                daemon=True,
                name="dot-campaign-runner",
            )
            self._thread.start()
        return self.events

    def request_stop(self) -> None:
        """Request a cooperative stop.

        The current optimizer wrapper does not expose a callback or cancellation
        hook, so this records intent and reports the limitation without killing
        the thread.
        """

        self._stop_requested.set()
        self.events.put(
            CampaignEvent(
                kind="progress",
                message="Stop requested; current optimizer call will finish in the background.",
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
    ) -> None:
        self.events.put(
            CampaignEvent(
                kind="progress",
                message=f"generation 0/{n_gen} evaluated",
                generation=0,
                total_generations=n_gen,
            )
        )
        try:
            result = run_campaign(
                topology,
                targets,
                feasibility,
                pop_size=pop_size,
                n_gen=n_gen,
                seed=seed,
            )
        except Exception as exc:  # pragma: no cover - defensive handoff to GUI.
            self.events.put(CampaignEvent(kind="error", message=str(exc), error=exc))
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
        self.events.put(
            CampaignEvent(
                kind="progress",
                message=f"generation {n_gen}/{n_gen} evaluated",
                generation=n_gen,
                total_generations=n_gen,
            )
        )
        self.events.put(CampaignEvent(kind="result", message="campaign finished", result=result))

    def _clear_events(self) -> None:
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                return

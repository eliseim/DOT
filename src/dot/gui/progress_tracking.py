"""Live campaign progress tracking: ETA and generation history.

The tracker is independent of Tkinter so timing and convergence history can
be shared safely by the campaign worker and GUI.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class GenerationRecord:
    """One generation's snapshot for the live convergence chart."""

    generation: int
    total_generations: int
    elapsed_seconds: float
    margin_percent: float | None
    harmonic_units: float | None
    topology_family_count: int | None
    total_turns: int | None = None


@dataclass(slots=True)
class CampaignProgressTracker:
    """Tracks generation timing/history and estimates time-to-completion.

    ETA uses a moving average over the last ``eta_window`` generation
    DURATIONS (not total-elapsed / generations-done), since this session's
    own campaigns showed per-generation cost can drift substantially as
    turn counts grow during a run -- an average over ALL generations from
    generation 1 would lag that drift and under/over-estimate badly late
    in a campaign. A short window tracks the CURRENT pace instead.
    """

    total_generations: int
    eta_window: int = 10
    _start_time: float | None = field(default=None, init=False)
    _last_generation_time: float | None = field(default=None, init=False)
    _durations: deque[float] = field(default_factory=deque, init=False)
    history: list[GenerationRecord] = field(default_factory=list, init=False)

    def start(self, *, now: float | None = None) -> None:
        """Start wall-clock tracking before the first generation begins."""

        timestamp = time.monotonic() if now is None else now
        self._start_time = timestamp
        self._last_generation_time = timestamp
        self._durations.clear()
        self.history.clear()

    def record(
        self,
        generation: int,
        margin_percent: float | None,
        harmonic_units: float | None,
        topology_family_count: int | None,
        *,
        total_turns: int | None = None,
        now: float | None = None,
    ) -> GenerationRecord:
        """Record one generation's completion; call once per generation, in order."""

        now = time.monotonic() if now is None else now
        if self._start_time is None:
            self._start_time = now
        if self._last_generation_time is not None:
            duration = now - self._last_generation_time
            self._durations.append(duration)
            while len(self._durations) > self.eta_window:
                self._durations.popleft()
        self._last_generation_time = now

        record = GenerationRecord(
            generation=generation,
            total_generations=self.total_generations,
            elapsed_seconds=now - self._start_time,
            margin_percent=margin_percent,
            harmonic_units=harmonic_units,
            topology_family_count=topology_family_count,
            total_turns=total_turns,
        )
        self.history.append(record)
        return record

    @property
    def elapsed_seconds(self) -> float | None:
        if self._start_time is None or self._last_generation_time is None:
            return None
        return self._last_generation_time - self._start_time

    @property
    def average_generation_seconds(self) -> float | None:
        if not self._durations:
            return None
        return sum(self._durations) / len(self._durations)

    @property
    def eta_seconds(self) -> float | None:
        """Estimated remaining wall-clock time, or ``None`` if not yet estimable."""

        if not self.history:
            return None
        average = self.average_generation_seconds
        if average is None:
            return None
        remaining_generations = self.total_generations - self.history[-1].generation
        if remaining_generations <= 0:
            return 0.0
        return average * remaining_generations

    @property
    def progress_fraction(self) -> float:
        if self.total_generations <= 0 or not self.history:
            return 0.0
        return min(1.0, self.history[-1].generation / self.total_generations)


def format_duration(seconds: float | None) -> str:
    """Render a duration as ``H:MM:SS`` (or ``MM:SS`` under an hour), ``"--:--"`` if unknown."""

    if seconds is None or seconds < 0:
        return "--:--"
    total_seconds = int(round(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

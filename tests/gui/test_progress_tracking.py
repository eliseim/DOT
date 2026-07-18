from __future__ import annotations

from dot.gui.progress_tracking import CampaignProgressTracker, format_duration


def test_explicit_start_makes_first_generation_contribute_to_eta() -> None:
    tracker = CampaignProgressTracker(total_generations=5)
    tracker.start(now=10.0)

    record = tracker.record(1, None, None, None, now=12.0)

    assert record.elapsed_seconds == 2.0
    assert tracker.average_generation_seconds == 2.0
    assert tracker.eta_seconds == 8.0


def test_tracker_records_first_generation_with_zero_elapsed() -> None:
    tracker = CampaignProgressTracker(total_generations=10)

    record = tracker.record(
        1,
        margin_percent=5.0,
        harmonic_units=3.0,
        topology_family_count=4,
        total_turns=42,
        now=100.0,
    )

    assert record.generation == 1
    assert record.elapsed_seconds == 0.0
    assert record.margin_percent == 5.0
    assert record.harmonic_units == 3.0
    assert record.topology_family_count == 4
    assert record.total_turns == 42


def test_tracker_computes_eta_from_average_generation_duration() -> None:
    tracker = CampaignProgressTracker(total_generations=10)
    tracker.record(1, margin_percent=None, harmonic_units=None, topology_family_count=None, now=0.0)
    tracker.record(2, margin_percent=None, harmonic_units=None, topology_family_count=None, now=10.0)
    tracker.record(3, margin_percent=None, harmonic_units=None, topology_family_count=None, now=20.0)

    # 2 recorded durations of 10s each -> average 10s/gen, 7 generations remaining.
    assert tracker.average_generation_seconds == 10.0
    assert tracker.eta_seconds == 70.0
    assert tracker.elapsed_seconds == 20.0


def test_tracker_eta_uses_a_short_moving_window_not_the_whole_history() -> None:
    # Simulates a campaign that starts fast then slows down -- a naive
    # total-elapsed/generations-done average would understate the true
    # remaining time; the moving window should track the CURRENT pace.
    tracker = CampaignProgressTracker(total_generations=20, eta_window=3)
    t = 0.0
    for _ in range(5):
        t += 5.0  # fast generations, 5s each
        tracker.record(tracker.history[-1].generation + 1 if tracker.history else 1, None, None, None, now=t)
    for _ in range(3):
        t += 50.0  # then it slows down sharply, 50s each
        tracker.record(tracker.history[-1].generation + 1, None, None, None, now=t)

    # Only the last 3 (slow) durations should be averaged, not all 7.
    assert tracker.average_generation_seconds == 50.0


def test_tracker_eta_is_none_before_any_duration_is_observed() -> None:
    tracker = CampaignProgressTracker(total_generations=10)
    tracker.record(1, margin_percent=None, harmonic_units=None, topology_family_count=None, now=0.0)

    assert tracker.eta_seconds is None


def test_tracker_eta_is_zero_at_the_final_generation() -> None:
    tracker = CampaignProgressTracker(total_generations=3)
    tracker.record(1, None, None, None, now=0.0)
    tracker.record(2, None, None, None, now=10.0)
    tracker.record(3, None, None, None, now=20.0)

    assert tracker.eta_seconds == 0.0
    assert tracker.progress_fraction == 1.0


def test_tracker_progress_fraction() -> None:
    tracker = CampaignProgressTracker(total_generations=4)
    tracker.record(1, None, None, None, now=0.0)
    tracker.record(2, None, None, None, now=10.0)

    assert tracker.progress_fraction == 0.5


def test_tracker_history_accumulates_all_records() -> None:
    tracker = CampaignProgressTracker(total_generations=5)
    for generation in range(1, 6):
        tracker.record(generation, margin_percent=float(generation), harmonic_units=None, topology_family_count=None, now=float(generation))

    assert len(tracker.history) == 5
    assert [r.margin_percent for r in tracker.history] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_format_duration_under_an_hour() -> None:
    assert format_duration(65.0) == "01:05"
    assert format_duration(0.0) == "00:00"


def test_format_duration_over_an_hour() -> None:
    assert format_duration(3725.0) == "1:02:05"


def test_format_duration_unknown() -> None:
    assert format_duration(None) == "--:--"

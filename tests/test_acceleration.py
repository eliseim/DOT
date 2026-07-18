from __future__ import annotations

import dot.acceleration as acceleration


def test_recommended_process_workers_is_conservative(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(acceleration.os, "cpu_count", lambda: 1)
    assert acceleration.recommended_process_workers() == 1

    monkeypatch.setattr(acceleration.os, "cpu_count", lambda: 4)
    assert acceleration.recommended_process_workers() == 3

    monkeypatch.setattr(acceleration.os, "cpu_count", lambda: 128)
    assert acceleration.recommended_process_workers() == 4


def test_jit_status_is_user_readable() -> None:
    status = acceleration.jit_status()

    assert status.startswith("Numba JIT")

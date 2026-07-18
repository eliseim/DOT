from __future__ import annotations

from dataclasses import replace

from dot.analysis import (
    ToleranceSpec,
    finite_difference_harmonic_sensitivities,
    monte_carlo_robustness,
)
from dot.geometry import Block, DipoleDesign, Layer
from dot.optimize.objectives import EvaluationFidelity

from tests.optimize.test_runner import _feasibility, _targets, _topology


def _design() -> DipoleDesign:
    topology = _topology()
    cable = topology.cables["inner"]
    radius = 20.0
    return DipoleDesign(
        topology.aperture_radius_mm,
        (
            Layer(
                radius,
                (
                    Block(70.0, 0.0, 1, cable, radius, 1.0),
                    Block(30.0, 0.0, 1, cable, radius, 1.0),
                ),
            ),
        ),
    )


def test_zero_tolerance_monte_carlo_is_deterministic() -> None:
    targets = replace(_targets(), harmonic_orders=(3,))
    result = monte_carlo_robustness(
        _design(),
        targets,
        _feasibility(),
        ToleranceSpec(0.0, 0.0, 0.0),
        n_samples=3,
        seed=7,
        fidelity=EvaluationFidelity("test", 1, 1),
    )

    assert len(result.samples) == 3
    assert result.geometry_feasible_fraction == 1.0
    assert len({row.worst_harmonic_units for row in result.samples}) == 1


def test_harmonic_sensitivity_reports_requested_orders() -> None:
    targets = replace(_targets(), harmonic_orders=(3,))
    records = finite_difference_harmonic_sensitivities(
        _design(),
        targets,
        fidelity=EvaluationFidelity("test", 1, 1),
    )

    assert records
    assert all(row.order == 3 for row in records)
    assert {row.parameter for row in records} == {"phi_deg", "alpha_deg"}

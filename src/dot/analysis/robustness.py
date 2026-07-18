"""Tolerance sensitivity and Monte Carlo certification for 2D coil designs."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from dot.geometry import DipoleDesign, Layer
from dot.geometry.constraints import check_feasibility
from dot.optimize.objectives import EvaluationFidelity, harmonic_table, load_line_margin_detail
from dot.optimize.operating_point import operating_point
from dot.optimize.problem import FeasibilitySettings, OptimizationTargets


@dataclass(frozen=True, slots=True)
class ToleranceSpec:
    """Independent one-sigma assembly errors used by the default Monte Carlo."""

    layer_radius_sigma_mm: float = 0.05
    block_phi_sigma_deg: float = 0.05
    block_alpha_sigma_deg: float = 0.05

    def __post_init__(self) -> None:
        for name, value in (
            ("layer_radius_sigma_mm", self.layer_radius_sigma_mm),
            ("block_phi_sigma_deg", self.block_phi_sigma_deg),
            ("block_alpha_sigma_deg", self.block_alpha_sigma_deg),
        ):
            if value < 0.0 or not math.isfinite(value):
                raise ValueError(f"{name} must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class RobustnessSample:
    geometry_feasible: bool
    meets_specification: bool
    worst_harmonic_units: float | None
    minimum_margin_percent: float | None
    operating_current_a: float | None


@dataclass(frozen=True, slots=True)
class RobustnessSummary:
    samples: tuple[RobustnessSample, ...]
    geometry_feasible_fraction: float
    specification_pass_fraction: float
    harmonic_p95_units: float | None
    harmonic_cvar95_units: float | None
    margin_p05_percent: float | None


@dataclass(frozen=True, slots=True)
class HarmonicSensitivity:
    layer_index: int
    block_index: int
    parameter: str
    order: int
    units_per_parameter_unit: float


def monte_carlo_robustness(
    design: DipoleDesign,
    targets: OptimizationTargets,
    feasibility: FeasibilitySettings,
    tolerances: ToleranceSpec,
    *,
    n_samples: int = 200,
    seed: int = 0,
    fidelity: EvaluationFidelity | None = None,
) -> RobustnessSummary:
    """Perturb assembly geometry and summarize yield/tail field quality.

    Errors are intentionally independent and Gaussian. Correlated tooling,
    systematic coil-size, and measured production distributions can be added
    later without changing the returned certification contract.
    """

    if n_samples < 1:
        raise ValueError("n_samples must be positive")
    evaluation_fidelity = targets.certification_fidelity if fidelity is None else fidelity
    rng = np.random.default_rng(seed)
    samples: list[RobustnessSample] = []
    for _ in range(n_samples):
        perturbed = _perturb_design(design, tolerances, rng)
        geometry = _check_geometry(perturbed, feasibility)
        if not geometry:
            samples.append(RobustnessSample(False, False, None, None, None))
            continue
        try:
            solved = operating_point(perturbed, targets.target_bore_field_t)
            harmonics = harmonic_table(
                solved.design,
                targets.r_ref_mm,
                targets.max_order,
                evaluation_fidelity,
            )
            wanted = set(targets.harmonic_orders)
            harmonic = max(
                abs(normal)
                for order, normal, _skew in harmonics
                if order >= 2 and (not wanted or order in wanted)
            )
            margins = load_line_margin_detail(
                solved.design,
                targets.cadata_by_layer,
                targets.temperature_k,
                fidelity=evaluation_fidelity,
            )
            margin = min(row.margin_percent for row in margins)
            current = abs(solved.operating_current_a)
            passes = (
                (targets.max_harmonic_units is None or harmonic <= targets.max_harmonic_units)
                and (targets.min_margin_percent is None or margin >= targets.min_margin_percent)
                and (targets.max_current_a is None or current <= targets.max_current_a)
            )
            samples.append(RobustnessSample(True, passes, harmonic, margin, current))
        except (KeyError, ValueError, ZeroDivisionError):
            samples.append(RobustnessSample(True, False, None, None, None))

    valid_harmonics = np.asarray(
        [row.worst_harmonic_units for row in samples if row.worst_harmonic_units is not None],
        dtype=float,
    )
    valid_margins = np.asarray(
        [row.minimum_margin_percent for row in samples if row.minimum_margin_percent is not None],
        dtype=float,
    )
    p95 = float(np.quantile(valid_harmonics, 0.95)) if valid_harmonics.size else None
    if valid_harmonics.size:
        tail = valid_harmonics[valid_harmonics >= p95]
        cvar95 = float(np.mean(tail))
    else:
        cvar95 = None
    return RobustnessSummary(
        samples=tuple(samples),
        geometry_feasible_fraction=sum(row.geometry_feasible for row in samples) / n_samples,
        specification_pass_fraction=sum(row.meets_specification for row in samples) / n_samples,
        harmonic_p95_units=p95,
        harmonic_cvar95_units=cvar95,
        margin_p05_percent=(float(np.quantile(valid_margins, 0.05)) if valid_margins.size else None),
    )


def finite_difference_harmonic_sensitivities(
    design: DipoleDesign,
    targets: OptimizationTargets,
    *,
    delta_deg: float = 0.01,
    fidelity: EvaluationFidelity | None = None,
) -> tuple[HarmonicSensitivity, ...]:
    """Return central-difference `b_n` sensitivities to every block angle."""

    if delta_deg <= 0.0 or not math.isfinite(delta_deg):
        raise ValueError("delta_deg must be finite and positive")
    evaluation_fidelity = targets.search_fidelity if fidelity is None else fidelity
    records: list[HarmonicSensitivity] = []
    for layer_index, layer in enumerate(design.layers):
        for block_index, _block in enumerate(layer.blocks):
            parameters = ("phi_deg",) if block_index == 0 else ("phi_deg", "alpha_deg")
            for parameter in parameters:
                plus = _perturb_one(design, layer_index, block_index, parameter, delta_deg)
                minus = _perturb_one(design, layer_index, block_index, parameter, -delta_deg)
                plus_table = harmonic_table(
                    operating_point(plus, targets.target_bore_field_t).design,
                    targets.r_ref_mm,
                    targets.max_order,
                    evaluation_fidelity,
                )
                minus_table = harmonic_table(
                    operating_point(minus, targets.target_bore_field_t).design,
                    targets.r_ref_mm,
                    targets.max_order,
                    evaluation_fidelity,
                )
                minus_by_order = {order: normal for order, normal, _skew in minus_table}
                for order, normal_plus, _skew in plus_table:
                    if order < 2 or (targets.harmonic_orders and order not in targets.harmonic_orders):
                        continue
                    records.append(
                        HarmonicSensitivity(
                            layer_index,
                            block_index,
                            parameter,
                            order,
                            (normal_plus - minus_by_order[order]) / (2.0 * delta_deg),
                        )
                    )
    return tuple(records)


def _perturb_design(
    design: DipoleDesign,
    tolerances: ToleranceSpec,
    rng: np.random.Generator,
) -> DipoleDesign:
    layers = []
    for layer in design.layers:
        radius_delta = float(rng.normal(0.0, tolerances.layer_radius_sigma_mm))
        radius = layer.inner_radius_mm + radius_delta
        blocks = tuple(
            replace(
                block,
                inner_radius_mm=radius,
                phi_deg=block.phi_deg + float(rng.normal(0.0, tolerances.block_phi_sigma_deg)),
                alpha_deg=block.alpha_deg
                + float(rng.normal(0.0, tolerances.block_alpha_sigma_deg)),
            )
            for block in layer.blocks
        )
        layers.append(Layer(inner_radius_mm=radius, blocks=blocks))
    return DipoleDesign(design.aperture_radius_mm, tuple(layers))


def _perturb_one(
    design: DipoleDesign,
    layer_index: int,
    block_index: int,
    parameter: str,
    delta: float,
) -> DipoleDesign:
    layers = list(design.layers)
    blocks = list(layers[layer_index].blocks)
    block = blocks[block_index]
    blocks[block_index] = replace(block, **{parameter: getattr(block, parameter) + delta})
    layers[layer_index] = Layer(layers[layer_index].inner_radius_mm, tuple(blocks))
    return DipoleDesign(design.aperture_radius_mm, tuple(layers))


def _check_geometry(design: DipoleDesign, feasibility: FeasibilitySettings) -> bool:
    return check_feasibility(
        design,
        aperture_radius_mm=design.aperture_radius_mm,
        min_gap_mm=feasibility.min_gap_mm,
        max_angle_deg=feasibility.max_angle_deg,
        min_layer_clearance_mm=feasibility.min_layer_clearance_mm,
        min_pole_gap_mm=feasibility.min_pole_gap_mm,
        min_pole_turn_radius_mm=feasibility.min_pole_turn_radius_mm,
        min_inter_block_gap_mm=feasibility.min_inter_block_gap_mm,
        enforce_layer_nesting=feasibility.enforce_layer_nesting,
        geometry_tolerance_mm=feasibility.geometry_tolerance_mm,
    ).is_feasible

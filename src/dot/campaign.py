"""Headless, versioned campaign configuration and result serialization."""

from __future__ import annotations

import json
import hashlib
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dot.conductors import resolve_conductor
from dot.geometry import CableSpec, midplane_anchors_from_gaps
from dot.optimize import LayerConductorData, LayerTopology, Topology
from dot.optimize.objectives import EvaluationFidelity
from dot.optimize.problem import FeasibilitySettings, OptimizationTargets
from dot.optimize.runner import ParetoResult


@dataclass(frozen=True, slots=True)
class CampaignRunSettings:
    population: int
    generations: int
    seeds: tuple[int, ...]
    workers: int
    adaptive_offspring: bool


@dataclass(frozen=True, slots=True)
class CampaignDefinition:
    name: str
    topology: Topology
    targets: OptimizationTargets
    feasibility: FeasibilitySettings
    run: CampaignRunSettings
    source_path: Path
    raw: dict[str, Any]


def load_campaign(path: str | Path) -> CampaignDefinition:
    """Load and validate a schema-v1 JSON campaign."""

    source = Path(path).resolve()
    raw = json.loads(source.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise ValueError("campaign schema_version must be 1")
    angle_convention = raw.get("geometry_angle_convention", "dot-pole-zero")
    if angle_convention not in {"roxie", "dot-pole-zero"}:
        raise ValueError("geometry_angle_convention must be 'roxie' or 'dot-pole-zero'")
    name = str(raw.get("name", "")).strip()
    if not name:
        raise ValueError("campaign name must be non-empty")
    magnet = _mapping(raw, "magnet")
    acceptance = _mapping(raw, "acceptance")
    geometry = _mapping(raw, "geometry")
    layer_rows = raw.get("layers")
    if not isinstance(layer_rows, list) or not layer_rows:
        raise ValueError("layers must be a non-empty list")
    aperture_radius_mm = _finite_positive(magnet["aperture_radius_mm"], "aperture_radius_mm")

    cables: dict[str, CableSpec] = {}
    cable_ids: list[str] = []
    layer_parameters: list[dict[str, Any]] = []
    conductor_data: list[LayerConductorData] = []
    for index, item in enumerate(layer_rows):
        if not isinstance(item, dict):
            raise ValueError(f"layers[{index}] must be an object")
        cadata_path = (source.parent / str(item["cadata"])).resolve()
        text = cadata_path.read_text(encoding="utf-8", errors="replace")
        conductor_name = str(item["conductor"])
        resolution = resolve_conductor(text, conductor_name)
        if not resolution.is_resolved:
            raise ValueError(
                f"layers[{index}] conductor {conductor_name!r} is not usable: {resolution.message}"
            )
        if resolution.strand is None or resolution.cable is None or resolution.remfit is None:
            raise ValueError(f"layers[{index}] conductor resolution is incomplete")
        cable_id = f"layer-{index + 1}:{conductor_name}"
        cable_ids.append(cable_id)
        cables[cable_id] = resolution.cable_spec()
        conductor_data.append(
            LayerConductorData(
                strand=resolution.strand,
                cable=resolution.cable,
                remfit=resolution.remfit,
            )
        )
        fixed_radius = _optional_positive(item.get("inner_radius_mm"), f"layers[{index}].inner_radius_mm")
        radius_bounds = None
        if fixed_radius is not None:
            radius_bounds = (fixed_radius, fixed_radius)
        elif "inner_radius_bounds_mm" in item:
            radius_bounds = _float_pair(
                item["inner_radius_bounds_mm"], f"layers[{index}].inner_radius_bounds_mm"
            )
        first_block_phi = _optional_finite(
            item.get("first_block_phi_deg"),
            f"layers[{index}].first_block_phi_deg",
        )
        phi_bounds = _float_pair(
            item.get("phi_bounds_deg", [0.0, 90.0]),
            f"layers[{index}].phi_bounds_deg",
        )
        alpha_bounds = _float_pair(item["alpha_bounds_deg"], f"layers[{index}].alpha_bounds_deg")
        first_block_alpha = _finite_number(
            item.get("first_block_alpha_deg", 0.0),
            f"layers[{index}].first_block_alpha_deg",
        )
        if angle_convention == "dot-pole-zero":
            phi_bounds = (90.0 - phi_bounds[1], 90.0 - phi_bounds[0])
            alpha_bounds = (-alpha_bounds[1], -alpha_bounds[0])
            if first_block_phi is not None:
                first_block_phi = 90.0 - first_block_phi
            first_block_alpha = -first_block_alpha
        layer_parameters.append(
            {
                "cable_id": cable_id,
                "n_blocks": _positive_int(item["max_blocks"], f"layers[{index}].max_blocks"),
                "min_blocks": _positive_int(
                    item.get("min_blocks", 1), f"layers[{index}].min_blocks"
                ),
                "inner_radius_bounds_mm": radius_bounds,
                "phi_bounds_deg": phi_bounds,
                "alpha_bounds_deg": alpha_bounds,
                "n_turns_bounds": _int_pair(
                    item["turn_bounds"], f"layers[{index}].turn_bounds"
                ),
                "inner_radius_mm": fixed_radius,
                "first_block_phi_deg": first_block_phi,
                "first_block_alpha_deg": first_block_alpha,
            }
        )

    gap_anchor_mode = all(
        parameters["inner_radius_bounds_mm"] is None for parameters in layer_parameters
    )
    if gap_anchor_mode:
        azimuthal_gaps = tuple(
            _finite_nonnegative(
                row.get("azimuthal_gap_mm", geometry["midplane_gap_mm"]),
                f"layers[{index}].azimuthal_gap_mm",
            )
            for index, row in enumerate(layer_rows)
        )
        legacy_first_gap = layer_rows[0].get("radial_gap_mm")
        if legacy_first_gap is not None and _finite_nonnegative(
            legacy_first_gap,
            "layers[0].radial_gap_mm",
        ) != 0.0:
            raise ValueError(
                "layers[0].radial_gap_mm must be omitted: Layer 1 R is the aperture radius"
            )
        radial_gaps = tuple(
            _finite_nonnegative(
                row.get("radial_gap_mm", geometry["inter_layer_gap_mm"]),
                f"layers[{index}].radial_gap_mm",
            )
            for index, row in enumerate(layer_rows[1:], start=1)
        )
        anchors = midplane_anchors_from_gaps(
            aperture_radius_mm,
            tuple(cables[cable_id] for cable_id in cable_ids),
            azimuthal_gaps,
            radial_gaps,
        )
        for parameters, (radius, phi, alpha) in zip(
            layer_parameters, anchors, strict=True
        ):
            parameters["inner_radius_bounds_mm"] = (radius, radius)
            parameters["inner_radius_mm"] = radius
            parameters["first_block_phi_deg"] = phi
            parameters["first_block_alpha_deg"] = alpha
    elif any(parameters["inner_radius_bounds_mm"] is None for parameters in layer_parameters):
        raise ValueError(
            "layers must either all use radial/azimuthal gaps or all define an inner radius"
        )

    layer_topologies = tuple(LayerTopology(**parameters) for parameters in layer_parameters)
    r_ref_mm = _finite_positive(magnet["reference_radius_mm"], "reference_radius_mm")
    if r_ref_mm >= aperture_radius_mm:
        raise ValueError("reference_radius_mm must be smaller than aperture_radius_mm")
    max_order = _positive_int(magnet["max_harmonic_order"], "max_harmonic_order")
    harmonic_orders = tuple(
        _positive_int(value, "acceptance.harmonic_orders")
        for value in acceptance.get("harmonic_orders", range(3, max_order + 1, 2))
    )
    if any(order < 3 or order > max_order or order % 2 == 0 for order in harmonic_orders):
        raise ValueError(
            "harmonic_orders must contain odd normal dipole orders from 3 through max order"
        )

    topology = Topology(
        aperture_radius_mm=aperture_radius_mm,
        layers=layer_topologies,
        cables=cables,
    )
    search_fidelity = _fidelity(
        acceptance.get("search_fidelity"), "search-v2", bore_default=3, peak_default=8
    )
    certification_fidelity = _fidelity(
        acceptance.get("certification_fidelity"),
        "certify-v1",
        bore_default=12,
        peak_default=80,
    )
    targets = OptimizationTargets(
        target_bore_field_t=_finite_positive(magnet["target_bore_field_t"], "target_bore_field_t"),
        r_ref_mm=r_ref_mm,
        max_order=max_order,
        harmonic_orders=harmonic_orders,
        harmonic_targets=_harmonic_targets(
            acceptance.get("harmonic_targets"),
            harmonic_orders,
        ),
        cadata_by_layer=tuple(conductor_data),
        temperature_k=_finite_positive(magnet["temperature_k"], "temperature_k"),
        max_harmonic_units=_optional_positive(
            acceptance.get("max_harmonic_units"), "max_harmonic_units"
        ),
        min_margin_percent=_optional_nonnegative(
            acceptance.get("min_margin_percent"), "min_margin_percent"
        ),
        max_current_a=_optional_positive(acceptance.get("max_current_a"), "max_current_a"),
        max_total_turns=_optional_positive_int(
            acceptance.get("max_total_turns"), "max_total_turns"
        ),
        max_turns_per_layer=_optional_positive_int(
            acceptance.get("max_turns_per_layer"), "max_turns_per_layer"
        ),
        pareto_search=_search_mode(acceptance.get("search_mode", "annealed")),
        search_fidelity=search_fidelity,
        certification_fidelity=certification_fidelity,
    )
    enforce_layer_nesting = bool(geometry.get("enforce_layer_nesting", True))
    default_nesting_repair = 15.0 if enforce_layer_nesting else None
    feasibility = FeasibilitySettings(
        min_gap_mm=_finite_nonnegative(geometry["midplane_gap_mm"], "midplane_gap_mm"),
        max_angle_deg=None,
        min_layer_clearance_mm=_finite_nonnegative(
            geometry["inter_layer_gap_mm"], "inter_layer_gap_mm"
        ),
        min_pole_gap_mm=None,
        min_pole_turn_radius_mm=_optional_positive(
            geometry.get(
                "min_pole_turn_radius_mm",
                geometry.get("pole_gap_mm"),
            ),
            "min_pole_turn_radius_mm",
        ),
        min_inter_block_gap_mm=_optional_layerwise_nonnegative(
            geometry.get("inter_block_gap_mm"),
            "inter_block_gap_mm",
            len(topology.layers),
        ),
        enforce_layer_nesting=enforce_layer_nesting,
        geometry_tolerance_mm=_finite_nonnegative(
            geometry.get("geometry_tolerance_mm", 0.005), "geometry_tolerance_mm"
        ),
        max_nesting_repair_deg=_optional_positive(
            geometry.get("max_nesting_repair_deg", default_nesting_repair),
            "max_nesting_repair_deg",
        ),
    )
    optimization = _mapping(raw, "optimization")
    if optimization.get("refinement") is not None:
        raise ValueError(
            "optimization.refinement has been removed; DOT now returns the certified NSGA-II "
            "Pareto archive directly"
        )
    seeds_raw = optimization.get("seeds", [7])
    if not isinstance(seeds_raw, list) or not seeds_raw:
        raise ValueError("optimization.seeds must be a non-empty list")
    run = CampaignRunSettings(
        population=_positive_int(optimization["population"], "optimization.population"),
        generations=_positive_int(optimization["generations"], "optimization.generations"),
        seeds=tuple(int(seed) for seed in seeds_raw),
        workers=_positive_int(optimization.get("workers", 1), "optimization.workers"),
        adaptive_offspring=bool(optimization.get("adaptive_offspring", True)),
    )
    return CampaignDefinition(
        name,
        topology,
        targets,
        feasibility,
        run,
        source,
        raw,
    )


def result_document(
    campaign: CampaignDefinition,
    result: ParetoResult,
    *,
    quick: bool,
) -> dict[str, Any]:
    """Build a stable JSON-serializable result document."""

    return {
        "schema_version": 1,
        "campaign": campaign.name,
        "source_config": str(campaign.source_path),
        "model_boundary": "two-dimensional coil-only/no-iron magnetostatics",
        "inputs": _input_manifest(campaign),
        "configured_run": asdict(campaign.run),
        "quick_run": quick,
        "reference_radius_mm": campaign.targets.r_ref_mm,
        "harmonic_convention": "CERN/European units: 1e-4 of main normal dipole",
        "search_fidelity": asdict(campaign.targets.search_fidelity),
        "certification_fidelity": asdict(campaign.targets.certification_fidelity),
        "candidate_count": len(result.candidates),
        "candidates": [
            _candidate_document(index, candidate)
            for index, candidate in enumerate(result.candidates)
        ],
        "near_feasible": [
            {
                "max_normalized_violation": item.max_violation,
                "normalized_violations": dict(item.normalized_violations),
                "search_objectives": {
                    "worst_harmonic_units": item.search_objectives[0],
                    "worst_harmonic_residual_units": item.search_objectives[0],
                    "negative_margin_percent": item.search_objectives[1],
                },
                "harmonic_targets": {
                    f"b{order}": target for order, target in item.harmonic_targets
                },
                "layers": [
                    {
                        "inner_radius_mm": layer.inner_radius_mm,
                        "blocks": [
                            {
                                "phi_deg": block.phi_deg,
                                "alpha_deg": block.alpha_deg,
                                "turns": block.n_turns,
                            }
                            for block in layer.blocks
                        ],
                    }
                    for layer in item.design.layers
                ],
            }
            for item in result.near_feasible
        ],
    }


def _candidate_document(index, candidate) -> dict[str, Any]:  # noqa: ANN001
    target_by_order = dict(candidate.harmonic_targets)
    return {
        "rank_index": index,
        "certified": candidate.certified,
        "objectives": {
            "worst_harmonic_units": candidate.objectives[0],
            "worst_harmonic_residual_units": candidate.objectives[0],
            "minimum_margin_percent": -candidate.objectives[1],
        },
        "harmonic_targets": {
            f"b{order}": target for order, target in candidate.harmonic_targets
        },
        "operating_current_a": candidate.operating_current_a,
        "harmonics": [
            {
                "order": order,
                "normal_units": b_n,
                "target_normal_units": target_by_order.get(order, 0.0),
                "normal_residual_units": b_n - target_by_order.get(order, 0.0),
                "skew_units": a_n,
            }
            for order, b_n, a_n in candidate.harmonics
        ],
        "margins_by_layer": [
            {
                "layer": row.layer_index + 1,
                "peak_field_t": row.peak_field_t,
                "operating_current_a": row.operating_current_a,
                "short_sample_current_a": row.short_sample_current_a,
                "margin_percent": row.margin_percent,
            }
            for row in candidate.margin_by_layer
        ],
        "margins_by_block": [
            {
                "roxie_block": row.roxie_block,
                "layer": row.layer_index + 1,
                "block_in_layer": row.block_index + 1,
                "peak_field_t": row.peak_field_t,
                "operating_current_a": row.operating_current_a,
                "short_sample_current_a": row.short_sample_current_a,
                "margin_percent": row.margin_percent,
            }
            for row in candidate.margin_by_block
        ],
        "layers": [
            {
                "inner_radius_mm": layer.inner_radius_mm,
                "blocks": [
                    {
                        "phi_deg": block.phi_deg,
                        "alpha_deg": block.alpha_deg,
                        "turns": block.n_turns,
                    }
                    for block in layer.blocks
                ],
            }
            for layer in candidate.design.layers
        ],
    }


def _input_manifest(campaign: CampaignDefinition) -> list[dict[str, str]]:
    paths: list[tuple[str, Path]] = [("campaign", campaign.source_path)]
    seen = {campaign.source_path}
    for row in campaign.raw["layers"]:
        path = (campaign.source_path.parent / str(row["cadata"])).resolve()
        if path not in seen:
            paths.append(("cadata", path))
            seen.add(path)
    return [
        {
            "role": role,
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for role, path in paths
    ]


def _mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _float_pair(value: Any, name: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must contain two values")
    pair = (float(value[0]), float(value[1]))
    if not all(math.isfinite(item) for item in pair) or pair[0] > pair[1]:
        raise ValueError(f"{name} must be finite and ordered")
    return pair


def _int_pair(value: Any, name: str) -> tuple[int, int]:
    pair = _float_pair(value, name)
    integers = (int(pair[0]), int(pair[1]))
    if pair != integers or integers[0] < 1:
        raise ValueError(f"{name} must contain positive integers")
    return integers


def _positive_int(value: Any, name: str) -> int:
    number = int(value)
    if isinstance(value, bool) or number != float(value) or number < 1:
        raise ValueError(f"{name} must be a positive integer")
    return number


def _optional_positive_int(value: Any, name: str) -> int | None:
    return None if value is None else _positive_int(value, name)


def _finite_positive(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def _finite_nonnegative(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return number


def _finite_number(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _optional_finite(value: Any, name: str) -> float | None:
    return None if value is None else _finite_number(value, name)


def _optional_positive(value: Any, name: str) -> float | None:
    return None if value is None or float(value) == 0.0 else _finite_positive(value, name)


def _optional_nonnegative(value: Any, name: str) -> float | None:
    return None if value is None else _finite_nonnegative(value, name)


def _optional_layerwise_nonnegative(
    value: Any,
    name: str,
    layer_count: int,
) -> float | tuple[float, ...] | None:
    """Parse a scalar or one non-negative value per layer."""

    if value is None:
        return None
    if isinstance(value, list):
        if len(value) != layer_count:
            raise ValueError(
                f"{name} must be a scalar or contain one value per layer "
                f"({len(value)} != {layer_count})"
            )
        return tuple(
            _finite_nonnegative(item, f"{name}[{index}]") for index, item in enumerate(value)
        )
    # Preserve schema-v1 behavior: scalar zero disables this optional check.
    return _optional_positive(value, name)


def _harmonic_targets(
    value: Any,
    harmonic_orders: tuple[int, ...],
) -> tuple[tuple[int, float], ...]:
    """Parse optional ``{"b3": -3}`` or ``{"3": -3}`` target mappings."""

    if value is None:
        return ()
    if not isinstance(value, dict):
        raise ValueError("acceptance.harmonic_targets must be an object")
    parsed: dict[int, float] = {}
    for raw_order, raw_target in value.items():
        text = str(raw_order).strip().lower()
        if text.startswith("b"):
            text = text[1:]
        try:
            order = _positive_int(text, "acceptance.harmonic_targets order")
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"invalid harmonic target key {raw_order!r}; use b3, b5, ..."
            ) from exc
        if order not in harmonic_orders:
            raise ValueError(
                f"harmonic target b{order} is not listed in acceptance.harmonic_orders"
            )
        if order in parsed:
            raise ValueError(f"duplicate harmonic target for b{order}")
        parsed[order] = _finite_number(
            raw_target,
            f"acceptance.harmonic_targets.b{order}",
        )
    return tuple((order, parsed[order]) for order in harmonic_orders if order in parsed)


def _search_mode(value: Any) -> bool:
    mode = str(value).strip().lower()
    if mode not in {"annealed", "pareto"}:
        raise ValueError("acceptance.search_mode must be 'annealed' or 'pareto'")
    return mode == "pareto"


def _fidelity(
    value: Any,
    default_name: str,
    *,
    bore_default: int,
    peak_default: int,
) -> EvaluationFidelity:
    if value is None:
        return EvaluationFidelity(default_name, bore_default, peak_default)
    if not isinstance(value, dict):
        raise ValueError("fidelity must be an object")
    return EvaluationFidelity(
        str(value.get("name", default_name)),
        _positive_int(value.get("bore_filaments_per_axis", bore_default), "bore fidelity"),
        _positive_int(value.get("peak_filaments_per_axis", peak_default), "peak fidelity"),
    )

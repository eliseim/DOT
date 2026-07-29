"""Geometry primitives for DOT."""

from .anchors import midplane_anchors_from_gaps
from .cable import CableSpec
from .primitives import Block, DipoleDesign, Layer, Point, TurnPolygon
from .radiality import (
    BlockRadiality,
    RadialitySummary,
    block_radiality,
    radiality_summary,
    radialized_block_alpha_deg,
)

__all__ = [
    "Block",
    "BlockRadiality",
    "CableSpec",
    "DipoleDesign",
    "Layer",
    "midplane_anchors_from_gaps",
    "Point",
    "RadialitySummary",
    "TurnPolygon",
    "block_radiality",
    "radiality_summary",
    "radialized_block_alpha_deg",
]

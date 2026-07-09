from __future__ import annotations

from dot.geometry import Block, CableSpec, DipoleDesign, Layer
from dot.gui.cross_section_plot import cross_section_figure, mirrored_turn_polygons
from dot.physics import LineCurrentSource, dipole_mirror_sources


def test_mirrored_turn_polygons_match_dipole_source_convention() -> None:
    design = _design()
    turn = design.all_turns()[0]

    mirrored = mirrored_turn_polygons(design)
    expected_sources = dipole_mirror_sources(LineCurrentSource(3.0, 5.0, turn.current_a))

    assert len(mirrored) == 4
    assert [polygon.current_a for polygon in mirrored] == [
        source.current_a for source in expected_sources
    ]
    assert mirrored[0].corners == turn.corners
    assert mirrored[1].corners == tuple((-x, y) for x, y in turn.corners)
    assert mirrored[2].corners == tuple((-x, -y) for x, y in turn.corners)
    assert mirrored[3].corners == tuple((x, -y) for x, y in turn.corners)


def test_cross_section_figure_draws_aperture_and_all_mirror_images() -> None:
    figure = cross_section_figure(_design())
    axes = figure.axes[0]

    assert len(axes.patches) == 5


def _design() -> DipoleDesign:
    cable = CableSpec(width_mm=2.0, height_mm=1.0, insulation_thickness_mm=0.0)
    return DipoleDesign(
        aperture_radius_mm=8.0,
        layers=(
            Layer(
                inner_radius_mm=12.0,
                blocks=(
                    Block(
                        phi_deg=35.0,
                        alpha_deg=0.0,
                        n_turns=1,
                        cable=cable,
                        inner_radius_mm=12.0,
                        current_a=100.0,
                    ),
                ),
            ),
        ),
    )


from __future__ import annotations

from dot.gui.config_io import load_config, save_config


def test_config_round_trips_form_state(tmp_path) -> None:  # noqa: ANN001
    state = {
        "target_bore_field_t": 0.02,
        "aperture_radius_mm": 8.0,
        "layers": [
            {
                "cadata_path": "inner.cadata",
                "n_blocks": 2,
                "turn_min": 1,
                "turn_max": 3,
            }
        ],
        "acceptance": {
            "max_harmonic_units": 10.0,
            "min_margin_percent": 15.0,
        },
        "nsga2": {
            "pop_size": 8,
            "n_gen": 3,
            "seed": 7,
        },
    }
    path = tmp_path / "gui-config.json"

    save_config(state, path)

    assert load_config(path) == state


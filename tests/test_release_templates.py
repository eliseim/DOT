from __future__ import annotations

import json
from pathlib import Path

from dot.gui.config_io import load_config


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = (
    ROOT / "campaign" / "7T_NbTi_template.json",
    ROOT / "campaign" / "11T_Nb3Sn_template.json",
)


def test_release_templates_are_portable_and_use_release_defaults() -> None:
    for path in TEMPLATES:
        document = json.loads(path.read_text(encoding="utf-8"))

        assert document["nsga2"]["parallel_evaluations"] is True
        assert document["nsga2"]["prefer_radial_design"] is True
        assert Path(document["output_dir"]) == Path("../results")
        for layer in document["layers"]:
            cadata_path = Path(layer["cadata_path"])
            assert not cadata_path.is_absolute()
            assert (path.parent / cadata_path).is_file()

        loaded = load_config(path)
        assert Path(loaded["output_dir"]) == ROOT / "results"
        assert all(Path(layer["cadata_path"]).is_file() for layer in loaded["layers"])


def test_release_templates_cover_nbti_and_nb3sn() -> None:
    conductors = {
        path.name: {
            layer["conductor_name"]
            for layer in json.loads(path.read_text(encoding="utf-8"))["layers"]
        }
        for path in TEMPLATES
    }

    assert conductors["7T_NbTi_template.json"] == {"YELLONIN", "YELLONOU"}
    assert conductors["11T_Nb3Sn_template.json"] == {"XF145_HFM"}

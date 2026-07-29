from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / "docs" / "validation"


def test_roxie_parity_evidence_is_complete_and_finite() -> None:
    with (VALIDATION / "roxie_parity_1000_results.csv").open(
        encoding="utf-8",
        newline="",
    ) as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 1000
    assert len({row["case_id"] for row in rows}) == 1000
    assert sum(row["topology_layers"] == "2" for row in rows) == 500
    assert sum(row["topology_layers"] == "4" for row in rows) == 500
    text_columns = {"case_id", "conductors"}
    assert all(
        math.isfinite(float(value))
        for row in rows
        for name, value in row.items()
        if name not in text_columns
    )


def test_roxie_parity_summary_matches_inputs_and_case_table() -> None:
    summary = json.loads(
        (VALIDATION / "roxie_parity_1000_summary.json").read_text(
            encoding="utf-8"
        )
    )

    assert summary["case_count"] == 1000
    assert summary["two_layer_cases"] == 500
    assert summary["four_layer_cases"] == 500
    assert summary["roxie_service_endpoint"] == "http://127.0.0.1:8080"
    assert summary["input_hashes_sha256"] == {
        "roxie_template": _sha256(ROOT / "tools" / "roxie_no_iron_template.data"),
        "cadata": _sha256(ROOT / "campaign" / "dot_cables.cadata"),
    }
    assert summary["numerical_fidelity"] == {
        "dot_bore_filaments_per_axis": 12,
        "dot_peak_filaments_per_axis": 80,
        "dot_bore_quadrature": "midpoint",
        "roxie_block_n1": 2,
        "roxie_block_n2_by_conductor": {
            "CTH_HF": 20,
            "CTH_LF": 15,
            "YELLONIN": 20,
            "YELLONOU": 20,
        },
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()

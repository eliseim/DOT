from __future__ import annotations

from pathlib import Path

import pytest

from dot.conductors import (
    Type1FitCoefficients,
    UnsupportedFitTypeError,
    parse_cadata_text,
)
from dot.conductors.cadata import find_type1_remfit
from dot.conductors.cadata import resolve_conductor


def test_parse_cadata_text_extracts_strand_cable_and_type1_remfit() -> None:
    text = """
VERSION 11
REMFIT 1
 11 FIT1   1           3E+09          9.2         0.57          0.9         2.32        27.04         14.5            0            0            0            0 'LHC NBTI'
 No Name   Type           C1           C2           C3           C4           C5           C6           C7           C8           C9          C10          C11  Comment
STRAND 1
  3 STR01            1.065          1.6    70          1.9           10       1433.3       500.34 'MB INNER'
 No Name             diam.        cu/sc   RRR         Tref         Bref      Jc@BrTr       dJc/dB  Comment
CABLE 1
 12 CABLE01           15.1        1.736        2.064    28          115            5 'MB INNER LAYER'
 No Name            height      width_i      width_o    ns      transp.        degrd  Comment
"""

    records = parse_cadata_text(text)

    assert records.strands["STR01"].diameter_mm == 1.065
    assert records.strands["STR01"].cu_to_sc_ratio == 1.6
    assert records.cables["CABLE01"].n_strands == 28
    assert records.cables["CABLE01"].degradation_percent == 5.0
    assert records.remfits["FIT1"] == Type1FitCoefficients(
        c1=3.0e9,
        c2=9.2,
        c3=0.57,
        c4=0.9,
        c5=2.32,
        c6=27.04,
        c7=14.5,
    )


def test_parse_cadata_text_rejects_non_type1_remfit() -> None:
    text = """
REMFIT 1
 12 PIT192 11     1.7834E+11           30           16         0.96         1.52          0.5            2            0            0            0            0 'PIT 192 REF'
"""

    with pytest.raises(UnsupportedFitTypeError) as exc_info:
        parse_cadata_text(text)

    assert exc_info.value.fit_type == 11
    assert exc_info.value.name == "PIT192"


def test_named_type1_remfit_ignores_unrelated_unsupported_records() -> None:
    text = """
REMFIT 3
  1 NB3SNA 5         3.5E+10           28           18            0            0            0            0            0            0            0            0 'PIT strand fit poor'
 11 FIT1   1           3E+09          9.2         0.57          0.9         2.32        27.04         14.5            0            0            0            0 'LHC NBTI'
 12 PIT192 11     1.7834E+11           30           16         0.96         1.52          0.5            2            0            0            0            0 'PIT 192 REF'
"""

    records = parse_cadata_text(text, remfit_name="FIT1")

    assert records.remfits == {
        "FIT1": Type1FitCoefficients(
            c1=3.0e9,
            c2=9.2,
            c3=0.57,
            c4=0.9,
            c5=2.32,
            c6=27.04,
            c7=14.5,
        )
    }


def test_named_unsupported_remfit_still_raises() -> None:
    text = """
REMFIT 2
  1 NB3SNA 5         3.5E+10           28           18            0            0            0            0            0            0            0            0 'PIT strand fit poor'
 11 FIT1   1           3E+09          9.2         0.57          0.9         2.32        27.04         14.5            0            0            0            0 'LHC NBTI'
"""

    with pytest.raises(UnsupportedFitTypeError) as exc_info:
        parse_cadata_text(text, remfit_name="NB3SNA")

    assert exc_info.value.fit_type == 5
    assert exc_info.value.name == "NB3SNA"


def test_real_roxie_cth_file_resolves_type1_fit_by_name() -> None:
    path = Path(r"C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata")
    text = path.read_text(encoding="utf-8")

    remfit = find_type1_remfit(text, "FIT1")

    assert remfit == Type1FitCoefficients(
        c1=3.0e9,
        c2=9.2,
        c3=0.57,
        c4=0.9,
        c5=2.32,
        c6=27.04,
        c7=14.5,
    )


def test_real_roxie_cth_file_resolves_named_conductor_links() -> None:
    path = Path(r"C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata")
    text = path.read_text(encoding="utf-8")

    lf = resolve_conductor(text, "CTH_LF")
    hf = resolve_conductor(text, "CTH_HF")

    assert lf.status == "resolved"
    assert lf.conductor is not None
    assert lf.conductor.cable_name == "CTH_CERN"
    assert lf.conductor.strand_name == "STR01_12"
    assert lf.conductor.remfit_name == "NBTILHC"
    assert lf.remfit_name == "FIT1"
    assert lf.temperature_k == pytest.approx(1.9)
    assert lf.strand is not None
    assert lf.strand.diameter_mm == pytest.approx(1.065)
    assert lf.strand.cu_to_sc_ratio == pytest.approx(1.2)
    assert lf.cable is not None
    assert lf.cable.n_strands == 30
    assert lf.cable.degradation_percent == pytest.approx(5.0)
    assert lf.remfit == Type1FitCoefficients(
        c1=3.0e9,
        c2=9.2,
        c3=0.57,
        c4=0.9,
        c5=2.32,
        c6=27.04,
        c7=14.5,
    )

    assert hf.status == "unsupported_fit_type"
    assert hf.conductor is not None
    assert hf.conductor.cable_name == "CXF150HT5"
    assert hf.conductor.remfit_name == "NB3SNMP"
    assert hf.remfit_name == "HFM1"
    assert hf.unsupported_fit_type == 11
    assert "unsupported REMFIT type 11" in hf.message


def test_resolve_conductor_reports_name_not_found() -> None:
    text = """
CONDUCTOR 1
 1 A 1 C S F I T R 1.9 'comment'
"""

    resolution = resolve_conductor(text, "MISSING")

    assert resolution.status == "not_found"
    assert "MISSING" in resolution.message

from __future__ import annotations

import pytest

from dot.conductors import (
    Type1FitCoefficients,
    UnsupportedFitTypeError,
    parse_cadata_text,
)


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

# TASK: Selective `.cadata` parsing (don't choke on unrelated conductor records)

- **ID**: 0007-cadata-selective-parsing
- **Status**: draft
- **Model/effort**: Medium effort. Focused bug-fix task found via the
  coordinator's manual end-to-end verification of task 0006 (not a review
  finding, a real repro): pointing DOT at the actual reference
  `roxie_CTH_cables.cadata` file failed immediately with
  `UnsupportedFitTypeError: unsupported REMFIT type 5 for 'NB3SNA'`, even
  though the layer only needed a *different*, type-1 (Nb-Ti) record in the
  same file.

## Goal

A real `.cadata` file legitimately contains multiple conductor definitions
of different types (Nb-Ti, Nb3Sn, ...) in the same file — that's normal,
not malformed input. DOT only supports type-1 (Bottura Nb-Ti) fits (task
0004, intentionally). Today, `parse_cadata_text` eagerly parses and
validates *every* `REMFIT` record in the file and raises
`UnsupportedFitTypeError` on the first unsupported one it encounters,
regardless of whether that record is ever going to be used. This makes DOT
unusable against real-world `.cadata` files that mix conductor types,
which is the common case, not an edge case.

Fix: parsing must be selective — a caller asks for a specific named cable/
conductor record, and only *that* record's fit type is validated. Unrelated
records elsewhere in the file, even unsupported ones, must not block
loading the one the caller actually needs.

## Scope (files/modules Codex may touch)

- `src/dot/conductors/cadata.py`
- `tests/conductors/test_cadata.py` (extend, don't rewrite existing
  passing tests unless they directly test the behavior being changed)
- `src/dot/gui/target_synthesis_gui.py` — update `_campaign_inputs()` to
  use the new selective-lookup API instead of the current eager whole-file
  parse, and to let the user pick a cable/conductor *name* from the file
  (or, minimally, keep the current "point at a file" UX but resolve the
  first *supported* record — coordinator judgment call, state which you
  chose and why; see notes).
- `tests/gui/test_target_synthesis_gui.py` (extend)

## Explicit non-goals

- Still no Nb3Sn/type-11 support — an unsupported type must still raise
  clearly, just only when the caller actually asks for that specific
  record, not for every other record in the same file.
- No GUI dropdown/picker UI polish beyond what's minimally needed to
  select a record if you choose that approach — keep it simple.

## Reference material

- `C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata` — the
  real file that exposed this bug; contains both a type-1 (Nb-Ti) record
  and at least one type-5/other unsupported record. Use this exact file
  path in a real (not synthetic) regression test if practical, since it's
  what exposed the bug — but do not modify it, read-only.

## Acceptance criteria

- [ ] A new regression test loads the real
      `C:\Users\elisei\Desktop\dipole_designer\roxie_CTH_cables.cadata`
      file and successfully resolves its type-1 Nb-Ti record by name
      without raising, proving the exact bug found is fixed.
- [ ] A record that IS requested by name but IS an unsupported type still
      raises `UnsupportedFitTypeError` clearly (this must not regress —
      add a test for it if one doesn't already cover the "asked-for record
      is unsupported" case specifically, as opposed to "some other record
      in the file is unsupported").
- [ ] The GUI's campaign-input path no longer fails on real multi-conductor
      `.cadata` files when the relevant record is supported.
- [ ] `ruff check` clean; `pytest` passes, no existing tests broken; no
      files outside declared scope modified.

## Notes / open questions

- Simplest fix: change the public parsing entry point to
  `find_type1_record(text, name) -> Type1FitCoefficients` (or similar) that
  scans sections lazily and only raises for the specifically-requested
  record, while still exposing the existing "parse everything eagerly"
  function if some other caller needs it (check — task 0006's GUI is the
  only current caller outside tests; if so, you can freely change its
  signature rather than maintaining two parallel APIs, keep it simple).
- If choosing to let the GUI resolve "the first supported record" rather
  than requiring the user to type a cable name, document that as an
  explicit simplification for this phase, not a permanent design decision.

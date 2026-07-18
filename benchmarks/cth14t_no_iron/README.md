# CTH-14T blind no-iron benchmark

This campaign asks DOT to synthesize a four-layer 12.4 T dipole at 1.9 K with a
25 mm aperture radius, at least 25% load-line margin, and every allowed normal
harmonic through b11 below 5 units. The inner two layers use `CTH_HF`; the outer
two use `CTH_LF`.

The input deliberately contains no published CTH block angles, block turn
allocation, or reference cross-section. First-block anchors are derived only
from the 0.15 mm azimuthal gap, 0.5 mm radial gaps, aperture, and cable
dimensions; broad angular bounds keep the search in the four-layer cos-theta family.
The minimal cadata file is transcribed from the project ROXIE cadata and keeps
the linked cable, strand, insulation, degradation, and critical-current fit
records needed for reproducible margin calculations.

Validate the benchmark without starting an optimization:

```powershell
dot validate benchmarks/cth14t_no_iron/blind_target.json
```

Run the complete multi-seed qualification campaign:

```powershell
dot optimize benchmarks/cth14t_no_iron/blind_target.json --output runs/cth14t
```

The existing physics parity test independently checks the known CTH geometry
against the no-iron ROXIE field and harmonics. That reference geometry is never
imported by this blind campaign or by the generic sector-coil initializer.

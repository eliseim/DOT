# FalconD blind no-iron benchmark

This qualification campaign asks DOT to create a two-layer, 50 mm aperture,
12 T no-iron dipole using the reacted FalconD Nb3Sn conductor. The acceptance
target is at least 20% load-line margin with b3 through b11 below 5 units.

The conductor data are transcribed from the Falcon Dipole Technical Design
Report: 40 strands of 1 mm diameter, Cu/non-Cu ratio 0.885, reacted cable width
21.420 mm, reacted edge thicknesses 1.797/1.989 mm, 0.15 mm insulation, and the
reported cabling-degraded Bordini critical-current fit. Because that fit already
includes cabling degradation, the cadata cable degradation field is zero.

No published block positions, turn counts, or wedge pattern are included in the
campaign. The report's iron-assisted reference design is not treated as a
no-iron certification result; this campaign deliberately asks for a new coil-only
solution with the same nominal field.

```powershell
dot validate benchmarks/falcond_no_iron/blind_target.json
dot optimize benchmarks/falcond_no_iron/blind_target.json --output runs/falcond
```

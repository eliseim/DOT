# Ready-to-run campaign

`dot_cables.cadata` is DOT's validated example conductor catalogue. In the GUI,
select this file for each layer and then choose one of the supported conductor
names offered by the selector.

`7T_NbTi_noiron_sample.json` is a ready-to-run two-layer Nb-Ti example for the
headless interface:

```text
dot validate campaign/7T_NbTi_noiron_sample.json
dot optimize campaign/7T_NbTi_noiron_sample.json --output results/7T_sample
```

The campaign contains targets and manufacturing limits only; it does not encode
a reference block layout.

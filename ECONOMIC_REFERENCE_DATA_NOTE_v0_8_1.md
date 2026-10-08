# QŪNAR v0.8.1 - economic reference-data hierarchy

QŪNAR preserves the evidence status of every economic input.

1. Farm/user value - preferred for decision support.
2. District-crop/provider reference - may be used only when an explicit sourced value exists in the packaged reference table.
3. Regional/national reference scenario - used only as an editable scenario assumption and never labelled as observed farm data.
4. Unavailable - the calculation is withheld rather than inventing a value.

`data/economic_reference_values.csv` currently contains only the general reference values already used by QŪNAR. It does **not** claim to contain complete district-level market prices, technology costs or crop production costs. Those fields remain user/verified inputs until a sourced database is added.

Technology investment and crop selling prices are not imputed automatically. Payback is produced only when an investment value is supplied. Economic optimization is activated only when contribution-margin information is supplied for at least two candidate crops.

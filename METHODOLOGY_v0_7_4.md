# QŪNAR v0.7.4 - computational methodology note

## Active QŪNAR decision score
For each district-crop option, the active decision layer uses three 0-100 components:
- Climate suitability: 50%
- Water efficiency: 35%
- Evidence/data reliability: 15%

The previous market-price and gross-revenue proxy is excluded from both ranking and optimization.

## Water default hierarchy
Primary normative source: Ministry of Water Resources and Irrigation of the Republic of Kazakhstan, Order No. 108-NQ of 4 June 2025, Table 3: https://adilet.zan.kz/rus/docs/V2500036253

The default lookup is district x crop. Directly named official zones receive the highest reliability. Keles, Sauran and Kentau use explicit geographic-zone fallbacks. Suzak and crop rows absent from the official table use the regional calibration benchmark 8,181.6 m3/ha and receive lower reliability. Sunflower/other oilseeds use an explicitly labelled mean of the official rapeseed and safflower norms where available.

User-entered actual water use always overrides the default. The optimizer treats available water as a feasibility constraint.

## Energy
Observed farm electricity is used when supplied by the user. Otherwise QŪNAR may display a reference pumping scenario based on 0.70509 kWh/m3. This is not described as observed farm energy use and does not fabricate a crop-specific electricity statistic.

## Climate and ML
Historical climate features use NASA POWER district coordinates. Live requests now include T2M, PRECTOTCORR, RH2M, GWETROOT and ALLSKY_SFC_SW_DWN for April-September.

Yield ML remains limited to the six crops in the verified analytical panel. Barley is not included in yield ML because the supplied district-year series duplicates wheat and requires source verification. Crop-specific validation metrics are used in the support index.

## Agrochemicals
National or regional pesticide/fertilizer benchmarks are not mechanically converted into district-crop observations. They can be shown as contextual benchmarks or user-editable inputs only when provenance is explicit.

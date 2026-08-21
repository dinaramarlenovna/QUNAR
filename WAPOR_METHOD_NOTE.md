
# FAO WaPOR integration in QÚNAR v0.2

## Source
WaPOR version 3 Level 1 AETI-D:
Actual Evapotranspiration and Interception, dekadal.

API catalogue:
https://data.apps.fao.org/gismgr/api/v2/catalog/workspaces/WAPOR-3/mapsets

## Calculation
The WaPOR AETI dekadal raster represents an average daily AETI rate for the dekad.
QÚNAR sums:

Seasonal AETI [mm] = Σ (mean daily AETI [mm/day] × overlapping days)

The field value is the mean of all valid WaPOR pixels intersecting the user-drawn polygon.
If no polygon is available, the selected point is sampled.

1 mm over 1 ha = 10 m³.

Consumptive water use [m³] =
Seasonal AETI [mm] × 10 × field area [ha]

Modelled physical water productivity [kg/m³] =
predicted crop production [kg] / consumptive water use [m³]

## Critical interpretation
AETI is NOT irrigation withdrawal.
It includes evapotranspiration supported by precipitation, soil moisture and irrigation.
QÚNAR therefore keeps farmer-reported abstraction/application and WaPOR consumptive use
as separate indicators.

## Authentication
WaPOR v3 API requires no API key/token or credentials.

## Spatial scale
Level 1 WaPOR v3 AETI uses an approximately 248 m pixel.
This is suitable for field/regional screening but small fields may contain few pixels.

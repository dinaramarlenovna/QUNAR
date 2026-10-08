# QŪNAR v0.8.1 - Economic and resource-saving extension

This build preserves the public/prototype version label **v0.8.1**.

## Economic logic
- Farm-specific values have priority.
- Missing market prices, variable costs and technology investment are **not invented**.
- Water may use an explicitly labelled district-crop/reference requirement when observed use is unavailable.
- Pumping electricity may be estimated from water volume only as an explicitly labelled scenario.
- Resource-saving results are reported as before/after **scenario estimates** when reference inputs are used.
- Payback is calculated only when an investment amount is supplied.

## Optimization
The default optimizer remains resource-climate constrained. An optional economic objective can be enabled only when the user enters crop-level contribution margins. The optimizer then combines normalized economic evidence with resource-climate utility. Missing economic values receive no invented market estimate.

## Spatial allocation
The coloured within-polygon allocation is an indicative visualization of optimized shares. It is not a field-level agronomic suitability map. True within-field crop placement requires spatial soil, moisture, terrain and irrigation-infrastructure layers.

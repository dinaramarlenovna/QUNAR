
# TURK-RESILIENCE architecture

User -> language -> calculation mode -> district -> field map -> farm inputs
-> live/fallback climate -> ML yield prediction -> resource accounting
-> reliability -> explanation -> (next: multi-objective optimization).

Target modes:
1. Assess my farm.
2. Check selected crop.
3. Recommend crop.
4. Optimize crop structure.

Data hierarchy:
farm measurement -> live field data -> district fallback -> marked scenario.

Rule: never silently invent a missing resource coefficient.

"""Exploratory survey-informed sensitivity profile, NOT statistically estimated weights.

Q3 asks about resource deficits and Q7 asks about obstacles to development.
Their response frequencies cannot identify paired preferences or AHP weights.
This frequency-ratio is provided ONLY as an explicitly chosen what-if profile.
"""
from __future__ import annotations
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "data" / "survey_2026_aggregates.json"


def survey_proxy_profile() -> dict:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    n = int(payload["n_responses"])
    water = int(payload["water_resource_q3_n"])
    climate = int(payload["climate_risk_q7_n"])
    if n <= 0 or water < 0 or climate < 0 or water > n or climate > n or water + climate == 0:
        raise ValueError("Survey frequency data invalid")
    return {
        "climate": climate / (water + climate),
        "water": water / (water + climate),
        "respondents": n,
        "water_mentions": water,
        "climate_mentions": climate,
        "source": "2026 survey, Q3 water deficiency / Q7 climate barriers",
        "method": "cross_question_frequency_ratio_sensitivity_only",
        "warning": "Exploratory scenario, not direct pairwise preferences or validated survey weights",
    }

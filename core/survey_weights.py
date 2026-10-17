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
    audit_survey_aggregates(SOURCE)  # Fail closed if the supplied questionnaire totals conflict.
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


def audit_survey_aggregates(source=SOURCE):
    """Check aggregate response arithmetic; does not invent respondent/district records."""
    payload = json.loads(Path(source).read_text(encoding='utf-8-sig'))
    n = int(payload['n_responses'])
    if n <= 0:
        raise ValueError('Survey sample must be positive')
    checks = []
    for key, question in payload['questions'].items():
        counts = question['counts']
        if not counts or any(not isinstance(v, int) or isinstance(v, bool) or v < 0 or v > n for v in counts.values()):
            raise ValueError(f'Invalid category frequency in {key}')
        total = sum(counts.values())
        if not question['multiple_choice'] and total != n:
            raise ValueError(f'Single-choice {key} total ({total}) differs from sample ({n})')
        checks.append({'question': key, 'type':'multiple' if question['multiple_choice'] else 'single',
                       'sum_of_category_mentions':total, 'respondents':n,
                       'arithmetic_status':'checked',
                       'interpretation':'Multiple selections; sum may exceed sample' if question['multiple_choice'] else 'Exclusive responses; must equal sample'})
    if payload['questions']['Q3']['counts']['Водные ресурсы'] != payload['water_resource_q3_n']:
        raise ValueError('Water count inconsistent with source Q3')
    if payload['questions']['Q7']['counts']['Климатические риски'] != payload['climate_risk_q7_n']:
        raise ValueError('Climate count inconsistent with source Q7')
    return {'n_responses':n, 'questions_checked':len(checks), 'question_checks':checks,
            'limitation':'Aggregates alone cannot establish territorial representativeness, pairwise preferences or respondent-level uncertainty.'}

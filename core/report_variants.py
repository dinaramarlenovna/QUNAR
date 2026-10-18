"""Safe, testable report library and multi-scenario comparisons for QŪNAR v0.8.1.

No numerical model calculations are changed here. The library is session-scoped.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import hashlib
import json


def report_fingerprint(payload: dict) -> str:
    """Exclude computation time and presentation-only text from repeat detection."""
    evidence = {k: payload.get(k) for k in
        ('mode_key', 'lang', 'assessment_year', 'assessment_type', 'climate_period',
         'inputs', 'summary', 'analysis', 'recommendations', 'table', 'chart')}
    encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:24]


def normalize_report_library(basket: dict) -> dict:
    """Upgrade old mode-keyed baskets without deleting an existing report."""
    if not isinstance(basket, dict):
        return {}
    result = {}
    for payload in basket.values():
        if isinstance(payload, dict):
            result.setdefault(report_fingerprint(payload), payload)
    return result


def add_report(basket: dict, payload: dict) -> bool:
    """True when a new scenario is added; identical inputs/outputs are deduplicated."""
    report_id = report_fingerprint(payload)
    if report_id in basket:
        return False
    basket[report_id] = deepcopy(payload)
    return True


def selected_reports(basket: dict, include: dict) -> list[dict]:
    return [deepcopy(payload) for rid, payload in basket.items() if include.get(rid, True)]


def _row_map(rows, key_idx=0, val_idx=1):
    data = {}
    counts = {}
    for row in rows or []:
        if len(row) <= max(key_idx, val_idx):
            continue
        key = str(row[key_idx])
        counts[key] = counts.get(key, 0) + 1
        if counts[key] > 1:
            key = f'{key} ({counts[key]})'
        data[key] = str(row[val_idx])
    return data


def _summary_map(payload):
    return _row_map([(r.get('label', ''), r.get('value', '')) for r in payload.get('summary', []) or [] if isinstance(r, dict)])


def compare_pair(baseline: dict, proposed: dict) -> dict:
    """Only report changed inputs and changed output indicators, without claiming causation."""
    a = _row_map(baseline.get('inputs'))
    b = _row_map(proposed.get('inputs'))
    sa = _summary_map(baseline)
    sb = _summary_map(proposed)
    return {
        'inputs': [(key, a.get(key, '—'), b.get(key, '—')) for key in dict.fromkeys([*a, *b]) if a.get(key) != b.get(key)],
        'results': [(key, sa.get(key, '—'), sb.get(key, '—')) for key in dict.fromkeys([*sa, *sb]) if sa.get(key) != sb.get(key)],
    }


def compared_variants(payloads: list[dict]) -> list[dict]:
    """Compare the first variant of a mode with each later selected variant."""
    by_mode = defaultdict(list)
    for payload in payloads:
        by_mode[str(payload.get('mode_key', 'unknown'))].append(payload)
    groups = []
    for mode, items in by_mode.items():
        if len(items) < 2:
            continue
        base = items[0]
        for n, candidate in enumerate(items[1:], 2):
            groups.append({'mode_key': mode, 'mode_label': base.get('mode_label', mode),
                           'baseline': 1, 'candidate': n, **compare_pair(base, candidate)})
    return groups


def condensed_variants(payloads: list[dict]) -> list[dict]:
    """Full first version; subsequent versions show only differences and changed tables.

    The comparison section lists changed inputs/outcomes. An unchanged source table
    remains available in the first, fully documented scenario of the same mode.
    """
    first = {}
    out = []
    for payload in payloads:
        mode = str(payload.get('mode_key', 'unknown'))
        if mode not in first:
            first[mode] = payload
            copy = deepcopy(payload)
            copy['variant_number'] = 1
            out.append(copy)
            continue
        base = first[mode]
        diff = compare_pair(base, payload)
        copy = deepcopy(payload)
        copy['variant_number'] = sum(1 for p in out if p.get('mode_key') == mode) + 1
        changed_keys = set(k for k, _, _ in diff['inputs'])
        changed_results = set(k for k, _, _ in diff['results'])
        # Preserve the original display labels / notes for changed outcomes.
        copy['inputs'] = [row for row in payload.get('inputs', []) if str(row[0]) in changed_keys]
        copy['summary'] = [row for row in payload.get('summary', []) if str(row.get('label')) in changed_results]
        if payload.get('table') == base.get('table'):
            copy['table'] = None
        if payload.get('chart') == base.get('chart'):
            copy['chart'] = None
        if payload.get('recommendations') == base.get('recommendations'):
            copy['recommendations'] = []
        if payload.get('analysis') == base.get('analysis'):
            copy['analysis'] = []
        out.append(copy)
    return out

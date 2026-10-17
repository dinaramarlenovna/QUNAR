"""Conservative environmental decision support for QŪNAR v0.8.1.

Compare LIKE-FOR-LIKE scenario quantities only. A rise is a risk signal,
not automatically a breach of a statutory limit. Incomplete inventories cannot
be certified as green. Never censor a computed economic result.
"""
from __future__ import annotations
from math import isfinite


def _optional_nonnegative(value, name):
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be numeric or unknown') from exc
    if not isfinite(x) or x < 0:
        raise ValueError(f'{name} must be finite and nonnegative')
    return x


def _optional_margin(value, name):
    if value is None:
        return None
    try:
        x = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be numeric or unknown') from exc
    if not isfinite(x):
        raise ValueError(f'{name} must be finite')
    return x


def evaluate_green_guard(*, water_before_m3=None, water_after_m3=None,
                         ghg_before_kgco2e=None, ghg_after_kgco2e=None,
                         margin_before_kzt=None, margin_after_kzt=None,
                         water_cap_m3=None, ghg_cap_kgco2e=None,
                         comparable=True, evidence='',
                         emissions_scope='partial operational emissions'):
    """Return status, not a synthetic environmental index.

    status: red / amber / green_conditional / incomplete / noncomparable.
    Absolute caps are optional EXPLICIT user limits, never invented policy caps.
    """
    wb = _optional_nonnegative(water_before_m3, 'baseline water')
    wa = _optional_nonnegative(water_after_m3, 'scenario water')
    gb = _optional_nonnegative(ghg_before_kgco2e, 'baseline GHG')
    ga = _optional_nonnegative(ghg_after_kgco2e, 'scenario GHG')
    mb = _optional_margin(margin_before_kzt, 'baseline margin')
    ma = _optional_margin(margin_after_kzt, 'scenario margin')
    wc = _optional_nonnegative(water_cap_m3, 'water cap')
    gc = _optional_nonnegative(ghg_cap_kgco2e, 'GHG cap')
    if not isinstance(comparable, bool):
        raise ValueError('comparability must be explicitly true/false')
    wd = wa - wb if wb is not None and wa is not None else None
    gd = ga - gb if gb is not None and ga is not None else None
    md = ma - mb if mb is not None and ma is not None else None

    def positive(delta, before, after):
        return delta is not None and delta > max(1e-6, abs(before)*1e-9, abs(after)*1e-9)

    w_up = positive(wd, wb, wa)
    g_up = positive(gd, gb, ga)
    w_cap_bad = wc is not None and wa is not None and wa > wc+max(1e-6,wc*1e-9)
    g_cap_bad = gc is not None and ga is not None and ga > gc+max(1e-6,gc*1e-9)
    missing = [k for k, val in [('water',wd),('GHG',gd)] if val is None]
    if not comparable:
        state = 'noncomparable'
    elif w_cap_bad or g_cap_bad or w_up and g_up:
        state = 'red'
    elif g_up:
        # A carbon-footprint increase is red even when margin is unavailable.
        state = 'red'
    elif w_up:
        state = 'red' if md is not None and md > 0 else 'amber'
    elif missing:
        state = 'incomplete'
    elif wd < -1e-6 or gd < -1e-6:
        state = 'green_conditional'
    else:
        state = 'neutral'
    return {
        'status':state, 'water_change_m3':wd,
        'partial_ghg_change_kgco2e':gd, 'margin_change_kzt':md,
        'water_increase':w_up,'ghg_increase':g_up,
        'explicit_water_cap_breached':w_cap_bad,
        'explicit_ghg_cap_breached':g_cap_bad,
        'unknown_comparisons':missing, 'comparable':comparable,
        'comparison_scope':emissions_scope,
        'evidence':str(evidence or ''),
        'full_footprint_certified':False,
        'legally_noncompliant':None,
        'scenario_not_observed':True,
        'recommendation': (
            'Reject automatic green endorsement; compare a water-and-partial-GHG constrained alternative.'
            if state in ('red','amber') else
            'Collect missing matched activity data before environmental endorsement.'
            if state in ('incomplete','noncomparable') else
            'Review feasible margin and uncertainty; a partial comparison is not full-life-cycle proof.'
        ),
    }


def alert_text(out: dict, lang: str='ru') -> tuple[str,str,str]:
    """Return heading, message and steering recommendation in one language."""
    lang = lang if lang in ('ru','kk','en') else 'en'
    status = out['status']
    both = out['water_increase'] and out['ghg_increase']
    mplus = out['margin_change_kzt'] is not None and out['margin_change_kzt'] > 0
    labels = {
        'ru': {
            'red': 'ЭКОЛОГИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ: рост нагрузки',
            'amber': 'ВНИМАНИЕ: экологическая нагрузка увеличивается',
            'incomplete': 'ЭКОЛОГИЧЕСКИЙ ВЫВОД НЕ ПОДТВЕРЖДЁН',
            'noncomparable': 'Нельзя сравнить сценарии по экологии',
            'green_conditional': 'Условно благоприятная экологическая динамика',
            'neutral': 'По доступным показателям роста нагрузки нет',
            'both': 'Одновременно увеличиваются водопотребление и учтённые выбросы CO₂e.',
            'margin': 'Маржа увеличивается, но это не компенсирует рост нагрузки на окружающую среду.',
            'cap':'Превышено указанное пользователем ограничение. Это не автоматически нарушение закона.',
            'unknown':'Неполные данные не позволяют подтвердить экологическую приемлемость.',
            'steer':'Сравните режим «Устойчивый компромисс»: вода и частичные выбросы не выше исходных, маржа с указанным допуском. Не скрывайте экономический результат.',
            'boundary':'Учтённые выбросы являются частичным сценарным расчётом, не полным углеродным следом и не фактическим эффектом.',
        },
        'kk': {
            'red':'ЭКОЛОГИЯЛЫҚ ЕСКЕРТУ: жүктеме артып отыр',
            'amber':'НАЗАР АУДАРЫҢЫЗ: экологиялық жүктеме артты',
            'incomplete':'ЭКОЛОГИЯЛЫҚ ҚОРЫТЫНДЫ РАСТАЛМАҒАН',
            'noncomparable':'Сценарийлерді экологиялық тұрғыда салыстыру мүмкін емес',
            'green_conditional':'Шартты түрде жағымды экологиялық өзгеріс',
            'neutral':'Белгілі көрсеткіштер бойынша жүктеме артқан жоқ',
            'both':'Су тұтыну да, есепке алынған CO₂e шығарындылары да өсті.',
            'margin':'Маржа артқаны экологиялық жүктеменің өсуін өтемейді.',
            'cap':'Пайдаланушы белгілеген шек асырылды. Бұл автоматты түрде заң бұзу емес.',
            'unknown':'Деректер толық емес: экологиялық қолайлылық расталмайды.',
            'steer':'«Тұрақты ымыра» режимін салыстырыңыз: су мен ішінара шығарындылар бастапқы деңгейден аспайды, маржа үшін рұқсат етілген төмендеу көрсетіледі.',
            'boundary':'Бұл ішінара сценарийлік шығарындылар есебі, толық көміртек ізі немесе нақты нәтиже емес.',
        },
        'en': {
            'red':'ENVIRONMENTAL WARNING: rising resource burden',
            'amber':'CAUTION: environmental burden increases',
            'incomplete':'ENVIRONMENTAL ASSESSMENT NOT VERIFIED',
            'noncomparable':'Scenarios cannot be compared environmentally',
            'green_conditional':'Conditionally favourable environmental change',
            'neutral':'No rise in the known environmental indicators',
            'both':'Both water use and included CO₂e emissions increase.',
            'margin':'Higher contribution margin does not offset increased environmental pressure.',
            'cap':'A user-entered limit was exceeded; this is not an automatic legal breach.',
            'unknown':'Missing data prevent an environmental endorsement.',
            'steer':'Compare the Sustainable compromise mode, constraining water and partial GHG at baseline and setting an explicit margin tolerance.',
            'boundary':'GHG covers only documented scenario components, not a full footprint or achieved mitigation.',
        },
    }[lang]
    parts = []
    if both:
        parts.append(labels['both'])
    if mplus and (out['water_increase'] or out['ghg_increase']):
        parts.append(labels['margin'])
    if out['explicit_water_cap_breached'] or out['explicit_ghg_cap_breached']:
        parts.append(labels['cap'])
    if status in ('incomplete','noncomparable') or out['unknown_comparisons']:
        parts.append(labels['unknown'])
    parts.append(labels['boundary'])
    return labels[status], ' '.join(parts), labels['steer']

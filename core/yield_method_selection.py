"""Transparent crop-wise yield-method routing for QUNAR v0.8.1.

The random-forest estimate is ALWAYS computed/reported for the six originally
trained crops. It is the active estimate only if independent forward validation
passes pre-specified conservative thresholds. Otherwise descriptive historic
statistics are offered as an *unvalidated planning reference*, not a forecast.

Earlier-window comparisons are method diagnostics, never post-hoc selection by
2021-2025 holdout. No source panel is invented for the other catalog crops.
"""
from dataclasses import dataclass
from pathlib import Path
from math import isfinite
import csv
import statistics

VALIDATED_ML_CROPS = frozenset(('Wheat','Corn','Rice','Cotton','Sunflower','Potato'))
METHODS = ('Pooled RF','Per-crop RF','ExtraTrees','CatBoost',
           'HistGradientBoosting','Ridge','Historical median','Last-three-year mean')

@dataclass(frozen=True)
class YieldMethodResult:
    crop: str
    active_value: float | None
    active_method: str
    rf_value: float | None
    ml_supported: bool
    reference_value: float | None
    reference_n: int
    reference_years: tuple[int,...]
    recent_mean: float | None
    recent_years: tuple[int,...]
    disclaimer: str


def _valid_number(v):
    try: x=float(v)
    except (ValueError,TypeError): return None
    return x if isfinite(x) and x>0 else None


def _observed_district_crop(data_dir,district,crop,assessment_year):
    """Historical yields strictly preceding assessment year and unique by year.

    Explicit exclusion: barley's unreliable wheat-duplicated yield series.
    """
    if str(crop)=='Barley':return []
    file=Path(data_dir)/'analytical_panel.csv'
    if not file.exists():return []
    observations={}
    with file.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r.get('District') != district or r.get('Crop') != crop:continue
            try:year=int(float(r['Year']))
            except (ValueError,TypeError,KeyError):continue
            if year>=int(assessment_year):continue
            val=_valid_number(r.get('Yield, centners/ha'))
            if val is None:continue
            # Do not silently average duplicate records for the same year.
            if year in observations and observations[year]!=val:
                raise ValueError('Contradictory district-crop-year yields')
            observations[year]=val
    return sorted(observations.items())


def all_method_history(evidence_dir,crop):
    """MAE evidence from training-era rolling 2011-2020 windows only.

    This is a historical comparison, NOT proof of future outperformance.
    """
    path=Path(evidence_dir)/'ml_rolling_by_crop.csv'
    if not path.exists():return []
    out=[]
    with path.open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r.get('crop') != crop or r.get('period')!='earlier_only':continue
            mae=_valid_number(r.get('MAE'))
            if mae is None:continue
            out.append({'method':r['model'],'n':int(r['n']),'mae_c_ha':mae,
                        'r2':float(r['R2'])})
    return sorted(out,key=lambda r:(r['mae_c_ha'],r['method']))


def route_yield(data_dir,district,crop,assessment_year,rf_value=None,
                *,minimum_n=30,minimum_r2=0.5,maximum_wape_pct=25.):
    """RF has first priority; insufficient forward evidence triggers reference.

    This selector does not tune candidate methods on the late 2021-25 period.
    Non-ML values are descriptive, not field-level or climate-specific forecasts.
    """
    from core.forecast_quality import forward_yield_evidence
    rf=_valid_number(rf_value)
    evidence=forward_yield_evidence(data_dir,crop,minimum_n=minimum_n,
                     minimum_r2=minimum_r2,maximum_wape_pct=maximum_wape_pct)
    rows=_observed_district_crop(data_dir,district,crop,assessment_year)
    vals=[x[1] for x in rows]
    ref=float(statistics.median(vals)) if len(vals)>=3 else None
    latest=(int(assessment_year)-3,int(assessment_year)-2,int(assessment_year)-1)
    recent=[(y,v) for y,v in rows if y in latest]
    trailing=sum(v for y,v in recent)/len(recent) if len(recent)>=2 else None
    supported=(str(crop) in VALIDATED_ML_CROPS and evidence.support=='historically_supported'
               and rf is not None)
    if supported:
        return YieldMethodResult(crop,rf,'Random Forest',rf,True,ref,len(vals),
                 tuple(y for y,v in rows),trailing,tuple(y for y,v in recent),
                 'RF has sufficient historical temporal backtest support; field accuracy not established')
    if ref is None and str(crop) in VALIDATED_ML_CROPS:
        # When a district has too few historical yield observations, the district
        # mean is UNAVAILABLE. A clearly marked oblast-level reference is safer
        # than silently presenting an unvalidated district ML point prediction.
        pool=[]
        source=Path(data_dir)/'analytical_panel.csv'
        if source.exists():
            with source.open(encoding='utf-8-sig',newline='') as f:
                for r in csv.DictReader(f):
                    if r.get('Crop')!=crop: continue
                    try:yr=int(float(r['Year']))
                    except (ValueError,TypeError,KeyError):continue
                    if yr>=int(assessment_year):continue
                    v=_valid_number(r.get('Yield, centners/ha'))
                    if v is not None:pool.append(v)
        if len(pool)>=30:
            regional_median=float(statistics.median(pool))
            return YieldMethodResult(crop,regional_median,'Regional crop median (proxy)',rf,False,
                   regional_median,len(pool),tuple(y for y,v in rows),None,(),
                   'District history has fewer than 3 observations; oblast-wide crop median is a descriptive proxy, not a validated district or field forecast')
    if ref is not None:
        detail=('RF temporal backtest is insufficient; '
                if str(crop) in VALIDATED_ML_CROPS else
                'No validated ML yield series for this crop; ')
        return YieldMethodResult(crop,ref,'Historical district-crop median',rf,False,ref,len(vals),
            tuple(y for y,v in rows),trailing,tuple(y for y,v in recent),
            detail+'historical median is DESCRIPTIVE, not validated next-season yield')
    return YieldMethodResult(crop,None,'Not verified',rf,False,None,len(vals),
        tuple(y for y,v in rows),trailing,tuple(y for y,v in recent),
        'Neither supported crop-level RF nor sufficient verified district-crop history; no numeric yield provided')

_METHOD_TRANSLATIONS = {
    'Random Forest':('Random Forest','Random Forest','Random Forest'),
    'Historical district-crop median':('Историческая медиана района и культуры',
                 'Аудан мен дақылдың тарихи медианасы','Historical district-crop median'),
    'Regional crop median (proxy)':('Областная медиана культуры (справочно)',
                 'Дақылдың облыстық медианасы (анықтамалық)','Regional crop median (proxy)'),
    'Not verified':('Достоверная оценка отсутствует', 'Расталған баға жоқ','Not verified')
}


def method_label(method,lang='ru'):
    return _METHOD_TRANSLATIONS.get(method,(method,method,method))[{'ru':0,'kk':1,'en':2}.get(lang,2)]


def method_caveat(result,lang='ru'):
    """Translate material limits instead of exporting internal English messages."""
    m=result.active_method
    if m=='Random Forest':
        return {'ru':'Порог временной проверки пройден; точность отдельного поля не установлена.',
                'kk':'Уақыттық тексеру шегі орындалған; нақты танап дәлдігі расталмаған.',
                'en':'Temporal validation threshold passed; individual-field accuracy not established.'}.get(lang,'')
    if m=='Historical district-crop median':
        return {'ru':f'RF не прошёл критерии временной проверки. Историческая медиана по {result.reference_n} районным наблюдениям — справочный ориентир, не проверенный прогноз на следующий год.',
                'kk':f'RF уақыттық тексеруден өтпеді. {result.reference_n} аудандық бақылаудың медианасы — анықтамалық көрсеткіш, келесі жыл болжамы емес.',
                'en':f'RF forward validation failed. Historical median of {result.reference_n} district observations is a descriptive reference, not a validated next-year forecast.'}.get(lang,'')
    if m=='Regional crop median (proxy)':
        return {'ru':'В районе меньше трёх наблюдений по культуре. Использована областная медиана с иной территориальной применимостью; прогноз участка не подтверждён.',
                'kk':'Ауданда үштен аз бақылау бар. Облыстық медиана анықтамалық қана; танап болжамы расталмаған.',
                'en':'Fewer than 3 district observations. Oblast-wide median is a proxy, not a validated district or field forecast.'}.get(lang,'')
    return {'ru':'Ни ML, ни достаточный исторический ряд недоступны. Численный прогноз не приводится.',
            'kk':'ML және жеткілікті тарихи деректер жоқ. Сандық болжам жоқ.',
            'en':'Neither supported ML nor sufficient historical data. No numeric forecast is supplied.'}.get(lang,'')

"""CCKP CMIP6 scenario inputs for QUNAR v0.8.1.

This is an additive scenario layer, not a training dataset. Regional label on
CCKP is Yujno-kazachstanskaya; its historical administrative boundaries may
not coincide with the current Turkestan region. Reference: 1995-2014.
"""
from dataclasses import dataclass
from pathlib import Path
import csv
from math import isfinite

MONTHS = ('Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep')
DAYS = (30, 31, 30, 31, 31, 30)
SCENARIOS = ('SSP2-4.5', 'SSP5-8.5')
BASELINE = '1995-2014'
PROJECTION = '2040-2059'


def _number(value):
    try:
        result = float(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid CCKP numeric observation: {value!r}') from exc
    if not isfinite(result):
        raise ValueError('Non-finite CCKP observation')
    return result


def cckp_csv_series(path, scenario, *, baseline=False):
    """Read CCKP ';' separated monthly CSV; no guessing values from charts."""
    if scenario not in SCENARIOS:
        raise ValueError(f'unsupported scenario: {scenario}')
    col = 'Historical Ref. Period 1995-2014' if baseline else scenario
    with Path(path).open(encoding='utf-8-sig', newline='') as fh:
        reader = csv.DictReader(fh, delimiter=';')
        if not reader.fieldnames or col not in reader.fieldnames:
            raise ValueError(f'missing CCKP column: {col}')
        rows = {}
        for r in reader:
            label = (r.get('Category') or '').strip()
            if label in rows:
                raise ValueError(f'Duplicate CCKP month/category: {label}')
            rows[label] = r
    if any(m not in rows for m in MONTHS):
        raise ValueError('missing April-September monthly records')
    return tuple(_number(rows[m][col]) for m in MONTHS)


def weighted_temperature_anomaly(values):
    """Seasonal mean temperature shift, weighted by calendar days."""
    if len(values) != len(DAYS) or any(not isfinite(float(v)) for v in values):
        raise ValueError('Temperature anomaly requires six finite Apr-Sep monthly values')
    return sum(v * d for v, d in zip(values, DAYS)) / sum(DAYS)


def precipitation_anomaly_pct(monthly_delta_mm, baseline_monthly_mm):
    """Seasonal change relative to baseline total, not mean of monthly %."""
    if (len(monthly_delta_mm) != len(baseline_monthly_mm) or not monthly_delta_mm
            or any(not isfinite(float(v)) for v in (*monthly_delta_mm, *baseline_monthly_mm))
            or any(v < 0 for v in baseline_monthly_mm)):
        raise ValueError('Invalid or unmatched monthly precipitation inputs')
    total = sum(baseline_monthly_mm)
    if total <= 0:
        raise ValueError('baseline precipitation must be positive')
    return 100.0 * sum(monthly_delta_mm) / total


@dataclass(frozen=True)
class ClimateScenario:
    scenario: str
    temperature_change_monthly_c: tuple
    precipitation_change_monthly_mm: tuple
    baseline_precip_monthly_mm: tuple
    days_over_35_monthly: tuple = ()
    days_over_40_monthly: tuple = ()
    days_over_45_monthly: tuple = ()

    @property
    def temperature_change_c(self):
        return weighted_temperature_anomaly(self.temperature_change_monthly_c)

    @property
    def precipitation_change_mm(self):
        return sum(self.precipitation_change_monthly_mm)

    @property
    def precipitation_change_pct(self):
        return precipitation_anomaly_pct(self.precipitation_change_monthly_mm,
                                         self.baseline_precip_monthly_mm)

    def as_dict(self):
        return {
            'scenario': self.scenario,
            'period': PROJECTION,
            'reference_period': BASELINE,
            'region_source_label': 'Yujno-kazachstanskaya',
            'source': 'World Bank Climate Change Knowledge Portal, CMIP6',
            'temperature_change_c': self.temperature_change_c,
            'precipitation_change_mm': self.precipitation_change_mm,
            'precipitation_change_pct': self.precipitation_change_pct,
            'days_over_35': sum(self.days_over_35_monthly) if self.days_over_35_monthly else None,
            'days_over_40': sum(self.days_over_40_monthly) if self.days_over_40_monthly else None,
            'days_over_45': sum(self.days_over_45_monthly) if self.days_over_45_monthly else None,
            'status': 'regional scenario estimate, not observed farm climate',
        }


def load_scenario(data_dir, scenario):
    """Consume shipped source CSVs without re-training the historical model."""
    d = Path(data_dir)
    args = dict(
        scenario=scenario,
        temperature_change_monthly_c=cckp_csv_series(d / 'temperature_anomaly.csv', scenario),
        precipitation_change_monthly_mm=cckp_csv_series(d / 'precipitation_anomaly.csv', scenario),
        baseline_precip_monthly_mm=cckp_csv_series(d / 'precipitation_mean.csv', scenario, baseline=True),
        days_over_35_monthly=cckp_csv_series(d / 'days_over_35_mean.csv', scenario),
        days_over_40_monthly=cckp_csv_series(d / 'days_over_40_mean.csv', scenario),
        days_over_45_monthly=cckp_csv_series(d / 'days_over_45_mean.csv', scenario),
    )
    for threshold in (35, 40, 45):
        series = args[f'days_over_{threshold}_monthly']
        if any(v < 0 or v > days + 1e-6 for v, days in zip(series, DAYS)):
            raise ValueError(f'CCKP projected >{threshold} °C days outside calendar limits')
    for d35, d40, d45 in zip(args['days_over_35_monthly'],
                                args['days_over_40_monthly'],
                                args['days_over_45_monthly']):
        if d35 + 1e-6 < d40 or d40 + 1e-6 < d45:
            raise ValueError('CCKP heat-day exceedance counts are not nested')
    return ClimateScenario(**args)

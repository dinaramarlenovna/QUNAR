"""2004 legal evidence for historical crop cost proportions, NOT modern farm prices.

Never load the 2004 KZT/ha as 2026 variable costs or subtract them from
current output revenue: changing input prices and water/energy duplication.
"""
from __future__ import annotations
from csv import DictReader
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / 'data' / 'south_kazakhstan_crop_cost_norms_2004.csv'
SOURCE_URL='https://adilet.zan.kz/rus/docs/P040000839_'


def historic_cost_mix(crop: str, *, agrozone: str | None = None,
                      irrigation: str | None = None, technology: str | None = None):
    """Return verified historical cost components, never a current currency fallback.

    Multiple candidate rows are intentionally returned where climate zone or
    technology cannot be matched. The caller may not choose an arbitrary row.
    """
    with _DATA.open(encoding='utf-8', newline='') as handle:
        records = list(DictReader(handle))
    records = [r for r in records if r['crop_code'] == crop]
    if agrozone is not None:
        records = [r for r in records if r['agrozone'] == agrozone]
    if irrigation is not None:
        records = [r for r in records if r['water_regime'] == irrigation]
    if technology is not None:
        records = [r for r in records if r['technology'] == technology]
    out=[]
    for r in records:
        total=float(r['total_cost_kzt_ha_2004'])
        subtotal=float(r['wages_fuel_seeds_kzt_ha_2004'])
        if not 0 <= subtotal <= total:
            raise ValueError('Inconsistent historical government table')
        out.append({**r,'historic_share_wages_fuel_seeds':subtotal/total,
                    'current_cost_kzt_ha':None,'source_status':'historical_2004_only'})
    return out

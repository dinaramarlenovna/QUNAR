import json
from datetime import date
import pytest
from core.regional_climate_cache import monthly_payload, daily_payload
from core.field_climate import fetch_farm_climate_normal
from core.fao56_irrigation import fetch_nasa_monthly_climatology


def _cache(tmp_path, monkeypatch):
    monkeypatch.setenv('QUNAR_NASA_CACHE_DIR',str(tmp_path))
    (tmp_path/'monthly').mkdir()
    (tmp_path/'manifest.json').write_text(json.dumps({'schema':'qunar-nasa-regional-cache-v1',
        'cells':[{'id':'cell1','latitude':42.,'longitude':68.125}]}))
    vals={'T2M':20,'T2M_MAX':25,'T2M_MIN':15,'RH2M':50,'WS2M':2,'PS':99,
          'PRECTOTCORR':1,'ALLSKY_SFC_SW_DWN':20,'GWETROOT':.3}
    payload={'properties':{'parameter':{name:{f'{y}{m:02d}':value
        for y in range(1995,2026) for m in range(1,13)} for name,value in vals.items()}}}
    (tmp_path/'monthly'/'cell1.json').write_text(json.dumps(payload))
    return payload


def test_offline_normal_1995_2025_and_cckp_baseline_separate(tmp_path,monkeypatch):
    _cache(tmp_path,monkeypatch)
    result=fetch_farm_climate_normal(42.,68.125)
    assert result['period_start']=='1995-04-01'
    assert result['period_end']=='2025-09-30'
    assert result['Apr-Sep root-zone wetness']==pytest.approx(.3)
    assert result['Apr-Sep precipitation, mm']==pytest.approx(183.)
    assert monthly_payload(42.1,68.1) is not None
    baseline=fetch_nasa_monthly_climatology(42.,68.125)
    assert len(baseline)==6
    assert baseline[0].rainfall_mm_month==30


def test_missing_cell_or_file_never_silent_partial(tmp_path,monkeypatch):
    _cache(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='does not cover'):monthly_payload(43,68.125)
    (tmp_path/'monthly'/'cell1.json').unlink()
    with pytest.raises(ValueError,match='missing/invalid'):monthly_payload(42,68.125)


def test_daily_cache_preserves_dates_across_years(tmp_path,monkeypatch):
    _cache(tmp_path,monkeypatch)
    path=tmp_path/'daily'/'cell1';path.mkdir(parents=True)
    for year,key in [(2024,'20241231'),(2025,'20250101')]:
        (path/f'{year}.json').write_text(json.dumps({'header':{'time_standard':'UTC'},'properties':{'parameter':{'T2M':{key:20}}}}))
    result=daily_payload(42,68.125,date(2024,12,31),date(2025,1,1))
    assert set(result['properties']['parameter']['T2M'])=={'20241231','20250101'}


def test_monthly_only_cache_keeps_live_daily_available(tmp_path,monkeypatch):
    _cache(tmp_path,monkeypatch)
    assert daily_payload(42,68.125,date(2025,4,1),date(2025,4,2)) is None


def test_partial_daily_cache_fails_instead_of_mixing_live_data(tmp_path,monkeypatch):
    _cache(tmp_path,monkeypatch)
    (tmp_path/'daily').mkdir()
    with pytest.raises(ValueError,match='missing/invalid daily'):
        daily_payload(42,68.125,date(2025,4,1),date(2025,4,2))


def test_daily_cache_rejects_local_solar_time(tmp_path,monkeypatch):
    _cache(tmp_path,monkeypatch)
    path=tmp_path/'daily'/'cell1';path.mkdir(parents=True)
    (path/'2025.json').write_text(json.dumps({'header':{'time_standard':'LST'},
        'properties':{'parameter':{'T2M':{'20250401':20}}}}))
    with pytest.raises(ValueError,match='UTC'):
        daily_payload(42,68.125,date(2025,4,1),date(2025,4,1))

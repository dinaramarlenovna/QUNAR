"""Sixth mode: mathematically consistent land/resource comparison, no false results."""
from pathlib import Path
import math
import pytest
from core.mixed_farm import compare_mixed_farm

CROPS=[
 {'crop':'Cotton','area_ha':30,'yield_c_ha':20,'price_kzt_t':310000,'other_cost_kzt_ha':540000,'grid_kwh_ha':950,'diesel_l_ha':120,'nitrogen_kg_n_ha':140},
 {'crop':'Wheat','area_ha':40,'yield_c_ha':24,'price_kzt_t':100000,'other_cost_kzt_ha':195000,'grid_kwh_ha':300,'diesel_l_ha':30,'nitrogen_kg_n_ha':80},
 {'crop':'Sunflower','area_ha':20,'yield_c_ha':14,'price_kzt_t':180000,'other_cost_kzt_ha':220000,'grid_kwh_ha':450,'diesel_l_ha':40,'nitrogen_kg_n_ha':60},
 {'crop':'Barley','area_ha':10,'yield_c_ha':20,'price_kzt_t':90000,'other_cost_kzt_ha':165000,'grid_kwh_ha':350,'diesel_l_ha':35,'nitrogen_kg_n_ha':70},
]

def calc(**changes):
    x=dict(district='Sauran District',crops=CROPS,pasture_ha=60.,crop_water_limit_m3=450000.,
        source_crop='Cotton',alternatives=[{'label':'A','convert_ha':0,'heads':0,'meat_t_year':0},
                                          {'label':'B','convert_ha':20,'heads':25,'meat_t_year':7},
                                          {'label':'C','convert_ha':30,'heads':40,'meat_t_year':10}],
        crop_water_price=1.16,electricity_price=41.06,diesel_price=300,
        cattle_price_kzt_t=1300000,cattle_other_cost_kzt_head=80000,
        dry_fodder_yield_t_ha_year=.35,purchased_feed_price_kzt_t=80000,
        purchase_feed_allowed=True,allowable_lu_ha=.30,legal_conversion_allowed=True,
        pasture_suitable=True,livestock_grid_kwh_per_head_year=40,livestock_diesel_l_per_head_year=16,
        livestock_water_limit_m3_year=1200)
    x.update(changes)
    return compare_mixed_farm(**x)

def test_three_scenarios_conserve_total_land():
    rs=calc()['scenarios']
    assert len(rs)==3
    assert [r['crop_area_ha'] for r in rs]==[100.,80.,70.]
    assert [r['pasture_ha'] for r in rs]==[60.,80.,90.]
    assert all(r['total_farm_ha']==160. for r in rs)
    assert [r['crop_water_m3'] for r in rs]==[437000.,303000.,236000.]
    assert all(r['feasible'] for r in rs)

def test_realistic_feed_balance_from_existing_reference():
    rs=calc()['scenarios']
    assert math.isclose(rs[1]['fodder_requirement_dm_t_year'],82.125)
    assert math.isclose(rs[1]['own_fodder_dm_t_year'],28)
    assert math.isclose(rs[1]['purchased_fodder_dm_t_year'],54.125)
    assert rs[1]['livestock_drinking_m3_year']>0
    assert rs[1]['partial_onsite_ghg_kg_co2e']>0
    assert rs[1]['embedded_feed_water_m3'] is None
    assert rs[1]['embedded_feed_ghg_kg_co2e'] is None
    assert not rs[1]['full_climate_comparability']

def test_missing_legal_and_forage_inputs_fail_closed():
    assert 'land_conversion_not_confirmed' in calc(legal_conversion_allowed=False)['scenarios'][1]['constraints']
    assert 'pasture_suitability_not_confirmed' in calc(pasture_suitable=False)['scenarios'][1]['constraints']
    assert 'crop_water_limit_unknown' in calc(crop_water_limit_m3=None)['scenarios'][0]['constraints']
    assert 'pasture_fodder_yield_unknown' in calc(dry_fodder_yield_t_ha_year=None)['scenarios'][1]['constraints']
    assert 'purchased_feed_price_unknown' in calc(purchased_feed_price_kzt_t=None)['scenarios'][1]['constraints']
    assert 'fodder_deficit_without_purchase' in calc(purchase_feed_allowed=False)['scenarios'][1]['constraints']

def test_no_double_count_water_or_feed_emissions():
    b=calc(feed_water_footprint_m3_t=100.,feed_ghg_footprint_kg_co2e_t=200.,
           manure_ghg_kg_co2e_head_year=120.)['scenarios'][1]
    assert math.isclose(b['embedded_feed_water_m3'],5412.5)
    assert math.isclose(b['total_water_including_external_feed_m3'],b['crop_water_m3']+b['livestock_drinking_m3_year']+5412.5)
    assert math.isclose(b['partial_ghg_including_feed_kg_co2e'],b['partial_onsite_ghg_kg_co2e']+54.125*200)
    assert b['full_climate_comparability']

def test_infeasible_water_and_pasture_loading():
    assert 'crop_water_limit_exceeded' in calc(crop_water_limit_m3=100000)['scenarios'][0]['constraints']
    assert 'pasture_capacity_exceeded' in calc(allowable_lu_ha=.1)['scenarios'][1]['constraints']
    assert 'livestock_water_limit_exceeded' in calc(livestock_water_limit_m3_year=10)['scenarios'][1]['constraints']

def test_no_invalid_or_double_counted_land():
    with pytest.raises(ValueError,match='exceeds'):
        calc(alternatives=[{'label':'A','convert_ha':0,'heads':0,'meat_t_year':0},{'label':'B','convert_ha':32,'heads':25,'meat_t_year':7}])
    with pytest.raises(ValueError,match='duplicate'):
        calc(crops=CROPS+[CROPS[0]])
    with pytest.raises(ValueError,match='negative'):
        calc(crops=[{**CROPS[0], 'price_kzt_t':-10}])

def test_ui_route_language_and_export_present():
    app=Path(__file__).resolve().parents[1]/'app.py'
    source=app.read_text(encoding='utf-8')
    assert '"mode5", "mode6"' in source
    assert "render_mixed_mode(lang=lang" in source
    assert "st.stop()" in source
    ui=(Path(__file__).resolve().parents[1]/'core/mixed_farm_ui.py').read_text(encoding='utf-8')
    assert "render_export_panel(report,lang)" in ui
    assert "'mode_key':'mode6'" in ui
    assert "Сравнить растениеводство и животноводство" in ui

def test_sixth_mode_renders_end_to_end_with_widget_double(monkeypatch):
    """Catch undefined locals and payload layout on the sixth route (offline widget double)."""
    from core import mixed_farm_ui
    from core.reporting import build_pdf_report,build_word_report,build_excel_report
    class FakeCtx:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def number_input(self,*args,**kwargs): return kwargs['value']
    class FakeST:
        def __init__(self): self.session_state={}; self.saved=[]; self.errors=[]
        def header(self,*a,**kw): pass
        def subheader(self,*a,**kw): pass
        def caption(self,*a,**kw): pass
        def info(self,*a,**kw): pass
        def warning(self,*a,**kw): pass
        def error(self,*a,**kw): self.errors.append(a)
        def columns(self,n): return [FakeCtx() for _ in range(n)]
        def expander(self,*a,**kw): return FakeCtx()
        def select_slider(self,*args,**kw): return kw['value']
        def selectbox(self,*args,**kw): return args[1][kw['index']] if 'index' in kw else args[1][0]
        def number_input(self,*a,**kw): return kw['value']
        def checkbox(self,*a,**kw): return kw.get('key') in ('qmix_legal','qmix_suitable','qmix_allow_feed')
        def button(self,*a,**kw): return kw.get('key')=='qmix_calculate'
        def dataframe(self,*a,**kw): pass
    fake=FakeST()
    monkeypatch.setattr(mixed_farm_ui,'st',fake)
    def render_export(report,lang):
        fake.saved.append(report)
        for f in (build_pdf_report,build_word_report,build_excel_report):
            assert len(f(report))>2000
    mixed_farm_ui.render_mixed_mode(lang='ru',district='Sauran District',
        district_title='Сауранский район',assessment_year=2027,render_export_panel=render_export)
    assert not fake.errors
    assert len(fake.saved)==1
    report=fake.saved[0]
    assert report['mode_key']=='mode6'
    assert len(report['table'])==3
    assert all(len(row)<=8 for row in report['table'])
    assert all('crop_' not in name for name in report['table'][0])

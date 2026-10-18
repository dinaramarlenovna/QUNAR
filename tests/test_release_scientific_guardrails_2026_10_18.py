from pathlib import Path
from core.forecast_quality import forward_yield_evidence,norm_vs_fao_comparison
from core.config import DATA_DIR


def test_forward_weak_crop_not_misrepresented_as_precise():
    for crop in ('Corn','Cotton','Potato','Rice','Sunflower','Wheat'):
        e=forward_yield_evidence(DATA_DIR,crop)
        assert e.support=='limited', (crop,e)
        assert e.tested_n>0
        assert e.r2 is not None
    assert forward_yield_evidence(DATA_DIR,'Rice').r2 < -3


def test_unavailable_validation_is_not_success(tmp_path):
    assert forward_yield_evidence(tmp_path,'Wheat').support == 'unverified'


def test_norm_vs_fao_avoids_fake_water_saving():
    m=norm_vs_fao_comparison(3550,12800.2)
    assert m['material_difference'] is True
    assert round(m['ratio_fao_to_norm'],2)==3.61
    assert m['comparable_effect'] is False
    assert norm_vs_fao_comparison(None,5000) is None
    assert norm_vs_fao_comparison(0,5000) is None


def test_crosschecks_applied_to_app_and_correct_text():
    code=(Path(__file__).parents[1]/'app.py').read_text(encoding='utf-8')
    assert 'forward_yield_evidence(DATA_DIR,crop)' in code
    assert 'norm_vs_fao_comparison(' in code
    assert 'Число RF — исследовательский ориентир' in code
    assert 'Разность НЕ является экономией' in code
    assert "ET₀ апрель–сентябрь, историческая NASA, мм" in code


def test_water_stress_and_norm_source_visible():
    root=Path(__file__).parents[1]
    code=(root/'app.py').read_text(encoding='utf-8')
    water=(root/'core'/'water_norms.py').read_text(encoding='utf-8')
    assert 'РЕЗЕРВ ВОДЫ ≤1%' in code
    assert '−10% и −20%' in code
    assert '16.09.2026' in water
    assert 'не подтверждено' in water


def test_legacy_fao_labels_translated():
    from core.report_localization import localize_string
    assert localize_string('FAO-56 gross irrigation scenario, m³/ha','ru').startswith('FAO-56: сценарная')
    assert localize_string('FAO field water delivery saving, m³/ha','kk').startswith('FAO:')


def test_a8_revised_coefficient_is_traceable_and_physical():
    from core.a8_reproducible_case import load_case,calculate_case
    from core.pumping_billing import pumping_kwh_per_m3
    import copy,pytest
    example=load_case(); tech=example['technical_assumptions']
    assert tech['water_supply_service_mode']=='gravity_with_separate_onfarm_pump'
    assert tech['pump_electricity_kwh_per_m3_field_delivery']==pytest.approx(pumping_kwh_per_m3(25,0.65))
    assert tech['grid_kg_co2e_per_kwh']==pytest.approx(0.813)
    res=calculate_case(example)
    assert res['normal']['optimized']['water_feasible'] is True
    assert res['stress']['optimized']['water_feasible'] is True
    bad=copy.deepcopy(example)
    bad['technical_assumptions']['pump_electricity_kwh_per_m3_field_delivery']=0.70509
    with pytest.raises(ValueError,match='head and efficiency'):
        calculate_case(bad)

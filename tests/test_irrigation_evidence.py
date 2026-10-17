from datetime import date
import pytest
from core.irrigation_evidence import (
    FIELD_EFFICIENCIES,field_efficiency,mixed_efficiency,irrigation_saving,
    parse_stage_lengths,monthly_kc_from_calendar,CROP_KC_STAGES,
)

def test_fao_field_application_values():
    assert FIELD_EFFICIENCIES == {'furrow':0.60,'sprinkler':0.75,'drip':0.90}
    assert field_efficiency('drip')==0.90

def test_unknown_and_mixed_never_silently_filled():
    for m in ('unknown','mixed','not_existing'):
        with pytest.raises(ValueError):field_efficiency(m)
    assert field_efficiency('mixed',override=0.72)==0.72

def test_reference_water_saving():
    x=irrigation_saving(3000,0.60,0.90,area_ha=100)
    assert x['baseline_m3_ha']==pytest.approx(5000)
    assert x['proposed_m3_ha']==pytest.approx(3333.3333333)
    assert x['saving_pct']==pytest.approx(33.333333)
    assert x['saving_m3_field']==pytest.approx(166666.666667)

def test_bad_efficiencies_rejected():
    for x in (0,-1,1.1,float('nan'),None):
        with pytest.raises((ValueError,TypeError)): field_efficiency('drip',override=x) if x is not None else field_efficiency('mixed')

def test_mixed_harmonic_efficiency():
    eta=mixed_efficiency({'furrow':0.5,'sprinkler':0,'drip':0.5})
    assert eta==pytest.approx(0.72)
    assert 3000/eta==pytest.approx(0.5*3000/0.6+0.5*3000/0.9)

def test_mixed_shares_must_sum_to_one():
    with pytest.raises(ValueError): mixed_efficiency({'furrow':0.4,'sprinkler':0.3,'drip':0.2})
    with pytest.raises(ValueError): mixed_efficiency({'furrow':0.2,'sprinkler':-0.1,'drip':0.9})

def test_no_arbitrary_rice_reference():
    assert 'Rice' not in CROP_KC_STAGES
    with pytest.raises(ValueError): monthly_kc_from_calendar('Rice',date(2025,4,1))

def test_stage_calendar_uses_planting_dates():
    kc=monthly_kc_from_calendar('Corn',date(2025,5,1))
    assert kc[0]==0.0
    assert kc[1]>0.0
    assert kc[-1]>=0.0
    assert len(kc)==6

def test_stage_override_changes_kc():
    a=monthly_kc_from_calendar('Potato',date(2025,4,1))
    b=monthly_kc_from_calendar('Potato',date(2025,4,1),(15,20,40,30))
    assert a!=b

def test_no_crop_outside_season():
    with pytest.raises(ValueError): monthly_kc_from_calendar('Cotton',date(2024,1,1))

def test_lengths_parse():
    assert parse_stage_lengths('20,30,50,20') == (20,30,50,20)
    for bad in ('0,1,1,1','10,3.5,10,10','1,2,3','1,-2,3,4'):
        with pytest.raises(ValueError): parse_stage_lengths(bad)

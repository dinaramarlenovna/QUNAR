from core.survey_weights import survey_proxy_profile
from core.optimizer import optimize_structure


def test_survey_proxy_exact_aggregates():
    p = survey_proxy_profile()
    assert p['respondents'] == 208
    assert p['water_mentions'] == 120
    assert p['climate_mentions'] == 93
    assert abs(p['climate'] - 93/213) < 1e-12
    assert abs(p['water'] - 120/213) < 1e-12
    assert abs(p['climate'] + p['water'] - 1) < 1e-12
    assert 'sensitivity' in p['method']


def test_survey_profile_does_not_override_baseline():
    kw = dict(district='Maktaaral District', area_ha=100.,n_crops=2,max_share=.6,
              available_water_m3=2000000., objective_mode='resource')
    _,base=optimize_structure(profile='balanced',**kw)
    _,alt=optimize_structure(profile='survey_proxy',**kw)
    assert base.get('climate_weight') == .60
    assert base.get('water_weight') == .40
    assert abs(alt.get('climate_weight')-93/213)<1e-12
    assert abs(alt.get('water_weight')-120/213)<1e-12
    assert 'exploratory' in alt.get('profile_source','')

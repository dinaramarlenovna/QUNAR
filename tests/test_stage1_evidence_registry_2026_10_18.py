"""Evidence-governed reference conversions, distinct from missing farm activity."""
import pytest
from core.evidence_registry import (
    validate_energy_sources, SOURCE_LABELS, SOURCES, diesel_combustion_factor,
    fertilizer_nitrogen_kg, direct_fertilizer_n2o_co2e, enteric_tier1_ch4,
    source_disclaimer)
from core.reference_fallbacks import irrigation_water_fallback, conditional_pumping_energy


def test_user_must_classify_operational_sources_with_non_fossil_options():
    with pytest.raises(ValueError):
        validate_energy_sources([])
    assert validate_energy_sources(['outsourced', 'manual_animal']) == ('outsourced', 'manual_animal')
    assert validate_energy_sources(['solar_pv', 'solar_pv']) == ('solar_pv',)
    for lang in ('ru','kk','en'):
        assert SOURCE_LABELS[lang]['coal']
        assert SOURCE_LABELS[lang]['outsourced']
        assert source_disclaimer(lang)


def test_ipcc_diesel_combustion_is_a_conversion_not_an_activity_guess():
    assert diesel_combustion_factor() == pytest.approx(2.676492)
    with pytest.raises(ValueError):
        diesel_combustion_factor(density_kg_l=0)
    assert 'eur-lex' in SOURCES['ipcc_diesel'].url


def test_fertilizer_product_mass_is_not_nitrogen_mass():
    assert fertilizer_nitrogen_kg(product_kg=100, nitrogen_mass_fraction=None) is None
    assert fertilizer_nitrogen_kg(product_kg=100, nitrogen_mass_fraction=0.46) == pytest.approx(46)
    assert direct_fertilizer_n2o_co2e(nitrogen_kg=None) is None
    generic = direct_fertilizer_n2o_co2e(nitrogen_kg=46)
    arid = direct_fertilizer_n2o_co2e(nitrogen_kg=46,dry_climate=True)
    assert arid == pytest.approx(generic/2)
    with pytest.raises(ValueError):
        fertilizer_nitrogen_kg(product_kg=100, nitrogen_mass_fraction=1.1)


def test_livestock_enteric_is_not_whole_farm_footprint():
    assert enteric_tier1_ch4(species='Dairy cows',heads=10) == pytest.approx(780)
    assert enteric_tier1_ch4(species='Sheep',heads=10,fraction_of_year=.5) == pytest.approx(25)
    assert enteric_tier1_ch4(species='Poultry layers',heads=100) == 0.0
    assert enteric_tier1_ch4(species='Unknown',heads=10) is None
    assert enteric_tier1_ch4(species='Cattle',heads=None) is None


def test_rice_paddy_requires_technology_and_no_auto_pump_meter():
    no_tech=irrigation_water_fallback('Maktaaral District','Rice',1,'unknown')
    assert no_tech.value is None
    flooded=irrigation_water_fallback('Maktaaral District','Rice',2,'flooded')
    assert flooded.value == pytest.approx(52000)
    assert 'gov.kz' in flooded.url
    assert flooded.source_tier == 'regional_official_pilot'
    assert conditional_pumping_energy(6000,pumping_confirmed=True).value is None


def test_supplier_specific_tariffs_never_automatically_generalized():
    from core.regional_tariffs import supplier_tariff
    assert supplier_tariff('kazvodkhoz_irrigation_gravity_2026') is None
    assert supplier_tariff('kentau_canal_2026',provider_confirmed=True).value_kzt_unit == 0.86
    # Source uses KZT/1000 m3; the application must convert it.
    assert supplier_tariff('turkestan_canal_2026',provider_confirmed=True).value_kzt_unit == pytest.approx(1.07315)
    assert supplier_tariff('electric_retail_commercial_2025_vat',provider_confirmed=True).unit == 'KZT/kWh'


def test_historical_2004_government_costs_never_become_current_monetary_fallback():
    from core.historical_crop_costs import historic_cost_mix, SOURCE_URL
    selected=historic_cost_mix('Cotton',agrozone='VIII subtropical desert',
        irrigation='irrigated',technology='scientific')
    assert len(selected)==1
    assert selected[0]['total_cost_kzt_ha_2004']=='63624'
    assert selected[0]['wages_fuel_seeds_kzt_ha_2004']=='31180'
    assert selected[0]['current_cost_kzt_ha'] is None
    assert 0 < selected[0]['historic_share_wages_fuel_seeds'] < 1
    assert historic_cost_mix('Rice')==[]
    assert SOURCE_URL.endswith('P040000839_')


def test_fertilizer_gost_nutrient_guarantees_and_sources():
    from core.evidence_registry import FERTILIZER_GOST_MIN_N_FRACTION, FERTILIZER_GOST_SOURCES
    assert FERTILIZER_GOST_MIN_N_FRACTION['urea_dry_B'] == pytest.approx(0.462)
    assert FERTILIZER_GOST_MIN_N_FRACTION['ammonium_nitrate_B_grade1_dry'] == pytest.approx(0.344)
    for product, source in FERTILIZER_GOST_SOURCES.items():
        assert 'ГОСТ' in SOURCES[source].name
        assert SOURCES[source].url.startswith('https://')
    assert fertilizer_nitrogen_kg(product_kg=100,
        nitrogen_mass_fraction=FERTILIZER_GOST_MIN_N_FRACTION['urea_dry_B']) == pytest.approx(46.2)


from core.ml import predict_yield
from core.resources import calculate_resources
from core.uncertainty import reliability_score

def test_prediction():
    pred, _ = predict_yield("Sauran District", "Corn", 20, {})
    assert pred >= 0

def test_resource_accounting():
    r = calculate_resources(
        area_ha=20,
        water_used_m3=100000,
        reuse_percent=10,
        energy_kwh=5000,
        electricity_ef=0.5,
        wapor_consumptive_water_m3=80000,
        predicted_yield_centners_ha=40,
    )
    assert abs(r["farm_freshwater_m3"] - 90000) < 1e-9
    assert abs(r["farm_water_m3_per_ha"] - 5000) < 1e-9
    assert abs(r["operational_co2e_kg"] - 2500) < 1e-9
    assert abs(r["wapor_consumptive_water_m3_per_ha"] - 4000) < 1e-9

def test_wapor_spatial_penalty():
    x = reliability_score(
        exact_location=True, live_climate=True, actual_water=True,
        actual_energy=True, emission_factor=True, wapor_used=True, wapor_pixels=1
    )
    assert x["spatial_penalty"] == 12
    assert x["score"] == 48

from core.admin_boundaries import detect_point, detect_polygon
from core.data import load_centroids

def test_admin_boundary_centroids_match():
    for district, (lat, lon) in load_centroids().items():
        match = detect_point(lat, lon)
        assert match is not None
        assert match['district'] == district

def test_sauran_polygon_point():
    lat, lon = load_centroids()['Sauran District']
    match = detect_point(lat, lon)
    assert match['district'] == 'Sauran District'

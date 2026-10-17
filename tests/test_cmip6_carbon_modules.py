import unittest
from pathlib import Path
from core.cmip6_scenarios import load_scenario, precipitation_anomaly_pct
from core.carbon_scenarios import partial_inventory, compare_partial_inventory
DATA = Path(__file__).resolve().parents[1] / 'data' / 'cmip6'

class AdditiveModulesTests(unittest.TestCase):
    def test_scenarios_from_actual_csv(self):
        mid=load_scenario(DATA, 'SSP2-4.5').as_dict()
        high=load_scenario(DATA, 'SSP5-8.5').as_dict()
        self.assertAlmostEqual(mid['precipitation_change_mm'], 1.59)
        self.assertAlmostEqual(high['precipitation_change_mm'], 1.03)
        self.assertTrue(1.95 < mid['temperature_change_c'] < 2.08)
        self.assertTrue(2.60 < high['temperature_change_c'] < 2.78)
        self.assertTrue(high['days_over_40'] > mid['days_over_40'])
        self.assertTrue(high['days_over_35'] > mid['days_over_35'])

    def test_precip_annualized_properly(self):
        self.assertAlmostEqual(precipitation_anomaly_pct([2,-1], [20,30]), 2)

    def test_carbon_and_uncertainty(self):
        old=partial_inventory(nitrogen_kg=100,diesel_litres=200,electricity_kwh=500,
                              grid_kg_co2e_kwh=.5,include_enteric=True,enteric_heads=2,
                              enteric_kg_ch4_head_year=50,enteric_year_fraction=1)
        new=partial_inventory(nitrogen_kg=80,diesel_litres=150,electricity_kwh=450,
                              grid_kg_co2e_kwh=.5,include_enteric=True,enteric_heads=2,
                              enteric_kg_ch4_head_year=50,enteric_year_fraction=1)
        self.assertGreater(compare_partial_inventory(old,new)['possible_reduction_kgco2e'],0)
        missing=partial_inventory(nitrogen_kg=None,diesel_litres=0,electricity_kwh=0,
                                  grid_kg_co2e_kwh=.5)
        self.assertFalse(missing.complete)
        with self.assertRaises(ValueError):
            compare_partial_inventory(old,missing)

if __name__=='__main__': unittest.main()

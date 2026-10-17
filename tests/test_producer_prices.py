import csv
from pathlib import Path

from core.producer_prices import reference_producer_price, DEFAULT_TABLE


def test_all_2025_exact_regional_prices():
    expected = {
        'Wheat': 100044, 'Corn': 99844, 'Rice': 183699,
        'Cotton': 255373, 'Sunflower': 135731, 'Potato': 177591,
        'Barley': 97129, 'Cabbage': 63325,
    }
    for crop, price in expected.items():
        p = reference_producer_price(crop, as_of_year=2026)
        assert p.price_kzt_t == price
        assert p.year == 2025
        assert p.source_cell.startswith('Q')
        assert p.price_kzt_t > 0


def test_historical_query_no_future_leakage():
    p = reference_producer_price('Wheat', as_of_year=2023)
    assert p.year == 2023
    assert p.price_kzt_t == 79863
    assert reference_producer_price('Wheat', as_of_year=2021) is None


def test_confidential_not_imputed():
    # 2023 rice suppressed: 2022 price exists and must remain dated 2022.
    p = reference_producer_price('Rice', as_of_year=2023)
    assert p.year == 2022
    assert p.price_kzt_t == 124710
    # All earlier sunflower observations are unpublished or suppressed.
    assert reference_producer_price('Sunflower', as_of_year=2024) is None


def test_no_substitution_of_nonmatching_crop_categories():
    for crop in ('Cucumbers','Tomatoes','PomeStone','Carrots','Onion','OtherFruits','OtherOilseeds'):
        assert reference_producer_price(crop, as_of_year=2026) is None


def test_dataset_coverage_and_flags():
    with DEFAULT_TABLE.open(encoding='utf-8', newline='') as fh:
        data=list(csv.DictReader(fh))
    assert len(data)==8*4
    assert len({(row['year'],row['crop_code']) for row in data})==32
    assert all(row['territory']=='Туркестанская область' for row in data)
    assert all(row['unit']=='KZT/t, excl. VAT' for row in data)
    assert all(row['source_file'] and row['source_cell'] and row['source_sheet'] for row in data)
    assert all(row['status'] in ('published','confidential','not_published') for row in data)
    assert all(bool(row['price_kzt_t']) == (row['status']=='published') for row in data)


def test_stale_reference_not_mislabeled_current():
    p = reference_producer_price('Wheat', as_of_year=2029)
    assert p.year == 2025
    assert p.years_old == 4
    assert '2025' in p.source_label
    assert 'не цена хозяйства' in p.source_label

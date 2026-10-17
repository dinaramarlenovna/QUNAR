"""Published annual agricultural producer prices for Turkestan oblast (BNS RK).

Reference values describe historical prices of the listed product category,
not farm-level sales contracts, price forecasts or net income.  Never fill
statistically suppressed or unpublished cells with inferred numbers.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TABLE = Path(__file__).resolve().parents[1] / 'data' / 'producer_prices_turkestan_2022_2025.csv'


@dataclass(frozen=True)
class ProducerPrice:
    crop_code: str
    year: int
    price_kzt_t: float
    product_label_ru: str
    source_file: str
    source_sheet: str
    source_cell: str
    as_of_year: int

    @property
    def years_old(self) -> int:
        return self.as_of_year - self.year

    @property
    def source_label(self) -> str:
        return (f'БНС РК, среднегодовая цена производителя по Туркестанской области, '
                f'{self.year}; {self.source_file}, лист {self.source_sheet}, '
                f'ячейка {self.source_cell}. Тг/т, без НДС. Справочный сценарий, не цена хозяйства.')


def reference_producer_price(crop_code: str, *, as_of_year: int, table_path: Path = DEFAULT_TABLE) -> ProducerPrice | None:
    """Latest *published* regional observation dated no later than as_of_year.

    A price is never substituted for a broader crop class (e.g. apples are not
    mapped to all pome/stone fruits). Missing/confidential values are excluded.
    If historical year y is modeled, callers must use as_of_year <= y-1.
    """
    as_of_year = int(as_of_year)
    candidate = None
    with Path(table_path).open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            if row['crop_code'] != str(crop_code) or int(row['year']) > as_of_year:
                continue
            if row['status'] != 'published' or not row['price_kzt_t']:
                continue
            year = int(row['year'])
            price = float(row['price_kzt_t'])
            if price <= 0:
                continue
            if candidate is None or year > candidate.year:
                candidate = ProducerPrice(
                    crop_code=str(crop_code), year=year,
                    price_kzt_t=price,
                    product_label_ru=row['product_label_ru'],
                    source_file=row['source_file'],
                    source_sheet=row['source_sheet'],
                    source_cell=row['source_cell'],
                    as_of_year=as_of_year,
                )
    return candidate

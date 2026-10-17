"""Source-labelled, service-type-specific reference tariffs for research scenarios.

Do not confuse drinking-water rates, regional canal rates, and pump delivery.
Do not add electricity transmission tariffs to full retail electricity tariffs.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date

KAZVODKHOZ_SOURCE = 'https://www.gov.kz/org/karaganda-tabigat/press/article/details/224741'
ELECTRIC_NOTICE_2025_11 = 'https://hearings.ndbecology.gov.kz/Public/PubHearings/LoadFile/245313'
ELECTRIC_RETAIL_SOURCE = ('https://energopotok.kz/wp-content/uploads/2025/07/'
    '%D0%98%D0%BD%D1%84%D0%BE%D1%80%D0%BC%D0%B0%D1%86%D0%B8%D1%8F-%D0%B4%D0%BB%D1%8F-'
    '%D1%81%D0%B0%D0%B9%D1%82%D0%B0-%D0%9E%D0%96%D0%A2-%D0%BF%D0%BE-'
    '%D1%81%D0%BD%D0%B0%D0%B1%D0%B6%D0%B5%D0%BD%D0%B8%D1%8E-%D1%80%D1%83%D1%81.pdf')

@dataclass(frozen=True)
class DocumentedTariff:
    value_kzt_unit: float
    unit: str
    provider: str
    source: str
    source_date: date
    tax_basis: str
    user_confirmation_required: bool
    caveat: str

REGIONAL_TARIFF_REFERENCES = {
    'electric_retail_commercial_2025_11_exvat': DocumentedTariff(
        41.06, 'KZT/kWh', 'Оңтүстік Жарық Транзит', ELECTRIC_NOTICE_2025_11,
        date(2025,11,1), 'excl VAT (45.9872 / 1.12)', True,
        'Documented November 2025 non-household tariff, VAT-removed for comparable costing; NOT independently confirmed for October 2026'),
    'electric_retail_commercial_2025_11_invat': DocumentedTariff(
        45.9872, 'KZT/kWh', 'Оңтүстік Жарық Транзит', ELECTRIC_NOTICE_2025_11,
        date(2025,11,1), 'incl VAT (2025 at 12%)', True,
        'Dated November 2025 tariff incl VAT; not verified for October 2026 and NOT comparable to water ex VAT without adjusting'),
    'electric_retail_commercial_2025_vat': DocumentedTariff(
        44.7552, 'KZT/kWh', 'Оңтүстік Жарық Транзит', ELECTRIC_RETAIL_SOURCE,
        date(2025,8,1), 'incl VAT', True,
        'HISTORICAL Aug-Oct 2025 tariff; replaced Nov 2025; NOT a current default'),
    'electric_retail_food_manufacturer_2025_vat': DocumentedTariff(
        38.4272, 'KZT/kWh', 'Оңтүстік Жарық Транзит', ELECTRIC_RETAIL_SOURCE,
        date(2025,8,1), 'incl VAT', True,
        'Only qualifying socially significant food manufacturer / industrial zone; not all farms'),
    'kazvodkhoz_irrigation_gravity_2026': DocumentedTariff(
        1.160, 'KZT/m³','РГП Казводхоз',KAZVODKHOZ_SOURCE,
        date(2026,1,1),'excl VAT',True,
        'Gravity canal supply for agricultural producers, only with that provider and supply method'),
    'kazvodkhoz_irrigation_pumped_2026': DocumentedTariff(
        44.120, 'KZT/m³','РГП Казводхоз',KAZVODKHOZ_SOURCE,
        date(2026,1,1),'excl VAT',True,
        'Mechanized canal supply for agricultural producers; service fee, not electricity kWh'),
    'saryagash_canal_2026': DocumentedTariff(
        0.282, 'KZT/m³','ГКП Сарыағаш ауданы су шаруашылығы',KAZVODKHOZ_SOURCE,
        date(2026,1,1),'as listed',True,
        'Only canals served by this specific local operator'),
    'ordabasy_canal_2026': DocumentedTariff(
        0.306, 'KZT/m³','ГКП Ордабасы су шаруашылығы',KAZVODKHOZ_SOURCE,
        date(2026,1,1),'as listed',True,
        'Only affected service area and published period (2025-10 to 2026-09)'),
    'kazygurt_canal_2026': DocumentedTariff(
        0.13734, 'KZT/m³','ГКП Қазығұрт су шаруашылығы',KAZVODKHOZ_SOURCE,
        date(2026,1,1),'as listed',True,
        'Only affected operator, service class and published period (2025-12 to 2026-11)'),
    'tolebi_canal_2026': DocumentedTariff(
        0.302, 'KZT/m³','ГКП Төлеби су шаруашылығы',KAZVODKHOZ_SOURCE,
        date(2026,1,1),'as listed',True,
        'Only affected operator and published period (2025-10 to 2026-09)'),
    'kentau_canal_2026': DocumentedTariff(
        0.86, 'KZT/m³','СПК Табақ бұлақ',KAZVODKHOZ_SOURCE,
        date(2026,1,1),'as listed',True,'Only this provider'),
    'turkestan_canal_2026': DocumentedTariff(
        1.07315, 'KZT/m³','ГКП Тұран су',KAZVODKHOZ_SOURCE,
        date(2026,1,1),'as listed',True,
        'Source quotes 1073.15 KZT per 1000 m³, correctly converted to 1.07315 per m³'),
}

def supplier_tariff(key: str | None, *, provider_confirmed=False) -> DocumentedTariff | None:
    """Rates available for informed selection only, not silently assigned to all farms."""
    if not provider_confirmed:
        return None
    return REGIONAL_TARIFF_REFERENCES.get(key)

"""Versioned source registry and defensible energy/accounting rules.

A source describing a conversion factor is not proof of a farm's activity level.
A normative amount is never silently relabelled as an observation.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable

ENERGY_SOURCES = (
    'grid_electricity', 'solar_pv', 'wind', 'diesel', 'petrol', 'natural_gas',
    'coal', 'biomass', 'outsourced', 'manual_animal', 'other',
)
SOURCE_LABELS = {
    'ru': {
        'grid_electricity':'Электроэнергия из сети', 'solar_pv':'Солнечная генерация',
        'wind':'Ветровая генерация', 'diesel':'Дизельное топливо',
        'petrol':'Бензин', 'natural_gas':'Природный газ', 'coal':'Уголь',
        'biomass':'Биотопливо/биомасса', 'outsourced':'Услуги подрядчика/аренда техники',
        'manual_animal':'Ручной труд/тягловые животные', 'other':'Другие источники',
    },
    'kk': {
        'grid_electricity':'Желіден алынатын электр энергиясы', 'solar_pv':'Күн генерациясы',
        'wind':'Жел генерациясы', 'diesel':'Дизель отыны', 'petrol':'Бензин',
        'natural_gas':'Табиғи газ', 'coal':'Көмір',
        'biomass':'Биоотын/биомасса', 'outsourced':'Мердігер/жалға алынған техника қызметі',
        'manual_animal':'Қол еңбегі/жегін мал', 'other':'Басқа энергия көздері',
    },
    'en': {
        'grid_electricity':'Grid electricity', 'solar_pv':'Solar PV generation',
        'wind':'Wind generation', 'diesel':'Diesel fuel', 'petrol':'Petrol/gasoline',
        'natural_gas':'Natural gas', 'coal':'Coal',
        'biomass':'Biofuel/biomass', 'outsourced':'Contracted equipment/services',
        'manual_animal':'Manual work/draught animals', 'other':'Other sources',
    },
}

@dataclass(frozen=True)
class Evidence:
    code: str
    name: str
    url: str
    year: int
    region: str
    status: str
    role: str
    caution: str = ''

SOURCES = {
    'historic_south_kazakhstan_costs_2004': Evidence('historic_south_kazakhstan_costs_2004',
        'Правительство РК № 839 от 2004 года, нормативы затрат по зонам бывшей Южно-Казахстанской области',
        'https://adilet.zan.kz/rus/docs/P040000839_',2004,'South Kazakhstan',
        'historical_official_only','Retains historic total and wages/fuel/seed subtotals: never use 2004 KZT as 2026 costs'),
    'water_2025': Evidence('water_2025','МВРИ РК № 108-НҚ от 04.06.2025, табл. 3',
        'https://adilet.zan.kz/rus/docs/V2500036253',2025,'Kazakhstan','official_historical',
        'Crop irrigation reference, original coefficients'),
    'water_2026': Evidence('water_2026','МВРИ РК № 288-НҚ от 09.09.2026, вступил 16.09.2026',
        'https://prg.kz/document/?doc_id=37089148',2026,'Kazakhstan','official_current_unmapped',
        'Current act; DO NOT relabel old coefficients without a row-by-row comparison'),
    'rice_turkestan_2026': Evidence('rice_turkestan_2026','Акимат Туркестанской области: пилотная технология выращивания риса',
        'https://www.gov.kz/memleket/entities/ontustik/press/news/details/1162846?lang=ru',
        2026,'Turkestan Region','regional_official_pilot','Traditional up to 26000 vs pilot drip 15000 m³/ha; not a general norm'),
    'fao_livestock_water': Evidence('fao_livestock_water',"FAO Livestock's Long Shadow (2006), Table 4.2",
        'https://www.fao.org/4/a0701e/a0701e04.pdf',2006,'International','methodological',
        'Drinking water under reference species/temperature, not all livestock farm water'),
    'fao_irrigation': Evidence('fao_irrigation','FAO Irrigation Water Management Training Manual 4, Annex I',
        'https://www.fao.org/4/t7202e/t7202e08.htm',1989,'International','methodological',
        'Field application efficiency, not conveyance efficiency'),
    'fao_rice': Evidence('fao_rice','FAO Irrigation Water Management, Chapter 4, §4.4 rice',
        'https://www.fao.org/4/s2022e/s2022e08.htm',1986,'International','methodological',
        'Include seepage, percolation, puddling, standing water'),
    'ipcc_diesel': Evidence('ipcc_diesel','IPCC 2006 Guidelines, Volume 2, Chapter 2, Table 2.2; Gas/Diesel Oil 74,100 kg CO2/TJ',
        'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A02018R2066-20240101',2006,'International','emission_method',
        'Combustion CO2 factor by energy, not farm activity; use fuel density and NCV'),
    'gost_diesel': Evidence('gost_diesel','ГОСТ 32511-2013, diesel density 820-845 kg/m³ at 15 °C',
        'https://base.garant.ru/57398418/',2013,'EAEU','fuel_specification',
        'Density range is a technical standard, not measured batch density'),
    'fertilizer_urea_gost': Evidence('fertilizer_urea_gost','ГОСТ 2081-2010, карбамид марки Б для растениеводства, азот ≥46.2% сухого вещества',
        'https://base.garant.ru/71439708/',2010,'EAEU','chemical_quality_specification',
        'Minimum guaranteed nitrogen fraction in DRY product; check actual label and water content'),
    'fertilizer_ammonium_nitrate_gost': Evidence('fertilizer_ammonium_nitrate_gost','ГОСТ 2-2013, селитра аммиачная марки Б: ≥34.4% N высший/первый сорт, 34.0% второй',
        'https://base.garant.ru/71100888/',2013,'EAEU','chemical_quality_specification',
        'Grade-specific minimum dry-matter fraction; check batch composition'),
    'ipcc_soils': Evidence('ipcc_soils','IPCC 2019 Refinement Vol 4, Ch 11, Table 11.1',
        'https://www.ipcc-nggip.iges.or.jp/public/2019rf/pdf/4_Volume4/19R_V4_Ch11_Soils_N2O_CO2.pdf',
        2019,'International','emission_method','EF1 0.01 general; dry climate 0.005 conditional'),
    'ipcc_livestock': Evidence('ipcc_livestock','IPCC 2019 Refinement Vol 4, Ch 10, Tables 10.10-10.11',
        'https://www.ipcc-nggip.iges.or.jp/public/2019rf/vol4.html',2019,'International','emission_method',
        'Choose species and representative productivity/system; do not count poultry enteric emissions'),
    'turkestan_cotton_cost_2025': Evidence('turkestan_cotton_cost_2025',
        'Казахстанская правда: полевые затраты на хлопок в Мактаарале, интервью фермера (2025)',
        'https://kazpravda.kz/n/sol-zemli-i-hlopok/',2025,'Maktaaral, Turkestan',
        'single_farm_quotation','450000 KZT/ha cited as approximate minimum total cost; not decomposed, not a verified regional average'),
    'ember_kazakhstan_2024': Evidence('ember_kazakhstan_2024',
        'Ember Yearly Electricity Data 2024, Kazakhstan generation intensity; 0.806 kg CO2/kWh (secondary display)',
        'https://ember-energy.org/data/yearly-electricity-data/',2024,'Kazakhstan',
        'open_energy_sector_statistics','Production-weighted national generation CO2 intensity, not a complete CO2e grid factor'),
    'ember_kazakhstan_2025': Evidence('ember_kazakhstan_2025',
        'Ember Yearly Electricity Data 2025, Kazakhstan generation intensity; 0.813 kg CO2/kWh (secondary display)',
        'https://ember-energy.org/data/yearly-electricity-data/',2025,'Kazakhstan',
        'open_energy_sector_statistics','Production-weighted national generation CO2 intensity, not farm meter or verified residual-mix Scope 2 factor'),
    'ales_2025': Evidence('ales_2025','АО АлЭС, экологические показатели 2025',
        'https://www.ales.kz/19-05-2026-prirodoohrannaya-deyatelnost-ao-ales-v-2025-godu/',
        2026,'Almaty','company_public_emissions',
        '0.972 tonnes CO2/MWh electricity generation in company report; NOT Kazakhstan grid factor'),
    'turkestan_fertilizer_subsidy': Evidence('turkestan_fertilizer_subsidy',
        'Акимат Туркестанской области № 68 от 11.03.2026, перечень субсидируемых удобрений',
        'https://adilet.zan.kz/rus/docs/G26U000068A',2026,'Turkestan Region','official_subsidy',
        'Subsidy per purchase unit is not a crop agronomic application rate and not a producer cost'),
    'andalusia_costs': Evidence('andalusia_costs','Junta de Andalucía, Observatorio de Precios y Mercados, crop budgets 2024/25',
        'https://www.juntadeandalucia.es/agriculturaypesca/observatorio/servlet/FrontController?action=List&ec=default&page=8&table=11210',
        2025,'Andalusia, Spain','foreign_technology_budget',
        'Physical task rates can inform scenarios after local adjustment, EUR budgets cannot become Turkestan KZT costs by simple FX'),
    'fao_budget_method': Evidence('fao_budget_method','FAO Farm Management, Enterprise Budgets §4.3',
        'https://www.fao.org/4/W7365E/w7365e07.htm',2000,'International','methodological',
        'State time period, variable vs fixed costs and planning vs observed basis'),
}

# Mass fractions are only the minimum from quality specifications; the
# actual batch label and moisture must be used for observed total nitrogen.
FERTILIZER_GOST_MIN_N_FRACTION = {'urea_dry_B':0.462, 'ammonium_nitrate_B_grade1_dry':0.344,
                                   'ammonium_nitrate_B_grade2_dry':0.340}
FERTILIZER_GOST_SOURCES = {'urea_dry_B':'fertilizer_urea_gost',
    'ammonium_nitrate_B_grade1_dry':'fertilizer_ammonium_nitrate_gost',
    'ammonium_nitrate_B_grade2_dry':'fertilizer_ammonium_nitrate_gost'}

# These are sourced methodological factors, not sources of unknown farm activity.
DIESEL_IPCC_KG_CO2_TJ = 74100.0
DIESEL_TYPICAL_NCV_MJ_KG = 43.0  # default fuel-energy reference; not farm batch observation
DIESEL_DENSITY_KG_L = 0.84  # within ГОСТ range, illustrative reference

def diesel_combustion_factor(*, density_kg_l=DIESEL_DENSITY_KG_L,
                             net_calorific_mj_kg=DIESEL_TYPICAL_NCV_MJ_KG,
                             emission_factor_kg_tj=DIESEL_IPCC_KG_CO2_TJ):
    """IPCC: litres × kg/L × MJ/kg × kg CO2/TJ / 10^6 MJ/TJ."""
    for val in (density_kg_l, net_calorific_mj_kg, emission_factor_kg_tj):
        if not isfinite(float(val)) or float(val) <= 0:
            raise ValueError('Fuel properties/factors must be positive and finite')
    return float(density_kg_l)*float(net_calorific_mj_kg)*float(emission_factor_kg_tj)/1e6

def validate_energy_sources(sources: Iterable[str]) -> tuple[str, ...]:
    if isinstance(sources, (str, bytes)):
        raise ValueError('Energy sources must be a collection of categories')
    values = tuple(dict.fromkeys(sources or ()))
    if not values:
        raise ValueError('Select at least one actual source of operational energy or labour')
    if any(v not in ENERGY_SOURCES for v in values):
        raise ValueError('Unknown energy-source category')
    return values

def reference_status_label(status: str, lang='ru') -> str:
    labels={
      'user_observed': {'ru':'Введено пользователем','kk':'Пайдаланушы енгізген','en':'User provided'},
      'direct': {'ru':'Официальная региональная норма (2025)','kk':'Өңірлік ресми норма (2025)','en':'Regional official norm (2025)'},
      'zone_fallback': {'ru':'Расчёт по соседней официальной зоне','kk':'Көршілес ресми аймақ бойынша есеп','en':'Adjacent official-zone estimate'},
      'regional_fallback': {'ru':'Справочный региональный сценарий','kk':'Өңірлік анықтамалық сценарий','en':'Regional reference scenario'},
      'international_reference': {'ru':'Международный справочный расчёт','kk':'Халықаралық анықтамалық есеп','en':'International reference estimate'},
      'unavailable': {'ru':'Нет обоснованных данных','kk':'Негізделген дерек жоқ','en':'No defensible estimate'},
    }
    return labels.get(status, labels['regional_fallback']).get(lang,labels['regional_fallback']['ru'])

def source_disclaimer(lang='ru') -> str:
    texts = {
     'ru':'Часть значений рассчитана по нормативным или методическим источникам. Это справочно-сценарные оценки, не измеренные показатели хозяйства; экономический результат зависит от фактической технологии, объёмов и тарифов.',
     'kk':'Кейбір көрсеткіштер нормативтік немесе әдістемелік дереккөздер бойынша есептелді. Олар шаруашылықтың өлшенген деректері емес, анықтамалық-сценарийлік бағалар; экономикалық нәтиже нақты технология, көлем мен тарифке тәуелді.',
     'en':'Some values are derived from normative or methodological references. They are reference-based scenario estimates, not farm measurements; financial results depend on actual technology, activity levels and tariffs.',
    }
    return texts.get(lang, texts['ru'])


def rice_regional_scenarios(method: str):
    """Documented regional demonstration, not broadly representative rice norm."""
    if method == 'drip': return 15000.0, SOURCES['rice_turkestan_2026']
    if method == 'furrow': return None, SOURCES['rice_turkestan_2026']
    if method == 'flooded': return 26000.0, SOURCES['rice_turkestan_2026']
    return None, SOURCES['rice_turkestan_2026']


# Factors do not justify guessing unknown farm consumption. Crop-input masses
# must be known before any nitrogen emissions can be calculated.
N2O_EF1_GENERAL = 0.01
N2O_EF1_DRY_CLIMATE = 0.005
N2O_MOLECULAR_RATIO = 44.0 / 28.0
N2O_GWP100_AR6 = 273.0
ENTERIC_CH4_ASIA_KG_HEAD_YEAR = {
    'Cattle': 54.0, 'Dairy cows': 78.0, 'Sheep': 5.0,
    'Goats': 5.0, 'Pigs': 1.0, 'Horses': 18.0, 'Camels': 46.0,
}

def fertilizer_nitrogen_kg(*, product_kg: float | None,
                           nitrogen_mass_fraction: float | None) -> float | None:
    """kg nutrient N, not kg fertilizer product. Unknown fraction stays unknown."""
    if product_kg is None or nitrogen_mass_fraction is None:
        return None
    amount, fraction = float(product_kg), float(nitrogen_mass_fraction)
    if not all(isfinite(v) for v in (amount, fraction)) or amount < 0 or not 0 <= fraction <= 1:
        raise ValueError('Fertilizer product kg and N mass fraction must be valid')
    return amount * fraction

def direct_fertilizer_n2o_co2e(*, nitrogen_kg: float | None, dry_climate: bool = False,
                               gwp100: float = N2O_GWP100_AR6) -> float | None:
    """Only direct soil N2O; excludes manufacturing, volatilization and leaching."""
    if nitrogen_kg is None:
        return None
    val = float(nitrogen_kg)
    if not isfinite(val) or val < 0 or not isfinite(gwp100) or gwp100 < 0:
        raise ValueError('Invalid nitrogen amount or N2O warming potential')
    ef = N2O_EF1_DRY_CLIMATE if dry_climate else N2O_EF1_GENERAL
    return val * ef * N2O_MOLECULAR_RATIO * gwp100

def enteric_tier1_ch4(*, species: str, heads: float | None,
                       fraction_of_year: float = 1.0) -> float | None:
    """Tentative Asian IPCC Tier 1 CH4, excluding manure and enteric from birds."""
    if heads is None:
        return None
    n = float(heads)
    if not isfinite(n) or n < 0 or not isfinite(fraction_of_year) or not 0 <= fraction_of_year <= 1:
        raise ValueError('Invalid herd activity or assessment period')
    if species in ('Poultry layers', 'Poultry broilers'):
        return 0.0  # physiological absence of appreciable enteric methane, not full livestock GHG
    ef = ENTERIC_CH4_ASIA_KG_HEAD_YEAR.get(species)
    return n * ef * fraction_of_year if ef is not None else None

# Updatable, non-regulatory CO2 intensity reference, sourced to Ember via
# public displays of the annual data. Not equivalent to a Kazakhstan government
# emissions compliance factor or a complete all-gases CO2e scope-2 inventory.
EMBer_KZ_GRID_GENERATION_CO2_KG_PER_KWH = {2024: 0.806, 2025: 0.813}

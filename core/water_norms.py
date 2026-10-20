"""Reference irrigation-water requirements for QŪNAR.

Historical source for the bundled coefficients: Order No. 108-NQ of 4 June 2025,
table 3. Order No. 288-NQ of 9 September 2026 took effect on 16 September 2026.
Do not label the 2025 numbers as values copied from Order 288-NQ unless a
2026 item-by-item mapping has been completed. This preserves historical
reproducibility and prevents inaccurate legal citations.

The application default is deliberately conservative and transparent:
- surface irrigation;
- automorphic soils (groundwater > 3 m);
- 50% exceedance probability (normal/reference year);
- district-specific water-management/agroclimatic zone where the order names it.

For districts created from/embedded in an explicitly named official zone, QŪNAR
uses a documented geographic fallback. For Suzak and crop categories not directly
specified by the order, it falls back to the regional irrigation benchmark
8,181.6 m3/ha and marks the value as a fallback rather than an observed fact.
"""
from __future__ import annotations

from dataclasses import dataclass

REGIONAL_BENCHMARK_M3_HA = 8181.6
PUMPING_REFERENCE_KWH_PER_M3 = 0.70509  # ARCHIVAL opt-in scenario ONLY; not automatic or official reference
SOURCE_URL = "https://adilet.zan.kz/rus/docs/V2500036253"
SOURCE_LABEL = "МВРИ РК, приказ №108-НҚ от 04.06.2025, табл. 3 (историческая справочная база; для 2026 г. требуется сверка с №288-НҚ)"

# Values are the first numeric column for each row: surface irrigation,
# automorphic soils, probability 50%.
# Crop names follow the official table; QŪNAR crop codes are mapped below.
ZONE_VALUES = {
    # WH sites 01.00.01.01 + 01.00.01.04: Maktaaral, Zhetysay, Arys, Otyrar, Shardara
    "south_desert_dry": {
        "spring_grains": 4600, "winter_wheat": 4100, "corn": 7450,
        "cotton": 8400, "potato": 7600, "vegetables": 9100,
        "melons": 5650, "vineyards": 6600, "orchards": 9350,
        "forage": 11000, "rapeseed": 4200, "safflower": 4600,
    },
    # WH 01.00.01.02: Saryagash, Kazygurt
    "saryagash_kazygurt": {
        "spring_grains": 3350, "winter_wheat": 2950, "corn": 5350,
        "cotton": 5500, "potato": 5350, "vegetables": 6400,
        # not all rows were directly returned in the official excerpt used for build;
        # values absent here intentionally trigger the transparent fallback.
        "rapeseed": 2150, "safflower": 2550,
    },
    # WH 01.00.01.02: Turkestan water-management site
    "turkestan": {
        "spring_grains": 4050, "winter_wheat": 3550, "corn": 6450,
        "cotton": 6700, "potato": 6450,
        "vineyards": 4300, "orchards": 6450, "forage": 7200,
        "rapeseed": 2450, "safflower": 2900,
    },
    # WH 01.00.01.03: Ordabasy, Sairam, Baidibek
    "ordabasy_sairam_baidibek": {
        "spring_grains": 3700, "winter_wheat": 3100, "corn": 5600,
        "cotton": 5350, "potato": 5850, "vegetables": 6900,
        "melons": 4150, "vineyards": 4700, "orchards": 7200,
        "forage": 8200, "rapeseed": 3150, "safflower": 3600,
    },
    # WH 01.00.01.03: Tulkibas, Tolebi, foothill semi-desert (full district profile)
    "tolebi_tulkibas": {
        "spring_grains": 3250, "winter_wheat": 2600, "corn": 5250,
        "cotton": 4750, "potato": 5050, "vegetables": 6050,
        "melons": 3550, "forage": 7450,
        "rapeseed": 3850, "safflower": 4250,
    },
}

DISTRICT_ZONE = {
    "Maktaaral District": ("south_desert_dry", "direct"),
    "Zhetysay District": ("south_desert_dry", "direct"),
    "Arys City": ("south_desert_dry", "direct"),
    "Otyrar District": ("south_desert_dry", "direct"),
    "Shardara District": ("south_desert_dry", "direct"),
    "Saryagash District": ("saryagash_kazygurt", "direct"),
    "Kazygurt District": ("saryagash_kazygurt", "direct"),
    "Ordabasy District": ("ordabasy_sairam_baidibek", "direct"),
    "Sairam District": ("ordabasy_sairam_baidibek", "direct"),
    "Baydibek District": ("ordabasy_sairam_baidibek", "direct"),
    "Tolebi District": ("tolebi_tulkibas", "direct"),
    "Tulkibas District": ("tolebi_tulkibas", "direct"),
    # Administrative/geographic fallbacks. They are deliberately labelled as such.
    "Keles District": ("saryagash_kazygurt", "zone_fallback"),
    "Turkestan City": ("turkestan", "direct"),
    "Sauran District": ("turkestan", "zone_fallback"),
    "Kentau City": ("turkestan", "zone_fallback"),
    "Suzak District": (None, "regional_fallback"),
}

CROP_TO_NORM = {
    "Wheat": "winter_wheat",
    "Barley": "spring_grains",
    "Corn": "corn",
    "Cotton": "cotton",
    "Potato": "potato",
    "Cabbage": "vegetables",
    "Cucumbers": "vegetables",
    "Tomatoes": "vegetables",
    "Carrots": "vegetables",
    "Onion": "vegetables",
    "Melons": "melons",
    "PomeStone": "orchards",
    "FreshGrapes": "vineyards",
    "OtherFruits": "orchards",
    "Forage": "forage",
    # Official order has rapeseed/safflower, not sunflower/other oilseeds as a single row.
    # Use mean of those two official oilseed norms as a modelled category proxy.
    "Sunflower": "oilseed_proxy",
    "OtherOilseeds": "oilseed_proxy",
    # Rice is not represented by a directly comparable row in the Turkestan excerpts used here.
    "Rice": None,
}

# CLREM product -> crop code, used when optimizing/ranking scenario rows.
PRODUCT_TO_CODE = {
    "Пшеница": "Wheat",
    "Ячмень": "Barley",
    "Кукуруза (маис)": "Corn",
    "Хлопок, очищенный или не очищенный от семян": "Cotton",
    "Семена подсолнечника": "Sunflower",
    "Картофель": "Potato",
    "Капуста": "Cabbage",
    "Культуры бахчевые": "Melons",
    "Огурцы и корнишоны": "Cucumbers",
    "Помидоры": "Tomatoes",
    "Морковь и турнепс": "Carrots",
    "Лук": "Onion",
    "Плоды семечковые и косточковые": "PomeStone",
    "Семена масличные прочие, не включенные в другие группировки": "OtherOilseeds",
    "Культуры кормовые": "Forage",
    "Виноград свежий": "FreshGrapes",
    "Ягоды и плоды прочие": "OtherFruits",
}

@dataclass(frozen=True)
class WaterDefault:
    m3_ha: float
    source_tier: str
    source_label: str
    zone: str | None
    norm_crop: str | None
    reliability_0_100: float


def _irrigation_factor(irrigation_type: str | None) -> float:
    # The official table contains separate drip values. For the generic UI categories,
    # use the surface value for unknown/furrow/mixed and a transparent efficiency
    # scenario for sprinkler/drip. These factors do not claim to be field observations.
    return {
        "unknown": 1.0,
        "furrow": 1.0,
        "mixed": 0.90,
        "sprinkler": 0.85,
        "drip": 0.80,
    }.get(str(irrigation_type or "unknown"), 1.0)


def default_water_requirement(district: str, crop_code: str | None, irrigation_type: str = "unknown") -> WaterDefault:
    zone, tier = DISTRICT_ZONE.get(district, (None, "regional_fallback"))
    norm_crop = CROP_TO_NORM.get(crop_code)
    base = None
    proxy = False
    if zone and norm_crop:
        z = ZONE_VALUES.get(zone, {})
        if norm_crop == "oilseed_proxy":
            vals = [z.get("rapeseed"), z.get("safflower")]
            vals = [v for v in vals if v is not None]
            if vals:
                base = sum(vals) / len(vals)
                proxy = True
        else:
            base = z.get(norm_crop)
    if base is None:
        base = REGIONAL_BENCHMARK_M3_HA
        tier = "regional_fallback"

    factor = _irrigation_factor(irrigation_type)
    val = float(base) * factor
    if tier == "direct" and not proxy and factor == 1.0:
        reliability = 95.0
        label = SOURCE_LABEL
    elif tier == "direct" and not proxy:
        reliability = 85.0
        label = SOURCE_LABEL + "; технологический сценарий по типу орошения"
    elif tier == "zone_fallback" and not proxy:
        reliability = 80.0
        label = SOURCE_LABEL + "; географический fallback к официальной зоне"
    elif proxy:
        reliability = 70.0
        label = SOURCE_LABEL + "; прокси масличных = среднее рапса и сафлора"
    else:
        reliability = 55.0
        label = "Региональный калибровочный benchmark 8 181,6 м³/га"
    return WaterDefault(val, tier, label, zone, norm_crop, reliability)


def default_pumping_energy_kwh(water_m3: float) -> None:
    """No universal pump kWh/m³: determine the energy from pump head and efficiency."""
    return None

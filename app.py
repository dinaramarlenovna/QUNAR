
from datetime import date, datetime, timedelta
from pathlib import Path
import uuid
import time
import html
import json
import hashlib
import inspect
import smtplib
import ssl
import requests
from email.message import EmailMessage
from urllib.parse import quote
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from core.config import (
    APP_NAME, APP_SUBTITLE, LANGUAGES, DISTRICT_ORDER, CROPS, TEXT, DATA_DIR,
    DISTRICT_LABELS, CROP_LABELS,
)
from core.data import load_centroids, district_climate, district_crop_context
from core.nasa import fetch_growing_season
# DEPLOY_COMPAT_v0.8.1_2026-10-18: forward-validation import works with older ml.py files.
from core.ml import predict_yield, rank_crops, validation_summary, validation_for_crop, spatial_validation_summary, prediction_interval_for_crop
try:
    from core.ml import forward_holdout_for_crop
except ImportError as _forward_import_error:
    if "forward_holdout_for_crop" not in str(_forward_import_error):
        raise

    def forward_holdout_for_crop(crop):
        """Read the same validated forward-test file if deployed core/ml.py predates this function.

        Compatibility only: no model retraining and no fabricated forecast metrics.
        """
        from math import isfinite as _isfinite
        _path = DATA_DIR / "forecast_holdout_2021_2025_metrics.csv"
        if not _path.exists():
            return None
        _df = pd.read_csv(_path)
        _rows = _df[_df["crop"].astype(str).eq(str(crop))]
        if _rows.empty:
            return None
        _r = _rows.iloc[0]
        _metric = {"mae": float(_r["MAE"]), "rmse": float(_r["RMSE"]),
                   "r2": float(_r["R2"]), "n": int(_r["n"]),
                   "train_end": int(_r["train_end"]),
                   "test_start": int(_r["test_start"]),
                   "test_end": int(_r["test_end"]),
                   "source": "forward-time test, NOT current farm validation"}
        if (_metric["n"] <= 0 or _metric["train_end"] >= _metric["test_start"]
                or not all(_isfinite(_metric[k]) for k in ("mae", "rmse", "r2"))):
            raise ValueError("Invalid forward holdout metrics")
        return _metric

from core.resources import calculate_resources
from core.reference_fallbacks import (optional_observation, irrigation_water_fallback,
                                      livestock_drinking_fallback, conditional_pumping_energy)
from core.regional_tariffs import REGIONAL_TARIFF_REFERENCES, supplier_tariff
from core.historical_crop_costs import historic_cost_mix, SOURCE_URL as HISTORIC_SOUTH_CROP_COST_SOURCE
from core.evidence_registry import (ENERGY_SOURCES, SOURCE_LABELS,
    validate_energy_sources, source_disclaimer, SOURCES, diesel_combustion_factor,
    ENTERIC_CH4_ASIA_KG_HEAD_YEAR, N2O_EF1_GENERAL, N2O_EF1_DRY_CLIMATE,
    EMBer_KZ_GRID_GENERATION_CO2_KG_PER_KWH,
    FERTILIZER_GOST_MIN_N_FRACTION, FERTILIZER_GOST_SOURCES,
    fertilizer_nitrogen_kg)
from core.water_norms import default_water_requirement
from core.economics import DEFAULT_EF_KZ_KGCO2_PER_KWH, DEFAULT_ELECTRICITY_TARIFF_KZT_KWH, DEFAULT_IRRIGATION_WATER_TARIFF_KZT_M3, DEFAULT_GREEN_SHARE_TARGET, DEFAULT_WATER_SAVING_TARGET, economic_climate_effect, payback_years
from core.economic_feasibility import economic_feasibility
from core.yield_reference import trailing_three_year_yield
from core.producer_prices import reference_producer_price
from core.production_costs import (reference_variable_cost, itemized_variable_cost, COST_FIELDS)
from core.agronomic_references import crop_references, suggest_diesel_l_per_ha, evidence_note
from core.cmip6_scenarios import load_scenario
from core.nasa_polygon import fetch_polygon_growing_season, fetch_polygon_daily_weather
from core.field_climate import fetch_farm_climate_normal
from core.soilgrids_reference import fetch_soilgrids_reference, indicative_texture_from_soilgrids, DOCS as SOILGRIDS_DOCS
from core.water_climate import temperature_only_water_sensitivity
from core.fao56_irrigation import (fetch_nasa_monthly_climatology, fetch_polygon_monthly_climatology,
                                  parse_kc_monthly, evaluate_irrigation_scenario, FAO_56_URL)
from core.irrigation_evidence import (
    FIELD_EFFICIENCIES, CROP_KC_STAGES, FAO_EFFICIENCY_URL, FAO_CROP_KC_URL,
    field_efficiency, mixed_efficiency, irrigation_saving,
    parse_stage_lengths, monthly_kc_from_calendar,
)
from core.carbon_scenarios import partial_inventory, compare_partial_inventory, DEFAULT_DIESEL_CO2_KG_L
from core.water_accounting import irrigation_water_balance, compare_irrigation_balances
from core.scenario_ui import render_integrated_scenario
from core.structure_water_scenarios import compare_structure_water
from core.soil_water_daily import (
    SOIL_PRESETS, CROP_ROOT_P, FAO_DAILY_SOURCE, FAO_SOIL_PROFILE_SOURCE,
    fetch_nasa_daily, daily_soil_balance,
)
from core.ghg_structure import compare_crop_structures
from core.forecast_reliability import evaluate_forecast_support
from core.forecast_quality import forward_yield_evidence, norm_vs_fao_comparison
from core.yield_method_selection import route_yield, all_method_history, method_label, method_caveat
from core.irrigation_economics import irrigation_comparison
from core.irrigation_report import irrigation_export
from core.uncertainty import support_score
from core.analysis_engine import build_analysis, build_recommendations
from core.wapor import seasonal_aeti, consumptive_water_metrics, WaPORError
from core.admin_boundaries import detect_point, detect_polygon, boundary_geojson
from core.optimizer import optimize_structure
from core.optimization_guard import validate_allocation
from core.clrem import check_crop_codes, label as _original_crop_label, method as crop_method, scenario_for_crop, scenario_for_district, observed_for_crop, observed_extra_for_district, decision_table, registry as clrem_registry
from core.reporting import build_excel_report, build_pdf_report, build_word_report, build_combined_excel_report, build_combined_pdf_report, build_combined_word_report
from core.report_variants import (report_fingerprint, normalize_report_library, add_report, selected_reports, compared_variants)
from core.environment import environmental_diagnostics, diversification_metrics
from core.livestock import (
    SPECIES, SPECIES_LABELS, PRODUCT_TYPES, PRODUCT_LABELS, DEFAULT_PRODUCT,
    livestock_resource_metrics, district_livestock_profile, district_species_history,
    district_species_benchmark, regional_productivity_benchmarks,
)


def extended_crop_label(code, lang='ru'):
    """Resolve both crop codes and internal product IDs in the selected language."""
    key = str(code)
    reg = clrem_registry()
    col = {'kk': 'KK', 'ru': 'RU', 'en': 'EN'}[lang]
    matches = reg[reg['Code'].astype(str).eq(key) | reg['CLREM_product'].astype(str).eq(key)]
    if not matches.empty:
        value = matches.iloc[0][col]
        if pd.notna(value) and str(value).strip():
            return str(value)
    return {'kk': 'Атауы қолжетімсіз', 'ru': 'Название недоступно', 'en': 'Name unavailable'}[lang]


def localized_solver_status(status, lang):
    labels = {
        'infeasible_under_hard_constraints': ('Қатаң шектеулерге сәйкес шешім жоқ', 'Нет решения при заданных жестких ограничениях', 'No feasible allocation under the hard constraints'),
        'infeasible_crop_count_or_cap': ('Дақыл саны немесе үлес шегі орындалмайды', 'Невыполнимые ограничения числа или доли культур', 'Infeasible crop-count or crop-share constraints'),
        'unknown': ('Белгісіз', 'Неизвестно', 'Unknown'),
    }
    return labels.get(str(status), labels['unknown'])[{'kk': 0, 'ru': 1, 'en': 2}[lang]]


GA_MEASUREMENT_ID = "G-B2WV23W45Y"
GA_PAGE_LOCATION = "https://qunar-turkestan.streamlit.app"
PUBLIC_VERSION = "v0.8.1"


@st.cache_data(ttl=2592000, show_spinner=False)
def _cached_fao56_historical_power(latitude, longitude):
    """Immutable reference climatology with 30-day caching for the public NASA API."""
    return fetch_nasa_monthly_climatology(latitude, longitude, start_year=1995, end_year=2014)


@st.cache_data(ttl=2592000, show_spinner=False)
def _cached_farm_climate_normal(latitude, longitude, geometry=None):
    """NASA location-aware 1995–2025 historical normal, not district centroid."""
    return fetch_farm_climate_normal(latitude, longitude, geometry=geometry)


@st.cache_data(ttl=2592000, show_spinner=False)
def _cached_polygon_daily_weather(geometry_json, first, last):
    import json as _json
    return fetch_polygon_daily_weather(_json.loads(geometry_json),start=first,end=last,
        fetch_point=lambda lat,lon,first,last:_cached_daily_soil_nasa(lat,lon,first,last))


@st.cache_data(ttl=86400, show_spinner=False)
def _cached_soilgrids_reference(latitude, longitude):
    return fetch_soilgrids_reference(latitude, longitude)


@st.cache_data(ttl=2592000, show_spinner=False)
def _cached_daily_soil_nasa(latitude, longitude, first, last):
    """Historical daily meteorology; cache avoids redundant NASA POWER calls."""
    return fetch_nasa_daily(latitude, longitude, start=first, end=last)


def _ga_client_id():
    # Stable for the current Streamlit session and suitable for GA4 Measurement Protocol.
    return st.session_state.setdefault("ga_client_id", f"{int(uuid.uuid4().int % 10**10)}.{int(time.time())}")


def _secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


def ga_event(event_name: str, **params):
    """Send GA4 events. Prefer official Measurement Protocol when its API secret is configured."""
    payload = {k: v for k, v in params.items() if v is not None}
    payload.setdefault("page_location", GA_PAGE_LOCATION)
    payload.setdefault("page_title", "QŪNAR")
    payload.setdefault("app_version", PUBLIC_VERSION)

    api_secret = _secret("GA4_API_SECRET")
    if api_secret:
        try:
            import requests
            requests.post(
                f"https://www.google-analytics.com/mp/collect?measurement_id={GA_MEASUREMENT_ID}&api_secret={api_secret}",
                json={
                    "client_id": _ga_client_id(),
                    "events": [{"name": str(event_name), "params": payload}],
                },
                timeout=4,
            )
            return
        except Exception:
            pass

    # Browser fallback. This works even though Streamlit cannot place scripts in the top-level <head>.
    js_payload = json.dumps(payload, ensure_ascii=False, default=str)
    event = json.dumps(str(event_name))
    cid = json.dumps(_ga_client_id())
    html_block = f"""
    <script>
      (() => {{
        const p = new URLSearchParams({{
          v: '2',
          tid: '{GA_MEASUREMENT_ID}',
          cid: {cid},
          en: {event},
          dl: '{GA_PAGE_LOCATION}',
          dt: 'QŪNAR',
          ul: navigator.language || 'en'
        }});
        const extra = {js_payload};
        for (const [k,v] of Object.entries(extra)) {{
          if (v !== null && v !== undefined) p.set('ep.' + k, String(v));
        }}
        fetch('https://www.google-analytics.com/g/collect?' + p.toString(), {{
          method: 'POST', mode: 'no-cors', keepalive: true
        }}).catch(() => {{}});
      }})();
    </script>
    """
    components.html(html_block, height=1, width=1)


def _send_bug_report(description: str, contact: str = "", error_text: str = "", screenshot=None):
    """Email a bug report when SMTP secrets are configured; otherwise return False."""
    try:
        mail_cfg = st.secrets.get("email", {})
    except Exception:
        mail_cfg = {}
    host = mail_cfg.get("smtp_host")
    port = int(mail_cfg.get("smtp_port", 465) or 465)
    user = mail_cfg.get("smtp_user")
    password = mail_cfg.get("smtp_password")
    recipient = mail_cfg.get("recipient") or user
    if not all([host, user, password, recipient]):
        return False, recipient

    msg = EmailMessage()
    msg["Subject"] = f"QŪNAR {PUBLIC_VERSION} - bug report"
    msg["From"] = user
    msg["To"] = recipient
    if contact:
        msg["Reply-To"] = contact
    body = (
        f"Version: {PUBLIC_VERSION}\n"
        f"Time UTC: {datetime.utcnow().isoformat(timespec='seconds')}Z\n"
        f"Page: {GA_PAGE_LOCATION}\n\n"
        f"Description:\n{description.strip()}\n\n"
        f"Error text / copied message:\n{error_text.strip() or '(not provided)'}\n"
    )
    msg.set_content(body)
    if screenshot is not None:
        data = screenshot.getvalue()
        ctype = screenshot.type or "image/png"
        maintype, subtype = (ctype.split("/", 1) + ["png"])[:2]
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=screenshot.name or "screenshot.png")
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=context, timeout=10) as server:
        server.login(user, password)
        server.send_message(msg)
    return True, recipient


def _default_widget_help(label):
    text = str(label or "").lower()
    lang_hint = globals().get("lang", "ru")
    # Field-specific everyday explanations precede the broad keyword fallbacks.
    detailed = [
        (("тариф воды", "water tariff", "су тарифі"),
         "Сколько хозяйство платит за подачу 1 м³ воды. Выберите поставщика: самотечная и механизированная подача оплачиваются по-разному. Если известен договорной тариф, внесите его; не включайте стоимость перекачки дважды.",
         "1 м³ су жеткізу үшін төлем. Жеткізушіні және су беру түрін таңдаңыз. Нақты шарттағы баға белгілі болса, оны енгізіңіз; сорғы ақысын екі рет қоспаңыз.",
         "Cost to deliver one cubic metre of water. Choose your provider and delivery type. Use your actual contract rate if available, and do not charge pumping twice."),
        (("тариф электроэнерг", "electricity tariff", "электр тариф"),
         "Сколько платите за 1 кВт·ч электроэнергии. Лучше взять цену из счёта поставщика; справочный тариф может не совпадать с вашим договором.",
         "1 кВт·сағ электр энергиясының бағасы. Мүмкін болса, келісімшарттағы тарифті көрсетіңіз; анықтамалық баға шарттағы бағамен бірдей болмауы мүмкін.",
         "Price of 1 kWh of electricity. Prefer your electricity bill; reference prices may differ from your contract."),
        (("энергоэффектив", "efficient pump", "тиімді сорғы"),
         "Есть ли оборудование, которое потребляет меньше энергии при той же работе? Это не означает, что известен фактический расход электричества.",
         "Бірдей жұмыс үшін энергияны аз пайдаланатын жабдық бар ма? Бұл нақты тұтыну белгілі дегенді білдірмейді.",
         "Does your equipment use less energy for the same work? This does not establish actual kWh consumption."),
        (("суммарный напор", "total dynamic pumping head", "жиынтық тегеурін"),
         "На какую высоту и с каким сопротивлением насос подаёт воду, в метрах. Возьмите из паспорта насоса или расчёта инженера. Если неизвестно, не придумывайте число.",
         "Сорғы суды қандай биіктікке және кедергімен жеткізеді, метрмен. Паспорттан немесе инженер есебінен алыңыз; белгісіз болса, ойдан енгізбеңіз.",
         "Total pumping head in metres, including friction losses. Use pump specifications or an engineer's estimate; do not invent a value."),
        (("суммарный кпд", "combined pump", "жалпы пәк"),
         "Какую долю затраченной энергии насос и двигатель превращают в полезную работу. Например, 65% вводят как 65. Если неизвестно, расчёт насосной энергии нельзя считать подтверждённым.",
         "Сорғы мен қозғалтқыш энергиясының пайдалы үлесі. Мысалы, 65% үшін 65 енгізіңіз. Белгісіз болса, энергия есебі расталмаған болып қалады.",
         "Combined pump and motor efficiency as a percentage: enter 65 for 65%. If unknown, pump energy cannot be verified."),
        (("сезонов в год", "seasons per year", "жылына маусым"),
         "Сколько раз в год выращивается культура на том же участке. Для одного урожая введите 1. Показатель влияет на годовые расходы, а не на площадь поля.",
         "Бір алқаптан бір жылда неше рет өнім алынады? Бір өнім болса, 1 енгізіңіз. Бұл жылдық шығынға әсер етеді.",
         "Number of production seasons on the same land each year. Enter 1 for one harvest; used for annual costs, not field area."),
        (("снижение потребности", "water saving target", "су үнемдеу"),
         "На сколько процентов предполагается уменьшить потребность в воде в отдельном сценарии. Например, 20 означает 20%. Это гипотеза, а не уже достигнутая экономия.",
         "Сценарий бойынша су қажеттілігі қанша пайызға азаяды? 20 дегеніміз - 20%. Бұл расталған үнем емес, болжам.",
         "Hypothetical percentage reduction in water use. Enter 20 for 20%. This is a scenario, not measured savings."),
        (("доля электроэнергии", "solar share", "күн энергиясы үлесі"),
         "Какая часть электричества поступает от солнечных или других возобновляемых источников. Например, 30 означает 30%. Выбирайте фактическую или явно сценарную долю.",
         "Электрдің қанша бөлігі күн не өзге жаңартылатын көздерден келеді? 30 дегеніміз 30%. Нақты немесе сценарийлік үлесті белгілеңіз.",
         "Share of electricity from solar or other renewables. Enter 30 for 30%. Distinguish actual and proposed shares."),
        (("расчётный год", "calculation year", "есептік жыл"),
         "Год, для которого оцениваете хозяйство. Прошедший сезон - ретроспективная оценка, будущий - сценарный прогноз.",
         "Шаруашылық бағаланатын жыл. Өткен маусым - тарихи бағалау, болашақ маусым - сценарийлік есеп.",
         "Year being assessed. Past seasons are retrospective; future seasons are scenarios."),
        (("поголов", "headcount", "мал саны"),
         "Сколько голов животных действительно содержится в вашем хозяйстве. Не вводите поголовье всего района вместо своего.",
         "Өз шаруашылығыңыздағы нақты мал басы. Ауданның жалпы мал санын өз шаруашылығыңыздікі деп енгізбеңіз.",
         "Actual number of animals kept by the farm, not the district total."),
        (("урожайност", "yield", "өнімділік"),
         "Сколько урожая получаете с одного гектара (центнеров на гектар). Если не знаете, программа использует отдельно подписанную районную справочную урожайность.",
         "Бір гектардан алынатын өнім мөлшері (ц/га). Белгісіз болса, аудандық анықтамалық мән бөлек көрсетіледі.",
         "Harvest per hectare, in centners/ha. If unknown, the tool may use an explicitly labelled district reference."),
        (("стоимость инвестиц", "инвест", "investment", "инвестици"),
         "Единовременные затраты на новое оборудование, если хотите оценить окупаемость. При отсутствии проекта не нужно подставлять произвольную сумму.",
         "Жаңа жабдықтың біржолғы құны. Жоба жоқ болса, ойдан сома енгізбеңіз.",
         "One-time cost of new equipment, for optional payback calculations. Do not invent a cost if there is no project."),
    ]
    for keys, ru, kk, en in detailed:
        if any(k in text for k in keys):
            return {"ru": ru, "kk": kk, "en": en}[lang_hint]
    rules = [
        (("коэффициент эмиссии", "emission factor", "эмисси"), "Показывает, сколько кг CO₂e связано с потреблением 1 кВт·ч электроэнергии. Используется для оценки углеродной нагрузки.", "Amount of CO₂e associated with 1 kWh of electricity; used to estimate operational carbon load."),
        (("площад", "area", "алаң"), "Площадь участка или производственной территории, для которой выполняется расчёт.", "Area of the field or production unit used in the calculation."),
        (("доступн", "available water"), "Общий объём воды, доступный для рассматриваемого производственного сезона. В режиме оптимизации это общий водный бюджет хозяйства: QŪNAR распределяет его между культурами автоматически, поэтому пользователю не нужно заранее делить воду по культурам.", "Total water available for the production season under assessment. In optimization mode this is the farm-level seasonal water budget; QŪNAR allocates it among crops automatically, so the user does not need to pre-allocate water crop by crop."),
        (("расход воды", "water use", "water used"), "Для растениеводства укажите суммарное фактическое или ожидаемое водопотребление за полный производственный цикл выбранной культуры - от предпосевной подготовки/посева до уборки урожая. Если значение неизвестно, оставьте 0: QŪNAR использует отдельную нормативную оценку и явно помечает её как расчётную.", "For crops, enter total observed or expected water use for the full production cycle - from pre-sowing preparation/sowing through harvest. If unknown, leave 0: QŪNAR uses a separate reference estimate and labels it as modelled rather than observed."),
        (("энерг", "electric"), "Для растениеводства укажите суммарное энергопотребление, непосредственно связанное с выбранной культурой за полный производственный цикл - подготовка почвы, посев, орошение/перекачка, уход и уборка, если эти операции потребляют энергию. Если значение неизвестно, оставьте 0.", "For crops, enter total energy directly attributable to the selected crop over the full production cycle - soil preparation, sowing, irrigation/pumping, crop care and harvest where energy is used. Leave 0 if unknown."),
        (("тариф", "tariff"), "Цена единицы ресурса, используемая для расчёта затрат и потенциальной экономии.", "Price per unit of resource used to estimate cost and potential savings."),
        (("виэ", "renewable", "green share"), "Доля электроэнергии из возобновляемых источников в рассматриваемом сценарии.", "Share of electricity supplied by renewable sources in the scenario."),
        (("повтор", "reuse"), "Доля воды, повторно использованной в рассматриваемом производственном цикле. Она уменьшает потребность в новом водозаборе; если фактическая доля неизвестна, оставьте 0 и не трактуйте это как подтверждённое отсутствие повторного использования.", "Share of water reused within the production cycle under assessment. It reduces the need for additional withdrawal; if the observed share is unknown, leave 0 and do not interpret this as verified absence of reuse."),
        (("инвест", "investment"), "Дополнительные инвестиционные затраты для оценки срока окупаемости ресурсосберегающего решения.", "Additional investment used to estimate the payback period of a resource-saving option."),
        (("пестиц", "pesticide"), "Фактическая нагрузка пестицидами. Если данных нет, показатель остаётся неизвестным и не заменяется нулём.", "Observed pesticide load. Missing values remain unknown rather than being treated as zero."),
        (("солен", "salinity"), "Показатель засоления почвы, если он известен пользователю или подтверждён наблюдениями.", "Soil salinity indicator when observed or supplied by the user."),
        (("деград", "degrad"), "Доля деградированной территории/пастбища, если она известна. Используется как экологический диагностический фактор.", "Observed degraded land/pasture share used as an environmental diagnostic."),
        (("максимальн", "maximum share"), "Ограничивает долю одной культуры в оптимизированной структуре, снижая чрезмерную концентрацию.", "Caps the share of any one crop in the optimized structure to limit excessive concentration."),
        (("количество культур", "number of crops"), "Число культур, между которыми оптимизатор распределяет доступную площадь.", "Number of crops among which the optimizer allocates the available area."),
    ]
    kk_help = [
        '1 кВт·сағ электр энергиясына сәйкес келетін CO₂e мөлшері. Операциялық көміртек жүктемесін есептеуге қолданылады.',
        'Есеп жүргізілетін алқаптың немесе өндірістік аумақтың ауданы.',
        'Бағаланатын өндірістік маусымға қолжетімді судың жалпы көлемі. Оңтайландыру кезінде модель осы су бюджетін дақылдар арасында бөледі.',
        'Дақылдың толық өндірістік циклі бойынша нақты немесе күтілетін су тұтынуы. Белгісіз болса, 0 қалдырыңыз: нормативтік қажеттілік бөлек есептеледі.',
        'Дақылдың толық өндірістік цикліне жұмсалатын энергия: топырақ дайындау, себу, суару, күтім және жинау. Белгісіз болса, 0 қалдырыңыз.',
        'Шығындар мен ықтимал үнемді есептеуге арналған ресурс бірлігінің бағасы.',
        'Сценарийдегі жаңартылатын көздерден алынатын электр энергиясының үлесі.',
        'Өндірістік циклде қайта пайдаланылатын судың үлесі. Белгісіз 0 мәні қайта пайдаланудың нақты жоқтығын растамайды.',
        'Ресурс үнемдейтін шешімнің өтелу мерзімін бағалауға арналған қосымша инвестиция.',
        'Пестицидтердің нақты жүктемесі. Белгісіз дерек нөлмен алмастырылмайды.',
        'Нақты бақылаумен немесе пайдаланушы дерегімен расталған топырақтың тұздану көрсеткіші.',
        'Тозған жер немесе жайылым үлесі. Экологиялық диагностикада қолданылады.',
        'Бір дақылдың оңтайландырылған құрылымдағы ең жоғары үлесін шектейді.',
        'Қолжетімді аудан бөлінетін дақылдар саны.',
    ]
    for i, (keys, ru, en) in enumerate(rules):
        if any(k in text for k in keys):
            return {"ru": ru, "kk": kk_help[i], "en": en}[lang_hint]
    return {"kk": "Шаруашылыққа немесе сценарийге сәйкес мәнді таңдаңыз немесе енгізіңіз.", "ru": "Выберите или введите значение, соответствующее хозяйству или сценарию.", "en": "Choose or enter the value that best matches the farm or scenario."}[lang_hint]


def q_number_input(label, *args, **kwargs):
    kwargs.setdefault("help", _default_widget_help(label))
    # General format hides .00 while preserving large amounts and decimal entry.
    if isinstance(kwargs.get("value", 0.0), float):
        kwargs.setdefault("format", "%.12g")
        suffix = {"ru":"Если нужно дробное число, вводите его через точку (например, 2.5).",
                  "kk":"Бөлшек санды нүктемен енгізіңіз (мысалы, 2.5).",
                  "en":"Enter a decimal using a dot (for example, 2.5)."}.get(
                      st.session_state.get("qunar_preferred_lang", "ru"), "Enter decimals with a dot.")
        kwargs["help"] = (str(kwargs.get("help") or "").strip() + " " + suffix).strip()
    return st.number_input(label, *args, **kwargs)
def q_selectbox(label, *args, **kwargs):
    kwargs.setdefault("help", _default_widget_help(label)); return st.selectbox(label, *args, **kwargs)
def q_radio(label, *args, **kwargs):
    kwargs.setdefault("help", _default_widget_help(label)); return st.radio(label, *args, **kwargs)
def q_toggle(label, *args, **kwargs):
    kwargs.setdefault("help", _default_widget_help(label)); return st.toggle(label, *args, **kwargs)

# Preserve widget inputs before Streamlit prunes controls hidden by mode changes.
# The backing dictionary is not a widget key and survives reruns/navigation.
def _install_persistent_input_widgets():
    import copy
    import functools

    if getattr(st, '_qunar_persistence_installed', False):
        return
    store_key = 'qunar_persistent_input_values_v2'
    supported = ('number_input', 'text_input', 'text_area', 'selectbox',
                 'radio', 'multiselect', 'checkbox', 'toggle', 'slider',
                 'date_input', 'time_input')

    def make_persistent(original, method):
        @functools.wraps(original)
        def wrapped(*args, **kwargs):
            key = kwargs.get('key')
            if not isinstance(key, str) or not key:
                return original(*args, **kwargs)
            stored = st.session_state.setdefault(store_key, {})
            # Never restore button state or output-only widget states.
            if key not in st.session_state and key in stored:
                candidate = copy.deepcopy(stored[key])
                options = kwargs.get('options')
                if options is None and method in ('selectbox', 'radio', 'multiselect'):
                    options = args[1] if len(args) > 1 else None
                if method in ('selectbox', 'radio') and options is not None:
                    try:
                        valid = candidate in options
                    except (TypeError, ValueError):
                        valid = False
                elif method == 'multiselect' and options is not None:
                    try:
                        valid = all(item in options for item in candidate)
                    except (TypeError, ValueError):
                        valid = False
                elif method in ('number_input', 'slider'):
                    lo = kwargs.get('min_value', kwargs.get('min'))
                    hi = kwargs.get('max_value', kwargs.get('max'))
                    try:
                        valid = (lo is None or candidate >= lo) and (hi is None or candidate <= hi)
                    except (TypeError, ValueError):
                        valid = False
                else:
                    valid = True
                if valid:
                    st.session_state[key] = candidate
            result = original(*args, **kwargs)
            stored[key] = copy.deepcopy(result)
            return result
        return wrapped

    for method in supported:
        if hasattr(st, method):
            setattr(st, method, make_persistent(getattr(st, method), method))
    # Sidebar methods route through their own object; keep them consistent.
    for method in supported:
        if hasattr(st.sidebar, method):
            setattr(st.sidebar, method, make_persistent(getattr(st.sidebar, method), method))
    st._qunar_persistence_installed = True


def _crop_saved_value(slot, fallback):
    """Persist shared crop-plot inputs even when mode widgets temporarily disappear."""
    return st.session_state.get("qunar_crop_saved_" + slot, fallback)


def _crop_remember_value(slot, value):
    st.session_state["qunar_crop_saved_" + slot] = value
    return value


def _on_crop_changed():
    """Reset only crop-specific inputs, never district, farm total, language or report basket."""
    chosen = st.session_state.get('qunar_assessed_crop_widget')
    previous = st.session_state.get('qunar_last_assessed_crop')
    if previous is not None and chosen != previous:
        crop_widgets = (
            'qunar_area_widget_crop', 'qunar_crop_available_water_widget',
            'qunar_crop_water_widget', 'qunar_crop_energy_widget',
            'qunar_crop_irrigation_widget', 'qunar_crop_reuse_widget',
            'qunar_crop_meter_widget', 'qunar_crop_soil_sensors_widget',
            'qunar_crop_efficient_pump_widget', 'qunar_crop_solar_widget',
            'qunar_crop_target_solar_widget', 'confirm_observed_zero_water_crop',
            'confirm_observed_zero_energy_crop', 'qunar_crop_resource_scope_widget',
        )
        for k in crop_widgets:
            st.session_state.pop(k, None)
            st.session_state.get('qunar_persistent_input_values_v2', {}).pop(k, None)
        for k in list(st.session_state):
            if k.startswith(('qunar_crop_saved_', 'qunar_saved_fuel_crop_', 'resource_amount_crop_')):
                st.session_state.pop(k, None)
                st.session_state.get('qunar_persistent_input_values_v2', {}).pop(k, None)
        st.session_state.pop('qunar_calculated_mode', None)
        st.session_state['qunar_crop_inputs_reset_notice'] = True
    st.session_state['qunar_last_assessed_crop'] = chosen

st.set_page_config(page_title=APP_NAME, page_icon="🌱", layout="wide", initial_sidebar_state="expanded")
_install_persistent_input_widgets()

if not st.session_state.get("ga_page_view_sent"):
    st.session_state["ga_page_view_sent"] = True
    ga_event("page_view")

st.markdown("""
<style>
:root { --qunar:#234f36; --qunar-soft:#f1f7f2; --text:#1f2923; --muted:#66736b; }
html, body, [class*="css"], .stApp, .stMarkdown, .stText, label, input, button {
  font-family: "Segoe UI", "Noto Sans", Arial, sans-serif !important;
}
html, body { font-size: 18px; }
/* Keep native Streamlit background and text paired in both themes. */
.block-container { max-width: 1320px; padding-top: 1.35rem; padding-bottom: 3rem; }
section[data-testid="stSidebar"] { border-right: 1px solid #e4e9e4; }
section[data-testid="stSidebar"] * { font-size: 16.5px !important; line-height:1.45 !important; }
h1 { font-size: 2.35rem !important; line-height: 1.16 !important; font-weight:760 !important; }
h2 { font-size: 1.95rem !important; line-height: 1.2 !important; font-weight:740 !important; }
h3 { font-size: 1.62rem !important; line-height: 1.23 !important; font-weight:730 !important; margin-top:1.15rem !important; }
h4 { font-size: 1.30rem !important; line-height: 1.3 !important; font-weight:700 !important; }
p, li, label, .stMarkdown { font-size:18px; line-height: 1.68; }
small, .stCaption, [data-testid="stCaptionContainer"] { font-size:15.5px !important; line-height:1.5 !important; }
div[data-testid="stMetric"] { background: #202c28; border: 1px solid #3b5045; border-radius: 15px; padding: 17px 18px; min-height: 112px; box-shadow:0 2px 8px rgba(31,62,42,.025); }
div[data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 760 !important; letter-spacing:-.02em; }
div[data-testid="stMetricLabel"] { font-size: 1.02rem !important; font-weight: 650 !important; }
.stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] button { min-height: 50px; border-radius: 11px; font-size: 17px !important; font-weight: 700; }
div[data-baseweb="input"] input, div[data-baseweb="select"] { min-height: 46px; font-size: 17px !important; }
div[data-testid="stAlert"] { border-radius: 12px; }
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
.qunar-hero { text-align:center; padding:3.35rem 1rem 1.10rem; margin:0 0 1.1rem; background:transparent; border:0; border-radius:0; box-shadow:none; overflow:visible; }
.qunar-brand { font-size:68px; line-height:1.18; font-weight:900; letter-spacing:2px; color:var(--qunar); margin:0; padding:.10em 0 0; overflow:visible; }
.qunar-acronym { margin-top:.52rem; font-size:29px; line-height:1.28; font-weight:400; color:inherit; letter-spacing:.002em; }
.qunar-acronym .qunar-initial { display:inline-block; font-size:1.08em; line-height:1; font-weight:950; color:inherit; letter-spacing:.01em; }
.qunar-translation { margin-top:.46rem; font-size:22px; line-height:1.28; font-weight:500; color:inherit; opacity:.82; letter-spacing:.008em; }
@media (max-width: 900px) {
  .qunar-hero { padding-top:4.25rem; }
  .qunar-brand { font-size:56px; line-height:1.20; }
  .qunar-acronym { font-size:23px; line-height:1.30; }
  .qunar-translation { font-size:19px; }
}
@media (max-width: 600px) {
  .qunar-hero { padding-top:4.85rem; padding-left:.35rem; padding-right:.35rem; }
  .qunar-brand { font-size:46px; line-height:1.22; }
  .qunar-acronym { font-size:19px; line-height:1.34; }
  .qunar-translation { font-size:17px; line-height:1.32; }
}
.qunar-key, .qunar-reco { background:#24392d; border-left:5px solid #4f7d5d; border-radius:10px; padding:15px 17px; margin:.65rem 0 1rem; font-size:18px; line-height:1.55; }
.qunar-key strong, .qunar-reco strong { font-weight:800; }
.qunar-insight { background:#202c28; border:1px solid #3b5045; border-radius:12px; padding:14px 17px; margin:.55rem 0; font-size:17.5px; line-height:1.58; }
.qunar-insight strong { color:inherit; font-weight:760; }
.qunar-export { margin-top:1.2rem; padding-top:.5rem; }
/* Do not force the root Streamlit background or text color. Native widgets own their theme. */
.qunar-hero, .qunar-key, .qunar-reco, .qunar-insight, div[data-testid="stMetric"] { color: inherit; }
.qunar-brand { color: #57a879; }
div[data-testid="stMetric"] [data-testid="stMetricLabel"] * { color:#c5d2ca !important; }
div[data-testid="stMetricValue"], div[data-testid="stMetricValue"] > div {
  white-space:normal !important; overflow:visible !important;
  text-overflow:clip !important; overflow-wrap:anywhere; line-height:1.25;
}
div[data-testid="stMetricLabel"], div[data-testid="stMetricLabel"] p {
  white-space:normal !important; overflow:visible !important; text-overflow:clip !important;
}

/* Muted green cards use paired foreground/background colors in either theme. */
div[data-testid="stMetric"],
div[data-testid="stMetric"] [data-testid="stMetricLabel"],
div[data-testid="stMetric"] [data-testid="stMetricValue"],
div[data-testid="stMetric"] [data-testid="stMetricLabel"] *,
div[data-testid="stMetric"] [data-testid="stMetricValue"] *,
.qunar-key, .qunar-key *, .qunar-reco, .qunar-reco *,
.qunar-insight, .qunar-insight * { color:#edf4ef !important; }


</style>
""", unsafe_allow_html=True)


_run_started = time.perf_counter()
_timings = {}
def timed_call(name, fn, *args, **kwargs):
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    _timings[name] = _timings.get(name, 0.0) + (time.perf_counter() - t0)
    return result

def insight_html(text):
    text = str(text).strip()
    if not text:
        return ""
    # Bold the first sentence so the actionable point is scannable.
    cut = text.find(".")
    if cut > 15:
        first, rest = text[:cut+1], text[cut+1:]
        return f'<div class="qunar-insight"><strong>{html.escape(first)}</strong>{html.escape(rest)}</div>'
    return f'<div class="qunar-insight">{html.escape(text)}</div>'



def smart_resource_scenario(lang, irrigation_type, actual_water_m3, area_ha, reference_water_m3_ha,
                            energy_kwh, water_tariff, electricity_tariff, saving_target_pct, investment,
                            seasons_per_year, water_source="user", energy_source="user"):
    """Transparent before/after resource-saving scenario with labelled fallback data."""
    area=max(float(area_ha or 0.0),0.0)
    ref_water=max(float(reference_water_m3_ha or 0.0),0.0)*area if area>0 else 0.0
    water=max(float(actual_water_m3 or 0.0),0.0)
    if water<=0 and ref_water>0 and water_source != "user":
        water=ref_water; water_source="district_crop_reference"
    # Never invent pumping kWh from an unsupported universal intensity.
    # Observed grid kWh alone does not prove that it was used for pumping.
    energy=float(energy_kwh) if energy_kwh is not None else None
    pumping_baseline=(energy if energy is not None and energy_source == 'physical_model' else 0.0)
    if energy is not None and energy<0:
        raise ValueError('Electricity consumption cannot be negative')
    wt=max(float(DEFAULT_IRRIGATION_WATER_TARIFF_KZT_M3 if water_tariff is None else water_tariff),0.0)
    et=max(float(DEFAULT_ELECTRICITY_TARIFF_KZT_KWH if electricity_tariff is None else electricity_tariff),0.0)
    saving=max(0.0,min(float(saving_target_pct or DEFAULT_WATER_SAVING_TARGET),100.0))/100.0
    pressure=(water/ref_water*100.0) if water>0 and ref_water>0 else None

    if irrigation_type=='furrow':
        tech={'kk':'тамшылатып немесе жаңбырлатып суару','ru':'капельное или дождевальное орошение','en':'drip or sprinkler irrigation'}[lang]
    elif irrigation_type=='sprinkler':
        tech={'kk':'тамшылатып суару немесе дәл суару кестесі','ru':'капельное орошение или точное планирование полива','en':'drip irrigation or precision irrigation scheduling'}[lang]
    elif irrigation_type=='drip':
        tech={'kk':'топырақ ылғалдылығы датчиктері және дәл суару кестесі','ru':'датчики влажности почвы и точное планирование полива','en':'soil-moisture sensors and precision irrigation scheduling'}[lang]
    else:
        tech={'kk':'су үнемдейтін суару технологиясы','ru':'водосберегающую технологию орошения','en':'a water-saving irrigation technology'}[lang]

    saved_water=water*saving; after_water=max(water-saved_water,0.0)
    before_water_cost=water*wt; after_water_cost=after_water*wt
    water_saving_cost=max(before_water_cost-after_water_cost,0.0)
    pumping_after=max(pumping_baseline*(1.0-saving),0.0)
    non_pumping=max(energy-pumping_baseline,0.0) if energy is not None else None
    after_energy=non_pumping+pumping_after if non_pumping is not None else None
    before_energy_cost=energy*et if energy is not None else None
    after_energy_cost=after_energy*et if after_energy is not None else None
    energy_saving_cost=max(before_energy_cost-after_energy_cost,0.0) if before_energy_cost is not None else None
    # Only cost components with a valid input are included. Never claim total farm saving.
    total_saving=water_saving_cost+(energy_saving_cost or 0.0)
    annual_saving=total_saving*max(float(seasons_per_year or 1.0),1.0)
    inv=max(float(investment or 0.0),0.0)
    pb=inv/annual_saving if inv>0 and annual_saving>0 else None

    observed_water = (water_source == 'user')
    if not observed_water and water>0:
        status={'kk':'Нақты су тұтынуы енгізілмеген. Сценарий анықтамалық су қажеттілігін бастапқы мән ретінде пайдаланады, сондықтан бұл шаруашылықтағы артық су тұтыну диагнозы емес.','ru':'Фактическое водопотребление не введено. Сценарий использует справочную потребность как базу, поэтому это не диагностика перерасхода воды конкретного хозяйства.','en':'Observed farm water use was not entered. The scenario uses the reference requirement as its baseline, so this is not a diagnosis of farm-level overuse.'}[lang]
    elif pressure is None:
        status={'kk':'Су жүктемесін салыстыру үшін жеткілікті дерек жоқ.','ru':'Недостаточно данных для сравнения водной нагрузки.','en':'There are not enough data for a water-pressure comparison.'}[lang]
    elif pressure>110:
        status={'kk':f'Су тұтынуы анықтамалық қажеттіліктің шамамен {pressure:.0f}% құрайды және жоғары деп белгіленді.','ru':f'Потребление воды составляет около {pressure:.0f}% от справочной потребности и отмечено как повышенное.','en':f'Water use is about {pressure:.0f}% of the reference requirement and is flagged as elevated.'}[lang]
    else:
        status={'kk':f'Су тұтынуы анықтамалық қажеттіліктің шамамен {pressure:.0f}% құрайды; айқын артық тұтыну белгісі жоқ.','ru':f'Потребление воды составляет около {pressure:.0f}% от справочной потребности; явного перерасхода по этому сравнению не выявлено.','en':f'Water use is about {pressure:.0f}% of the reference requirement; this comparison does not indicate clear overuse.'}[lang]
    if observed_water and pressure is not None and pressure>110:
        recommendation={'kk':f'QŪNAR {tech} сценарийін басым түрде қарастыруды ұсынады.','ru':f'QŪNAR рекомендует приоритетно рассмотреть {tech}.','en':f'QŪNAR recommends prioritising a {tech} scenario.'}[lang]
    else:
        recommendation={'kk':f'Су шығынын азайту мақсаты болса, QŪNAR {tech} сценарийін салыстыруды ұсынады.','ru':f'Если цель - снизить водные затраты, QŪNAR предлагает сравнить сценарий: {tech}.','en':f'If reducing water use is a priority, QŪNAR suggests comparing a {tech} scenario.'}[lang]
    labels={
      'kk':{'user':'пайдаланушы деректері','district_crop_reference':'аудан-дақыл анықтамасы','pumping_reference':'су айдау коэффициенті бойынша бағалау','user_total_with_pumping_estimate':'пайдаланушының жалпы энергиясы; суару үлесі айдау коэффициентімен бағаланды','physical_model':'сорғының тегеуріні мен ПӘК бойынша есеп','unknown':'белгісіз','unavailable':'дерек жоқ'},
      'ru':{'user':'данные пользователя','district_crop_reference':'районно-культурный справочник','pumping_reference':'оценка по коэффициенту перекачки воды','user_total_with_pumping_estimate':'общая энергия пользователя; насосная доля оценена по коэффициенту перекачки','physical_model':'по напору и КПД насоса (сценарий)','unknown':'неизвестно','unavailable':'нет данных'},
      'en':{'user':'user data','district_crop_reference':'district-crop reference','pumping_reference':'estimate from pumping-energy coefficient','user_total_with_pumping_estimate':'user total energy; pumping share estimated from water-pumping coefficient','physical_model':'physical pumping model (scenario)','unknown':'unknown','unavailable':'unavailable'}}[lang]
    if water_source == 'user' and str(energy_source).startswith('user'):
        evidence_grade = {'kk':'жоғары','ru':'высокая','en':'high'}[lang]
    elif water_source == 'user' or str(energy_source).startswith('user'):
        evidence_grade = {'kk':'орташа','ru':'средняя','en':'medium'}[lang]
    else:
        evidence_grade = {'kk':'анықтамалық сценарий','ru':'справочный сценарий','en':'reference scenario'}[lang]
    return {'technology':tech,'status':status,'recommendation':recommendation,'water_pressure_pct':pressure,
      'evidence_grade':evidence_grade,
      'before_water_m3':water,'after_water_m3':after_water,'saved_water_m3':saved_water,
      'before_water_cost_kzt':before_water_cost,'after_water_cost_kzt':after_water_cost,'water_cost_saving_kzt':water_saving_cost,
      'before_energy_kwh':energy,'after_energy_kwh':after_energy,'before_energy_cost_kzt':before_energy_cost,
      'after_energy_cost_kzt':after_energy_cost,'energy_cost_saving_kzt':energy_saving_cost,'total_saving_kzt':total_saving,
      'payback_years':pb,'saving_target_pct':saving*100.0,'investment_used_kzt':inv,
      'water_source':labels.get(water_source,water_source),'energy_source':labels.get(energy_source,energy_source),
      'investment_source':labels.get('user' if inv>0 else 'unavailable'),
      'tariff_source':{'kk':'QŪNAR жалпы анықтамалық сценарий тарифі немесе пайдаланушы мәні','ru':'общий справочный сценарийный тариф QŪNAR или значение пользователя','en':'QŪNAR general reference scenario tariff or user value'}[lang]}

def structured_recommendations(texts, analysis, lang):
    texts = list(texts or [])
    analysis = list(analysis or [])
    labels = {
        "evidence": {"kk":"Негіздеме","ru":"Основание","en":"Evidence"}[lang],
        "effect": {"kk":"Күтілетін әсер","ru":"Ожидаемый эффект","en":"Expected effect"}[lang],
        "priority": {"kk":"Басымдық","ru":"Приоритет","en":"Priority"}[lang],
        "effect_text": {
            "kk":"Ресурстық шығынды, климаттық тәуекелді немесе өндірістік шығынды төмендетуге бағытталған. Нақты әсер пайдаланушы енгізген жағдайлар мен тарифтерге тәуелді.",
            "ru":"Направлено на снижение ресурсной нагрузки, климатического риска или производственных затрат. Точный эффект зависит от введенных условий и тарифов.",
            "en":"Targets lower resource pressure, climate risk or operating cost. The exact effect depends on the entered conditions and tariffs."
        }[lang],
    }
    out=[]
    for i,text in enumerate(texts[:5],1):
        ev = analysis[min(i-1, len(analysis)-1)] if analysis else ""
        out.append({
            "title": f"{labels['priority']} {i}",
            "text": str(text),
            "evidence": str(ev),
            "effect": labels["effect_text"],
            "evidence_label": labels["evidence"],
            "effect_label": labels["effect"],
        })
    return out

@st.cache_data(show_spinner=False)
def _cached_excel_report(payload_json: str) -> bytes:
    return build_excel_report(json.loads(payload_json))

@st.cache_data(show_spinner=False)
def _cached_pdf_report(payload_json: str) -> bytes:
    return build_pdf_report(json.loads(payload_json))

@st.cache_data(show_spinner=False)
def _cached_word_report(payload_json: str) -> bytes:
    return build_word_report(json.loads(payload_json))


@st.cache_data(show_spinner=False)
def _cached_combined_excel(payload_json: str) -> bytes:
    return build_combined_excel_report(json.loads(payload_json))

@st.cache_data(show_spinner=False)
def _cached_combined_pdf(payload_json: str) -> bytes:
    return build_combined_pdf_report(json.loads(payload_json))

@st.cache_data(show_spinner=False)
def _cached_combined_word(payload_json: str) -> bytes:
    return build_combined_word_report(json.loads(payload_json))

def _report_basket():
    basket = st.session_state.setdefault("qunar_report_basket", {})
    normalized = normalize_report_library(basket)
    if set(basket.keys()) != set(normalized.keys()):
        st.session_state["qunar_report_basket"] = normalized
    return normalized


@st.fragment
def render_report_workspace(lang: str):
    """Session-scoped report library, with selection and deletion independent of inclusion."""
    labels = {
        'title': {'ru':'Мой отчёт', 'kk':'Менің есебім', 'en':'My report'}[lang],
        'empty': {'ru':'Расчёты пока не сохранены. После расчёта нажмите «Добавить в общий отчёт».',
                  'kk':'Сақталған есеп жоқ. Есептеуден кейін жалпы есепке қосыңыз.',
                  'en':'No saved calculations. Add one after running an assessment.'}[lang],
        'select': {'ru':'Включить в выгрузку', 'kk':'Жүктеуге қосу', 'en':'Include in export'}[lang],
        'delete': {'ru':'Удалить', 'kk':'Жою', 'en':'Delete'}[lang],
        'clear': {'ru':'Удалить все сохранённые расчёты', 'kk':'Барлық есепті жою', 'en':'Delete all saved calculations'}[lang],
        'none': {'ru':'Отметьте хотя бы один расчёт для выгрузки.', 'kk':'Жүктеу үшін кемінде бір есепті белгілеңіз.',
                 'en':'Select at least one calculation to export.'}[lang],
        'hint': {'ru':'Галочка управляет выгрузкой, а не удалением. Разные варианты одного режима сохраняются отдельно; одинаковые повторно не добавляются.',
                 'kk':'Белгі тек жүктеуге әсер етеді. Әртүрлі сценарийлер жеке сақталады, бірдейі қайталанбайды.',
                 'en':'Checkboxes control exports only. Different scenarios are saved independently; identical ones are not duplicated.'}[lang],
        'comparison': {'ru':'Сравнение вариантов', 'kk':'Нұсқаларды салыстыру', 'en':'Scenario comparison'}[lang],
    }
    basket = _report_basket()
    st.markdown('<div id="qunar-report-workspace"></div>', unsafe_allow_html=True)
    with st.expander(f"{labels['title']} ({len(basket)})", expanded=False):
        if not basket:
            st.caption(labels['empty'])
            return
        st.caption(labels['hint'])
        include = {}
        mode_counter = {}
        for rid, payload in list(basket.items()):
            mode = str(payload.get('mode_key', ''))
            mode_counter[mode] = mode_counter.get(mode, 0) + 1
            tag = f"{payload.get('mode_label', mode)} · #{mode_counter[mode]} · {payload.get('generated_at', '')}"
            select_col, delete_col = st.columns([5, 1])
            with select_col:
                include[rid] = st.checkbox(f"{labels['select']}: {tag}", key=f"qunar_report_include_{rid}", value=True)
            with delete_col:
                if st.button(labels['delete'], key=f"qunar_report_delete_{rid}", use_container_width=True):
                    basket.pop(rid, None)
                    st.session_state['qunar_report_basket'] = basket
                    st.session_state.pop(f'qunar_report_include_{rid}', None)
                    st.rerun(scope='fragment')
        chosen = selected_reports(basket, include)
        if not chosen:
            st.info(labels['none'])
        else:
            diffs = compared_variants(chosen)
            if diffs:
                st.caption(f"{labels['comparison']}: {len(diffs)}")
                for comp in diffs:
                    with st.expander(f"{comp['mode_label']} · #1 ↔ #{comp['candidate']}", expanded=False):
                        for name, old, new in (comp['inputs'][:12] + comp['results'][:12]):
                            st.write(f"**{name}**: {old} → {new}")
            payload_json = json.dumps(chosen, ensure_ascii=False, sort_keys=True, default=str)
            bundle_id = hashlib.sha256(payload_json.encode('utf-8')).hexdigest()[:16]
            if st.session_state.get('qunar_bundle_id') != bundle_id:
                st.session_state['qunar_bundle_id'] = bundle_id
                for ext in ('pdf', 'word', 'xlsx'):
                    st.session_state.pop('qunar_full_'+ext, None)
            cols = st.columns(3)
            formats = [
                ('pdf', 'PDF', _cached_combined_pdf, 'application/pdf'),
                ('word', 'Word', _cached_combined_word, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
                ('xlsx', 'Excel', _cached_combined_excel, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ]
            for col, (ext, caption, create, mime) in zip(cols, formats):
                with col:
                    prep = {'ru':f'Подготовить {caption}', 'kk':f'{caption} дайындау', 'en':f'Prepare {caption}'}[lang]
                    download = {'ru':f'Скачать {caption}', 'kk':f'{caption} жүктеу', 'en':f'Download {caption}'}[lang]
                    if st.button(prep, use_container_width=True, key=f'prep_full_{ext}_{bundle_id}'):
                        ga_event('generate_report', report_format=ext, report_scope='combined')
                        with st.spinner(prep+'...'):
                            st.session_state['qunar_full_'+ext] = create(payload_json)
                    data = st.session_state.get('qunar_full_'+ext)
                    if data:
                        file_ext = 'docx' if ext == 'word' else ext
                        clicked = st.download_button(download, data=data,
                            file_name=f'QUNAR_full_report_{datetime.now():%Y%m%d_%H%M}.{file_ext}',
                            mime=mime, use_container_width=True, key=f'full_{ext}_{bundle_id}')
                        if clicked: ga_event('download_'+ext, report_scope='combined')
        if st.button(labels['clear'], use_container_width=True, key='clear_report_basket'):
            st.session_state['qunar_report_basket'] = {}
            st.rerun(scope='fragment')


@st.fragment
def render_export_panel(report_payload: dict, lang: str):
    """Preserve the separate calculation's download buttons in PDF, Word, Excel order."""
    payload_json = json.dumps(report_payload, ensure_ascii=False, sort_keys=True, default=str)
    report_id = report_fingerprint(report_payload)
    if st.session_state.get('qunar_export_report_id') != report_id:
        st.session_state['qunar_export_report_id'] = report_id
        for ext in ('pdf', 'word', 'xlsx'):
            st.session_state.pop('qunar_'+ext, None)
    title = {'ru':'Скачать отчёт', 'kk':'Есепті жүктеу', 'en':'Download report'}[lang]
    with st.expander(title, expanded=False):
        st.caption({'ru':'Можно скачать отдельный расчёт или сохранить его в «Мой отчёт».',
                    'kk':'Бұл есепті бөлек жүктеуге немесе «Менің есебім» бөліміне қосуға болады.',
                    'en':'Download this calculation or save it in My report.'}[lang])
        add = {'ru':'Добавить в общий отчёт', 'kk':'Жалпы есепке қосу', 'en':'Add to combined report'}[lang]
        if st.button(add, use_container_width=True, key=f'add_bundle_{report_id}'):
            basket = _report_basket()
            added = add_report(basket, report_payload)
            st.session_state['qunar_report_basket'] = basket
            st.info(({'ru':'Сохранён новый сценарий.', 'kk':'Жаңа сценарий сақталды.', 'en':'New scenario saved.'} if added else
                     {'ru':'Такой расчёт уже сохранён; дубликат не добавлен.',
                      'kk':'Бұл есеп бұрын сақталған, қайталанған жоқ.',
                      'en':'This exact calculation is already saved; no duplicate added.'})[lang])
        cols = st.columns(3)
        formats = [('pdf', 'PDF', _cached_pdf_report, 'application/pdf'),
                   ('word', 'Word', _cached_word_report, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
                   ('xlsx', 'Excel', _cached_excel_report, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')]
        for col, (ext, caption, create, mime) in zip(cols, formats):
            with col:
                prep = {'ru':f'Подготовить {caption}', 'kk':f'{caption} дайындау', 'en':f'Prepare {caption}'}[lang]
                download = {'ru':f'Скачать {caption}', 'kk':f'{caption} жүктеу', 'en':f'Download {caption}'}[lang]
                if st.button(prep, use_container_width=True, key=f'prepare_{ext}_{report_id}'):
                    ga_event('generate_report', report_format=ext, report_scope='single', mode_key=report_payload.get('mode_key'))
                    with st.spinner(prep+'...'):
                        st.session_state['qunar_'+ext] = create(payload_json)
                data = st.session_state.get('qunar_'+ext)
                if data:
                    file_ext = 'docx' if ext == 'word' else ext
                    clicked = st.download_button(download, data=data,
                        file_name=f'QUNAR_report_{datetime.now():%Y%m%d_%H%M}.{file_ext}',
                        mime=mime, use_container_width=True, key=f'download_{ext}_{report_id}')
                    if clicked: ga_event('download_'+ext, report_scope='single', mode_key=report_payload.get('mode_key'))

# Keep the language selector identity stable across reruns. Streamlit treats a
# widget whose translated label changes as a new widget; index=0 used to reset
# the interface to Kazakh whenever a mode/radio triggered a rerun.
_prior_lang = st.session_state.get("qunar_preferred_lang", "kk")
_lang_by_code = {code: caption for caption, code in LANGUAGES.items()}
if st.session_state.get("qunar_language_selector") not in LANGUAGES:
    st.session_state["qunar_language_selector"] = _lang_by_code.get(_prior_lang, _lang_by_code["kk"])
_lang_select_caption = {
    'ru': 'Язык интерфейса',
    'kk': 'Интерфейс тілі',
    'en': 'Interface language',
}.get(_prior_lang, 'Интерфейс тілі')
st.sidebar.markdown('**' + _lang_select_caption + '**')
lang_label = st.sidebar.selectbox(
    'QUNAR language selector - stable internal label',
    list(LANGUAGES.keys()),
    key='qunar_language_selector',
    label_visibility='collapsed',
    help='Қазақша / Русский / English - select the interface language.',
)
lang = LANGUAGES[lang_label]
st.session_state['qunar_preferred_lang'] = lang

# Retain canonical sidebar selections when their visible labels are translated.
# The "saved" keys are separate from Streamlit widget keys on purpose.
def _sidebar_saved_index(slot, choices, fallback):
    options = list(choices)
    saved = st.session_state.get('qunar_saved_' + slot, fallback)
    return options.index(saved) if saved in options else options.index(fallback)

def _remember_sidebar(slot, value):
    st.session_state['qunar_saved_' + slot] = value
    return value
if st.session_state.get("ga_last_language") != lang:
    if st.session_state.get("ga_last_language") is not None:
        ga_event("change_language", language=lang)
    st.session_state["ga_last_language"] = lang
# Copy translations locally so deployment remains backward-compatible if Streamlit
# briefly serves app.py with a cached/older core.config during a GitHub redeploy.
t = dict(TEXT[lang])
_MODE_LABEL_FALLBACK = {
    "kk": {"mode5": "Мал шаруашылығы ресурстарын бағалау"},
    "ru": {"mode5": "Оценить ресурсы животноводства"},
    "en": {"mode5": "Assess livestock resources"},
}
# Keep mode6 experimental status visible in the sidebar in all three languages.
# This is a display-only change: stable mode key remains 'mode6'.
_MODE_LABEL_FALLBACK['ru']['mode6'] = 'Сравнить растениеводство и животноводство (бета-версия)'
_MODE_LABEL_FALLBACK['kk']['mode6'] = 'Өсімдік және мал шаруашылығын салыстыру (бета-нұсқа)'
_MODE_LABEL_FALLBACK['en']['mode6'] = 'Compare crops and livestock (beta)'
for _key, _label in _MODE_LABEL_FALLBACK[lang].items():
    t.setdefault(_key, _label)

UNITS = {
    "kk": {
        "ha":"га", "m3":"м³", "m3_ha":"м³/га", "kwh":"кВт·сағ", "kwh_ha":"кВт·сағ/га",
        "kg":"кг", "kg_ha":"кг/га", "t":"т", "dry_t":"т құрғақ зат",
        "centner_ha":"ц/га", "solar":"МДж/м²/тәул.", "co2_t":"т CO₂e", "co2_kg_ha":"кг CO₂e/га",
        "livestock_unit":"шартты мал бірлігі", "livestock_unit_ha":"шартты мал бірлігі/га",
        "mm":"мм", "growth_year":"%/жыл", "currency":"тг"
    },
    "ru": {
        "ha":"га", "m3":"м³", "m3_ha":"м³/га", "kwh":"кВт·ч", "kwh_ha":"кВт·ч/га",
        "kg":"кг", "kg_ha":"кг/га", "t":"т", "dry_t":"т сухого вещества",
        "centner_ha":"ц/га", "solar":"МДж/м²/сут.", "co2_t":"т CO₂e", "co2_kg_ha":"кг CO₂e/га",
        "livestock_unit":"условная единица скота", "livestock_unit_ha":"условная единица скота/га",
        "mm":"мм", "growth_year":"%/год", "currency":"тг"
    },
    "en": {
        "ha":"ha", "m3":"m³", "m3_ha":"m³/ha", "kwh":"kWh", "kwh_ha":"kWh/ha",
        "kg":"kg", "kg_ha":"kg/ha", "t":"t", "dry_t":"t dry matter",
        "centner_ha":"centners/ha", "solar":"MJ/m²/day", "co2_t":"t CO₂e", "co2_kg_ha":"kg CO₂e/ha",
        "livestock_unit":"livestock unit (LU)", "livestock_unit_ha":"LU/ha",
        "mm":"mm", "growth_year":"%/year", "currency":"KZT"
    },
}[lang]

_BENCHMARK_CATEGORY_LABELS = {
    "Cattle": {"kk":"Ірі қара мал", "ru":"Крупный рогатый скот", "en":"Cattle"},
    "Cows": {"kk":"Сиырлар", "ru":"Коровы", "en":"Cows"},
    "Sheep/goats": {"kk":"Қой мен ешкі", "ru":"Овцы и козы", "en":"Sheep and goats"},
    "Pigs": {"kk":"Шошқа", "ru":"Свиньи", "en":"Pigs"},
    "Horses": {"kk":"Жылқы", "ru":"Лошади", "en":"Horses"},
    "Camels": {"kk":"Түйе", "ru":"Верблюды", "en":"Camels"},
    "Poultry": {"kk":"Құс", "ru":"Птица", "en":"Poultry"},
}

def benchmark_category_label(code):
    return _BENCHMARK_CATEGORY_LABELS.get(str(code), {}).get(lang, str(code))

_MODEL_TIER_LABELS = {
    "ML": {"kk":"Машиналық оқыту", "ru":"Машинное обучение", "en":"Machine learning"},
    "ML + QŪNAR": {"kk":"Машиналық оқыту + QŪNAR", "ru":"Машинное обучение + QŪNAR", "en":"Machine learning + QŪNAR"},
    "ML + CLREM": {"kk":"Машиналық оқыту + CLREM", "ru":"Машинное обучение + CLREM", "en":"Machine learning + CLREM"},
    "QŪNAR": {"kk":"QŪNAR есептік модулі", "ru":"Расчетный модуль QŪNAR", "en":"QŪNAR decision module"},
    "Observed evidence": {"kk":"Бақыланған деректер", "ru":"Наблюдаемые данные", "en":"Observed evidence"},
}
def model_tier_label(raw):
    return _MODEL_TIER_LABELS.get(str(raw), {}).get(lang, str(raw))

_RECOMMENDATION_TYPE_LABELS = {
    "Priority": {"kk":"Басым", "ru":"Приоритетный", "en":"Priority"},
    "Promising": {"kk":"Перспективалы", "ru":"Перспективный", "en":"Promising"},
    "Moderate": {"kk":"Орташа басымдық", "ru":"Умеренный приоритет", "en":"Moderate"},
    "Low priority": {"kk":"Төмен басымдық", "ru":"Низкий приоритет", "en":"Low priority"},
}
def recommendation_type_label(raw):
    return _RECOMMENDATION_TYPE_LABELS.get(str(raw), {}).get(lang, str(raw))

def water_source_label(info):
    if info is None:
        return {"kk":"Енгізілмеген", "ru":"Не введено", "en":"Not entered"}[lang]
    if getattr(info, "source_tier", "") == "regional_fallback":
        return {
            "kk":"Өңірлік калибрлеу мәні",
            "ru":"Региональное калибровочное значение",
            "en":"Regional calibration value",
        }[lang]
    return {
        "kk":"Қазақстан Республикасының ресми суару нормалары және есептік түзету",
        "ru":"Официальные нормы орошения Республики Казахстан и расчетная корректировка",
        "en":"Official irrigation norms of the Republic of Kazakhstan with model adjustment",
    }[lang]
user_level = _remember_sidebar('user_level', st.sidebar.radio(
    t["user_level"],
    ["farmer", "specialist", "researcher"],
    format_func=lambda x: {"farmer": t["level_farmer"], "specialist": t["level_specialist"], "researcher": t["level_researcher"]}[x],
    index=_sidebar_saved_index('user_level', ["farmer", "specialist", "researcher"], 'farmer'),
    key='qunar_user_level_widget',
    help={"kk":"Базалық: жылдам есеп. Кеңейтілген: тарифтер, сорғылар, технология және сценарийлер. Зерттеуші: дереккөздер мен модель сапасын тексеру. Есептік нормативтер деңгейге қарай өзгермейді.","ru":"Базовый: минимум полей и быстрый результат. Расширенный: тарифы, насосы, технологии и сценарии. Исследовательский: источники данных, диагностика машинного обучения и научные проверки. Расчётные нормативы между уровнями не меняются.","en":"Basic: quick assessment with fewer inputs. Advanced: costs, pumping, technologies and scenarios. Research: source data and model diagnostics. The reference norms do not change between levels."}[lang],
))
if user_level == "farmer":
    st.sidebar.caption(t["level_basic_hint"])
    st.sidebar.caption({"kk":"QŪNAR анонимді пайдалану статистикасын Google Analytics арқылы жинайды.","ru":"QŪNAR собирает обезличенную статистику использования через Google Analytics.","en":"QŪNAR collects anonymized usage statistics through Google Analytics."}[lang])

    with st.sidebar.expander({"kk":"Қате туралы хабарлау","ru":"Сообщить об ошибке","en":"Report an error"}[lang]):
        st.caption({
            "kk":"Мәселені сипаттаңыз, қате мәтінін қойыңыз және қажет болса скриншот тіркеңіз.",
            "ru":"Опишите проблему, вставьте текст ошибки и при необходимости приложите скриншот.",
            "en":"Describe the problem, paste the error text and optionally attach a screenshot."
        }[lang])
        with st.form("bug_report_form", clear_on_submit=True):
            bug_desc = st.text_area({"kk":"Не болды?","ru":"Что произошло?","en":"What happened?"}[lang], height=100)
            bug_error = st.text_area({"kk":"Қате мәтіні","ru":"Текст ошибки","en":"Error text"}[lang], height=90)
            bug_contact = st.text_input({"kk":"Сіздің e-mail (міндетті емес)","ru":"Ваш e-mail (необязательно)","en":"Your email (optional)"}[lang])
            bug_shot = st.file_uploader({"kk":"Скриншот (міндетті емес)","ru":"Скриншот (необязательно)","en":"Screenshot (optional)"}[lang], type=["png","jpg","jpeg","webp"])
            bug_submit = st.form_submit_button({"kk":"Жіберу","ru":"Отправить сообщение","en":"Send report"}[lang], use_container_width=True)
        if bug_submit:
            if not (bug_desc or bug_error):
                st.warning({"kk":"Қысқаша сипаттама немесе қате мәтінін енгізіңіз.","ru":"Добавьте описание или текст ошибки.","en":"Add a description or error text."}[lang])
            else:
                try:
                    sent, recipient = _send_bug_report(bug_desc, bug_contact, bug_error, bug_shot)
                    if sent:
                        st.success({"kk":"Хабарлама жіберілді. Рақмет.","ru":"Сообщение отправлено. Спасибо.","en":"Report sent. Thank you."}[lang])
                        ga_event("bug_report_sent")
                    else:
                        st.info({
                            "kk":"Автоматты жіберу үшін Streamlit Secrets ішінде e-mail параметрлерін қосу қажет.",
                            "ru":"Для автоматической отправки нужно один раз добавить почтовые параметры в Streamlit Secrets.",
                            "en":"To enable automatic sending, add the email settings to Streamlit Secrets once."
                        }[lang])
                except Exception as exc:
                    st.error({"kk":"Хабарламаны жіберу сәтсіз аяқталды.","ru":"Не удалось отправить сообщение.","en":"Could not send the report."}[lang])
                    if user_level == "researcher":
                        st.caption(str(exc))
elif user_level == "specialist":
    st.sidebar.caption(t["level_advanced_hint"])
else:
    st.sidebar.caption(t["level_research_hint"])

st.sidebar.caption({
    "farmer": {
        "ru":"Для фермера: район, площадь, культура, вода и обязательный источник энергии. Остальное - справочные расчёты.",
        "kk":"Фермер үшін: аудан, жер көлемі, дақыл, су және міндетті энергия көзі. Қалғаны анықтамалық есеп.",
        "en":"For farmers: district, area, crop, water and a required energy source; remaining inputs use references."}[lang],
    "specialist": {
        "ru":"Для агронома и экономиста: тарифы, полив, насосы, затраты и сценарии «до/после».",
        "kk":"Агроном мен экономист үшін: тариф, суару, сорғы, шығын және «дейін/кейін» сценарийі.",
        "en":"For specialists: tariffs, irrigation, pumps, costs and before/after scenarios."}[lang],
    "researcher": {
        "ru":"Для исследователя: источники данных, проверки ML, чувствительность, FAO-56 и CMIP6.",
        "kk":"Зерттеуші үшін: деректер, ML тексерістері, сезімталдық, FAO-56 және CMIP6.",
        "en":"For researchers: data provenance, ML diagnostics, sensitivity, FAO-56 and CMIP6."}[lang],
}[user_level])

def district_label(code):
    return DISTRICT_LABELS[lang].get(code, code)

def crop_label(code):
    return CROP_LABELS[lang].get(code, code)

_brand_translation = {
    "kk": "Ауыл шаруашылығы табиғи ресурстарын сандық бағалау",
    "ru": "Количественная оценка природных ресурсов сельского хозяйства",
    "en": "",
}[lang]

st.markdown(
    f"""
    <div class="qunar-hero" id="qunar-page-top">
      <div class="qunar-brand">QŪNAR</div>
      <div class="qunar-acronym"><span class="qunar-initial">Q</span>uantified <span class="qunar-initial">U</span>tilization of <span class="qunar-initial">N</span>atural <span class="qunar-initial">A</span>gricultural <span class="qunar-initial">R</span>esources</div>
      {f'<div class="qunar-translation">{_brand_translation}</div>' if _brand_translation else ''}
    </div>
    """,
    unsafe_allow_html=True,
)
st.markdown("""<style>
a.qunar-fixed-nav {position:fixed;right:10px;z-index:99999;background:#f9fbf9;
 color:#214432 !important;border:1px solid #acc2b0;box-shadow:0 2px 9px #0002;
 border-radius:10px;padding:9px 12px;text-decoration:none;font-size:13px;font-weight:600;}
a.qunar-go-top{top:105px;} a.qunar-go-bottom{bottom:110px;}
a.qunar-go-report{top:51%;background:#e9f3ec;}
@media (max-width:640px){a.qunar-fixed-nav{right:5px;font-size:12px;padding:8px 9px;}
 a.qunar-go-top{top:92px;} a.qunar-go-bottom{bottom:125px;}}
</style>
<a class="qunar-fixed-nav qunar-go-top" href="#qunar-page-top" title="Back to top">↑</a>
<a class="qunar-fixed-nav qunar-go-report" href="#qunar-page-top" title="QŪNAR - к логотипу / QŪNAR - back to top">▤</a>
<a class="qunar-fixed-nav qunar-go-bottom" href="#qunar-page-bottom" title="Go to bottom">↓</a>""", unsafe_allow_html=True)
# A single language-matched guide download sits beneath the QŪNAR wordmark,
# ahead of My report. Do not add another top-level expander here.
_guide_file = Path(__file__).resolve().parent / 'docs' / f'QUNAR_User_Guide_{lang.upper()}_v0.8.1.pdf'
if _guide_file.is_file():
    _guide_title = {
        'kk': 'Пайдаланушы нұсқаулығы (PDF)',
        'ru': 'Руководство пользователя (PDF)',
        'en': 'User Guide (PDF)',
    }[lang]
    _guide_help = {
        'kk': 'Алты режимнің кіріс деректері, есептеу әдістері және шектеулері.',
        'ru': 'Ввод данных, методы расчёта и ограничения всех шести режимов.',
        'en': 'Inputs, calculation methods and limitations of all six modes.',
    }[lang]
    _guide_left, _guide_action = st.columns([5, 1], vertical_alignment='center')
    with _guide_action:
        st.download_button(
            label=f'📖 {_guide_title}',
            data=_guide_file.read_bytes(),
            file_name=_guide_file.name,
            mime='application/pdf',
            key='qunar_guide_download',
            help=_guide_help,
            use_container_width=True,
        )
render_report_workspace(lang)

mode_keys = ["mode1", "mode2", "mode3", "mode4", "mode5", "mode6"]
mode_key = _remember_sidebar('mode', st.sidebar.radio(
    t["mode"], mode_keys, format_func=lambda k: t.get(k, k),
    index=_sidebar_saved_index('mode', mode_keys, 'mode1'),
    key='qunar_mode_widget',
    help={"kk":"QŪNAR есептеу міндетін таңдаңыз.","ru":"Выберите задачу, которую должен выполнить QŪNAR.","en":"Choose the analytical task QŪNAR should perform."}[lang],
))
# Keep mode-owned widget values across navigation. Streamlit normally prunes the
# state of widgets that are not rendered in the next mode. The snapshots are
# independent of widget keys, so they survive that cleanup.
_MODE_INPUT_SNAPSHOTS = st.session_state.setdefault('qunar_mode_input_snapshots_v1', {})
_PREVIOUS_INPUT_MODE = st.session_state.get('qunar_last_input_mode_v1')
if _PREVIOUS_INPUT_MODE and _PREVIOUS_INPUT_MODE != mode_key:
    _last_snapshot = _MODE_INPUT_SNAPSHOTS.setdefault(_PREVIOUS_INPUT_MODE, {})
    for _widget_k, _widget_v in list(st.session_state.items()):
        if _widget_k.startswith(('qunar_saved_', 'qunar_farm_', 'qunar_report_')):
            continue  # shared crop, canonical sidebar and reports have separate persistence
        if _widget_k in ('qunar_mode_input_snapshots_v1', 'qunar_last_input_mode_v1'):
            continue
        # Button states are transient and cannot be assigned through session_state.
        # In particular qmix_calculate is a Streamlit button, not a user input.
        if _widget_k in ('qmix_calculate',):
            continue
        if _widget_k.startswith(('qunar_', 'qmix_', 'tariff_basis_', 'confirm_', 'sust_')):
            try:
                import copy as _copy
                _last_snapshot[_widget_k] = _copy.deepcopy(_widget_v)
            except Exception:
                pass
    for _widget_k, _widget_v in _MODE_INPUT_SNAPSHOTS.get(mode_key, {}).items():
        if _widget_k in ('qmix_calculate',):
            continue  # Never restore Streamlit's read-only button state.
        if _widget_k not in st.session_state:
            try:
                import copy as _copy
                st.session_state[_widget_k] = _copy.deepcopy(_widget_v)
            except Exception:
                pass
# qmix_calculate is a momentary Streamlit button. Do not restore it from
# snapshots and do not pop it here: on a button-triggered rerun that would
# erase the click before render_mixed_mode can consume it.
st.session_state['qunar_last_input_mode_v1'] = mode_key

if st.session_state.get("ga_last_mode") != mode_key:
    if st.session_state.get("ga_last_mode") is not None:
        ga_event("assessment_mode", mode_key=mode_key)
    st.session_state["ga_last_mode"] = mode_key
district = _remember_sidebar('district', st.sidebar.selectbox(
    t["district"], DISTRICT_ORDER, format_func=district_label,
    index=_sidebar_saved_index('district', DISTRICT_ORDER, DISTRICT_ORDER[0]),
    key='qunar_district_widget',
    help={"kk":"Есептеу жүргізілетін әкімшілік аудан немесе қала.","ru":"Административный район или город, для которого выполняется расчёт.","en":"Administrative district or city used for the calculation."}[lang],
))

SEASON_MODE_LABELS = {
    "kk": {"next":"Келесі маусым", "current":"Ағымдағы маусым", "completed":"Соңғы аяқталған маусым"},
    "ru": {"next":"Следующий сезон", "current":"Текущий сезон", "completed":"Последний завершённый сезон"},
    "en": {"next":"Next season", "current":"Current season", "completed":"Last completed season"},
}[lang]
season_mode = _remember_sidebar('season', st.sidebar.radio(
    {"kk":"Бағалау кезеңі","ru":"Период оценки","en":"Assessment period"}[lang],
    ["next","current","completed"],
    format_func=lambda x: SEASON_MODE_LABELS[x],
    index=_sidebar_saved_index('season', ["next","current","completed"], 'next'),
    key='qunar_season_widget',
    help={"kk":"Келесі маусым - жоспарлау сценарийі; ағымдағы - маусым барысындағы алдын ала мониторинг; аяқталған - толық өткен маусымды ретроспективті бағалау.","ru":"Следующий сезон - плановый сценарий; текущий - предварительный мониторинг по мере поступления данных; завершённый - ретроспективная оценка полного сезона.","en":"Next season is the planning scenario; current season is an in-season preliminary assessment; completed season is a retrospective full-season assessment."}[lang],
))
_today = date.today()
if season_mode == "next":
    calculation_year = _today.year + 1
    assessment_type = {"kk":"жоспарлы әлеуетті сценарий","ru":"плановый потенциальный сценарий","en":"prospective planning scenario"}[lang]
    climate_period_label = f"04-09 / {calculation_year} ({ {'kk':'тарихи климаттық профиль','ru':'исторический климатический профиль','en':'historical climate profile'}[lang] })"
elif season_mode == "current":
    calculation_year = _today.year
    assessment_type = {"kk":"алдын ала ағымдағы бағалау","ru":"предварительная текущая оценка","en":"preliminary current-season assessment"}[lang]
    climate_period_label = f"01.04.{calculation_year}-30.09.{calculation_year}"
else:
    calculation_year = _today.year if _today > date(_today.year, 9, 30) else _today.year - 1
    assessment_type = {"kk":"ретроспективті бағалау","ru":"ретроспективная оценка","en":"retrospective assessment"}[lang]
    climate_period_label = f"01.04.{calculation_year}-30.09.{calculation_year}"

st.sidebar.caption({
    "kk":f"Есептік жыл: {calculation_year}. Ашық алқаптағы дақылдар үшін базалық климаттық терезе - сәуір-қыркүйек.",
    "ru":f"Расчётный год: {calculation_year}. Для культур открытого грунта базовое климатическое окно - апрель-сентябрь.",
    "en":f"Calculation year: {calculation_year}. The baseline climate window for open-field crops is April-September.",
}[lang])

# The crop/livestock comparison uses its own annual scenario accounting, so
# it cannot inherit the crop-specific area, irrigation meter, or FAO-56 widgets.
# Keep existing modes, report basket and session-wide language/district intact.
if mode_key == 'mode6':
    from core.mixed_farm_ui import render_mixed_mode
    render_mixed_mode(lang=lang, district=district,
        district_title=district_label(district), assessment_year=calculation_year,
        render_export_panel=render_export_panel)
    st.markdown('<div id="qunar-page-bottom"></div>', unsafe_allow_html=True)
    st.stop()

centroids = load_centroids()
default_lat, default_lon = centroids[district]

# State
st.session_state.setdefault("field_lat", default_lat)
st.session_state.setdefault("field_lon", default_lon)
st.session_state.setdefault("field_geojson", None)
st.session_state.setdefault("polygon_area_ha", None)
st.session_state.setdefault("field_locked", False)
st.session_state.setdefault("detected_map_district", None)
st.session_state.setdefault("district_for_location", district)

if st.session_state["district_for_location"] != district and not st.session_state["field_locked"]:
    st.session_state.field_lat = default_lat
    st.session_state.field_lon = default_lon
    st.session_state.field_geojson = None
    st.session_state.polygon_area_ha = None
    st.session_state.district_for_location = district


location_source = q_radio(
    t.get("location_source", {"kk":"Геодерек көзі","ru":"Источник геоданных","en":"Geodata source"}[lang]),
    ["district", "map"],
    format_func=lambda x: t.get("location_district", {"kk":"Таңдалған аудан бойынша есептеу","ru":"Считать по выбранному району","en":"Calculate by selected district"}[lang]) if x == "district" else t.get("location_map", {"kk":"Картадағы контур бойынша есептеу","ru":"Считать по контуру на карте","en":"Calculate by map polygon"}[lang]),
    horizontal=True,
)
st.caption(t.get("location_note", ""))

if st.button(t.get("clear_map", {"kk":"Картаны тазалау / контурды өшіру","ru":"Очистить карту / сбросить контур","en":"Clear map / reset boundary"}[lang])):
    st.session_state.field_lat = default_lat
    st.session_state.field_lon = default_lon
    st.session_state.field_geojson = None
    st.session_state.polygon_area_ha = None
    st.session_state.field_locked = False
    st.session_state.detected_map_district = None
    st.success(t.get("clear_map_done", {"kk":"Карта контуры тазаланды.","ru":"Контур карты очищен.","en":"Map boundary cleared."}[lang]))

use_map = q_toggle(t["map_toggle"], value=False, help=t["map_help"], disabled=(location_source == "district"))
st.caption(t["polygon_help"])

if not use_map or location_source == "district":
    # Old map geometry is kept only for possible manual recovery, but is not used for calculations.
    calc_lat, calc_lon = default_lat, default_lon
    calc_geojson = None
    calc_polygon_area = None
else:
    calc_lat, calc_lon = st.session_state.field_lat, st.session_state.field_lon
    calc_geojson = st.session_state.field_geojson
    calc_polygon_area = st.session_state.polygon_area_ha

if use_map and location_source == "map":
    @st.fragment
    def field_map_fragment():
        import folium
        from folium.plugins import Draw
        from streamlit_folium import st_folium
        from core.geo import polygon_area_hectares, representative_point

        st.subheader(t["map"])
        m = folium.Map(
            location=[st.session_state.field_lat, st.session_state.field_lon],
            zoom_start=11, control_scale=True, prefer_canvas=True, tiles="OpenStreetMap",
        )
        try:
            folium.GeoJson(
                boundary_geojson(),
                name="Turkestan districts",
                style_function=lambda _: {"fillOpacity": 0.03, "weight": 1.2},
                tooltip=folium.GeoJsonTooltip(fields=["name", "name_kk", "coderayon"], aliases=["RU", "KZ", "KATO"]),
            ).add_to(m)
        except Exception:
            pass
        Draw(
            export=False,
            draw_options={
                "polyline": False, "polygon": True, "rectangle": True,
                "circle": False, "marker": False, "circlemarker": False,
            },
            edit_options={"edit": True, "remove": True},
        ).add_to(m)
        map_data = st_folium(
            m, height=360, use_container_width=True,
            returned_objects=["last_active_drawing"], key=f"field-map-{district}",
        )
        last = map_data.get("last_active_drawing") if map_data else None
        if not last or not last.get("geometry"):
            return

        g = last["geometry"]
        if g.get("type") in ("Polygon", "MultiPolygon"):
            try:
                area = polygon_area_hectares(g)
                lat, lon = representative_point(g)
                st.session_state.polygon_area_ha = area
                st.session_state.field_lat = lat
                st.session_state.field_lon = lon
                st.session_state.field_geojson = g
                st.session_state.field_locked = True
                st.success(f"{t['map_area']}: {area:.2f} {'га' if lang != 'en' else 'ha'}")
            except Exception as exc:
                st.warning(str(exc))

    field_map_fragment()

# Re-read geometry after the map fragment and determine the administrative unit from polygons.
if location_source == "map" and use_map:
    calc_lat, calc_lon = st.session_state.field_lat, st.session_state.field_lon
    calc_geojson = st.session_state.field_geojson
    calc_polygon_area = st.session_state.polygon_area_ha
    official_match = detect_polygon(calc_geojson) if calc_geojson else detect_point(calc_lat, calc_lon)
else:
    calc_lat, calc_lon = default_lat, default_lon
    calc_geojson = None
    calc_polygon_area = None
    official_match = None

map_district = official_match.get("district") if official_match else None
map_district_share = official_match.get("share") if official_match else None
used_district = map_district if (location_source == "map" and map_district) else district

# Map geometry and scope must exist on every rerun, even without a drawn map.
# The input-side choice is required BEFORE report_payload is assembled.
polygon_area = calc_polygon_area
polygon_scope = "calculation_plot"

area_input_label = ({"ru":"Общая площадь посевов для оптимизации, га",
                     "kk":"Оңтайландырылатын егістік алқаптың жалпы ауданы, га",
                     "en":"Total cropping area to optimize, ha"}[lang]
                    if mode_key == "mode4" else t["area"]) if mode_key != "mode5" else {
    "kk":"Жайылым / өндірістік жер алаңы, га",
    "ru":"Площадь пастбища / производственной территории, га",
    "en":"Pasture / production land area, ha",
}[lang]

# Separate the total holding from the plot actually assessed.  This is
# contextual metadata only: crop-water and production formulas still use area_ha.
# A zero TOTAL denotes "not entered" and is never treated as a 0-ha farm.
farm_total_area_ha = 0.0
plot_area_explanations = {
    "mode1": {
        "ru":"Это площадь участка под выбранной культурой, а не обязательно всего хозяйства. Например: хозяйство 100 га, подсолнечник 40 га - здесь 40 га.",
        "kk":"Бұл таңдалған дақылдың танап алаңы, барлық шаруашылықтың жері емес. Мысалы: шаруашылық 100 га, күнбағыс 40 га - мұнда 40 га.",
        "en":"Area of the selected crop, not necessarily the whole farm. Example: 100 ha farm with 40 ha sunflower - enter 40 ha here.",
    },
    "mode2": {
        "ru":"Площадь участка, для которого проверяется выбранная культура. Не вводите общую площадь разных культур.",
        "kk":"Таңдалған дақыл тексерілетін танап алаңы. Әртүрлі дақылдар өскен барлық жерді енгізбеңіз.",
        "en":"Area of the plot being checked for this crop, not the whole mixed-crop farm.",
    },
    "mode3": {
        "ru":"Площадь участка, для которого QŪNAR сравнит возможные культуры. Это не вся территория смешанного хозяйства, если анализируется отдельное поле.",
        "kk":"QŪNAR дақылдарды салыстыратын танаптың алаңы. Бұл аралас шаруашылықтың барлық жері емес.",
        "en":"Area of the plot for comparing candidate crops, not necessarily the total holding.",
    },
    "mode4": {
        "ru":"Это общая площадь посевов, которую оптимизатор распределяет между культурами. Пастбища и строения сюда не входят.",
        "kk":"Оңтайландыру дақылдарға бөлетін егістік жердің жалпы алаңы. Жайылым мен ғимарат кірмейді.",
        "en":"Total arable cropping area to allocate across crops; exclude pasture and buildings.",
    },
    "mode5": {
        "ru":"Это площадь пастбища или территории, относящейся к рассматриваемому животноводству, не вся площадь предприятия.",
        "kk":"Бұл қарастырылатын мал шаруашылығына арналған жайылым немесе өндірістік жер; бүкіл кәсіпорын аумағы емес.",
        "en":"Pasture or land assigned to livestock, not necessarily the entire farm holding.",
    },
}
with st.container():
    c1, c2, c3 = st.columns(3)
    with c1:
        if mode_key in ("mode1", "mode2", "mode3", "mode5"):
            farm_total_area_ha = q_number_input(
                {"ru":"Общая площадь хозяйства, га (необязательно)",
                 "kk":"Шаруашылықтың жалпы аумағы, га (міндетті емес)",
                 "en":"Total farm area, ha (optional)"}[lang],
                min_value=0.0,
                value=float(st.session_state.get("qunar_farm_total_area_saved", 0.0)),
                step=0.5, key="qunar_total_farm_area_widget",
                help={"ru":"Вся земля предприятия: поля, пастбища и другая территория. 0 означает, что площадь не указана; это не нулевая площадь.",
                      "kk":"Кәсіпорынның барлық жері: танап, жайылым және басқа жерлер. 0 - енгізілмеген.",
                      "en":"All land of the holding, including fields and pasture. 0 means not provided."}[lang],
            )
            st.session_state["qunar_farm_total_area_saved"] = float(farm_total_area_ha)
            st.caption({"ru":"Справочная общая площадь. Не заменяет площадь выбранного участка и не умножает нормы расхода.",
                        "kk":"Бұл жалпы аумақ тек ақпарат үшін. Дақыл танабының алаңын алмастырмайды.",
                        "en":"Holding-level context only; does not replace the selected plot area or scale crop inputs."}[lang])
        # A crop plot, the total arable structure and livestock pasture are
        # distinct areas. Save per mode across Streamlit widget destruction.
        _is_crop_assessment = mode_key in ('mode1', 'mode2')
        _area_saved_key = 'qunar_crop_saved_area' if _is_crop_assessment else 'qunar_saved_area_'+mode_key
        _area_widget_key = 'qunar_area_widget_crop' if _is_crop_assessment else 'qunar_area_widget_'+mode_key
        area_ha = q_number_input(area_input_label, min_value=0.1,
                                 value=float(st.session_state.get(_area_saved_key, 10.0)),
                                 step=0.5, key=_area_widget_key,
                                 help=t["declared_area_help"])
        st.session_state[_area_saved_key] = float(area_ha)
        st.caption(plot_area_explanations[mode_key][lang])
        if farm_total_area_ha > 0 and area_ha > farm_total_area_ha:
            st.error({"ru":"Площадь выбранного участка превышает общую площадь хозяйства. Проверьте значения перед расчётом.",
                      "kk":"Таңдалған жер алаңы шаруашылықтың жалпы аумағынан үлкен. Екі мәнді тексеріңіз.",
                      "en":"Selected plot exceeds total farm area. Check both entries before calculating."}[lang])
            st.stop()
    with c2:
        available_water_label = t["water"] if mode_key != "mode5" else {
            "kk":"Жылдық қолжетімді су көлемі, м³",
            "ru":"Доступный годовой объем воды, м³",
            "en":"Available annual water volume, m³",
        }[lang]
        _water_budget_crop = mode_key in ('mode1', 'mode2')
        _water_budget_key = ('qunar_crop_available_water_widget' if _water_budget_crop
                             else 'qunar_available_water_'+mode_key)
        available_water = q_number_input(
            available_water_label, min_value=0.0,
            value=float(_crop_saved_value('available_water', 0.0)) if _water_budget_crop else float(st.session_state.get('qunar_saved_water_budget_'+mode_key, _crop_saved_value('available_water', 0.0) if mode_key == 'mode3' else 0.0)),
            step=1000.0, help=t["available_water_note"], key=_water_budget_key,
        )
        st.session_state['qunar_saved_water_budget_'+mode_key] = float(available_water)
        if _water_budget_crop:
            _crop_remember_value('available_water', float(available_water))
            st.caption({
                'ru':'Здесь лимит воды именно для анализируемого участка. Если известен только общий лимит всего хозяйства и не установлено, сколько доступно этой культуре, оставьте 0 (= неизвестно). Не распределяйте общий лимит автоматически по гектарам.',
                'kk':'Мұнда тек қарастырылатын танапқа қолжетімді су лимитін енгізіңіз. Бүкіл шаруашылықтың ғана лимиті белгілі болса, 0 қалдырыңыз (= белгісіз).',
                'en':'Enter water available to this assessed plot. If only the whole-farm water allowance is known and no crop allocation exists, leave 0 (= unknown). Do not apportion by area automatically.',
            }[lang])
    with c3:
        st.caption(t["nasa_auto_note"])
        if user_level == "farmer":
            st.caption(t["wapor_basic_note"])
            use_wapor = False
        else:
            use_wapor = st.checkbox(t["wapor_toggle"], value=True)

    if polygon_area and farm_total_area_ha > 0 and mode_key in ("mode1", "mode2", "mode3", "mode5"):
        polygon_scope = q_radio(
            {"ru":"Что обозначает нарисованный контур карты?",
             "kk":"Картадағы сызылған контур нені білдіреді?",
             "en":"What does the drawn map polygon represent?"}[lang],
            ["calculation_plot", "whole_farm"],
            format_func=lambda x: ({
                "calculation_plot":{"ru":"Анализируемый участок (культура / пастбище)","kk":"Қарастырылатын танап немесе жайылым","en":"Assessed plot (crop / pasture)"},
                "whole_farm":{"ru":"Всё хозяйство (включая другие участки)","kk":"Бүкіл шаруашылық (басқа учаскелермен)","en":"Entire farm (including other plots)"},
            }[x][lang]), key="qunar_map_area_scope",
            help={"ru":"Если контур охватывает 100 га всего хозяйства, а культура занимает 40 га, выберите «Всё хозяйство». QŪNAR сравнит контур со 100 га, а воду культуры рассчитает на 40 га.",
                  "kk":"Контур жалпы аумақты көрсетсе, «Бүкіл шаруашылық» таңдаңыз; дақыл шығыны тек танап алаңына есептеледі.",
                  "en":"Choose Entire farm for a whole-holding polygon; crop resources still use the selected plot area."}[lang],
        )
    crop = None
    if mode_key in ('mode1', 'mode2'):
        _crop_options = list(check_crop_codes())
        _crop_default = st.session_state.get('qunar_last_assessed_crop', _crop_options[0])
        crop = q_selectbox(
            t['crop'], _crop_options, format_func=lambda c: extended_crop_label(c, lang),
            index=_crop_options.index(_crop_default) if _crop_default in _crop_options else 0,
            key='qunar_assessed_crop_widget', on_change=_on_crop_changed,
        )
        # Handle first render or a mode transition without replacing saved inputs.
        st.session_state['qunar_last_assessed_crop'] = crop
        st.caption({
            'ru':'Нормы воды, агротехнологии и урожайность относятся к этой культуре и площади её участка. Они не являются нормами всего хозяйства. Если расход известен только по общему счётчику, укажите это ниже в «Границы учёта».',
            'kk':'Су, технология және өнімділік нормативтері осы дақыл мен оның танап алаңына қатысты. Жалпы шаруашылық есептегішін бөлек көрсетіңіз.',
            'en':'Crop water, production and yield references apply only to this crop and its assessed plot, not the entire holding. Mark whole-farm meter readings below.',
        }[lang])
        if user_level in ('specialist', 'researcher'):
            _crop_norm_note = default_water_requirement(used_district, crop, 'unknown')
            st.caption({
                'ru':f'Справочная норма: {_crop_norm_note.m3_ha:,.0f} м³/га, только для выбранной культуры. Источник: {_crop_norm_note.source_label}. Это не измеренный расход.',
                'kk':f'Анықтамалық норма: {_crop_norm_note.m3_ha:,.0f} м³/га, тек таңдалған дақыл үшін. Дереккөз: {_crop_norm_note.source_label}. Бұл нақты өлшеу емес.',
                'en':f'Crop-specific reference: {_crop_norm_note.m3_ha:,.0f} m³/ha. Source: {_crop_norm_note.source_label}. This is not measured consumption.',
            }[lang])
        if st.session_state.pop('qunar_crop_inputs_reset_notice', False):
            st.info({'ru':'Культура изменена: сброшены только показатели выбранной культуры. Общая площадь хозяйства, район, язык и другие режимы сохранены.',
                     'kk':'Дақыл өзгерді: осы дақылдың көрсеткіштері ғана тазартылды. Жалпы аумақ, аудан және тіл сақталды.',
                     'en':'Crop changed: only crop-specific inputs were reset; farm area, district and language were preserved.'}[lang])

    livestock_species = "Cattle"
    livestock_heads = 0.0
    livestock_fodder_t = 0.0
    livestock_feed_source = "unknown"
    livestock_production_amount = 0.0
    livestock_production_kind = "meat_tonnes"
    if mode_key == "mode5":
        st.markdown("#### " + {"kk":"Мал шаруашылығының өндірістік профилі","ru":"Производственный профиль животноводства","en":"Livestock production profile"}[lang])
        l1,l2,l3,l4 = st.columns(4)
        with l1:
            livestock_species = q_selectbox(
                {"kk":"Мал түрі","ru":"Вид животных","en":"Livestock type"}[lang],
                SPECIES,
                format_func=lambda x: SPECIES_LABELS[lang][x],
            )
        with l2:
            livestock_heads = q_number_input(
                {"kk":"Мал саны, бас","ru":"Поголовье, голов","en":"Number of animals, head"}[lang],
                min_value=0.0, value=0.0, step=10.0,
                help={
                    "kk":"0 қалдырылса, шаруашылықтағы мал саны белгісіз болып қалады; аудан көрсеткіші бөлек анықтама ретінде беріледі.",
                    "ru":"Если оставить 0, поголовье хозяйства будет считаться неизвестным. Районные значения показываются отдельно только для сравнения.",
                    "en":"If left at 0, the farm herd remains unknown; district livestock counts are shown separately for context.",
                }[lang],
            )
        with l3:
            livestock_production_kind = q_selectbox(
                {"kk":"Өнім түрі","ru":"Вид продукции","en":"Product type"}[lang],
                PRODUCT_TYPES,
                index=PRODUCT_TYPES.index(DEFAULT_PRODUCT.get(livestock_species, "meat_tonnes")),
                format_func=lambda x: PRODUCT_LABELS[lang][x],
            )
        with l4:
            livestock_production_amount = q_number_input(
                ({"kk":"Жылдық өнім көлемі, мың дана", "ru":"Годовой объём продукции, тыс. шт.", "en":"Annual production volume, thousand pieces"}[lang]
                 if livestock_production_kind == "thousand_eggs" else
                 {"kk":"Жылдық өнім көлемі, т", "ru":"Годовой объём продукции, т", "en":"Annual production volume, t"}[lang]),
                min_value=0.0, value=0.0, step=1.0,
                help={
                    "kk":"0 мәні нақты өнім көлемі белгісіз екенін білдіреді; аймақтық анықтамалық өнімділік бөлек көрсетіледі.",
                    "ru":"0 означает, что фактический выпуск неизвестен; региональный ориентир производительности будет показан отдельно.",
                    "en":"0 means observed production is unknown; a regional productivity reference is shown separately.",
                }[lang],
            )

        livestock_feed_source = q_selectbox(
            {"kk":"Жемшөп қоры туралы дерек","ru":"Данные о годовом запасе кормов","en":"Annual feed-supply data"}[lang],
            ["unknown", "own"],
            format_func=lambda x: {
                "unknown":{"kk":"Білмеймін / анықтамалық қажеттілікті есептеу","ru":"Не знаю / рассчитать справочную потребность","en":"Unknown / calculate reference requirement"}[lang],
                "own":{"kk":"Өз дерегімді енгізу","ru":"Ввести свои данные","en":"Enter my data"}[lang],
            }[x],
        )
        if livestock_feed_source == "own":
            livestock_fodder_t = q_number_input(
                {"kk":"Жылдық жемшөп қоры, т құрғақ зат","ru":"Годовой запас кормов, т сухого вещества","en":"Annual feed supply, t dry matter"}[lang],
                min_value=0.0, value=0.0, step=1.0,
            )
        st.caption({
            "kk":"Су мен жемшөптің анықтамалық қажеттілігі мал түріне және температураға байланысты коэффициенттермен автоматты есептеледі. Белгісіз нақты мәндер нөл ретінде түсіндірілмейді.",
            "ru":"Справочная потребность в воде и кормах рассчитывается автоматически по виду животных и температуре. Неизвестные фактические значения не трактуются как нулевое потребление.",
            "en":"Reference water and feed requirements are calculated automatically from species and temperature. Unknown observed values are not treated as zero use.",
        }[lang])

    # Interface detail levels change both the amount of input and the amount of model detail shown.
    # Basic: essential operational inputs. Advanced: technologies, tariffs and scenarios.
    # Research: Advanced + model sources, validation and satellite diagnostics.
    water_used = 0.0
    reuse = 0.0
    energy = 0.0
    grid_energy_input_label = {
        'ru':'Потребление электричества из сети, кВт·ч (0 = неизвестно)',
        'kk':'Желілік электр энергиясын тұтыну, кВт·сағ (0 = белгісіз)',
        'en':'Purchased grid electricity, kWh (0 = unknown)',
    }[lang]
    ef = float(DEFAULT_EF_KZ_KGCO2_PER_KWH)
    irrigation_type = "unknown"
    water_meter = False
    soil_sensors = False
    efficient_pump = False
    current_solar = 0.0
    target_solar = float(DEFAULT_GREEN_SHARE_TARGET)
    electricity_tariff = float(DEFAULT_ELECTRICITY_TARIFF_KZT_KWH)
    # Historical QUNAR 0.845 KZT/m³ applied only to Arys operator in a prior period.
    # Use the published 2026 national supplier gravity price strictly as a
    # labelled ILLUSTRATIVE scenario unless the user confirms a contract/provider.
    water_tariff = REGIONAL_TARIFF_REFERENCES['kazvodkhoz_irrigation_gravity_2026'].value_kzt_unit
    electricity_tariff_doc = None
    water_tariff_doc = None
    _tariff_water_ref = 'custom'  # basic and livestock modes have no supplier selector
    water_saving_target = float(DEFAULT_WATER_SAVING_TARGET)
    investment = 0.0
    seasons_per_year = 1.0
    expected_yield_c_ha = 0.0
    selling_price_kzt_t = 0.0
    selling_price_source = ""
    variable_cost_kzt_ha = 0.0
    variable_cost_source = ""
    irrigation_compare_enabled = False
    irrigation_target = "drip"
    irrigation_yield_change_pct = 0.0
    irrigation_evidence = ""
    irrigation_extra_cost = 0.0
    irrigation_extra_energy = 0.0
    # Optional environmental observations use None for "unknown".
    # A measured zero remains a valid observation and is therefore distinct from missing data.
    pesticide_kg_ha = None
    salinized_share_pct = None
    pasture_degraded_share_pct = None

    if mode_key == "mode5":
        st.markdown("#### " + {"kk":"Мал шаруашылығы ресурстары","ru":"Ресурсы животноводства","en":"Livestock resources"}[lang])
        lr1, lr2 = st.columns(2)
        with lr1:
            water_used = q_number_input(
                {"kk":"Нақты жылдық су тұтынуы, м³","ru":"Фактическое годовое водопотребление, м³","en":"Observed annual water use, m³"}[lang],
                min_value=0.0, value=0.0, step=100.0,
            )
        with lr2:
            energy = q_number_input(
                {"kk":"Желіден алынған электр энергиясы, кВт·сағ/жыл (0 = белгісіз)","ru":"Электроэнергия из сети, кВт·ч/год (0 = неизвестно)","en":"Purchased grid electricity, kWh/year (0 = unknown)"}[lang],
                min_value=0.0, value=0.0, step=100.0,
            )
        if user_level == "researcher":
            ef = q_number_input(t["ef"], min_value=0.0, value=float(DEFAULT_EF_KZ_KGCO2_PER_KWH), step=0.001)
            st.caption(t["ef_source"])
        else:
            ef = float(DEFAULT_EF_KZ_KGCO2_PER_KWH)
        st.caption({
            "kk":"0 нақты нөл ретінде қабылданбайды: мұндай жағдайда QŪNAR фактілік тұтынуды белгісіз деп сақтап, су мен жемшөптің анықтамалық қажеттілігін бөлек есептейді.",
            "ru":"Значение 0 здесь означает отсутствие фактических данных. QŪNAR сохраняет его как неизвестное наблюдение и отдельно рассчитывает справочную потребность в воде и кормах.",
            "en":"A value of 0 means observed data are unavailable. QŪNAR keeps the observation unknown and calculates reference water and feed requirements separately.",
        }[lang])
    elif user_level == "farmer":
        st.markdown("#### " + {"kk":"Негізгі шаруашылық деректері","ru":"Основные данные хозяйства","en":"Essential farm data"}[lang])
        b1,b2,b3=st.columns(3)
        with b1:
            water_used = q_number_input(t["water_used"], min_value=0.0,
                value=float(_crop_saved_value('water_used', 0.0)) if mode_key in ('mode1','mode2') else 0.0,
                step=1000.0, key='qunar_crop_water_widget' if mode_key in ('mode1','mode2') else 'qunar_water_'+mode_key)
            if mode_key in ('mode1','mode2'): _crop_remember_value('water_used', float(water_used))
        with b2:
            energy = q_number_input(grid_energy_input_label, min_value=0.0,
                value=float(_crop_saved_value('energy', 0.0)) if mode_key in ('mode1','mode2') else 0.0,
                step=100.0, key='qunar_crop_energy_widget' if mode_key in ('mode1','mode2') else 'qunar_energy_'+mode_key)
            if mode_key in ('mode1','mode2'): _crop_remember_value('energy', float(energy))
        with b3:
            irrigation_type = q_selectbox(
                t["irrigation_type"], ["unknown","furrow","sprinkler","drip","mixed"],
                format_func=lambda x:{"unknown":t["irrigation_unknown"],"furrow":t["irrigation_furrow"],"sprinkler":t["irrigation_sprinkler"],"drip":t["irrigation_drip"],"mixed":t["irrigation_mixed"]}[x],
                index=['unknown','furrow','sprinkler','drip','mixed'].index(_crop_saved_value('irrigation_type', 'unknown')),
                key='qunar_crop_irrigation_widget',
            )
            _crop_remember_value('irrigation_type', irrigation_type)
        st.caption({"kk":"Қалған техникалық параметрлер анықтамалық сценариймен есептеледі. Нақты тарифтер, өлшеу сенсорлары, сорғы және сценарийлер үшін «Кеңейтілген» деңгейді таңдаңыз.","ru":"Остальные технические параметры рассчитываются по справочному сценарию. Для точных тарифов, датчиков, насоса и сценариев выберите «Расширенный» уровень.","en":"Other technical parameters use the reference scenario. Choose Advanced for exact tariffs, sensors, pump and what-if settings."}[lang])
        st.caption({"kk":"Өсімдік шаруашылығы үшін енгізілетін нақты су мен энергия мәндері толық өндірістік циклге жатады; оларды сәуір-қыркүйек климаттық терезесімен шектемеңіз.","ru":"Для растениеводства фактические вода и энергия относятся ко всему производственному циклу культуры; ограничивать эти значения только апрелем-сентябрём не нужно.","en":"For crops, observed water and energy refer to the full production cycle; do not restrict these inputs to the April-September climate window."}[lang])
    else:
        with st.expander(t["resource_inputs"], expanded=True):
            a,b=st.columns(2)
            with a:
                water_used=q_number_input(t['water_used'],min_value=0.0,
                    value=float(_crop_saved_value('water_used',0.0)) if mode_key in ('mode1','mode2') else 0.0,
                    step=1000.0,key='qunar_crop_water_widget' if mode_key in ('mode1','mode2') else 'qunar_water_'+mode_key)
                if mode_key in ('mode1','mode2'): _crop_remember_value('water_used',float(water_used))
                reuse=q_number_input(t['reuse'],min_value=0.0,max_value=100.0,value=0.0,step=0.1,
                    key='qunar_crop_reuse_widget' if mode_key in ('mode1','mode2') else 'qunar_reuse_'+mode_key)
                irrigation_type=q_selectbox(t['irrigation_type'],['unknown','furrow','sprinkler','drip','mixed'],
                    format_func=lambda x:{'unknown':t['irrigation_unknown'],'furrow':t['irrigation_furrow'],'sprinkler':t['irrigation_sprinkler'],'drip':t['irrigation_drip'],'mixed':t['irrigation_mixed']}[x],
                    index=['unknown','furrow','sprinkler','drip','mixed'].index(_crop_saved_value('irrigation_type','unknown')) if mode_key in ('mode1','mode2') else 0,
                    key='qunar_crop_irrigation_widget' if mode_key in ('mode1','mode2') else 'qunar_irrigation_'+mode_key)
                if mode_key in ('mode1','mode2'): _crop_remember_value('irrigation_type',irrigation_type)
                water_meter=st.checkbox(t['has_water_meter'],value=False,
                    key='qunar_crop_meter_widget' if mode_key in ('mode1','mode2') else 'qunar_meter_'+mode_key)
                soil_sensors=st.checkbox(t['has_soil_sensors'],value=False,
                    key='qunar_crop_soil_sensors_widget' if mode_key in ('mode1','mode2') else 'qunar_sensors_'+mode_key)
            with b:
                energy=q_number_input(grid_energy_input_label,min_value=0.0,
                    value=float(_crop_saved_value('energy',0.0)) if mode_key in ('mode1','mode2') else 0.0,
                    step=100.0,key='qunar_crop_energy_widget' if mode_key in ('mode1','mode2') else 'qunar_energy_'+mode_key)
                if mode_key in ('mode1','mode2'): _crop_remember_value('energy',float(energy))
                efficient_pump=st.checkbox(t['has_efficient_pump'],value=False,
                    key='qunar_crop_efficient_pump_widget' if mode_key in ('mode1','mode2') else 'qunar_pump_eff_'+mode_key)
                current_solar=q_number_input(t['current_solar'],min_value=0.0,max_value=100.0,value=0.0,step=0.1,
                    key='qunar_crop_solar_widget' if mode_key in ('mode1','mode2') else 'qunar_solar_'+mode_key)
                target_solar=q_number_input(t['target_solar'],min_value=0.0,max_value=100.0,value=float(DEFAULT_GREEN_SHARE_TARGET),step=0.5,
                    key='qunar_crop_target_solar_widget' if mode_key in ('mode1','mode2') else 'qunar_target_solar_'+mode_key)
            st.caption({"kk":"Ресурстық енгізулер толық өндірістік циклге жатады: егіс алдындағы дайындық/себу, өсіру кезеңі және өнім жинау. Сәуір-қыркүйек шекарасы тек ML климаттық белгілеріне қолданылады.","ru":"Ресурсные вводы относятся к полному производственному циклу: предпосевная подготовка/посев, выращивание и уборка. Граница апрель-сентябрь применяется только к климатическим признакам ML.","en":"Resource inputs cover the full production cycle: pre-sowing preparation/sowing, crop growth and harvest. The April-September boundary applies only to ML climate features."}[lang])
            st.markdown("##### "+t["econ_block"])
            st.caption(t["whatif_help"])
            p1,p2,p3,p4=st.columns(4)
            with p1:
                electricity_tariff=q_number_input(t["electricity_tariff"],min_value=0.0,value=float(DEFAULT_ELECTRICITY_TARIFF_KZT_KWH),step=0.1)
            with p2:
                water_tariff=q_number_input(t["water_tariff"],min_value=0.0,value=REGIONAL_TARIFF_REFERENCES['kazvodkhoz_irrigation_gravity_2026'].value_kzt_unit,step=0.01)
            _tariff_energy_ref=st.selectbox(
                {'ru':'Основание тарифа на электроэнергию', 'kk':'Электр энергиясы тарифінің негізі',
                 'en':'Electricity tariff basis'}[lang],
                ['custom','electric_retail_commercial_2025_11_exvat','electric_retail_commercial_2025_11_invat','electric_retail_commercial_2025_vat','electric_retail_food_manufacturer_2025_vat'],
                format_func=lambda k: {
                    'custom':{'ru':'Собственный тариф / сценарий', 'kk':'Өз тарифі / сценарий', 'en':'Own tariff / scenario'},
                    'electric_retail_commercial_2025_11_exvat':{'ru':'Ноябрь 2025, бизнес, без НДС: 41,06 (справочно)', 'kk':'2025 қараша, бизнес, ҚҚС-сыз: 41,06 (анықтамалық)', 'en':'November 2025 business ex VAT: 41.06 (reference)'},
                    'electric_retail_commercial_2025_11_invat':{'ru':'Ноябрь 2025, бизнес, с НДС: 45,9872 (справочно)', 'kk':'2025 қараша, бизнес, ҚҚС-пен: 45,9872 (анықтамалық)', 'en':'November 2025 business incl VAT: 45.9872 (reference)'},
                    'electric_retail_commercial_2025_vat':{'ru':'Архивный тариф до ноября 2025', 'kk':'2025 қарашаға дейінгі тарихи тариф', 'en':'Historical pre-November 2025 tariff'},
                    'electric_retail_food_manufacturer_2025_vat':{'ru':'Туркестанская область: льготная категория производителя пищевых товаров, 2025', 'kk':'Түркістан: азық-түлік өндіруші санаты, 2025', 'en':'Turkestan: eligible food producer, 2025'},
                }[k][lang], key='tariff_basis_electricity')
            if _tariff_energy_ref != 'custom':
                electricity_tariff_doc = supplier_tariff(_tariff_energy_ref, provider_confirmed=True)
                electricity_tariff = electricity_tariff_doc.value_kzt_unit
                st.metric({'ru':'Расчётный тариф электроэнергии, тг/кВт·ч',
                           'kk':'Есептік электр тарифі, тг/кВт·сағ','en':'Reference electricity tariff, KZT/kWh'}[lang],
                          f'{electricity_tariff:.4f}')
            _water_tariff_options=['custom','kazvodkhoz_irrigation_gravity_2026',
                   'kazvodkhoz_irrigation_pumped_2026','saryagash_canal_2026',
                   'ordabasy_canal_2026','kazygurt_canal_2026',
                   'tolebi_canal_2026','kentau_canal_2026','turkestan_canal_2026']
            _tariff_water_ref=st.selectbox(
                {'ru':'Основание платы за подачу оросительной воды',
                 'kk':'Суармалы суды жеткізу ақысының негізі',
                 'en':'Irrigation water delivery tariff basis'}[lang],
                _water_tariff_options,
                format_func=lambda k: ({'ru':'Собственный тариф / сценарий','kk':'Өз тарифі / сценарий',
                    'en':'Own tariff / scenario'}[lang] if k=='custom'
                    else REGIONAL_TARIFF_REFERENCES[k].provider+' ('+({'gravity':{'ru':'самотёк','kk':'өздігінен ағу','en':'gravity'},'pumped':{'ru':'механизированная подача','kk':'сорғымен жеткізу','en':'pumped'},'canal':{'ru':'канал','kk':'арна','en':'canal'}}.get(k.split('_')[-2],{}).get(lang,k.split('_')[-2]))+')'),
                key='tariff_basis_water',
                help={'ru':'Это цена услуги по доставке 1 м³ воды. Самотечная подача и подача насосами стоят по-разному. Проверьте название поставщика в договоре. Если перекачка включена в тариф, не добавляйте те же насосные затраты повторно.',
                      'kk':'Бұл 1 м³ суды жеткізу қызметінің бағасы. Өздігінен ағу мен сорғымен жеткізу тарифтері әртүрлі. Келісімшарттағы жеткізушіні тексеріп, сорғы шығынын екі рет қоспаңыз.',
                      'en':'Delivery charge per m³. Gravity and pumped supply have different prices. Confirm the provider and avoid double counting supplier pumping.'}[lang])
            if _tariff_water_ref != 'custom':
                water_tariff_doc = supplier_tariff(_tariff_water_ref,provider_confirmed=True)
                water_tariff = water_tariff_doc.value_kzt_unit
                st.metric({'ru':'Расчётная плата за воду, тг/м³',
                           'kk':'Судың есептік ақысы, тг/м³', 'en':'Reference water tariff, KZT/m³'}[lang],
                          f'{water_tariff:.5f}')
            with p3:
                water_saving_target=q_number_input(t["water_saving_target"],min_value=0.0,max_value=100.0,value=float(DEFAULT_WATER_SAVING_TARGET),step=0.1)
            with p4:
                investment=q_number_input(t["investment"],min_value=0.0,value=0.0,step=100000.0)
            seasons_per_year=q_number_input(t["seasons_per_year"],min_value=1.0,value=1.0,step=1.0)
            if user_level == "researcher":
                st.markdown("##### " + {"kk":"Зерттеу параметрлері","ru":"Исследовательские параметры","en":"Research parameters"}[lang])
                ef=q_number_input(t["ef"],min_value=0.0,value=float(DEFAULT_EF_KZ_KGCO2_PER_KWH),step=0.001)
                st.caption(t["ef_source"])
                st.caption(t["tariff_source_note"])
                st.caption(t["decimal_note"])
            else:
                ef=float(DEFAULT_EF_KZ_KGCO2_PER_KWH)
                st.caption(t["tariff_note"])

        st.caption(t["api_offline"])

    _grid_ef_source = st.selectbox(
        {'ru':'Основание коэффициента сетевых выбросов (справочный расчёт)',
         'kk':'Желілік шығарындылар коэффициентінің негізі (анықтамалық есеп)',
         'en':'Grid emission factor basis (reference scenario)'}[lang],
        ['ember2025','ember2024','model_scenario'],
        format_func=lambda code: {'ember2025':{
            'ru':'Средняя генерация Казахстана, 2025 (данные Ember)',
            'kk':'Қазақстандағы орташа электр өндіру, 2025 (Ember)',
            'en':'Kazakhstan generation mix 2025 (Ember)'},
            'ember2024':{
            'ru':'Средняя генерация Казахстана, 2024 (данные Ember)',
            'kk':'Қазақстандағы орташа электр өндіру, 2024 (Ember)',
            'en':'Kazakhstan generation mix 2024 (Ember)'},
            'model_scenario':{
            'ru':'Сценарий QŪNAR / введённый коэффициент',
            'kk':'QŪNAR сценарийі / енгізілген коэффициент',
            'en':'QŪNAR assumption / user-entered factor'}}[code][lang],
        help={'ru':'Ember - международная аналитическая организация, публикующая данные об электроэнергетике. Здесь использован средний показатель выбросов CO₂ при выработке электричества в Казахстане, не измерение вашей фермы и не официальный договорной коэффициент.',
              'kk':'Ember - электр энергетикасы бойынша халықаралық деректерді жариялайтын зерттеу ұйымы. Көрсеткіш Қазақстан генерациясының орташа CO₂ шығарындылары, шаруашылықтың өлшемі емес.',
              'en':'Ember is an international energy-data research organisation. This is a national generation-average CO₂ figure, not a farm-specific or contract-specific emission factor.'}[lang],
        key='grid_ef_method')
    if _grid_ef_source in ('ember2025','ember2024'):
        ef = EMBer_KZ_GRID_GENERATION_CO2_KG_PER_KWH[int(_grid_ef_source[-4:])]
    if mode_key == "mode5":
        with st.expander({"kk":"Жайылымның экологиялық диагностикасы (міндетті емес)","ru":"Экологическая диагностика пастбища (необязательно)","en":"Pasture environmental diagnostics (optional)"}[lang], expanded=False):
            pasture_source = q_selectbox(
                {"kk":"Жайылым деградациясы туралы дерек","ru":"Данные о деградации пастбища","en":"Pasture-degradation data"}[lang],
                ["unknown", "own"],
                format_func=lambda x: {
                    "unknown":{"kk":"Білмеймін / дерек жоқ","ru":"Не знаю / данных нет","en":"Unknown / no data"}[lang],
                    "own":{"kk":"Өз дерегімді енгізу","ru":"Ввести свои данные","en":"Enter my data"}[lang],
                }[x],
            )
            if pasture_source == "own":
                pasture_degraded_share_pct = q_number_input(
                    {"kk":"Деградацияланған жайылым үлесі, %","ru":"Доля деградированного пастбища, %","en":"Degraded pasture share, %"}[lang],
                    min_value=0.0, max_value=100.0, value=0.0, step=1.0,
                )
            else:
                pasture_degraded_share_pct = None
            st.caption({
                "kk":"«Дерек жоқ» нөлдік деградацияны білдірмейді. 0% тек нақты өлшеу немесе бағалау бар кезде енгізіледі.",
                "ru":"«Данных нет» не означает нулевую деградацию. Значение 0% используется только при наличии фактической оценки.",
                "en":"No data does not mean zero degradation. Enter 0% only when an observed assessment supports it.",
            }[lang])
    elif mode_key in ("mode1","mode2","mode4"):
        with st.expander({"kk":"Экологиялық диагностика (міндетті емес)","ru":"Экологическая диагностика (необязательно)","en":"Environmental diagnostics (optional)"}[lang], expanded=False):
            ee1,ee2 = st.columns(2)
            with ee1:
                pesticide_source = q_selectbox(
                    {"kk":"Пестицид жүктемесі туралы дерек","ru":"Данные о пестицидной нагрузке","en":"Pesticide-load data"}[lang],
                    ["unknown", "own"],
                    format_func=lambda x: {
                        "unknown":{"kk":"Білмеймін / дерек жоқ","ru":"Не знаю / данных нет","en":"Unknown / no data"}[lang],
                        "own":{"kk":"Өз дерегімді енгізу","ru":"Ввести свои данные","en":"Enter my data"}[lang],
                    }[x],
                )
                if pesticide_source == "own":
                    pesticide_kg_ha = q_number_input(
                        {"kk":"Пестицид жүктемесі, кг/га","ru":"Пестицидная нагрузка, кг/га","en":"Pesticide load, kg/ha"}[lang],
                        min_value=0.0, value=0.0, step=0.01,
                    )
                else:
                    pesticide_kg_ha = None
            with ee2:
                salinity_source = q_selectbox(
                    {"kk":"Тұздану туралы дерек","ru":"Данные о засолении","en":"Salinity data"}[lang],
                    ["unknown", "own"],
                    format_func=lambda x: {
                        "unknown":{"kk":"Білмеймін / дерек жоқ","ru":"Не знаю / данных нет","en":"Unknown / no data"}[lang],
                        "own":{"kk":"Өз дерегімді енгізу","ru":"Ввести свои данные","en":"Enter my data"}[lang],
                    }[x],
                )
                if salinity_source == "own":
                    salinized_share_pct = q_number_input(
                        {"kk":"Тұзданған жер үлесі, %","ru":"Доля засоленной земли, %","en":"Salinized land share, %"}[lang],
                        min_value=0.0, max_value=100.0, value=0.0, step=1.0,
                    )
                else:
                    salinized_share_pct = None
            st.caption({
                "kk":"Белгісіз мәндер нөлге ауыстырылмайды және экологиялық қамту көрсеткішіне қосылмайды. Нөл тек нақты өлшенген нөл ретінде есептеледі.",
                "ru":"Неизвестные значения не заменяются нулями и не входят в показатель полноты экологических данных. Ноль учитывается только как фактически подтвержденное значение.",
                "en":"Unknown values are not replaced with zeros and are excluded from environmental data coverage. Zero is counted only when it is an observed value.",
            }[lang])
    if crop is not None:
        with st.expander({"kk":"Экономикалық контур (міндетті емес)","ru":"Экономический контур (необязательно)","en":"Economic contour (optional)"}[lang], expanded=False):
            st.caption({
                "kk":"Баға мен шығынды өз деректеріңізбен енгізіңіз. Өнімділік енгізілмесе, өткен үш күнтізбелік жылдың аудандық орташа мәні қолданылады (бар болса); ML жеке көрсетіледі.",
                "ru":"Укажите цену и затраты. Если урожайность хозяйства не введена, для маржи используется средняя урожайность культуры в районе за три предыдущих календарных года (если имеются данные). Random Forest показывается отдельно.",
                "en":"Enter the price and costs. If farm yield is not supplied, the economic calculation uses the district/crop historical mean over the preceding three calendar years (if available). ML remains separate."
            }[lang])
            ec1,ec2,ec3=st.columns(3)
            with ec1:
                expected_yield_c_ha=q_number_input({"kk":"Күтілетін өнімділік, ц/га","ru":"Ожидаемая урожайность, ц/га","en":"Expected yield, centners/ha"}[lang],min_value=0.0,value=0.0,step=1.0)
            with ec2:
                # Reference prices are annual *producer* prices from BNS RK. Never
                # silently estimate censored cells, infer prices for other crops,
                # or use a publication from the year being backtested.
                _bns_price = reference_producer_price(crop, as_of_year=calculation_year - 1)
                _using_bns_price = False
                if _bns_price is not None:
                    _using_bns_price = st.checkbox(
                        {"kk": f"БНС өңірлік бағасын қолдану ({_bns_price.year})",
                         "ru": f"Использовать справочную цену БНС ({_bns_price.year})",
                         "en": f"Use regional BNS reference price ({_bns_price.year})"}[lang],
                        value=(_bns_price.years_old <= 2),
                        key=f"bns_producer_price_{crop}_{calculation_year}",
                    )
                if _using_bns_price:
                    selling_price_kzt_t = float(_bns_price.price_kzt_t)
                    selling_price_source = _bns_price.source_label
                    st.metric({"kk":"Сату бағасы, тг/т", "ru":"Цена реализации, тг/т", "en":"Selling price, KZT/t"}[lang], f"{selling_price_kzt_t:,.0f}")
                    st.caption({"kk":f"БНС { _bns_price.year}: {_bns_price.product_label_ru}; ҚҚС-сыз. Бұл фермердің нақты бағасы да, болашақ баға болжамы да емес.",
                                "ru":f"БНС {_bns_price.year}: {_bns_price.product_label_ru}; без НДС. Это региональная историческая цена, не цена хозяйства и не прогноз будущей цены.",
                                "en":f"BNS {_bns_price.year}: {_bns_price.product_label_ru}; excl. VAT. Historical regional producer price, not the farm sale price or a future price forecast."}[lang])
                    if _bns_price.years_old > 1:
                        st.warning({"kk":"Соңғы жарияланған баға ескірген; сценарийге сақтықпен қолданыңыз.",
                                    "ru":"Последняя опубликованная цена устарела; используйте её для сценария с осторожностью.",
                                    "en":"The most recent published reference price is dated; use cautiously in scenarios."}[lang])
                else:
                    selling_price_kzt_t=q_number_input({"kk":"Сату бағасы, тг/т","ru":"Цена реализации, тг/т","en":"Selling price, KZT/t"}[lang],min_value=0.0,value=0.0,step=1000.0)
                    selling_price_source = {"kk":"Шаруашылық/пайдаланушы енгізген баға","ru":"Цена, введённая пользователем","en":"User-entered price"}[lang]
                    if _bns_price is None:
                        st.caption({"kk":"Бұл өнім үшін салыстырылатын өңірлік өндіруші бағасы жоқ; есепке қолданушы бағасы қажет.",
                                    "ru":"Для этой категории культуры сопоставимая опубликованная региональная цена отсутствует; требуется ввод пользователя.",
                                    "en":"There is no published regional producer price for this exact crop category; enter your own price."}[lang])
            with ec3:
                # A5: never infer costs from selling prices or out-of-force insurance norms.
                _other_cost_ref = reference_variable_cost(
                    crop, as_of_year=calculation_year - 1,
                    technology=irrigation_type if irrigation_type != 'unknown' else 'unspecified')
                _use_other_cost_ref = False
                if _other_cost_ref is not None:
                    _use_other_cost_ref = st.checkbox(
                        {"kk":"Жарияланған шығын анықтамасын қолдану", "ru":"Использовать подтверждённые справочные затраты", "en":"Use documented reference costs"}[lang],
                        value=False, key=f'cost_ref_{crop}_{calculation_year}')
                if _use_other_cost_ref:
                    variable_cost_kzt_ha = _other_cost_ref.other_variable_cost_kzt_ha
                    variable_cost_source = _other_cost_ref.source_label
                    st.metric({"kk":"Өзге айнымалы шығындар, тг/га", "ru":"Прочие переменные затраты, тг/га", "en":"Other variable costs, KZT/ha"}[lang],
                              f'{variable_cost_kzt_ha:,.0f}')
                    st.caption(variable_cost_source)
                else:
                    _cost_entry_mode = st.selectbox(
                        {"kk":"Шығындарды енгізу тәсілі", "ru":"Как ввести затраты", "en":"Cost entry method"}[lang],
                        ['total', 'items'],
                        format_func=lambda x: {
                            'total': {"kk":"Жалпы сома", "ru":"Общая сумма", "en":"Total amount"}[lang],
                            'items': {"kk":"Шығындар баптары", "ru":"По статьям", "en":"Itemized budget"}[lang],
                        }[x], key=f'cost_mode_{crop}_{calculation_year}')
                    if _cost_entry_mode == 'total':
                        variable_cost_kzt_ha = q_number_input(
                            {"kk":"Басқа айнымалы шығындар, тг/га", "ru":"Прочие переменные затраты, тг/га", "en":"Other variable costs, KZT/ha"}[lang],
                            min_value=0.0, value=0.0, step=10000.0)
                        if variable_cost_kzt_ha > 0:
                            variable_cost_source = {"kk":"Пайдаланушының сомасы", "ru":"Сумма, указанная пользователем", "en":"User-entered total"}[lang]
                    else:
                        st.caption({
                            'kk':'Көрсетілген алты бапты толтырыңыз. Нөл мәні тек шығын шынымен болмаған кезде жарамды.',
                            'ru':'Заполните шесть статей расходов на гектар. Ноль означает подтверждённое отсутствие статьи, а не неизвестные затраты.',
                            'en':'Fill six cost categories per hectare. Zero means confirmed no cost, not missing information.'
                        }[lang])
                        _cost_item_names = {
                            'seeds': {'kk':'Тұқым', 'ru':'Семена', 'en':'Seeds'},
                            'fertilizer': {'kk':'Тыңайтқыш', 'ru':'Удобрения', 'en':'Fertilizer'},
                            'crop_protection': {'kk':'Өсімдікті қорғау', 'ru':'Защита растений', 'en':'Crop protection'},
                            'diesel': {'kk':'Жанармай және ГСМ', 'ru':'Топливо и ГСМ', 'en':'Diesel and fuel'},
                            'labor': {'kk':'Еңбекақы', 'ru':'Оплата труда', 'en':'Labour'},
                            'other': {'kk':'Өзге айнымалы шығындар', 'ru':'Прочие затраты', 'en':'Other costs'},
                        }
                        _entered_cost_items = {}
                        for _cost_key in COST_FIELDS:
                            _entered_cost_items[_cost_key] = q_number_input(
                                _cost_item_names[_cost_key][lang] + ' (KZT/ha)',
                                min_value=0.0, value=0.0, step=1000.0,
                                key=f'cost_{crop}_{calculation_year}_{_cost_key}')
                        _items_confirmed = st.checkbox(
                            {"kk":"Растаймын: барлық баптар тексерілді; 0 нақты шығын жоқ екенін білдіреді.",
                             "ru":"Подтверждаю: все статьи проверены; ноль означает отсутствие расхода, а не пропущенные данные.",
                             "en":"I confirm all categories were checked; zero means no cost rather than missing data."}[lang],
                            value=False, key=f'cost_confirm_{crop}_{calculation_year}')
                        _item_total = itemized_variable_cost(entries=_entered_cost_items) if _items_confirmed else None
                        variable_cost_kzt_ha = _item_total or 0.0
                        if _item_total is not None:
                            variable_cost_source = {"kk":"Пайдаланушының баптар бойынша бюджеті", "ru":"Постатейный бюджет пользователя", "en":"User-entered itemized budget"}[lang]
                            st.metric({"kk":"Барлық шығын, тг/га", "ru":"Итого затрат, тг/га", "en":"Total costs, KZT/ha"}[lang], f'{_item_total:,.0f}')
            st.caption({"kk":"Су мен электр энергиясына төлемді енгізбеңіз, олар бөлек есептеледі.",
                        "ru":"Не включайте расходы на воду и электроэнергию: они учитываются отдельно. При отсутствии подтверждённых затрат маржа не рассчитывается.",
                        "en":"Exclude water and electricity costs; QŪNAR calculates them separately. Without evidenced costs, no contribution margin is shown."}[lang])
            if _other_cost_ref is None:
                st.caption({"kk":"Осы дақыл мен технология бойынша расталған облыстық шығындар анықтамасы жоқ.",
                            "ru":"Подтверждённого сопоставимого регионального среднего по затратам для этой культуры и технологии пока нет.",
                            "en":"No verified comparable regional cost reference for this crop and technology is currently available."}[lang])
            # Historical Kazakhstan cards are shown for audit ONLY; nominal old
            # amounts must never feed modern prices or contribution margin.
            _historic_candidates=historic_cost_mix(crop)
            if _historic_candidates:
                with st.expander({
                    'ru':'Документированные исторические затраты (НЕ текущая себестоимость)',
                    'kk':'Құжатталған тарихи шығындар (ағымдағы өзіндік құн ЕМЕС)',
                    'en':'Published historical cost cards (NOT current production costs)'
                }[lang],expanded=False):
                    _hist_rows=[{
                        '2004 agrozone':x['agrozone'],
                        'Technology':x['technology'],
                        'Historical total KZT/ha':float(x['total_cost_kzt_ha_2004']),
                        'Historical wages+fuel+seeds KZT/ha':float(x['wages_fuel_seeds_kzt_ha_2004'])
                    } for x in _historic_candidates]
                    st.dataframe(pd.DataFrame(_hist_rows),hide_index=True,use_container_width=True)
                    st.caption({'ru':'Нормативы РК за 2004 год, https://adilet.zan.kz/rus/docs/P040000839_. Суммы НЕ подставляются в маржу: исторические цены и полная разбивка воды/электроэнергии не сопоставимы с текущим расчётом.',
                        'kk':'2004 жылғы ҚР нормативтері. Бұл сомалар қазіргі маржаға қосылмайды: су мен электр шығындары толық бөлінбеген.',
                        'en':'Kazakhstan 2004 published cards. NOT applied to current contribution margin: nominal historical costs and water/electricity accounting are not comparable.'}[lang])
            # Historical normative cost cards are an optional baseline, never a current price.
            # The factor is user supplied; the historical norm has unspecified water/power share.
            if _historic_candidates and variable_cost_kzt_ha <= 0:
                st.caption({
                    'ru':'Доступна историческая база затрат РК 2004 года. Для расчёта современной маржи необходима сопоставимая постатейная смета хозяйства: индексирование всей суммы может повторно учесть воду и электричество.',
                    'kk':'2004 жылғы ҚР тарихи шығын базасы бар. Қазіргі маржаны есептеу үшін су мен электрді бөлек көрсететін нақты смета қажет.',
                    'en':'Kazakhstan 2004 cost cards are available, but their total cannot be indexed into present-day margin without an itemized water/electricity split.'}[lang])
            irrigation_compare_enabled = st.checkbox({"kk":"Суару технологиясын өзгерту сценарийін салыстыру","ru":"Сравнить сценарий смены типа орошения","en":"Compare an irrigation-switch scenario"}[lang], value=False)
            if irrigation_compare_enabled:
                irrigation_target = st.selectbox({"kk":"Ұсынылатын суару","ru":"Предлагаемый тип орошения","en":"Proposed irrigation type"}[lang], ["furrow", "sprinkler", "drip", "mixed"], format_func=lambda x: {
                    'furrow': {'ru': 'Бороздовой', 'kk': 'Бороздалы', 'en': 'Furrow'},
                    'sprinkler': {'ru': 'Дождевальный', 'kk': 'Жаңбырлатып', 'en': 'Sprinkler'},
                    'drip': {'ru': 'Капельный', 'kk': 'Тамшылатып', 'en': 'Drip'},
                    'mixed': {'ru': 'Смешанный', 'kk': 'Аралас', 'en': 'Mixed'},
                }[x][lang])
                irrigation_yield_change_pct = q_number_input({"kk":"Суарудан өнімділік өзгерісі, %","ru":"Изменение урожайности от орошения, %","en":"Irrigation yield change, %"}[lang], min_value=-100.0, max_value=200.0, value=0.0, step=1.0)
                irrigation_evidence = st.text_input({"kk":"Өнімділік әсерінің дереккөзі немесе жорамал","ru":"Источник или допущение для изменения урожайности","en":"Source or assumption for yield change"}[lang], value="", help={"kk":"Зерттеу, тәжірибе немесе шаруашылық дерегін көрсетіңіз; жорамал болса, оны нақты белгілеңіз.","ru":"Укажите исследование, эксперимент или данные хозяйства; явно обозначьте допущение.","en":"Specify study/experimental estimate, farm records, or explicitly label as an assumption"}[lang])
                irrigation_extra_cost = q_number_input({"kk":"Жаңа технологияның қосымша маусымдық шығындары, тг/га","ru":"Дополнительные сезонные расходы на технологию, тг/га","en":"Extra seasonal technology costs, KZT/ha"}[lang], min_value=0.0, value=0.0, step=1000.0)
                irrigation_extra_energy = q_number_input({"kk":"Энергия өзгерісі, кВт·сағ/га (+/-)","ru":"Изменение потребления энергии, кВт·ч/га (+/-)","en":"Change in energy use, kWh/ha (+/-)"}[lang], value=0.0, step=10.0)
                st.caption({"kk":"Бұл ML болжамы емес: өнімділік өзгерісі тек құжатталған сценарий. Инвестиция және амортизация қосымша маусымдық шығындарда есептелмесе, маржаға кірмейді.","ru":"Это отдельный сценарий, не прогноз ML. Без указанного источника расчёт не выполняется. Капвложения и амортизация учитываются только если включены в дополнительные сезонные расходы.","en":"A separate what-if, not an ML prediction. Source/assumption is required. Capital costs and depreciation are included only if entered as seasonal costs."}[lang])


    optimization_profile = "balanced"
    optimization_custom_climate_weight = None
    optimization_max_share = 0.40
    optimization_n_crops = 5
    optimization_temp_delta_c = 0.0
    optimization_precip_change_pct = 0.0
    optimization_water_budget_change_pct = 0.0
    if mode_key == "mode4" and user_level != "farmer":
        st.markdown("#### " + {"kk":"Оңтайландыру сценарийі","ru":"Сценарий оптимизации","en":"Optimization scenario"}[lang])
        op1, op2, op3 = st.columns(3)
        with op1:
            optimization_profile = q_selectbox(
                {"kk":"Басымдық","ru":"Приоритет","en":"Priority"}[lang],
                ["balanced", "climate", "resource", "survey_proxy", "custom"],
                format_func=lambda x: {
                    "balanced":{"kk":"Теңгерімді","ru":"Сбалансированный","en":"Balanced"}[lang],
                    "climate":{"kk":"Климаттық тұрақтылық","ru":"Климатическая устойчивость","en":"Climate resilience"}[lang],
                    "resource":{"kk":"Ресурс үнемдеу","ru":"Ресурсосбережение","en":"Resource saving"}[lang],
                    "survey_proxy":{"kk":"Сауалнама негізіндегі сценарий (эксперимент)","ru":"Опросный сценарий (эксперимент)","en":"Survey-informed sensitivity (experimental)"}[lang],
                    "custom":{"kk":"Жеке салмақтар","ru":"Пользовательские веса","en":"Custom weights"}[lang],
                }[x],
            )
            if optimization_profile == 'survey_proxy':
                st.caption({
                    'kk':'2026 жылғы сауалнама, 208 жауап: су тапшылығы 120/208 (3-сұрақ), климаттық тәуекелдер 93/208 (7-сұрақ). Су 56,3%, климат 43,7% - әртүрлі сұрақтар жиіліктерінен алынған тек сезімталдық сценарийі, статистикалық бағаланған салмақ емес.',
                    'ru':'Опрос 2026, 208 ответов: дефицит воды 120/208 (вопрос 3), климатические риски 93/208 (вопрос 7). Вода 56,3%, климат 43,7% - только сценарий чувствительности по частотам из разных вопросов, не статистически оценённые веса.',
                    'en':'2026 survey, 208 responses: water scarcity 120/208 (Q3), climate risk 93/208 (Q7). Water 56.3%, climate 43.7% - an exploratory sensitivity profile from different questions, not estimated survey weights.'
                }[lang])
            if optimization_profile == 'custom':
                optimization_custom_climate_weight=q_number_input(
                    {"kk":"Климат салмағы, %","ru":"Вес климата, %","en":"Climate weight, %"}[lang],
                    min_value=0.0,max_value=100.0,value=60.0,step=1.0)/100.0
                st.caption({"kk":"Су салмағы = 100% - климат. Бұл сауалнама бойынша автоматты калибрлеу емес.",
                            "ru":"Вес воды = 100% минус вес климата. Это сценарий чувствительности, не калибровка по опросу.",
                            "en":"Water weight = 100% minus climate weight. Exploratory sensitivity only, not survey-calibrated."}[lang])
        with op2:
            optimization_max_share = q_number_input(
                {"kk":"Бір дақылдың ең жоғары үлесі, %","ru":"Максимальная доля одной культуры, %","en":"Maximum share of one crop, %"}[lang],
                min_value=20.0, max_value=80.0, value=40.0, step=5.0
            ) / 100.0
        with op3:
            optimization_n_crops = int(q_number_input(
                {"kk":"Егіс құрылымындағы дақылдар саны","ru":"Количество культур в структуре посевов","en":"Number of crops in the cropping structure"}[lang],
                min_value=2, max_value=8, value=5, step=1,
                help={
                    "kk":"Модель егістік ауданды қанша түрлі дақыл арасында бөлетінін көрсетіңіз. Мысалы, 5 - ұсынылатын құрылымда бес дақыл болады.",
                    "ru":"Укажите, между сколькими культурами модель должна распределить посевную площадь. Например, 5 означает структуру из пяти культур.",
                    "en":"Choose how many different crops should share the cultivated area. For example, 5 means a five-crop structure."
                }[lang]
            ))

    if mode_key == "mode4" and user_level != "farmer":
        with st.expander({"kk":"Климат және су стресс-сценарийі (міндетті емес)","ru":"Климатический и водный стресс-сценарий (необязательно)","en":"Climate and water stress scenario (optional)"}[lang], expanded=False):
            _cs1,_cs2,_cs3=st.columns(3)
            with _cs1:
                optimization_temp_delta_c=q_number_input({"kk":"Температура өзгерісі, °C","ru":"Изменение температуры, °C","en":"Temperature change, °C"}[lang],min_value=-5.0,max_value=8.0,value=0.0,step=0.5)
            with _cs2:
                optimization_precip_change_pct=q_number_input({"kk":"Жауын-шашын өзгерісі, %","ru":"Изменение осадков, %","en":"Precipitation change, %"}[lang],min_value=-80.0,max_value=100.0,value=0.0,step=5.0)
            with _cs3:
                optimization_water_budget_change_pct=q_number_input({"kk":"Қолжетімді су бюджетінің өзгерісі, %","ru":"Изменение доступного водного бюджета, %","en":"Available-water budget change, %"}[lang],min_value=-90.0,max_value=100.0,value=0.0,step=5.0)
            st.caption({"kk":"Бұл SSP/CMIP ұзақмерзімді проекциясы емес. Бұл пайдаланушы анықтайтын stress-test: бастапқы климаттық профильге температура/жауын-шашын өзгерісі және су бюджетінің өзгерісі қолданылады.","ru":"Это не долгосрочная SSP/CMIP-проекция. Это пользовательский стресс-тест: к базовому климатическому профилю применяются заданные изменения температуры, осадков и доступного водного бюджета.","en":"This is not a long-term SSP/CMIP projection. It is a user-defined stress test applying temperature, precipitation and available-water changes to the baseline climate profile."}[lang])

    optimization_use_economics = False
    optimization_objective_mode = "resource"
    optimization_economic_weight = 0.35
    optimization_economic_margins = {}
    optimization_baseline_shares = {}
    optimization_ghg_by_product = {}
    optimization_ghg_evidence = ""
    optimization_ghg_confirmed = False
    optimization_margin_decline_pct = 5.0
    optimization_absolute_ghg_cap_kg = None
    if mode_key == "mode4" and user_level != "farmer":
        with st.expander({"kk":"Экономикалық мақсат және «дейін/кейін» салыстыру","ru":"Экономическая цель и сравнение «до/после»","en":"Economic objective and before/after comparison"}[lang], expanded=False):
            optimization_objective_mode = st.selectbox(
                {"kk":"Оңтайландыру мақсаты","ru":"Цель оптимизации","en":"Optimization objective"}[lang],
                ["resource","balanced","economic","sustainable"],
                format_func=lambda x: {
                    "resource":{"kk":"Ресурс-климаттық тиімділік","ru":"Ресурсно-климатическая эффективность","en":"Resource-climate efficiency"}[lang],
                    "balanced":{"kk":"Теңгерімді: ресурс + экономика","ru":"Сбалансированный: ресурсы + экономика","en":"Balanced: resources + economics"}[lang],
                    "economic":{"kk":"Экономикалық нәтиже басымдығы","ru":"Приоритет экономического результата","en":"Economic-return priority"}[lang],
                    "sustainable":{"kk":"Тұрақты ымыра: су, CO₂e, маржа","ru":"Устойчивый компромисс: вода, CO₂e, маржа","en":"Sustainable compromise: water, CO₂e, margin"}[lang],
                }[x],
            )
            optimization_use_economics = optimization_objective_mode != "resource"
            st.caption({"kk":"QŪNAR жетіспейтін нарықтық деректерді ойдан шығармайды. Экономикалық режим тек пайдаланушы енгізген немесе тексерілген маржа мәндері бар дақылдарды салыстырады. Ағымдағы құрылым үлесін енгізсеңіз, модель «дейін/кейін» экономикалық және су тиімділігін есептейді.","ru":"QŪNAR не выдумывает отсутствующие рыночные данные. Экономические режимы сравнивают только культуры, для которых введена подтвержденная или сценарная маржа. Если указать текущую структуру посевов, модель дополнительно рассчитает экономический и водный эффект «до/после».","en":"QŪNAR never fabricates missing market data. Economic modes compare only crops with a verified/scenario user-entered contribution margin. If the current crop structure is entered, QŪNAR also calculates before/after economic and water effects."}[lang])
            st.warning({
                "ru": "ПРОИСХОЖДЕНИЕ ДАННЫХ: QŪNAR пока не располагает подтверждённым справочником текущих затрат без воды и электроэнергии, азота и дизеля по всем культурам/районам. Площади 50/30/20, затраты и активности из демонстрационного A8 - исследовательские допущения, НЕ статистика БНС. Вводимая маржа является пользовательским сценарием и не становится официальной из-за наличия цен БНС. Для научного использования приложите источники каждого компонента.",
                "kk": "ДЕРЕККӨЗ МӘРТЕБЕСІ: QŪNAR-да барлық дақылдар мен аудандарға арналған су мен электрді қоспаған ағымдағы шығындар, азот және дизель бойынша толық расталған анықтамалық жоқ. A8 мысалындағы 50/30/20 үлестері, шығындар және ресурстар - ғылыми сценарий жорамалдары, ҰСБ деректері емес. Енгізілген маржа ресми статистика болып саналмайды. Әр құрамдас бөлікке дереккөз келтіріңіз.",
                "en": "DATA PROVENANCE: QŪNAR has no complete validated current reference catalogue for non-water/non-electricity production costs, nitrogen or diesel across all crops and districts. The illustrative A8 50/30/20 shares, costs and activities are research assumptions, NOT official BNS observations. User-entered margins remain scenarios even when producer prices come from BNS. Cite each component before academic use."
            }[lang])
            if optimization_use_economics:
                _default_weight = 70 if optimization_objective_mode == "economic" else 35
                optimization_economic_weight = st.slider({"kk":"Экономикалық критерий салмағы, %","ru":"Вес экономического критерия, %","en":"Economic-objective weight, %"}[lang], 10, 85, _default_weight, 5) / 100.0
                if optimization_objective_mode == "sustainable":
                    optimization_margin_decline_pct = st.slider({"kk":"Бастапқы маржадан ең көп төмендеу, %","ru":"Допустимое снижение маржи относительно исходной структуры, %","en":"Maximum contribution margin decline from baseline, %"}[lang], 0, 30, 5, 1)
                    optimization_ghg_evidence = st.text_input({"kk":"CO₂e дақылдық бағаларының көзі мен есепке алу кезеңі","ru":"Источник оценок CO₂e по культурам и период учёта","en":"Per-crop CO₂e source and accounting period"}[lang], placeholder="e.g. scenario partial N₂O + diesel + pumping, Apr–Sep 2026")
                    optimization_ghg_confirmed = st.checkbox({"kk":"Барлық дақылдар үшін бірдей шекара мен коэффициенттер расталды","ru":"Подтверждаю единые границы учёта и коэффициенты для всех культур","en":"I confirm consistent emissions boundaries and factors for all crops"}[lang])
                    _use_absolute_ghg_cap=st.checkbox({'ru':'Ограничить CO₂e абсолютным уровнем (например, базовый год до потепления)',
                        'kk':'CO₂e үшін абсолютті шек орнату (мысалы, базалық жыл)',
                        'en':'Apply absolute CO₂e cap (e.g. pre-warming reference year)' }[lang],value=False,key='sust_abs_ghg_toggle')
                    if _use_absolute_ghg_cap:
                        optimization_absolute_ghg_cap_kg=q_number_input({'ru':'Абсолютный предел частичных выбросов, кг CO₂e / хозяйство / сезон',
                            'kk':'Ішінара шығарындылар шегі, кг CO₂e / шаруашылық / маусым',
                            'en':'Absolute partial GHG ceiling, kg CO₂e / farm / season'}[lang],min_value=0.0,value=0.0,step=100.0,key='sust_abs_ghg_value')
            try:
                _sc = scenario_for_district(used_district, None, irrigation_type)
                _reg = clrem_registry()[['CLREM_product', {'kk':'KK','ru':'RU','en':'EN'}[lang]]].dropna().drop_duplicates('CLREM_product')
                _reg.columns=['product','display']
                _econ_rows = _sc[['product']].drop_duplicates().merge(_reg,on='product',how='left')
                _econ_rows['display']=_econ_rows['product'].map(lambda x: extended_crop_label(x, lang))
                _saved_econ_rows = st.session_state.get('qunar_econ_table_saved', {})
                # Blank is unreported; an explicitly entered zero is break-even.
                _econ_rows['margin_kzt_ha']=float('nan')
                _econ_rows['current_share_pct']=0.0
                _econ_rows['partial_ghg_kg_co2e_ha']=float('nan')
                for _i, _er in _econ_rows.iterrows():
                    _saved = _saved_econ_rows.get(str(_er['product']), {})
                    for _column in ('margin_kzt_ha', 'current_share_pct', 'partial_ghg_kg_co2e_ha'):
                        if _column in _saved and _saved[_column] is not None:
                            _econ_rows.at[_i, _column] = _saved[_column]
                _visible_cols=['product','display','margin_kzt_ha','current_share_pct'] + (['partial_ghg_kg_co2e_ha'] if optimization_objective_mode == 'sustainable' else [])
                _edited = st.data_editor(_econ_rows[_visible_cols], hide_index=True, use_container_width=True, key='qunar_econ_editor_'+optimization_objective_mode,
                    disabled=['product','display'], column_config={
                        'product': None,
                        'display': st.column_config.TextColumn({"kk":"Дақыл","ru":"Культура","en":"Crop"}[lang]),
                        'margin_kzt_ha': st.column_config.NumberColumn({"kk":"Маржа, тг/га","ru":"Маржа, тг/га","en":"Contribution margin, KZT/ha"}[lang], min_value=-1000000000.0, step=10000.0, format='%.0f'),
                        'current_share_pct': st.column_config.NumberColumn({"kk":"Ағымдағы үлес, %","ru":"Текущая доля, %","en":"Current share, %"}[lang], min_value=0.0, max_value=100.0, step=1.0, format='%.5g')
                    })
                st.session_state['qunar_econ_table_saved'] = {
                    str(_er['product']): {
                        _col: (float(_er[_col]) if pd.notna(_er[_col]) else None)
                        for _col in ('margin_kzt_ha','current_share_pct','partial_ghg_kg_co2e_ha')
                        if _col in _edited.columns
                    }
                    for _,_er in _edited.iterrows()
                }
                optimization_economic_margins={str(r['product']):float(r['margin_kzt_ha']) for _,r in _edited.iterrows() if pd.notna(r['margin_kzt_ha'])}
                optimization_baseline_shares={str(r['product']):float(r['current_share_pct']) for _,r in _edited.iterrows() if float(r['current_share_pct'] or 0)>0}
                if optimization_objective_mode == 'sustainable':
                    optimization_ghg_by_product={str(r['product']):float(r['partial_ghg_kg_co2e_ha']) for _,r in _edited.iterrows() if pd.notna(r['partial_ghg_kg_co2e_ha'])}
                    st.caption({'ru':'Выбросы должны охватывать одни и те же источники (например, азот, дизель, электричество) и период для всех культур. Пустое поле не равно нулю. Снижение частичных выбросов не означает сокращения полного углеродного следа.', 'kk':'Барлық дақылдар үшін шығарындылардың кезеңі мен құрамы бірдей болуы тиіс; бос жол нөл емес.', 'en':'Emissions must cover the same components and period across crops; blank is not zero. Partial emissions are not a full footprint.'}[lang])
                _share_sum=sum(optimization_baseline_shares.values())
                if _share_sum>0 and abs(_share_sum-100.0)>0.5:
                    st.warning({"kk":f"Ағымдағы үлестердің қосындысы {_share_sum:.1f}%. «Дейін/кейін» салыстыру үшін барлық үлестердің қосындысы 100% болуға тиіс; есеп автоматты түрде толтырылмайды.","ru":f"Сумма текущих долей {_share_sum:.1f}%. Для корректного сравнения «до/после» введите все культуры, чтобы получилось 100%. Частичная структура не будет автоматически нормализована.","en":f"Current shares sum to {_share_sum:.1f}%. Enter a complete baseline adding to 100%; an incomplete structure will not be automatically normalized."}[lang])
                st.caption({"kk":"Бос ұяшық - дерек жоқ, 0 - залалсыздық, теріс сан - залал.","ru":"Пустая ячейка - данные отсутствуют; 0 - безубыточность; отрицательная маржа - убыток.","en":"Blank cell means missing data; 0 means break-even; negative margin represents a loss."}[lang])
            except Exception as _econ_exc:
                st.caption(str(_econ_exc))

    # Crop-specific water inputs are an explicit second accounting boundary.
    # Never mix official gross norms with root-zone net irrigation volumes.
    structure_water_enabled = False
    structure_water_data = {}
    structure_water_provenance = ''
    structure_water_confirmed = False
    structure_water_conveyance = None
    structure_water_baseline_returns = None
    structure_water_proposed_returns = None
    structure_water_baseline_conveyance_return = None
    structure_water_proposed_conveyance_return = None
    structure_water_optimizer_basis = 'field_delivery'
    structure_water_use_hard_constraint = False
    if mode_key == 'mode4' and user_level != 'farmer':
        with st.expander({'ru':'Водный баланс всей структуры посевов (дополнительно)',
                          'kk':'Егіс құрылымының толық су балансы (қосымша)',
                          'en':'Crop-mix water accounting (optional)'}[lang],expanded=False):
            structure_water_enabled = st.checkbox({'ru':'Сравнить исходную и оптимизированную структуры по воде',
                'kk':'Бастапқы және оңтайландырылған құрылымның су есебін салыстыру',
                'en':'Compare baseline and optimized crop-mix water'}[lang],value=False)
            if structure_water_enabled:
                st.caption({'ru':'Введите ЧИСТУЮ потребность корневой зоны каждой культуры за один и тот же сезон (м³/га), например из подтверждённого FAO-56 расчёта. Не вставляйте сюда готовые валовые нормы водоподачи. Пропуск нельзя считать нулём.',
                            'kk':'Әр дақылдың тамыр аймағындағы таза суару қажеттілігін (м³/га) бір маусымға енгізіңіз. Жалпы су беру нормасын қолданбаңыз.',
                            'en':'Enter net ROOT-ZONE irrigation need per crop for the same season (m³/ha), e.g. from a documented FAO-56 calculation. Do not paste gross official delivery norms; blanks are not zero.'}[lang])
                _sm1,_sm2=st.columns(2)
                with _sm1:
                    _sw_base_method=st.selectbox({'ru':'Исходное орошение (FAO, ориентир)',
                        'kk':'Бастапқы суару (FAO бағасы)','en':'Baseline field method (FAO reference)'}[lang],
                        list(FIELD_EFFICIENCIES),key='structure_water_baseline_method')
                with _sm2:
                    _sw_new_method=st.selectbox({'ru':'Сценарное орошение (FAO, ориентир)',
                        'kk':'Сценарийлік суару (FAO бағасы)','en':'Proposed field method (FAO reference)'}[lang],
                        list(FIELD_EFFICIENCIES),index=2,key='structure_water_proposed_method')
                _sw_product_rows=scenario_for_district(used_district,None,irrigation_type)[['product']].drop_duplicates().copy()
                _sw_product_rows['display']=_sw_product_rows['product'].map(lambda c: extended_crop_label(c,lang))
                _sw_product_rows['net_m3_ha']=float('nan')
                _sw_product_rows['eta_before_pct']=FIELD_EFFICIENCIES[_sw_base_method]*100.0
                _sw_product_rows['eta_after_pct']=FIELD_EFFICIENCIES[_sw_new_method]*100.0
                _sw_edited=st.data_editor(_sw_product_rows,hide_index=True,use_container_width=True,
                    disabled=['product','display'],key='structure_water_crop_editor',column_config={
                      'product':None,
                      'net_m3_ha':st.column_config.NumberColumn('Net irrigation, m³/ha',min_value=0.0,format='%.0f'),
                      'eta_before_pct':st.column_config.NumberColumn('Baseline field efficiency, %',min_value=1.0,max_value=100.0,format='%.5g'),
                      'eta_after_pct':st.column_config.NumberColumn('Proposed field efficiency, %',min_value=1.0,max_value=100.0,format='%.5g'),
                    })
                for _,_row in _sw_edited.iterrows():
                    if pd.notna(_row['net_m3_ha']):
                        structure_water_data[str(_row['product'])]={
                            'net':float(_row['net_m3_ha']),
                            'eta_before':float(_row['eta_before_pct'])/100.0,
                            'eta_after':float(_row['eta_after_pct'])/100.0}
                _sw_convey_known=st.checkbox({'ru':'Есть подтверждённая или сценарная эффективность доставки воды от источника',
                   'kk':'Су көзінен жеткізу тиімділігі белгілі','en':'Conveyance efficiency is supported/assumed'}[lang],key='structure_water_convey_known')
                if _sw_convey_known:
                    structure_water_conveyance=q_number_input({'ru':'Эффективность транспортировки воды, %',
                        'kk':'Су жеткізу тиімділігі, %','en':'Conveyance efficiency, %'}[lang],
                        min_value=1.0,max_value=100.0,value=80.0,step=1.0,key='structure_water_convey_eta')/100.0
                _sw_return_known=st.checkbox({'ru':'Есть данные/явные сценарные допущения о возвратных потоках',
                     'kk':'Қайтарымды ағындарға деректер немесе жорамалдар бар',
                     'en':'Return-flow fractions supported by evidence/scenario assumptions'}[lang],
                     key='structure_water_return_known')
                if _sw_return_known:
                    _sr1,_sr2=st.columns(2)
                    with _sr1:
                        _return_baseline=q_number_input({'ru':'Возвратная доля полевых потерь до, %','kk':'Бастапқы қайтарым үлесі, %','en':'Recoverable field losses before, %'}[lang],
                            min_value=0.0,max_value=100.0,value=0.0,key='structure_water_r1')/100.0
                    with _sr2:
                        _return_proposed=q_number_input({'ru':'Возвратная доля полевых потерь после, %','kk':'Сценарийлік қайтарым үлесі, %','en':'Recoverable field losses after, %'}[lang],
                            min_value=0.0,max_value=100.0,value=0.0,key='structure_water_r2')/100.0
                    structure_water_baseline_returns={k:_return_baseline for k in structure_water_data}
                    structure_water_proposed_returns={k:_return_proposed for k in structure_water_data}
                    if structure_water_conveyance is not None:
                        _cr1,_cr2=st.columns(2)
                        with _cr1:
                            structure_water_baseline_conveyance_return=q_number_input({'ru':'Возвратная доля потерь транспортировки до, %','kk':'Жеткізу шығынының қайтарымы дейін, %','en':'Recoverable conveyance losses before, %'}[lang],
                                min_value=0.0,max_value=100.0,value=0.0,key='structure_water_cr1')/100.0
                        with _cr2:
                            structure_water_proposed_conveyance_return=q_number_input({'ru':'Возвратная доля потерь транспортировки после, %','kk':'Жеткізу шығынының қайтарымы кейін, %','en':'Recoverable conveyance losses after, %'}[lang],
                                min_value=0.0,max_value=100.0,value=0.0,key='structure_water_cr2')/100.0
                structure_water_provenance=st.text_input({'ru':'Источник потребности культур и допущений о поливе',
                    'kk':'Дақыл қажеттілігі мен суару жорамалдарының дереккөзі',
                    'en':'Net irrigation data source and method assumptions'}[lang],key='structure_water_evidence')
                structure_water_confirmed=st.checkbox({'ru':'Подтверждаю период, единицы, исходные нули и допущения',
                    'kk':'Мерзім, өлшем бірлігі, нөлдер мен жорамалдарды растаймын',
                    'en':'Confirm time period, units, true zero values and assumptions'}[lang],key='structure_water_confirmed')
                structure_water_use_hard_constraint=st.checkbox({'ru':'Использовать этот сценарий как ЖЁСТКОЕ водное ограничение оптимизатора',
                    'kk':'Осы сценарийді оңтайландыруда қатаң су шектеуі ретінде қолдану',
                    'en':'Use crop-specific scenario as optimizer hard water constraint'}[lang],key='structure_water_hard_constraint')
                if structure_water_use_hard_constraint:
                    _sw_basis_opts=['field_delivery']+(['source_withdrawal'] if structure_water_conveyance is not None else [])
                    structure_water_optimizer_basis=st.selectbox({'ru':'Что именно означает введённый водный лимит?',
                        'kk':'Енгізілген су лимитінің негізі',
                        'en':'What is the accounting boundary of the water budget?'}[lang],_sw_basis_opts,
                        format_func=lambda x:{'field_delivery':'Подача воды на поле / Field delivery','source_withdrawal':'Забор из источника / Source withdrawal'}[x],
                        key='structure_water_budget_basis')
                    st.warning({'ru':'Сценарный водный лимит и справочные официальные нормы являются РАЗНЫМИ границами учёта. Новые показатели не означают, что государственные нормы изменились.',
                         'kk':'Сценарийлік лимит пен ресми нормативтердің есеп шекарасы бөлек.',
                         'en':'Scenario volumes and official irrigation references are different accounting boundaries. This does not change official norms.'}[lang])

    # Optional, user-declared activity comparison. It is a partial inventory only.
    carbon_enabled = False
    carbon_inputs = {}
    carbon_enteric = False
    carbon_activity_confirmed = False
    if mode_key in ("mode1", "mode2", "mode4", "mode5"):
        with st.expander({"kk":"Парниктік газдардың ішінара есебі (міндетті емес)",
                          "ru":"Частичный учёт парниковых газов (необязательно)",
                          "en":"Partial greenhouse-gas inventory (optional)"}[lang], expanded=False):
            carbon_enabled = st.checkbox({
                "kk":"Екі нұсқа үшін кіріс деректерін енгізіп, сценарийді салыстыру",
                "ru":"Ввести исходные данные для двух вариантов и сравнить сценарии",
                "en":"Enter activities for both cases and compare scenario emissions"}[lang],value=False)
            if carbon_enabled:
                st.caption({
                    "kk":"Тек тікелей N₂O (азот), дизель жануы, электр энергиясы және қажет болғанда малдың асқорыту метаны. Өндіріс, жанама N₂O, көң, топырақ көміртегі қамтылмайды. Нөлді тек расталған жағдайда енгізіңіз.",
                    "ru":"Только прямой N₂O от азота, сгорание дизеля, электроэнергия и при необходимости энтеральный метан. Производство удобрений, косвенный N₂O, навоз и углерод почвы не учитываются. Ноль вводите только при подтверждённом отсутствии расхода.",
                    "en":"Only direct N2O from nitrogen, diesel combustion, electricity and optionally enteric methane. Fertilizer manufacturing, indirect N2O, manure and soil carbon excluded. Enter zero only when confirmed."}[lang])
                carbon_accounting_period = st.selectbox(
                    {'kk':'Парниктік газдар есебінің кезеңі','ru':'Расчётный период выбросов','en':'GHG accounting period'}[lang],
                    ['apr_sep','calendar_year'],
                    format_func=lambda x: {
                        'apr_sep':{'kk':'Сәуір-қыркүйек (183 күн)','ru':'Апрель-сентябрь (183 дня)','en':'April-September (183 days)'}[lang],
                        'calendar_year':{'kk':'Күнтізбелік жыл','ru':'Календарный год','en':'Calendar year'}[lang],
                    }[x],
                    key='ghg_accounting_period')
                st.caption({
                    'kk':'Екі нұсқаның азот, дизель және электр тұтынуын таңдалған бірдей кезеңге енгізіңіз. Мал метаны үшін жылдық коэффициент сәуір-қыркүйек кезеңіне 183/365 үлесімен шартты түрде аударылады.',
                    'ru':'Для обоих вариантов введите азот, дизель и электроэнергию за один и тот же выбранный период. Годовой коэффициент метана животных для апреля-сентября пересчитывается пропорционально 183/365; это допущение.',
                    'en':'Enter nitrogen, diesel and electricity for the same selected period in both cases. Annual livestock methane is scaled by 183/365 for April-September; this is an assumption.'
                }[lang])
                _ghg_n_mode = st.selectbox(
                    {'ru':'Основание массы азота', 'kk':'Азот массасының негізі',
                     'en':'Nitrogen activity basis'}[lang],
                    ['nutrient_n','fertilizer_product'],
                    format_func=lambda code: {
                        'nutrient_n':{'ru':'Известен действующий азот, кг N',
                          'kk':'Әсер етуші азот белгілі, кг N', 'en':'Elemental nitrogen known, kg N'},
                        'fertilizer_product':{'ru':'Известна масса удобрения и его вид, кг продукта',
                          'kk':'Тыңайтқыш массасы мен түрі белгілі, кг өнім',
                          'en':'Fertilizer product mass and type known, kg product'}
                    }[code][lang], key='ghg_n_input_mode')
                _ghg_product=None
                _ghg_n_fraction=None
                if _ghg_n_mode == 'fertilizer_product':
                    _ghg_product = st.selectbox(
                        {'ru':'Минеральное удобрение / гарантированный состав',
                         'kk':'Минералды тыңайтқыш / кепілдік құрамы',
                         'en':'Fertilizer product / guaranteed composition'}[lang],
                        list(FERTILIZER_GOST_MIN_N_FRACTION)+['custom'],
                        format_func=lambda c:{
                            'urea_dry_B':{'ru':'Карбамид Б - ≥46,2% N (ГОСТ)',
                              'kk':'Карбамид Б - ≥46,2% N (МЕМСТ)',
                              'en':'Urea grade B - ≥46.2% N (GOST)'},
                            'ammonium_nitrate_B_grade1_dry':{'ru':'Аммиачная селитра Б, 1 сорт - ≥34,4% N',
                              'kk':'Аммоний селитрасы Б, 1 сұрып - ≥34,4% N',
                              'en':'Ammonium nitrate B, 1st grade - ≥34.4% N'},
                            'ammonium_nitrate_B_grade2_dry':{'ru':'Аммиачная селитра Б, 2 сорт - ≥34,0% N',
                              'kk':'Аммоний селитрасы Б, 2 сұрып - ≥34,0% N',
                              'en':'Ammonium nitrate B, 2nd grade - ≥34.0% N'},
                            'custom':{'ru':'Состав с этикетки / другой вид удобрения',
                              'kk':'Жапсырмадағы құрам / басқа тыңайтқыш',
                              'en':'Label composition / another product'}
                        }[c][lang], key='ghg_fertilizer_product')
                    if _ghg_product == 'custom':
                        _pct = q_number_input(
                            {'ru':'Содержание N в продукте, % (с этикетки)',
                             'kk':'Өнімдегі N үлесі, % (жапсырмадан)',
                             'en':'Nitrogen fraction, % (from product label)'}[lang],
                            min_value=0.0,max_value=100.0,value=0.0,step=0.1)
                        _ghg_n_fraction=(_pct/100 if _pct>0 else None)
                    else:
                        _ghg_n_fraction=FERTILIZER_GOST_MIN_N_FRACTION[_ghg_product]
                cba, cbb = st.columns(2)
                for slot, (column, title) in enumerate(((cba,{"kk":"Ағымдағы нұсқа","ru":"Исходный вариант","en":"Baseline"}[lang]),
                                                        (cbb,{"kk":"Сценарий","ru":"Сценарный вариант","en":"Proposed scenario"}[lang]))):
                    case='baseline' if slot==0 else 'proposed'
                    with column:
                        st.markdown("**"+title+"**")
                        cn = q_number_input(({
                            'kk':'Тыңайтқыш өнімі, кг (бүкіл аумақ)',
                            'ru':'Масса удобрения, кг (вся площадь)',
                            'en':'Fertilizer product kg (whole area)'}[lang] if _ghg_n_mode == 'fertilizer_product'
                            else {"kk":"Азот, кг N (барлық алаң)","ru":"Азот, кг N (вся площадь)",
                                  "en":"Nitrogen, kg N (whole area)"}[lang]) + " / " + title,
                                            min_value=0.0,value=0.0,step=10.0,key="ghg_n_"+case)
                        cd = q_number_input({"kk":"Дизель, л","ru":"Дизель, л","en":"Diesel, litres"}[lang] + " / " + title,
                                            min_value=0.0,value=0.0,step=10.0,key="ghg_diesel_"+case)
                        ce = q_number_input({"kk":"Электр энергиясы, кВт·сағ","ru":"Электроэнергия, кВт·ч","en":"Electricity, kWh"}[lang] + " / " + title,
                                            min_value=0.0,value=0.0,step=100.0,key="ghg_electric_"+case)
                        carbon_inputs[case]={'nitrogen_kg':(fertilizer_nitrogen_kg(
                            product_kg=cn,nitrogen_mass_fraction=_ghg_n_fraction)
                            if _ghg_n_mode == 'fertilizer_product' else cn),
                            'diesel_litres':cd,'electricity_kwh':ce}
                carbon_activity_confirmed = st.checkbox({
                    "kk":"Екі сценарий бойынша барлық енгізілген мөлшер тексерілді, оның ішінде нөлдік мәндер",
                    "ru":"Подтверждаю все количества для обоих сценариев, включая действительно нулевые значения",
                    "en":"I confirm all activity amounts for both scenarios, including any verified zeros"}[lang],value=False)
                carbon_n2o_climate = st.selectbox(
                    {'ru':'Климатическая категория IPCC для прямого N₂O',
                     'kk':'Тікелей N₂O үшін IPCC климаттық санаты',
                     'en':'IPCC direct soil N2O climate class'}[lang],
                    ['general','dry'],
                    format_func=lambda item: {'general':{
                        'ru':'Общий коэффициент EF1 = 0,01',
                        'kk':'Жалпы коэффициент EF1 = 0,01',
                        'en':'General EF1 = 0.01'},
                        'dry':{
                        'ru':'Сухой климат: EF1 = 0,005 (при подтверждении применимости)',
                        'kk':'Құрғақ климат: EF1 = 0,005 (сәйкестігін тексеру қажет)',
                        'en':'Dry-climate EF1 = 0.005 (when applicable)'}}[item][lang],
                    key='ghg_n2o_climate_class')
                carbon_diesel_factor=q_number_input(
                    {"kk":"Дизель үшін сценарийлік коэффициент, кг CO₂/л","ru":"Сценарный коэффициент дизеля, кг CO₂/л","en":"Diesel scenario factor, kg CO₂/litre"}[lang],
                    min_value=0.0,value=float(round(diesel_combustion_factor(),6)),step=0.001)
                st.caption({"kk":"2,676492 кг/л - IPCC жану коэффициенті, үлгілік тығыздық пен жану жылуы бойынша есеп. Нақты отын көрсеткіштерін енгізуге болады.",
                            "ru":"2,676492 кг/л - расчёт сгорания по IPCC при справочных плотности и теплоте сгорания. Это не полный жизненный цикл топлива; коэффициент редактируется.",
                            "en":"2.676492 kg/l derives from the IPCC combustion factor and reference fuel density and heating value; editable and not full lifecycle emissions."}[lang])
                if mode_key == 'mode5':
                    carbon_enteric = st.checkbox({"kk":"Асқорыту метанын қосу","ru":"Добавить метан пищеварения животных","en":"Include enteric methane"}[lang],value=False)
                    if carbon_enteric:
                        if livestock_species in ('Poultry layers','Poultry broilers'):
                            st.info({'ru':'Энтеральный CH₄ у птицы не рассчитывается. Метан навоза при этом не равен нулю.',
                                     'kk':'Құстар үшін ішектік CH₄ есептелмейді. Бұл көң шығарындылары жоқ дегенді білдірмейді.',
                                     'en':'Enteric CH4 is not calculated for poultry; manure emissions may still occur.'}[lang])
                            carbon_enteric=False
                        else:
                            carbon_enteric_factor=q_number_input({"kk":"CH₄ коэффициенті, кг/бас/жыл","ru":"Коэффициент CH₄, кг/голову/год","en":"CH4 factor, kg/head/year"}[lang],
                                min_value=0.0,value=float(ENTERIC_CH4_ASIA_KG_HEAD_YEAR.get(livestock_species, 0.0)),step=1.0)
                            st.caption({'ru':'IPCC 2019, Tier 1, регион Азия: справочный коэффициент, а не измерение стада. ',
                                        'kk':'IPCC 2019, 1-деңгей, Азия: анықтамалық коэффициент, нақты мал өлшемі емес. ',
                                        'en':'IPCC 2019 Tier 1, Asia: reference factor, not a measured herd rate. '}[lang])
                            carbon_enteric_base=q_number_input({"kk":"Бастапқы мал саны","ru":"Исходное поголовье, голов","en":"Baseline heads"}[lang],min_value=0.0,value=0.0,step=1.0)
                            carbon_enteric_proposed=q_number_input({"kk":"Сценарий мал саны","ru":"Сценарное поголовье, голов","en":"Proposed heads"}[lang],min_value=0.0,value=0.0,step=1.0)
                            st.caption({"kk":"Коэффициент түрге сай сенімді дереккөзден алынуы керек; есептік кезең жоғарыда таңдалады.",
                                    "ru":"Коэффициент должен иметь источник для выбранного вида животных; расчётный период выбирается выше.",
                                    "en":"Use a source-supported coefficient for the species; the accounting period is selected above."}[lang])

    # Exploratory CMIP6 side-by-side scenario; never mutates the historical model.
    climate_future_scenario = "none"
    climate_future_apply_opt = False
    fao56_enabled = False
    fao56_kc_text = ''
    fao56_kc_mode = 'none'
    fao56_sowing_date = None
    fao56_stage_lengths_text = ''
    fao56_efficiency = None
    fao56_efficiency_source = 'not_selected'
    fao56_target_method = 'none'
    fao56_rain_method = 'none'
    climate_water_proxy_enabled = False
    if (user_level == "researcher" and mode_key == "mode4") or (user_level in ("specialist", "researcher") and mode_key in ("mode1", "mode2")):
        with st.expander({"kk":"CMIP6 климаттық сценарийі (2040-2059)","ru":"Климатический сценарий CMIP6 (2040-2059)","en":"CMIP6 climate scenario (2040-2059)"}[lang], expanded=False):
            climate_future_scenario = st.selectbox(
                {"kk":"Болашақ климат сценарийі","ru":"Сценарий будущего климата","en":"Future climate scenario"}[lang],
                ["none", "SSP2-4.5", "SSP5-8.5"],
                format_func=lambda x: ({"kk":"Өшірілген","ru":"Без сценария","en":"No scenario"}[lang] if x == "none" else x),
            )
            if climate_future_scenario != 'none' and mode_key == 'mode4':
                climate_future_apply_opt = st.checkbox({
                    'kk':'Бұл CMIP6 аномалияларын егіс құрылымының сценарийлік есебінде пайдалану',
                    'ru':'Применить эти аномалии CMIP6 в сценарном расчёте структуры посевов',
                    'en':'Apply CMIP6 anomalies to the crop-allocation stress scenario'}[lang], value=False)
                if climate_future_apply_opt:
                    st.caption({'ru':'Переопределяет введённые выше изменения температуры и осадков, но не водный лимит. Экстраполяция урожайности за пределы обучения не подтверждена.',
                                'kk':'Жоғарыдағы температура мен жауын-шашын өзгерістерін ауыстырады, бірақ су лимитін өзгертпейді. Оқыту ауқымынан тыс экстраполяция расталмаған.',
                                'en':'Overrides manual temperature and rainfall changes above, not the water limit. Yield extrapolation beyond training support is not validated.'}[lang])
            if climate_future_scenario != 'none' and mode_key in ('mode1','mode2'):
                climate_water_proxy_enabled=st.checkbox({"kk":"Температураға ғана негізделген су стресс-индикаторын көрсету",
                                                         "ru":"Показать ориентировочный водный стресс по температуре",
                                                         "en":"Show temperature-only water stress indicator"}[lang],value=False)
                if climate_water_proxy_enabled:
                    st.caption({"kk":"Тек Харгривс формуласындағы (T+17,8) мүшесінің сезімталдығы. Суару нормасының өзгерісі емес және су лимитін автоматты ауыстырмайды.",
                                "ru":"Это только чувствительность температурного члена (T+17,8) Харгривса. Не является новой нормой полива и не меняет водный лимит или оптимизацию.",
                                "en":"Sensitivity of the (T+17.8) Hargreaves term only; not a new irrigation requirement and does not modify water limits or optimization."}[lang])
            if climate_future_scenario != 'none' and mode_key in ('mode1','mode2'):
                with st.expander({
                    'kk':'FAO-56: су қажеттілігінің ғылыми сценарийі',
                    'ru':'FAO-56: расчёт климатической потребности в воде (отдельный сценарий)',
                    'en':'FAO-56: climate-sensitive irrigation demand (separate scenario)'}[lang],expanded=False):
                    fao56_enabled=st.checkbox({
                        'kk':'FAO-56 айлық есебін NASA POWER және CMIP6 арқылы орындау',
                        'ru':'Рассчитать месячный водный сценарий FAO-56 по NASA POWER и CMIP6',
                        'en':'Calculate FAO-56 monthly water scenario from NASA POWER and CMIP6'}[lang], value=False)
                    if fao56_enabled:
                        st.caption({
                            'kk':'NASA POWER 1995-2014 сәуір-қыркүйек: ауа температурасы, ылғалдылық, жел, радиация, қысым және жауын. FAO-56 бойынша ET₀ есептеледі. Дақылға нақты ETc және су қажеттілігі үшін айлық Kc қажет.',
                            'ru':'NASA POWER 1995-2014: температура, влажность, ветер, радиация, давление и осадки по месяцам. ET₀ рассчитывается по FAO-56. Для ETc и полива конкретной культуры нужны шесть коэффициентов Kc по фазам развития.',
                            'en':'NASA POWER 1995-2014 monthly temperature, RH, wind, solar, pressure and rainfall. FAO-56 ET0 requires these inputs. Six phenology-specific monthly Kc values are required for crop ETc/irrigation.'}[lang])
                        _available_kc_modes=['none','manual']
                        if crop in CROP_KC_STAGES:
                            _available_kc_modes.append('fao_crop_stages')
                        fao56_kc_mode=st.selectbox({
                            'kk':'Дақыл коэффициенті Kc дереккөзі',
                            'ru':'Источник коэффициентов культуры Kc',
                            'en':'Crop coefficient Kc source'}[lang],
                            _available_kc_modes, index=(_available_kc_modes.index('fao_crop_stages')
                                  if 'fao_crop_stages' in _available_kc_modes else 0), format_func=lambda m:{
                                'none':{'kk':'Kc жоқ: тек ET₀','ru':'Kc не задан: только ET₀','en':'No Kc: ET0 only'},
                                'manual':{'kk':'6 айлық Kc қолмен','ru':'Ввести 6 месячных Kc вручную','en':'Enter six monthly Kc'},
                                'fao_crop_stages':{'kk':'FAO фазалары бойынша (анықтамалық)','ru':'Рассчитать по фазам роста FAO (справочно)','en':'FAO crop stages (reference scenario)'}
                            }[m][lang])
                        if fao56_kc_mode == 'manual':
                            fao56_kc_text=st.text_input({
                                'kk':'Kc сәуір-қыркүйек, үтір арқылы',
                                'ru':'Kc апреля-сентября, через запятую',
                                'en':'Apr-Sep Kc, comma-separated'}[lang],
                                value='',placeholder='0.4, 0.7, 1.1, 1.1, 0.9, 0.6',
                                help={'kk':'Мәндер – тек мысал.', 'ru':'Пример не является проверенным календарём посевов.',
                                      'en':'Example is not a validated crop calendar.'}[lang])
                        elif fao56_kc_mode == 'fao_crop_stages':
                            _ref_kc,_ref_lengths=CROP_KC_STAGES[crop]
                            st.caption({'kk':'FAO кестесі: Kc фазалары '+str(_ref_kc)+'; ұзақтығы жергілікті жағдайға сай нақтыланады.',
                                        'ru':'FAO (справочно): Kc по фазам '+str(_ref_kc)+'. Даты и длительность уточняются для вашего хозяйства.',
                                        'en':'FAO stage Kc '+str(_ref_kc)+'. Dates and durations need local confirmation.'}[lang])
                            fao56_sowing_date=st.date_input({'kk':'Егу күні (сценарий)','ru':'Дата посева (сценарий)','en':'Sowing date (scenario)'}[lang],value=date(2025,4,1))
                            fao56_stage_lengths_text=st.text_input({
                                'kk':'Өсу кезеңдері, күн: бастапқы, даму, орта, соңғы',
                                'ru':'Длительность фаз, дней: начальная, развитие, середина, завершение',
                                'en':'Stage duration in days: initial, development, mid, late'}[lang],
                                value=', '.join(map(str,_ref_lengths)))
                            st.caption(FAO_CROP_KC_URL)
                        fao56_rain_method=st.selectbox({
                            'kk':'Тиімді жауын-шашынды есептеу',
                            'ru':'Метод оценки эффективных осадков',
                            'en':'Effective rainfall method'}[lang], ['none','fao_training'],
                            index=(1 if fao56_kc_mode!='none' else 0),
                            format_func=lambda x: ({
                                'none':{'kk':'Есептемеу (тек ET₀/ETc)','ru':'Не оценивать (только ET₀/ETc)','en':'Not estimated (ET0/ETc only)'},
                                'fao_training':{'kk':'FAO оқу әдістемесі, шартты','ru':'Эмпирический метод FAO, допущение','en':'FAO empirical training formula (assumed)'}}[x][lang]))
                        if fao56_rain_method!='none':
                            _known_method=irrigation_type in FIELD_EFFICIENCIES
                            _method_choices=['fao_reference','manual'] if _known_method else ['manual']
                            if irrigation_type=='mixed':
                                _method_choices=['mixed_area_shares','manual']
                            fao56_efficiency_source=st.selectbox({
                                'kk':'Суару тиімділігінің көзі',
                                'ru':'Источник коэффициента эффективности полива',
                                'en':'Irrigation efficiency source'}[lang], _method_choices,
                                format_func=lambda v:{'fao_reference':{'ru':'FAO, справочный показатель','kk':'FAO, анықтамалық','en':'FAO field reference'},
                                  'manual':{'ru':'Задать вручную','kk':'Қолмен енгізу','en':'User-supplied'},
                                  'mixed_area_shares':{'ru':'Смешанный полив: доли площадей','kk':'Аралас суару: үлестер','en':'Mixed irrigation: area shares'}}[v][lang])
                            if fao56_efficiency_source=='fao_reference':
                                fao56_efficiency=field_efficiency(irrigation_type)
                                st.caption({'ru':f'FAO: эффективность подачи воды на поле {100*fao56_efficiency:.0f}%. Это ориентир, не измерение хозяйства.',
                                            'kk':f'FAO: егістікте су беру тиімділігі {100*fao56_efficiency:.0f}%, тек анықтамалық.',
                                            'en':f'FAO indicative field application efficiency {100*fao56_efficiency:.0f}%, not farm measurement.'}[lang])
                            elif fao56_efficiency_source=='manual':
                                fao56_efficiency=q_number_input({
                                    'kk':'Егістіктегі су беру тиімділігі (0-1)',
                                    'ru':'Эффективность подачи воды на поле (0-1)',
                                    'en':'Field application efficiency (0-1)'}[lang],
                                    min_value=0.10,max_value=1.0,value=0.75,step=0.01)
                            else:
                                st.caption({'ru':'Укажите доли площади под каждым способом, сумма должна быть 100%.',
                                            'kk':'Әр суару тәсілінің егістік үлесін көрсетіңіз (барлығы 100%).',
                                            'en':'Enter the share of field area by irrigation type (must total 100%).'}[lang])
                                _mix={}
                                for _key,_ru in [('furrow','Бороздовой'),('sprinkler','Дождевание'),('drip','Капельный')]:
                                    _mix[_key]=q_number_input(_ru+' / '+_key+' (%)',min_value=0.0,max_value=100.0,value=0.0,step=5.0,key='fao56_mixed_'+_key)/100
                                # Avoid treating an incomplete mixture as valid until calculation is submitted.
                                fao56_efficiency_source='mixed_area_shares'
                                fao56_mixed_shares=_mix
                            st.caption(FAO_EFFICIENCY_URL)
                            fao56_target_method=st.selectbox({
                                'kk':'Салыстырылатын басқа суару тәсілі (міндетті емес)',
                                'ru':'Сравнить с другим способом полива (необязательно)',
                                'en':'Compare with another irrigation method (optional)'}[lang],
                                ['none','furrow','sprinkler','drip'],
                                format_func=lambda m:{'none':{'ru':'Не сравнивать','kk':'Салыстырмау','en':'No comparison'},
                                     'furrow':{'ru':'Бороздовой','kk':'Бороздалы','en':'Furrow'},
                                     'sprinkler':{'ru':'Дождевание','kk':'Жаңбырлатып','en':'Sprinkler'},
                                     'drip':{'ru':'Капельный','kk':'Тамшылатып','en':'Drip'}}[m][lang])
                        st.caption({
                            'kk':'Бұл жаңа ресми суару нормасы емес. Су лимитін өзгерпейді. Топырақ ылғалы, жер асты суы, күріш су бастыруы және дақыл күнтізбесі автоматты түрде болжанбайды.',
                            'ru':'Не заменяет приказ №108-НҚ и не меняет жёсткий водный лимит. Влажность почвы, грунтовые воды, затопление риса и фенология не моделируются автоматически. Изменения влажности, ветра и радиации в будущем приняты нулевыми.',
                            'en':'Not the official 108-NQ norm; no changes to the hard water cap. Soil storage, groundwater, paddy flooding and phenology are not inferred. Future RH, wind and solar radiation held fixed.'}[lang])
            st.caption({"kk":"Дереккөз: World Bank CCKP, бұрынғы Yujno-kazachstanskaya аумағы. Апрель-қыркүйек, 1995-2014 базасы. Бұл тарихи ML валидациясын өзгертпейді.",
                        "ru":"Источник: World Bank CCKP, территория Yujno-kazachstanskaya (границы могут отличаться от современных). Апрель-сентябрь, база 1995-2014. Не меняет историческую валидацию ML.",
                        "en":"Source: World Bank CCKP, historic Yujno-kazachstanskaya boundaries may differ from today's. Apr-Sep, 1995-2014 reference. Historical ML validation is unchanged."}[lang])

    # An untouched zero-sized number widget is NOT evidence of measured zero.
    # The user may explicitly confirm a real 0 (rain-fed cultivation, disconnected meter, etc.).
    water_zero_confirmed = False
    energy_zero_confirmed = False
    if float(water_used or 0) == 0.0:
        water_zero_confirmed = st.checkbox({
            'ru':'Подтверждаю: фактически измеренное использование воды равно 0 м³',
            'kk':'Растаймын: нақты өлшенген су пайдалану 0 м³',
            'en':'Confirm measured water consumption is exactly 0 m³',
        }[lang], value=False, key='confirm_observed_zero_water_crop' if mode_key in ('mode1','mode2') else 'confirm_observed_zero_water_'+mode_key)
    if float(energy or 0) == 0.0:
        energy_zero_confirmed = st.checkbox({
            'ru':'Подтверждаю: фактически измеренное потребление электроэнергии равно 0 кВт·ч',
            'kk':'Растаймын: нақты өлшенген электр тұтынуы 0 кВт·сағ',
            'en':'Confirm measured electricity consumption is exactly 0 kWh',
        }[lang], value=False, key='confirm_observed_zero_energy_crop' if mode_key in ('mode1','mode2') else 'confirm_observed_zero_energy_'+mode_key)

    # Explicit accounting boundary: data for the WHOLE holding must not be
    # silently used as consumption of a single crop. The baseline for a plot
    # falls back to a source-labelled reference, not an invented allocation.
    resource_accounting_scope = "assessed_plot"
    if mode_key in ("mode1", "mode2") or mode_key == "mode5":
        resource_accounting_scope = q_radio(
            {"ru":"К какой площади относятся введённые расходы ресурсов?",
             "kk":"Енгізілген ресурстар шығыны қай аумаққа қатысты?",
             "en":"Which area do the entered resource quantities refer to?"}[lang],
            ["assessed_plot", "whole_farm", "unknown"],
            format_func=lambda x: ({
                "assessed_plot":{"ru":"Только животноводческая часть" if mode_key == "mode5" else "Только участок выбранной культуры",
                                 "kk":"Мал шаруашылығы бөлігі ғана" if mode_key == "mode5" else "Таңдалған дақыл танабы ғана",
                                 "en":"Livestock activity only" if mode_key == "mode5" else "Selected crop plot only"},
                "whole_farm":{"ru":"Всё хозяйство, включая другие виды деятельности","kk":"Барлық өндіріс түрлерімен бүкіл шаруашылық","en":"Entire farm including other activities"},
                "unknown":{"ru":"Не могу определить / данные не разделены","kk":"Белгісіз / деректер бөлінбеген","en":"Unknown / not allocated"},
            }[x][lang]),
            index=['assessed_plot','whole_farm','unknown'].index(
                st.session_state.get('qunar_crop_saved_resource_scope','unknown') if mode_key in ('mode1','mode2')
                else st.session_state.get('qunar_saved_resource_scope_'+mode_key,'unknown')),
            key='qunar_crop_resource_scope_widget' if mode_key in ('mode1','mode2') else 'qunar_resource_input_scope_'+mode_key,
            horizontal=False,
            help={"ru":"Например, 120 000 м³ по общему счётчику всего хозяйства нельзя приписывать одному полю подсолнечника. Для участка будут использованы нормативы, пока нет отдельного счётчика или документированного распределения.",
                  "kk":"Жалпы шаруашылық есептегішінің көрсеткішін бір дақылға телуге болмайды; танап бойынша анықтамалық қажеттілік бөлек есептеледі.",
                  "en":"Do not assign whole-farm meter readings to one crop. Plot estimates use documented references until allocation is justified."}[lang],
        )
        if mode_key in ('mode1','mode2'):
            _crop_remember_value('resource_scope', resource_accounting_scope)
        else:
            st.session_state['qunar_saved_resource_scope_'+mode_key] = resource_accounting_scope
        if resource_accounting_scope != "assessed_plot":
            st.info({"ru":"Общие показания воды, электричества и топлива не будут приписаны выбранной культуре или животноводству. Нормативная потребность рассчитывается отдельно и помечается как оценка.",
                     "kk":"Жалпы су, электр және отын шығыны дақылға не мал шаруашылығына тікелей жатқызылмайды. Қажеттілік бөлек анықтамалық есеппен бағаланады.",
                     "en":"Whole-farm water, electricity and fuel are not assigned directly to one crop or livestock activity. Reference resource demand is estimated separately."}[lang])

    # Mandatory energy-source *classification*, not mandatory fossil-fuel consumption.
    # A rain-fed/manual/contractor-powered farm is allowed and is NOT assigned diesel.
    st.caption({
        'ru': 'Обязательное поле ниже. Выберите источники энергии или способ выполнения работ. Оно находится прямо над настройками FAO-56 и кнопкой «Рассчитать».',
        'kk': 'Төмендегі міндетті өрісте энергия көзін немесе жұмысты орындау тәсілін таңдаңыз. Ол FAO-56 параметрлері мен «Есептеу» батырмасының дәл үстінде.',
        'en': 'Required field below: select an energy source or a way of performing farm work. It is immediately above FAO-56 settings and the Calculate button.',
    }[lang])
    # The localized multiselect label changes widget identity on language switch.
    # Restore valid canonical codes rather than silently clearing the user's choice.
    _remembered_sources = [code for code in st.session_state.get('qunar_saved_operational_energy_sources', [])
                           if code in ENERGY_SOURCES]
    selected_energy_sources = st.multiselect(
        {'ru':'Источники энергии и выполнения работ (обязательно)',
         'kk':'Энергия және жұмыс орындалуының көздері (міндетті)',
         'en':'Operational energy/work sources (required)'}[lang],
        options=list(ENERGY_SOURCES), default=_remembered_sources,
        format_func=lambda code: SOURCE_LABELS[lang][code],
        key='farm_operational_energy_sources',
        help={'ru':'Выберите все применяемые источники. Подрядная техника и ручной труд допускаются. Выбор источника не означает известный расход топлива.',
              'kk':'Қолданылатын барлық көздерді таңдаңыз. Мердігер техника мен қол еңбегі болуы мүмкін. Таңдау отын шығынын дәлелдемейді.',
              'en':'Select all that apply. Contracted machinery and manual labour are valid. Selecting a fuel does not establish its consumption.'}[lang])
    st.session_state['qunar_saved_operational_energy_sources'] = list(selected_energy_sources)
    _fuel_observations = {}
    for _src, _units in [('diesel','L'),('petrol','L'),('natural_gas','m³'),('coal','kg'),
                         ('biomass','kg'),('solar_pv','kWh'),('wind','kWh')]:
        if _src in selected_energy_sources:
            _val = q_number_input(
                SOURCE_LABELS[lang][_src] + ' (' + {
                    'L': {'ru':'л', 'kk':'л', 'en':'L'},
                    'kg': {'ru':'кг', 'kk':'кг', 'en':'kg'},
                    'kWh': {'ru':'кВт·ч', 'kk':'кВт·сағ', 'en':'kWh'},
                    'm³': {'ru':'м³', 'kk':'м³', 'en':'m³'},
                }.get(_units, {}).get(lang, _units) + '; '
                + {'ru':'0 = неизвестно', 'kk':'0 = белгісіз', 'en':'0 = unknown'}[lang] + ')',
                min_value=0.0,
                value=float(st.session_state.get('qunar_saved_fuel_'+('crop' if mode_key in ('mode1','mode2') else mode_key)+'_'+_src, 0.0)),
                step=1.0, key='resource_amount_'+('crop' if mode_key in ('mode1','mode2') else mode_key)+'_'+_src)
            st.session_state['qunar_saved_fuel_'+('crop' if mode_key in ('mode1','mode2') else mode_key)+'_'+_src] = float(_val)
            _fuel_observations[_src] = float(_val) if float(_val) > 0 else None

    pumping_confirmed = False
    pump_head_m = None
    pump_efficiency = None
    if ('grid_electricity' in selected_energy_sources or 'solar_pv' in selected_energy_sources
        or 'diesel' in selected_energy_sources):
        with st.expander({'ru':'Параметры насоса для расчёта энергопотребления (при наличии)',
                          'kk':'Энергияны есептеуге арналған сорғы параметрлері (бар болса)',
                          'en':'Pumping energy inputs (if the farm uses a pump)'}[lang], expanded=False):
            pumping_confirmed = st.checkbox({
                'ru':'Вода действительно подаётся насосом',
                'kk':'Су шынында да сорғымен беріледі',
                'en':'The farm actually pumps this water'}[lang], value=False,
                key='pumping_is_used',
                help={'ru':'Отметьте только если хозяйство само перекачивает воду насосом. Для расчёта электричества потребуются напор и КПД. Если услугу перекачки выполняет поставщик по отдельному тарифу, её не нужно учитывать второй раз.',
                      'kk':'Шаруашылық өзі сорғы пайдаланғанда ғана таңдаңыз. Энергия есебіне тегеурін мен ПӘК керек. Жеткізуші сорғысы тарифке кірсе, қайта қоспаңыз.',
                      'en':'Confirm an on-farm pump. Head and efficiency are needed to estimate electricity; do not count supplier pumping twice.'}[lang])
            if pumping_confirmed:
                _h = q_number_input({'ru':'Суммарный напор насоса, м',
                    'kk':'Сорғының жиынтық тегеуріні, м',
                    'en':'Total dynamic pumping head, m'}[lang],
                    min_value=0.0, value=0.0, step=1.0,key='farm_pump_head')
                _eta = q_number_input({'ru':'Суммарный КПД насоса и двигателя, %',
                    'kk':'Сорғы мен қозғалтқыштың жалпы ПӘК, %',
                    'en':'Combined pump + motor efficiency, %'}[lang],
                    min_value=0.0, max_value=100.0, value=0.0, step=1.0,
                    key='farm_pump_efficiency')
                if _h > 0 and _eta > 0:
                    pump_head_m, pump_efficiency = float(_h), float(_eta)/100.0
    # Daily FAO-56 inputs are intentionally ABOVE the Calculate button; outputs
    # appear below the Results heading after the main calculation is submitted.
    _daily_enabled = False
    if mode_key in ('mode1','mode2') and crop in CROP_ROOT_P:
        with st.expander({
            'ru':'FAO-56: суточный баланс влаги почвы и график полива (сценарий)',
            'kk':'FAO-56: топырақтың тәуліктік су балансы және суару күнтізбесі (сценарий)',
            'en':'FAO-56: historical daily root-zone balance and irrigation schedule (scenario)'
        }[lang],expanded=False):
            st.caption({
                'ru':'Это исторический расчёт по ежедневным данным NASA POWER, а не прогноз погоды на 2050 год. Тип почвы и глубина корней — справочные допущения, которые можно изменить. Для риса нужна отдельная модель затопления.',
                'kk':'NASA POWER тарихи тәуліктік деректері: бұл 2050 жылғы ауа райы болжамы емес. Топырақ пен тамыр параметрлері анықтамалық жорамалдар, оларды өзгертуге болады.',
                'en':'Historical NASA POWER daily weather, NOT a 2050 daily forecast. Soil and root values are illustrative, editable assumptions. Paddy rice requires a separate flooded-soil model.'
            }[lang])
            _daily_enabled=st.checkbox({
                'ru':'Включить исторический суточный расчёт FAO-56 при нажатии «Рассчитать»',
                'kk':'«Есептеу» батырмасымен тарихи FAO-56 тәуліктік есебін қосу',
                'en':'Include historical daily FAO-56 balance when calculating'}[lang],
                value=False,key='daily_soil_enable',
                help={'ru':'Суточный расчёт берёт погоду выбранного прошлого года. Не является прогнозом 2040–2059. Для будущих сценариев выберите CMIP6 и месячный FAO-56 выше.',
                      'kk':'Тәуліктік есеп өткен жылдың ауа райын пайдаланады. 2040–2059 болжамы емес; болашақ үшін жоғарыдағы CMIP6 айлық есебін таңдаңыз.',
                      'en':'Daily calculation uses a past weather year, not 2040–2059. For future scenarios use the monthly NASA+CMIP6 comparison above.'}[lang])
            _daily_year=st.selectbox({'ru':'Год исторической погоды','kk':'Тарихи ауа райы жылы','en':'Historical weather year'}[lang],
                                    [2025,2024,2023],key='daily_soil_year')
            _daily_sow=st.date_input({'ru':'Дата посева в выбранном году','kk':'Егу күні','en':'Sowing date'}[lang],
                value=date(_daily_year,4,1),min_value=date(_daily_year,4,1),
                max_value=date(_daily_year,9,15),key=f'daily_soil_sow_{_daily_year}_{crop}')
            _daily_stages=CROP_KC_STAGES[crop][1]
            _daily_stage_text=st.text_input({'ru':'Длительность четырёх фаз роста, дней',
                'kk':'Төрт өсу кезеңінің ұзақтығы, күн','en':'Four crop-stage durations, days'}[lang],
                value=', '.join(map(str,_daily_stages)),key=f'daily_soil_stage_lengths_{crop}')
            _map_soil_state=st.session_state.get('soilgrids_last')
            _mapped_soil_available=bool(_map_soil_state and _map_soil_state[0]==(
                round(float(calc_lat),5),round(float(calc_lon),5)))
            _soil_modes=['fao_reference','measured']+(['mapped_soilgrids'] if _mapped_soil_available else [])
            _daily_soil_mode=st.selectbox({'ru':'Источник параметров почвы','kk':'Топырақ деректерінің көзі',
                'en':'Soil data source'}[lang],_soil_modes,
                format_func=lambda x:{'fao_reference':{'ru':'Справочный профиль FAO AquaCrop',
                    'kk':'FAO AquaCrop анықтамалық топырағы','en':'FAO AquaCrop reference profile'},
                    'measured':{'ru':'Ввести собственные измерения','kk':'Өз өлшемдерін енгізу',
                    'en':'Enter field-measured values'},
                    'mapped_soilgrids':{'ru':'Карта SoilGrids: приблизительная текстура + FAO-параметры',
                    'kk':'SoilGrids: топырақ текстурасы + FAO бағалары',
                    'en':'SoilGrids: mapped indicative texture + FAO parameters'}}[x][lang],key='daily_soil_profile_mode')
            _daily_soil_tex=st.selectbox({'ru':'Тип почвы (для справочного сценария)',
                'kk':'Топырақ түрі','en':'Indicative soil texture'}[lang],list(SOIL_PRESETS),index=list(SOIL_PRESETS).index('loam'),
                format_func=lambda x:{'sand':{'ru':'Песок','kk':'Құм','en':'Sand'},
                  'sandy_loam':{'ru':'Супесь','kk':'Құмдақ','en':'Sandy loam'},
                  'loam':{'ru':'Суглинок','kk':'Саздақ','en':'Loam'},
                  'silt_loam':{'ru':'Пылеватый суглинок','kk':'Шаңды саздақ','en':'Silt loam'},
                  'clay_loam':{'ru':'Глинистый суглинок','kk':'Сазды саздақ','en':'Clay loam'}}[x][lang],
                key='daily_soil_texture')
            _fc,_wp=SOIL_PRESETS[_daily_soil_tex]
            if _daily_soil_mode=='mapped_soilgrids':
                try:
                    _mapped_texture=indicative_texture_from_soilgrids(_map_soil_state[1])
                    _daily_soil_tex=_mapped_texture['faopreset']
                    _fc,_wp=SOIL_PRESETS[_daily_soil_tex]
                    st.caption({'ru':f"SoilGrids: предварительная категория {_daily_soil_tex}, θFC={_fc:.2f}, θWP={_wp:.2f} по FAO. Это не измерения поля!",
                        'kk':f"SoilGrids: {_daily_soil_tex} болжамды текстурасы, FAO θFC={_fc:.2f}, θWP={_wp:.2f}. Өлшем емес!",
                        'en':f"SoilGrids indicative {_daily_soil_tex} texture; FAO θFC={_fc:.2f}, θWP={_wp:.2f}; NOT measured!"}[lang])
                except ValueError as _texture_err:
                    st.error(str(_texture_err))
                    st.stop()
            if _daily_soil_mode=='measured':
                _fc=q_number_input({'ru':'Полевая влагоёмкость (м³/м³)', 'kk':'Егістік ылғал сыйымдылығы (м³/м³)', 'en':'Field capacity (m³/m³)'}[lang],
                    min_value=.05,max_value=.70,value=float(_fc),step=.01,key='daily_soil_fc')
                _wp=q_number_input({'ru':'Влажность завядания (м³/м³)', 'kk':'Солу ылғалдылығы (м³/м³)', 'en':'Wilting point (m³/m³)'}[lang],
                    min_value=0.0,max_value=.65,value=float(_wp),step=.01,key='daily_soil_wp')
            else:
                st.caption({
                    'ru':f'Справочный почвенный сценарий FAO AquaCrop: θFC={_fc:.2f}, θWP={_wp:.2f} м³/м³. ',
                    'kk':f'FAO AquaCrop анықтамалық топырақ сценарийі: θFC={_fc:.2f}, θWP={_wp:.2f} м³/м³. ',
                    'en':f'FAO AquaCrop reference soil scenario: θFC={_fc:.2f}, θWP={_wp:.2f} m³/m³. ',
                }[lang]+FAO_SOIL_PROFILE_SOURCE)
            _root_fao,_p_fao=CROP_ROOT_P[crop]
            _root=q_number_input({'ru':'Глубина корневой зоны, м (справочный максимум FAO)',
                'kk':'Тамыр тереңдігі, м (FAO)','en':'Rooting depth, m (FAO reference)'}[lang],
                min_value=.10,max_value=3.0,value=float(_root_fao),step=.1,key=f'daily_soil_root_{crop}')
            _p=q_number_input({'ru':'Доля доступной влаги до стресса p (FAO-56)',
                'kk':'Стресс басталуындағы ылғал үлесі p','en':'Depletion fraction p (FAO-56)'}[lang],
                min_value=.10,max_value=.80,value=float(_p_fao),step=.05,key=f'daily_soil_p_{crop}')
            _start_frac=st.slider({'ru':'Начальная степень иссушения корневой зоны, % TAW',
                'kk':'Бастапқы ылғал тапшылығы, % TAW','en':'Initial root-zone depletion, % of TAW'}[lang],
                min_value=0,max_value=100,value=50,step=5,key='daily_soil_initial')/100.
            _runoff=st.slider({'ru':'Доля стока при осадках, % (сценарное допущение)',
                'kk':'Жауыннан ағып кететін су, %','en':'Rainfall runoff share, % (assumption)'}[lang],
                0,100,0,5,key='daily_soil_runoff')/100.
            _cr=q_number_input({'ru':'Капиллярное поступление из грунтовых вод, мм/сутки (0 — допущение)',
                'kk':'Жерасты суынан көтерілу, мм/тәулік (0 — жорамал)',
                'en':'Groundwater capillary rise, mm/day (0 is an assumption)'}[lang],
                min_value=0.,max_value=20.,value=0.,step=.5,key='daily_soil_cr')
            _daily_eta_method=st.selectbox({'ru':'Способ полива (справочная эффективность FAO)',
                'kk':'Суару түрі (FAO анықтамалығы)','en':'Irrigation type (FAO reference)'}[lang],
                list(FIELD_EFFICIENCIES),
                format_func=lambda x: {
                    'furrow': {'ru': 'Бороздовой', 'kk': 'Бороздалы', 'en': 'Furrow'},
                    'sprinkler': {'ru': 'Дождевальный', 'kk': 'Жаңбырлатып', 'en': 'Sprinkler'},
                    'drip': {'ru': 'Капельный', 'kk': 'Тамшылатып', 'en': 'Drip'},
                }.get(x, {}).get(lang, x),
                key='daily_soil_irrigation')
            _daily_eta=field_efficiency(_daily_eta_method)
            _daily_sched=st.selectbox({'ru':'Режим расчёта','kk':'Есептеу режимі','en':'Daily schedule mode'}[lang],
                ['auto','rainfed'],format_func=lambda x:{'auto':{'ru':'Иллюстративный автоматический полив по порогу RAW',
                   'kk':'RAW шегіне сай шартты суару','en':'Illustrative RAW-threshold automatic irrigation'},
                   'rainfed':{'ru':'Без орошения (проверка водного стресса)',
                   'kk':'Суарусыз (ылғал тапшылығы)','en':'No irrigation (soil stress case)'}}[x][lang],
                key='daily_soil_sched')
            st.caption({'ru':'После выбора параметров нажмите основную кнопку «Рассчитать» ниже. Суточная модель не изменяет прогноз Random Forest и водный лимит.',
                        'kk':'Параметрлерді таңдағаннан кейін төмендегі «Есептеу» батырмасын басыңыз. Есеп Random Forest пен су лимитін өзгертпейді.',
                        'en':'After setting inputs, click the main Calculate button below. This does not change RF forecasts or water caps.'}[lang])
            _daily_confirm=st.checkbox({'ru':'Подтверждаю: все почвенные параметры, дата посева и потери воды — мои сценарные допущения либо измерения, а не автоматически установленные факты',
                'kk':'Топырақ, егу күні және шығындар өлшенген немесе сценарийлік жорамал екенін растаймын',
                'en':'I confirm soil parameters, crop calendar and water losses are measured or scenario assumptions, not automatically verified facts'}[lang],
                key='daily_soil_assumptions')
            import json as _daily_json
            _daily_geometry_string=(_daily_json.dumps(calc_geojson,sort_keys=True)
                  if location_source=='map' and calc_geojson is not None else None)
            _daily_fingerprint=(crop,_daily_year,str(_daily_sow),_daily_stage_text,
                _daily_geometry_string,
                _daily_soil_mode,_daily_soil_tex,float(_fc),float(_wp),float(_root),
                float(_p),float(_start_frac),float(_runoff),float(_cr),
                _daily_eta_method,_daily_sched,float(calc_lat),float(calc_lon))

    # Scenario configuration belongs to the input area, not beneath Results.
    # Streamlit's container allows us to fill this slot after the main model
    # has produced the reference quantities needed by the comparison.
    _scenario_inputs_slot = st.container() if (user_level != "farmer" and mode_key in ("mode1", "mode5")) else None
    submitted = st.button(t["calculate"], type="primary", use_container_width=True, key="calculate_main")

# Keep the optional scenario controls available while editing them after a run.
# Changes to the inputs are reflected in a new calculation using the same model.
if submitted:
    st.session_state['qunar_calculated_mode'] = mode_key
    st.session_state['qunar_calculated_level'] = user_level
elif (st.session_state.get('qunar_calculated_mode') == mode_key
      and st.session_state.get('qunar_calculated_level') == user_level):
    submitted = True

if submitted:
    if not selected_energy_sources:
        st.error({
            'ru': 'Не выбран источник энергии или выполнения работ. Откройте поле «Источники энергии и выполнения работ (обязательно)» (в основном блоке ввода, прямо над «FAO-56» и кнопкой «Рассчитать») и выберите хотя бы один вариант: электросеть, солнечная энергия, подрядная техника или ручной труд.',
            'kk': 'Энергия не жұмысты орындау көзі таңдалмаған. «Энергия және жұмыс орындалуының көздері (міндетті)» өрісіне өтіңіз (негізгі енгізу бөлімінде, «FAO-56» мен «Есептеу» батырмасының үстінде) және кемінде біреуін таңдаңыз: электр желісі, күн энергиясы, мердігер техника не қол еңбегі.',
            'en': 'No energy or work source selected. Find “Operational energy/work sources (required)” (in the main input section, immediately above FAO-56 and the Calculate button) and choose at least one: grid electricity, solar, contracted machinery, or manual labour.',
        }[lang])
        st.stop()
    validate_energy_sources(selected_energy_sources)
    ga_event("run_assessment", mode_key=mode_key, season_mode=season_mode, calculation_year=calculation_year, user_level=user_level)
    live_ok = False

    reported_farm_resource_context = None
    if mode_key in ('mode1', 'mode2', 'mode5') and resource_accounting_scope != 'assessed_plot':
        reported_farm_resource_context = {
            "water_m3": optional_observation(water_used, measured_zero=water_zero_confirmed),
            "grid_kwh": optional_observation(energy, measured_zero=energy_zero_confirmed),
            "fuel_quantities": dict(_fuel_observations),
        }
        # No area-share shortcut: crop energy and water require crop-specific data
        # or explicit engineering/normative estimation, not division by hectares.
        observed_water = None
        observed_energy = None
        water_zero_confirmed = False
        energy_zero_confirmed = False
        _fuel_observations = {k: None for k in _fuel_observations}
    else:
        observed_water = optional_observation(water_used, measured_zero=water_zero_confirmed)
        observed_energy = optional_observation(energy, measured_zero=energy_zero_confirmed)
    water_default_info = default_water_requirement(used_district, crop, irrigation_type) if crop is not None else None
    if mode_key == 'mode5':
        # Drinking water is a defensible *minimum component*, NOT total livestock operations.
        # No herd count -> no invented herd water benchmark.
        water_reference = livestock_drinking_fallback(livestock_species, livestock_heads,
            observed=observed_water, measured_zero=water_zero_confirmed)
    else:
        water_reference = irrigation_water_fallback(used_district,crop,area_ha,irrigation_type,
            observed=observed_water,measured_zero=water_zero_confirmed)
    effective_water_used = water_reference.value
    if 'grid_electricity' not in selected_energy_sources and observed_energy is not None and observed_energy > 0:
        st.error({'ru':'Указан расход сетевой электроэнергии, но сеть не выбрана среди источников.',
                  'kk':'Желілік электр тұтынуы енгізілген, бірақ желі энергия көзі ретінде таңдалмады.',
                  'en':'Positive grid-electricity consumption was entered without selecting grid electricity.'}[lang])
        st.stop()
    water_input_source = 'user' if water_reference.source_tier == 'user_observed' else water_reference.source_tier
    energy_reference = conditional_pumping_energy(effective_water_used,
        observed=observed_energy, measured_zero=energy_zero_confirmed,
        pumping_confirmed=(pumping_confirmed and 'grid_electricity' in selected_energy_sources and _tariff_water_ref != 'kazvodkhoz_irrigation_pumped_2026'),
        head_m=pump_head_m, overall_efficiency=pump_efficiency)
    if pumping_confirmed and _tariff_water_ref == 'kazvodkhoz_irrigation_pumped_2026':
        st.warning({
            'ru':'Выбран тариф механизированной подачи воды: перекачка поставщика уже включена в эту услугу. Автоматический расчёт энергии собственного насоса отключён, чтобы не начислять одни расходы дважды. Если есть отдельный насос на поле, укажите его фактическую электроэнергию отдельно.',
            'kk':'Механикаландырылған су беру тарифінде жеткізушінің сорғы қызметі бар. Қосарлы есеп болмас үшін жеке сорғы энергиясы автоматты түрде есептелмейді. Танапта бөлек сорғы болса, оның нақты энергиясын жеке енгізіңіз.',
            'en':'Mechanized water supply already includes supplier pumping. Automatic on-farm pump energy is disabled to avoid double charging; enter separately metered downstream pumping if present.'
        }[lang])
    _grid_known = energy_reference.value is not None
    # A missing value is not measured zero. Use one shared source for all modes,
    # including Selected Crop; otherwise mode2 previously raised NameError.
    economic_energy_kwh = (float(observed_energy) if observed_energy is not None
                           else float(energy_reference.value) if energy_reference.value is not None
                           else None)
    economic_energy_source = (
        "user_observed" if observed_energy is not None else
        f"{energy_reference.source_tier}: {energy_reference.source}" if energy_reference.value is not None
        else "unknown_electricity_no_estimate"
    )
    # Methodological references are not measurements; tariff and EF defaults
    # remain labelled scenarios unless an actual bill/factor is entered.

    report_payload = {
        "mode_key": mode_key,
        "report_level": user_level,
        "research_tables": [],
        "lang": lang,
        "brand_acronym": t.get("brand_acronym", ""),
        "brand_translation": t.get("brand_translation", ""),
        "mode_label": t.get(mode_key, mode_key),
        "generated_label": {"kk":"Есеп жасалған уақыт","ru":"Дата расчета","en":"Generated"}[lang],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "assessment_year": calculation_year,
        "assessment_type": assessment_type,
        "climate_period": climate_period_label,
        "summary_title": {"kk":"Негізгі нәтижелер","ru":"Ключевые результаты","en":"Key results"}[lang],
        "indicator_label": {"kk":"Көрсеткіш","ru":"Показатель","en":"Indicator"}[lang],
        "value_label": {"kk":"Мәні","ru":"Значение","en":"Value"}[lang],
        "note_label": {"kk":"Түсіндірме","ru":"Комментарий","en":"Note"}[lang],
        "recommendations_title": {"kk":"Негізгі ұсыныстар","ru":"Ключевые рекомендации","en":"Key recommendations"}[lang],
        "analysis_title": t.get("explanation", {"kk":"Нәтижені талдау","ru":"Анализ результата","en":"Result analysis"}[lang]),
        "inputs_title": {"kk":"Енгізілген деректер және дереккөздер","ru":"Входные данные и источники","en":"Inputs and sources"}[lang],
        "parameter_label": t.get("audit_parameter", {"kk":"Көрсеткіш","ru":"Показатель","en":"Parameter"}[lang]),
        "source_label": t.get("audit_source", {"kk":"Дереккөз / рөл","ru":"Источник / роль","en":"Source / role"}[lang]),
        "table_title": {"kk":"Толық нәтиже","ru":"Подробный результат","en":"Detailed result"}[lang],
        "summary": [], "analysis": [], "recommendations": [], "table": None,
        "inputs": [
            [{"kk":"Бағалау режимі","ru":"Режим оценки","en":"Assessment mode"}[lang], SEASON_MODE_LABELS[season_mode], {"kk":"QŪNAR сценарий логикасы","ru":"Сценарная логика QŪNAR","en":"QŪNAR scenario logic"}[lang]],
            [{"kk":"Есептік жыл","ru":"Расчётный год","en":"Calculation year"}[lang], str(calculation_year), assessment_type],
            [{"kk":"Климаттық терезе","ru":"Климатическое окно","en":"Climate window"}[lang], climate_period_label, {"kk":"Сәуір-қыркүйек базалық спецификациясы","ru":"Базовая спецификация апрель-сентябрь","en":"April-September baseline specification"}[lang]],
            [t["district"], district_label(used_district), {"kk":"Әкімшілік полигон/таңдау","ru":"Административный полигон/выбор","en":"Administrative polygon/selection"}[lang]],
            [area_input_label, f"{area_ha:.2f}", t["source_user"]],
            [{"kk":"Есеп координатасы","ru":"Координаты расчета","en":"Calculation coordinates"}[lang], f"{calc_lat:.6f}, {calc_lon:.6f}", {"kk":"Карта/аудан","ru":"Карта/район","en":"Map/district"}[lang]],
            [available_water_label, f"{available_water:.2f}" if available_water > 0 else {"kk":"белгісіз","ru":"неизвестно","en":"unknown"}[lang], t["source_user"] if available_water > 0 else {"kk":"Енгізілмеген","ru":"Не введено","en":"Not entered"}[lang]],
            [({"kk":"Нақты жылдық су тұтынуы, м³","ru":"Фактическое годовое водопотребление, м³","en":"Observed annual water use, m³"}[lang] if mode_key=="mode5" and water_input_source=="user" else {"kk":"Есепте қолданылған су көлемі, м³","ru":"Объем воды, использованный в расчете, м³","en":"Water volume used in calculation, m³"}[lang]), f"{effective_water_used:.2f}" if effective_water_used is not None else {"kk":"белгісіз","ru":"неизвестно","en":"unknown"}[lang], (t["source_user"] if water_input_source=="user" else (water_reference.source_tier+": "+water_reference.source))],
            [t["energy"], f"{observed_energy:.2f}" if observed_energy is not None else {"kk":"белгісіз","ru":"неизвестно","en":"unknown"}[lang], t["source_user"] if observed_energy is not None else {"kk":"Енгізілмеген","ru":"Не введено","en":"Not entered"}[lang]],
        ]
    }
    if farm_total_area_ha > 0:
        report_payload['inputs'].append([
            {"ru":"Общая площадь хозяйства, га", "kk":"Шаруашылықтың жалпы аумағы, га", "en":"Total farm holding area, ha"}[lang],
            f"{farm_total_area_ha:.2f}",
            {"ru":"Контекст хозяйства, не площадь расчёта по культуре", "kk":"Шаруашылық туралы анықтама, дақыл алаңы емес", "en":"Holding context only, not crop calculation area"}[lang],
        ])
    if polygon_area:
        report_payload['inputs'].append([
            {"ru":"Назначение контура карты", "kk":"Карта контурының мақсаты", "en":"Map polygon scope"}[lang],
            ({"ru":"Всё хозяйство", "kk":"Бүкіл шаруашылық", "en":"Entire farm"}[lang]
             if polygon_scope == "whole_farm" else
             {"ru":"Расчётный участок", "kk":"Есептік танап", "en":"Assessed plot"}[lang]),
            {"ru":"Площадь контура сопоставляется только с указанным назначением", "kk":"Контур алаңы таңдалған аумақ түрімен салыстырылады", "en":"Polygon area compared with declared map scope"}[lang],
        ])
    if mode_key in ("mode1", "mode2") or mode_key == "mode5":
        report_payload['inputs'].append([
            {"ru":"Границы учёта введённых ресурсов", "kk":"Енгізілген ресурс есебінің шекарасы", "en":"Scope of entered resource consumption"}[lang],
            {"assessed_plot":{"ru":"Животноводческая часть" if mode_key == "mode5" else "Участок выбранной культуры",
                               "kk":"Мал шаруашылығы бөлігі" if mode_key == "mode5" else "Таңдалған дақыл танабы",
                               "en":"Livestock activity" if mode_key == "mode5" else "Selected crop plot"},
             "whole_farm":{"ru":"Всё хозяйство", "kk":"Бүкіл шаруашылық", "en":"Entire farm"},
             "unknown":{"ru":"Не установлено", "kk":"Белгісіз", "en":"Not established"}}[resource_accounting_scope][lang],
            {"ru":"Общий расход хозяйства не приписывается отдельной культуре или животноводству без подтверждённого распределения", "kk":"Жалпы шығындар дәлелсіз дақылдарға бөлінбейді", "en":"Whole-farm consumption is not attributed to a crop or livestock activity without justified allocation"}[lang],
        ])
        if reported_farm_resource_context is not None:
            for source_key, val in [
                ("water_m3", reported_farm_resource_context["water_m3"]),
                ("grid_kwh", reported_farm_resource_context["grid_kwh"]),
            ]:
                report_payload['inputs'].append([
                    ({"water_m3":{"ru":"Вода по общему учёту хозяйства, м³", "kk":"Шаруашылық суының жалпы есебі, м³", "en":"Whole-farm water meter, m³"},
                      "grid_kwh":{"ru":"Электроэнергия всего хозяйства, кВт·ч", "kk":"Шаруашылықтың жалпы электрі, кВт·сағ", "en":"Whole-farm purchased electricity, kWh"}}[source_key][lang]),
                    (f"{val:.2f}" if val is not None else {"ru":"нет данных", "kk":"дерек жоқ", "en":"not provided"}[lang]),
                    {"ru":"Только справочный контекст, не включено в расчёт выбранного вида деятельности", "kk":"Тек анықтамалық, таңдалған дақыл есебіне кірмейді", "en":"Context only, excluded from selected activity footprint"}[lang],
                ])
            for source_key, val in reported_farm_resource_context['fuel_quantities'].items():
                report_payload['inputs'].append([
                    SOURCE_LABELS[lang][source_key],
                    f"{val:.2f}" if val is not None else {"ru":"нет данных", "kk":"дерек жоқ", "en":"not provided"}[lang],
                    {"ru":"Общий расход хозяйства, не отнесён на выбранный вид деятельности", "kk":"Шаруашылықтың жалпы шығыны, дақылға жатқызылмаған", "en":"Whole-farm amount, not allocated to selected activity"}[lang],
                ])
    report_payload['inputs'].append([
        {'ru':'Используемые источники энергии / труда', 'kk':'Энергия және еңбек көздері',
         'en':'Operational energy and work sources'}[lang],
        ', '.join(SOURCE_LABELS[lang][code] for code in selected_energy_sources),
        {'ru':'Категории выбраны пользователем; объём ресурса не подтверждается выбором',
         'kk':'Санаттарды пайдаланушы таңдады; мөлшер таңдау арқылы расталмайды',
         'en':'Source categories are user-selected; fuel quantities require separate evidence'}[lang]
    ])
    for _src, _quantity in _fuel_observations.items():
        _unit = {'diesel':'л', 'petrol':'л', 'natural_gas':'м³', 'coal':'кг',
                 'biomass':'кг', 'solar_pv':'кВт·ч', 'wind':'кВт·ч'}[_src]
        report_payload['inputs'].append([
            SOURCE_LABELS[lang][_src],
            f'{_quantity:,.2f} {_unit}' if _quantity is not None else
                {'ru':'неизвестно','kk':'белгісіз','en':'unknown'}[lang],
            {'ru':'Фактическое значение пользователя' if _quantity is not None else 'Не подставлен произвольный расход',
             'kk':'Пайдаланушы енгізген нақты дерек' if _quantity is not None else 'Ерікті шығыс қосылмады',
             'en':'User activity input' if _quantity is not None else 'No unjustified usage substituted'}[lang]
        ])
    if _fuel_observations.get('diesel') is not None:
        report_payload['inputs'].append([
            {'ru':'CO₂ от дизеля, расчётный фактор IPCC', 'kk':'Дизельден CO₂, IPCC факторы',
             'en':'Diesel CO₂, IPCC derived combustion factor'}[lang],
            f"{diesel_combustion_factor():.5f} кг CO₂/л; "
            f"{_fuel_observations['diesel']*diesel_combustion_factor():.2f} кг CO₂",
            SOURCES['ipcc_diesel'].url+'; '+SOURCES['gost_diesel'].url+
            '; 0.84 кг/л, 43 МДж/кг (оценочные параметры); прямое сжигание, не жизненный цикл'
        ])
    for _cost_type,_rate,_doc in (
        ('electricity',electricity_tariff,electricity_tariff_doc),
        ('water',water_tariff,water_tariff_doc)):
        report_payload['inputs'].append([
            {'ru':'Тариф: ','kk':'Тариф: ','en':'Tariff: '}[lang]+_cost_type,
            f'{_rate:.5f} '+('KZT/kWh' if _cost_type=='electricity' else 'KZT/m³'),
            (_doc.provider+'; '+_doc.source+'; '+_doc.caveat if _doc is not None else
             {'ru':'Введённое значение или сценарное значение QŪNAR. Не подтверждено как тариф этого хозяйства.',
              'kk':'Пайдаланушы енгізген немесе QŪNAR сценарийлік мәні. Шаруашылықтың нақты тарифі екені расталмаған.',
              'en':'User-entered or QŪNAR scenario value; not verified as the farm contract tariff.'}[lang])
        ])
    report_payload['inputs'].append([
        {'ru':'Коэффициент выбросов сетевой электроэнергии', 'kk':'Желілік электр энергиясының эмиссия коэффициенті',
         'en':'Grid electricity emission factor'}[lang],
        f'{ef:.5f} кг CO₂/кВт·ч',
        (SOURCES['ember_kazakhstan_'+_grid_ef_source[-4:]].name+'; '+SOURCES['ember_kazakhstan_'+_grid_ef_source[-4:]].url+
         '; generation-average CO2 factor, not full CO2e or a contractual grid factor'
         if _grid_ef_source.startswith('ember') else
         {'ru':'Редактируемое допущение QŪNAR (национальный официальный фактор не подтверждён)',
          'kk':'QŪNAR-дың өзгертілетін болжамы (ресми ұлттық коэффициент расталмаған)',
          'en':'Editable QŪNAR scenario assumption (no verified official national factor)'}[lang])
    ])
    report_payload['inputs'].append([
        {'ru':'Статус автоматических подстановок', 'kk':'Автоматты алмастыру мәртебесі',
         'en':'Reference imputation status'}[lang],
        {'ru':'Справочно-сценарный расчёт', 'kk':'Анықтамалық-сценарийлік есеп',
         'en':'Reference-based scenario calculation'}[lang],
        source_disclaimer(lang)
    ])
    report_payload['inputs'].append([
        {'ru':'Вода: измерение либо справочная потребность',
         'kk':'Су: нақты мән немесе алмастыру','en':'Water: observation or fallback'}[lang],
        'нет данных' if effective_water_used is None else f'{effective_water_used:,.2f} м³',
        water_reference.source_tier + ': ' + water_reference.source + ('; '+water_reference.url if water_reference.url else '')
        + ('; '+water_reference.caveat if water_reference.caveat else '')
    ])
    report_payload['inputs'].append([
        {'ru':'Электроэнергия: фактическое значение / отсутствие',
         'kk':'Электр энергиясы: нақты / белгісіз','en':'Electricity: observed / unknown'}[lang],
        'нет данных' if energy_reference.value is None else f'{energy_reference.value:,.2f} кВт·ч',
        energy_reference.source_tier + ': ' + energy_reference.source
    ])
    if crop is not None:
        report_payload["inputs"].append([t["crop"], extended_crop_label(crop, lang), t["source_user"]])
        if variable_cost_kzt_ha <= 0:
            _hist_costs = historic_cost_mix(crop)
            if _hist_costs:
                _mix_min = min(row['historic_share_wages_fuel_seeds'] for row in _hist_costs)*100
                _mix_max = max(row['historic_share_wages_fuel_seeds'] for row in _hist_costs)*100
                report_payload['inputs'].append([
                    {'ru':'Историческая структура затрат, доля зарплаты/ГСМ/семян',
                     'kk':'Тарихи шығын құрылымы: еңбекақы/ЖЖМ/тұқым үлесі',
                     'en':'Historical cost structure, wages/fuel/seeds share'}[lang],
                    f'{_mix_min:.1f}%-{_mix_max:.1f}% (2004)',
                    HISTORIC_SOUTH_CROP_COST_SOURCE + '; '+
                    {'ru':'Исторические нормы бывшей Южно-Казахстанской области. Не являются себестоимостью 2026 года: современная маржа не рассчитывается без актуальных затрат.',
                     'kk':'Бұрынғы Оңтүстік Қазақстан облысының тарихи нормалары. 2026 жылғы өзіндік құн емес; ағымдағы шығынсыз маржа есептелмейді.',
                     'en':'Historical norms for former South Kazakhstan; NOT current KZT/ha costs. Margin is unavailable without current costs.'}[lang]
                ])
    if mode_key == "mode5":
        livestock_head_source_label = (
            t["source_user"] if livestock_heads > 0
            else {"kk":"Енгізілмеген; аудан дерегі тек салыстыру үшін", "ru":"Не введено; районный показатель отдельно для справки", "en":"Not entered; district statistic is separate context"}[lang]
        )
        feed_source_label = (
            t["source_user"] if livestock_feed_source == "own"
            else {"kk":"Белгісіз; QŪNAR анықтамалық қажеттілікті бөлек есептейді","ru":"Неизвестно; QŪNAR отдельно рассчитывает справочную потребность","en":"Unknown; QŪNAR calculates reference requirement separately"}[lang]
        )
        production_source_label = (
            t["source_user"] if livestock_production_amount > 0
            else {"kk":"Белгісіз","ru":"Неизвестно","en":"Unknown"}[lang]
        )
        report_payload["inputs"].extend([
            [{"kk":"Мал түрі","ru":"Вид животных","en":"Livestock type"}[lang], SPECIES_LABELS[lang][livestock_species], t["source_user"]],
            [{"kk":"Мал саны","ru":"Поголовье","en":"Animals"}[lang], f"{livestock_heads:.0f}" if livestock_heads > 0 else {"kk":"енгізілмеген","ru":"не введено","en":"not entered"}[lang], livestock_head_source_label],
            [{"kk":"Жемшөп қоры","ru":"Запас кормов","en":"Feed reserve"}[lang], f"{livestock_fodder_t:.2f} {UNITS['dry_t']}" if livestock_feed_source == "own" else {"kk":"белгісіз","ru":"неизвестно","en":"unknown"}[lang], feed_source_label],
            [{"kk":"Өнім түрі","ru":"Вид продукции","en":"Product type"}[lang], PRODUCT_LABELS[lang][livestock_production_kind], t["source_user"]],
            [({"kk":"Өнім көлемі, мың дана","ru":"Объём продукции, тыс. шт.","en":"Production volume, thousand pieces"}[lang]
              if livestock_production_kind == 'thousand_eggs' else
              {"kk":"Өнім көлемі, т","ru":"Объём продукции, т","en":"Production volume, t"}[lang]), f"{livestock_production_amount:g}" if livestock_production_amount > 0 else {"kk":"белгісіз","ru":"неизвестно","en":"unknown"}[lang], production_source_label],
        ])
    climate = district_climate(used_district) or {}
    baseline_climate = dict(climate)
    climate_source = t["fallback_source"]
    climate_period_actual = climate_period_label
    partial_season = False

    if season_mode == "next":
        # Future weather cannot be observed. User map means historical NASA
        # climatology at exactly that location, NEVER a district centroid in disguise.
        if location_source == 'map' and calc_geojson is not None:
            try:
                _normal = timed_call('NASA POWER polygon historical normal',
                    _cached_farm_climate_normal,float(calc_lat),float(calc_lon),calc_geojson)
                climate = {**climate,**_normal}
                if _normal.get('estimated_monthly_values'):
                    st.warning({'ru':'NASA POWER: отдельные месяцы климатической базы восстановлены линейной интерполяцией; это оценочные значения.',
                        'kk':'NASA POWER: кейбір айлық мәндер сызықтық интерполяциямен бағаланды.',
                        'en':'NASA POWER: isolated climatology-month gaps were linearly interpolated and labelled estimates.'}[lang])
                    report_payload['inputs'].append(['NASA POWER monthly imputations',
                        str(_normal['estimated_monthly_values']), 'bounded annual adjacent-month interpolation'])
                climate_source = _normal['source']
                climate_period_actual = _normal['period_start']+' / '+_normal['period_end']
                report_payload['inputs'].append(['NASA POWER farm polygon climatology',
                    f"{_normal['polygon_sample_count']} nominal cells, 1995-2025; user geometry",
                    _normal['source']])
                st.caption({'ru':f"Планирование: историческая климатическая норма NASA POWER непосредственно по контуру ({_normal['polygon_sample_count']} ячеек). Это не фактическая погода будущего сезона.",
                    'kk':f"Жоспарлау: шаруашылық контурындағы NASA POWER тарихи климаттық нормасы ({_normal['polygon_sample_count']} ұяшық), болашақ ауа райы емес.",
                    'en':f"Planning: NASA POWER 1995-2025 climatology at user polygon ({_normal['polygon_sample_count']} cells), not future observations."}[lang])
                live_ok = True
            except (ValueError,KeyError,requests.exceptions.RequestException) as _normal_error:
                st.error({'ru':'NASA POWER не предоставил климат для нарисованного участка. Районный центроид НЕ подставлен незаметно. Выберите режим «по району» для отдельного районного расчёта. Ошибка: ',
                    'kk':'NASA POWER осы алқаптың климаты бойынша жауап бермеді. Аудан орталығы автоматты түрде алмастырылған жоқ. Қате: ',
                    'en':'NASA POWER polygon climate unavailable. District centroid was NOT silently substituted; switch to district mode explicitly. Error: '}[lang]+str(_normal_error))
                st.stop()
        else:
            climate_source = {"kk":"2004-2025 тарихи аудандық климаттық профиль","ru":"Исторический районный климатический профиль 2004-2025","en":"Historical district climate profile, 2004-2025"}[lang]
    else:
        try:
            with st.spinner(t["nasa_loading"]):
                if location_source == 'map' and calc_geojson is not None:
                    nasa = timed_call('NASA POWER polygon', fetch_polygon_growing_season,
                        calc_geojson, calculation_year, fetch_point=fetch_growing_season)
                else:
                    nasa = timed_call('NASA POWER',fetch_growing_season,calc_lat,calc_lon,calculation_year)
            climate = {**climate, **nasa}
            if nasa.get('interpolated_daily_values',0):
                st.warning({'ru':f"NASA POWER: {nasa['interpolated_daily_values']} значений восстановлены по соседним дням и являются оценочными.",
                    'kk':f"NASA POWER: {nasa['interpolated_daily_values']} мән іргелес күндерден интерполяцияланды (баға).",
                    'en':f"NASA POWER: {nasa['interpolated_daily_values']} values interpolated from adjacent days (estimates)."}[lang])
                report_payload['inputs'].append(['NASA POWER temporal data quality',
                    f"Interpolated elements {nasa['interpolated_daily_values']}",nasa.get('quality','estimated')])
            if nasa.get('polygon_sample_count'):
                _n_nasa = nasa['polygon_sample_count']
                st.caption({"kk":f"NASA POWER: контур {int(_n_nasa)} тор нүктесі бойынша жуықтап біріктірілді. Шағын алқапта бір ғана тор ұяшығы болуы қалыпты.",
                            "ru":f"NASA POWER: ориентировочное усреднение по {int(_n_nasa)} точкам сетки контура. Для небольшого поля одна ячейка нормальна.",
                            "en":f"NASA POWER: approximate polygon averaging over {int(_n_nasa)} grid samples. A small field usually fits one cell."}[lang])
                report_payload['inputs'].append([{'ru':'NASA POWER, пространственный метод','kk':'NASA POWER кеңістіктік тәсілі','en':'NASA POWER spatial method'}[lang],
                                                f'Area-weighted nominal grid samples: {_n_nasa}',
                                                'NASA POWER 0.5°x0.625° meteorology; solar source is coarser'])
            climate_source = t["live_source"]
            climate_period_actual = f"{nasa.get('period_start','')}-{nasa.get('period_end','')}"
            partial_season = bool(nasa.get("partial_season", False))
            live_ok = True
        except Exception as _nasa_error:
            if location_source == 'map' and calc_geojson is not None:
                st.error({'ru':'NASA POWER по контуру недоступен. Районные данные автоматически НЕ подставлены. Для районной оценки переключите источник геоданных. Ошибка: ',
                          'kk':'Контур үшін NASA POWER қолжетімсіз. Аудандық деректер автоматты алмастырылмады. Қате: ',
                          'en':'NASA polygon API unavailable; district climate NOT silently substituted. Switch explicitly to district mode. Error: '}[lang]+str(_nasa_error))
                st.stop()
            st.warning(t["nasa_error"]+f' ({_nasa_error})')

    if location_source == 'map' and calc_geojson is not None:
        with st.expander({'ru':'Почвенные свойства выбранного участка — SoilGrids (справочно)',
                         'kk':'Алқаптың топырақ қасиеттері — SoilGrids (анықтамалық)',
                         'en':'Location-specific soil properties — SoilGrids reference'}[lang], expanded=False):
            st.caption({'ru':'ISRIC SoilGrids (250 м): прогнозные pH, углерод, азот, текстура и ёмкость катионного обмена. Это НЕ измеренное плодородие и НЕ анализ всего полигона. API ISRIC может быть временно недоступен.',
                        'kk':'ISRIC SoilGrids (250 м): рН, көміртек, азот, гранулометрия және катионалмасу сыйымдылығы. Бұл өлшенген құнарлылық емес; API қолжетімсіз болуы мүмкін.',
                        'en':'ISRIC SoilGrids (250 m) maps pH, carbon, nitrogen, texture, CEC. This is a single-point prediction, NOT measured fertility or field-average. API may be unavailable.'}[lang])
            _soil_loc=(round(float(calc_lat),5),round(float(calc_lon),5))
            if st.button({'ru':'Запросить почвенные свойства по координатам',
                          'kk':'Координат бойынша топырақ қасиеттерін алу',
                          'en':'Request soil properties for location'}[lang],key='request_soilgrids'):
                try:
                    _soil_ref=_cached_soilgrids_reference(*_soil_loc)
                    st.session_state['soilgrids_last']=(_soil_loc,_soil_ref)
                except (ValueError,KeyError,requests.exceptions.RequestException) as _soil_fetch_error:
                    st.warning({'ru':'Почвенные данные недоступны (отсутствие данных не равно нулю): ',
                                'kk':'Топырақ деректері қолжетімсіз (нөл емес): ',
                                'en':'Mapped soil unavailable; missing is not zero: '}[lang]+str(_soil_fetch_error))
            _soil_last=st.session_state.get('soilgrids_last')
            if _soil_last and _soil_last[0]==_soil_loc:
                _soil_data=_soil_last[1]
                st.dataframe(pd.DataFrame([
                    {'Property':_name,'Depth':_depth,'Value':_val,
                     'Unit':_soil_data['units'].get(_name,'as published')}
                    for _name,_depth_values in _soil_data['values'].items()
                    for _depth,_val in _depth_values.items()]),hide_index=True)
                st.caption(_soil_data['note']+' '+SOILGRIDS_DOCS)
                report_payload['inputs'].append(['SoilGrids point soil context',
                   f"{_soil_loc}: {_soil_data['values']}",_soil_data['source']+'; single sampled pixel; not a fertility index'])

    st.subheader(t["results"])
    st.caption({"kk":f"Бағалау: {SEASON_MODE_LABELS[season_mode]} | есептік жыл: {calculation_year} | климаттық кезең: {climate_period_actual}" + (" | маусым әлі аяқталмаған" if partial_season else ""),"ru":f"Оценка: {SEASON_MODE_LABELS[season_mode]} | расчётный год: {calculation_year} | климатический период: {climate_period_actual}" + (" | сезон ещё не завершён" if partial_season else ""),"en":f"Assessment: {SEASON_MODE_LABELS[season_mode]} | calculation year: {calculation_year} | climate period: {climate_period_actual}" + (" | season is still incomplete" if partial_season else "")}[lang])
    if climate_future_scenario != "none":
        try:
            _cm = load_scenario(DATA_DIR / "cmip6", climate_future_scenario).as_dict()
            st.markdown("#### " + {"kk":"CMIP6 болашақ климаты","ru":"Будущий климат CMIP6","en":"CMIP6 future climate"}[lang])
            _c1, _c2, _c3 = st.columns(3)
            _c1.metric({"kk":"Температура өзгерісі","ru":"Изменение температуры","en":"Temperature change"}[lang], f"{_cm['temperature_change_c']:+.2f} °C")
            _c2.metric({"kk":"Жауын-шашын өзгерісі","ru":"Изменение осадков","en":"Precipitation change"}[lang], f"{_cm['precipitation_change_pct']:+.2f}%")
            _c3.metric({"kk":"40 °C-тан жоғары күндер","ru":"Дней выше 40 °C","en":"Days above 40 °C"}[lang], f"{_cm['days_over_40']:.2f}")
            st.caption({"kk":"Бұл жалпы облыстық сценарий: жеке алаңға болжам емес. Ауа райы, өнімділік пен су қажеттілігі автоматты түрде түзетілмейді; тарихи бағалау өзгеріссіз қалды.",
                        "ru":"Региональный сценарий, а не прогноз для конкретного поля. Он пока не меняет автоматически урожайность, водные нормы и основной оптимизационный расчёт. Аномалии осадков использованы из таблицы Anomaly.",
                        "en":"Regional scenario, not field-level weather. Does not automatically alter yields, irrigation norms or primary optimization. Precipitation changes are from the Anomaly table."}[lang])
            if climate_water_proxy_enabled and mode_key in ('mode1','mode2') and (effective_water_used is not None and effective_water_used > 0):
                try:
                    _baseline_t = float(baseline_climate['Apr-Sep temperature, °C'])
                    _wt = temperature_only_water_sensitivity(
                        effective_water_used, _baseline_t, _cm['temperature_change_c'])
                    st.metric({"kk":"Су стресс-проксиі, м³","ru":"Температурный водный прокси, м³","en":"Temperature-only water proxy, m³"}[lang],
                              f"{_wt.reference_only_water_m3:,.0f}", f"{(_wt.temperature_term_multiplier-1)*100:+.2f}%")
                    st.caption({"kk":"Бұл есептік прокси, дақылға нақты суару қажеттілігі де, ресми су нормасы да емес.",
                                "ru":"Прокси при фиксированных прочих факторах, а не реальная потребность в поливной воде или официальная норма.",
                                "en":"Proxy holding other factors fixed, not crop irrigation demand or an official norm."}[lang])
                    report_payload['summary'].append({'label':'CMIP6 temperature-only water proxy, m³',
                                                      'value':f"{_wt.reference_only_water_m3:,.0f}",
                                                      'note':'Sensitivity, NOT FAO-56 ETc or official irrigation norm'})
                except (ValueError,KeyError) as _werr:
                    st.caption(str(_werr))
            _season_note = {
                "kk":"CCKP, 2040-2059, 1995-2014 базасы; өңірлік сценарий",
                "ru":"CCKP, 2040-2059 к базе 1995-2014; региональный сценарий",
                "en":"CCKP, 2040-2059 vs 1995-2014; regional scenario"}[lang]
            _heat_note = {
                "kk":"Маусымдық орташа күн саны, шаруашылықта өлшенген жоқ",
                "ru":"Среднемноголетнее число дней за сезон, не измерение хозяйства",
                "en":"Seasonal mean count, not observed at farm"}[lang]
            report_payload["summary"].extend([
                {"label":"CMIP6 " + climate_future_scenario + " ΔT (°C)","value":f"{_cm['temperature_change_c']:+.2f}","note":_season_note},
                {"label":"CMIP6 " + climate_future_scenario + " ΔP (%)","value":f"{_cm['precipitation_change_pct']:+.2f}",
                 "note":{"kk":"CCKP Anomaly: сәуір-қыркүйек, алқаптағы жауын-шашын емес",
                         "ru":"CCKP Anomaly: апрель-сентябрь, не осадки отдельного поля",
                         "en":"CCKP Anomaly: Apr-Sep, not individual field rainfall"}[lang]},
                *[{"label": {"kk":f"CMIP6 {climate_future_scenario}: {level} °C-тан жоғары күндер",
                              "ru":f"CMIP6 {climate_future_scenario}: дней выше {level} °C",
                              "en":f"CMIP6 {climate_future_scenario}: days above {level} °C"}[lang],
                   "value": f"{_cm[f'days_over_{level}']:.2f}", "note": _heat_note}
                  for level in (35,40,45)]
            ])
            report_payload["inputs"].append([
                {"kk":"CMIP6 болашақ сценарийі", "ru":"Сценарий CMIP6", "en":"CMIP6 future scenario"}[lang],
                f"{climate_future_scenario}, { _cm['period'] }",
                _season_note])
        except (ValueError, OSError, KeyError) as _cm_err:
            st.warning({"kk":"CMIP6 деректерін оқу мүмкін болмады.","ru":"Не удалось прочитать сценарий CMIP6.","en":"Could not read CMIP6 scenario data."}[lang] + f" ({_cm_err})")

    if fao56_enabled and climate_future_scenario != 'none' and mode_key in ('mode1','mode2'):
        st.markdown('#### '+{'kk':'FAO-56 айлық су сценарийі','ru':'Водный сценарий FAO-56','en':'FAO-56 irrigation scenario'}[lang])
        try:
            _kc=(parse_kc_monthly(fao56_kc_text) if fao56_kc_mode=='manual'
                 else monthly_kc_from_calendar(crop,fao56_sowing_date,
                        parse_stage_lengths(fao56_stage_lengths_text))
                        if fao56_kc_mode=='fao_crop_stages' else None)
            if _kc is not None and fao56_rain_method=='fao_training' and fao56_efficiency_source=='mixed_area_shares':
                fao56_efficiency=mixed_efficiency(fao56_mixed_shares)
            with st.spinner({'ru':'Загрузка месячной климатической базы NASA POWER (1995–2014)...',
                             'kk':'NASA POWER айлық климат деректері жүктелуде...',
                             'en':'Loading NASA POWER baseline monthly climate (1995-2014)...'}[lang]):
                if location_source=='map' and calc_geojson is not None:
                    _w56=fetch_polygon_monthly_climatology(calc_geojson,
                         fetch_point=_cached_fao56_historical_power,max_samples=8)
                    _geo_note='NASA POWER: area-weighted nominal polygon cells'
                else:
                    _w56=_cached_fao56_historical_power(float(calc_lat),float(calc_lon))
                    _geo_note='NASA POWER: representative coordinate'
            _est56=[code for rec in _w56 for code in rec.estimated_values]
            if _est56:
                st.warning({'ru':f'FAO-56: {len(_est56)} исходных значений NASA помечены как интерполированные.',
                    'kk':f'FAO-56: NASA-ның {len(_est56)} бастапқы мәні интерполяцияланды.',
                    'en':f'FAO-56: {len(_est56)} NASA source values were interpolated.'}[lang])
                report_payload['inputs'].append(['FAO-56 NASA monthly imputation',str(_est56),'NASA POWER temporal interpolation, estimated'])
            _c56=load_scenario(DATA_DIR/'cmip6',climate_future_scenario)
            _v56=evaluate_irrigation_scenario(
                _w56,_c56,float(calc_lat),kc_monthly=_kc,
                effective_rainfall=('fao_training' if _kc is not None and fao56_rain_method=='fao_training' else None),
                application_efficiency=(float(fao56_efficiency) if _kc is not None and fao56_rain_method=='fao_training' else None),
                area_ha=(float(area_ha) if _kc is not None and fao56_rain_method=='fao_training' else None),
                weather_source=_geo_note+'; NASA POWER historical 1995-2014')
            _summary56=_v56['totals']
            # Different methodology, period, Kc, rainfall and application
            # efficiencies: keep the historical official norm separate.
            _ref_norm=(water_default_info.m3_ha if water_default_info is not None else None)
            _water_method_crosscheck=norm_vs_fao_comparison(
                _ref_norm,_summary56.get('baseline_gross_irrigation_m3_ha'))
            if _water_method_crosscheck:
                _ratio=_water_method_crosscheck['ratio_fao_to_norm']
                _comparison_note={
                    'ru':f'Справочная норма: {_ref_norm:,.0f} м³/га; FAO-56 (историческая климатическая база): {_water_method_crosscheck["fao_m3_ha"]:,.0f} м³/га. Отношение FAO/норма = {_ratio:.2f}. Это НЕ две взаимозаменяемые оценки: могут различаться период, Kc, эффективные осадки, КПД и методические границы. Разность НЕ является экономией или ошибкой нормы.',
                    'kk':f'Анықтамалық норма: {_ref_norm:,.0f} м³/га; FAO-56 (тарихи климат): {_water_method_crosscheck["fao_m3_ha"]:,.0f} м³/га. Қатынас = {_ratio:.2f}. Әдістер, кезең, Kc, жауын және ПӘК әртүрлі; айырма үнем не норманың қатесі емес.',
                    'en':f'Reference norm: {_ref_norm:,.0f} m³/ha; FAO-56 historical baseline: {_water_method_crosscheck["fao_m3_ha"]:,.0f} m³/ha. Ratio = {_ratio:.2f}. Different methods, phenology, effective rain and application efficiency; their difference is NOT observed saving or proof of norm error.'}[lang]
                (st.warning if _water_method_crosscheck['material_difference'] else st.info)(_comparison_note)
                report_payload['inputs'].append([
                    {'ru':'Сопоставимость нормативов и FAO-56','kk':'Норма мен FAO-56 салыстырмалылығы','en':'Normative vs FAO-56 comparability'}[lang],
                    f'{_ref_norm:.1f} / {_water_method_crosscheck["fao_m3_ha"]:.1f} m³/ha; ratio={_ratio:.2f}',
                    _comparison_note])

            # Both scenarios are derived from the same historical NASA reference
            # and are not merged into the historical observations or RF features.
            _fao56_compare = {}
            for _ssp_name in ('SSP2-4.5', 'SSP5-8.5'):
                _ssp_eval = (_v56 if _ssp_name == climate_future_scenario else
                    evaluate_irrigation_scenario(_w56,load_scenario(DATA_DIR/'cmip6',_ssp_name),
                        float(calc_lat),kc_monthly=_kc,
                        effective_rainfall=('fao_training' if _kc is not None and fao56_rain_method=='fao_training' else None),
                        application_efficiency=(float(fao56_efficiency) if _kc is not None and fao56_rain_method=='fao_training' else None),
                        area_ha=(float(area_ha) if _kc is not None and fao56_rain_method=='fao_training' else None),
                        weather_source=_geo_note+'; NASA POWER historical 1995-2014'))
                _fao56_compare[_ssp_name] = _ssp_eval['totals']
            st.markdown('##### '+{'ru':'Сравнение FAO-56: оба климатических сценария 2040–2059',
                'kk':'FAO-56 салыстыруы: екі климат сценарийі, 2040–2059',
                'en':'FAO-56 comparison: both 2040–2059 climate scenarios'}[lang])
            _cols56={
                'name':{'ru':'Климатический вариант','kk':'Климат нұсқасы','en':'Climate option'}[lang],
                'et0':{'ru':'ET₀, мм за апрель–сентябрь','kk':'ET₀, мм, сәуір–қыркүйек','en':'ET₀, Apr–Sep, mm'}[lang],
                'etc':{'ru':'ETc культуры, мм','kk':'ETc, мм','en':'Crop ETc, mm'}[lang],
                'water':{'ru':'Подача воды, м³/га','kk':'Су беру, м³/га','en':'Field delivery, m³/ha'}[lang],
            }
            _reference56 = {k:v for k,v in {
                'baseline_et0_mm':_summary56['baseline_et0_mm'],
                'baseline_etc_mm':_summary56.get('baseline_etc_mm'),
                'baseline_gross_irrigation_m3_ha':_summary56.get('baseline_gross_irrigation_m3_ha')
            }.items() if v is not None}
            _cmp_rows=[]
            for _caption,_metric_values,_suffix in [
                ({'ru':'Историческая база NASA 1995–2014','kk':'NASA тарихи базасы 1995–2014','en':'NASA 1995–2014 baseline'}[lang],_reference56,'baseline'),
                ('SSP2-4.5',_fao56_compare['SSP2-4.5'],'future'),
                ('SSP5-8.5',_fao56_compare['SSP5-8.5'],'future')]:
                _cmp_rows.append({
                    _cols56['name']:_caption,
                    _cols56['et0']:round(_metric_values[f'{_suffix}_et0_mm'],1),
                    _cols56['etc']:(round(_metric_values[f'{_suffix}_etc_mm'],1) if f'{_suffix}_etc_mm' in _metric_values else None),
                    _cols56['water']:(round(_metric_values[f'{_suffix}_gross_irrigation_m3_ha'],1) if f'{_suffix}_gross_irrigation_m3_ha' in _metric_values else None),
                })
            st.dataframe(pd.DataFrame(_cmp_rows),hide_index=True,use_container_width=True)
            st.caption({'ru':'Единая база NASA POWER 1995–2014 и помесячные аномалии World Bank CCKP. Влажность, ветер, радиация и давление в будущих сценариях сохранены на историческом уровне. ETc требует Kc, а подача воды - дополнительно эффективных осадков и КПД полива. Прочерк означает неизвестное, а не ноль. Это сценарий, не прогноз погоды 2050 года.',
                'kk':'NASA POWER 1995–2014 негізі мен CCKP айлық аномалиялары. Болашақта ылғалдылық, жел, радиация мен қысым өзгермейді деп алынған. ETc үшін Kc, ал су беру үшін тиімді жауын мен ПӘК қажет. Бос орын нөл емес; бұл ауа райы болжамы емес.',
                'en':'Common NASA POWER 1995–2014 baseline with CCKP monthly anomalies. Future humidity, wind, solar and pressure are held fixed. Crop ETc requires Kc; delivery needs effective rain and efficiency. Blank means unavailable, not zero. This is a scenario, not a 2050 weather forecast.'}[lang])
            for _r56 in _cmp_rows:
                report_payload['summary'].append({'label':str(_r56[_cols56['name']])+' - '+_cols56['et0'],
                    'value':str(_r56[_cols56['et0']]),
                    'note':{'ru':'NASA POWER 1995–2014 и месячные аномалии CCKP; FAO-56, остальные климатические параметры фиксированы', 'kk':'NASA POWER 1995–2014 және CCKP айлық ауытқулары; FAO-56, қалған климаттық көрсеткіштер тұрақты', 'en':'NASA POWER 1995–2014 + CCKP monthly anomalies; FAO-56, other climate parameters fixed'}[lang]})
                for _ckey in ('etc','water'):
                    if _r56[_cols56[_ckey]] is not None:
                        report_payload['summary'].append({'label':str(_r56[_cols56['name']])+' - '+_cols56[_ckey],
                            'value':str(_r56[_cols56[_ckey]]),
                            'note':{'ru':'FAO-56: справочные Kc, эффективные осадки и КПД, если заданы; только сценарий', 'kk':'FAO-56: Kc, тиімді жауын-шашын және ПӘК берілсе; сценарийлік нәтиже', 'en':'FAO-56: documented Kc, effective rain and field efficiency if supplied; scenario only'}[lang]})
            _a,_b=st.columns(2)
            _a.metric({'ru':'ET₀ апрель–сентябрь, историческая NASA, мм','kk':'NASA тарихи ET₀ сәуір–қыркүйек, мм','en':'ET₀ Apr-Sep, NASA baseline (mm)'}[lang], f"{_summary56['baseline_et0_mm']:.1f}")
            _b.metric({'ru':'ET₀ апрель–сентябрь, сценарий CMIP6, мм','kk':'CMIP6 ET₀ сәуір–қыркүйек, мм','en':'ET₀ Apr-Sep, CMIP6 scenario (mm)'}[lang], f"{_summary56['future_et0_mm']:.1f}")
            if 'future_etc_mm' in _summary56:
                st.metric({'ru':'ETc культуры, апрель–сентябрь, мм','kk':'Дақылдың ETc сәуір–қыркүйек, мм','en':'ETc Apr-Sep, crop scenario (mm)'}[lang],f"{_summary56['future_etc_mm']:.1f}")
            if 'future_gross_irrigation_m3_ha' in _summary56:
                st.metric('Estimated gross irrigation (m³/ha)',
                         f"{_summary56['future_gross_irrigation_m3_ha']:,.0f}",
                         f"{_summary56['future_gross_irrigation_m3_ha']-_summary56['baseline_gross_irrigation_m3_ha']:+,.0f}")
            if (fao56_target_method!='none' and
                    'future_net_irrigation_mm' in _summary56 and fao56_efficiency is not None):
                _w56comp=irrigation_saving(_summary56['future_net_irrigation_mm']*10,
                    fao56_efficiency,field_efficiency(fao56_target_method),area_ha=float(area_ha))
                st.metric({'ru':'Сценарная экономия подачи воды при смене способа, м³/га',
                           'kk':'Суару тәсілін өзгерткендегі су үнемі, м³/га',
                           'en':'Conditional field water delivery saving, m³/ha'}[lang],
                          f"{_w56comp['saving_m3_ha']:,.0f}",f"{_w56comp['saving_pct']:+.1f}%")
                st.caption({'ru':'FAO: сравнение при одной и той же чистой потребности культуры. Это не подтверждённая экономия хозяйства и не снижение безвозвратного водопотребления.',
                            'kk':'FAO анықтамалық сценарийі, нақты шаруашылықтың үнемі емес.',
                            'en':'FAO reference comparison at unchanged net crop need, not measured farm or consumptive saving.'}[lang])
                report_payload['summary'].append({'label':'FAO field water delivery saving, m³/ha',
                    'value':f"{_w56comp['saving_m3_ha']:.3f}",
                    'note':f"Reference comparison: {irrigation_type} eta={fao56_efficiency:.3f} to {fao56_target_method} eta={FIELD_EFFICIENCIES[fao56_target_method]:.3f}; {FAO_EFFICIENCY_URL}; not observed."})
            if (fao56_target_method!='none' and
                    'future_net_irrigation_mm' in _summary56 and fao56_efficiency is not None):
                with st.expander({'ru':'Расширенный водный баланс: каналы и возвратные потоки',
                                  'kk':'Кеңейтілген су балансы: арналар және қайтарымды ағындар',
                                  'en':'Advanced water balance: conveyance and return flows'}[lang], expanded=False):
                    st.caption({'ru':'Сокращение подачи на поле не обязательно означает снижение безвозвратного потребления. Укажите характеристики системы, иначе неизвестные потери не считаются нулевыми.',
                                'kk':'Егістікте су берудің азаюы су тұтынудың азаюын дәлелдемейді. Белгісіз қайтарымды ағындар нөл емес.',
                                'en':'Reduced field delivery does not demonstrate reduced consumptive use. Unknown return flows are not zero.'}[lang])
                    _adv_convey=st.checkbox({'ru':'Известна эффективность транспортировки воды до поля',
                                             'kk':'Суды алқапқа жеткізу тиімділігі белгілі',
                                             'en':'Conveyance efficiency is known'}[lang],key='water_balance_convey_known')
                    _adv_ec=None
                    if _adv_convey:
                        _adv_ec=q_number_input({'ru':'Эффективность транспортировки, % (пользовательская оценка)',
                                                'kk':'Суды жеткізу тиімділігі, % (пайдаланушы бағалауы)',
                                                'en':'Conveyance efficiency, % (user estimate)'}[lang],
                                               min_value=1.0,max_value=100.0,value=80.0,step=1.0,key='water_balance_convey_eta')/100.0
                    _adv_r=st.checkbox({'ru':'Есть данные или явные сценарные допущения о возвратных потоках',
                                        'kk':'Қайтарымды ағындар туралы дерек немесе сценарийлік жорамал бар',
                                        'en':'Return-flow fractions are known or explicitly assumed'}[lang],key='water_balance_recovery_known')
                    _r1=_r2=_c1=_c2=None
                    if _adv_r:
                        st.warning({'ru':'Это доля НЕиспользованной воды, возвращающаяся в доступную водную систему. Нельзя выбирать проценты наугад и называть это фактическим водосбережением.',
                                    'kk':'Бұл пайдаланылмаған судың қолжетімді су жүйесіне қайту үлесі. Нақты дерексіз үнем деп атауға болмайды.',
                                    'en':'These fractions describe non-consumed water returning to a recoverable system. Do not claim an observed basin saving from assumptions.'}[lang])
                        _r1=q_number_input({'ru':'Возвратная доля полевых потерь: исходный полив, %',
                                            'kk':'Далалық шығынның қайту үлесі: бастапқы, %',
                                            'en':'Recoverable share of field losses: baseline, %'}[lang],
                                           min_value=0.0,max_value=100.0,value=0.0,step=5.0,key='water_balance_return_baseline')/100.0
                        _r2=q_number_input({'ru':'Возвратная доля полевых потерь: новый полив, %',
                                            'kk':'Далалық шығынның қайту үлесі: жаңа, %',
                                            'en':'Recoverable share of field losses: proposed, %'}[lang],
                                           min_value=0.0,max_value=100.0,value=0.0,step=5.0,key='water_balance_return_proposed')/100.0
                        if _adv_convey:
                            _c1=q_number_input({'ru':'Возвратная доля потерь в канале: исходно, %',
                                                'kk':'Арна шығынының қайту үлесі: бастапқы, %',
                                                'en':'Recoverable share of conveyance losses: baseline, %'}[lang],
                                               min_value=0.0,max_value=100.0,value=0.0,step=5.0,key='water_balance_convey_return_baseline')/100.0
                            _c2=q_number_input({'ru':'Возвратная доля потерь в канале: сценарий, %',
                                                'kk':'Арна шығынының қайту үлесі: сценарий, %',
                                                'en':'Recoverable share of conveyance losses: proposed, %'}[lang],
                                               min_value=0.0,max_value=100.0,value=0.0,step=5.0,key='water_balance_convey_return_proposed')/100.0
                    _adv_evidence=st.text_input({'ru':'Источник измерений или сценарных допущений для водного баланса',
                                                 'kk':'Су балансының дереккөзі немесе жорамалы',
                                                 'en':'Water balance measurement source or scenario assumptions'}[lang],
                                                value='',key='water_balance_source')
                    _adv_confirm=st.checkbox({'ru':'Подтверждаю введённые доли потерь/возврата; нули не означают пропущенные данные',
                                              'kk':'Шығын және қайту үлестерін растадым; нөл бос дерек емес',
                                              'en':'I confirm all entered rates; zero is not missing data'}[lang],key='water_balance_confirm')
                    if _adv_confirm and _adv_evidence.strip():
                        _future_net=float(_summary56['future_net_irrigation_mm'])*10.0
                        _wa=irrigation_water_balance(net_irrigation_m3_ha=_future_net,
                            field_efficiency=fao56_efficiency,conveyance_efficiency=_adv_ec,
                            field_recoverable_fraction=_r1,conveyance_recoverable_fraction=_c1,evidence=_adv_evidence)
                        _wb=irrigation_water_balance(net_irrigation_m3_ha=_future_net,
                            field_efficiency=field_efficiency(fao56_target_method),conveyance_efficiency=_adv_ec,
                            field_recoverable_fraction=_r2,conveyance_recoverable_fraction=_c2,evidence=_adv_evidence)
                        _wd=compare_irrigation_balances(_wa,_wb,area_ha=float(area_ha))
                        st.metric({'ru':'Изменение подачи воды на поле, м³ на хозяйство',
                                   'kk':'Егістікке су беру өзгерісі, м³',
                                   'en':'Reduction in field-delivered water, m³'}[lang],
                                  f"{_wd['field_delivery_reduction_m3']:,.0f}")
                        if _wd['source_withdrawal_reduction_m3'] is not None:
                            st.metric({'ru':'Расчётное сокращение забора воды из источника, м³',
                                       'kk':'Су көзінен алу көлемінің болжамды азаюы, м³',
                                       'en':'Conditional reduction in source withdrawals, m³'}[lang],
                                      f"{_wd['source_withdrawal_reduction_m3']:,.0f}")
                        if _wd['depletion_proxy_reduction_m3'] is not None:
                            st.metric({'ru':'Расчётное снижение безвозвратного потребления*, м³',
                                       'kk':'Қайтарымсыз тұтынудың сценарийлік азаюы*, м³',
                                       'en':'Scenario reduction in depletion proxy*, m³'}[lang],
                                      f"{_wd['depletion_proxy_reduction_m3']:,.0f}")
                            st.caption({'ru':'*Прокси по поливу, не измеренное водосбережение бассейна. Не учитывает изменение запасов влаги, грунтовые воды, засоление и повторное использование за пределами поля.',
                                        'kk':'*Бассейн бойынша нақты үнем емес; топырақ ылғалы мен дренажға қатысты шектеулер бар.',
                                        'en':'*Irrigation-attributable proxy, not verified basin conservation; soil storage, groundwater and outside-field reuse unresolved.'}[lang])
                        else:
                            st.info({'ru':'Возвратные потоки не подтверждены: безвозвратное потребление не рассчитано.',
                                     'kk':'Қайтарымды ағындар расталмаған: қайтарымсыз тұтыну есептелмеді.',
                                     'en':'Return-flow data incomplete: water depletion is not calculated.'}[lang])
                        report_payload['summary'].append({'label':'FAO conditional field delivery reduction, m³',
                           'value':f"{_wd['field_delivery_reduction_m3']:.2f}",
                           'note':_adv_evidence+'; field-level not basin saving'})
                        for _val,_name in [('source_withdrawal_reduction_m3','Conditional source withdrawal reduction, m³'),
                                           ('depletion_proxy_reduction_m3','Conditional depletion proxy reduction, m³')]:
                            if _wd[_val] is not None:
                                report_payload['summary'].append({'label':_name,'value':f"{_wd[_val]:.2f}",
                                   'note':_adv_evidence+'; user-specified return fractions; not measured basin saving'})
                        report_payload['inputs'].append(['Water accounting assumptions',
                            f'field eta={_wa.field_efficiency}/{_wb.field_efficiency}; conveyance eta={_adv_ec}; '
                            f'field recovery={_r1}/{_r2}; conveyance recovery={_c1}/{_c2}; area={area_ha} ha',
                            _adv_evidence])
                    elif _adv_confirm:
                        st.warning({'ru':'Нужен источник или точное описание сценарного допущения.',
                                    'kk':'Дереккөзді немесе сценарий жорамалын көрсетіңіз.',
                                    'en':'Document the evidence or scenario assumptions first.'}[lang])
            st.dataframe(pd.DataFrame(_v56['months']),hide_index=True,use_container_width=True)
            st.caption({'kk':'Сценарийлік бағалау ғана; ресми су нормалары мен су лимиті өзгерген жоқ.',
                        'ru':'Сценарная оценка, а не фактический расход воды. Нормы 108-НҚ и водный лимит не изменены.',
                        'en':'Scenario estimate, not actual irrigation use. 108-NQ norm and hard water cap unchanged.'}[lang])
            report_payload['summary'].append({'label':'FAO-56 ET0 baseline Apr-Sep, mm',
                                'value':f"{_summary56['baseline_et0_mm']:.3f}",
                                'note':'NASA POWER climatology 1995-2014; '+_geo_note})
            report_payload['summary'].append({'label':'FAO-56 ET0 '+climate_future_scenario+', mm',
                                'value':f"{_summary56['future_et0_mm']:.3f}",
                                'note':'World Bank CCKP 2040-2059, monthly anomalies, other inputs fixed'})
            for key,label in [('future_etc_mm','FAO-56 ETc scenario, mm'),
                              ('future_gross_irrigation_m3_ha','FAO-56 gross irrigation scenario, m³/ha'),
                              ('future_gross_irrigation_m3','FAO-56 gross irrigation scenario, m³ for field')]:
                if key in _summary56:
                    report_payload['summary'].append({'label':label,'value':f"{_summary56[key]:.3f}",
                        'note':'Conditional crop/water scenario; not observed demand or official 108-NQ norm'})
            report_payload['inputs'].append(['FAO-56 evidence and assumptions',
                                f'Kc={_kc}; Kc mode={fao56_kc_mode}; effective rainfall={fao56_rain_method}; efficiency={fao56_efficiency}; efficiency_source={fao56_efficiency_source}; '+_geo_note,
                                f'{FAO_56_URL}; {FAO_EFFICIENCY_URL}; {FAO_CROP_KC_URL}; NASA POWER 1995-2014; CCKP {climate_future_scenario}, 2040-2059; hypothetical'])
        except (ValueError,TypeError,KeyError,requests.exceptions.RequestException) as _e56:
            st.warning({'kk':'FAO-56 есебі аяқталмады. Мәлімет жетіспейді: ',
                        'ru':'Расчёт FAO-56 не выполнен; проверьте исходные данные и NASA: ',
                        'en':'FAO-56 computation unavailable; check inputs/NASA: '}[lang]+str(_e56))

    # Output only: all daily FAO-56 input widgets live above the Calculate button.
    if mode_key in ('mode1','mode2') and crop in CROP_ROOT_P and _daily_enabled:
        with st.expander({
            'ru':'Итог суточного FAO-56: влага почвы и график полива',
            'kk':'FAO-56 тәуліктік нәтижесі: топырақ ылғалы және суару кестесі',
            'en':'Daily FAO-56 results: root-zone balance and irrigation schedule'}[lang], expanded=True):
            if not _daily_confirm:
                st.warning({'ru':'Подтвердите исходные предположения выше и повторите расчёт.',
                            'kk':'Жоғарыдағы жорамалдарды растаңыз да, қайта есептеңіз.',
                            'en':'Confirm assumptions above and calculate again.'}[lang])
            else:
                try:
                    _lengths=parse_stage_lengths(_daily_stage_text)
                    _end=min(date(_daily_year,9,30),_daily_sow+timedelta(days=sum(_lengths)-1))
                    with st.spinner({'ru':'Загрузка ежедневных данных NASA POWER...',
                      'kk':'NASA POWER тәуліктік деректерін жүктеу...',
                      'en':'Loading daily NASA POWER observations...'}[lang]):
                        if _daily_geometry_string:
                            _weather=_cached_polygon_daily_weather(_daily_geometry_string,_daily_sow,_end)
                        else:
                            _weather=_cached_daily_soil_nasa(float(calc_lat),float(calc_lon),_daily_sow,_end)
                    _soil_result=daily_soil_balance(_weather,crop=crop,sowing_date=_daily_sow,
                        latitude_deg=float(calc_lat),field_efficiency=_daily_eta,
                        soil_fc=_fc,soil_wp=_wp,root_max_m=_root,depletion_p=_p,
                        initial_depletion_fraction=_start_frac,stage_lengths=_lengths,
                        mode=_daily_sched,runoff_fraction=_runoff,
                        capillary_rise_mm_day=_cr,assumptions_confirmed=True)
                    _soil_result['location']={'latitude':float(calc_lat),'longitude':float(calc_lon)}
                    _soil_result['weather_year']=_daily_year
                    _soil_result['spatial_weather_source']=('NASA polygon-weighted daily samples' if _daily_geometry_string else 'NASA district/user single point')
                    _soil_result['fingerprint']=_daily_fingerprint
                    _soil_result['soil_source']=('SoilGrids point texture mapped to FAO indicative profile' if _daily_soil_mode=='mapped_soilgrids' else 'FAO AquaCrop reference: '+_daily_soil_tex if _daily_soil_mode=='fao_reference' else 'User-supplied soil parameters')
                    st.session_state['daily_soil_last_result']=_soil_result
                except (ValueError,KeyError,TypeError,requests.exceptions.RequestException) as _soil_err:
                    st.warning({'ru':'Расчёт не выполнен: ','kk':'Есеп жасалмады: ',
                                'en':'Daily calculation unavailable: '}[lang]+str(_soil_err))
            _result=(st.session_state.get('daily_soil_last_result') if _daily_confirm else None)
            if _result and _result.get('fingerprint') == _daily_fingerprint:
                _ts=_result['totals']
                _col1,_col2,_col3=st.columns(3)
                _col1.metric({'ru':'Фактическая ETc в расчёте, мм','kk':'Есептік нақты ETc, мм','en':'Modelled actual ETc, mm'}[lang],f"{_ts['actual_etc_mm']:.1f}")
                _col2.metric({'ru':'Чистая потребность в поливе, м³/га','kk':'Таза суару қажеттілігі, м³/га','en':'Net irrigation, m³/ha'}[lang],f"{_ts['net_irrigation_m3_ha']:.0f}")
                _col3.metric({'ru':'Подача воды на поле, м³/га','kk':'Егістікке су беру, м³/га','en':'Field delivery, m³/ha'}[lang],f"{_ts['field_delivery_m3_ha']:.0f}")
                st.caption({'ru':f"Исторический сценарий {_result['weather_year']}: дней с водным стрессом {_ts['days_under_stress']}; расчётных поливов {_ts['irrigation_events']}. Не является измеренной экономией воды.",
                  'kk':f"{_result['weather_year']} тарихи сценарий: стресс күндері {_ts['days_under_stress']}, суару оқиғалары {_ts['irrigation_events']}.",
                  'en':f"Historical {_result['weather_year']} scenario: {_ts['days_under_stress']} stress days; {_ts['irrigation_events']} modeled irrigations; not observed water saving."}[lang])
                _soil_df=pd.DataFrame(_result['daily'])
                st.line_chart(_soil_df.set_index('date')[['depletion_end_mm','RAW_mm','TAW_mm']])
                st.dataframe(_soil_df,hide_index=True,use_container_width=True)
                st.caption(FAO_DAILY_SOURCE+' | '+FAO_SOIL_PROFILE_SOURCE)
                report_payload['summary'].append({'label':'Daily FAO-56 field delivery scenario m³/ha',
                    'value':f"{_ts['field_delivery_m3_ha']:.2f}",
                    'note':'Historical NASA POWER '+str(_result['weather_year'])+'; reference soil and crop calendar; not 108-NQ or observed saving'})
                report_payload['inputs'].append(['Daily root-zone soil scenario',
                    str(_result['inputs']), 'FAO-56 Ch8 Eq82-88; FAO AquaCrop Table 2.13a; NASA POWER daily'])

    if carbon_enabled and not carbon_activity_confirmed:
        st.warning({"kk":"GHG салыстыруы үшін бастапқы мөлшерлерді растаңыз.",
                    "ru":"Для расчёта выбросов подтвердите все исходные количества; неизвестные значения нельзя считать нулями.",
                    "en":"Confirm all activity amounts before calculating; unknown activity is not zero."}[lang])
    if carbon_enabled and carbon_activity_confirmed and _ghg_n_mode == 'fertilizer_product' and _ghg_n_fraction is None:
        st.error({'ru':'Для расчёта N₂O требуется доля действующего азота с этикетки удобрения.',
                  'kk':'N₂O есебі үшін тыңайтқыш жапсырмасындағы азот үлесі қажет.',
                  'en':'Product nitrogen fraction is required to calculate N2O.'}[lang])
        st.stop()
    if carbon_enabled and carbon_activity_confirmed:
        try:
            _b = carbon_inputs['baseline']; _q = carbon_inputs['proposed']
            _methane_args={}
            if carbon_enteric:
                _methane_args={"include_enteric":True,
                    "enteric_kg_ch4_head_year":carbon_enteric_factor,
                    "enteric_year_fraction":(183.0/365.0 if carbon_accounting_period == 'apr_sep' else 1.0)}
            _cb=partial_inventory(**_b, grid_kg_co2e_kwh=ef,
                                  accounting_period=carbon_accounting_period,
                                  diesel_factor=carbon_diesel_factor,
                                  n2o_factor=(N2O_EF1_DRY_CLIMATE if carbon_n2o_climate == 'dry' else N2O_EF1_GENERAL),
                                  **_methane_args,
                                  **({'enteric_heads':carbon_enteric_base} if carbon_enteric else {}))
            _cp=partial_inventory(**_q, grid_kg_co2e_kwh=ef,
                                  accounting_period=carbon_accounting_period,
                                  diesel_factor=carbon_diesel_factor,
                                  n2o_factor=(N2O_EF1_DRY_CLIMATE if carbon_n2o_climate == 'dry' else N2O_EF1_GENERAL),
                                  **_methane_args,
                                  **({'enteric_heads':carbon_enteric_proposed} if carbon_enteric else {}))
            _cc=compare_partial_inventory(_cb,_cp)
            st.markdown('### '+{'ru':'Частичный углеродный учёт: сравнение сценариев',
                                'kk':'Парниктік газдардың ішінара есебі: сценарийлер',
                                'en':'Partial GHG inventory: scenario comparison'}[lang])
            _ca,_cpcol,_cd=st.columns(3)
            _ca.metric({'ru':'Исходный вариант','kk':'Бастапқы нұсқа','en':'Baseline'}[lang],f"{_cc['baseline_kgco2e']:,.1f} kg CO₂e")
            _cpcol.metric({'ru':'Сценарий','kk':'Сценарий','en':'Proposed'}[lang],f"{_cc['scenario_kgco2e']:,.1f} kg CO₂e")
            _cd.metric({'ru':'Изменение','kk':'Өзгеріс','en':'Change'}[lang],f"{_cc['change_kgco2e']:+,.1f} kg CO₂e")
            st.caption({'ru':'Только прямой N₂O от азота, дизель, электричество и (если включено) метан пищеварения. Сравнение пользовательских сценариев, не доказанная экономия и не полный углеродный след.',
                        'kk':'Тек азоттан тікелей N₂O, дизель, электр қуаты және (таңдалса) мал метаны. Бұл пайдаланушы сценарийі, дәлелденген үнемдеу немесе толық көміртегі ізі емес.',
                        'en':'Only direct fertilizer N2O, diesel, electricity and optional enteric CH4. User scenario, not observed reductions or complete footprint.'}[lang])
            _period_display = 'Apr-Sep (183 days)' if carbon_accounting_period == 'apr_sep' else 'calendar year'
            report_payload['inputs'].append([
                {'kk':'Парниктік газдар есебінің кезеңі','ru':'Расчётный период выбросов','en':'GHG accounting period'}[lang],
                _period_display,
                {'kk':'Екі сценарийде бірдей кезең','ru':'Одинаковый период в обоих сценариях','en':'Same period for both scenarios'}[lang]])
            _co2_boundary = {"kk":"Пайдаланушының деректері; толық өмірлік цикл емес",
                             "ru":"Сценарий пользователя, без полного жизненного цикла",
                             "en":"User scenario; not full life-cycle inventory"}[lang]
            report_payload['summary'].extend([
                {'label':{'kk':'Бастапқы ішінара CO₂e, кг','ru':'Частичные выбросы: исходные, кг CO₂e','en':'Partial GHG baseline, kg CO₂e'}[lang],
                 'value':f"{_cc['baseline_kgco2e']:.2f}", 'note':_co2_boundary},
                {'label':{'kk':'Сценарийлік ішінара CO₂e, кг','ru':'Частичные выбросы: сценарий, кг CO₂e','en':'Partial GHG scenario, kg CO₂e'}[lang],
                 'value':f"{_cc['scenario_kgco2e']:.2f}", 'note':_co2_boundary},
                {'label':{'kk':'Ішінара CO₂e өзгерісі, кг','ru':'Изменение частичных выбросов, кг CO₂e','en':'Partial GHG change, kg CO₂e'}[lang],
                 'value':f"{_cc['change_kgco2e']:+.2f}",
                 'note':{'kk':'Болжамды өзгеріс, нақты төмендеу емес',
                         'ru':'Расчётное изменение, не подтверждённое сокращение',
                         'en':'Counterfactual difference, not observed reduction'}[lang]}])
            report_payload['inputs'].append([
                {'kk':'GHG кіріс деректері мен коэффициенттері','ru':'Исходные данные и коэффициенты выбросов','en':'GHG activity and factor assumptions'}[lang],
                f"N: {_b['nitrogen_kg']}/{_q['nitrogen_kg']} kg; diesel: {_b['diesel_litres']}/{_q['diesel_litres']} L; electricity: {_b['electricity_kwh']}/{_q['electricity_kwh']} kWh; diesel EF: {carbon_diesel_factor} kg/L; grid EF: {ef} kg/kWh",
                _co2_boundary + '; N₂O EF1 '+str(N2O_EF1_DRY_CLIMATE if carbon_n2o_climate == 'dry' else N2O_EF1_GENERAL)
                + '; '+SOURCES['ipcc_soils'].url+'; diesel: '+SOURCES['ipcc_diesel'].url+'; density standard: '+SOURCES['gost_diesel'].url])
            if _ghg_n_mode == 'fertilizer_product':
                _n_source=(SOURCES[FERTILIZER_GOST_SOURCES[_ghg_product]].url
                    if _ghg_product!='custom' else
                    {'ru':'Состав по этикетке, введённый пользователем',
                     'kk':'Пайдаланушы көрсеткен таңбалау құрамы',
                     'en':'Product-label composition entered by user'}[lang])
                report_payload['inputs'].append([
                    {'ru':'Азот: перевод удобрения в кг N',
                     'kk':'Азот: тыңайтқышты кг N-ге ауыстыру',
                     'en':'Nitrogen conversion from fertilizer product to kg N'}[lang],
                    f'N fraction={_ghg_n_fraction:.4f}; baseline={_b["nitrogen_kg"]:.2f} kg N; scenario={_q["nitrogen_kg"]:.2f} kg N',
                    _n_source+'; minimum dry-matter guarantee if GOST option; reference scenario, not lab analysis'])
            if carbon_enteric:
                report_payload['inputs'].append([
                    {'kk':'Мал метаны: коэффициент пен мал саны','ru':'Метан пищеварения: коэффициент и поголовье','en':'Enteric methane: factor and heads'}[lang],
                    f"{carbon_enteric_factor} kg CH4/head/year; {carbon_enteric_base}/{carbon_enteric_proposed} heads; {_period_display}; fraction={_methane_args['enteric_year_fraction']:.6f}",
                    _co2_boundary + '; '+SOURCES['ipcc_livestock'].url])
        except (ValueError,KeyError) as _c_err:
            st.warning(str(_c_err))

    # Cross-cutting results must survive mode-specific report summary resets below.
    _cross_module_summary_rows = list(report_payload['summary'])
    if crop in CROPS and mode_key in ('mode1','mode2'):
        try:
            _fc = evaluate_forecast_support(DATA_DIR, used_district, crop)
            if _fc.low_confidence:
                _reason='; '.join(_fc.reasons)
                st.warning({
                    'ru':f'Прогноз урожайности: ограниченная доказательная надёжность ({_reason}). Рекомендуется использовать собственную урожайность хозяйства для экономического планирования.',
                    'kk':f'Өнімділік болжамы: дәлелдік сенімділігі шектеулі ({_reason}). Экономикалық жоспарлау үшін шаруашылықтың өз өнімділік дерегін пайдаланыңыз.',
                    'en':f'Yield forecast: limited validation support ({_reason}). Use farm-entered yield for economic planning.'}[lang])
            _cross_module_summary_rows.append({
                'label': {'kk':'ML болжамының дәлелдік шектеуі','ru':'Историческая пространственно-временная проверка ML','en':'ML forecast validation caution'}[lang],
                'value': {'kk':'Төмен/шектеулі сенімділік','ru':'Низкая/ограниченная уверенность','en':'Low/limited support'}[lang] if _fc.low_confidence else {'kk':'Айқын ескерту жоқ','ru':'Нет дополнительного предупреждения по старой CV; см. временной тест','en':'No specific warning'}[lang],
                'note':'; '.join(_fc.reasons) if _fc.reasons else f'Crop R²={_fc.crop_r2:.3f}; district leave-out R²={_fc.district_r2:.3f}; NOT a 2025 holdout test'})
            _forward_quality = forward_yield_evidence(DATA_DIR,crop)
            if _forward_quality.support != 'historically_supported':
                _reason='; '.join(_forward_quality.reasons)
                st.warning({
                    'ru':f'ПРОВЕРКА ПРОГНОЗА ПО КУЛЬТУРЕ (2021–2025): недостаточная подтверждённая точность. {_reason}. Число RF — исследовательский ориентир, НЕ прогноз урожайности конкретного поля. Для хозяйственного решения используйте собственную урожайность и результаты ресурсного анализа.',
                    'kk':f'Дақылдың 2021–2025 жылдардағы болжамы жеткілікті дәлелденбеген: {_reason}. RF мәні нақты танап өніміне кепіл емес; шаруашылық дерегін қолданыңыз.',
                    'en':f'Crop-specific 2021–2025 predictive accuracy is not established: {_reason}. RF is a research benchmark, NOT a validated individual-field forecast; use observed farm yield and resource analysis.'}[lang])
                _cross_module_summary_rows.append({
                    'label':{'ru':'Предупреждение: точность ML по культуре','kk':'Ескерту: дақыл бойынша ML дәлдігі','en':'Warning: crop-specific ML predictive validity'}[lang],
                    'value':{'ru':'Ограниченная, использовать с осторожностью','kk':'Шектеулі, сақтық қажет','en':'Limited, exercise caution'}[lang],
                    'note':_reason+'; historical forward validation, not new-farm accuracy'})
            _holdout_evidence = forward_holdout_for_crop(crop)
            if _holdout_evidence:
                _cross_module_summary_rows.append({
                    'label': {'ru':'ML: R² при прогнозе 2021–2025',
                              'kk':'ML: 2021–2025 жж. болжамының R² көрсеткіші',
                              'en':'ML: forward R² for 2021–2025'}[lang],
                    'value': f"{_holdout_evidence['r2']:.3f}",
                    'note': {'ru':'Обучение 2004–2020, проверка 2021–2025. Отрицательный R² означает слабее прогноза среднего по контрольной выборке.',
                             'kk':'2004–2020 жж. оқыту, 2021–2025 жж. тексеру. Теріс R² бақылау жиынының орташа мәнінен нашар нәтижені білдіреді.',
                             'en':'Trained 2004–2020, tested 2021–2025. Negative R² means worse than the heldout-target mean.'}[lang]
                            + f"; N={_holdout_evidence['n']}; MAE={_holdout_evidence['mae']:.2f} centners/ha"
                })
            _pi_evidence = prediction_interval_for_crop(crop)
            if _pi_evidence and _pi_evidence.get('is_forward_backtest') and _pi_evidence['empirical_coverage'] < _pi_evidence['coverage_target']:
                st.warning({'ru':'Независимое историческое покрытие интервала ниже целевых 90%. Не интерпретируйте интервал как гарантированную точность для нового сезона.',
                            'kk':'Тарихи аралықты қамту 90% мақсаттан төмен; болашақ маусымға кепіл емес.',
                            'en':'Forward interval coverage falls below its nominal 90% target; no future coverage guarantee.'}[lang])
            if _pi_evidence and _pi_evidence.get('is_forward_backtest') and _pi_evidence['empirical_coverage'] < _pi_evidence['coverage_target']:
                _cross_module_summary_rows.append({'label':{'ru':'Интервал ML: покрытие ниже цели 90%','kk':'ML аралығы: қамту 90%-дан төмен','en':'ML interval below 90% coverage target'}[lang], 'value':f"{100*_pi_evidence['empirical_coverage']:.1f}% / 90%", 'note':{'ru':'Исторический недоохват, не гарантия будущих прогнозов.','kk':'Тарихи қамту жеткіліксіз, болашаққа кепіл емес.','en':'Observed undercoverage, not a future guarantee.'}[lang]})
            if _pi_evidence and _pi_evidence.get('is_forward_backtest'):
                _cross_module_summary_rows.append({
                    'label': {'ru':'Историческое покрытие ML-интервала 2021–2025',
                              'kk':'ML аралығының 2021–2025 жж. тарихи қамтуы',
                              'en':'ML interval historical coverage 2021–2025'}[lang],
                    'value': f"{100*_pi_evidence['empirical_coverage']:.1f}% / 90%",
                    'note': {'ru':'Проверка будущего периода по более ранней калибровке; результат не гарантирует покрытие новых прогнозов.',
                             'kk':'Ертеректегі калибрлеуге негізделген кейінгі кезеңнің тексерісі; жаңа болжамдарға кепілдік емес.',
                             'en':'Forward-period backtest using prior calibration; no guarantee for new forecasts.'}[lang]
                           + f"; N={_pi_evidence['n']}; ±{_pi_evidence['half_width_centners_ha']:.2f} centners/ha"
                })
        except (OSError,ValueError) as _validation_error:
            st.caption({'ru':'Файл валидации не найден: ','kk':'Валидация файлы табылмады: ','en':'Validation unavailable: '}[lang]+str(_validation_error))

    if mode_key == "mode5":
        st.caption({
            "kk":"Мал шаруашылығы модулі ауданның өндірістік құрылымын, климаттық экспозициясын және шаруашылық енгізген су, жемшөп, жайылым, энергия мен өнім деректерін біріктіреді.",
            "ru":"Модуль животноводства объединяет наблюдаемую структуру района, климатическую экспозицию и введенные хозяйством данные по воде, кормам, пастбищу, энергии и продукции.",
            "en":"The livestock module combines the observed district production structure, climate exposure and farm-entered water, feed, pasture, energy and production data."
        }[lang])
    else:
        st.caption({
            "kk":"QŪNAR аумақтың ресурстық және климаттық шектеулерін бір шешім кеңістігінде салыстырады. Көрсеткіштер салыстырмалы; дәлелдердің сенімділігі жеке көрсетіледі.",
            "ru":"QŪNAR сопоставляет ресурсные и климатические ограничения территории в едином пространстве решений. Баллы имеют сравнительный смысл; сила доказательной базы показывается отдельно.",
            "en":"QŪNAR compares territorial resource and climate constraints within one decision space. Scores are comparative; evidence strength is reported separately."
        }[lang])

    # The map area and its declared scope were set at input time, prior to
    # building the report; do not redefine the user's selection here.
    area_geometry_mismatch = False
    if polygon_area:
        comparison_area = (farm_total_area_ha if polygon_scope == "whole_farm" else area_ha)
        if polygon_scope == "whole_farm" and mode_key in ("mode1", "mode2", "mode3"):
            st.info({"ru":"Климат и спутниковые данные рассчитываются для контура всего хозяйства. Это пространственный ориентир, а не измерение конкретного участка выбранной культуры.",
                     "kk":"Климат пен спутниктік деректер бүкіл шаруашылық контуры үшін есептеледі. Бұл таңдалған дақыл танабының нақты өлшемі емес.",
                     "en":"Climate and satellite inputs represent the whole-holding polygon, not a direct measurement of the selected crop plot."}[lang])
        diff_pct = abs(polygon_area - comparison_area) / max(comparison_area, 0.0001) * 100.0
        st.caption(t["area_compare"].format(declared=comparison_area, polygon=polygon_area, diff=diff_pct))
        area_geometry_mismatch = diff_pct > 25
        if area_geometry_mismatch:
            st.warning(t["area_mismatch"].format(declared=comparison_area, polygon=polygon_area, diff=diff_pct))
        else:
            st.success(t["area_match"].format(diff=diff_pct))
        detected = map_district
        st.session_state.detected_map_district = detected
        if detected:
            share_txt = f"{map_district_share*100:.1f}%" if map_district_share is not None else ""
            if detected == district:
                st.success({"kk":f"Карта контуры {district_label(detected)} аумағына жатады ({share_txt}).",
                            "ru":f"Контур карты относится к {district_label(detected)} ({share_txt}).",
                            "en":f"The map polygon belongs to {district_label(detected)} ({share_txt})."}[lang])
            else:
                st.warning({"kk":f"Формада {district_label(district)} таңдалған, бірақ ресми полигондар бойынша контур {district_label(detected)} аумағына жатады ({share_txt}). Есепте карта бойынша аудан қолданылады.",
                            "ru":f"В форме выбран {district_label(district)}, но по административным полигонам контур относится к {district_label(detected)} ({share_txt}). В расчете используется район по карте.",
                            "en":f"The form selected {district_label(district)}, but the polygon falls in {district_label(detected)} ({share_txt}). The map district is used in the calculation."}[lang])
        else:
            st.warning({"kk":"Контур әкімшілік полигондармен сенімді сәйкестендірілмеді. Есепте формада таңдалған аудан қолданылады.",
                        "ru":"Контур не удалось надежно сопоставить с административными полигонами. Используется район, выбранный в форме.",
                        "en":"The polygon could not be matched reliably to an administrative boundary. The selected district is used."}[lang])

    if mode_key == "mode5":
        livestock = livestock_resource_metrics(
            district=used_district,
            species=livestock_species,
            heads=livestock_heads,
            pasture_ha=area_ha,
            fodder_t=livestock_fodder_t,
            available_water_m3=available_water,
            water_used_m3=effective_water_used,
            energy_kwh=observed_energy,
            emission_factor_kgco2_kwh=ef,
            production_amount=livestock_production_amount,
            production_kind=livestock_production_kind,
            pasture_degraded_share_pct=pasture_degraded_share_pct,
            climate=climate,
            use_district_reference_if_missing=False,
        )
        lp = district_livestock_profile(used_district)
        benchmark = livestock.get("district_benchmark", {}) or {}
        forecast = livestock.get("forecast", {}) or {}
        species_validation = forecast.get("species_validation", {}) or {}
        regional_prod = livestock.get("regional_productivity", {}) or {}
        trend = livestock.get("regional_product_trend", {}) or {}

        st.markdown("### " + {
            "kk":"QŪNAR мал шаруашылығы - ресурстық-болжамдық модуль",
            "ru":"QŪNAR животноводство - ресурсно-прогнозный модуль",
            "en":"QŪNAR Livestock - resource and forecasting module",
        }[lang])
        st.caption({
            "kk":"Модуль аудандық мал санының ресми динамикасын, NASA POWER бойынша вегетациялық кезең климатын, мал түріне арналған су мен жемшөптің анықтамалық мөлшерлерін және шаруашылық енгізген деректерді бір есептік жүйеде біріктіреді.",
            "ru":"Модуль объединяет официальную районную динамику поголовья, климатический профиль NASA POWER, справочные потребности в воде и кормах по видам животных и фактические данные хозяйства.",
            "en":"The layer integrates official district herd dynamics, NASA POWER growing-season climate, species-specific water/feed references and farm observations.",
        }[lang])

        # 1. District structure and herd state.
        st.markdown("#### " + {
            "kk":"Аудандық құрылым және мал саны",
            "ru":"Районная структура и поголовье",
            "en":"District structure and herd status",
        }[lang])
        effective_heads = float(livestock.get("heads") or 0.0)
        heads_source = livestock.get("heads_source")
        r1,r2,r3,r4 = st.columns(4)
        r1.metric(
            {"kk":"Мал шаруашылығының аудан өніміндегі үлесі","ru":"Доля животноводства в выпуске района","en":"Livestock share of district output"}[lang],
            f"{float(lp.get('livestock_share_pct',0)):.1f}%"
        )
        r2.metric(
            {"kk":"Есепте қолданылған мал саны","ru":"Поголовье в расчете","en":"Herd used in calculation"}[lang],
            f"{effective_heads:,.0f}" if heads_source == "user" else "—"
        )
        r3.metric(
            {"kk":"Соңғы ресми аудандық мән","ru":"Последнее официальное значение района","en":"Latest official district count"}[lang],
            f"{float(benchmark.get('latest_district_heads',0)):,.0f}" if benchmark.get("latest_district_heads") is not None else "—",
            help=(
                f"{benchmark.get('latest_year','—')}"
                if benchmark.get("latest_year") is not None else None
            ),
        )
        r4.metric(
            {"kk":"Шартты мал бірлігі","ru":"Условные единицы скота","en":"Livestock units (LU)"}[lang],
            f"{float(livestock.get('livestock_units')):,.1f}" if livestock.get("livestock_units") is not None else "—"
        )

        if heads_source == "district_reference":
            st.info({
                "kk":f"Шаруашылықтың нақты мал саны енгізілмеді. Есептік сценарийде {benchmark.get('latest_year','соңғы қолжетімді')} жылғы аудандық ресми мән қолданылды: {effective_heads:,.0f} бас. Бұл мән шаруашылықтың нақты мал саны ретінде белгіленбейді.",
                "ru":f"Поголовье конкретного хозяйства не введено. В справочном сценарии использовано последнее официальное районное значение за {benchmark.get('latest_year','последний доступный')} год: {effective_heads:,.0f} голов. В отчете оно отмечается как районное справочное значение.",
                "en":f"No farm-specific herd count was entered. The reference scenario uses the latest official district value for {benchmark.get('latest_year','the latest available year')}: {effective_heads:,.0f} head, explicitly flagged as a district reference.",
            }[lang])
        if heads_source == "unknown":
            st.info({
                "ru":"Поголовье хозяйства не введено. Районная статистика показана отдельно для справки. Потребность фермы в воде, кормах и нагрузка на пастбище не рассчитываются без поголовья.",
                "kk":"Шаруашылықтың мал саны енгізілмеген. Аудандық статистика бөлек көрсетіледі. Мал саны жоқ кезде ферма суы, жемі және жайылым жүктемесі есептелмейді.",
                "en":"Farm herd size was not entered. District statistics are context only. Farm water, feed and stocking pressure remain unavailable without farm animal counts."}[lang])
        benchmark_category = benchmark.get("benchmark_species")
        if benchmark_category and str(benchmark_category) != str(livestock_species):
            st.caption({
                "kk":f"Ресми тарихи салыстыру санаты: {benchmark_category_label(benchmark_category)}. Таңдалған мал түрі үшін су мен жемшөп коэффициенттері жеке қолданылады.",
                "ru":f"Официальная историческая категория для сравнения: {benchmark_category_label(benchmark_category)}. Коэффициенты воды и кормов для выбранного вида применяются отдельно.",
                "en":f"Official historical benchmark category: {benchmark_category_label(benchmark_category)}. Species-specific water and feed coefficients are applied separately for the selected type.",
            }[lang])

        if benchmark.get("district_percentile") is not None:
            st.caption({
                "kk":f"{SPECIES_LABELS[lang][livestock_species]} бойынша ауданның мал саны қолжетімді аумақтар арасындағы салыстырмалы бөліністің {benchmark['district_percentile']:.0f}-пайыздық деңгейінде; тарихи қатар {benchmark.get('history_start_year','—')}-{benchmark.get('latest_year','—')}, бақылау саны: {benchmark.get('observations','—')}.",
                "ru":f"По категории «{SPECIES_LABELS[lang][livestock_species]}» район находится примерно на {benchmark['district_percentile']:.0f}-м перцентиле распределения поголовья среди доступных территорий; исторический ряд {benchmark.get('history_start_year','—')}-{benchmark.get('latest_year','—')}, наблюдений: {benchmark.get('observations','—')}.",
                "en":f"For {SPECIES_LABELS[lang][livestock_species]}, the district is near the {benchmark['district_percentile']:.0f}th percentile of available district herd counts; history {benchmark.get('history_start_year','—')}-{benchmark.get('latest_year','—')}, observations: {benchmark.get('observations','—')}.",
            }[lang])

        if livestock.get("lu_per_pasture_ha") is not None:
            st.metric(
                {"kk":"Шартты мал бірлігі / жайылым га","ru":"Условных единиц скота на гектар пастбища","en":"LU per pasture ha"}[lang],
                f"{livestock['lu_per_pasture_ha']:.3f} {UNITS['livestock_unit_ha']}"
            )

        # Detailed time-series ML diagnostics are for the research interface.
        if user_level == "researcher":
            # 2. Historical dynamics and one-step ML forecast.
            st.markdown("#### " + {
                "kk":"Тарихи динамика және машиналық оқыту болжамы",
                "ru":"Историческая динамика и прогноз машинного обучения",
                "en":"Historical dynamics and ML forecast",
            }[lang])
            f1,f2,f3,f4 = st.columns(4)
            f1.metric(
                {"kk":"Соңғы бақылау","ru":"Последнее наблюдение","en":"Latest observation"}[lang],
                f"{float(benchmark.get('latest_district_heads',0)):,.0f}" if benchmark.get("latest_district_heads") is not None else "—",
                help=str(benchmark.get("latest_year",""))
            )
            f2.metric(
                {"kk":"Келесі жылға машиналық оқыту болжамы","ru":"Прогноз машинного обучения на следующий год","en":"Next-year machine-learning forecast"}[lang],
                f"{float(forecast.get('forecast_heads')):,.0f}" if forecast.get("available") and forecast.get("publish_forecast") else "—",
                delta=(f"{float(forecast.get('forecast_change_pct')):+.1f}%" if forecast.get("publish_forecast") and forecast.get("forecast_change_pct") is not None else None)
            )
            f3.metric(
                {"kk":"Санат бойынша R² (логарифмдік шкала)","ru":"R² по категории (логарифмическая шкала)","en":"Category R² (log scale)"}[lang],
                f"{float(species_validation.get('r2_log')):.3f}" if species_validation.get("r2_log") is not None and pd.notna(species_validation.get("r2_log")) else "—"
            )
            f4.metric(
                {"kk":"Медианалық абсолюттік пайыздық қате","ru":"Медианная абсолютная процентная ошибка","en":"Median absolute percentage error"}[lang],
                f"{float(species_validation.get('median_ape_pct')):.1f}%" if species_validation.get("median_ape_pct") is not None and pd.notna(species_validation.get("median_ape_pct")) else "—"
            )

            hist = district_species_history(used_district, livestock_species)
            if not hist.empty:
                observed_col = {"kk":"Нақты мән","ru":"Фактическое значение","en":"Observed"}[lang]
                forecast_col = {"kk":"Болжам","ru":"Прогноз","en":"Forecast"}[lang]
                hplot = hist.rename(columns={"Heads": observed_col}).set_index("Year")[[observed_col]]
                hplot[forecast_col] = float("nan")
                if forecast.get("available") and forecast.get("publish_forecast"):
                    fy = int(forecast["forecast_year"])
                    if fy not in hplot.index:
                        hplot.loc[fy, observed_col] = float("nan")
                    hplot.loc[fy, forecast_col] = float(forecast["forecast_heads"])
                    # Retain the latest observed point in the forecast series so the one-step path is visible.
                    ly = int(forecast["previous_year"])
                    hplot.loc[ly, forecast_col] = float(forecast["previous_heads"])
                    hplot = hplot.sort_index()
                st.line_chart(hplot)
            if forecast.get("available") and not forecast.get("publish_forecast"):
                st.warning({
                    "kk":f"Бұл санат бойынша машиналық оқыту болжамы жарияланбайды: уақыт бойынша кезеңдік тексерудің сапасы жеткіліксіз (R²={species_validation.get('r2_log', float('nan')):.3f}, медианалық абсолюттік пайыздық қате={species_validation.get('median_ape_pct', float('nan')):.1f}%). QŪNAR тарихи динамика мен ресурстық диагностикаға сүйенеді.",
                    "ru":f"Для этой категории численный прогноз машинного обучения не публикуется: последовательная проверка по времени недостаточно надежна (R²={species_validation.get('r2_log', float('nan')):.3f}, медианная абсолютная процентная ошибка={species_validation.get('median_ape_pct', float('nan')):.1f}%). QŪNAR сохраняет историческую динамику и ресурсную диагностику без выдачи слабого прогноза.",
                    "en":f"A numerical ML forecast is withheld for this category because category-level rolling-origin validation is not reliable enough (R²={species_validation.get('r2_log', float('nan')):.3f}, median APE={species_validation.get('median_ape_pct', float('nan')):.1f}%). QŪNAR retains history and resource diagnostics without publishing a weak forecast.",
                }[lang])
            if forecast.get("available"):
                climate_flag = {
                    "kk":"аймақтық медианамен толықтырылған" if forecast.get("climate_imputed") else "аудандық",
                    "ru":"дополнен региональной медианой" if forecast.get("climate_imputed") else "районный",
                    "en":"regional-median imputed" if forecast.get("climate_imputed") else "district",
                }[lang]
                st.caption({
                    "kk":f"Кездейсоқ орман алгоритмінің белгілері: аудан, мал санаты, алдыңғы жылғы мал саны, жыл, сәуір-қыркүйек температурасы, жауын-шашын, тамыр аймағының ылғалы және күн радиациясы. Уақыт бойынша кезеңдік тексеру жылдары: {', '.join(map(str, forecast.get('validation_years', [])))}; жалпы бақылау саны={forecast.get('validation_n',0)}, жалпы R²={forecast.get('r2_log', float('nan')):.3f}; таңдалған санаттағы бақылау саны={species_validation.get('n',0)}, R²={species_validation.get('r2_log', float('nan')):.3f}, медианалық абсолюттік пайыздық қате={species_validation.get('median_ape_pct', float('nan')):.1f}%. Климаттық анықтама: {forecast.get('climate_reference_year','—')} жыл, {climate_flag}.",
                    "ru":f"Алгоритм случайного леса использует район, категорию животных, поголовье предыдущего года, год, температуру апреля-сентября, осадки, влажность корневой зоны и солнечную радиацию. Последовательная проверка по времени охватывает {', '.join(map(str, forecast.get('validation_years', [])))} годы; общее число наблюдений={forecast.get('validation_n',0)}, общий R²={forecast.get('r2_log', float('nan')):.3f}; для выбранной категории число наблюдений={species_validation.get('n',0)}, R²={species_validation.get('r2_log', float('nan')):.3f}, медианная абсолютная процентная ошибка={species_validation.get('median_ape_pct', float('nan')):.1f}%. Климатическая опора прогноза: {forecast.get('climate_reference_year','—')} год, профиль {climate_flag}.",
                    "en":f"Random Forest uses district, livestock category, previous-year herd size, year, Apr-Sep temperature, precipitation, root-zone wetness and solar radiation. Rolling-origin validation covers {', '.join(map(str, forecast.get('validation_years', [])))}; overall n={forecast.get('validation_n',0)}, overall R²(log)={forecast.get('r2_log', float('nan')):.3f}; selected-category n={species_validation.get('n',0)}, R²(log)={species_validation.get('r2_log', float('nan')):.3f}, median APE={species_validation.get('median_ape_pct', float('nan')):.1f}%. Forecast climate reference: {forecast.get('climate_reference_year','—')}, {climate_flag} profile.",
                }[lang])

        # 3. Biological/resource reference layer.
        st.markdown("#### " + {
            "kk":"Су және жемшөп ресурстық теңгерімі",
            "ru":"Ресурсный баланс воды и кормов",
            "en":"Water and feed resource balance",
        }[lang])
        b1,b2,b3,b4 = st.columns(4)
        b1.metric(
            {"kk":"Су қажеттілігі, л/бас/тәул.","ru":"Справочная потребность в воде, л/гол./сут.","en":"Reference water need, L/head/day"}[lang],
            f"{float(livestock.get('reference_water_l_head_day')):,.1f}" if livestock.get("reference_water_l_head_day") is not None else "—"
        )
        b2.metric(
            {"kk":"Жылдық су қажеттілігі","ru":"Справочная годовая потребность в воде","en":"Reference annual water requirement"}[lang],
            f"{float(livestock.get('reference_water_m3_year')):,.0f} {UNITS['m3']}" if livestock.get("reference_water_m3_year") is not None else "—"
        )
        b3.metric(
            {"kk":"Жемшөп құрғақ заты / бас / тәул.","ru":"Сухое вещество корма, кг/гол./сут.","en":"Feed dry matter, kg/head/day"}[lang],
            f"{float(livestock.get('reference_feed_dm_kg_head_day')):,.2f}" if livestock.get("reference_feed_dm_kg_head_day") is not None else "—"
        )
        b4.metric(
            {"kk":"Жылдық жемшөп қажеттілігі","ru":"Справочная годовая потребность в кормах","en":"Reference annual feed requirement"}[lang],
            f"{float(livestock.get('reference_feed_dm_t_year')):,.1f} {UNITS['dry_t']}" if livestock.get("reference_feed_dm_t_year") is not None else "—"
        )
        st.caption({
            "kk":f"Судың анықтамалық қажеттілігі {float(livestock.get('reference_temperature_c',25)):.1f} °C температура үшін есептелді; мал түрі коэффициенттерінің дереккөзі: {livestock.get('reference_source','—')}. Бұл шамалар жоспарлауға арналған анықтамалық мәндер ретінде қолданылады.",
            "ru":f"Водный ориентир рассчитан для климатической температуры {float(livestock.get('reference_temperature_c',25)):.1f} °C; источник видоспецифических коэффициентов: {livestock.get('reference_source','—')}. Эти значения используются как прозрачный расчетный ориентир.",
            "en":f"The water reference is evaluated at {float(livestock.get('reference_temperature_c',25)):.1f} °C; species coefficient source: {livestock.get('reference_source','—')}. Values are retained as transparent planning references.",
        }[lang])

        if livestock.get("reference_water_coverage_pct") is not None:
            cov = float(livestock["reference_water_coverage_pct"])
            msg = {
                "kk":f"Көрсетілген қолжетімді су анықтамалық жылдық қажеттіліктің {cov:.1f}% жабады.",
                "ru":f"Указанный доступный объем воды покрывает {cov:.1f}% справочной годовой потребности.",
                "en":f"Stated available water covers {cov:.1f}% of the annual reference requirement.",
            }[lang]
            (st.success if cov >= 100 else st.warning)(msg)

        if livestock.get("feed_reference_coverage_pct") is not None:
            cov = float(livestock["feed_reference_coverage_pct"])
            msg = {
                "kk":f"Енгізілген жемшөп қоры құрғақ зат бойынша анықтамалық жылдық қажеттіліктің {cov:.1f}% жабады.",
                "ru":f"Введенный запас кормов покрывает {cov:.1f}% справочной годовой потребности в сухом веществе.",
                "en":f"Entered feed supply covers {cov:.1f}% of the annual reference dry-matter requirement.",
            }[lang]
            (st.success if cov >= 100 else st.warning)(msg)

        if livestock.get("water_vs_reference_pct") is not None:
            st.caption({
                "kk":f"Енгізілген нақты су тұтынуы анықтамалық биологиялық су көлемінің {float(livestock['water_vs_reference_pct']):.1f}% құрайды. Айырмашылық өлшеу, технология, рацион, маусым және мал өнімділігімен бірге түсіндіріледі.",
                "ru":f"Введенное фактическое водопотребление составляет {float(livestock['water_vs_reference_pct']):.1f}% справочного биологического объема. Разница интерпретируется вместе с технологией содержания, рационом, сезоном и продуктивностью.",
                "en":f"Entered observed water use equals {float(livestock['water_vs_reference_pct']):.1f}% of the biological reference volume. The difference is interpreted with housing technology, diet, season and productivity.",
            }[lang])

        # 4. Production performance.
        st.markdown("#### " + {
            "kk":"Өнімділік және өңірлік салыстырмалы көрсеткіш",
            "ru":"Продуктивность и региональное сравнение",
            "en":"Productivity and regional benchmark",
        }[lang])
        p1,p2,p3,p4 = st.columns(4)
        if livestock_production_kind == "thousand_eggs":
            own_prod = livestock.get("eggs_per_head")
            own_label = {"kk":"Жұмыртқа / бас","ru":"Яиц на голову","en":"Eggs per bird"}[lang]
            own_fmt = f"{float(own_prod):,.1f}" if own_prod is not None else "—"
        else:
            own_prod = livestock.get("production_kg_per_head")
            own_label = {"kk":"Өнім / бас","ru":"Продукция на голову","en":"Output per head"}[lang]
            own_fmt = f"{float(own_prod):,.1f} {UNITS['kg']}" if own_prod is not None else "—"
        p1.metric(own_label, own_fmt)

        ref_kind = livestock.get("productivity_reference_kind")
        ref_val = livestock.get("productivity_reference_value")
        ratio = livestock.get("productivity_reference_ratio_pct")
        p2.metric(
            {"kk":"2023 жылғы өңірлік салыстыру","ru":"Региональное сравнение за 2023 год","en":"2023 regional reference"}[lang],
            f"{float(ref_val):,.1f}" if ref_val is not None else "—",
            help=str(ref_kind or "")
        )
        p3.metric(
            {"kk":"Өңірлік мәнге қатысты","ru":"Относительно регионального значения","en":"Relative to reference"}[lang],
            f"{float(ratio):,.1f}%" if ratio is not None else "—"
        )
        p4.metric(
            {"kk":"Орташа жылдық өсу қарқыны","ru":"Среднегодовой темп роста","en":"Regional CAGR"}[lang],
            f"{float(trend.get('cagr_pct')):+.2f}{UNITS['growth_year']}" if trend.get("cagr_pct") is not None else "—",
            help=(f"{trend.get('start_year','—')}-{trend.get('end_year','—')}" if trend else None)
        )

        if livestock_production_amount <= 0:
            refs = []
            if livestock_species == "Dairy cows" and regional_prod.get("milk_kg_per_cow") is not None:
                refs.append({"kk":f"Сүт: {regional_prod['milk_kg_per_cow']:.0f} кг/сиыр","ru":f"Молоко: {regional_prod['milk_kg_per_cow']:.0f} кг/корову","en":f"Milk: {regional_prod['milk_kg_per_cow']:.0f} kg/cow"}[lang])
            elif livestock_species == "Poultry layers" and regional_prod.get("eggs_per_bird") is not None:
                refs.append({"kk":f"Жұмыртқа: {regional_prod['eggs_per_bird']:.1f} дана/құс","ru":f"Яйца: {regional_prod['eggs_per_bird']:.1f} шт./птицу","en":f"Eggs: {regional_prod['eggs_per_bird']:.1f}/bird"}[lang])
            elif livestock_species in ("Sheep","Goats") and regional_prod.get("wool_kg_per_sheep_goat") is not None:
                refs.append({"kk":f"Жүн: {regional_prod['wool_kg_per_sheep_goat']:.2f} кг/қой-ешкі","ru":f"Шерсть: {regional_prod['wool_kg_per_sheep_goat']:.2f} кг/овцу-козу","en":f"Wool: {regional_prod['wool_kg_per_sheep_goat']:.2f} kg/sheep-goat"}[lang])
            if regional_prod.get("aggregate_meat_kg_per_lu") is not None and livestock_production_kind == "meat_tonnes":
                refs.append({"kk":f"Ет бойынша жүйелік салыстырмалы мән: {regional_prod['aggregate_meat_kg_per_lu']:.1f} кг/шартты мал бірлігі","ru":f"Системное сравнительное значение по мясу: {regional_prod['aggregate_meat_kg_per_lu']:.1f} кг/условную единицу скота","en":f"System meat reference: {regional_prod['aggregate_meat_kg_per_lu']:.1f} kg/LU"}[lang])
            if refs:
                st.info({
                    "kk":"Шаруашылықтың өнім көлемі енгізілмеді. 2023 жылғы аймақтық салыстыру үшін: " + "; ".join(refs),
                    "ru":"Фактический выпуск хозяйства не введен. Для сопоставления показан региональный ориентир 2023 года: " + "; ".join(refs),
                    "en":"Observed farm output was not entered. The 2023 regional comparison reference is: " + "; ".join(refs),
                }[lang])

        # 5. Climate and environmental exposure.
        st.markdown("#### " + {
            "kk":"Климат, энергия және жайылым жағдайы",
            "ru":"Климат, энергия и состояние пастбища",
            "en":"Climate, energy and pasture condition",
        }[lang])
        c1,c2,c3,c4 = st.columns(4)
        c1.metric({"kk":"Температура, сәуір-қыркүйек","ru":"Температура, апрель-сентябрь","en":"Apr-Sep temperature"}[lang],
                  f"{float(livestock.get('temperature_c')):.1f} °C" if livestock.get("temperature_c") is not None else "—")
        c2.metric({"kk":"Жауын-шашын, сәуір-қыркүйек","ru":"Осадки, апрель-сентябрь","en":"Apr-Sep precipitation"}[lang],
                  f"{float(livestock.get('precipitation_mm')):.0f} {UNITS['mm']}" if livestock.get("precipitation_mm") is not None else "—")
        c3.metric({"kk":"Тамыр аймағының ылғалы","ru":"Влажность корневой зоны","en":"Root-zone wetness"}[lang],
                  f"{float(livestock.get('root_zone_wetness')):.3f}" if livestock.get("root_zone_wetness") is not None else "—")
        c4.metric({"kk":"Күн радиациясы","ru":"Солнечная радиация","en":"Solar radiation"}[lang],
                  f"{float(livestock.get('solar_radiation_mj_m2_day')):.2f} {UNITS['solar']}" if livestock.get("solar_radiation_mj_m2_day") is not None else "—")

        c5,c6,c7 = st.columns(3)
        c5.metric({"kk":"Энергия / бас","ru":"Энергия на голову","en":"Energy per head"}[lang],
                  f"{float(livestock.get('energy_kwh_per_head')):,.1f} {UNITS['kwh']}" if livestock.get("energy_kwh_per_head") is not None else "—")
        c6.metric({"kk":"Электр энергиясынан CO₂","ru":"CO₂ от электроэнергии","en":"Electricity CO₂"}[lang],
                  f"{float(livestock.get('operational_co2e_kg'))/1000:,.2f} {UNITS['co2_t']}" if livestock.get("operational_co2e_kg") is not None else "—")
        c7.metric({"kk":"Енгізілген дерек толықтығы","ru":"Полнота фактических данных","en":"Observed-input completeness"}[lang],
                  f"{float(livestock.get('input_completeness_pct',0)):.0f}%")

        if livestock.get("degraded_pasture_ha") is not None:
            st.warning({
                "kk":f"Енгізілген бағалау бойынша деградацияланған жайылым: {float(livestock['degraded_pasture_ha']):,.1f} га ({float(livestock.get('pasture_degraded_share_pct',0)):.1f}%).",
                "ru":f"По введенной оценке деградированное пастбище занимает {float(livestock['degraded_pasture_ha']):,.1f} га ({float(livestock.get('pasture_degraded_share_pct',0)):.1f}%).",
                "en":f"Entered assessment indicates {float(livestock['degraded_pasture_ha']):,.1f} ha of degraded pasture ({float(livestock.get('pasture_degraded_share_pct',0)):.1f}%).",
            }[lang])

        # Report payload keeps reference values and observed inputs distinguishable.
        report_payload["summary"] = [
            {"label":{"kk":"Мал шаруашылығының үлесі","ru":"Доля животноводства в выпуске района","en":"Livestock share of district output"}[lang],
             "value":f"{float(lp.get('livestock_share_pct',0)):.1f}%"},
            {"label":{"kk":"Мал саны","ru":"Поголовье","en":"Herd"}[lang],
             "value":({"kk":"енгізілмеген", "ru":"не указано", "en":"not entered"}[lang] if heads_source == "unknown" else f"{effective_heads:,.0f} ({ {'user': {'kk':'пайдаланушы дерегі','ru':'данные пользователя','en':'user data'}, 'district_reference': {'kk':'аудандық анықтамалық мән','ru':'районное справочное значение','en':'district reference'} }.get(heads_source, {'kk':str(heads_source),'ru':str(heads_source),'en':str(heads_source)})[lang] })"),},
            {"label":{"kk":"Машиналық оқыту болжамы","ru":"Районный прогноз поголовья (ML)","en":"District herd forecast (ML)"}[lang],
             "value":f"{float(forecast.get('forecast_heads')):,.0f} ({forecast.get('forecast_year','—')})" if forecast.get("available") and forecast.get("publish_forecast") else {"kk":"жарияланбайды","ru":"не публикуется","en":"withheld"}[lang]},
            {"label":{"kk":"Шартты мал бірлігі","ru":"Условные единицы скота","en":"Livestock units (LU)"}[lang],
             "value":f"{float(livestock.get('livestock_units')):,.1f}" if livestock.get("livestock_units") is not None else "—"},
        ]
        report_payload["analysis"] = [{
            "kk":f"{district_label(used_district)} аумағындағы «{SPECIES_LABELS[lang][livestock_species]}» ресурстық профилі ресми аудандық динамика, климаттық әсер, мал түріне арналған су мен жемшөптің анықтамалық мөлшерлері және шаруашылық енгізген деректер негізінде есептелді.",
            "ru":f"Ресурсный профиль категории «{SPECIES_LABELS[lang][livestock_species]}» для территории «{district_label(used_district)}» рассчитан по официальной районной динамике, климатическим условиям, справочным потребностям в воде и кормах по виду животных и введенным данным хозяйства.",
            "en":f"The {SPECIES_LABELS[lang][livestock_species]} resource profile for {used_district} integrates official district dynamics, climate exposure, species-specific water/feed references and entered farm observations.",
        }[lang]]
        report_payload["recommendations"] = [{
            "title":{"kk":"Ресурстық теңгерім","ru":"Ресурсный баланс","en":"Resource balance"}[lang],
            "text":{
                "kk":"Мал саны, су қоры, жемшөптің құрғақ заты, жайылым жүктемесі және өнімділік бір жылдық есептік кезеңде салыстырылады.",
                "ru":"Поголовье, водообеспеченность, сухое вещество кормов, пастбищная нагрузка и продуктивность сопоставляются в едином годовом расчетном горизонте.",
                "en":"Herd size, water availability, feed dry matter, pasture pressure and productivity are compared within one annual accounting horizon.",
            }[lang],
            "evidence":{
                "kk":"Аудандық статистикалық қатар, NASA POWER климаттық қабаты және FAO/Merck түрлік анықтамалары.",
                "ru":"Районный статистический ряд, климатический слой NASA POWER и видоспецифические справочные коэффициенты FAO/Merck.",
                "en":"District statistical history, NASA POWER climate layer and FAO/Merck species reference coefficients.",
            }[lang],
            "effect":{
                "kk":"Өндірістік өсудің су, жемшөп және жайылым ресурстарымен үйлесімділігі сандық түрде көрінеді.",
                "ru":"Совместимость производственного масштаба с водой, кормами и пастбищным ресурсом становится количественно наблюдаемой.",
                "en":"Compatibility of production scale with water, feed and pasture resources becomes quantitatively visible.",
            }[lang],
            "evidence_label":{"kk":"Негіздеме","ru":"Основание","en":"Evidence"}[lang],
            "effect_label":{"kk":"Әсер","ru":"Эффект","en":"Effect"}[lang],
        }]
        if heads_source == "unknown":
            report_payload["analysis"] = [{
                "ru":"Поголовье хозяйства не введено. Районная статистика приводится только для сравнения; индивидуальные потребности в воде и кормах, пастбищная нагрузка и экономический эффект не рассчитаны.",
                "kk":"Шаруашылықтағы мал саны енгізілмеген. Аудандық статистика тек салыстыру үшін берілген; су, жемшөп және жайылым жүктемесі жеке шаруашылық үшін есептелмеді.",
                "en":"Farm herd size was not entered. District figures are contextual only; farm water/feed demand, pasture load and economic effect have not been calculated."}[lang]]
            report_payload["recommendations"] = [{
                "title":{"ru":"Нужны данные о поголовье", "kk":"Мал саны туралы дерек қажет", "en":"Farm herd input required"}[lang],
                "text":{"ru":"Введите фактическое количество животных для расчёта потребности вашего хозяйства. Районное поголовье не подставляется вместо него.", "kk":"Шаруашылығыңыз үшін есептеу мақсатында мал санын енгізіңіз. Аудандық көрсеткіш оның орнына қойылмайды.", "en":"Enter your farm herd to calculate farm requirements. District headcounts cannot substitute for it."}[lang],
                "evidence":{"ru":"Отсутствует поголовье хозяйства", "kk":"Шаруашылықтың мал саны белгісіз", "en":"Farm herd is missing"}[lang],
                "effect":{"ru":"Индивидуальный водный и кормовой баланс не рассчитан", "kk":"Жеке су және жемшөп теңгерімі есептелмеді", "en":"Farm water/feed balance not calculated"}[lang]
            }]


    elif mode_key == "mode1" and crop not in CROPS:
        # Expanded farm assessment for crops without a calibrated yield ML model.
        scenario = scenario_for_crop(used_district, crop, climate, irrigation_type)
        obs_ev = observed_for_crop(used_district, crop)
        resource = calculate_resources(
            area_ha=area_ha,
            water_used_m3=effective_water_used if (effective_water_used is not None and effective_water_used > 0) else None,
            reuse_percent=reuse,
            energy_kwh=observed_energy,
            electricity_ef=ef if ef > 0 else None,
            predicted_yield_centners_ha=None,
            water_source=water_input_source,
        )
        st.markdown("### " + {"kk":"Шаруашылықтың ресурстық бағасы","ru":"Ресурсная оценка хозяйства","en":"Farm resource assessment"}[lang])
        if scenario is not None:
            q=float(scenario['QUNAR_score_0_100'])
            a,b,c,d=st.columns(4)
            a.metric({"kk":"QŪNAR бағасы","ru":"Оценка QŪNAR","en":"QŪNAR score"}[lang], f"{q:.1f}/100")
            b.metric({"kk":"Климат","ru":"Климат","en":"Climate"}[lang], f"{float(scenario['Climate_score_0_100']):.1f}/100")
            c.metric({"kk":"Су жүктемесі","ru":"Водная нагрузка","en":"Water pressure"}[lang], f"{float(scenario['Resource_efficiency_0_100']):.1f}/100")
            d.metric({"kk":"Бағалау сенімділігі","ru":"Уверенность в оценке","en":"Assessment confidence"}[lang], f"{float(scenario['Data_reliability_0_100']):.1f}/100")
            st.caption({"kk":"Бұл дақыл үшін жеке машиналық оқыту болжамы қолжетімсіз болғанда аудандық QŪNAR есептік қабаты қолданылады.","ru":"Для этой культуры при отсутствии индивидуального прогноза машинного обучения используется районный расчетный слой QŪNAR.","en":"For this crop, the district QŪNAR decision layer is used instead of an individual ML yield forecast."}[lang])
        else:
            st.info({"kk":"Бұл дақыл бойынша толық аудандық QŪNAR сценарийі жоқ. Шаруашылықтың су, энергия және көміртек көрсеткіштері пайдаланушы енгізген деректер бойынша есептеледі.","ru":"Для этой культуры нет полного районного сценария QŪNAR. Водные, энергетические и углеродные показатели хозяйства рассчитываются по введенным пользователем данным.","en":"No full district QŪNAR scenario is available for this crop. Farm water, energy and carbon indicators are calculated from user inputs."}[lang])
        if "farm_water_m3_per_ha" in resource:
            c1,c2=st.columns(2); c1.metric(t["water_use"], f"{resource['farm_water_m3_per_ha']:,.0f} {UNITS['m3_ha']}"); c2.metric(t["freshwater"], f"{resource['farm_freshwater_m3']:,.0f} {UNITS['m3']}")
        if "energy_kwh_per_ha" in resource:
            st.metric(t["energy_use"], f"{resource['energy_kwh_per_ha']:,.0f} {UNITS['kwh_ha']}")
        elif "reference_pumping_energy_kwh_per_ha" in resource:
            st.caption({"kk":"Сорғы электр энергиясын анықтау үшін нақты арыны мен жалпы КПД қажет. Әмбебап кВт·сағ/м³ нормативі қолданылмайды.","ru":"Для расчёта насосной электроэнергии нужны напор и общий КПД. Универсальная норма кВт·ч/м³ не подставляется.","en":"Pump electricity requires documented total head and overall efficiency. No universal kWh/m³ value is imputed."}[lang])
        if "operational_co2e_kg_per_ha" in resource: st.metric(t["co2"], f"{resource['operational_co2e_kg_per_ha']:,.1f} {UNITS['co2_kg_ha']}")
        econ = economic_climate_effect(energy_kwh=(energy_reference.value if _grid_known else None), freshwater_m3=resource.get("farm_freshwater_m3"), electricity_tariff=electricity_tariff, water_tariff=water_tariff, emission_factor=ef, current_solar_share=current_solar, target_solar_share=target_solar, water_saving_target=water_saving_target)
        if user_level != "farmer":
            st.markdown("### " + t["climate_cost_title"])
            e1,e2,e3,e4=st.columns(4)
            e1.metric(t["energy_cost"], f"{econ['current_energy_cost_kzt']:,.0f} {UNITS['currency']}" if _grid_known else "—")
            e2.metric(t["water_cost"], f"{econ['current_water_cost_kzt']:,.0f} {UNITS['currency']}" if econ['current_water_cost_kzt'] is not None else "—")
            e3.metric(t["co2_reduction"], f"{econ['co2_reduction_kg']/1000:,.2f} {UNITS['t']} CO₂" if _grid_known else "—")
            e4.metric(t["total_saving"], f"{econ['total_saving_kzt']:,.0f} {UNITS['currency']}" if _grid_known and econ['total_saving_kzt'] is not None else "—")
        st.markdown("### " + {"kk":"Практикалық қорытынды","ru":"Практический вывод","en":"Practical conclusion"}[lang])
        if scenario is not None:
            st.write({"kk":f"{extended_crop_label(crop,lang)} бойынша негізгі шектеулер климат, нормативтік су жүктемесі және дерек сенімділігі бірге қарастырылып бағаланды.","ru":f"Для культуры «{extended_crop_label(crop,lang)}» ограничения оцениваются совместно по климату, нормативной водной нагрузке и надежности исходных данных.","en":f"For {extended_crop_label(crop,lang)}, constraints are assessed jointly through climate, normative water demand and evidence reliability."}[lang])
        if user_level == "researcher":
            with st.expander(t["model_inputs"]):
                st.write({"kk":f"Есеп координатасы: {calc_lat:.6f}, {calc_lon:.6f}; қолданылған аудан: {district_label(used_district)}; әдіс: {model_tier_label(crop_method(crop))}.","ru":f"Координаты расчета: {calc_lat:.6f}, {calc_lon:.6f}; использованный район: {district_label(used_district)}; метод: {model_tier_label(crop_method(crop))}.","en":f"Calculation coordinates: {calc_lat:.6f}, {calc_lon:.6f}; district used: {district_label(used_district)}; method: {model_tier_label(crop_method(crop))}."}[lang])

    elif mode_key == "mode1":
        with st.spinner(t["ml_loading"]):
            pred, used = timed_call("ML prediction", predict_yield, used_district, crop, area_ha, climate)
        _original_rf_pred = pred
        _yield_choice = route_yield(DATA_DIR, used_district, crop, calculation_year, rf_value=pred)
        _active_yield = _yield_choice.active_value
        if _active_yield is not None:
            pred = _active_yield
        # The RF remains the first computed model and is always reported separately;
        # alternatives are only descriptive when its forward verification fails.
        report_payload['summary'].append({
            'label':{'ru':'Основной алгоритм проекта: Random Forest, ц/га','kk':'Жобаның негізгі алгоритмі: Random Forest, ц/га','en':'Project primary algorithm: Random Forest, c/ha'}[lang],
            'value':f'{_original_rf_pred:.2f}',
            'note':{'ru':'Отдельная оценка ML; проверка на будущих годах приведена ниже. Не измеренная урожайность поля.',
                    'kk':'ML бағасы; кейінгі жылдардағы тексеру төменде. Танаптың нақты өнімі емес.',
                    'en':'ML benchmark; later-year validation below, not observed field yield.'}[lang]})
        report_payload['summary'].append({
            'label':{'ru':'Метод, используемый в оценке урожайности','kk':'Өнімділікті бағалау үшін таңдалған әдіс','en':'Method selected for yield assessment'}[lang],
            'value':({'Random Forest':'Random Forest', 'Historical district-crop median':{'ru':'Историческая медиана района и культуры','kk':'Аудан мен дақылдың тарихи медианасы','en':'Historical district-crop median'}[lang], 'Regional crop median (proxy)':{'ru':'Региональная медиана культуры (ориентир)','kk':'Дақылдың өңірлік медианасы (бағдар)','en':'Regional crop median (proxy)'}[lang], 'Not verified':{'ru':'Недостаточно данных','kk':'Деректер жеткіліксіз','en':'Insufficient data'}[lang]}.get(_yield_choice.active_method, _yield_choice.active_method)),
            'note':method_caveat(_yield_choice,lang)})
        if not _yield_choice.ml_supported:
            st.warning({'ru':'ML по этой культуре не прошёл заданные критерии временной валидации. Для планирования показан исторический районный ориентир, который не является достоверным прогнозом следующего года.',
                        'kk':'Бұл дақыл бойынша ML уақытша тексеру талаптарынан өтпеді. Жоспарлау үшін келесі жылдың кепілді болжамы емес, тарихи аудандық көрсеткіш қолданылады.',
                        'en':'ML did not meet predeclared forward-year accuracy criteria. A descriptive district history is used for planning, NOT a validated next-year forecast.'}[lang])
        if user_level == 'researcher':
            _history_methods = all_method_history(Path(DATA_DIR).parent/'examples'/'stage2_evidence',crop)
            if _history_methods:
                with st.expander({'ru':'Сравнение альтернативных методов прогнозирования (валидация до 2021 г.)','kk':'Баламалы болжам әдістерін салыстыру (2021 жылға дейін)','en':'Alternative forecasting methods (pre-2021 validation)'}[lang]):
                    _method_names={'Pooled RF':'Random Forest (общая модель)','Per-crop RF':'Random Forest (по культуре)','ExtraTrees':'ExtraTrees','CatBoost':'CatBoost','HistGradientBoosting':'Градиентный бустинг','Ridge':'Ridge (регрессия)','Historical median':'Историческая медиана'}
                    st.dataframe(pd.DataFrame([{'Метод' if lang=='ru' else 'Method':_method_names.get(r['method'],r['method']),
                          'MAE, ц/га' if lang=='ru' else 'MAE, c/ha':round(r['mae_c_ha'],2),
                          'R²':round(r['r2'],3), 'N':r['n']} for r in _history_methods]),use_container_width=True,hide_index=True)
                    st.caption({'ru':'Алгоритмы сравнивались на предшествующих годах, без обучения на тестовых годах. Выбор альтернативы по 2021–2025 задним числом запрещён; низкая ошибка на ранних годах не доказывает качество следующего сезона.',
                                'kk':'Әдістер бұрынғы жылдарда сыналды. 2021–2025 жылдар бойынша кейіннен үздік әдісті таңдау ғылыми дәлел емес.',
                                'en':'Methods compared on earlier years without using future observations in fitting. No post-hoc selection from 2021–2025.'}[lang])

        # WaPOR is retrieved after ML because water productivity uses predicted output.
        wapor_result = None
        wapor_water = None
        wapor_pixels = None
        if use_wapor:
            try:
                today = date.today()
                season_start = date(today.year, 4, 1)
                season_end = min(today, date(today.year, 9, 30))
                if season_end >= season_start:
                    with st.spinner(t["wapor_loading"]):
                        if not calc_geojson:
                            raise WaPORError("WAPOR_FIELD_POLYGON_REQUIRED")
                        wapor_result = seasonal_aeti(
                            season_start,
                            season_end,
                            geometry_geojson=calc_geojson,
                        )
                    wapor_water = consumptive_water_metrics(wapor_result["aeti_mm"], area_ha, pred)
                    if wapor_result.get("details"):
                        wapor_pixels = max(int(x.get("pixels", 0)) for x in wapor_result["details"])
            except WaPORError as exc:
                if str(exc) == "WAPOR_DEPENDENCY_MISSING":
                    st.warning(t["wapor_dependency"])
                elif str(exc) == "WAPOR_FIELD_POLYGON_REQUIRED":
                    st.warning(t["wapor_polygon_required"])
                else:
                    st.warning(t["wapor_error"])
            except Exception:
                st.warning(t["wapor_error"])

        resource = calculate_resources(
            area_ha=area_ha,
            water_used_m3=effective_water_used if (effective_water_used is not None and effective_water_used > 0) else None,
            reuse_percent=reuse,
            energy_kwh=observed_energy,
            electricity_ef=ef if ef > 0 else None,
            wapor_consumptive_water_m3=(
                wapor_water["consumptive_water_total_m3"] if wapor_water else None
            ),
            predicted_yield_centners_ha=pred,
            water_source=water_input_source,
        )

        has_location = bool(calc_geojson)
        ctx_for_support = district_crop_context(used_district, crop)
        val_for_support = validation_for_crop(crop)
        reliability = support_score(
            exact_location=has_location,
            live_climate=live_ok,
            actual_water=water_input_source == "user",
            actual_energy=observed_energy is not None,
            emission_factor=ef > 0,
            wapor_used=bool(wapor_water),
            wapor_pixels=wapor_pixels,
            area_geometry_mismatch=area_geometry_mismatch,
            ml_mae=val_for_support.get("mae"),
            historical_yield_median=(ctx_for_support or {}).get("historical_yield_median"),
        )

        _active_yield_label=(t['baseline_label'] if _yield_choice.ml_supported else
            {'ru':'Исторический ориентир (не прогноз), ц/га','kk':'Тарихи анықтама (болжам емес), ц/га','en':'Historical reference (not forecast), c/ha'}[lang])
        if user_level == "farmer":
            x,z=st.columns(2)
            x.metric(_active_yield_label, f"{pred:.1f} {UNITS['centner_ha']}")
            z.metric(t["climate"], climate_source)
            st.caption(t["scope_note"])
        else:
            x,y,z=st.columns(3)
            x.metric(_active_yield_label, f"{pred:.1f} {UNITS['centner_ha']}")
            y.metric(t["support_label"], f"{t[reliability['level']]} ({reliability['score']}/100)")
            z.metric(t["climate"], climate_source)
            st.caption(t["scope_note"] + " " + t["support_note"])
        if mode_key == "mode2":
            st.info(t.get("mode2_distinct_note", ""))

        if "farm_water_m3_per_ha" in resource:
            x1, x2 = st.columns(2)
            x1.metric(t["water_use"], f"{resource['farm_water_m3_per_ha']:,.0f} {UNITS['m3']}/га" if lang != "en" else f"{resource['farm_water_m3_per_ha']:,.0f} m³/ha")
            x2.metric(t["freshwater"], f"{resource['farm_freshwater_m3']:,.0f} {UNITS['m3']}" if lang != "en" else f"{resource['farm_freshwater_m3']:,.0f} {UNITS['m3']}")

        if "energy_kwh_per_ha" in resource:
            st.metric(t["energy_use"], f"{resource['energy_kwh_per_ha']:,.0f} кВт·ч/га" if lang != "en" else f"{resource['energy_kwh_per_ha']:,.0f} kWh/ha")

        if "operational_co2e_kg_per_ha" in resource:
            st.metric(t["co2"], f"{resource['operational_co2e_kg_per_ha']:,.1f} кг CO₂e/га" if lang != "en" else f"{resource['operational_co2e_kg_per_ha']:,.1f} kg CO₂e/ha")

        # Economic reference is explicitly scenario-based unless it is an observation.
        # In particular, a user-confirmed measured zero MUST NOT trigger a pumping fallback.
        if observed_energy is not None:
            economic_energy_kwh = float(observed_energy)
            economic_energy_source = "user_observed"
        elif energy_reference.value is not None:
            economic_energy_kwh = float(energy_reference.value)
            economic_energy_source = energy_reference.source_tier + ': '+energy_reference.source
        else:
            # Preserve missing energy as unknown; no silent 0 kWh.
            economic_energy_kwh = None
            economic_energy_source = "unknown_electricity_no_estimate"
        report_payload["inputs"].append([
            {"kk":"Экономикалық сценарийдегі электр энергиясы","ru":"Электроэнергия в экономическом сценарии","en":"Electricity in economic scenario"}[lang],
            f"{economic_energy_kwh:,.2f} кВт·ч" if economic_energy_kwh is not None else {"kk":"белгісіз","ru":"неизвестно","en":"unknown"}[lang],
            economic_energy_source + ("; НЕ фактическое потребление, исходный коэффициент не подтверждён как норматив РК" if economic_energy_source.startswith("hypothetical") else ""),
        ])
        if economic_energy_kwh is None:
            st.caption({
                "ru":"Расход электроэнергии неизвестен. Для расчёта насосной энергии укажите напор, КПД и границу услуги; нулевой расход не предполагается.",
                "kk":"Электр энергиясының шығыны белгісіз. Сорғы есебі үшін арын, КПД және қызмет шекарасы қажет; нөлдік шығын болжанбайды.",
                "en":"Electricity consumption is unknown. Pump energy needs head, efficiency and the service boundary; zero consumption is not assumed.",
            }[lang])
        econ = economic_climate_effect(
            energy_kwh=economic_energy_kwh,
            freshwater_m3=resource.get("farm_freshwater_m3"),
            electricity_tariff=electricity_tariff,
            water_tariff=water_tariff,
            emission_factor=ef,
            current_solar_share=current_solar,
            target_solar_share=target_solar,
            water_saving_target=water_saving_target,
        )
        if mode_key == "mode1" and user_level != "farmer":
            st.markdown("### " + t["climate_cost_title"])
            ec1, ec2, ec3, ec4 = st.columns(4)
            ec1.metric(t["grid_energy"], (f"{econ['current_grid_energy_kwh']:,.0f} кВт·ч" if lang != "en" else f"{econ['current_grid_energy_kwh']:,.0f} kWh") if _grid_known else "—")
            ec2.metric(t["co2_calc"], (f"{econ['current_co2_kg']/1000:,.2f} т CO₂" if lang != "en" else f"{econ['current_co2_kg']/1000:,.2f} t CO₂") if _grid_known else "—")
            ec3.metric(t["energy_cost"], f"{econ['current_energy_cost_kzt']:,.0f} {UNITS['currency']}" if _grid_known else "—")
            ec4.metric(t["water_cost"], f"{econ['current_water_cost_kzt']:,.0f} {UNITS['currency']}" if econ['current_water_cost_kzt'] is not None else "—")
            wc1, wc2, wc3, wc4 = st.columns(4)
            wc1.metric(t["green_saving"], (f"{econ['energy_saving_kzt']:,.0f} тг" if lang != "en" else f"{econ['energy_saving_kzt']:,.0f} {UNITS['currency']}") if _grid_known else "—")
            wc2.metric(t["water_saving"], (f"{econ['water_saving_m3']:,.0f} {UNITS['m3']} / {econ['water_saving_kzt']:,.0f} {UNITS['currency']}" if econ['water_saving_kzt'] is not None else "—"))
            wc3.metric(t["co2_reduction"], f"{econ['co2_reduction_kg']/1000:,.2f} т CO₂" if _grid_known else "—")
            wc4.metric(t["total_saving"], f"{econ['total_saving_kzt']:,.0f} {UNITS['currency']}" if _grid_known and econ['total_saving_kzt'] is not None else "—")
            pb = payback_years(investment, econ["total_saving_kzt"], seasons_per_year) if _grid_known else None
            if pb is not None:
                st.caption(f"{t['payback']}: {pb:.1f} " + ("жыл" if lang == "kk" else "лет" if lang == "ru" else "years"))
            else:
                st.caption(t["payback_na"])
            st.markdown("#### " + t["climate_helper"])
            st.write(t["helper_green"])
            st.write(t["helper_drip_existing"] if irrigation_type == "drip" else t["helper_drip_missing"])

        if mode_key == "mode2":
            st.markdown("### " + {"kk":"Дақылдың жарамдылығы","ru":"Пригодность выбранной культуры","en":"Selected crop suitability"}[lang])
            ctx2 = district_crop_context(used_district, crop) or {}
            med2 = ctx2.get("historical_yield_median")
            if med2 is not None:
                diff2 = (pred - float(med2)) / max(float(med2), 0.0001) * 100
                if diff2 >= 0:
                    st.success({"kk":f"Болжам тарихи медианадан {abs(diff2):.1f}% жоғары.","ru":f"Прогноз на {abs(diff2):.1f}% выше исторической медианы.","en":f"The prediction is {abs(diff2):.1f}% above the historical median."}[lang])
                else:
                    st.warning({"kk":f"Болжам тарихи медианадан {abs(diff2):.1f}% төмен. Дақылды су, энергия және климаттық тәуекел бойынша қосымша тексеру қажет.","ru":f"Прогноз на {abs(diff2):.1f}% ниже исторической медианы. Культуру нужно дополнительно проверить по воде, энергии и климатическому риску.","en":f"The prediction is {abs(diff2):.1f}% below the historical median. The crop needs additional checking by water, energy and climate risk."}[lang])
            st.write({"kk":"Бұл блок шаруашылықты толық бағалау емес, таңдалған дақылдың жарамдылығын тексереді.",
                      "ru":"Этот блок не заменяет полный отчет по хозяйству, а проверяет пригодность выбранной культуры.",
                      "en":"This block does not replace the full farm report; it checks suitability of the selected crop."}[lang])

        if wapor_water:
            wc1, wc2, wc3 = st.columns(3)
            wc1.metric(t["wapor_aeti"], f"{wapor_result['aeti_mm']:.1f} мм" if lang != "en" else f"{wapor_result['aeti_mm']:.1f} mm")
            wc2.metric(t["wapor_consumptive"], f"{wapor_water['consumptive_water_m3_per_ha']:,.0f} {UNITS['m3']}/га" if lang != "en" else f"{wapor_water['consumptive_water_m3_per_ha']:,.0f} m³/ha")
            wc3.metric(t["wapor_wp"], f"{wapor_water['modelled_water_productivity_kg_m3']:.2f} кг/{UNITS['m3']}" if lang != "en" else f"{wapor_water['modelled_water_productivity_kg_m3']:.2f} kg/m³")
            st.caption(t["wapor_note"])
            if wapor_pixels is not None and wapor_pixels <= 3:
                st.warning(t["small_field_warning"])

        if mode_key == "mode1" and user_level == "farmer":
            st.markdown("### " + {"kk":"Ақша және климат әсері","ru":"Деньги и климатический эффект","en":"Money and climate effect"}[lang])
            c1,c2,c3=st.columns(3)
            c1.metric({"kk":"Электр шығыны","ru":"Расходы на электроэнергию","en":"Electricity cost"}[lang], f"{econ['current_energy_cost_kzt']:,.0f} {UNITS['currency']}" if _grid_known else "—")
            c2.metric({"kk":"Су шығыны","ru":"Стоимость воды","en":"Water cost"}[lang], f"{econ['current_water_cost_kzt']:,.0f} {UNITS['currency']}" if econ['current_water_cost_kzt'] is not None else "—")
            c3.metric({"kk":"Сценарийлік үнем","ru":"Потенциальная экономия","en":"Potential saving"}[lang], f"{econ['total_saving_kzt']:,.0f} {UNITS['currency']}" if _grid_known and econ['total_saving_kzt'] is not None else "—")

        if mode_key == "mode1":
            ref_m3_ha = float(water_default_info.m3_ha) if water_default_info is not None else 0.0
            smart = smart_resource_scenario(
                lang=lang, irrigation_type=irrigation_type, actual_water_m3=effective_water_used if effective_water_used is not None else 0.0,
                area_ha=area_ha, reference_water_m3_ha=ref_m3_ha, energy_kwh=energy_reference.value,
                water_tariff=water_tariff, electricity_tariff=electricity_tariff,
                saving_target_pct=water_saving_target, investment=investment, seasons_per_year=seasons_per_year,
                water_source=("user" if water_input_source == "user" else "district_crop_reference"),
                energy_source=(energy_reference.source_tier if energy_reference.value is not None else "unknown"),
            )
            st.markdown("### " + {"kk":"Ақылды ресурс үнемдеу ұсынысы","ru":"Умная рекомендация по экономии ресурсов","en":"Smart resource-saving recommendation"}[lang])
            st.caption({"kk":f"Сценарий дәлелінің деңгейі: {smart.get('evidence_grade','—')}.","ru":f"Уровень доказательности сценария: {smart.get('evidence_grade','—')}.","en":f"Scenario evidence grade: {smart.get('evidence_grade','—')}."}[lang])
            st.write(smart["status"])
            st.markdown(f'<div class="qunar-reco"><strong>{html.escape(smart["recommendation"])}</strong></div>', unsafe_allow_html=True)
            sc1,sc2,sc3,sc4=st.columns(4)
            sc1.metric({"kk":"Бастапқы су","ru":"Исходная вода","en":"Baseline water"}[lang], f"{smart['before_water_m3']:,.0f} {UNITS['m3']}")
            sc2.metric({"kk":"Сценарийден кейін","ru":"После сценария","en":"After scenario"}[lang], f"{smart['after_water_m3']:,.0f} {UNITS['m3']}")
            sc3.metric({"kk":"Су үнемі","ru":"Экономия воды","en":"Water saving"}[lang], f"{smart['saved_water_m3']:,.0f} {UNITS['m3']}")
            sc3.caption({"kk":"Су үнемі", "ru":"Снижение расхода воды", "en":"Water use reduction"}[lang] + f": {smart['saving_target_pct']:.0f}%")
            sc4.metric({"kk":"Ресурстық шығын үнемі","ru":"Экономия ресурсных затрат","en":"Resource-cost saving"}[lang], f"{smart['total_saving_kzt']:,.0f} {UNITS['currency']}")
            st.caption({"kk":f"Дереккөздер: су - {smart['water_source']}; энергия - {smart['energy_source']}; тариф - {smart['tariff_source']}.","ru":f"Источники: вода - {smart['water_source']}; энергия - {smart['energy_source']}; тариф - {smart['tariff_source']}.","en":f"Sources: water - {smart['water_source']}; energy - {smart['energy_source']}; tariff - {smart['tariff_source']}."}[lang])
            e1,e2=st.columns(2)
            e1.metric({"kk":"Энергия, бастапқы","ru":"Энергия, исходно","en":"Energy, baseline"}[lang], (f"{smart['before_energy_kwh']:,.0f} {UNITS['kwh']}" if smart['before_energy_kwh'] is not None else "—"))
            e2.metric({"kk":"Энергия, сценарий","ru":"Энергия, сценарий","en":"Energy, scenario"}[lang], (f"{smart['after_energy_kwh']:,.0f} {UNITS['kwh']}" if smart['after_energy_kwh'] is not None else "—"))
            if smart['investment_used_kzt'] > 0:
                i1,i2=st.columns(2)
                i1.metric({"kk":"Сценарийлік инвестиция","ru":"Сценарная инвестиция","en":"Scenario investment"}[lang], f"{smart['investment_used_kzt']:,.0f} {UNITS['currency']}")
                if smart.get("payback_years") is not None:
                    i2.metric({"kk":"Өтелу мерзімі","ru":"Окупаемость","en":"Payback"}[lang], f"{smart['payback_years']:.1f} " + {"kk":"жыл","ru":"года","en":"years"}[lang])
            else:
                st.caption({"kk":"Технология құны енгізілмеген: инвестиция мен өтелу мерзімі автоматты түрде ойдан шығарылмайды.","ru":"Стоимость технологии не введена: инвестиция и срок окупаемости автоматически не подставляются.","en":"Technology cost was not entered: investment and payback are not auto-filled."}[lang])
            report_payload["summary"].extend([
                {"label":{"kk":"Бөлек ресурс үнемдеу сценарийі: су","ru":"Отдельный сценарий ресурсосбережения: вода","en":"Separate resource-saving scenario: water"}[lang],"value":f"{smart['saved_water_m3']:,.0f} m³"},
                {"label":{"kk":"Бөлек сценарий: тек есептелген шығын үнемі","ru":"Отдельный сценарий: снижение только рассчитанных затрат","en":"Separate scenario: known cost reductions only"}[lang],"value":f"{smart['total_saving_kzt']:,.0f} {UNITS['currency']}"},
            ])

        analysis = build_analysis(
            lang=lang,
            district=used_district,
            crop_label=crop_label(crop),
            crop_code=crop,
            pred_yield=pred,
            climate=climate,
            resource=resource,
            reliability=reliability,
            available_water=available_water,
            wapor_result=wapor_result,
        )
        ctx_rec = district_crop_context(used_district, crop) or {}
        recs = build_recommendations(
            lang, pred, ctx_rec.get("historical_yield_median"),
            available_water, resource, t
        )
        if mode_key == "mode1":
            st.markdown("### " + t["explanation"])
            for paragraph in analysis:
                st.markdown(insight_html(paragraph), unsafe_allow_html=True)
            if recs:
                st.markdown("### " + t["recommendation"])
                for r in recs:
                    st.markdown(f'<div class="qunar-reco"><strong>{html.escape(str(r))}</strong></div>', unsafe_allow_html=True)
        else:
            st.markdown("### " + {"kk":"Қысқаша қорытынды","ru":"Краткий вывод","en":"Short conclusion"}[lang])
            med = ctx_rec.get("historical_yield_median")
            if med:
                delta = (pred-float(med))/max(float(med),0.0001)*100
                verdict = ({"kk":"шартты түрде жарамды","ru":"подходит с ограничениями","en":"suitable with constraints"} if delta < -10 else {"kk":"жарамды","ru":"подходит","en":"suitable"})
                st.write({"kk":f"{crop_label(crop)}: {verdict['kk']}. Болжам тарихи медианамен салыстырғанда {delta:+.1f}%.",
                          "ru":f"{crop_label(crop)}: {verdict['ru']}. Прогноз относительно исторической медианы {delta:+.1f}%.",
                          "en":f"{crop_label(crop)}: {verdict['en']}. Prediction versus historical median: {delta:+.1f}%."}[lang])
            st.caption({"kk":"Толық су-энергетикалық және экономикалық есеп «Менің шаруашылығымды бағалау» режимінде көрсетіледі.",
                        "ru":"Полный водно-энергетический и экономический отчет доступен в режиме «Оценить мое хозяйство».",
                        "en":"The full water-energy and economic report is available in the farm-assessment mode."}[lang])

        if user_level == "researcher":
            with st.expander(t["model_inputs"]):
                ctx = district_crop_context(used_district, crop)
                detected_label = st.session_state.get("detected_map_district")
                rows = [
                    [t.get("district_selected", t["district"]), district_label(district), t["source_user"]],
                    [t.get("district_used", t["district"]), district_label(used_district), {"kk":"Әкімшілік полигон/пайдаланушы таңдауы","ru":"Административный полигон/выбор пользователя","en":"Administrative polygon/user selection"}[lang]],
                    [t.get("district_detected", {"kk":"Карта бойынша алдын ала анықталған аудан","ru":"Предварительный район по карте","en":"Provisional district from map"}[lang]), district_label(detected_label) if detected_label else "—", {"kk":"Түркістан облысының әкімшілік полигондары","ru":"Административные полигоны Туркестанской области","en":"Turkestan administrative polygons"}[lang]],
                    [t["crop"], crop_label(crop), t["source_user"]],
                    [t["area"], f"{area_ha:.2f}", t["source_user"]],
                    [{"kk":"Есеп координатасы (ендік, бойлық)","ru":"Координаты расчета (широта, долгота)","en":"Calculation coordinates (lat, lon)"}[lang], f"{calc_lat:.6f}, {calc_lon:.6f}", {"kk":"Карта контуры" if location_source == "map" else "Аудан координатасы","ru":"Контур карты" if location_source == "map" else "Координата района","en":"Map polygon" if location_source == "map" else "District coordinate"}[lang]],
                    [{"kk":"Аудан бойынша дақылдың тарихи егіс алаңы, мың га","ru":"Историческая посевная площадь культуры по району, тыс. га","en":"Historical district crop sown area, th. ha"}[lang], f"{used['Sown area, th. ha']:.3f}", t["source_ml"]],
                    [{"kk":"Сәуір-қыркүйек температурасы, °C","ru":"Температура апрель-сентябрь, °C","en":"Apr-Sep temperature, °C"}[lang], f"{used['Apr-Sep temperature, °C']:.3f}", climate_source],
                    [{"kk":"Сәуір-қыркүйек жауын-шашыны, мм","ru":"Осадки апрель-сентябрь, мм","en":"Apr-Sep precipitation, mm"}[lang], f"{used['Apr-Sep precipitation, mm']:.2f}", climate_source],
                    [{"kk":"Тамыр аймағының ылғалдылығы","ru":"Влажность корневой зоны","en":"Root-zone wetness"}[lang], f"{used['Apr-Sep root-zone wetness']:.4f}", climate_source],
                    [{"kk":"Күн радиациясы, МДж/м²/тәулік","ru":"Солнечная радиация, МДж/м²/сутки","en":"Solar radiation, MJ/m²/day"}[lang], f"{used['Apr-Sep solar radiation, MJ/m²/day']:.3f}", climate_source],
                ]
                if ctx:
                    rows += [
                        [{"kk":"Тарихи өнімділік медианасы, ц/га","ru":"Историческая медиана урожайности, ц/га","en":"Historical yield median, c/ha"}[lang], f"{ctx['historical_yield_median']:.2f}", {
                            "kk":f"{int(ctx['first_year'])}-{int(ctx['last_year'])}; бақылау саны={int(ctx['n_years'])}",
                            "ru":f"{int(ctx['first_year'])}-{int(ctx['last_year'])}; наблюдений={int(ctx['n_years'])}",
                            "en":f"{int(ctx['first_year'])}-{int(ctx['last_year'])}; observations={int(ctx['n_years'])}",
                        }[lang]],
                        [{"kk":"Тарихи өнімділік Q25-Q75, ц/га","ru":"Историческая урожайность Q25-Q75, ц/га","en":"Historical yield Q25-Q75, c/ha"}[lang], f"{ctx['historical_yield_q25']:.2f}-{ctx['historical_yield_q75']:.2f}", t["source_history"]],
                    ]
                rows.extend([
                    [{"kk":"Эмиссия коэффициенті, кг CO₂/кВт·сағ","ru":"Коэффициент эмиссии, кг CO₂/кВт·ч","en":"Emission factor, kg CO₂/kWh"}[lang], f"{ef:.4f}", {"kk":"Халықаралық энергетикалық агенттік (IEA), 2025 / өзгертілетін есептік сценарий","ru":"Международное энергетическое агентство (IEA), 2025 / редактируемый расчетный сценарий","en":"IEA Emissions Factors 2025 / editable scenario"}[lang]],
                    [{"kk":"Электр тарифі, тг/кВт·сағ","ru":"Тариф электроэнергии, тг/кВт·ч","en":"Electricity tariff, KZT/kWh"}[lang], f"{electricity_tariff:.4f}", {"kk":"Өзгертілетін анықтамалық сценарий; шаруашылықтың немесе жеткізушінің тарифімен ауыстырылады","ru":"Редактируемый справочный сценарий; заменяется тарифом хозяйства или поставщика","en":"Editable reference scenario; replace with farm/provider tariff"}[lang]],
                    [{"kk":"Су тарифі, тг/м³","ru":"Тариф воды, тг/м³","en":"Water tariff, KZT/m³"}[lang], f"{water_tariff:.4f}", {"kk":"Өзгертілетін анықтамалық сценарий; қызмет түріне байланысты нақты тариф енгізіледі","ru":"Редактируемый справочный сценарий; фактический тариф зависит от вида услуги","en":"Editable reference scenario; service type matters"}[lang]],
                    [{"kk":"Қазіргі жасыл энергия үлесі, %","ru":"Текущая доля зеленой энергии, %","en":"Current green energy share, %"}[lang], f"{current_solar:.1f}", t["source_user"]],
                    [{"kk":"Сценарий: жасыл энергия үлесі, %","ru":"Сценарий: доля зеленой энергии, %","en":"Scenario: green-energy share, %"}[lang], f"{target_solar:.1f}", {"kk":"Сценарийлік алғышарт","ru":"Сценарное допущение","en":"Scenario assumption"}[lang]],
                    [{"kk":"Сценарий: су үнемі, %","ru":"Сценарий: снижение свежей воды, %","en":"Scenario: freshwater saving, %"}[lang], f"{water_saving_target:.1f}", {"kk":"Сценарийлік алғышарт","ru":"Сценарное допущение","en":"Scenario assumption"}[lang]],
                ])
                st.dataframe(pd.DataFrame(rows, columns=[t["audit_parameter"],t["audit_value"],t["audit_source"]]), use_container_width=True, hide_index=True)
                val = validation_for_crop(crop)
                if user_level == "researcher" and val.get("mae") is not None:
                    if lang == "ru":
                        st.caption(f"Проверка качества машинного обучения по годам: средняя абсолютная ошибка (MAE)={val['mae']:.2f} ц/га; корень из средней квадратичной ошибки (RMSE)={val.get('rmse', float('nan')):.2f} ц/га; R²={val['r2']:.3f}; 5 временных блоков; число наблюдений={val['n']}.")
                    elif lang == "kk":
                        st.caption(f"Машиналық оқыту сапасын жылдар бойынша тексеру: орташа абсолюттік қате (MAE)={val['mae']:.2f} ц/га; орташа квадраттық қатенің түбірі (RMSE)={val.get('rmse', float('nan')):.2f} ц/га; R²={val['r2']:.3f}; 5 уақыттық блок; бақылау саны={val['n']}.")
                    else:
                        st.caption(f"ML validation by year: MAE={val['mae']:.2f} centners/ha; RMSE={val.get('rmse', float('nan')):.2f} centners/ha; R²={val['r2']:.3f}; 5 year-groups; N={val['n']}.")
                    _sv = spatial_validation_summary()
                    if _sv:
                        st.caption({"kk":f"Кеңістіктік тасымалдану стресс-тесті (leave-one-district-out): R²={_sv['r2']:.3f}, MAE={_sv['mae']:.2f}, RMSE={_sv['rmse']:.2f}, {int(_sv['districts'])} аумақ.","ru":f"Стресс-тест пространственной переносимости leave-one-district-out: R²={_sv['r2']:.3f}, MAE={_sv['mae']:.2f}, RMSE={_sv['rmse']:.2f}, {int(_sv['districts'])} территорий.","en":f"Leave-one-district-out spatial transferability stress test: R²={_sv['r2']:.3f}, MAE={_sv['mae']:.2f}, RMSE={_sv['rmse']:.2f}, {int(_sv['districts'])} territories."}[lang])

        if user_level == "researcher":
            _future = forward_holdout_for_crop(crop)
            if _future:
                st.caption({
                    "ru":f"Прямая временная проверка ML (обучение до 2020 г., тест 2021–2025): R²={_future['r2']:.3f}, MAE={_future['mae']:.2f} ц/га, N={_future['n']}. Отрицательный R² указывает на слабое качество прогноза на этом периоде.",
                    "kk":f"ML уақыттық тексеруі (2020 жылға дейін оқыту, 2021–2025 сынағы): R²={_future['r2']:.3f}, MAE={_future['mae']:.2f} ц/га, N={_future['n']}. Теріс R² осы кезеңдегі болжам сапасының төмендігін көрсетеді.",
                    "en":f"Forward ML test (train through 2020, test 2021–2025): R²={_future['r2']:.3f}, MAE={_future['mae']:.2f} centners/ha, N={_future['n']}. Negative R² indicates weak predictions in this period."
                }[lang])
            _pi = prediction_interval_for_crop(crop)
            if _pi and _pi.get("is_forward_backtest"):
                _coverage_pct = 100.0 * _pi["empirical_coverage"]
                st.caption({
                    "ru": f"Историческая проверка интервалов: ширина ±{_pi['half_width_centners_ha']:.1f} ц/га рассчитана до 2021 г.; фактическое покрытие за 2021–2025 гг. = {_coverage_pct:.1f}% при целевых 90% (N={_pi['n']}). Это не гарантия для нового прогноза.",
                    "kk": f"Аралықтардың тарихи тексеруі: ±{_pi['half_width_centners_ha']:.1f} ц/га ені 2021 жылға дейін есептелген; 2021–2025 жылдардағы нақты қамту {_coverage_pct:.1f}%, мақсаттысы 90% (N={_pi['n']}). Бұл жаңа болжамның кепілдігі емес.",
                    "en": f"Historical interval backtest: width ±{_pi['half_width_centners_ha']:.1f} centners/ha calibrated before 2021; observed 2021–2025 coverage {_coverage_pct:.1f}% versus nominal 90% (N={_pi['n']}). This does not guarantee coverage of a new forecast."
                }[lang])
            elif _pi:
                st.caption({
                    "ru":"Доступна только ретроспективная калибровка на тех же остатках; независимое покрытие не проверено.",
                    "kk":"Тек сол қалдықтар бойынша тарихи калибрлеу бар; тәуелсіз қамту тексерілмеген.",
                    "en":"Only same-residual retrospective calibration exists; independent coverage has not been tested."
                }[lang])

    elif mode_key == "mode2":
        st.markdown("### " + {"kk":"Дақылдың жарамдылығын бағалау","ru":"Оценка пригодности культуры","en":"Crop suitability assessment"}[lang])
        st.caption({
            "kk":"Бұл режим шаруашылық есебін қайталамайды. Негізгі сұрақ - таңдалған дақыл осы аумаққа қаншалықты сәйкес келеді және қандай факторлар оны шектейді?",
            "ru":"Этот режим не повторяет отчет по хозяйству. Главный вопрос - насколько выбранная культура подходит этой территории и какие факторы ее ограничивают?",
            "en":"This mode does not repeat the farm report. It asks how suitable the selected crop is for this location and which factors constrain it."
        }[lang])

        method_name=model_tier_label(crop_method(crop))
        scenario=scenario_for_crop(used_district,crop,climate,irrigation_type)
        ml_pred=None; ml_used=None; hist=None
        if crop in CROPS:
            with st.spinner(t["ml_loading"]):
                ml_pred, ml_used = timed_call("ML prediction", predict_yield, used_district, crop, area_ha, climate)
            _mode2_rf_pred=ml_pred
            _mode2_choice=route_yield(DATA_DIR,used_district,crop,calculation_year,rf_value=ml_pred)
            if _mode2_choice.active_value is not None:
                ml_pred=_mode2_choice.active_value
            if not _mode2_choice.ml_supported:
                st.warning({'ru':'Оценка урожайности: ML не прошёл временную проверку; активный ориентир — историческая медиана района и культуры, не прогноз следующего года.',
                            'kk':'ML уақыттық тексеруден өтпеді. Белсенді көрсеткіш — аудан мен дақылдың тарихи медианасы, болашақ өнім болжамы емес.',
                            'en':'ML did not pass forward validation; the active estimate is a descriptive historical district-crop median, not a next-year forecast.'}[lang])
            report_payload['summary'].append({'label':{'ru':'Random Forest, ц/га (исследовательский ориентир)','kk':'Random Forest, ц/га (зерттеу нәтижесі)','en':'Random Forest, c/ha (research baseline)'}[lang],
                  'value':f'{_mode2_rf_pred:.2f}', 'note':'Forward ML verification 2021–2025; not farm-observed'})
            report_payload['summary'].append({'label':{'ru':'Метод оценки урожайности','kk':'Өнімділікті бағалау әдісі','en':'Yield estimate method'}[lang],
                  'value':method_label(_mode2_choice.active_method,lang),'note':method_caveat(_mode2_choice,lang)})
            hist=district_crop_context(used_district,crop) or {}

        if crop not in CROPS:
            _nonml_yield=route_yield(DATA_DIR,used_district,crop,calculation_year)
            if _nonml_yield.active_value is None:
                st.caption({'ru':'Достоверный численный прогноз урожайности этой культуры недоступен; рейтинг QŪNAR рассчитывается отдельно по климату, водной нагрузке и источникам.',
                            'kk':'Бұл дақылға расталған сандық өнімділік болжамы жоқ; QŪNAR рейтингі климат, су және дерек көздеріне негізделеді.',
                            'en':'No validated numerical yield forecast for this crop. The QŪNAR suitability ranking uses climate, water and evidence separately.'}[lang])
            else:
                st.caption({'ru':f'Историческая медиана по району и культуре: {_nonml_yield.active_value:.1f} ц/га. Это справочный ориентир, а не прогноз следующего сезона.',
                            'kk':f'Аудан мен дақылдың тарихи медианасы: {_nonml_yield.active_value:.1f} ц/га. Бұл болашақ өнім болжамы емес.',
                            'en':f'Historical district-crop median: {_nonml_yield.active_value:.1f} c/ha. Descriptive reference, not a next-season forecast.'}[lang])
            report_payload['inputs'].append([{'ru':'Метод оценки урожайности по культуре','kk':'Дақыл бойынша өнімділікті бағалау әдісі','en':'Crop yield-estimate method'}[lang],method_label(_nonml_yield.active_method,lang),method_caveat(_nonml_yield,lang)])

        # Main verdict is method-aware and never fabricates an ML forecast for non-ML crops.
        if scenario is not None:
            q=float(scenario['QUNAR_score_0_100']); climate_sc=float(scenario['Climate_score_0_100']); resource_sc=float(scenario['Resource_efficiency_0_100']); reliability_sc=float(scenario['Data_reliability_0_100'])
            if q >= 60: verdict={"kk":"жоғары жарамдылық","ru":"высокая пригодность","en":"high suitability"}[lang]
            elif q >= 40: verdict={"kk":"шартты жарамдылық","ru":"условная пригодность","en":"conditional suitability"}[lang]
            else: verdict={"kk":"шектеулері көп","ru":"существенные ограничения","en":"substantial constraints"}[lang]
            if user_level == "farmer":
                a,b=st.columns(2)
                a.metric({"kk":"Жарамдылық бағасы","ru":"Оценка пригодности","en":"Suitability score"}[lang], f"{q:.1f}/100")
                b.metric({"kk":"Қорытынды","ru":"Вывод","en":"Conclusion"}[lang], verdict)
            else:
                a,b,c,d=st.columns(4)
                a.metric({"kk":"QŪNAR бағасы","ru":"Оценка QŪNAR","en":"QŪNAR score"}[lang], f"{q:.1f}/100")
                b.metric({"kk":"Климат","ru":"Климат","en":"Climate"}[lang], f"{climate_sc:.1f}/100")
                c.metric({"kk":"Су жүктемесі","ru":"Водная нагрузка","en":"Water pressure"}[lang], f"{resource_sc:.1f}/100")
                d.metric({"kk":"Бағалау сенімділігі","ru":"Уверенность в оценке","en":"Assessment confidence"}[lang], f"{reliability_sc:.1f}/100")
            st.info({"kk":f"Қорытынды: {extended_crop_label(crop,lang)} - {verdict}.","ru":f"Вывод: {extended_crop_label(crop,lang)} - {verdict}.","en":f"Conclusion: {extended_crop_label(crop,lang)} - {verdict}."}[lang])

            factors=[]
            if float(scenario['official_water_default_m3_ha']) >= 8000: factors.append({"kk":"нормативтік су қажеттілігі жоғары","ru":"высокая нормативная потребность в воде","en":"high normative water requirement"}[lang])
            if float(scenario['Data_reliability_0_100']) < 70: factors.append({"kk":"дерек сенімділігі шектеулі","ru":"ограниченная надежность исходных данных","en":"limited input-data reliability"}[lang])
            if climate_sc < 55: factors.append({"kk":"климаттық сәйкестік шектеулі","ru":"климатическая пригодность ограничена","en":"climate suitability is limited"}[lang])
            if not factors: factors.append({"kk":"айқын критикалық шектеу анықталмады","ru":"явного критического ограничения не выявлено","en":"no single critical constraint is dominant"}[lang])
            st.markdown("#### " + {"kk":"Негізгі факторлар","ru":"Ключевые факторы","en":"Key factors"}[lang])
            for f in factors[:4]: st.write("• "+f)
            if live_ok and baseline_climate:
                cur_t=climate.get("Apr-Sep temperature, °C"); base_t=baseline_climate.get("Apr-Sep temperature, °C")
                cur_p=climate.get("Apr-Sep precipitation, mm"); base_p=baseline_climate.get("Apr-Sep precipitation, mm")
                climate_bits=[]
                if cur_t is not None and base_t is not None:
                    dt=float(cur_t)-float(base_t)
                    climate_bits.append({"kk":f"температура тарихи аудандық профильден {dt:+.1f}°C ауытқыды","ru":f"температура отклоняется от исторического районного профиля на {dt:+.1f}°C","en":f"temperature differs from the historical district profile by {dt:+.1f}°C"}[lang])
                if cur_p is not None and base_p is not None and float(base_p)>0:
                    dp=(float(cur_p)-float(base_p))/float(base_p)*100
                    climate_bits.append({"kk":f"жауын-шашын {dp:+.0f}%","ru":f"осадки {dp:+.0f}%","en":f"precipitation {dp:+.0f}%"}[lang])
                if climate_bits:
                    st.write("• "+{"kk":"Ағымдағы климат: ","ru":"Текущий климат: ","en":"Current climate: "}[lang]+"; ".join(climate_bits)+".")
            if user_level != "farmer":
                st.caption({
                    "kk":f"Су нормасы: {float(scenario['official_water_default_m3_ha']):,.0f} {UNITS['m3']}/га. Дерек сенімділігі: {float(scenario['Data_reliability_0_100']):.1f}/100.",
                    "ru":f"Норматив воды: {float(scenario['official_water_default_m3_ha']):,.0f} {UNITS['m3']}/га. Надежность данных: {float(scenario['Data_reliability_0_100']):.1f}/100.",
                    "en":f"Water norm: {float(scenario['official_water_default_m3_ha']):,.0f} m³/ha. Data reliability: {float(scenario['Data_reliability_0_100']):.1f}/100."
                }[lang])
        else:
            # No fabricated CLREM score: show the strongest evidence actually available.
            if ml_pred is not None:
                if user_level == "farmer":
                    st.info({
                        "kk":"Бұл дақылдың бағасы өнімділік тарихы мен ағымдағы климатқа негізделеді. Толық көпкритерийлі профиль әзірге қолжетімсіз.",
                        "ru":"Оценка этой культуры основана на истории урожайности и текущем климате. Полный многокритериальный профиль пока недоступен.",
                        "en":"This crop assessment uses yield history and current climate. A full multi-criteria profile is not yet available."
                    }[lang])
                else:
                    st.info({
                        "kk":"Бұл дақыл үшін аудандық көпкритерийлі профиль жоқ. Сондықтан бағалау машиналық оқыту арқылы алынған өнімділік қатары мен климаттық деректерге негізделеді.",
                        "ru":"Для этой культуры нет районного многокритериального профиля. Исторический ориентир и климатическая пригодность показываются отдельно.",
                        "en":"No district multi-criteria profile is available for this crop yet. The assessment therefore uses the ML yield series and climate evidence."
                    }[lang])
            elif not observed_for_crop(used_district,crop).empty:
                st.info({
                    "kk":"Толық аудандық сценарий жоқ, бірақ 2023 жылғы тікелей байқалған нарықтық дерек бар. Ол төменде жеке дәлел ретінде көрсетіледі.",
                    "ru":"Полного районного сценария пока нет, но есть непосредственно наблюдаемое рыночное свидетельство за 2023 год. Оно показано ниже отдельно.",
                    "en":"A full district scenario is not yet available, but directly observed 2023 market evidence exists and is shown separately below."
                }[lang])
            else:
                st.warning({
                    "kk":"Бұл дақыл бойынша сенімді аудандық қорытынды жасауға әзірге дерек жеткіліксіз.",
                    "ru":"По этой культуре пока недостаточно данных для надежного районного вывода.",
                    "en":"There is not yet enough evidence for a reliable district-level conclusion for this crop."
                }[lang])

        if ml_pred is not None:
            if user_level == "researcher":
                st.markdown("#### " + {"kk":"Машиналық оқыту бойынша өнімділік бағасы","ru":"Оценка урожайности и выбор метода","en":"ML yield evidence"}[lang])
            else:
                st.markdown("#### " + {"kk":"Күтілетін өнімділік","ru":"Ожидаемая урожайность","en":"Expected yield"}[lang])
            med=hist.get('historical_yield_median') if hist else None
            if med:
                delta=(ml_pred-float(med))/float(med)*100
                if user_level == "researcher":
                    st.write({"kk":f"Аудан-дақыл бойынша машиналық оқыту базалық болжамы: {ml_pred:.1f} ц/га; тарихи медианаға қатысты {delta:+.1f}%.","ru":f"Расчётный ориентир урожайности: {ml_pred:.1f} ц/га; относительно исторической медианы {delta:+.1f}%. Метод: {method_label(_mode2_choice.active_method,lang)}.","en":f"District-crop ML baseline: {ml_pred:.1f} c/ha; {delta:+.1f}% versus historical median."}[lang])
                else:
                    st.write({"kk":f"Күтілетін деңгей: {ml_pred:.1f} ц/га, тарихи аудандық медианадан {delta:+.1f}%.","ru":f"Ожидаемый уровень: {ml_pred:.1f} ц/га, отклонение от исторической районной медианы {delta:+.1f}%.","en":f"Expected level: {ml_pred:.1f} c/ha, {delta:+.1f}% versus the historical district median."}[lang])
            else:
                st.write({"kk":f"Аудан-дақыл бойынша машиналық оқыту базалық болжамы: {ml_pred:.1f} ц/га.","ru":f"Расчётный ориентир урожайности: {ml_pred:.1f} ц/га. Метод: {method_label(_mode2_choice.active_method,lang)}.","en":f"District-crop ML baseline: {ml_pred:.1f} c/ha."}[lang])
        elif crop == 'Barley':
            st.warning({"kk":"Арпа үшін машиналық оқыту арқылы өнімділікті болжау әдейі қосылмады: берілген бастапқы панельде арпа өнімділігі бидай қатарын қайталайды және дереккөзді қайта тексеру қажет.","ru":"Модель машинного обучения для прогнозирования урожайности ячменя намеренно не включена: в предоставленной исходной панели ряд урожайности ячменя дублирует пшеницу и требует проверки источника.","en":"Barley yield ML is intentionally disabled: the supplied source panel duplicates the wheat yield series and needs source verification."}[lang])

        obs_ev=observed_for_crop(used_district,crop)
        if not obs_ev.empty:
            st.markdown("#### " + {"kk":"2023 жылғы байқалған нарықтық дәлел","ru":"Наблюдаемое рыночное свидетельство 2023","en":"Observed 2023 market evidence"}[lang])
            r=obs_ev.iloc[0]
            st.write({"kk":f"Ауыл шаруашылығы кооперативтері бойынша іске асыру: {r['volume_t']:,.1f} т; құны {r['value_thousand_kzt']:,.0f} мың тг. Бұл дерек QŪNAR рейтингіне тікелей кірмейді.","ru":f"По сельхозкооперативам: реализация {r['volume_t']:,.1f} т; стоимость {r['value_thousand_kzt']:,.0f} тыс. тг. Эти данные показаны как контекст и напрямую не входят в рейтинг QŪNAR.","en":f"Agricultural cooperatives: {r['volume_t']:,.1f} t realized; value {r['value_thousand_kzt']:,.0f} thousand {UNITS['currency']}. This evidence is contextual and does not directly enter the QŪNAR ranking."}[lang])

        if user_level == "researcher":
            with st.expander({"kk":"Әдістеме және дереккөздер","ru":"Методика и источники","en":"Method and sources"}[lang]):
                st.write({
                  "kk":f"Модель деңгейі: {method_name}. Аудан: {district_label(used_district)}. Есеп координатасы: {calc_lat:.6f}, {calc_lon:.6f}. QŪNAR құрамдастары: климат, ресми/әдепкі су қажеттілігі және дерек сенімділігі.",
                  "ru":f"Уровень модели: {method_name}. Район: {district_label(used_district)}. Координаты расчета: {calc_lat:.6f}, {calc_lon:.6f}. Компоненты QŪNAR: климат, официальный/расчетный норматив воды и надежность данных.",
                  "en":f"Model tier: {method_name}. District: {district_label(used_district)}. Calculation coordinates: {calc_lat:.6f}, {calc_lon:.6f}. QŪNAR components: climate, official/default water requirement and evidence reliability."
                }[lang])

    elif mode_key == "mode3":
        ranking = timed_call("QUNAR ranking", decision_table, used_district, lang, climate, irrigation_type).copy()
        ranking = ranking.rename(columns={
            'District_rank': {'kk':'Орын','ru':'Место','en':'Rank'}[lang],
            'display': {'kk':'Дақыл','ru':'Культура','en':'Crop'}[lang],
            'QUNAR_score_0_100': {'kk':'QŪNAR жалпы бағасы','ru':'Общий балл QŪNAR','en':'QŪNAR overall score'}[lang],
            'Climate_score_0_100': {'kk':'Климат','ru':'Климат','en':'Climate'}[lang],
            'Water_pressure_score_0_100': {'kk':'Су жүктемесі','ru':'Водная нагрузка','en':'Water pressure'}[lang],
            'Confidence_0_100': {'kk':'Бағалау сенімділігі','ru':'Уверенность в оценке','en':'Assessment confidence'}[lang],
            'official_water_default_m3_ha': {'kk':'Әдепкі су нормасы, м³/га','ru':'Норма воды по умолчанию, м³/га','en':'Default water norm, m³/ha'}[lang],
            'water_default_source': {'kk':'Су нормасының дереккөзі','ru':'Источник нормы воды','en':'Water-norm source'}[lang],
        })
        keep=list(ranking.columns[:7])
        # Human-readable precision: decision-support values are scenarios/proxies, not accounting outputs.
        score_cols=[{'kk':'QŪNAR жалпы бағасы','ru':'Общий балл QŪNAR','en':'QŪNAR overall score'}[lang], {'kk':'Климат','ru':'Климат','en':'Climate'}[lang], {'kk':'Су жүктемесі','ru':'Водная нагрузка','en':'Water pressure'}[lang], {'kk':'Бағалау сенімділігі','ru':'Уверенность в оценке','en':'Assessment confidence'}[lang]]
        for col in score_cols:
            ranking[col]=pd.to_numeric(ranking[col],errors='coerce').round(1)
        wcol={'kk':'Әдепкі су нормасы, м³/га','ru':'Норма воды по умолчанию, м³/га','en':'Default water norm, m³/ha'}[lang]
        ranking[wcol]=pd.to_numeric(ranking[wcol],errors='coerce').round(0).astype('Int64')
        st.markdown("### " + {'kk':'QŪNAR көпкритерийлі рейтингі','ru':'Многокритериальный рейтинг QŪNAR','en':'QŪNAR multi-criteria ranking'}[lang])
        if user_level == "farmer":
            basic_cols=[{'kk':'Орын','ru':'Место','en':'Rank'}[lang],{'kk':'Дақыл','ru':'Культура','en':'Crop'}[lang],{'kk':'QŪNAR жалпы бағасы','ru':'Общий балл QŪNAR','en':'QŪNAR overall score'}[lang],{'kk':'Климат','ru':'Климат','en':'Climate'}[lang],{'kk':'Су жүктемесі','ru':'Водная нагрузка','en':'Water pressure'}[lang]]
            st.dataframe(ranking[basic_cols],use_container_width=True,hide_index=True)
        else:
            st.dataframe(ranking[keep], use_container_width=True, hide_index=True, column_config={wcol: st.column_config.NumberColumn(format="%d")})
        st.caption({
            'kk':'Рейтинг нарықтық бағаның жанама көрсеткішін пайдаланбайды. QŪNAR бағасы климатты, аудан-дақыл бойынша ресми немесе әдепкі су нормасын және дерек сенімділігін біріктіреді.',
            'ru':'Рейтинг больше не использует косвенный рыночный показатель цены. Балл QŪNAR объединяет климат, официальный или расчетный норматив воды для пары район-культура и надежность исходных данных.',
            'en':'The ranking no longer uses the market-price proxy. QŪNAR combines climate, the official/default district-crop water norm and input-data reliability.'
        }[lang])
        top=ranking.iloc[0]
        crop_col={'kk':'Дақыл','ru':'Культура','en':'Crop'}[lang]
        score_col={'kk':'QŪNAR жалпы бағасы','ru':'Общий балл QŪNAR','en':'QŪNAR overall score'}[lang]
        top_msg={
            'kk':f"<strong>Негізгі ұсыныс:</strong> {top[crop_col]} - <strong>{float(top[score_col]):.1f}/100</strong>.",
            'ru':f"<strong>Ключевая рекомендация:</strong> {top[crop_col]} - <strong>{float(top[score_col]):.1f}/100</strong>.",
            'en':f"<strong>Key recommendation:</strong> {top[crop_col]} - <strong>{float(top[score_col]):.1f}/100</strong>."
        }[lang]
        st.markdown(f'<div class="qunar-key">{top_msg}</div>', unsafe_allow_html=True)

        if user_level == "researcher":
            with st.expander({'ru':'Доступность методов прогноза для всех культур','kk':'Барлық дақылдар бойынша болжам әдістері','en':'Forecast-method coverage for all crops'}[lang]):
                _registry=clrem_registry()
                _method_rows=[]
                for _entry in _registry.itertuples(index=False):
                    if pd.isna(_entry.CLREM_product): continue
                    _status=route_yield(DATA_DIR,used_district,_entry.Code,calculation_year)
                    _method_rows.append({
                        {'ru':'Культура','kk':'Дақыл','en':'Crop'}[lang]:extended_crop_label(_entry.Code,lang),
                        {'ru':'Статус методов','kk':'Әдістер мәртебесі','en':'Methods status'}[lang]:
                            ({'ru':'ML + историческая альтернатива','kk':'ML және тарихи балама','en':'ML with historical alternative'}[lang]
                             if _entry.Code in CROPS else {'ru':'Исторические данные / без проверенного ML','kk':'Тарихи деректер / тексерілген ML жоқ','en':'Historical data / no verified ML'}[lang]),
                        {'ru':'Наблюдений в районе','kk':'Аудандағы бақылаулар','en':'District observations'}[lang]:_status.reference_n})
                report_payload["research_tables"].append({"title": {"ru":"Доступность методов прогноза","kk":"Болжау әдістерінің қолжетімділігі","en":"Forecast-method coverage"}[lang], "rows": pd.DataFrame(_method_rows).to_dict(orient="records")})
                st.dataframe(pd.DataFrame(_method_rows),use_container_width=True,hide_index=True)
                st.caption({'ru':'Отсутствующие урожайности не подменяются рейтингом QŪNAR. Рейтинг пригодности и прогноз урожайности — разные показатели.',
                            'kk':'Жоқ өнімділік QŪNAR рейтингімен алмастырылмайды. Жарамдылық пен өнімділік болжамы бөлек.',
                            'en':'Missing yield observations are not substituted with QŪNAR suitability scores.'}[lang])
        if user_level == "researcher":
            with st.expander({'kk':'Машиналық оқыту бойынша өнімділік бағасы - 6 калибрленген егістік дақыл','ru':'Оценка урожайности машинным обучением - 6 откалиброванных полевых культур','en':'ML yield evidence - 6 calibrated field crops'}[lang]):
                with st.spinner(t['ml_loading']):
                    mlrank=timed_call("ML crop ranking", rank_crops, used_district, area_ha, climate, CROPS).copy()
                mlrank['Crop']=mlrank['Crop'].map(CROP_LABELS[lang])
                mlrank=mlrank.rename(columns={'Crop':t['ranking_crop'],'Predicted yield, centners/ha':t['ranking_yield']})
                report_payload["research_tables"].append({"title": {"ru":"Оценки урожайности ML","kk":"ML өнімділік бағалары","en":"ML yield evidence"}[lang], "rows": mlrank.to_dict(orient="records")})
                st.dataframe(mlrank,use_container_width=True,hide_index=True)
                st.caption({'kk':'Бұл кесте машиналық оқыту арқылы алынған өнімділік бағаларын ғана көрсетеді. Әртүрлі дақылдардың ц/га мәндерін тікелей «ең жақсы дақыл» рейтингі ретінде түсіндіруге болмайды.', 'ru':'Таблица показывает только оценки урожайности, полученные машинным обучением. Значения ц/га разных культур нельзя напрямую трактовать как рейтинг «лучшей культуры».','en':'This is ML yield evidence only. Yield values across different crops must not be interpreted directly as a best-crop ranking.'}[lang])

        extra=observed_extra_for_district(used_district)
        if user_level != "farmer" and not extra.empty:
            with st.expander({'kk':'Қосымша байқалған 2023 дәлелдері','ru':'Дополнительные наблюдаемые данные 2023','en':'Additional observed 2023 evidence'}[lang]):
                show=extra[['product','volume_t','value_thousand_kzt','recommendation_type']].copy()
                show['recommendation_type'] = show['recommendation_type'].map(recommendation_type_label)
                show=show.rename(columns={
                    'product': {'kk':'Өнім','ru':'Продукт','en':'Product'}[lang],
                    'volume_t': {'kk':'Көлемі, т','ru':'Объем, т','en':'Volume, t'}[lang],
                    'value_thousand_kzt': {'kk':'Құны, мың тг','ru':'Стоимость, тыс. тг','en':'Value, thousand KZT'}[lang],
                    'recommendation_type': {'kk':'Бағалау санаты','ru':'Категория оценки','en':'Assessment category'}[lang],
                })
                report_payload["research_tables"].append({"title": {"ru":"Дополнительные наблюдаемые данные 2023","kk":"Қосымша 2023 бақыланған деректер","en":"Additional observed 2023 evidence"}[lang], "rows": show.to_dict(orient="records")})
                st.dataframe(show,use_container_width=True,hide_index=True)

        if user_level == "researcher":
            st.warning({'kk':'Арпа машиналық оқыту арқылы өнімділік рейтингіне әдейі кірмейді: берілген аудан-жыл өнімділік қатары бидайды толық қайталайды. Арпа QŪNAR шешім рейтингінде климат, су нормасы және дерек сенімділігі арқылы бағаланады; машиналық оқыту қолданылмайды.', 'ru':'Ячмень намеренно не включен в рейтинг урожайности, полученный машинным обучением: предоставленный районно-годовой ряд урожайности полностью дублирует пшеницу. В рейтинге QŪNAR ячмень пока оценивается по климату, водному нормативу и надежности данных; машинное обучение для него не используется.','en':'Barley is intentionally excluded from yield ML because its supplied district-year yield series duplicates wheat. It remains in the QŪNAR decision ranking based on climate, water-norm and evidence-reliability layers; yield ML is not used.'}[lang])
    else:
        st.markdown("### " + {"kk":"Шаруашылық құрылымын оңтайландыру","ru":"Оптимизация структуры хозяйства","en":"Farm-structure optimization"}[lang])
        st.caption({
            "kk":"QŪNAR климаттық тұрақтылықты, су тиімділігін және дерек сенімділігін теңестіреді. Қолжетімді су енгізілсе, ол оңтайландырудың нақты шектеуі болады.",
            "ru":"QŪNAR распределяет площадь по ресурсно-климатической полезности. Уверенность в оценке показывается отдельно и не повышает привлекательность культуры. Если указана доступная вода, она становится жестким ограничением оптимизации.",
            "en":"QŪNAR allocates land using resource-climate utility. Assessment confidence is reported separately and does not make a crop more attractive. Entered available water becomes a hard optimization constraint."
        }[lang])
        # Compatibility-safe optimizer call. Some deployed QŪNAR v0.8.1 environments may
        # still contain the earlier optimizer signature without the optional economic arguments.
        # We inspect the callable instead of catching an arbitrary TypeError from inside the solver.
        _opt_params = inspect.signature(optimize_structure).parameters
        if climate_future_apply_opt and climate_future_scenario != 'none':
            try:
                _opt_cm = load_scenario(DATA_DIR / 'cmip6', climate_future_scenario).as_dict()
                optimization_temp_delta_c = float(_opt_cm['temperature_change_c'])
                optimization_precip_change_pct = float(_opt_cm['precipitation_change_pct'])
                st.warning({'ru':'Климатический стресс основан на CMIP6, но это экстраполяция климатического блока, а не валидированный прогноз урожайности до 2059 года.',
                            'kk':'Климаттық стресс CMIP6-ға негізделген, бірақ бұл климат блогының экстраполяциясы, 2059 жылға дейінгі тексерілген өнімділік болжамы емес.',
                            'en':'CMIP6 climate stress is exploratory extrapolation, not a validated yield forecast to 2059.'}[lang])
            except (ValueError,OSError,KeyError) as _ec:
                st.warning(str(_ec) + ' | CMIP6 climate inputs not applied')
        if climate_future_apply_opt and climate_future_scenario != 'none':
            report_payload['inputs'].append([
                {'kk':'Оңтайландыруда қолданылған CMIP6','ru':'CMIP6, применённый в оптимизации','en':'CMIP6 applied to optimization'}[lang],
                f"{climate_future_scenario}, ΔT={optimization_temp_delta_c:+.3f} °C, ΔP={optimization_precip_change_pct:+.3f}%",
                {'kk':'Тек климаттық баллға сценарийлік әсер; су лимиті өзгермеді',
                 'ru':'Сценарийное изменение климатического балла; лимит воды не изменён',
                 'en':'Climate-score sensitivity only; water limit unchanged'}[lang]])
        _scenario_climate = dict(climate or {})
        if optimization_temp_delta_c:
            _k="Apr-Sep temperature, °C"
            if _k in _scenario_climate and _scenario_climate.get(_k) is not None:
                _scenario_climate[_k]=float(_scenario_climate[_k])+float(optimization_temp_delta_c)
        if optimization_precip_change_pct:
            _k="Apr-Sep precipitation, mm"
            if _k in _scenario_climate and _scenario_climate.get(_k) is not None:
                _scenario_climate[_k]=max(0.0,float(_scenario_climate[_k])*(1.0+float(optimization_precip_change_pct)/100.0))
        _scenario_available_water=float(available_water or 0.0)
        if _scenario_available_water>0 and optimization_water_budget_change_pct:
            _scenario_available_water=max(0.0,_scenario_available_water*(1.0+float(optimization_water_budget_change_pct)/100.0))
        _opt_kwargs = {
            "district": used_district,
            "area_ha": area_ha,
            "profile": optimization_profile,
            "max_share": optimization_max_share,
            "n_crops": optimization_n_crops,
            "available_water_m3": _scenario_available_water,
            "climate": _scenario_climate,
            "irrigation_type": irrigation_type,
        }
        if "economic_margin_by_product" in _opt_params:
            _opt_kwargs["economic_margin_by_product"] = (
                optimization_economic_margins if optimization_use_economics else None
            )
        if "economic_weight" in _opt_params:
            _opt_kwargs["economic_weight"] = optimization_economic_weight
        if "objective_mode" in _opt_params:
            _opt_kwargs["objective_mode"] = optimization_objective_mode
        if "baseline_share_by_product" in _opt_params:
            _opt_kwargs["baseline_share_by_product"] = optimization_baseline_shares
        if optimization_objective_mode == 'sustainable':
            if not (optimization_ghg_confirmed and optimization_ghg_evidence.strip()):
                st.error({'ru':'Для устойчивого компромисса подтвердите источник и единую методику расчёта CO₂e.',
                    'kk':'Тұрақты ымыра үшін CO₂e есептеу көзін және әдісін растаңыз.',
                    'en':'Confirm the GHG data source and consistent emission-accounting method.'}[lang])
                st.stop()
            _opt_kwargs.update({
                'ghg_kg_co2e_by_product':optimization_ghg_by_product,
                'sustainable_max_margin_decline_pct':optimization_margin_decline_pct,
                'sustainable_absolute_ghg_cap_kg':optimization_absolute_ghg_cap_kg,
            })
            report_payload['inputs'].append([
                {'ru':'Ограничения устойчивого компромисса','kk':'Тұрақты ымыра шектеулері','en':'Sustainable compromise constraints'}[lang],
                f'Water <= baseline; partial CO2e <= baseline and absolute cap {optimization_absolute_ghg_cap_kg} if entered; margin >= baseline less {optimization_margin_decline_pct:.1f}%; per-crop emissions kg CO2e/ha: {optimization_ghg_by_product}; source: {optimization_ghg_evidence}',
                'User-supplied per-crop margins and PARTIAL emissions, same crop period/boundary. Not observed impact.'])
        if "custom_climate_weight" in _opt_params and optimization_profile == "custom":
            _opt_kwargs["custom_climate_weight"] = optimization_custom_climate_weight
        if structure_water_enabled and structure_water_use_hard_constraint:
            if not (structure_water_confirmed and structure_water_provenance.strip()):
                st.error({'ru':'Для сценарного водного лимита подтвердите данные и укажите источник.',
                    'kk':'Су шектеуі үшін дереккөз бен растау қажет.',
                    'en':'Confirm the input data and evidence before using a scenario water budget.'}[lang])
                st.stop()
            elif _scenario_available_water <= 0:
                st.error({'ru':'Для жёсткого сценарного ограничения сначала введите доступный объём воды.',
                    'kk':'Қатаң шектеу үшін су көлемін енгізіңіз.',
                    'en':'Enter an available-water budget before activating a hard constraint.'}[lang])
                st.stop()
            elif not structure_water_data:
                st.error({'ru':'Нет заполненных культур для водного сценария.',
                    'kk':'Дақылдардың су қажеттілігі енгізілмеген.',
                    'en':'No crops have entered net irrigation demand.'}[lang])
                st.stop()
            else:
                _sw_override={k: d['net']/d['eta_after']/(structure_water_conveyance if structure_water_optimizer_basis=='source_withdrawal' else 1.)
                    for k,d in structure_water_data.items()}
                _opt_kwargs.update({
                    'water_requirement_by_product':_sw_override,
                    'water_constraint_definition':structure_water_optimizer_basis,
                    'water_requirement_evidence':structure_water_provenance,
                    'water_requirement_confirmed':True})
                report_payload['inputs'].append(['Optimizer water-accounting boundary',
                    f'{structure_water_optimizer_basis}; user-defined root-zone need / field efficiency / optional conveyance; '
                    f'crop-specific m3/ha={_sw_override}',structure_water_provenance])
        alloc, opt = timed_call("Optimization", optimize_structure, **_opt_kwargs)
        if opt.get('water_accounting_basis') not in (None, 'official_reference'):
            _cross_module_summary_rows.append({
                'label':{'ru':'Граница сценарного водного ограничения',
                         'kk':'Сценарийлік су шектеуінің шекарасы',
                         'en':'Scenario water-constraint accounting boundary'}[lang],
                'value':str(opt['water_accounting_basis']),
                'note':structure_water_provenance+'; USER SCENARIO, not official statutory irrigation norm'})
        # Final independent guard: reject a legacy/stale solver result if it breaches
        # any hard constraint. Prevents an infeasible allocation reaching UI or exports.
        _allocation_check = validate_allocation(
            alloc, opt, area_ha=area_ha,
            available_water_m3=_scenario_available_water,
            max_share=optimization_max_share, n_crops=optimization_n_crops,
        )
        if not _allocation_check['ok']:
            opt = dict(opt or {})
            opt['water_feasible'] = False
            opt['solver_status'] = str(opt.get('solver_status') or 'infeasible_under_hard_constraints')
            opt['rejection_reasons'] = _allocation_check['reasons']
            opt['rejected_water_m3'] = _allocation_check['modelled_water_m3']
            opt['water_deficit_m3'] = _allocation_check['water_deficit_m3']
            opt['available_water_m3'] = float(_scenario_available_water)
            # Never present an infeasible numerical optimum or claimed financial gain.
            for _invalid_key in (
                'optimized_contribution_margin_kzt', 'economic_gain_kzt',
                'economic_gain_pct', 'optimized_margin_per_m3_kzt',
                'weighted_economic_margin_kzt_ha'
            ):
                opt[_invalid_key] = None
            alloc = alloc.iloc[0:0].copy()
        # Feasible at the declared limit can still mean zero buffer for dry years.
        if (not alloc.empty and _scenario_available_water > 0
                and _allocation_check.get('modelled_water_m3') is not None):
            _w_used=float(_allocation_check['modelled_water_m3'])
            _buffer_ratio=(_scenario_available_water-_w_used)/_scenario_available_water
            if -1e-8 <= _buffer_ratio <= 0.01:
                _water_buffer_msg={
                    'ru':f'РЕЗЕРВ ВОДЫ ≤1%: модель использует {_w_used:,.0f} из {_scenario_available_water:,.0f} м³. План математически допустим при данном лимите, но не защищён от сокращения подачи в засушливый сезон. Повторите оптимизацию с бюджетом −10% и −20%, сравните допустимость, маржу и выбросы.',
                    'kk':f'СУ ҚОРЫ ≤1%: {_w_used:,.0f} / {_scenario_available_water:,.0f} м³. Бұл жоспар берілген шектеуде ғана мүмкін; су −10% және −20% жағдайларын тексеріңіз.',
                    'en':f'WATER BUFFER ≤1%: {_w_used:,.0f} of {_scenario_available_water:,.0f} m³ used. Feasible at current budget, but not robust to reduced supply. Re-run at −10% and −20% water budgets.'}[lang]
                st.warning(_water_buffer_msg)
                _cross_module_summary_rows.append({
                    'label':{'ru':'Проверка устойчивости: резерв воды','kk':'Тұрақтылық: су қоры','en':'Robustness: water budget buffer'}[lang],
                    'value':f'{max(0.0,100*_buffer_ratio):.2f}%',
                    'note':_water_buffer_msg})
        if alloc.empty and optimization_objective_mode == 'sustainable':
            st.warning({
                'ru':'При заданных данных математически допустимый устойчивый компромисс не найден либо недостаёт исходных показателей. Не ослабляйте ограничения незаметно; проверьте полноту маржи, CO₂e, исходных долей и числа культур.',
                'kk':'Берілген деректер бойынша тұрақты ымыра табылмады немесе кіріс деректері жеткіліксіз. Шектеулер жасырын түрде өзгертілмейді.',
                'en':'No feasible sustainable compromise under the supplied inputs, or data are incomplete. The constraints will not be relaxed silently.'
            }[lang])
        if alloc.empty:
            st.error({"kk":"Берілген су, дақыл саны және үлес шектеулері бойынша іске асатын жоспар табылмады. Су лимитін немесе параметрлерді тексеріңіз.","ru":"Допустимый план не найден. Проверьте водный лимит, число культур и максимальную долю. Маржа и эффект оптимизации не рассчитаны.","en":"No feasible plan under the water budget, crop count and share cap. No optimized margin or gain is reported."}[lang])
            if opt.get('solver_status') == 'infeasible_crop_count_or_cap':
                _eligible = int(opt.get('eligible_crop_count', 0))
                if _eligible < optimization_n_crops and opt.get('economic_objective_active'):
                    st.warning({
                        'ru':f'Экономические показатели введены только для {_eligible} культур при запрошенных {optimization_n_crops}. Заполните маржу ещё для {optimization_n_crops-_eligible} культур или уменьшите их число.',
                        'kk':f'Экономикалық деректер {_eligible} дақыл үшін ғана енгізілген, ал {optimization_n_crops} қажет. Маржа деректерін толықтырыңыз немесе дақыл санын азайтыңыз.',
                        'en':f'Margins are available for {_eligible} crops, but {optimization_n_crops} were requested. Supply the missing margins or reduce the number of crops.'
                    }[lang])
                elif optimization_max_share*optimization_n_crops < 1-1e-9:
                    st.warning({
                        'ru':'Количество культур и максимальная доля несовместимы: сумма допустимых долей меньше 100%.',
                        'kk':'Дақыл саны мен үлес шегі сәйкес емес: мүмкін болатын үлестер қосындысы 100%-ға жетпейді.',
                        'en':'Crop count and maximum share are incompatible: capped shares cannot sum to 100%.'
                    }[lang])
            if opt:
                st.caption({
                    'kk': f"Шешім күйі: {localized_solver_status(opt.get('solver_status', 'unknown'), lang)}; бір дақыл үшін теориялық ең аз су: {opt.get('minimum_uniform_water_m3', '—')} {UNITS['m3']}",
                    'ru': f"Статус решения: {localized_solver_status(opt.get('solver_status', 'unknown'), lang)}; минимальный теоретический объем воды для одной культуры: {opt.get('minimum_uniform_water_m3', '—')} {UNITS['m3']}",
                    'en': f"Solver: {localized_solver_status(opt.get('solver_status', 'unknown'), lang)}; minimum theoretical water for a single crop: {opt.get('minimum_uniform_water_m3', '—')} m³",
                }[lang])
        else:
            name_col={"kk":"KK","ru":"RU","en":"EN"}[lang]
            _water_table_column = 'constraint_water_m3_ha' if opt.get('water_accounting_basis') != 'official_reference' else 'official_water_default_m3_ha'
            out=alloc[[name_col,"share","area_ha","QUNAR_score_0_100","Climate_score_0_100","Resource_efficiency_0_100","Data_reliability_0_100",_water_table_column,"modelled_water_m3"]].copy()
            out.columns=[
                {"kk":"Дақыл","ru":"Культура","en":"Crop"}[lang],
                {"kk":"Үлес, %","ru":"Доля, %","en":"Share, %"}[lang],
                {"kk":"Аудан, га","ru":"Площадь, га","en":"Area, ha"}[lang],
                {"kk":"QŪNAR бағасы","ru":"Оценка QŪNAR","en":"QŪNAR score"}[lang],
                {"kk":"Климат","ru":"Климат","en":"Climate"}[lang],
                {"kk":"Су жүктемесі","ru":"Водная нагрузка","en":"Water pressure"}[lang],
                {"kk":"Бағалау сенімділігі","ru":"Уверенность в оценке","en":"Assessment confidence"}[lang],
                {"kk":"Су нормасы, м³/га","ru":"Норма воды, м³/га","en":"Water norm, m³/ha"}[lang],
                {"kk":"Есептік су, м³","ru":"Расчетная вода, м³","en":"Modelled water, m³"}[lang],
            ]
            out.iloc[:,1]=(out.iloc[:,1]*100).round(1)
            out.iloc[:,2]=out.iloc[:,2].round(2)
            for j in range(3,7): out.iloc[:,j]=pd.to_numeric(out.iloc[:,j],errors='coerce').round(1)
            out.iloc[:,7]=pd.to_numeric(out.iloc[:,7],errors='coerce').round(0)
            out.iloc[:,8]=pd.to_numeric(out.iloc[:,8],errors='coerce').round(0)
            if optimization_profile in ('survey_proxy', 'custom') and 'profile_score_0_100' in alloc.columns:
                _profile_col = {'kk':'Сценарий балы','ru':'Бал выбранного сценария','en':'Selected profile score'}[lang]
                out[_profile_col] = pd.to_numeric(alloc['profile_score_0_100'],errors='coerce').round(1).to_numpy()
            if opt.get('water_accounting_basis') != 'official_reference':
                out.rename(columns={out.columns[7]:{'ru':'Сценарная потребность, м³/га','kk':'Сценарийлік қажеттілік, м³/га','en':'Scenario water, m³/ha'}[lang]},inplace=True)
                st.caption({'ru':f"Жёсткое ограничение применено к {opt['water_accounting_basis']}; заданные пользователем сценарные значения, не государственные нормы. Источник: {structure_water_provenance}",
                            'kk':f"Су шектеуінің негізі: {opt['water_accounting_basis']}; бұл мемлекеттік норматив емес.",
                            'en':f"Hard water boundary: {opt['water_accounting_basis']}; user-supplied scenario, not a statutory norm. Source: {structure_water_provenance}"}[lang])
            st.dataframe(out,use_container_width=True,hide_index=True)
            if structure_water_enabled:
                with st.expander({'ru':'Вода: исходная структура и оптимизированный план',
                    'kk':'Су: бастапқы және оңтайландырылған егіс құрылымы',
                    'en':'Water: baseline vs optimized crop structure'}[lang],expanded=False):
                    if not (structure_water_confirmed and structure_water_provenance.strip()):
                        st.warning({'ru':'Введите источник и подтвердите данные, чтобы сравнить структуры.',
                          'kk':'Құрылымды салыстыру үшін дереккөзді растап енгізіңіз.',
                          'en':'Confirm water data and source before comparing structures.'}[lang])
                    else:
                        _water_b={str(k):float(v)*float(area_ha)/100.0 for k,v in optimization_baseline_shares.items()}
                        _water_a={str(r['product']):float(r['area_ha']) for _,r in alloc.iterrows()}
                        try:
                            _wres=compare_structure_water(
                                baseline_areas=_water_b,proposed_areas=_water_a,
                                net_irrigation_m3_ha={k:v['net'] for k,v in structure_water_data.items()},
                                baseline_field_efficiency_by_crop={k:v['eta_before'] for k,v in structure_water_data.items()},
                                proposed_field_efficiency_by_crop={k:v['eta_after'] for k,v in structure_water_data.items()},
                                conveyance_efficiency=structure_water_conveyance,
                                baseline_recoverable_by_crop=structure_water_baseline_returns,
                                proposed_recoverable_by_crop=structure_water_proposed_returns,
                                baseline_conveyance_recovery=structure_water_baseline_conveyance_return,
                                proposed_conveyance_recovery=structure_water_proposed_conveyance_return,
                                evidence=structure_water_provenance,confirmed=True)
                            _wb,_wp,_wd=_wres['baseline'],_wres['proposed'],_wres['difference']
                            _wm1,_wm2,_wm3=st.columns(3)
                            _wm1.metric({'ru':'Подача на поле: до, м³','kk':'Алқапқа су беру: дейін, м³','en':'Field delivery before, m³'}[lang],f"{_wb['field_delivery_m3']:,.0f}")
                            _wm2.metric({'ru':'Подача на поле: после, м³','kk':'Алқапқа су беру: кейін, м³','en':'Field delivery after, m³'}[lang],f"{_wp['field_delivery_m3']:,.0f}")
                            _wm3.metric({'ru':'Сокращение подачи, м³','kk':'Су беру азаюы, м³','en':'Field delivery reduction, m³'}[lang],f"{_wd['field_delivery_m3_reduction']:+,.0f}")
                            _cross_module_summary_rows.append({'label':'Farm crop-mix field water delivery change, m3',
                                'value':f"{_wd['field_delivery_m3_reduction']:+.2f}",
                                'note':'Counterfactual field delivery, not observed basin water savings; '+structure_water_provenance})
                            for _wkey,_wtitle in [('source_withdrawal_m3_reduction','Source withdrawal reduction'),
                                                   ('irrigation_depletion_proxy_m3_reduction','Irrigation-attributable depletion proxy reduction')]:
                                if _wd[_wkey] is not None:
                                    st.metric(_wtitle+' (m³)',f"{_wd[_wkey]:+,.0f}")
                                    _cross_module_summary_rows.append({'label':'Farm crop-mix '+_wtitle+', m3',
                                        'value':f"{_wd[_wkey]:+.2f}",'note':_wres['scope']+'; '+structure_water_provenance})
                            st.caption({'ru':'Изменение состава культур и технологии полива рассчитано одновременно; их эффекты не идентифицированы отдельно. Уменьшение подачи или забора воды не равно доказанному водосбережению бассейна. Параметры почв, повторный водозабор и запасы влаги не калиброваны.',
                                'kk':'Егіс пен суару технологиясының әсері бірге есептелген; бұл нақты бассейндік үнем емес.',
                                'en':'Crop mix and irrigation method change jointly; effects are not separately identified. Lower delivery/withdrawal is not proven catchment savings. Soil storage, reused flows and field measurements are not calibrated.'}[lang])
                            report_payload['inputs'].append(['Farm crop-mix water scenario assumptions',
                                f"baseline_ha={_water_b}; proposed_ha={_water_a}; per_crop={structure_water_data}; conveyance_eta={structure_water_conveyance}; return assumptions={structure_water_baseline_returns}/{structure_water_proposed_returns}; period=one documented growing season",structure_water_provenance])
                        except (ValueError,TypeError,KeyError) as _sw_err:
                            st.warning({'ru':'Расчёт воды до/после недоступен: ',
                                        'kk':'Су есебі қолжетімсіз: ',
                                        'en':'Crop-mix water comparison unavailable: '}[lang]+str(_sw_err))
            with st.expander({'ru':'А1: выбросы исходной и оптимизированной структуры',
                              'kk':'A1: бастапқы және оңтайлы егіс құрылымының шығарындылары',
                              'en':'A1: baseline vs optimized crop-mix emissions'}[lang],expanded=False):
                st.caption({'ru':'Частичный углеродный след по культурам: азот (кг N/га), дизель (л/га), электричество (кВт·ч/га). Заполните все активные культуры. Пустые поля не равны нулю. Текущие доли посевов задаются в блоке экономической цели выше; маржа для этого не требуется.',
                            'kk':'Дақыл бойынша азот (кг N/га), дизель (л/га), электр (кВт·сағ/га). Бос дерек нөл емес. Бастапқы егіс үлестері жоғарыдағы экономикалық бөлімде енгізіледі.',
                            'en':'Partial per-crop GHG: nitrogen kg N/ha, diesel litres/ha, electricity kWh/ha. Missing is not zero. Enter baseline shares in the economic section above; margin inputs are optional.'}[lang])
                _a1_products=sorted(set(str(x) for x in alloc['product']) | set(optimization_baseline_shares))
                _a1_base={str(k):float(v)*float(area_ha)/100 for k,v in optimization_baseline_shares.items()}
                _a1_plan={str(r['product']):float(r['area_ha']) for _,r in alloc.iterrows()}
                # Published activities are optional SCENARIOS, not observed farm values.
                # Streamlit data_editor is never auto-populated unless user selects the
                # explicit historical/analogue reference switch.
                _ref_option=st.checkbox({
                    'ru':'Заполнить доступные справочные нормы N и дизеля (исторические / аналоги; низкая точность)',
                    'kk':'N және дизель бойынша қолда бар анықтамалық нормаларды қолдану (тарихи / балама; дәлдігі төмен)',
                    'en':'Prefill available N and diesel reference rates (historical / analogues; low confidence)'
                }[lang],value=False,key='qunar_a1_evidence_prefill')
                _ref_density=None
                if _ref_option:
                    _ref_density=q_number_input({
                        'ru':'Плотность дизеля для пересчёта кг → л, кг/л (допущение)',
                        'kk':'Дизель тығыздығы, кг/л (жорамал)',
                        'en':'Diesel density to convert kg to litres, kg/L (assumption)'
                    }[lang],min_value=0.8,max_value=0.9,value=0.835,step=0.005,
                       key='qunar_a1_diesel_density')
                _ref_evidence_notes=[]
                _ref_n_and_d={}
                if _ref_option:
                    for _p in _a1_products:
                        _nref=crop_references(_p,'nitrogen_kg_n_ha',as_of_year=calculation_year)
                        _dref=suggest_diesel_l_per_ha(_p,density_kg_l=_ref_density)
                        # Conditional Kazakhstan N90 requires exactly the target technology;
                        # use FAO regional analogue as explicitly labelled generic scenario.
                        _candidate=next((x for x in _nref if x.evidence_level=='external_historical_analogue'),None)
                        _ref_n_and_d[_p]={
                            'nitrogen_kg_ha':(_candidate.midpoint if _candidate else float('nan')),
                            'diesel_litres_ha':(_dref[0] if _dref else float('nan'))}
                        if _candidate:
                            _ref_evidence_notes.append(_p+' N: '+evidence_note(_candidate))
                        if _dref:
                            _ref_evidence_notes.append(_p+' diesel: '+evidence_note(_dref[1])+
                                f'; user-chosen density={_ref_density:.3f} kg/L')
                    st.warning({
                        'ru':'Подставлены исторические или зарубежные типовые значения, НЕ данные хозяйства. Электричество осталось неизвестным; его нельзя считать нулевым. Проверьте почву и технологию. Экономическая себестоимость автоматически не подставляется.',
                        'kk':'Ескі немесе шетелдік үлгілік мәндер берілді, шаруашылықтың нақты дерегі емес. Электр энергиясы белгісіз, нөл емес. Шығынның ағымдағы құны автоматты енгізілмейді.',
                        'en':'Historical or foreign reference rates are scenarios, not farm measurements. Electricity remains unknown, NOT zero; modern production costs are not inferred.'
                    }[lang])
                    with st.expander({'ru':'Источники подставленных нормативов','kk':'Нормалардың дереккөздері','en':'Reference rate sources'}[lang]):
                        for _note in _ref_evidence_notes:
                            st.caption(_note)
                _a1_frame=pd.DataFrame([{
                    'product':p,'display':extended_crop_label(p,lang),
                    'baseline_area_ha':_a1_base.get(p,0.0),
                    'optimized_area_ha':_a1_plan.get(p,0.0),
                    'nitrogen_kg_ha':_ref_n_and_d.get(p,{}).get('nitrogen_kg_ha',float('nan')),
                    'diesel_litres_ha':_ref_n_and_d.get(p,{}).get('diesel_litres_ha',float('nan')),
                    'electricity_kwh_ha':float('nan')}
                    for p in _a1_products])
                _a1_edited=st.data_editor(_a1_frame,hide_index=True,use_container_width=True,
                    disabled=['product','display','baseline_area_ha','optimized_area_ha'],
                    key=('a1_crop_intensity_editor_ref' if _ref_option else 'a1_crop_intensity_editor'),column_config={'product':None})
                _a1_evidence=st.text_input({'ru':'Источник/сценарное допущение для норм затрат ресурсов по культурам',
                                            'kk':'Дақылдардың ресурстық нормаларының дереккөзі/жорамалдары',
                                            'en':'Evidence or assumptions for crop activity intensities'}[lang],key='a1_crop_intensity_source')
                _a1_confirm=st.checkbox({'ru':'Подтверждаю значения, включая реальные нули, и неизменность норм на гектар при перераспределении',
                                         'kk':'Мәндерді және га бойынша шығын нормалары өзгермейтінін растадым',
                                         'en':'Confirm amounts including true zeros and unchanged per-ha rates for the crop-mix comparison'}[lang],key='a1_crop_intensity_confirm')
                if _a1_confirm:
                    try:
                        if abs(sum(_a1_base.values())-float(area_ha))>max(.01,float(area_ha)*.005):
                            raise ValueError('Baseline crop shares must sum to 100% (entered in economic section).')
                        _a1_acts={str(r['product']):{
                            'nitrogen_kg_ha':r['nitrogen_kg_ha'],
                            'diesel_litres_ha':r['diesel_litres_ha'],
                            'electricity_kwh_ha':r['electricity_kwh_ha']}
                            for _,r in _a1_edited.iterrows()}
                        _a1_source_for_calc=(_a1_evidence.strip() + (' | ' if _a1_evidence.strip() and _ref_evidence_notes else '') + ' | '.join(_ref_evidence_notes))
                        _a1_comp=compare_crop_structures(baseline_areas=_a1_base,
                            proposed_areas=_a1_plan,baseline_activity_per_ha=_a1_acts,
                            grid_factor=float(ef),diesel_factor=float(DEFAULT_DIESEL_CO2_KG_L),
                            accounting_period='apr_sep',evidence=_a1_source_for_calc,confirmed=True)
                        _m1,_m2,_m3=st.columns(3)
                        _m1.metric({'ru':'Исходные выбросы, кг CO₂e','kk':'Бастапқы шығарындылар, кг CO₂e','en':'Baseline, kg CO₂e'}[lang],f"{_a1_comp['baseline_kgco2e']:,.1f}")
                        _m2.metric({'ru':'Сценарные выбросы, кг CO₂e','kk':'Сценарий шығарындылары, кг CO₂e','en':'Scenario, kg CO₂e'}[lang],f"{_a1_comp['scenario_kgco2e']:,.1f}")
                        _m3.metric({'ru':'Изменение, кг CO₂e','kk':'Өзгеріс, кг CO₂e','en':'Change, kg CO₂e'}[lang],f"{_a1_comp['change_kgco2e']:+,.1f}")
                        st.caption({'ru':'Сценарное изменение частичных выбросов при сохранении норм на гектар, не фактическое сокращение CO₂e. Не учтены производство удобрений, косвенный N₂O, изменение почвенного углерода и навоз.',
                                    'kk':'Бұл нақты төмендеу емес: дақылдар үлесі өзгергендегі ішінара сценарийлік есеп.',
                                    'en':'Counterfactual partial emissions assuming unchanged per-ha activities; not achieved mitigation. Fertilizer manufacture, indirect N2O, soil carbon and manure excluded.'}[lang])
                        _cross_module_summary_rows.append({'label':'A1 crop structure partial GHG baseline, kg CO2e',
                            'value':f"{_a1_comp['baseline_kgco2e']:.2f}",'note':_a1_evidence})
                        _cross_module_summary_rows.append({'label':'A1 crop structure partial GHG scenario, kg CO2e',
                            'value':f"{_a1_comp['scenario_kgco2e']:.2f}",'note':_a1_evidence})
                        _cross_module_summary_rows.append({'label':'A1 crop structure partial GHG change, kg CO2e',
                            'value':f"{_a1_comp['change_kgco2e']:+.2f}",
                            'note':'Partial counterfactual crop mix, not observed mitigation'})
                        report_payload['inputs'].append(['A1 crop-level GHG assumptions',
                            f'Apr-Sep; grid={ef} kgCO2e/kWh; diesel={DEFAULT_DIESEL_CO2_KG_L} kgCO2/L; '
                            f'per-crop N/diesel/electricity={_a1_acts}; baseline shares={optimization_baseline_shares}; '
                            f'optimized areas={_a1_plan}',_a1_evidence])
                    except (ValueError,TypeError,KeyError) as _a1_err:
                        st.warning(str(_a1_err))
            s1,s2,s3,s4=st.columns(4)
            s1.metric({"kk":"Құрылымның QŪNAR бағасы","ru":"Оценка структуры QŪNAR","en":"Structure QŪNAR score"}[lang],f"{opt['weighted_qunar']:.1f}/100")
            if optimization_profile in ('survey_proxy','custom'):
                st.caption({'kk':f"Таңдалған салмақ профилінің орташа балы: {opt['weighted_profile_score']:.1f}/100. Жоғарыдағы QŪNAR негізгі балы 60/40 салыстыруға арналған.",
                            'ru':f"Средний балл выбранного профиля: {opt['weighted_profile_score']:.1f}/100. Базовый балл QŪNAR выше по-прежнему рассчитан по весам 60/40 для сопоставимости.",
                            'en':f"Mean score under selected weights: {opt['weighted_profile_score']:.1f}/100. Baseline QŪNAR score above remains based on 60/40 for comparison."}[lang])
            s2.metric({"kk":"Климаттық тұрақтылық","ru":"Климатическая устойчивость","en":"Climate resilience"}[lang],f"{opt['weighted_climate']:.1f}/100")
            s3.metric({"kk":"Ресурс тиімділігі","ru":"Ресурсоэффективность","en":"Resource efficiency"}[lang],f"{opt['weighted_resource']:.1f}/100")
            s4.metric({"kk":"Бағалау сенімділігі","ru":"Уверенность в оценке","en":"Assessment confidence"}[lang],f"{opt['weighted_reliability']:.1f}/100")
            _structure_msg = {
                "kk":f"Есептік құрылым {area_ha:.1f} га аумақты {len(out)} дақылға бөледі; ең ірі үлес {out.iloc[:,1].max():.1f}%.",
                "ru":f"Расчётная структура распределяет {area_ha:.1f} га между {len(out)} культурами. Максимальная доля {out.iloc[:,1].max():.1f}%.",
                "en":f"Calculated allocation covers {area_ha:.1f} ha and {len(out)} crops. Largest share {out.iloc[:,1].max():.1f}%."
            }[lang]
            if _scenario_available_water > 0:
                st.success(_structure_msg)
            else:
                st.info(_structure_msg)
            _sust = opt.get('sustainable_comparison')
            if _sust:
                if _sust.get('baseline_feasible_under_current_water_budget') is False:
                    st.warning({'ru':'Исходная структура нарушает действующий водный лимит: показатели «до» приведены только как недопустимый контрфактический сценарий, а не реализуемая база экономии.', 'kk':'Бастапқы құрылым су шегінен асады; «дейін» мәндері іске асырылатын жоспар емес.', 'en':'The baseline exceeds the current water limit; before-values are infeasible counterfactuals, not demonstrated savings.'}[lang])
                st.markdown('#### ' + {'ru':'Устойчивый компромисс: строгие ограничения','kk':'Тұрақты ымыра: қатаң шектеулер','en':'Sustainable compromise: hard safeguards'}[lang])
                _scols=st.columns(3)
                _scols[0].metric({'ru':'Подача воды (до → после)','kk':'Су беру (дейін → кейін)','en':'Water delivery (before → after)'}[lang],f"{_sust['optimized_water_m3']:,.0f} м³",f"{_sust['optimized_water_m3']-_sust['baseline_water_m3']:+,.0f} м³")
                _scols[1].metric({'ru':'Частичные выбросы (до → после)','kk':'Ішінара шығарындылар','en':'Partial emissions (before → after)'}[lang],f"{_sust['optimized_partial_ghg_kg_co2e']:,.0f} кг",f"{_sust['optimized_partial_ghg_kg_co2e']-_sust['baseline_partial_ghg_kg_co2e']:+,.0f} кг")
                _scols[2].metric({'ru':'Сценарная маржа (до → после)','kk':'Сценарийлік маржа','en':'Scenario margin (before → after)'}[lang],f"{_sust['optimized_margin_kzt']:,.0f} тг",f"{_sust['optimized_margin_kzt']-_sust['baseline_margin_kzt']:+,.0f} тг")
                st.caption({'ru':'Ограничения: вода и частичные выбросы не выше исходной структуры, маржа не ниже заданного порога. Это математически допустимый сценарий с указанными предположениями; не доказанный фактический эффект.',
                    'kk':'Су мен ішінара шығарындылар бастапқы деңгейден жоғары емес; маржа берілген шектен төмен емес. Бұл нақты өлшенген әсер емес.',
                    'en':'Water and partial emissions do not exceed the baseline; margin respects its floor. This is a conditional feasible scenario, not observed improvement.'}[lang])
                report_payload['summary'].extend([
                    {'label':'Sustainable compromise (conditional)', 'value':'Feasible under explicit margin/water/partial-GHG constraints', 'note':optimization_ghg_evidence},
                    {'label':'Water baseline / optimized (m³)', 'value':f"{_sust['baseline_water_m3']:,.0f} / {_sust['optimized_water_m3']:,.0f}"},
                    {'label':'Partial GHG baseline / optimized (kg CO₂e)', 'value':f"{_sust['baseline_partial_ghg_kg_co2e']:,.0f} / {_sust['optimized_partial_ghg_kg_co2e']:,.0f}"},
                    {'label':'Margin baseline / optimized (KZT)', 'value':f"{_sust['baseline_margin_kzt']:,.0f} / {_sust['optimized_margin_kzt']:,.0f}"},
                ])
            if opt.get("economic_objective_active"):
                em1,em2,em3=st.columns(3)
                em1.metric({"kk":"Орташа экономикалық маржа","ru":"Средняя экономическая маржа","en":"Weighted economic margin"}[lang], f"{opt.get('weighted_economic_margin_kzt_ha',0):,.0f} {UNITS['currency']}/{UNITS['ha']}")
                em2.metric({"kk":"Экономикалық критерий салмағы","ru":"Вес экономического критерия","en":"Economic-objective weight"}[lang], f"{opt.get('economic_weight',0)*100:.0f}%")
                em3.metric({"kk":"Оңтайландырылған маржа","ru":"Оптимизированная маржа","en":"Optimized contribution margin"}[lang], f"{opt.get('optimized_contribution_margin_kzt',0):,.0f} {UNITS['currency']}")
                st.caption({"kk":"Экономикалық критерий оң және теріс енгізілген маржаларды салыстырады; жоқ деректерді толтырмайды.","ru":"Экономический критерий учитывает введённую положительную и отрицательную маржу; недостающие данные не подставляются.","en":"The economic criterion uses both positive and negative user-entered margins, without imputing missing data."}[lang])
                st.warning({"kk":"Көрсетілген маржа - болжамды сценарийлік көрсеткіш, нақты таза пайда емес. Ол әр дақыл бойынша шаруашылықтың нақты өнімділігіне, сату бағасына, өндірістік және суару шығындарына тәуелді. Расталмаған деректер болса, нәтижені кепілдендірілген табыс ретінде пайдаланбаңыз.","ru":"Маржа - ориентировочная сценарная оценка, не фактическая чистая прибыль. Она зависит от урожайности, цены реализации и производственных затрат конкретного хозяйства по каждой культуре, включая орошение. При неподтверждённых данных нельзя считать её гарантированным доходом.","en":"Contribution margin is an indicative scenario estimate, not observed net profit. It depends on farm-specific yields, selling prices and crop-level production costs, including irrigation. Unverified inputs cannot support guaranteed-income claims."}[lang])
                if opt.get('baseline_status') == 'shares_do_not_sum_to_100':
                    st.warning({'ru':'Сравнение «до/после» не рассчитано: текущие доли посевов не составляют 100%.','kk':'«Дейін/кейін» салыстыруы есептелмеді: бастапқы үлестердің қосындысы 100% емес.','en':'Before/after comparison omitted: baseline shares do not sum to 100%.'}[lang])
                if opt.get('baseline_water_feasible') is False:
                    st.warning({'ru':'Исходная структура превышает тот же водный лимит. Её нельзя использовать как реализуемую базу для сравнения финансового эффекта.',
                                'kk':'Бастапқы құрылым да су лимитінен асады. Оны іске асатын экономикалық база ретінде салыстыруға болмайды.',
                                'en':'The baseline also breaches the water limit and cannot be treated as an achievable financial comparator.'}[lang])
                if opt.get('baseline_available'):
                    st.markdown("#### " + {"kk":"Құрылымның тиімділігі: дейін / кейін","ru":"Эффект структуры: до / после","en":"Structure effect: before / after"}[lang])
                    _b1,_b2,_b3,_b4=st.columns(4)
                    _b1.metric({"kk":"Маржа - дейін","ru":"Маржа - до","en":"Margin - before"}[lang], f"{opt.get('baseline_contribution_margin_kzt',0):,.0f} {UNITS['currency']}" if opt.get('baseline_contribution_margin_kzt') is not None else "—")
                    _b2.metric({"kk":"Маржа - кейін","ru":"Маржа - после","en":"Margin - after"}[lang], f"{opt.get('optimized_contribution_margin_kzt',0):,.0f} {UNITS['currency']}")
                    _gain=opt.get('economic_gain_kzt')
                    _gain_pct=opt.get('economic_gain_pct')
                    _b3.metric({"kk":"Экономикалық өзгеріс","ru":"Экономический эффект","en":"Economic change"}[lang], f"{_gain:,.0f} {UNITS['currency']}" if _gain is not None else "—", f"{_gain_pct:+.1f}%" if _gain_pct is not None else None)
                    _wch=opt.get('water_change_m3'); _wchp=opt.get('water_change_pct')
                    _b4.metric({"kk":"Су қажеттілігінің өзгеруі","ru":"Изменение потребности в воде","en":"Water-demand change"}[lang], f"{_wch:,.0f} m³" if _wch is not None else "—", f"{_wchp:+.1f}%" if _wchp is not None else None)
                    if opt.get('baseline_margin_per_m3_kzt') is not None and opt.get('optimized_margin_per_m3_kzt') is not None:
                        st.caption({"kk":f"1 {UNITS['m3']} суға маржа: дейін {opt['baseline_margin_per_m3_kzt']:.2f} тг/{UNITS['m3']}, кейін {opt['optimized_margin_per_m3_kzt']:.2f} тг/{UNITS['m3']}.","ru":f"Маржа на 1 {UNITS['m3']} воды: до {opt['baseline_margin_per_m3_kzt']:.2f} тг/{UNITS['m3']}, после {opt['optimized_margin_per_m3_kzt']:.2f} тг/{UNITS['m3']}.","en":f"Contribution margin per 1 m³ of water: before {opt['baseline_margin_per_m3_kzt']:.2f} {UNITS['currency']}/m³, after {opt['optimized_margin_per_m3_kzt']:.2f} {UNITS['currency']}/m³."}[lang])
            elif opt.get('economic_objective_requested') in ('balanced','economic'):
                st.warning({"kk":"Экономикалық режим сұралды, бірақ кемінде екі дақыл бойынша маржа енгізілмеген. Сондықтан QŪNAR ресурс-климаттық мақсатқа қауіпсіз түрде қайтты.","ru":"Экономический режим выбран, но маржа введена менее чем для двух культур. QŪNAR безопасно вернулся к ресурсно-климатической целевой функции.","en":"An economic mode was requested, but margins were supplied for fewer than two crops. QŪNAR safely fell back to the resource-climate objective."}[lang])

            if opt.get("effective_max_share", optimization_max_share) > optimization_max_share + 1e-9:
                st.info({
                    "kk":f"Таңдалған дақыл саны үшін {optimization_max_share*100:.0f}% шегі математикалық тұрғыдан мүмкін емес. Есепте ең төмен мүмкін шек {opt['effective_max_share']*100:.1f}% қолданылды.",
                    "ru":f"Для выбранного числа культур ограничение {optimization_max_share*100:.0f}% математически невыполнимо. В расчете использован минимально допустимый предел {opt['effective_max_share']*100:.1f}%.",
                    "en":f"For the selected number of crops, a {optimization_max_share*100:.0f}% cap is infeasible. The minimum feasible cap of {opt['effective_max_share']*100:.1f}% was used."
                }[lang])
            st.markdown("#### " + {"kk":"Сценарийді түсіндіру","ru":"Интерпретация сценария","en":"Scenario interpretation"}[lang])
            st.write({
                "kk":f"Ұсынылған құрылымның орташа су нормасы {opt['weighted_water_m3_ha']:,.0f} {UNITS['m3']}/га, жалпы есептік қажеттілік {opt['modelled_total_water_m3']:,.0f} {UNITS['m3']}.",
                "ru":f"Средняя норма воды в рекомендуемой структуре {opt['weighted_water_m3_ha']:,.0f} {UNITS['m3']}/га, общая расчетная потребность {opt['modelled_total_water_m3']:,.0f} {UNITS['m3']}.",
                "en":f"The recommended structure averages {opt['weighted_water_m3_ha']:,.0f} m³/ha, with total modelled demand of {opt['modelled_total_water_m3']:,.0f} m³."
            }[lang])
            if _scenario_available_water > 0:
                if opt.get("water_feasible"):
                    st.success({"kk":f"Су шектеуі орындалды: {opt['modelled_total_water_m3']:,.0f} {UNITS['m3']} ≤ {_scenario_available_water:,.0f} {UNITS['m3']}.","ru":f"Ограничение по воде соблюдено: {opt['modelled_total_water_m3']:,.0f} {UNITS['m3']} ≤ {_scenario_available_water:,.0f} {UNITS['m3']}.","en":f"Water constraint satisfied: {opt['modelled_total_water_m3']:,.0f} m³ ≤ {_scenario_available_water:,.0f} m³."}[lang])
                else:
                    st.error({"kk":"Берілген су көлемімен таңдалған дақыл саны/үлес шектеулері шеңберінде толық орындалатын құрылым табылмады.","ru":"При указанном объеме воды не найдено полностью выполнимой структуры при текущем числе культур и ограничениях долей.","en":"No fully feasible structure was found under the entered water volume and current crop/share constraints."}[lang])
            else:
                st.warning({"kk":"Су лимиті енгізілмеді: құрылым алдын ала есептелді, судың жеткіліктілігі тексерілген жоқ.","ru":"Водный лимит не указан: структура предварительная, обеспеченность водой не проверена.","en":"Water budget not entered: allocation is provisional and water feasibility has not been checked."}[lang])
            if user_level == "researcher":
                with st.expander({"kk":"Оңтайландыру әдістемесі","ru":"Методика оптимизации","en":"Optimization method"}[lang]):
                    st.write({
                        "kk":f"Алдымен климат пен су жүктемесі бойынша Парето басымдығына түспейтін нұсқалар анықталады. Одан кейін таңдалған басымдық салмақтары бойынша жиынтық пайдалылық есептеліп, бір дақыл үлесі {optimization_max_share*100:.0f}% шегінен аспайтындай етіп аудан бөлінеді. Су жүктемесі ресми немесе дерек болмаған жағдайда ашық белгіленген есептік {UNITS['m3']}/га нормаларына негізделеді; нарықтық бағаның жанама көрсеткіші қолданылмайды.",
                        "ru":f"Структура решается как задача линейного программирования: максимизируется ресурсно-климатическая полезность при равенстве суммарной площади, ограничении доли одной культуры не выше {optimization_max_share*100:.0f}% и, при заданном объеме воды, жестком водном ограничении. Уверенность в данных не входит в целевую функцию. Косвенный рыночный показатель цены исключен. Если включена экономическая цель и пользователь ввел маржу по культурам, ресурсно-климатическая полезность объединяется с нормированным экономическим критерием; при отсутствии таких данных экономическая часть не подставляется.",
                        "en":f"First, Pareto non-dominated options are identified across climate, water efficiency and evidence reliability. Utility is then computed with the selected weights and land is allocated with a single-crop cap of {optimization_max_share*100:.0f}%. Water pressure uses official/explicitly labelled fallback m³/ha norms; the market-price proxy is excluded. If the economic objective is enabled and user-entered crop margins are available, resource-climate utility is combined with a normalized economic criterion; otherwise no economic values are imputed."
                    }[lang])


    # v0.8 economic contour: transparent scenario, never a hidden-price profit claim.
    if crop is not None and selling_price_kzt_t > 0:
        _yield_reference = None
        if expected_yield_c_ha > 0:
            econ_yield = float(expected_yield_c_ha)
            econ_yield_source = {"kk":"Шаруашылық енгізген өнімділік","ru":"Урожайность хозяйства, введённая пользователем","en":"User-entered farm yield"}[lang]
        else:
            _yield_reference = trailing_three_year_yield(DATA_DIR / "analytical_panel.csv", used_district, crop, calculation_year)
            econ_yield = _yield_reference.value_c_ha
            econ_yield_source = {"kk":"Аудандық орташа өнімділік","ru":"Средняя урожайность района","en":"District historical mean yield"}[lang]
        if econ_yield is not None:
            _yield_years = ', '.join(map(str, _yield_reference.years)) if _yield_reference else ''
            st.caption({"kk":f"Экономикалық есептегі өнімділік: {econ_yield:.2f} ц/га. Дереккөзі: {econ_yield_source}. " + (f"Жылдар: {_yield_years}. Бұл шаруашылық көрсеткіші емес." if _yield_reference else ""),
                        "ru":f"Урожайность для экономического расчёта: {econ_yield:.2f} ц/га. Источник: {econ_yield_source}. " + (f"Годы: {_yield_years}. Это справочное среднее, не фактическая урожайность хозяйства." if _yield_reference else ""),
                        "en":f"Yield for the economic calculation: {econ_yield:.2f} c/ha. Source: {econ_yield_source}. " + (f"Years: {_yield_years}. District reference, not observed farm yield." if _yield_reference else "")}[lang])
            if _yield_reference and len(_yield_reference.years) < 3:
                st.warning({"kk":f"Тек {len(_yield_reference.years)}/3 жыл қолжетімді.","ru":f"Доступны только {len(_yield_reference.years)} из 3 предыдущих лет. Оценка менее надёжна.","en":f"Only {len(_yield_reference.years)} of the last 3 years available; lower confidence."}[lang])
            if 'pred' in locals() and pred is not None:
                st.caption({"kk":f"Random Forest жеке климаттық бағдар: {pred:.2f} ц/га (маржада қолданылмайды).", "ru":f"Отдельный климатический ориентир Random Forest: {pred:.2f} ц/га (не используется для маржи).", "en":f"Separate Random Forest climate reference: {pred:.2f} c/ha (not used in contribution margin)."}[lang])
            report_payload['inputs'].append([
                {"kk":"Экономикалық есеп үшін өнімділік","ru":"Урожайность для экономического расчёта","en":"Economic calculation yield"}[lang],
                f"{econ_yield:.2f} c/ha",
                econ_yield_source + (f"; {_yield_years}" if _yield_reference else "")])
            if _yield_reference:
                report_payload['inputs'].append([
                    {"kk":"Аудандық анықтаманың мәртебесі","ru":"Статус районного справочника","en":"District reference evidence"}[lang],
                    str(len(_yield_reference.years)) + "/3",
                    {"kk":"Ресми аудандық мәлімет, ферма өлшемі емес","ru":"Официальный районный ряд, не измерения хозяйства","en":"Official district series, not farm observation"}[lang]])
            report_payload['inputs'].append([
                {"kk":"Экономикалық есептегі баға, тг/т", "ru":"Цена для экономического расчёта, тг/т", "en":"Economic calculation price, KZT/t"}[lang],
                f"{selling_price_kzt_t:,.2f}", selling_price_source,
            ])
            report_payload['inputs'].append([
                {"kk":"Өзге айнымалы шығындар (су/энергиясыз), тг/га",
                 "ru":"Прочие переменные затраты (без воды/энергии), тг/га",
                 "en":"Other variable costs excluding water/energy, KZT/ha"}[lang],
                f'{variable_cost_kzt_ha:,.2f}' if variable_cost_kzt_ha > 0 else '—',
                variable_cost_source or {"kk":"Белгісіз, маржа есептелмейді",
                                         "ru":"Неизвестно, маржа недоступна",
                                         "en":"Unknown, margin unavailable"}[lang],
            ])
            econ08 = economic_feasibility(
                yield_centners_ha=econ_yield,
                selling_price_kzt_t=selling_price_kzt_t,
                variable_cost_kzt_ha=(variable_cost_kzt_ha if variable_cost_kzt_ha > 0 else None),
                water_m3_ha=(effective_water_used/area_ha if effective_water_used is not None and area_ha > 0 else None),
                water_tariff_kzt_m3=water_tariff,
                energy_kwh_ha=(economic_energy_kwh/area_ha if economic_energy_kwh is not None and area_ha > 0 else None),
                electricity_tariff_kzt_kwh=electricity_tariff,
                variable_cost_includes_water_energy=False,  # field explicitly describes OTHER variable costs
            )
            st.markdown("### " + {"kk":"Экономикалық орындылық","ru":"Экономическая целесообразность","en":"Economic feasibility"}[lang])
            e1,e2,e3=st.columns(3)
            e1.metric({"kk":"Жалпы түсім, тг/га","ru":"Валовая выручка, тг/га","en":"Gross revenue, KZT/ha"}[lang], f"{econ08['gross_revenue_kzt_ha']:,.0f}")
            e2.metric({"kk":"Ресурстық шығын, тг/га","ru":"Стоимость воды и энергии, тг/га","en":"Water + energy cost, KZT/ha"}[lang], (f"{econ08['resource_cost_kzt_ha']:,.0f}" if econ08["resource_cost_kzt_ha"] is not None else "—"))
            _margin = econ08.get('contribution_margin_kzt_ha')
            e3.metric({"kk":"Салым маржасы, тг/га","ru":"Отдельная маржа по введённому водопотреблению, тг/га","en":"Contribution margin, KZT/ha"}[lang], f"{_margin:,.0f}" if _margin is not None else "—")
            st.caption({
                "kk":"Бұл нәтиже таза пайда емес: ол енгізілген баға, айнымалы шығындар, су және энергия шығындары негізіндегі сценарийлік маржа.",
                "ru":"Этот результат не равен чистой прибыли: это сценарная маржа на основе введенной цены, переменных затрат и учтенных расходов на воду и энергию.",
                "en":"This is not net profit. It is a scenario contribution margin based on the entered price, variable costs, water and energy costs."
            }[lang])
            if irrigation_compare_enabled and economic_energy_kwh is None:
                st.info({"ru":"Сравнение стоимости энергии недоступно: потребление электроэнергии не введено и параметры насоса неизвестны.",
                         "kk":"Энергия құнын салыстыру мүмкін емес: электр тұтынуы мен сорғы сипаттары белгісіз.",
                         "en":"Energy-cost comparison unavailable: neither measured electricity nor a documented pumping estimate is available."}[lang])
            if irrigation_compare_enabled and economic_energy_kwh is not None:
                if not irrigation_evidence.strip() or not (variable_cost_kzt_ha > 0) or irrigation_type == "unknown":
                    st.warning({"kk":"Сценарий үшін бастапқы суару түрі, шығындар және өнімділік өзгерісінің негіздемесі қажет.","ru":"Для сравнения нужны исходный тип орошения, переменные затраты и источник/явное допущение для изменения урожайности.","en":"Comparison requires known baseline irrigation, variable costs and a documented yield-effect assumption."}[lang])
                elif irrigation_target == irrigation_type:
                    st.info({"kk":"Салыстыру үшін басқа суару түрін таңдаңыз.","ru":"Выберите другой тип орошения для сравнения.","en":"Choose a different irrigation type."}[lang])
                else:
                    wd_initial = default_water_requirement(used_district, crop, irrigation_type)
                    wd_target = default_water_requirement(used_district, crop, irrigation_target)
                    if wd_initial.m3_ha <= 0 or wd_target.m3_ha <= 0:
                        st.warning({"kk":"Су нормалары жоқ.","ru":"Нет сопоставимых норм воды.","en":"Comparable water norms are unavailable."}[lang])
                    else:
                        baseline_kwh = economic_energy_kwh / area_ha if area_ha > 0 else 0.0
                        if baseline_kwh + irrigation_extra_energy < 0:
                            st.warning({"kk":"Энергия теріс болуы мүмкін емес.","ru":"Энергопотребление не может быть отрицательным.","en":"Energy consumption cannot be negative."}[lang])
                        else:
                            comp = irrigation_comparison(
                                baseline_yield_centners_ha=econ_yield, price_kzt_t=selling_price_kzt_t,
                                other_variable_cost_kzt_ha=variable_cost_kzt_ha,
                                baseline_water_m3_ha=wd_initial.m3_ha, proposed_water_m3_ha=wd_target.m3_ha,
                                baseline_energy_kwh_ha=baseline_kwh,
                                proposed_energy_kwh_ha=baseline_kwh + irrigation_extra_energy,
                                water_tariff_kzt_m3=water_tariff, electricity_tariff_kzt_kwh=electricity_tariff,
                                yield_change_pct=irrigation_yield_change_pct,
                                extra_technology_cost_kzt_ha=irrigation_extra_cost,
                                evidence=irrigation_evidence)
                            st.markdown("#### " + {"kk":"Суару сценарийінің экономикалық әсері","ru":"Экономический эффект смены орошения","en":"Irrigation-switch economic scenario"}[lang])
                            st.dataframe(pd.DataFrame([
                                {"indicator":{"ru":"Вода, м³/га","kk":"Су, м³/га","en":"Water, m³/ha"}[lang], "before":comp['baseline_water_m3_ha'], "after":comp['proposed_water_m3_ha']},
                                {"indicator":{"ru":"Маржа, тг/га","kk":"Маржа, тг/га","en":"Margin, KZT/ha"}[lang], "before":comp['baseline_margin_kzt_ha'], "after":comp['proposed_margin_kzt_ha']},
                                {"indicator":{"ru":"Стресс-маржа, тг/га","kk":"Стресс маржа, тг/га","en":"Stress margin, KZT/ha"}[lang], "before":comp['stress_baseline_margin_kzt_ha'], "after":comp['stress_proposed_margin_kzt_ha']},
                            ]).rename(columns={"indicator":{"ru":"Показатель","kk":"Көрсеткіш","en":"Metric"}[lang],"before":{"ru":"До","kk":"Бұрын","en":"Current"}[lang],"after":{"ru":"После","kk":"Кейін","en":"Proposed"}[lang]}), hide_index=True)
                            st.caption({"kk":"Стресс: баға -10%, өнімділік -10%, шығын +10%. Екі технологияға бірдей қолданылады. Су нормалары технологиялық сценарий, тәжірибелік дәлел емес.","ru":"Стресс-тест: цена -10%, урожайность -10%, расходы +10% для обеих технологий. Водные нормы содержат сценарные технологические коэффициенты. Результат не является подтверждённым полевым эффектом.","en":"Stress test: price -10%, yield -10%, costs +10% for both technologies. Water norms include technology scenario factors, not a measured treatment effect."}[lang])
                            report_payload["summary"].append({"label":{"ru":"Изменение маржи при смене полива, тг/га","kk":"Суару өзгергендегі маржа айырмасы, тг/га","en":"Irrigation-switch margin change, KZT/ha"}[lang], "value":f"{comp['margin_change_kzt_ha']:,.0f}", "note":irrigation_evidence})
                            report_payload["summary"].append({"label":{"ru":"Изменение маржи в стресс-тесте, тг/га","kk":"Стресс-тесттегі маржа айырмасы, тг/га","en":"Stress-test margin change, KZT/ha"}[lang], "value":f"{comp['stress_margin_change_kzt_ha']:,.0f}", "note":{"ru":"Цена -10%, урожайность -10%, затраты +10%","kk":"Баға -10%, өнімділік -10%, шығындар +10%","en":"Price -10%, yield -10%, costs +10%"}[lang]})
            if "comp" in locals() and irrigation_compare_enabled:
                _irrigation_rows, _irrigation_recommendation = irrigation_export(
                    comp, area_ha=area_ha,
                    input_yield_centners_ha=econ_yield,
                    ml_yield_centners_ha=pred if "pred" in locals() else None,
                    selling_price_kzt_t=selling_price_kzt_t,
                    other_variable_cost_kzt_ha=variable_cost_kzt_ha,
                    extra_technology_cost_kzt_ha=irrigation_extra_cost,
                    yield_change_pct=irrigation_yield_change_pct,
                    evidence=irrigation_evidence,
                    lang=lang, available_water_m3=available_water, reuse_pct=reuse)
                report_payload["summary"].extend(_irrigation_rows)
                # Keep the on-screen feasibility conclusion identical to the
                # report instead of relying on the generic farm water balance.
                st.info(_irrigation_recommendation["text"])
                st.caption({
                    "ru":"В сравнении технологий применяется районная норма воды для каждого вида полива; общий расчёт маржи выше использует введённое водопотребление. Сценарии зелёной энергии и смены полива независимы.",
                    "kk":"Суару технологияларын салыстыруда әр тәсілдің аудандық су нормасы қолданылады; жоғарыдағы жалпы маржа енгізілген су шығыны бойынша есептеледі. Жасыл энергия мен суару сценарийлері бөлек.",
                    "en":"Irrigation uses the district water norm for each method; the generic margin above uses entered farm water use. Green-energy and irrigation scenarios are separate."
                }[lang])
                _irrigation_names = {
                    "unknown":t["irrigation_unknown"], "furrow":t["irrigation_furrow"],
                    "sprinkler":t["irrigation_sprinkler"], "drip":t["irrigation_drip"],
                    "mixed":t["irrigation_mixed"]
                }
                report_payload["inputs"].extend([
                    [{"ru":"Исходная технология полива","kk":"Бастапқы суару тәсілі","en":"Baseline irrigation method"}[lang], _irrigation_names[irrigation_type], t["source_user"]],
                    [{"ru":"Сравниваемая технология полива","kk":"Салыстырылатын суару тәсілі","en":"Proposed irrigation method"}[lang], _irrigation_names[irrigation_target], t["source_user"]],
                    [{"ru":"Тариф воды, тг/м³","kk":"Су тарифі, тг/м³","en":"Water tariff, KZT/m³"}[lang], f"{water_tariff:.4f}", t["source_user"]],
                    [{"ru":"Тариф электроэнергии, тг/кВт·ч","kk":"Электр тарифі, тг/кВт·сағ","en":"Electricity tariff, KZT/kWh"}[lang], f"{electricity_tariff:.4f}", t["source_user"]],
                    [{"ru":"Сценарий смены полива: эффект урожайности, %","kk":"Суару сценарийі: өнімділік әсері, %","en":"Irrigation scenario: yield change, %"}[lang], f"{irrigation_yield_change_pct:.2f}", irrigation_evidence],
                ])
            if _margin is not None:
                report_payload["summary"].append({"label":{"kk":"Маржиналды нәтиже, тг/га","ru":"Отдельная маржа по введённому водопотреблению, тг/га","en":"Contribution margin, KZT/ha"}[lang],"value":f"{_margin:,.0f}"})
            else:
                st.info({"kk":"Маржаны есептеу үшін басқа айнымалы шығындарды енгізіңіз.","ru":"Для расчета маржинального результата введите прочие переменные затраты.","en":"Enter other variable costs to calculate the contribution margin."}[lang])
        else:
            st.info({"kk":"Ауданда осы дақыл бойынша соңғы үш жылдық деректер жоқ: өнімділікті енгізіңіз.","ru":"Для этой культуры и района нет доступной урожайности за три предыдущих года. Введите урожайность хозяйства для экономического расчёта.","en":"No valid district/crop yield data in the previous three years. Enter farm yield for the economic calculation."}[lang])

    if mode_key in ("mode1","mode2") and crop is not None:
        env = environmental_diagnostics(
            used_district, climate, area_ha, energy_kwh=observed_energy,
            emission_factor_kgco2_kwh=ef, pesticide_kg_ha=pesticide_kg_ha,
            salinized_share_pct=salinized_share_pct,
        )
        st.markdown("### " + {"kk":"Экологиялық диагностика","ru":"Экологическая диагностика","en":"Environmental diagnostics"}[lang])
        z1,z2,z3,z4 = st.columns(4)
        z1.metric({"kk":"Жылу экспозициясының процентилі","ru":"Перцентиль тепловой экспозиции","en":"Heat-exposure percentile"}[lang], f"{env.get('heat_exposure_percentile',0):.0f}/100")
        z2.metric({"kk":"Төмен жауын-шашын экспозициясы","ru":"Экспозиция к низким осадкам","en":"Low-precipitation exposure"}[lang], f"{env.get('low_precipitation_percentile',0):.0f}/100")
        z3.metric({"kk":"Төмен топырақ ылғалы экспозициясы","ru":"Экспозиция к низкой влажности почвы","en":"Low-soil-moisture exposure"}[lang], f"{env.get('low_soil_moisture_percentile',0):.0f}/100")
        z4.metric({"kk":"Экологиялық дерек қабаттары","ru":"Доступные экологические слои","en":"Environmental evidence layers"}[lang], f"{env.get('evidence_layers_available',0)}/{env.get('evidence_layers_max',7)}")
        status_available = {"kk":"бар","ru":"есть","en":"available"}[lang]
        status_unknown = {"kk":"белгісіз","ru":"неизвестно","en":"unknown"}[lang]
        st.caption({
            "kk":f"NASA климат қабаты: {status_available} · Энергия/CO₂: {status_available if env.get('energy_observed') else status_unknown} · Пестицидтер: {status_available if env.get('pesticide_observed') else status_unknown} · Тұздану: {status_available if env.get('salinity_observed') else status_unknown}",
            "ru":f"Климат NASA: {status_available} · Энергия/CO₂: {status_available if env.get('energy_observed') else status_unknown} · Пестициды: {status_available if env.get('pesticide_observed') else status_unknown} · Засоление: {status_available if env.get('salinity_observed') else status_unknown}",
            "en":f"NASA climate: {status_available} · Energy/CO₂: {status_available if env.get('energy_observed') else status_unknown} · Pesticides: {status_available if env.get('pesticide_observed') else status_unknown} · Salinity: {status_available if env.get('salinity_observed') else status_unknown}",
        }[lang])
        if env.get("operational_co2e_kg_ha") is not None:
            st.write("• " + {"kk":f"Электр энергиясына байланысты операциялық шығарындылар: {env['operational_co2e_kg_ha']:.1f} кг CO₂e/га.","ru":f"Операционные выбросы, связанные с электроэнергией: {env['operational_co2e_kg_ha']:.1f} кг CO₂e/га.","en":f"Electricity-related operational emissions: {env['operational_co2e_kg_ha']:.1f} kg CO₂e/ha."}[lang])
        if env.get("pesticide_kg_ha") is not None:
            st.write("• " + {"kk":f"Енгізілген пестицид жүктемесі: {env['pesticide_kg_ha']:.2f} кг/га.","ru":f"Введенная пестицидная нагрузка: {env['pesticide_kg_ha']:.2f} кг/га.","en":f"Entered pesticide load: {env['pesticide_kg_ha']:.2f} kg/ha."}[lang])
        if env.get("salinized_share_pct") is not None:
            st.write("• " + {"kk":f"Тұзданған жер үлесі: {env['salinized_share_pct']:.1f}% ({env.get('salinized_area_ha',0):.1f} га).","ru":f"Доля засоленной земли: {env['salinized_share_pct']:.1f}% ({env.get('salinized_area_ha',0):.1f} га).","en":f"Salinized land share: {env['salinized_share_pct']:.1f}% ({env.get('salinized_area_ha',0):.1f} ha)."}[lang])
        st.caption({"kk":"Бұл блок QŪNAR-да дәлелмен немесе нақты енгізумен қамтамасыз етілген климаттық, топырақ-ылғал, энергия-көміртек, пестицид және тұздану көрсеткіштерін бөлек көрсетеді. Экожүйенің толық жағдайы жеке бақылау жиынтығын қажет етеді.","ru":"Блок показывает экологически значимые показатели, обеспеченные климатическими данными или фактическим вводом: тепло, осадки, влажность корневой зоны, энергия/CO₂, пестициды и засоление. Комплексное состояние экосистемы требует отдельного набора наблюдений.","en":"This block reports environmentally relevant indicators supported by climate data or observed input: heat, precipitation, root-zone wetness, energy/CO₂, pesticides and salinity. Full ecosystem condition requires a separate observation set."}[lang])

    if mode_key == "mode4" and "out" in locals():
        div = diversification_metrics(pd.to_numeric(alloc["share"], errors="coerce").fillna(0).tolist())
        st.markdown("### " + {"kk":"Егіс құрылымының әртараптануы","ru":"Диверсификация структуры посевов","en":"Cropping-structure diversification"}[lang])
        d1,d2,d3 = st.columns(3)
        d1.metric({"kk":"Герфиндал-Хиршман индексі","ru":"Индекс Герфиндаля-Хиршмана","en":"HHI"}[lang], f"{div['hhi']:.3f}")
        d2.metric({"kk":"Тиімді дақылдар саны","ru":"Эффективное число культур","en":"Effective number of crops"}[lang], f"{div['effective_number_of_crops']:.2f}")
        d3.metric({"kk":"Әртараптандыру","ru":"Диверсификация","en":"Diversification"}[lang], f"{div['diversification_0_100']:.1f}/100")
        st.caption({"kk":"Герфиндал-Хиршман индексі егіс құрылымының шоғырлануын сипаттайды; төмен мән бірнеше дақыл арасында біркелкі бөлінуді көрсетеді.","ru":"Индекс Герфиндаля-Хиршмана характеризует концентрацию структуры посевов; более низкое значение соответствует более равномерному распределению площади между культурами.","en":"HHI describes cropping concentration; a lower value corresponds to a more even allocation across crops."}[lang])

    # Build a lightweight export snapshot from results already calculated on screen.
    if mode_key == "mode5" and "livestock" in locals():
        benchmark_export = livestock.get("district_benchmark", {}) or {}
        forecast_export = livestock.get("forecast", {}) or {}
        table_indicator = {"kk":"Көрсеткіш","ru":"Показатель","en":"Indicator"}[lang]
        table_value = {"kk":"Мәні","ru":"Значение","en":"Value"}[lang]
        head_source_export = {
            "user": {"kk":"Пайдаланушы дерегі","ru":"Данные пользователя","en":"User data"}[lang],
            "district_reference": {"kk":"Аудандық анықтамалық мән","ru":"Районное справочное значение","en":"District reference"}[lang],
            "unknown": {"kk":"Белгісіз","ru":"Неизвестно","en":"Unknown"}[lang],
        }.get(str(livestock.get("heads_source")), str(livestock.get("heads_source")))
        forecast_tier_export = {
            "validated": {"kk":"Тексерілген","ru":"Проверенный","en":"Validated"}[lang],
            "usable": {"kk":"Қолдануға болады","ru":"Допустимый","en":"Usable"}[lang],
            "guarded": {"kk":"Шектелген","ru":"Ограниченный","en":"Guarded"}[lang],
            "withheld": {"kk":"Жарияланбайды","ru":"Не публикуется","en":"Withheld"}[lang],
        }.get(str(forecast_export.get("forecast_tier")), str(forecast_export.get("forecast_tier") or ""))
        published_export = {
            True: {"kk":"Иә","ru":"Да","en":"Yes"}[lang],
            False: {"kk":"Жоқ","ru":"Нет","en":"No"}[lang],
        }.get(bool(forecast_export.get("publish_forecast")))
        def _row(label_kk, label_ru, label_en, value):
            return {table_indicator: {"kk":label_kk,"ru":label_ru,"en":label_en}[lang], table_value: value}
        report_payload["table"] = [
            _row("Аудан өніміндегі мал шаруашылығы үлесі, %", "Доля животноводства в выпуске района, %", "Livestock share of district output, %", livestock.get("livestock_share_pct")),
            _row("Есепте қолданылған мал саны, бас", "Поголовье в расчете, голов", "Herd used in calculation, head", livestock.get("heads") if heads_source != "unknown" else None),
            _row("Мал санының дереккөзі", "Источник данных о поголовье", "Herd source", head_source_export),
            _row("Соңғы ресми аудандық мал саны, бас", "Последнее официальное районное поголовье, голов", "Latest official district herd, head", benchmark_export.get("latest_district_heads")),
            _row("Соңғы ресми жыл", "Последний официальный год", "Latest official year", benchmark_export.get("latest_year")),
            _row("Аудандық салыстырмалы пайыздық деңгей, %", "Районный сравнительный перцентиль, %", "District herd percentile, %", benchmark_export.get("district_percentile")),
            _row("Шартты мал бірлігі", "Условные единицы скота", "Livestock units (LU)", livestock.get("livestock_units")),
            _row("Жайылым гектарына шартты мал бірлігі", "Условные единицы скота на гектар пастбища", "Livestock units per pasture ha", livestock.get("lu_per_pasture_ha")),
            _row("Анықтамалық су қажеттілігі, л/бас/тәул.", "Справочная потребность в воде, л/гол./сут.", "Reference water, L/head/day", livestock.get("reference_water_l_head_day")),
            _row("Жылдық анықтамалық су қажеттілігі, м³", "Справочная годовая потребность в воде, м³", "Reference annual water, m³", livestock.get("reference_water_m3_year")),
            _row("Қолжетімді судың қажеттілікті жабуы, %", "Покрытие справочной потребности доступной водой, %", "Available-water coverage of reference, %", livestock.get("reference_water_coverage_pct")),
            _row("Нақты су тұтынуы, м³/бас", "Фактическое водопотребление, м³/гол.", "Observed water, m³/head", livestock.get("water_m3_per_head")),
            _row("Жемшөп құрғақ затының қажеттілігі, кг/бас/тәул.", "Потребность в сухом веществе корма, кг/гол./сут.", "Reference feed dry matter, kg/head/day", livestock.get("reference_feed_dm_kg_head_day")),
            _row("Жылдық жемшөп қажеттілігі, т құрғақ зат", "Годовая потребность в кормах, т сухого вещества", "Reference annual feed dry matter, t", livestock.get("reference_feed_dm_t_year")),
            _row("Енгізілген жемшөп қорының қажеттілікті жабуы, %", "Покрытие потребности введенным запасом кормов, %", "Entered feed coverage of reference, %", livestock.get("feed_reference_coverage_pct")),
            _row("Нақты энергия тұтынуы, басына", "Фактическое энергопотребление на голову", "Observed energy, kWh/head", livestock.get("energy_kwh_per_head")),
            _row("Электр энергиясына байланысты CO₂e, кг", "Выбросы CO₂e, связанные с электроэнергией, кг", "Operational CO₂e, kg", livestock.get("operational_co2e_kg")),
            _row("Өңірлік мәнге қатысты өнімділік, %", "Продуктивность относительно регионального значения, %", "Productivity relative to regional reference, %", livestock.get("productivity_reference_ratio_pct")),
            _row("Болжам жылы", "Год прогноза", "Forecast year", forecast_export.get("forecast_year")),
            _row("Машиналық оқыту болжамы жариялана ма", "Публикуется ли прогноз машинного обучения", "Machine-learning forecast published", published_export),
            _row("Болжамның сенімділік деңгейі", "Уровень надежности прогноза", "Forecast tier", forecast_tier_export),
            _row("Машиналық оқыту болжамы, бас", "Прогноз машинного обучения, голов", "Machine-learning forecast herd, head", forecast_export.get("forecast_heads") if forecast_export.get("publish_forecast") else None),
            _row("Болжамдағы өзгеріс, %", "Изменение по прогнозу, %", "Forecast change, %", forecast_export.get("forecast_change_pct") if forecast_export.get("publish_forecast") else None),
            _row("Жалпы R², логарифмдік шкала", "Общий R², логарифмическая шкала", "Overall R², log scale", forecast_export.get("r2_log")),
            _row("Жалпы медианалық абсолюттік пайыздық қате, %", "Общая медианная абсолютная процентная ошибка, %", "Overall median absolute percentage error, %", forecast_export.get("median_ape_pct")),
            _row("Жалпы тексеру бақылауларының саны", "Общее число проверочных наблюдений", "Overall validation observations", forecast_export.get("validation_n")),
            _row("Таңдалған санаттың R² көрсеткіші", "R² выбранной категории", "Selected-category R²", ((forecast_export.get("species_validation") or {}).get("r2_log"))),
            _row("Таңдалған санаттың медианалық абсолюттік пайыздық қатесі, %", "Медианная абсолютная процентная ошибка выбранной категории, %", "Selected-category median absolute percentage error, %", ((forecast_export.get("species_validation") or {}).get("median_ape_pct"))),
            _row("Таңдалған санат бойынша тексеру бақылаулары", "Число проверочных наблюдений выбранной категории", "Selected-category validation observations", ((forecast_export.get("species_validation") or {}).get("n"))),
            _row("Сәуір-қыркүйек температурасы, °C", "Температура апреля-сентября, °C", "Apr-Sep temperature, °C", livestock.get("temperature_c")),
            _row("Сәуір-қыркүйек жауын-шашыны, мм", "Осадки апреля-сентября, мм", "Apr-Sep precipitation, mm", livestock.get("precipitation_mm")),
            _row("Сәуір-қыркүйектегі тамыр аймағының ылғалы", "Влажность корневой зоны в апреле-сентябре", "Apr-Sep root-zone wetness", livestock.get("root_zone_wetness")),
            _row("Сәуір-қыркүйек күн радиациясы, МДж/м²/тәул.", "Солнечная радиация апреля-сентября, МДж/м²/сут.", "Apr-Sep solar radiation, MJ/m²/day", livestock.get("solar_radiation_mj_m2_day")),
            _row("Деградацияланған жайылым, га", "Деградированное пастбище, га", "Degraded pasture, ha", livestock.get("degraded_pasture_ha")),
            _row("Нақты енгізілген деректердің толықтығы, %", "Полнота фактически введенных данных, %", "Observed-input completeness, %", livestock.get("input_completeness_pct")),
        ]
    elif mode_key == "mode1":
        if "pred" in locals():
            report_payload["summary"].append({"label":_active_yield_label, "value":f"{pred:.1f} {UNITS['centner_ha']}",
                  "note": _yield_choice.disclaimer})
        elif "scenario" in locals() and scenario is not None:
            report_payload["summary"].append({"label":{"kk":"QŪNAR бағасы","ru":"Оценка QŪNAR","en":"QŪNAR score"}[lang], "value":f"{float(scenario['QUNAR_score_0_100']):.1f}/100"})
        if "resource" in locals():
            if resource.get("farm_freshwater_m3") is not None: report_payload["summary"].append({"label":t["freshwater"],"value":f"{resource['farm_freshwater_m3']:,.0f} {UNITS['m3']}"})
            if resource.get("energy_kwh") is not None: report_payload["summary"].append({"label":t["energy_use"],"value":f"{resource['energy_kwh']:,.0f} {UNITS['kwh']}"})
            if resource.get("operational_co2e_kg") is not None: report_payload["summary"].append({"label":t["co2"],"value":f"{resource['operational_co2e_kg']:,.0f} {UNITS['kg']} CO₂e"})
        if "econ" in locals() and _grid_known and econ.get('total_saving_kzt') is not None:
            report_payload["summary"].append({"label":{"kk":"Жасыл энергия және таза су бойынша бөлек сценарий, тг","ru":"Отдельный сценарий зелёной энергии и пресной воды, тг","en":"Separate green-energy and freshwater scenario, KZT"}[lang],"value":f"{econ['total_saving_kzt']:,.0f} {UNITS['currency']}"})
        report_payload["analysis"] = list(locals().get("analysis", []) or [])
        report_payload["recommendations"] = structured_recommendations(locals().get("recs", []) or [], report_payload["analysis"], lang)
        if "econ" in locals() and _grid_known and econ.get('total_saving_kzt') is not None and econ['total_saving_kzt'] > 0:
            report_payload["recommendations"].insert(0, {
                "title":{"kk":"Экономикалық және климаттық басымдық","ru":"Экономико-климатический приоритет","en":"Economic and climate priority"}[lang],
                "text":{"kk":"Суару өзгерісінен бөлек жасыл энергия мен жалпы ресурс үнемдеу сценарийін қарастыруға болады. Екі нәтиженің үнемін қосуға болмайды.","ru":"Отдельно от смены полива можно рассмотреть сценарий зелёной энергии и общего ресурсосбережения. Его экономию нельзя прибавлять к результату смены полива.","en":"Separately from the irrigation switch, consider the green-energy and general resource-saving scenario. Do not add its savings to the irrigation outcome."}[lang],
                "evidence":{"kk":f"Ағымдағы параметрлерде маусымдық әлеуетті үнем шамамен {econ['total_saving_kzt']:,.0f} тг: электр энергиясынан {econ.get('energy_saving_kzt',0):,.0f} тг және судан {econ.get('water_saving_kzt',0):,.0f} тг.","ru":f"При текущих параметрах потенциальная сезонная экономия составляет около {econ['total_saving_kzt']:,.0f} тг: {econ.get('energy_saving_kzt',0):,.0f} тг по электроэнергии и {econ.get('water_saving_kzt',0):,.0f} тг по воде.","en":f"Under the current inputs, potential seasonal savings are about {econ['total_saving_kzt']:,.0f} {UNITS['currency']}: {econ.get('energy_saving_kzt',0):,.0f} {UNITS['currency']} from electricity and {econ.get('water_saving_kzt',0):,.0f} {UNITS['currency']} from water."}[lang],
                "effect":{"kk":f"Электр энергиясынан CO₂ төмендеуі шамамен {econ.get('co2_reduction_kg',0)/1000:.2f} т CO₂e және су үнемі {econ.get('water_saving_m3',0):,.0f} {UNITS['m3']} болуы мүмкін. Бұл сценарийлік бағалау, нақты инвестициялық шешім алдында тарифтер мен жабдық құнын нақтылау керек.","ru":f"Потенциальное снижение выбросов от электроэнергии - около {econ.get('co2_reduction_kg',0)/1000:.2f} т CO₂e, экономия воды - {econ.get('water_saving_m3',0):,.0f} {UNITS['m3']}. Это сценарная оценка, поэтому перед инвестиционным решением следует уточнить тарифы и стоимость оборудования.","en":f"Potential electricity-related reduction is about {econ.get('co2_reduction_kg',0)/1000:.2f} t CO₂e and water saving {econ.get('water_saving_m3',0):,.0f} m³. This is a scenario estimate, so tariffs and equipment costs should be verified before investment."}[lang],
                "evidence_label":{"kk":"Сандық негіздеме","ru":"Количественное основание","en":"Quantitative evidence"}[lang],
                "effect_label":{"kk":"Күтілетін әсер","ru":"Ожидаемый эффект","en":"Expected effect"}[lang],
            })
        if "_irrigation_recommendation" in locals() and irrigation_compare_enabled:
            # In a focused irrigation report generic crop/water observations can
            # contradict the district-specific irrigation water balance.
            report_payload["recommendations"] = [
                _irrigation_recommendation,
                *[r for r in report_payload["recommendations"]
                  if r.get("title") == {"kk":"Экономикалық және климаттық басымдық", "ru":"Экономико-климатический приоритет", "en":"Economic and climate priority"}[lang]]
            ]
        if "econ" in locals() and _grid_known and econ.get('total_saving_kzt') is not None:
            cats=[]; vals=[]
            if econ.get("energy_saving_kzt") is not None:
                cats.append({"kk":"Жасыл энергия","ru":"Зеленая энергия","en":"Green energy"}[lang]); vals.append(float(econ.get("energy_saving_kzt",0)))
            if econ.get("water_saving_kzt") is not None:
                cats.append({"kk":"Су үнемдеу","ru":"Экономия воды","en":"Water saving"}[lang]); vals.append(float(econ.get("water_saving_kzt",0)))
            if cats and any(v != 0 for v in vals):
                report_payload["chart"]={"title":{"kk":"Маусымдық үнем құрылымы","ru":"Структура потенциальной сезонной экономии","en":"Potential seasonal savings structure"}[lang],"section_title":{"kk":"Экономикалық әсердің құрылымы","ru":"Структура экономического эффекта","en":"Economic effect structure"}[lang],"categories":cats,"values":vals,"value_label":UNITS["currency"],"axis_label":UNITS["currency"]}
    elif mode_key == "mode2":
        if "scenario" in locals() and scenario is not None:
            report_payload["summary"] = [
                {"label":{"kk":"QŪNAR бағасы","ru":"Оценка QŪNAR","en":"QŪNAR score"}[lang],"value":f"{float(scenario['QUNAR_score_0_100']):.1f}/100"},
                {"label":{"kk":"Климат","ru":"Климат","en":"Climate"}[lang],"value":f"{float(scenario['Climate_score_0_100']):.1f}/100"},
                {"label":{"kk":"Ресурс тиімділігі","ru":"Ресурсоэффективность","en":"Resource efficiency"}[lang],"value":f"{float(scenario['Resource_efficiency_0_100']):.1f}/100"},
                {"label":{"kk":"Бағалау сенімділігі","ru":"Уверенность в оценке","en":"Assessment confidence"}[lang],"value":f"{float(scenario['Data_reliability_0_100']):.1f}/100"},
            ]
            if "factors" in locals(): report_payload["recommendations"] = structured_recommendations(list(factors), [], lang)
            report_payload["chart"]={
                "title":{"kk":"Дақылдың төрт өлшем бойынша бағасы","ru":"Оценка культуры по четырем измерениям","en":"Crop score across four dimensions"}[lang],
                "section_title":{"kk":"Дақыл профилі","ru":"Профиль культуры","en":"Crop profile"}[lang],
                "categories":[{"kk":"Жалпы баға","ru":"Общий балл","en":"Overall"}[lang],{"kk":"Климат","ru":"Климат","en":"Climate"}[lang],{"kk":"Ресурс","ru":"Ресурсы","en":"Resources"}[lang],{"kk":"Дерек","ru":"Уверенность в оценке","en":"Reliability"}[lang]],
                "values":[float(scenario['QUNAR_score_0_100']),float(scenario['Climate_score_0_100']),float(scenario['Resource_efficiency_0_100']),float(scenario['Data_reliability_0_100'])],
                "value_label":"0-100","axis_label":"0-100"
            }
        elif "ml_pred" in locals() and ml_pred is not None:
            report_payload["summary"] = [{"label":{"ru":"Расчётный ориентир урожайности","kk":"Өнімділік бағдары","en":"Reference yield estimate"}[lang],
                "value":f"{ml_pred:.1f} {UNITS['centner_ha']}", "note":_mode2_choice.disclaimer}]
        if "_mode2_choice" in locals():
            report_payload['summary'].extend([
                {'label':{'ru':'Метод оценки урожайности','kk':'Өнімділікті бағалау әдісі','en':'Yield method'}[lang],
                  'value':method_label(_mode2_choice.active_method,lang),'note':method_caveat(_mode2_choice,lang)},
                {'label':{'ru':'Оценка Random Forest, ц/га (отдельно)','kk':'Random Forest бағасы, ц/га','en':'Separate Random Forest estimate, c/ha'}[lang],
                  'value':f'{_mode2_rf_pred:.2f}', 'note':'Research ML benchmark; validation diagnostics below'}])
    elif mode_key == "mode3" and "ranking" in locals():
        report_payload["table"] = ranking[keep].to_dict(orient="records")
        top_row = ranking.iloc[0]
        top_name = str(top_row.iloc[1])
        top_score = float(top_row[{'kk':'QŪNAR жалпы бағасы','ru':'Общий балл QŪNAR','en':'QŪNAR overall score'}[lang]])
        report_payload["recommendations"] = [{
            "title":{"kk":"Негізгі таңдау","ru":"Приоритетный выбор","en":"Priority choice"}[lang],
            "text":{"kk":f"{top_name} ағымдағы критерийлер бойынша бірінші орында. Оны автоматты шешім емес, бастапқы басым нұсқа ретінде қарастырыңыз.","ru":f"{top_name} занимает первое место по текущему набору критериев. Рассматривайте его как приоритетный вариант для дальнейшей проверки, а не как автоматическое решение.","en":f"{top_name} ranks first under the current criteria. Treat it as the priority option for further verification, not an automatic decision."}[lang],
            "evidence":{"kk":f"QŪNAR жалпы бағасы {top_score:.1f}/100; рейтинг климатты, су тиімділігін және дерек сенімділігін бірге салыстырады.","ru":f"Общий балл QŪNAR {top_score:.1f}/100; рейтинг учитывает климат, водную эффективность и надежность исходных данных, но не подтверждает экономическую маржу.","en":f"QŪNAR overall score is {top_score:.1f}/100; the ranking combines climate, water efficiency and evidence reliability."}[lang],
            "effect":{"kk":"Келесі қадам - топ-3 нұсқаны су қолжетімділігі, технология және нарықтық жағдай бойынша салыстыру.","ru":"Следующий шаг - сопоставить три лучших варианта по доступности воды, технологии выращивания и рыночным условиям.","en":"Next, compare the top three options against water availability, production technology and market conditions."}[lang],
            "evidence_label":{"kk":"Негіздеме","ru":"Основание","en":"Evidence"}[lang],
            "effect_label":{"kk":"Келесі қадам","ru":"Следующий шаг","en":"Next step"}[lang],
        }]
        score_col={'kk':'QŪNAR жалпы бағасы','ru':'Общий балл QŪNAR','en':'QŪNAR overall score'}[lang]
        crop_col={'kk':'Дақыл','ru':'Культура','en':'Crop'}[lang]
        top5=ranking.head(5)
        report_payload["chart"]={"title":{"kk":"QŪNAR бойынша үздік 5 дақыл","ru":"5 лучших культур по QŪNAR","en":"QŪNAR top 5 crops"}[lang],"section_title":{"kk":"Салыстырмалы рейтинг","ru":"Сравнительный рейтинг","en":"Comparative ranking"}[lang],"categories":top5[crop_col].astype(str).tolist(),"values":pd.to_numeric(top5[score_col],errors='coerce').fillna(0).astype(float).tolist(),"value_label":"0-100","axis_label":"0-100"}
    elif mode_key == "mode4" and "opt" in locals():
        # Reproducibility: the chosen objective, weights, crop cap and scenario
        # inputs must travel with the PDF/Word/Excel instead of relying on memory.
        _opt_names = {
            'ru': ('Приоритет ресурсно-климатической оценки', 'Режим экономической цели', 'Вес экономического критерия, %', 'Максимальная доля культуры, %', 'Число культур', 'Изменение доступной воды, %'),
            'kk': ('Ресурс-климаттық басымдық', 'Экономикалық мақсат режимі', 'Экономикалық критерий салмағы, %', 'Дақыл үлесінің шегі, %', 'Дақыл саны', 'Қолжетімді судың өзгерісі, %'),
            'en': ('Resource-climate priority', 'Economic objective mode', 'Economic objective weight, %', 'Maximum crop share, %', 'Number of crops', 'Available-water scenario change, %'),
        }[lang]
        _profile_label = {
            'balanced': {'kk':'Теңгерімді','ru':'Сбалансированный','en':'Balanced'},
            'climate': {'kk':'Климаттық тұрақтылық','ru':'Климатическая устойчивость','en':'Climate resilience'},
            'resource': {'kk':'Ресурс үнемдеу','ru':'Ресурсосбережение','en':'Resource saving'},
            'survey_proxy': {'kk':'Сауалнама сценарийі (эксперимент)','ru':'Опросный сценарий (эксперимент)','en':'Survey sensitivity (experimental)'},
            'custom': {'kk':'Жеке салмақтар','ru':'Пользовательские веса','en':'Custom weights'},
        }[optimization_profile][lang]
        _objective_label = {
            'resource': {'kk':'Ресурс-климаттық тиімділік','ru':'Ресурсно-климатическая эффективность','en':'Resource-climate efficiency'},
            'balanced': {'kk':'Теңгерімді: ресурс + экономика','ru':'Сбалансированный: ресурсы + экономика','en':'Balanced: resources + economics'},
            'economic': {'kk':'Экономикалық нәтиже басымдығы','ru':'Приоритет экономического результата','en':'Economic-return priority'},
            'sustainable': {'kk':'Тұрақты ымыра','ru':'Устойчивый компромисс','en':'Sustainable compromise'},
        }[optimization_objective_mode][lang]
        _params = [_profile_label, _objective_label,
                   f'{optimization_economic_weight*100:.0f}' if optimization_use_economics else '0',
                   f'{optimization_max_share*100:.1f}',str(optimization_n_crops),f'{optimization_water_budget_change_pct:.1f}']
        report_payload['inputs'].extend([[name, val, t['source_user']] for name, val in zip(_opt_names, _params)])
        if optimization_profile == 'survey_proxy':
            report_payload['inputs'].append([
                {'kk':'Климат/су салмағы','ru':'Веса климат/вода','en':'Climate/water weights'}[lang],
                f"{float(opt.get('climate_weight', 93/213)):.5f}/{float(opt.get('water_weight', 120/213)):.5f}",
                {'kk':'2026 сауалнама Q3/Q7, 208 жауап; әртүрлі сұрақтар бойынша эвристикалық сценарий',
                 'ru':'Опрос 2026, Q3/Q7, 208 ответов; эвристика по разным вопросам, не калибровка',
                 'en':'2026 survey, Q3/Q7, 208 responses; cross-question exploratory proxy, not calibrated'}[lang]
            ])
        if optimization_profile == 'custom':
            report_payload['inputs'].append([{'kk':'Климат/су салмағы','ru':'Веса климат/вода','en':'Climate/water weights'}[lang],
                                            f'{optimization_custom_climate_weight:.3f}/{1.0-optimization_custom_climate_weight:.3f}',
                                            'User-defined, not survey-calibrated'])
        report_payload['inputs'].extend([
            [{'kk':'Температура өзгерісі, °C','ru':'Изменение температуры, °C','en':'Temperature change, °C'}[lang], f'{optimization_temp_delta_c:.1f}', t['source_user']],
            [{'kk':'Жауын-шашын өзгерісі, %','ru':'Изменение осадков, %','en':'Precipitation change, %'}[lang], f'{optimization_precip_change_pct:.1f}', t['source_user']],
        ])
        report_payload['inputs'].append([
            {'ru':'Проверка водного ограничения','kk':'Су лимитін тексеру','en':'Water constraint verification'}[lang],
            {'ru':'Проверено' if opt.get('water_feasible') is True else 'Не выполнено: лимит не введён' if opt.get('water_feasible') is None else 'Не соблюдено',
             'kk':'Тексерілді' if opt.get('water_feasible') is True else 'Тексерілмеді: су лимиті жоқ' if opt.get('water_feasible') is None else 'Орындалмады',
             'en':'Verified' if opt.get('water_feasible') is True else 'Not checked: budget not entered' if opt.get('water_feasible') is None else 'Not satisfied'}[lang],
            {'ru':'Ограничение оптимизатора','kk':'Оңтайландырғыш шектеуі','en':'Optimizer constraint'}[lang],
        ])
        if optimization_use_economics:
            report_payload['inputs'].append([
                {'ru':'Маржа по культурам','kk':'Дақылдар маржасы','en':'Crop contribution margins'}[lang],
                '; '.join(f'{extended_crop_label(str(_k),lang)}: {_v:,.0f} ' + {'ru':'тг/га','kk':'тг/га','en':'KZT/ha'}[lang] for _k,_v in optimization_economic_margins.items()) or {'ru':'Не введена','kk':'Енгізілмеген','en':'Not supplied'}[lang],
                {'ru':'Сценарный ввод пользователя','kk':'Пайдаланушы сценарийі','en':'User scenario inputs'}[lang]
            ])
        if optimization_baseline_shares:
            report_payload['inputs'].append([
                {'ru':'Текущая структура посевов, %','kk':'Ағымдағы егіс құрылымы, %','en':'Baseline crop shares, %'}[lang],
                '; '.join(f'{extended_crop_label(str(_k),lang)}: {_v:.1f}%' for _k,_v in optimization_baseline_shares.items()),
                t['source_user']
            ])
        report_payload['table'] = out.to_dict(orient="records") if 'out' in locals() and not alloc.empty else []
        if 'out' in locals() and not alloc.empty and opt.get('water_feasible') is not False:
            report_payload["summary"] = [
                {"label":{"kk":"Құрылымның QŪNAR бағасы","ru":"Оценка структуры QŪNAR","en":"Structure QŪNAR score"}[lang],"value":f"{opt['weighted_qunar']:.1f}/100"},
                {"label":{"kk":"Климаттық тұрақтылық","ru":"Климатическая устойчивость","en":"Climate resilience"}[lang],"value":f"{opt['weighted_climate']:.1f}/100"},
                {"label":{"kk":"Ресурс тиімділігі","ru":"Ресурсоэффективность","en":"Resource efficiency"}[lang],"value":f"{opt['weighted_resource']:.1f}/100"},
                {"label":{"kk":"Бағалау сенімділігі","ru":"Уверенность в оценке","en":"Assessment confidence"}[lang],"value":f"{opt['weighted_reliability']:.1f}/100"},
                {"label":{"kk":"Есептік су қажеттілігі","ru":"Расчетная потребность в воде","en":"Modelled water demand"}[lang],"value":f"{opt['modelled_total_water_m3']:,.0f} {UNITS['m3']}"},
            ]
            if optimization_profile in ('survey_proxy','custom'):
                report_payload['summary'].append({
                    'label':{'kk':'Таңдалған салмақтар бойынша балл','ru':'Балл выбранного профиля','en':'Score under selected weights'}[lang],
                    'value':f"{opt['weighted_profile_score']:.1f}/100"
                })
            _top_ix = pd.to_numeric(out.iloc[:,1], errors='coerce').idxmax()
            first_crop=str(out.loc[_top_ix, out.columns[0]]); first_share=float(out.loc[_top_ix, out.columns[1]])
            _water_provisional = opt.get('water_feasible') is None
            if _water_provisional:
                report_payload['summary'].append({
                    'label': {'ru':'Проверка водного лимита','kk':'Су лимитін тексеру','en':'Water-budget verification'}[lang],
                    'value': {'ru':'Не выполнена: лимит воды не введён. Структура предварительная.','kk':'Орындалмады: су лимиті енгізілмеген. Құрылым алдын ала берілген.','en':'Not performed: water budget missing. Allocation is provisional.'}[lang],
                })
            report_payload["recommendations"]=[{
                "title":{"kk":"Ұсынылатын құрылым","ru":"Рекомендуемая структура","en":"Recommended structure"}[lang],
                "text":{"kk":f"Егістік ауданды {len(out)} дақыл арасында бөлу ұсынылады; ең ірі үлес {first_crop} үшін {first_share:.1f}%.","ru":f"Рекомендуется распределить посевную площадь между {len(out)} культурами; наибольшая доля {first_share:.1f}% приходится на {first_crop}.","en":f"Allocate the cultivated area across {len(out)} crops; the largest share is {first_share:.1f}% for {first_crop}."}[lang],
                "evidence":{"kk":f"Құрылымның QŪNAR бағасы {opt['weighted_qunar']:.1f}/100, климаттық тұрақтылығы {opt['weighted_climate']:.1f}/100 және ресурс тиімділігі {opt['weighted_resource']:.1f}/100.","ru":f"Оценка структуры QŪNAR {opt['weighted_qunar']:.1f}/100, климатическая устойчивость {opt['weighted_climate']:.1f}/100 и ресурсоэффективность {opt['weighted_resource']:.1f}/100.","en":f"Structure QŪNAR score {opt['weighted_qunar']:.1f}/100, climate resilience {opt['weighted_climate']:.1f}/100 and resource efficiency {opt['weighted_resource']:.1f}/100."}[lang],
                "effect":{"kk":"Бұл әртараптандыру бір дақылға тәуелділікті азайтып, климат, су жүктемесі және дерек сенімділігі арасындағы теңгерімді сақтауға бағытталған.","ru":"Такая диверсификация направлена на снижение зависимости от одной культуры и сохранение баланса между климатической устойчивостью, водной нагрузкой и надежностью данных.","en":"This diversification is intended to reduce single-crop dependence while balancing climate resilience, water demand and evidence reliability."}[lang],
                "evidence_label":{"kk":"Негіздеме","ru":"Основание","en":"Evidence"}[lang],
                "effect_label":{"kk":"Күтілетін әсер","ru":"Ожидаемый эффект","en":"Expected effect"}[lang],
            }]
            if _water_provisional:
                report_payload['recommendations'][0]['title'] = {'ru':'Предварительная структура, водный лимит не проверен','kk':'Алдын ала құрылым, су лимиті тексерілмеді','en':'Provisional allocation, water budget unverified'}[lang]
                report_payload['recommendations'][0]['text'] = {'ru':'Рассчитаны только доли и модельное водопотребление. До подтверждения доступной воды применять структуру нельзя.','kk':'Тек үлестер мен есептік су қажеттілігі анықталды. Су көлемі расталғанша құрылымды енгізуге болмайды.','en':'Only shares and modelled water demand are estimated. Do not implement before checking water availability.'}[lang]
            # Actionable, quantified recommendations: water feasibility status must be explicit.
            _plan_lines = []
            for _r in alloc.itertuples(index=False):
                _name = extended_crop_label(str(getattr(_r, 'product', '')), lang)
                _area = float(getattr(_r, 'area_ha'))
                _water = float(getattr(_r, 'modelled_water_m3'))
                _plan_lines.append({
                    'ru':f'{_name}: {_area:.1f} га, {_water:,.0f} {UNITS["m3"]} воды',
                    'kk':f'{_name}: {_area:.1f} га, {_water:,.0f} {UNITS["m3"]} су',
                    'en':f'{_name}: {_area:.1f} ha, {_water:,.0f} m³ water',
                }[lang])
            _gain = opt.get('economic_gain_kzt')
            _margin_after = opt.get('optimized_contribution_margin_kzt')
            _source_remark = {
                'ru': ('Расчётная маржа является сценарием; введённые пользователем затраты и цены требуют проверки.' if _margin_after is not None else 'Структура рассчитана по ресурсно-климатическим критериям. Экономический эффект не определён: данные о марже культур отсутствуют.'),
                'kk': ('Есептік маржа - сценарий; енгізілген баға мен шығындар тексерілуі керек.' if _margin_after is not None else 'Құрылым ресурс-климат өлшемдері бойынша есептелді. Дақыл маржасы жоқ болғандықтан экономикалық әсер анықталмады.'),
                'en': ('Contribution margin is a scenario; entered prices and costs require confirmation.' if _margin_after is not None else 'Allocation uses climate-resource criteria. No economic effect can be claimed without crop margins.')
            }[lang]
            report_payload['recommendations'].append({
                'title': ({'ru':'Предварительные расчётные доли (без водного лимита)','kk':'Алдын ала үлестер (су лимиті жоқ)','en':'Provisional allocation (no water budget)'} if _water_provisional else {'ru':'Практический план посевов','kk':'Егіс бойынша нақты жоспар','en':'Quantified crop allocation'})[lang],
                'text': '; '.join(_plan_lines),
                'evidence': {
                    'ru': (f"Водопотребление: {opt['modelled_total_water_m3']:,.0f} из {opt['available_water_m3']:,.0f} {UNITS['m3']}. " if not _water_provisional else f"Потребность в воде: {opt['modelled_total_water_m3']:,.0f} {UNITS['m3']}; лимит не введён, обеспеченность не проверена. ")
                          + (f"Сценарная маржа: {_margin_after:,.0f} тг. " if _margin_after is not None else '')
                          + (f"Изменение относительно исходной структуры: {_gain:,.0f} тг." if _gain is not None else ''),
                    'kk': (f"Су тұтынуы: {opt['modelled_total_water_m3']:,.0f} / {opt['available_water_m3']:,.0f} {UNITS['m3']}. " if not _water_provisional else f"Су қажеттілігі: {opt['modelled_total_water_m3']:,.0f} {UNITS['m3']}; қолжетімді су көлемі тексерілмеді. ")
                          + (f"Сценарийлік маржа: {_margin_after:,.0f} тг. " if _margin_after is not None else '')
                          + (f"Бастапқы құрылыммен салыстырғандағы өзгеріс: {_gain:,.0f} тг." if _gain is not None else ''),
                    'en': (f"Water demand: {opt['modelled_total_water_m3']:,.0f} / {opt['available_water_m3']:,.0f} m³. " if not _water_provisional else f"Modelled water demand: {opt['modelled_total_water_m3']:,.0f} m³; budget not entered and feasibility unverified. ")
                          + (f"Scenario margin: {_margin_after:,.0f} {UNITS['currency']}. " if _margin_after is not None else '')
                          + (f"Change relative to baseline: {_gain:,.0f} {UNITS['currency']}." if _gain is not None else ''),
                }[lang],
                'effect': _source_remark,
                'evidence_label': {'ru':'Основание','kk':'Негіздеме','en':'Evidence'}[lang],
                'effect_label': {'ru':'Ожидаемый эффект','kk':'Күтілетін әсер','en':'Expected effect'}[lang],
            })
            if _margin_after is not None:
                report_payload['summary'].append({'label': {'ru':'Ограничение экономической оценки','kk':'Экономикалық бағалаудың шектеуі','en':'Economic estimate limitation'}[lang],
                    'value': {'ru':'Маржа является приблизительной сценарной оценкой; зависит от фактических производственных затрат, урожайности, цены и технологии полива хозяйства. Не является подтверждённой прибылью.', 'kk':'Маржа болжамды сценарийлік баға; ол шаруашылықтың нақты шығындарына, өнімділігіне, бағасына және суару тәсіліне тәуелді. Расталған пайда емес.', 'en':'Indicative scenario margin depends on actual farm production costs, yield, prices and irrigation method. It is not verified profit.'}[lang]})
                report_payload['summary'].append({'label': {'ru':'Потенциальная сценарная маржа, тг','kk':'Сценарийлік ықтимал маржа, тг','en':'Potential scenario margin, KZT'}[lang],
                                                  'value':f"{_margin_after:,.0f}"})
            # Transparent before/after indicators. Unknown energy and GHG effects
            # must never be silently displayed as zero reductions.
            _bi = opt.get('baseline_contribution_margin_kzt')
            _bp = opt.get('baseline_water_m3')
            _wa = opt.get('modelled_total_water_m3')
            _metrics = []
            if _bi is not None and _margin_after is not None:
                _metrics += [
                    ('Baseline contribution margin, KZT', f'{_bi:,.0f}'),
                    ('Optimized contribution margin, KZT', f'{_margin_after:,.0f}'),
                    ('Contribution margin increase, %', f"{float(opt.get('economic_gain_pct') or 0):+.1f}%"),
                ]
            if _bp is not None and _wa is not None:
                _metrics += [
                    ('Baseline crop water demand, m³', f'{_bp:,.0f}'),
                    ('Optimized crop water demand, m³', f'{_wa:,.0f}'),
                    ('Water demand change, m³', f"{float(opt.get('water_change_m3') or 0):+,.0f}"),
                    ('Water demand change, %', f"{float(opt.get('water_change_pct') or 0):+.1f}%"),
                ]
            _sust = opt.get('sustainable_comparison') or {}
            if _sust and _sust.get('baseline_partial_ghg_kg_co2e') is not None and _sust.get('optimized_partial_ghg_kg_co2e') is not None:
                _gb = float(_sust['baseline_partial_ghg_kg_co2e'])
                _ga = float(_sust['optimized_partial_ghg_kg_co2e'])
                _metrics += [('Baseline partial GHG, kg CO₂e', f'{_gb:,.1f}'),
                             ('Optimized partial GHG, kg CO₂e', f'{_ga:,.1f}'),
                             ('Partial GHG change, kg CO₂e', f'{_ga-_gb:+,.1f}')]
            else:
                _metrics.append(('Environmental footprint comparison', 'Not quantified: matched crop-level emission factors required'))
            _metrics.append(('Energy consumption comparison', 'Not quantified: matched crop-level kWh data required'))
            if lang == 'en':
                report_payload['summary'].extend({'label':k, 'value':v} for k,v in _metrics)
            else:
                _translations = {
                    'Baseline contribution margin, KZT': ('Исходная маржа, тг','Бастапқы маржа, тг'),
                    'Optimized contribution margin, KZT': ('Маржа после оптимизации, тг','Оңтайландырудан кейінгі маржа, тг'),
                    'Contribution margin increase, %': ('Прирост маржи, %','Маржа өсімі, %'),
                    'Baseline crop water demand, m³': ('Исходная потребность в воде, м³','Бастапқы су қажеттілігі, м³'),
                    'Optimized crop water demand, m³': ('Потребность в воде после оптимизации, м³','Оңтайландырудан кейінгі су қажеттілігі, м³'),
                    'Water demand change, m³': ('Изменение водопотребления, м³','Су тұтыну өзгерісі, м³'),
                    'Water demand change, %': ('Изменение водопотребления, %','Су тұтыну өзгерісі, %'),
                    'Baseline partial GHG, kg CO₂e': ('Исходные частичные выбросы, кг CO₂e','Бастапқы ішінара шығарындылар, кг CO₂e'),
                    'Optimized partial GHG, kg CO₂e': ('Частичные выбросы после оптимизации, кг CO₂e','Оңтайландырудан кейінгі ішінара шығарындылар, кг CO₂e'),
                    'Partial GHG change, kg CO₂e': ('Изменение частичных выбросов, кг CO₂e','Ішінара шығарындылар өзгерісі, кг CO₂e'),
                    'Environmental footprint comparison': ('Сравнение экологического следа','Экологиялық ізді салыстыру'),
                    'Energy consumption comparison': ('Сравнение энергопотребления','Энергия тұтынуды салыстыру'),
                }
                _unknown = ('Не рассчитано: нужны сопоставимые покультурные исходные данные','Есептелмеген: салыстырмалы дақылдық деректер қажет')
                report_payload['summary'].extend({'label':_translations.get(k,(k,k))[0 if lang=='ru' else 1],
                    'value':(_unknown[0 if lang=='ru' else 1] if v.startswith('Not quantified:') else v)} for k,v in _metrics)
            if opt.get('baseline_status') not in ('not_entered', 'valid_comparison'):
                _bl_reason = {
                    'shares_do_not_sum_to_100': {'ru':'Сумма текущих долей не равна 100%.','kk':'Бастапқы үлестердің қосындысы 100% емес.','en':'Baseline shares do not total 100%.'},
                    'unrecognized_baseline_crops': {'ru':'Есть нераспознанные культуры в исходной структуре.','kk':'Бастапқы құрылымда танылмаған дақылдар бар.','en':'Baseline contains unknown crops.'},
                    'baseline_exceeds_water_limit': {'ru':'Исходная структура превышает доступную воду.','kk':'Бастапқы құрылым су лимитінен асады.','en':'Baseline exceeds water budget.'},
                    'water_budget_not_entered': {'ru':'Водный лимит не введён.','kk':'Су лимиті енгізілмеген.','en':'Water budget not entered.'},
                    'missing_baseline_crop_margins': {'ru':'Не для всех исходных культур введена маржа.','kk':'Бастапқы дақылдардың маржасы толық енгізілмеген.','en':'Baseline crop margins are incomplete.'},
                }.get(opt.get('baseline_status'), {}).get(lang)
                if _bl_reason:
                    report_payload['summary'].append({'label': {'ru':'Сравнение «до/после»','kk':'«Дейін/кейін» салыстыру','en':'Before/after comparison'}[lang], 'value': _bl_reason + ' ' + {'ru':'Прирост маржи не рассчитывается.','kk':'Маржа өзгерісі есептелмейді.','en':'No margin gain is reported.'}[lang]})
            if _gain is not None:
                report_payload['summary'].append({'label': {'ru':'Сценарное изменение маржи, тг','kk':'Сценарийлік маржаның өзгерісі, тг','en':'Scenario margin change, KZT'}[lang],
                                                  'value':f"{_gain:+,.0f}"})
            report_payload["chart"]={"title":{"kk":"Ұсынылатын егіс құрылымы","ru":"Рекомендуемая структура посевов","en":"Recommended cropping structure"}[lang],"section_title":{"kk":"Ауданның бөлінуі","ru":"Распределение площади","en":"Land allocation"}[lang],"categories":out.iloc[:,0].astype(str).tolist(),"values":pd.to_numeric(out.iloc[:,1],errors='coerce').fillna(0).astype(float).tolist(),"value_label":"%","axis_label":"%"}

        else:
            report_payload['table'] = []
            report_payload['chart'] = None
            _available = float(opt.get('available_water_m3') or _scenario_available_water or 0.0)
            _candidate_water = opt.get('rejected_water_m3')
            _candidate_water = float(_candidate_water) if _candidate_water is not None else None
            _deficit = (max(0.0, _candidate_water - _available) if _candidate_water is not None and _available > 0 else None)
            report_payload['summary'] = [{
                'label': {'ru':'Статус оптимизации','kk':'Оңтайландыру мәртебесі','en':'Optimization status'}[lang],
                'value': {'ru':'Допустимая структура не найдена','kk':'Рұқсат етілген құрылым табылмады','en':'No feasible allocation found'}[lang],
            }]
            if _available > 0:
                report_payload['summary'].append({
                    'label': {'ru':'Доступный водный лимит','kk':'Қолжетімді су лимиті','en':'Available water budget'}[lang],
                    'value': f'{_available:,.0f} {UNITS["m3"]}',
                })
            if _candidate_water is not None:
                report_payload['summary'].append({
                    'label': {'ru':'Потребность отклонённого варианта','kk':'Қабылданбаған нұсқаның су қажеттілігі','en':'Water required by rejected allocation'}[lang],
                    'value': f'{_candidate_water:,.0f} {UNITS["m3"]}',
                })
            if _deficit is not None and _deficit > 0:
                report_payload['summary'].append({
                    'label': {'ru':'Превышение водного лимита','kk':'Су лимитінің артуы','en':'Water-budget excess'}[lang],
                    'value': f'{_deficit:,.0f} {UNITS["m3"]}',
                })
            if opt.get('solver_status') == 'infeasible_crop_count_or_cap' and opt.get('economic_objective_active') and int(opt.get('eligible_crop_count', 0)) < optimization_n_crops:
                report_payload['summary'].append({
                    'label': {'ru':'Недостаточно экономических данных','kk':'Экономикалық деректер жеткіліксіз','en':'Insufficient crop margin inputs'}[lang],
                    'value': {'ru':f'Введена маржа для {opt.get("eligible_crop_count",0)} культур из {optimization_n_crops}.',
                              'kk':f'{optimization_n_crops} дақылдың {opt.get("eligible_crop_count",0)} үшін маржа енгізілген.',
                              'en':f'Margins provided for {opt.get("eligible_crop_count",0)} of {optimization_n_crops} requested crops.'}[lang],
                })
            report_payload['recommendations'] = [{
                'title': {'ru':'План отклонён','kk':'Жоспар қабылданбады','en':'Allocation rejected'}[lang],
                'text': {
                    'ru':'При текущих ограничениях допустимая структура не найдена. Распределение площадей не рекомендуется к внедрению.',
                    'kk':'Ағымдағы шектеулермен рұқсат етілген құрылым табылмады. Егіс аудандарын бөлу енгізуге ұсынылмайды.',
                    'en':'No allocation satisfies the current constraints. Do not implement this crop plan.',
                }[lang],
                'evidence': ({
                    'ru':f'Водный лимит {_available:,.0f} {UNITS["m3"]}; недопустимый кандидат требовал {_candidate_water:,.0f} {UNITS["m3"]}.' if _candidate_water is not None else f'Водный лимит {_available:,.0f} {UNITS["m3"]}. Решатель: {localized_solver_status(opt.get("solver_status","unknown"), lang)}.',
                    'kk':f'Су лимиті {_available:,.0f} {UNITS["m3"]}; қабылданбаған нұсқаға {_candidate_water:,.0f} {UNITS["m3"]} қажет.' if _candidate_water is not None else f'Су лимиті {_available:,.0f} {UNITS["m3"]}. Есептеу мәртебесі: {localized_solver_status(opt.get("solver_status","unknown"), lang)}.',
                    'en':f'Water budget {_available:,.0f} m³; rejected candidate required {_candidate_water:,.0f} m³.' if _candidate_water is not None else f'Water budget {_available:,.0f} m³. Solver: {localized_solver_status(opt.get("solver_status","unknown"), lang)}.',
                }[lang]),
                'effect': {
                    'ru':'Сценарное изменение маржи не рассчитано: допустимое решение не найдено при заданных условиях.',
                    'kk':'Сценарийлік маржа өзгерісі есептелмеді: берілген шарттарда рұқсат етілген шешім табылмады.',
                    'en':'No scenario margin change is reported because no admissible allocation was found.',
                }[lang],
                'evidence_label': {'kk':'Негіздеме','ru':'Основание','en':'Evidence'}[lang],
                'effect_label': {'kk':'Салдары','ru':'Следствие','en':'Consequence'}[lang],
            }, {
                'title': {'ru':'Как получить допустимый вариант','kk':'Рұқсат етілген нұсқаға қол жеткізу','en':'How to obtain a feasible plan'}[lang],
                'text': {
                    'ru':'При неизменном лимите воды повторите расчёт с менее водоёмкими культурами и/или другой технологией полива; при необходимости проверьте сокращение площади и ограничения числа культур. Не увеличивайте доступную воду без документального основания.',
                    'kk':'Су лимиті өзгермесе, суды аз тұтынатын дақылдармен және/немесе басқа суару тәсілімен қайта есептеңіз; қажет болса егіс ауданын және дақыл санының шектеулерін тексеріңіз. Расталмаған су көлемін қоспаңыз.',
                    'en':'Re-run with less water-intensive crops and/or another irrigation method; review land area and crop-count constraints as needed. Do not increase the water budget without evidence.',
                }[lang],
                'evidence': {
                    'ru':'Каждую альтернативу необходимо проверить по площади, воде и экономическим затратам.',
                    'kk':'Әрбір баламаны жер, су және экономикалық шығын шектеулері бойынша тексеру қажет.',
                    'en':'Each alternative must be checked against land, water and economic constraints.',
                }[lang],
                'evidence_label': {'ru':'Основание','kk':'Негіздеме','en':'Evidence'}[lang],
            }]
    # Independent A8 scientific reference case. It is NOT linked to the current
    # user's farm input and never overwrites any user report or optimization.
    if mode_key == "mode4":
        with st.expander({
            'ru': 'Научный пример A8: Мактаарал, 100 га (условные данные)',
            'kk': 'А8 ғылыми мысалы: Мақтаарал, 100 га (шартты деректер)',
            'en': 'A8 research example: Maktaaral, 100 ha (illustrative)',
        }[lang], expanded=False):
            st.caption({
                'ru': 'Отдельный пример на данных БНС и районной урожайности. Затраты, тарифы, лимит, технологические коэффициенты и исходная структура условные. Результаты НЕ относятся к вашему хозяйству.',
                'kk': 'БНС бағалары мен аудандық өнімділік негізіндегі бөлек мысал. Шығындар, тарифтер, су лимиті, технология коэффициенттері және бастапқы құрылым шартты. Нәтижелер СІЗДІҢ шаруашылығыңызға қатысты емес.',
                'en': 'Separate research case using BNS prices and district yield history. Costs, tariffs, water budget, technology and original crop areas are assumptions, NOT your farm inputs.',
            }[lang])
            if st.button({'ru':'Рассчитать A8','kk':'A8 есептеу','en':'Calculate A8'}[lang],
                         key='a8_reference_case_run'):
                try:
                    from core.a8_reproducible_case import calculate_case, load_case
                    st.session_state['a8_reference_case_result'] = calculate_case(load_case())
                except (ValueError, KeyError, OSError, ImportError) as _a8_err:
                    st.error(str(_a8_err))
            _a8_demo = st.session_state.get('a8_reference_case_result')
            if _a8_demo is not None:
                _a8_normal = _a8_demo['normal']; _a8_stress = _a8_demo['stress']
                _a8_labels = {
                    'ru':['Исходная структура','Оптимизация: обычные условия','Исходная структура: стресс (недопустима)','Оптимизация: стресс'],
                    'kk':['Бастапқы құрылым','Әдеттегі жағдайдағы оңтайландыру','Бастапқы құрылым: стресс (жарамсыз)','Стресс кезіндегі оңтайландыру'],
                    'en':['Baseline crop mix','Optimized: normal conditions','Baseline: stress (infeasible)','Optimized: stress'],
                }[lang]
                _a8_parts=[_a8_normal['baseline'], _a8_normal['optimized'],
                           _a8_stress['baseline_counterfactual'], _a8_stress['optimized']]
                st.dataframe(pd.DataFrame([{
                    {'ru':'Сценарий','kk':'Сценарий','en':'Scenario'}[lang]:label,
                    {'ru':'Вода, м³','kk':'Су, м³','en':'Water, m³'}[lang]:round(part['water_field_delivery_m3']),
                    {'ru':'Уложился в водный лимит','kk':'Су лимитіне сәйкес','en':'Water feasible'}[lang]:part['water_feasible'],
                    {'ru':'Электроэнергия, кВт·ч','kk':'Электр энергиясы, кВт·сағ','en':'Electricity, kWh'}[lang]:round(part['pump_energy_kwh']),
                    {'ru':'Маржа, тг','kk':'Маржа, тг','en':'Contribution margin, KZT'}[lang]:round(part['contribution_margin_kzt']),
                    {'ru':'Учтённые выбросы, кг CO₂e','kk':'Есептелген шығарындылар, кг CO₂e','en':'Partial GHG, kg CO₂e'}[lang]:round(part['partial_ghg_kg_co2e']),
                } for label, part in zip(_a8_labels,_a8_parts)]),hide_index=True)
                st.warning({
                    'ru':'При стрессе исходная структура нарушает водный лимит. Её маржу нельзя трактовать как допустимую альтернативу. CO₂e и вода — расчётные сценарии, не измеренная экономия.',
                    'kk':'Стресс кезінде бастапқы құрылым су шегінен асады. Оның маржасы жарамды балама емес. CO₂e және су көрсеткіштері - өлшенген үнем емес, сценарийлік есеп.',
                    'en':'Under stress the original crop mix exceeds its water budget. Its margin is not a feasible alternative. GHG and water changes are model scenarios, not measured savings.',
                }[lang])
                from core.a8_reproducible_case import report_markdown
                st.download_button('A8: result JSON',
                    data=json.dumps(_a8_demo,ensure_ascii=False,indent=2),
                    file_name='a8_maktaaral_case_results.json',mime='application/json',
                    key='a8_reference_case_json')
                st.download_button('A8: report Markdown',
                    data=report_markdown(_a8_demo),
                    file_name='a8_maktaaral_for_claude.md',mime='text/markdown',
                    key='a8_reference_case_markdown')
            _a8_research_tolerance=st.slider({'ru':'A8: допустимое снижение маржи для сценариев SSP, %',
                'kk':'A8: SSP маржасының рұқсат етілген төмендеуі, %',
                'en':'A8: maximum scenario contribution-margin decline, %'}[lang],
                min_value=0,max_value=25,value=5,step=1,key='a8_research_tolerance')
            if st.button({'ru':'Сверить A8: компромисс и SSP при единых коэффициентах',
                          'kk':'А8 тексеру: ымыра және SSP сценарийлері',
                          'en':'Cross-check A8: sustainable allocation and SSP using one input set'}[lang],
                         key='a8_full_crosscheck_run'):
                try:
                    from core.a8_crosscheck import generate_a8_crosscheck
                    st.session_state['a8_full_crosscheck_result']=generate_a8_crosscheck(margin_tolerance_pct=_a8_research_tolerance)
                except (ValueError,KeyError,OSError,ImportError,AssertionError) as _a8_check_err:
                    st.error(str(_a8_check_err))
            _cross_a8=st.session_state.get('a8_full_crosscheck_result')
            if _cross_a8 and _cross_a8.get('sustainable_margin_tolerance_pct')==_a8_research_tolerance:
                _a8_normal_ref=_cross_a8['ordinary_economic_optimum']['baseline']
                _a8_economic_ref=_cross_a8['ordinary_economic_optimum']['optimized']
                _a8_sust_ref=_cross_a8['sustainable_current']['optimized']
                _a8_stressed_ref=_cross_a8['stress']['optimized']
                _cross_a8_rows=[({'ru':'Исходная','kk':'Бастапқы','en':'Baseline'}[lang],_a8_normal_ref),
                     ({'ru':'Экономический оптимум','kk':'Экономикалық оңтайлы','en':'Economic optimum'}[lang],_a8_economic_ref),
                     ({'ru':'Устойчивый компромисс','kk':'Тұрақты ымыра','en':'Sustainable compromise'}[lang],_a8_sust_ref)]
                for _name,_scenario in _cross_a8['climate_scenarios'].items():
                    _cross_a8_rows.append((_name+' '+{'ru':'(пересчитано, приближение)','kk':'(қайта есептелген, жуық)','en':'(reoptimized proxy)'}[lang],
                        _scenario['reoptimized'].get('optimized')))
                    _cross_a8_rows.append((_name+' '+{'ru':'(лимит текущих выбросов)','kk':'(ағымдағы шығарындылар шегі)','en':'(present-day CO₂e cap)'}[lang],
                        _scenario['reoptimized_with_absolute_present_carbon_cap'].get('optimized')))
                _cross_a8_rows.append(({'ru':'Комбинированный стресс','kk':'Біріктірілген стресс','en':'Joint stress'}[lang],_a8_stressed_ref))
                st.dataframe(pd.DataFrame([{
                    {'ru':'Сценарий','kk':'Сценарий','en':'Scenario'}[lang]:_name,
                    {'ru':'Вода, м³','kk':'Су, м³','en':'Water, m³'}[lang]:round(_values['water_field_delivery_m3']) if _values else None,
                    {'ru':'Маржа, тг','kk':'Маржа, тг','en':'Margin, KZT'}[lang]:round(_values['contribution_margin_kzt']) if _values else None,
                    {'ru':'Учтённые выбросы, кг CO₂e','kk':'Есептелген шығарындылар, кг CO₂e','en':'Partial GHG, kg CO₂e'}[lang]:round(_values['partial_ghg_kg_co2e']) if _values else None,
                    {'ru':'Статус','kk':'Мәртебе','en':'Status'}[lang]:({'ru':'Расчётный сценарий','kk':'Есептік сценарий','en':'Scenario result'}[lang] if _values else {'ru':'Нет допустимого решения','kk':'Жарамды шешім жоқ','en':'No feasible allocation'}[lang]),
                } for _name,_values in _cross_a8_rows]),hide_index=True)
                st.caption({'ru':'SSP: только отношение температурного члена Харгривса (T+17,8). Пересчитаны насосная энергия, затраты и частичные выбросы; это НЕ FAO-56 и НЕ прогноз фактической урожайности.',
                            'kk':'SSP: Харгривс (T+17,8) температура мүшесінің сценарийі, толық FAO-56 емес; сорғы энергиясы, шығындар, шығарындылар қайта есептелді.',
                            'en':'SSP: Hargreaves (T+17.8) temperature-term proxy, NOT FAO-56. Pumping, variable costs and partial emissions recalculated; crop yields held constant.'}[lang])
                st.download_button('A8: full reproducible climate crosscheck JSON',
                    data=json.dumps(_cross_a8,ensure_ascii=False,indent=2),
                    file_name='a8_sustainable_ssp_crosscheck.json',mime='application/json',
                    key='a8_full_crosscheck_json')

    # Integrated what-if across water, electricity, partial CO2e and costs.
    # This scenario uses the same underlying inputs/period and is deliberately
    # separate from the constrained crop allocation unless user explicitly
    # changes and re-runs the optimizer.
    _integrated_fragment = None
    if _scenario_inputs_slot is not None:
        with _scenario_inputs_slot:
            _has_farm_subject = (mode_key == "mode1" and crop is not None) or (mode_key == "mode5" and livestock_heads > 0)
            _scenario_opted_in = st.checkbox({
                "ru":"Рассчитать дополнительный сценарий «до / после»",
                "kk":"Қосымша «дейін / кейін» сценарийін есептеу",
                "en":"Calculate optional before/after scenario"}[lang],
                value=False, key=f"qunar_integrated_optin_{mode_key}",
                help={"ru":"Необязательно. Включите, только если хотите сравнить две технологии для этого хозяйства. Результат не является подтверждённой фактической экономией.",
                      "kk":"Міндетті емес. Осы шаруашылық үшін екі технологияны салыстыру қажет болса ғана қосыңыз.",
                      "en":"Optional. Enable only when comparing two technologies for this farm; savings are not measured."}[lang],
                disabled=not _has_farm_subject)
            if not _has_farm_subject and _scenario_opted_in:
                _scenario_opted_in = False
            if _scenario_opted_in:
                st.markdown("#### " + {
                "ru":"Дополнительный сценарий «до / после» (параметры)",
                "kk":"«Дейін / кейін» қосымша сценарийі (параметрлер)",
                "en":"Optional before/after scenario (inputs)"}[lang])
                _integrated_fragment = render_integrated_scenario(
                    lang=lang, mode_key=mode_key, district=used_district,
                    crop=crop, area_ha=area_ha, irrigation_type=irrigation_type,
                    observed_water_m3=observed_water, observed_energy_kwh=observed_energy,
                    grid_factor=ef, water_tariff=water_tariff,
                    electricity_tariff=electricity_tariff,
                    expected_yield_c_ha=expected_yield_c_ha,
                    selling_price_kzt_t=selling_price_kzt_t,
                    other_cost_kzt_ha=variable_cost_kzt_ha,
                    livestock_heads=livestock_heads, livestock_species=livestock_species,
                    livestock_production_amount=livestock_production_amount,
                    livestock_production_kind=livestock_production_kind,
                    livestock_reference=locals().get('livestock'),
                    assessment_year=calculation_year,
                    main_pump_confirmed=(pumping_confirmed and pump_head_m is not None and pump_efficiency is not None),
                    main_pump_head_m=pump_head_m, main_pump_efficiency=pump_efficiency,
                    purchased_mechanized_water=(_tariff_water_ref == 'kazvodkhoz_irrigation_pumped_2026'),
                )
    if _integrated_fragment is not None:
        report_payload['summary'].extend(_integrated_fragment['summary'])
        report_payload['inputs'].extend(_integrated_fragment['inputs'])
        report_payload['recommendations'].append(_integrated_fragment['recommendation'])
    for _cross_row in _cross_module_summary_rows:
        if _cross_row not in report_payload['summary']:
            report_payload['summary'].append(_cross_row)
    st.session_state["last_report_payload"] = report_payload
    st.markdown('<div class="qunar-export"></div>', unsafe_allow_html=True)
    render_export_panel(report_payload, lang)

    _timings["Total rerun"] = time.perf_counter() - _run_started
    if user_level == "researcher":
        with st.expander({"kk":"Өнімділік диагностикасы","ru":"Диагностика производительности","en":"Performance diagnostics"}[lang]):
            perf_df = pd.DataFrame([{"Этап":k, "Секунды":round(v,3)} for k,v in sorted(_timings.items(), key=lambda x:-x[1])])
            st.dataframe(perf_df, use_container_width=True, hide_index=True)
            st.caption({"kk":"Бұл блок лагтың нақты қай кезеңде пайда болатынын анықтауға көмектеседі.","ru":"Этот блок показывает, какой этап реально занимает время, чтобы не оптимизировать приложение наугад.","en":"This shows which stage actually takes time, so performance work can target the real bottleneck."}[lang])

st.markdown('<div id="qunar-page-bottom"></div>', unsafe_allow_html=True)
st.divider()
st.caption(t["footer"])

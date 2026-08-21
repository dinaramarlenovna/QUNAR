
from datetime import date, datetime
import time
import html
import json
import hashlib
import streamlit as st
import pandas as pd

from core.config import (
    APP_NAME, APP_SUBTITLE, LANGUAGES, DISTRICT_ORDER, CROPS, TEXT,
    DISTRICT_LABELS, CROP_LABELS,
)
from core.data import load_centroids, district_climate, district_crop_context
from core.nasa import fetch_growing_season
from core.ml import predict_yield, rank_crops, validation_summary, validation_for_crop
from core.resources import calculate_resources
from core.water_norms import default_water_requirement, PUMPING_REFERENCE_KWH_PER_M3
from core.economics import DEFAULT_EF_KZ_KGCO2_PER_KWH, DEFAULT_ELECTRICITY_TARIFF_KZT_KWH, DEFAULT_IRRIGATION_WATER_TARIFF_KZT_M3, DEFAULT_GREEN_SHARE_TARGET, DEFAULT_WATER_SAVING_TARGET, economic_climate_effect, payback_years
from core.economic_feasibility import economic_feasibility
from core.uncertainty import support_score
from core.analysis_engine import build_analysis, build_recommendations
from core.wapor import seasonal_aeti, consumptive_water_metrics, WaPORError
from core.location import browser_geolocation, reverse_geocode
from core.admin_boundaries import detect_point, detect_polygon, boundary_geojson
from core.optimizer import optimize_structure
from core.clrem import check_crop_codes, label as extended_crop_label, method as crop_method, scenario_for_crop, observed_for_crop, observed_extra_for_district, decision_table
from core.reporting import build_excel_report, build_pdf_report, build_combined_excel_report, build_combined_pdf_report
from core.environment import environmental_diagnostics, diversification_metrics
from core.livestock import (
    SPECIES, SPECIES_LABELS, PRODUCT_TYPES, PRODUCT_LABELS, DEFAULT_PRODUCT,
    livestock_resource_metrics, district_livestock_profile, district_species_history,
    district_species_benchmark, regional_productivity_benchmarks,
)

st.set_page_config(page_title=APP_NAME, page_icon="🌱", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
:root { --qunar:#234f36; --qunar-soft:#f1f7f2; --text:#1f2923; --muted:#66736b; }
html, body, [class*="css"], .stApp, .stMarkdown, .stText, label, input, button {
  font-family: "Segoe UI", "Noto Sans", Arial, sans-serif !important;
}
html, body, [class*="css"] { font-size: 18px; color:var(--text); }
.stApp { background: #fbfcfa; }
.block-container { max-width: 1320px; padding-top: 1.35rem; padding-bottom: 3rem; }
section[data-testid="stSidebar"] { border-right: 1px solid #e4e9e4; }
section[data-testid="stSidebar"] * { font-size: 16.5px !important; line-height:1.45 !important; }
h1 { font-size: 2.35rem !important; line-height: 1.16 !important; font-weight:760 !important; }
h2 { font-size: 1.95rem !important; line-height: 1.2 !important; font-weight:740 !important; }
h3 { font-size: 1.62rem !important; line-height: 1.23 !important; font-weight:730 !important; margin-top:1.15rem !important; }
h4 { font-size: 1.30rem !important; line-height: 1.3 !important; font-weight:700 !important; }
p, li, label, .stMarkdown { font-size:18px; line-height: 1.68; }
small, .stCaption, [data-testid="stCaptionContainer"] { font-size:15.5px !important; line-height:1.5 !important; }
div[data-testid="stMetric"] { background: white; border: 1px solid #dfe7e1; border-radius: 15px; padding: 17px 18px; min-height: 112px; box-shadow:0 2px 8px rgba(31,62,42,.025); }
div[data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 760 !important; letter-spacing:-.02em; }
div[data-testid="stMetricLabel"] { font-size: 1.02rem !important; font-weight: 650 !important; }
.stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] button { min-height: 50px; border-radius: 11px; font-size: 17px !important; font-weight: 700; }
div[data-baseweb="input"] input, div[data-baseweb="select"] { min-height: 46px; font-size: 17px !important; }
div[data-testid="stAlert"] { border-radius: 12px; }
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
.qunar-hero { text-align:center; padding:1.3rem 1.1rem 1.4rem; margin-bottom:1.1rem; background:white; border:1px solid #e1e8e2; border-radius:18px; box-shadow:0 4px 18px rgba(31,62,42,.055); }
.qunar-brand { font-size:68px; line-height:1; font-weight:850; letter-spacing:3px; color:var(--qunar); }
.qunar-acronym { margin-top:.7rem; font-size:18px; font-weight:430; color:#315e43; letter-spacing:.01em; }
.qunar-acronym b { font-weight:850; color:#173d27; }
.qunar-translation { margin-top:.38rem; font-size:17px; font-weight:650; color:#596a60; }
.qunar-key, .qunar-reco { background:var(--qunar-soft); border-left:5px solid #4f7d5d; border-radius:10px; padding:15px 17px; margin:.65rem 0 1rem; font-size:18px; line-height:1.55; }
.qunar-key strong, .qunar-reco strong { font-weight:800; }
.qunar-insight { background:#fff; border:1px solid #e1e8e2; border-radius:12px; padding:14px 17px; margin:.55rem 0; font-size:17.5px; line-height:1.58; }
.qunar-insight strong { color:#243d2d; font-weight:760; }
.qunar-export { margin-top:1.2rem; padding-top:.5rem; }
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
def _cached_combined_excel(payload_json: str) -> bytes:
    return build_combined_excel_report(json.loads(payload_json))

@st.cache_data(show_spinner=False)
def _cached_combined_pdf(payload_json: str) -> bytes:
    return build_combined_pdf_report(json.loads(payload_json))

def _report_basket():
    return st.session_state.setdefault("qunar_report_basket", {})

def render_report_workspace(lang: str):
    labels = {
        "title": {"kk":"Менің есебім","ru":"Мой отчет","en":"My report"}[lang],
        "empty": {"kk":"Әзірге бөлімдер қосылған жоқ. Есептеуден кейін бөлімді жалпы есепке қосуға болады.","ru":"Пока разделы не добавлены. После расчета можно добавить текущий режим в общий отчет.","en":"No sections added yet. After a calculation, add the current mode to the combined report."}[lang],
        "included": {"kk":"Қосылған бөлімдер","ru":"Добавленные разделы","en":"Included sections"}[lang],
        "clear": {"kk":"Есепті тазарту","ru":"Очистить отчет","en":"Clear report"}[lang],
        "pdf": {"kk":"Толық PDF жүктеу","ru":"Скачать полный PDF","en":"Download full PDF"}[lang],
        "xlsx": {"kk":"Толық Excel жүктеу","ru":"Скачать полный Excel","en":"Download full Excel"}[lang],
    }
    basket = _report_basket()
    with st.expander(f"{labels['title']} ({len(basket)}/5)", expanded=False):
        if not basket:
            st.caption(labels["empty"])
            return
        st.markdown("**" + labels["included"] + ":**")
        for payload in basket.values():
            st.write("• " + str(payload.get("mode_label", "")))
        c1, c2, c3 = st.columns([1,1,0.7])
        payloads = list(basket.values())
        payload_json = json.dumps(payloads, ensure_ascii=False, sort_keys=True, default=str)
        bundle_id = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()[:16]
        if st.session_state.get("qunar_bundle_id") != bundle_id:
            st.session_state["qunar_bundle_id"] = bundle_id
            st.session_state.pop("qunar_full_pdf", None)
            st.session_state.pop("qunar_full_xlsx", None)
        with c1:
            if st.button({"kk":"Толық PDF дайындау","ru":"Подготовить полный PDF","en":"Prepare full PDF"}[lang], use_container_width=True, key=f"prep_full_pdf_{bundle_id}"):
                with st.spinner({"kk":"PDF дайындалуда...","ru":"Формируем PDF...","en":"Building PDF..."}[lang]):
                    st.session_state["qunar_full_pdf"] = _cached_combined_pdf(payload_json)
            if st.session_state.get("qunar_full_pdf"):
                st.download_button(labels["pdf"], data=st.session_state["qunar_full_pdf"], file_name=f"QUNAR_full_report_{datetime.now():%Y%m%d_%H%M}.pdf", mime="application/pdf", use_container_width=True, key=f"full_pdf_{bundle_id}")
        with c2:
            if st.button({"kk":"Толық Excel дайындау","ru":"Подготовить полный Excel","en":"Prepare full Excel"}[lang], use_container_width=True, key=f"prep_full_xlsx_{bundle_id}"):
                with st.spinner({"kk":"Excel дайындалуда...","ru":"Формируем Excel...","en":"Building Excel..."}[lang]):
                    st.session_state["qunar_full_xlsx"] = _cached_combined_excel(payload_json)
            if st.session_state.get("qunar_full_xlsx"):
                st.download_button(labels["xlsx"], data=st.session_state["qunar_full_xlsx"], file_name=f"QUNAR_full_report_{datetime.now():%Y%m%d_%H%M}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key=f"full_xlsx_{bundle_id}")
        with c3:
            if st.button(labels["clear"], use_container_width=True, key="clear_report_basket"):
                st.session_state["qunar_report_basket"] = {}
                st.session_state.pop("qunar_full_pdf", None)
                st.session_state.pop("qunar_full_xlsx", None)
                st.rerun()

@st.fragment
def render_export_panel(report_payload: dict, lang: str):
    labels = {
        "title": {"kk":"Есепті жүктеу","ru":"Скачать отчет","en":"Download report"}[lang],
        "caption": {"kk":"Файл осы блокта дайындалады. Беттің жоғарғы жағына қайта жібермейді.","ru":"Файл готовится внутри этого блока - страница больше не должна перескакивать наверх.","en":"The file is prepared inside this block, so the page should no longer jump to the top."}[lang],
        "prep_xlsx": {"kk":"Excel дайындау","ru":"Подготовить Excel","en":"Prepare Excel"}[lang],
        "down_xlsx": {"kk":"Excel жүктеу","ru":"Скачать Excel","en":"Download Excel"}[lang],
        "prep_pdf": {"kk":"PDF дайындау","ru":"Подготовить PDF","en":"Prepare PDF"}[lang],
        "down_pdf": {"kk":"PDF жүктеу","ru":"Скачать PDF","en":"Download PDF"}[lang],
        "ready": {"kk":"Файл дайын. Төмендегі жүктеу батырмасын басыңыз.","ru":"Файл готов. Нажмите кнопку скачивания ниже.","en":"File ready. Use the download button below."}[lang],
        "add": {"kk":"Жалпы есепке қосу","ru":"Добавить в общий отчет","en":"Add to combined report"}[lang],
        "added": {"kk":"Бұл бөлім жалпы есепке қосылды.","ru":"Этот раздел добавлен в общий отчет.","en":"This section was added to the combined report."}[lang],
    }
    payload_json = json.dumps(report_payload, ensure_ascii=False, sort_keys=True, default=str)
    report_id = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()[:16]
    if st.session_state.get("qunar_export_report_id") != report_id:
        st.session_state["qunar_export_report_id"] = report_id
        st.session_state.pop("qunar_xlsx", None)
        st.session_state.pop("qunar_pdf", None)

    with st.expander(labels["title"], expanded=bool(st.session_state.get("qunar_xlsx") or st.session_state.get("qunar_pdf"))):
        st.caption(labels["caption"])
        if st.button(labels["add"], use_container_width=True, key=f"add_bundle_{report_id}"):
            basket = _report_basket()
            basket[str(report_payload.get("mode_key", report_id))] = report_payload
            st.session_state["qunar_report_basket"] = basket
            st.success(labels["added"])
        ex1, ex2 = st.columns(2)
        with ex1:
            if st.button(labels["prep_xlsx"], use_container_width=True, key=f"prepare_xlsx_{report_id}"):
                with st.spinner(labels["prep_xlsx"] + "..."):
                    st.session_state["qunar_xlsx"] = _cached_excel_report(payload_json)
            if st.session_state.get("qunar_xlsx"):
                st.success(labels["ready"])
                st.download_button(labels["down_xlsx"], data=st.session_state["qunar_xlsx"], file_name=f"QUNAR_report_{datetime.now():%Y%m%d_%H%M}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key=f"download_xlsx_{report_id}")
        with ex2:
            if st.button(labels["prep_pdf"], use_container_width=True, key=f"prepare_pdf_{report_id}"):
                with st.spinner(labels["prep_pdf"] + "..."):
                    st.session_state["qunar_pdf"] = _cached_pdf_report(payload_json)
            if st.session_state.get("qunar_pdf"):
                st.success(labels["ready"])
                st.download_button(labels["down_pdf"], data=st.session_state["qunar_pdf"], file_name=f"QUNAR_report_{datetime.now():%Y%m%d_%H%M}.pdf", mime="application/pdf", use_container_width=True, key=f"download_pdf_{report_id}")

lang_label = st.sidebar.selectbox("Тіл / Язык / Language", list(LANGUAGES.keys()), index=0)
lang = LANGUAGES[lang_label]
# Copy translations locally so deployment remains backward-compatible if Streamlit
# briefly serves app.py with a cached/older core.config during a GitHub redeploy.
t = dict(TEXT[lang])
_MODE_LABEL_FALLBACK = {
    "kk": {"mode5": "Мал шаруашылығы ресурстарын бағалау"},
    "ru": {"mode5": "Оценить ресурсы животноводства"},
    "en": {"mode5": "Assess livestock resources"},
}
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
user_level = st.sidebar.radio(
    t["user_level"],
    ["farmer", "specialist", "researcher"],
    format_func=lambda x: {"farmer": t["level_farmer"], "specialist": t["level_specialist"], "researcher": t["level_researcher"]}[x],
    index=0,
)
if user_level == "farmer":
    st.sidebar.caption(t["level_basic_hint"])
elif user_level == "specialist":
    st.sidebar.caption(t["level_advanced_hint"])
else:
    st.sidebar.caption(t["level_research_hint"])

def district_label(code):
    return DISTRICT_LABELS[lang].get(code, code)

def crop_label(code):
    return CROP_LABELS[lang].get(code, code)

st.markdown(
    f"""
    <div class="qunar-hero">
      <div class="qunar-brand">QŪNAR</div>
      <div class="qunar-acronym">{t["brand_line"]}</div>
      <div class="qunar-translation">{t["brand_translation"]}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
render_report_workspace(lang)
st.info(t["session_warning"])
st.caption(t["save_restore_note"])

mode_keys = ["mode1", "mode2", "mode3", "mode4", "mode5"]
mode_key = st.sidebar.radio(t["mode"], mode_keys, format_func=lambda k: t.get(k, k))
district = st.sidebar.selectbox(t["district"], DISTRICT_ORDER, format_func=district_label)

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

st.caption(t["fast_mode_note"])

gps_enabled = st.toggle(t["gps_use"], value=False, help=t["gps_title"])
if gps_enabled:
    gps_loc, gps_err = timed_call("Browser geolocation", browser_geolocation)
    if gps_err == "missing_component":
        st.caption(t["gps_missing"])
    elif gps_loc:
        # GPS is navigation only. Keeping it opt-in avoids loading the browser component on every rerun.
        st.session_state.field_lat = gps_loc["latitude"]
        st.session_state.field_lon = gps_loc["longitude"]
        acc = gps_loc.get("accuracy_m")
        msg = f"{t['gps_ok']}: {gps_loc['latitude']:.6f}, {gps_loc['longitude']:.6f}"
        if acc is not None:
            msg += f" | {t['gps_accuracy']}: ~{float(acc):.0f} m"
        st.success(msg)
        try:
            rg = timed_call("Reverse geocoding", reverse_geocode, gps_loc["latitude"], gps_loc["longitude"])
            if rg.get("matched_district"):
                if rg["matched_district"] == district:
                    st.info(t["district_check_ok"])
                else:
                    st.warning(t["district_check_warn"] + " " + DISTRICT_LABELS[lang].get(rg["matched_district"], rg["matched_district"]))
            st.caption(t["district_check_note"])
        except Exception:
            pass


location_source = st.radio(
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

use_map = st.toggle(t["map_toggle"], value=False, help=t["map_help"], disabled=(location_source == "district"))
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

area_input_label = t["area"] if mode_key != "mode5" else {
    "kk":"Жайылым / өндірістік жер алаңы, га",
    "ru":"Площадь пастбища / производственной территории, га",
    "en":"Pasture / production land area, ha",
}[lang]

with st.form("farm_inputs", clear_on_submit=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        area_ha = st.number_input(area_input_label, min_value=0.1, value=10.0, step=0.5, help=t["declared_area_help"])
    with c2:
        available_water_label = t["water"] if mode_key != "mode5" else {
            "kk":"Жылдық қолжетімді су көлемі, м³",
            "ru":"Доступный годовой объем воды, м³",
            "en":"Available annual water volume, m³",
        }[lang]
        available_water = st.number_input(
            available_water_label, min_value=0.0, value=0.0, step=1000.0, help=t["available_water_note"]
        )
    with c3:
        st.caption(t["nasa_auto_note"])
        if user_level == "farmer":
            st.caption(t["wapor_basic_note"])
            use_wapor = False
        else:
            use_wapor = st.checkbox(t["wapor_toggle"], value=True)

    crop = None
    if mode_key == "mode1":
        crop = st.selectbox(t["crop"], check_crop_codes(), format_func=lambda c: extended_crop_label(c, lang))
    elif mode_key == "mode2":
        crop = st.selectbox(t["crop"], check_crop_codes(), format_func=lambda c: extended_crop_label(c, lang))

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
            livestock_species = st.selectbox(
                {"kk":"Мал түрі","ru":"Вид животных","en":"Livestock type"}[lang],
                SPECIES,
                format_func=lambda x: SPECIES_LABELS[lang][x],
            )
        with l2:
            livestock_heads = st.number_input(
                {"kk":"Мал саны, бас","ru":"Поголовье, голов","en":"Number of animals, head"}[lang],
                min_value=0.0, value=0.0, step=10.0,
                help={
                    "kk":"0 қалдырылса, аудан бойынша соңғы қолжетімді ресми мал саны анықтамалық сценарий ретінде пайдаланылады.",
                    "ru":"Если оставить 0, QŪNAR использует последнее доступное официальное поголовье района как справочный сценарий.",
                    "en":"If left at 0, QŪNAR uses the latest available official district herd count as a reference scenario.",
                }[lang],
            )
        with l3:
            livestock_production_kind = st.selectbox(
                {"kk":"Өнім түрі","ru":"Вид продукции","en":"Product type"}[lang],
                PRODUCT_TYPES,
                index=PRODUCT_TYPES.index(DEFAULT_PRODUCT.get(livestock_species, "meat_tonnes")),
                format_func=lambda x: PRODUCT_LABELS[lang][x],
            )
        with l4:
            livestock_production_amount = st.number_input(
                {"kk":"Жылдық өнім көлемі","ru":"Годовой объем продукции","en":"Annual production volume"}[lang],
                min_value=0.0, value=0.0, step=1.0,
                help={
                    "kk":"0 мәні нақты өнім көлемі белгісіз екенін білдіреді; аймақтық анықтамалық өнімділік бөлек көрсетіледі.",
                    "ru":"0 означает, что фактический выпуск неизвестен; региональный ориентир производительности будет показан отдельно.",
                    "en":"0 means observed production is unknown; a regional productivity reference is shown separately.",
                }[lang],
            )

        livestock_feed_source = st.selectbox(
            {"kk":"Жемшөп қоры туралы дерек","ru":"Данные о годовом запасе кормов","en":"Annual feed-supply data"}[lang],
            ["unknown", "own"],
            format_func=lambda x: {
                "unknown":{"kk":"Білмеймін / анықтамалық қажеттілікті есептеу","ru":"Не знаю / рассчитать справочную потребность","en":"Unknown / calculate reference requirement"}[lang],
                "own":{"kk":"Өз дерегімді енгізу","ru":"Ввести свои данные","en":"Enter my data"}[lang],
            }[x],
        )
        if livestock_feed_source == "own":
            livestock_fodder_t = st.number_input(
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
    ef = float(DEFAULT_EF_KZ_KGCO2_PER_KWH)
    irrigation_type = "unknown"
    water_meter = False
    soil_sensors = False
    efficient_pump = False
    current_solar = 0.0
    target_solar = float(DEFAULT_GREEN_SHARE_TARGET)
    electricity_tariff = float(DEFAULT_ELECTRICITY_TARIFF_KZT_KWH)
    water_tariff = float(DEFAULT_IRRIGATION_WATER_TARIFF_KZT_M3)
    water_saving_target = float(DEFAULT_WATER_SAVING_TARGET)
    investment = 0.0
    seasons_per_year = 1.0
    expected_yield_c_ha = 0.0
    selling_price_kzt_t = 0.0
    variable_cost_kzt_ha = 0.0
    # Optional environmental observations use None for "unknown".
    # A measured zero remains a valid observation and is therefore distinct from missing data.
    pesticide_kg_ha = None
    salinized_share_pct = None
    pasture_degraded_share_pct = None

    if mode_key == "mode5":
        st.markdown("#### " + {"kk":"Мал шаруашылығы ресурстары","ru":"Ресурсы животноводства","en":"Livestock resources"}[lang])
        lr1, lr2 = st.columns(2)
        with lr1:
            water_used = st.number_input(
                {"kk":"Нақты жылдық су тұтынуы, м³","ru":"Фактическое годовое водопотребление, м³","en":"Observed annual water use, m³"}[lang],
                min_value=0.0, value=0.0, step=100.0,
            )
        with lr2:
            energy = st.number_input(
                {"kk":"Нақты жылдық энергия тұтынуы, кВт·сағ","ru":"Фактическое годовое энергопотребление, кВт·ч","en":"Observed annual energy use, kWh"}[lang],
                min_value=0.0, value=0.0, step=100.0,
            )
        if user_level == "researcher":
            ef = st.number_input(t["ef"], min_value=0.0, value=float(DEFAULT_EF_KZ_KGCO2_PER_KWH), step=0.001)
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
            water_used = st.number_input(t["water_used"], min_value=0.0, value=0.0, step=1000.0)
        with b2:
            energy = st.number_input(t["energy"], min_value=0.0, value=0.0, step=100.0)
        with b3:
            irrigation_type = st.selectbox(
                t["irrigation_type"], ["unknown","furrow","sprinkler","drip","mixed"],
                format_func=lambda x:{"unknown":t["irrigation_unknown"],"furrow":t["irrigation_furrow"],"sprinkler":t["irrigation_sprinkler"],"drip":t["irrigation_drip"],"mixed":t["irrigation_mixed"]}[x]
            )
        st.caption({"kk":"Қалған техникалық параметрлер анықтамалық сценариймен есептеледі. Нақты тарифтер, өлшеу сенсорлары, сорғы және сценарийлер үшін «Кеңейтілген» деңгейді таңдаңыз.","ru":"Остальные технические параметры рассчитываются по справочному сценарию. Для точных тарифов, датчиков, насоса и сценариев выберите «Расширенный» уровень.","en":"Other technical parameters use the reference scenario. Choose Advanced for exact tariffs, sensors, pump and what-if settings."}[lang])
    else:
        with st.expander(t["resource_inputs"], expanded=True):
            a,b=st.columns(2)
            with a:
                water_used=st.number_input(t["water_used"],min_value=0.0,value=0.0,step=1000.0)
                reuse=st.number_input(t["reuse"],min_value=0.0,max_value=100.0,value=0.0,step=0.1)
                irrigation_type=st.selectbox(t["irrigation_type"],["unknown","furrow","sprinkler","drip","mixed"],format_func=lambda x:{"unknown":t["irrigation_unknown"],"furrow":t["irrigation_furrow"],"sprinkler":t["irrigation_sprinkler"],"drip":t["irrigation_drip"],"mixed":t["irrigation_mixed"]}[x])
                water_meter=st.checkbox(t["has_water_meter"],value=False)
                soil_sensors=st.checkbox(t["has_soil_sensors"],value=False)
            with b:
                energy=st.number_input(t["energy"],min_value=0.0,value=0.0,step=100.0)
                efficient_pump=st.checkbox(t["has_efficient_pump"],value=False)
                current_solar=st.number_input(t["current_solar"],min_value=0.0,max_value=100.0,value=0.0,step=0.1)
                target_solar=st.number_input(t["target_solar"],min_value=0.0,max_value=100.0,value=float(DEFAULT_GREEN_SHARE_TARGET),step=0.5)
            st.markdown("##### "+t["econ_block"])
            st.caption(t["whatif_help"])
            p1,p2,p3,p4=st.columns(4)
            with p1:
                electricity_tariff=st.number_input(t["electricity_tariff"],min_value=0.0,value=float(DEFAULT_ELECTRICITY_TARIFF_KZT_KWH),step=0.1)
            with p2:
                water_tariff=st.number_input(t["water_tariff"],min_value=0.0,value=float(DEFAULT_IRRIGATION_WATER_TARIFF_KZT_M3),step=0.01)
            with p3:
                water_saving_target=st.number_input(t["water_saving_target"],min_value=0.0,max_value=100.0,value=float(DEFAULT_WATER_SAVING_TARGET),step=0.1)
            with p4:
                investment=st.number_input(t["investment"],min_value=0.0,value=0.0,step=100000.0)
            seasons_per_year=st.number_input(t["seasons_per_year"],min_value=1.0,value=1.0,step=1.0)
            if user_level == "researcher":
                st.markdown("##### " + {"kk":"Зерттеу параметрлері","ru":"Исследовательские параметры","en":"Research parameters"}[lang])
                ef=st.number_input(t["ef"],min_value=0.0,value=float(DEFAULT_EF_KZ_KGCO2_PER_KWH),step=0.001)
                st.caption(t["ef_source"])
                st.caption(t["tariff_source_note"])
                st.caption(t["decimal_note"])
            else:
                ef=float(DEFAULT_EF_KZ_KGCO2_PER_KWH)
                st.caption(t["tariff_note"])

        st.caption(t["api_offline"])

    if mode_key == "mode5":
        with st.expander({"kk":"Жайылымның экологиялық диагностикасы (міндетті емес)","ru":"Экологическая диагностика пастбища (необязательно)","en":"Pasture environmental diagnostics (optional)"}[lang], expanded=False):
            pasture_source = st.selectbox(
                {"kk":"Жайылым деградациясы туралы дерек","ru":"Данные о деградации пастбища","en":"Pasture-degradation data"}[lang],
                ["unknown", "own"],
                format_func=lambda x: {
                    "unknown":{"kk":"Білмеймін / дерек жоқ","ru":"Не знаю / данных нет","en":"Unknown / no data"}[lang],
                    "own":{"kk":"Өз дерегімді енгізу","ru":"Ввести свои данные","en":"Enter my data"}[lang],
                }[x],
            )
            if pasture_source == "own":
                pasture_degraded_share_pct = st.number_input(
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
                pesticide_source = st.selectbox(
                    {"kk":"Пестицид жүктемесі туралы дерек","ru":"Данные о пестицидной нагрузке","en":"Pesticide-load data"}[lang],
                    ["unknown", "own"],
                    format_func=lambda x: {
                        "unknown":{"kk":"Білмеймін / дерек жоқ","ru":"Не знаю / данных нет","en":"Unknown / no data"}[lang],
                        "own":{"kk":"Өз дерегімді енгізу","ru":"Ввести свои данные","en":"Enter my data"}[lang],
                    }[x],
                )
                if pesticide_source == "own":
                    pesticide_kg_ha = st.number_input(
                        {"kk":"Пестицид жүктемесі, кг/га","ru":"Пестицидная нагрузка, кг/га","en":"Pesticide load, kg/ha"}[lang],
                        min_value=0.0, value=0.0, step=0.01,
                    )
                else:
                    pesticide_kg_ha = None
            with ee2:
                salinity_source = st.selectbox(
                    {"kk":"Тұздану туралы дерек","ru":"Данные о засолении","en":"Salinity data"}[lang],
                    ["unknown", "own"],
                    format_func=lambda x: {
                        "unknown":{"kk":"Білмеймін / дерек жоқ","ru":"Не знаю / данных нет","en":"Unknown / no data"}[lang],
                        "own":{"kk":"Өз дерегімді енгізу","ru":"Ввести свои данные","en":"Enter my data"}[lang],
                    }[x],
                )
                if salinity_source == "own":
                    salinized_share_pct = st.number_input(
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
                "kk":"Баға жасырын жанама көрсеткіштен алынбайды. Нарықтық баға мен шығынды өз деректеріңізбен енгізіңіз; өнімділік енгізілмесе, машиналық оқыту арқылы қолжетімді баға пайдаланылады.",
                "ru":"Цена не берется из скрытого рыночного косвенного показателя. Укажите подтвержденную цену и затраты; если урожайность не введена, при наличии используется оценка машинного обучения.",
                "en":"No hidden market-price proxy is used. Enter a verified price and costs; if yield is omitted, an available ML estimate is used."
            }[lang])
            ec1,ec2,ec3=st.columns(3)
            with ec1:
                expected_yield_c_ha=st.number_input({"kk":"Күтілетін өнімділік, ц/га","ru":"Ожидаемая урожайность, ц/га","en":"Expected yield, centners/ha"}[lang],min_value=0.0,value=0.0,step=1.0)
            with ec2:
                selling_price_kzt_t=st.number_input({"kk":"Сату бағасы, тг/т","ru":"Цена реализации, тг/т","en":"Selling price, KZT/t"}[lang],min_value=0.0,value=0.0,step=1000.0)
            with ec3:
                variable_cost_kzt_ha=st.number_input({"kk":"Басқа айнымалы шығындар, тг/га","ru":"Прочие переменные затраты, тг/га","en":"Other variable costs, KZT/ha"}[lang],min_value=0.0,value=0.0,step=10000.0)

    optimization_profile = "balanced"
    optimization_max_share = 0.40
    optimization_n_crops = 5
    if mode_key == "mode4" and user_level != "farmer":
        st.markdown("#### " + {"kk":"Оңтайландыру сценарийі","ru":"Сценарий оптимизации","en":"Optimization scenario"}[lang])
        op1, op2, op3 = st.columns(3)
        with op1:
            optimization_profile = st.selectbox(
                {"kk":"Басымдық","ru":"Приоритет","en":"Priority"}[lang],
                ["balanced", "climate", "resource"],
                format_func=lambda x: {
                    "balanced":{"kk":"Теңгерімді","ru":"Сбалансированный","en":"Balanced"}[lang],
                    "climate":{"kk":"Климаттық тұрақтылық","ru":"Климатическая устойчивость","en":"Climate resilience"}[lang],
                    "resource":{"kk":"Ресурс үнемдеу","ru":"Ресурсосбережение","en":"Resource saving"}[lang],
                }[x],
            )
        with op2:
            optimization_max_share = st.number_input(
                {"kk":"Бір дақылдың ең жоғары үлесі, %","ru":"Максимальная доля одной культуры, %","en":"Maximum share of one crop, %"}[lang],
                min_value=20.0, max_value=80.0, value=40.0, step=5.0
            ) / 100.0
        with op3:
            optimization_n_crops = int(st.number_input(
                {"kk":"Егіс құрылымындағы дақылдар саны","ru":"Количество культур в структуре посевов","en":"Number of crops in the cropping structure"}[lang],
                min_value=2, max_value=8, value=5, step=1,
                help={
                    "kk":"Модель егістік ауданды қанша түрлі дақыл арасында бөлетінін көрсетіңіз. Мысалы, 5 - ұсынылатын құрылымда бес дақыл болады.",
                    "ru":"Укажите, между сколькими культурами модель должна распределить посевную площадь. Например, 5 означает структуру из пяти культур.",
                    "en":"Choose how many different crops should share the cultivated area. For example, 5 means a five-crop structure."
                }[lang]
            ))

    submitted = st.form_submit_button(t["calculate"], type="primary", use_container_width=True)

if submitted:
    live_ok = False

    # v0.7.4: zero water input means "use the official/default district-crop norm",
    # not "assume zero water". User-entered positive values always override it.
    water_default_info = default_water_requirement(used_district, crop, irrigation_type) if crop is not None else None
    if water_used > 0:
        effective_water_used = float(water_used)
        water_input_source = "user"
    elif water_default_info is not None:
        effective_water_used = float(water_default_info.m3_ha) * float(area_ha)
        water_input_source = "official_default"
        st.caption({
            "kk":f"Су шығыны енгізілмегендіктен, есепте {water_default_info.m3_ha:,.0f} м³/га әдепкі мәні қолданылды. Дереккөзі: {water_source_label(water_default_info)}. Оны өз дерегіңізбен ауыстыруға болады.",
            "ru":f"Расход воды не введен, поэтому используется редактируемое значение по умолчанию {water_default_info.m3_ha:,.0f} м³/га. Источник: {water_source_label(water_default_info)}.",
            "en":f"No farm water use was entered, so the editable default {water_default_info.m3_ha:,.0f} m³/ha is used. Source: {water_source_label(water_default_info)}."
        }[lang])
    else:
        effective_water_used = 0.0
        water_input_source = "none"

    report_payload = {
        "mode_key": mode_key,
        "lang": lang,
        "brand_translation": t.get("brand_translation", ""),
        "mode_label": t.get(mode_key, mode_key),
        "generated_label": {"kk":"Есеп жасалған уақыт","ru":"Дата расчета","en":"Generated"}[lang],
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
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
            [t["district"], district_label(used_district), {"kk":"Әкімшілік полигон/таңдау","ru":"Административный полигон/выбор","en":"Administrative polygon/selection"}[lang]],
            [area_input_label, f"{area_ha:.2f}", t["source_user"]],
            [{"kk":"Есеп координатасы","ru":"Координаты расчета","en":"Calculation coordinates"}[lang], f"{calc_lat:.6f}, {calc_lon:.6f}", {"kk":"Карта/аудан","ru":"Карта/район","en":"Map/district"}[lang]],
            [available_water_label, f"{available_water:.2f}" if available_water > 0 else {"kk":"белгісіз","ru":"неизвестно","en":"unknown"}[lang], t["source_user"] if available_water > 0 else {"kk":"Енгізілмеген","ru":"Не введено","en":"Not entered"}[lang]],
            [({"kk":"Нақты жылдық су тұтынуы, м³","ru":"Фактическое годовое водопотребление, м³","en":"Observed annual water use, m³"}[lang] if mode_key=="mode5" else t["water_used"]), f"{effective_water_used:.2f}" if effective_water_used > 0 else {"kk":"белгісіз","ru":"неизвестно","en":"unknown"}[lang], (t["source_user"] if water_input_source=="user" else water_source_label(water_default_info))],
            [t["energy"], f"{energy:.2f}" if energy > 0 else {"kk":"белгісіз","ru":"неизвестно","en":"unknown"}[lang], t["source_user"] if energy > 0 else {"kk":"Енгізілмеген","ru":"Не введено","en":"Not entered"}[lang]],
        ]
    }
    if crop is not None:
        report_payload["inputs"].append([t["crop"], extended_crop_label(crop, lang), t["source_user"]])
    if mode_key == "mode5":
        livestock_head_source_label = (
            t["source_user"] if livestock_heads > 0
            else {"kk":"Аудандық ресми анықтамалық сценарий","ru":"Районный официальный справочный сценарий","en":"Official district reference scenario"}[lang]
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
            [{"kk":"Өнім көлемі","ru":"Объем продукции","en":"Production volume"}[lang], f"{livestock_production_amount:.2f}" if livestock_production_amount > 0 else {"kk":"белгісіз","ru":"неизвестно","en":"unknown"}[lang], production_source_label],
        ])
    climate = district_climate(used_district) or {}
    baseline_climate = dict(climate)
    climate_source = t["fallback_source"]

    if True:
        try:
            with st.spinner(t["nasa_loading"]):
                nasa = timed_call("NASA POWER", fetch_growing_season, calc_lat, calc_lon)
            climate = {**climate, **nasa}
            climate_source = t["live_source"]
            live_ok = True
        except Exception:
            st.warning(t["nasa_error"])

    st.subheader(t["results"])
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

    polygon_area = calc_polygon_area
    area_geometry_mismatch = False
    if polygon_area:
        diff_pct = abs(polygon_area - area_ha) / max(area_ha, 0.0001) * 100.0
        st.caption(t["area_compare"].format(declared=area_ha, polygon=polygon_area, diff=diff_pct))
        area_geometry_mismatch = diff_pct > 25
        if area_geometry_mismatch:
            st.warning(t["area_mismatch"].format(declared=area_ha, polygon=polygon_area, diff=diff_pct))
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
            energy_kwh=energy,
            emission_factor_kgco2_kwh=ef,
            production_amount=livestock_production_amount,
            production_kind=livestock_production_kind,
            pasture_degraded_share_pct=pasture_degraded_share_pct,
            climate=climate,
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
            f"{effective_heads:,.0f}"
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
            {"label":{"kk":"Мал шаруашылығының үлесі","ru":"Доля животноводства","en":"Livestock share"}[lang],
             "value":f"{float(lp.get('livestock_share_pct',0)):.1f}%"},
            {"label":{"kk":"Мал саны","ru":"Поголовье","en":"Herd"}[lang],
             "value":f"{effective_heads:,.0f} ({ {'user': {'kk':'пайдаланушы дерегі','ru':'данные пользователя','en':'user data'}, 'district_reference': {'kk':'аудандық анықтамалық мән','ru':'районное справочное значение','en':'district reference'}, 'unknown': {'kk':'белгісіз','ru':'неизвестно','en':'unknown'} }.get(heads_source, {'kk':str(heads_source),'ru':str(heads_source),'en':str(heads_source)})[lang] })"},
            {"label":{"kk":"Машиналық оқыту болжамы","ru":"Прогноз машинного обучения","en":"Machine-learning forecast"}[lang],
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

    elif mode_key == "mode1" and crop not in CROPS:
        # Expanded farm assessment for crops without a calibrated yield ML model.
        scenario = scenario_for_crop(used_district, crop, climate, irrigation_type)
        obs_ev = observed_for_crop(used_district, crop)
        resource = calculate_resources(
            area_ha=area_ha,
            water_used_m3=effective_water_used if effective_water_used > 0 else None,
            reuse_percent=reuse,
            energy_kwh=energy if energy > 0 else None,
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
            st.caption({"kk":f"Егер осы су көлемі сорғымен берілсе, анықтамалық энергия сценарийі ≈ {resource['reference_pumping_energy_kwh_per_ha']:,.0f} кВт·сағ/га (0,70509 кВт·сағ/м³). Бұл нақты тұтыну емес.","ru":f"Если весь этот объем подается насосом, справочный энергетический сценарий ≈ {resource['reference_pumping_energy_kwh_per_ha']:,.0f} кВт·ч/га (0,70509 кВт·ч/м³). Это не фактическое энергопотребление хозяйства.","en":f"If the full water volume is pumped, the reference energy scenario is ≈ {resource['reference_pumping_energy_kwh_per_ha']:,.0f} kWh/ha (0.70509 kWh/m³). This is not observed farm energy use."}[lang])
        if "operational_co2e_kg_per_ha" in resource: st.metric(t["co2"], f"{resource['operational_co2e_kg_per_ha']:,.1f} {UNITS['co2_kg_ha']}")
        econ = economic_climate_effect(energy_kwh=energy, freshwater_m3=resource.get("farm_freshwater_m3"), electricity_tariff=electricity_tariff, water_tariff=water_tariff, emission_factor=ef, current_solar_share=current_solar, target_solar_share=target_solar, water_saving_target=water_saving_target)
        if user_level != "farmer":
            st.markdown("### " + t["climate_cost_title"])
            e1,e2,e3,e4=st.columns(4)
            e1.metric(t["energy_cost"], f"{econ['current_energy_cost_kzt']:,.0f} {UNITS['currency']}")
            e2.metric(t["water_cost"], f"{econ['current_water_cost_kzt']:,.0f} {UNITS['currency']}")
            e3.metric(t["co2_reduction"], f"{econ['co2_reduction_kg']/1000:,.2f} {UNITS['t']} CO₂")
            e4.metric(t["total_saving"], f"{econ['total_saving_kzt']:,.0f} {UNITS['currency']}")
        st.markdown("### " + {"kk":"Практикалық қорытынды","ru":"Практический вывод","en":"Practical conclusion"}[lang])
        if scenario is not None:
            st.write({"kk":f"{extended_crop_label(crop,lang)} бойынша негізгі шектеулер климат, нормативтік су жүктемесі және дерек сенімділігі бірге қарастырылып бағаланды.","ru":f"Для культуры «{extended_crop_label(crop,lang)}» ограничения оцениваются совместно по климату, нормативной водной нагрузке и надежности исходных данных.","en":f"For {extended_crop_label(crop,lang)}, constraints are assessed jointly through climate, normative water demand and evidence reliability."}[lang])
        if user_level == "researcher":
            with st.expander(t["model_inputs"]):
                st.write({"kk":f"Есеп координатасы: {calc_lat:.6f}, {calc_lon:.6f}; қолданылған аудан: {district_label(used_district)}; әдіс: {model_tier_label(crop_method(crop))}.","ru":f"Координаты расчета: {calc_lat:.6f}, {calc_lon:.6f}; использованный район: {district_label(used_district)}; метод: {model_tier_label(crop_method(crop))}.","en":f"Calculation coordinates: {calc_lat:.6f}, {calc_lon:.6f}; district used: {district_label(used_district)}; method: {model_tier_label(crop_method(crop))}."}[lang])

    elif mode_key == "mode1":
        with st.spinner(t["ml_loading"]):
            pred, used = timed_call("ML prediction", predict_yield, used_district, crop, area_ha, climate)

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
            water_used_m3=effective_water_used if effective_water_used > 0 else None,
            reuse_percent=reuse,
            energy_kwh=energy if energy > 0 else None,
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
            actual_energy=energy > 0,
            emission_factor=ef > 0,
            wapor_used=bool(wapor_water),
            wapor_pixels=wapor_pixels,
            area_geometry_mismatch=area_geometry_mismatch,
            ml_mae=val_for_support.get("mae"),
            historical_yield_median=(ctx_for_support or {}).get("historical_yield_median"),
        )

        if user_level == "farmer":
            x,z=st.columns(2)
            x.metric(t["baseline_label"], f"{pred:.1f} {UNITS['centner_ha']}")
            z.metric(t["climate"], climate_source)
            st.caption(t["scope_note"])
        else:
            x,y,z=st.columns(3)
            x.metric(t["baseline_label"], f"{pred:.1f} {UNITS['centner_ha']}")
            y.metric(t["support_label"], f"{t[reliability['level']]} ({reliability['score']}/100)")
            z.metric(t["climate"], climate_source)
            st.caption(t["scope_note"] + " " + t["support_note"])
        if mode_key == "mode2":
            st.info(t.get("mode2_distinct_note", ""))

        if "farm_water_m3_per_ha" in resource:
            x1, x2 = st.columns(2)
            x1.metric(t["water_use"], f"{resource['farm_water_m3_per_ha']:,.0f} м³/га" if lang != "en" else f"{resource['farm_water_m3_per_ha']:,.0f} m³/ha")
            x2.metric(t["freshwater"], f"{resource['farm_freshwater_m3']:,.0f} м³" if lang != "en" else f"{resource['farm_freshwater_m3']:,.0f} {UNITS['m3']}")

        if "energy_kwh_per_ha" in resource:
            st.metric(t["energy_use"], f"{resource['energy_kwh_per_ha']:,.0f} кВт·ч/га" if lang != "en" else f"{resource['energy_kwh_per_ha']:,.0f} kWh/ha")

        if "operational_co2e_kg_per_ha" in resource:
            st.metric(t["co2"], f"{resource['operational_co2e_kg_per_ha']:,.1f} кг CO₂e/га" if lang != "en" else f"{resource['operational_co2e_kg_per_ha']:,.1f} kg CO₂e/ha")

        econ = economic_climate_effect(
            energy_kwh=energy,
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
            ec1.metric(t["grid_energy"], f"{econ['current_grid_energy_kwh']:,.0f} кВт·ч" if lang != "en" else f"{econ['current_grid_energy_kwh']:,.0f} kWh")
            ec2.metric(t["co2_calc"], f"{econ['current_co2_kg']/1000:,.2f} т CO₂" if lang != "en" else f"{econ['current_co2_kg']/1000:,.2f} t CO₂")
            ec3.metric(t["energy_cost"], f"{econ['current_energy_cost_kzt']:,.0f} {UNITS['currency']}" if lang != "en" else f"{econ['current_energy_cost_kzt']:,.0f} KZT")
            ec4.metric(t["water_cost"], f"{econ['current_water_cost_kzt']:,.0f} {UNITS['currency']}" if lang != "en" else f"{econ['current_water_cost_kzt']:,.0f} KZT")
            wc1, wc2, wc3, wc4 = st.columns(4)
            wc1.metric(t["green_saving"], f"{econ['energy_saving_kzt']:,.0f} тг" if lang != "en" else f"{econ['energy_saving_kzt']:,.0f} KZT")
            wc2.metric(t["water_saving"], f"{econ['water_saving_m3']:,.0f} м³ / {econ['water_saving_kzt']:,.0f} тг" if lang != "en" else f"{econ['water_saving_m3']:,.0f} m³ / {econ['water_saving_kzt']:,.0f} KZT")
            wc3.metric(t["co2_reduction"], f"{econ['co2_reduction_kg']/1000:,.2f} т CO₂" if lang != "en" else f"{econ['co2_reduction_kg']/1000:,.2f} t CO₂")
            wc4.metric(t["total_saving"], f"{econ['total_saving_kzt']:,.0f} {UNITS['currency']}" if lang != "en" else f"{econ['total_saving_kzt']:,.0f} {UNITS['currency']}")
            pb = payback_years(investment, econ["total_saving_kzt"], seasons_per_year)
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
            wc2.metric(t["wapor_consumptive"], f"{wapor_water['consumptive_water_m3_per_ha']:,.0f} м³/га" if lang != "en" else f"{wapor_water['consumptive_water_m3_per_ha']:,.0f} m³/ha")
            wc3.metric(t["wapor_wp"], f"{wapor_water['modelled_water_productivity_kg_m3']:.2f} кг/м³" if lang != "en" else f"{wapor_water['modelled_water_productivity_kg_m3']:.2f} kg/m³")
            st.caption(t["wapor_note"])
            if wapor_pixels is not None and wapor_pixels <= 3:
                st.warning(t["small_field_warning"])

        if mode_key == "mode1" and user_level == "farmer":
            st.markdown("### " + {"kk":"Ақша және климат әсері","ru":"Деньги и климатический эффект","en":"Money and climate effect"}[lang])
            c1,c2,c3=st.columns(3)
            c1.metric({"kk":"Электр шығыны","ru":"Расходы на электроэнергию","en":"Electricity cost"}[lang],f"{econ['current_energy_cost_kzt']:,.0f} {UNITS['currency']}" if lang!="en" else f"{econ['current_energy_cost_kzt']:,.0f} KZT")
            c2.metric({"kk":"Су шығыны","ru":"Стоимость воды","en":"Water cost"}[lang],f"{econ['current_water_cost_kzt']:,.0f} {UNITS['currency']}" if lang!="en" else f"{econ['current_water_cost_kzt']:,.0f} KZT")
            c3.metric({"kk":"Сценарийлік үнем","ru":"Потенциальная экономия","en":"Potential saving"}[lang],f"{econ['total_saving_kzt']:,.0f} {UNITS['currency']}" if lang!="en" else f"{econ['total_saving_kzt']:,.0f} {UNITS['currency']}")

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
            hist=district_crop_context(used_district,crop) or {}

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
                    "kk":f"Су нормасы: {float(scenario['official_water_default_m3_ha']):,.0f} м³/га. Дерек сенімділігі: {float(scenario['Data_reliability_0_100']):.1f}/100.",
                    "ru":f"Норматив воды: {float(scenario['official_water_default_m3_ha']):,.0f} м³/га. Надежность данных: {float(scenario['Data_reliability_0_100']):.1f}/100.",
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
                        "ru":"Для этой культуры пока нет районного многокритериального профиля. Поэтому оценка основана на ряду урожайности, полученном машинным обучением, и климатических данных.",
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
                st.markdown("#### " + {"kk":"Машиналық оқыту бойынша өнімділік бағасы","ru":"Оценка урожайности машинным обучением","en":"ML yield evidence"}[lang])
            else:
                st.markdown("#### " + {"kk":"Күтілетін өнімділік","ru":"Ожидаемая урожайность","en":"Expected yield"}[lang])
            med=hist.get('historical_yield_median') if hist else None
            if med:
                delta=(ml_pred-float(med))/float(med)*100
                if user_level == "researcher":
                    st.write({"kk":f"Аудан-дақыл бойынша машиналық оқыту базалық болжамы: {ml_pred:.1f} ц/га; тарихи медианаға қатысты {delta:+.1f}%.","ru":f"Базовый прогноз машинного обучения по району и культуре: {ml_pred:.1f} ц/га; относительно исторической медианы {delta:+.1f}%.","en":f"District-crop ML baseline: {ml_pred:.1f} c/ha; {delta:+.1f}% versus historical median."}[lang])
                else:
                    st.write({"kk":f"Күтілетін деңгей: {ml_pred:.1f} ц/га, тарихи аудандық медианадан {delta:+.1f}%.","ru":f"Ожидаемый уровень: {ml_pred:.1f} ц/га, отклонение от исторической районной медианы {delta:+.1f}%.","en":f"Expected level: {ml_pred:.1f} c/ha, {delta:+.1f}% versus the historical district median."}[lang])
            else:
                st.write({"kk":f"Аудан-дақыл бойынша машиналық оқыту базалық болжамы: {ml_pred:.1f} ц/га.","ru":f"Базовый прогноз машинного обучения по району и культуре: {ml_pred:.1f} ц/га.","en":f"District-crop ML baseline: {ml_pred:.1f} c/ha."}[lang])
        elif crop == 'Barley':
            st.warning({"kk":"Арпа үшін машиналық оқыту арқылы өнімділікті болжау әдейі қосылмады: берілген бастапқы панельде арпа өнімділігі бидай қатарын қайталайды және дереккөзді қайта тексеру қажет.","ru":"Модель машинного обучения для прогнозирования урожайности ячменя намеренно не включена: в предоставленной исходной панели ряд урожайности ячменя дублирует пшеницу и требует проверки источника.","en":"Barley yield ML is intentionally disabled: the supplied source panel duplicates the wheat yield series and needs source verification."}[lang])

        obs_ev=observed_for_crop(used_district,crop)
        if not obs_ev.empty:
            st.markdown("#### " + {"kk":"2023 жылғы байқалған нарықтық дәлел","ru":"Наблюдаемое рыночное свидетельство 2023","en":"Observed 2023 market evidence"}[lang])
            r=obs_ev.iloc[0]
            st.write({"kk":f"Ауыл шаруашылығы кооперативтері бойынша іске асыру: {r['volume_t']:,.1f} т; құны {r['value_thousand_kzt']:,.0f} мың тг. Бұл дерек QŪNAR рейтингіне тікелей кірмейді.","ru":f"По сельхозкооперативам: реализация {r['volume_t']:,.1f} т; стоимость {r['value_thousand_kzt']:,.0f} тыс. тг. Эти данные показаны как контекст и напрямую не входят в рейтинг QŪNAR.","en":f"Agricultural cooperatives: {r['volume_t']:,.1f} t realized; value {r['value_thousand_kzt']:,.0f} thousand KZT. This evidence is contextual and does not directly enter the QŪNAR ranking."}[lang])

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
            with st.expander({'kk':'Машиналық оқыту бойынша өнімділік бағасы - 6 калибрленген егістік дақыл','ru':'Оценка урожайности машинным обучением - 6 откалиброванных полевых культур','en':'ML yield evidence - 6 calibrated field crops'}[lang]):
                with st.spinner(t['ml_loading']):
                    mlrank=timed_call("ML crop ranking", rank_crops, used_district, area_ha, climate, CROPS).copy()
                mlrank['Crop']=mlrank['Crop'].map(CROP_LABELS[lang])
                mlrank=mlrank.rename(columns={'Crop':t['ranking_crop'],'Predicted yield, centners/ha':t['ranking_yield']})
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
        alloc, opt = timed_call("Optimization", optimize_structure, used_district, area_ha, optimization_profile, optimization_max_share, optimization_n_crops, available_water, climate, irrigation_type)
        if alloc.empty:
            st.error({"kk":"Бұл аудан үшін оңтайландыру деректері табылмады.","ru":"Для этого района не найдены данные для оптимизации.","en":"No optimization data were found for this district."}[lang])
        else:
            name_col={"kk":"KK","ru":"RU","en":"EN"}[lang]
            out=alloc[[name_col,"share","area_ha","QUNAR_score_0_100","Climate_score_0_100","Resource_efficiency_0_100","Data_reliability_0_100","official_water_default_m3_ha","modelled_water_m3"]].copy()
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
            st.dataframe(out,use_container_width=True,hide_index=True)
            s1,s2,s3,s4=st.columns(4)
            s1.metric({"kk":"Құрылымның QŪNAR бағасы","ru":"Оценка структуры QŪNAR","en":"Structure QŪNAR score"}[lang],f"{opt['weighted_qunar']:.1f}/100")
            s2.metric({"kk":"Климаттық тұрақтылық","ru":"Климатическая устойчивость","en":"Climate resilience"}[lang],f"{opt['weighted_climate']:.1f}/100")
            s3.metric({"kk":"Ресурс тиімділігі","ru":"Ресурсоэффективность","en":"Resource efficiency"}[lang],f"{opt['weighted_resource']:.1f}/100")
            s4.metric({"kk":"Бағалау сенімділігі","ru":"Уверенность в оценке","en":"Assessment confidence"}[lang],f"{opt['weighted_reliability']:.1f}/100")
            st.success({
                "kk":f"Ұсынылған құрылым {area_ha:.1f} га аумақты {len(out)} дақыл арасында бөледі. Ең ірі үлес {out.iloc[0,1]:.1f}% деңгейінде.",
                "ru":f"Предлагаемая структура распределяет {area_ha:.1f} га между {len(out)} культурами. Наибольшая доля составляет {out.iloc[0,1]:.1f}%.",
                "en":f"The proposed structure allocates {area_ha:.1f} ha across {len(out)} crops. The largest share is {out.iloc[0,1]:.1f}%."
            }[lang])
            if opt.get("effective_max_share", optimization_max_share) > optimization_max_share + 1e-9:
                st.info({
                    "kk":f"Таңдалған дақыл саны үшін {optimization_max_share*100:.0f}% шегі математикалық тұрғыдан мүмкін емес. Есепте ең төмен мүмкін шек {opt['effective_max_share']*100:.1f}% қолданылды.",
                    "ru":f"Для выбранного числа культур ограничение {optimization_max_share*100:.0f}% математически невыполнимо. В расчете использован минимально допустимый предел {opt['effective_max_share']*100:.1f}%.",
                    "en":f"For the selected number of crops, a {optimization_max_share*100:.0f}% cap is infeasible. The minimum feasible cap of {opt['effective_max_share']*100:.1f}% was used."
                }[lang])
            st.markdown("#### " + {"kk":"Сценарийді түсіндіру","ru":"Интерпретация сценария","en":"Scenario interpretation"}[lang])
            st.write({
                "kk":f"Ұсынылған құрылымның орташа су нормасы {opt['weighted_water_m3_ha']:,.0f} м³/га, жалпы есептік қажеттілік {opt['modelled_total_water_m3']:,.0f} м³.",
                "ru":f"Средняя норма воды в рекомендуемой структуре {opt['weighted_water_m3_ha']:,.0f} м³/га, общая расчетная потребность {opt['modelled_total_water_m3']:,.0f} м³.",
                "en":f"The recommended structure averages {opt['weighted_water_m3_ha']:,.0f} m³/ha, with total modelled demand of {opt['modelled_total_water_m3']:,.0f} m³."
            }[lang])
            if available_water > 0:
                if opt.get("water_feasible"):
                    st.success({"kk":f"Су шектеуі орындалды: {opt['modelled_total_water_m3']:,.0f} м³ ≤ {available_water:,.0f} м³.","ru":f"Ограничение по воде соблюдено: {opt['modelled_total_water_m3']:,.0f} м³ ≤ {available_water:,.0f} м³.","en":f"Water constraint satisfied: {opt['modelled_total_water_m3']:,.0f} m³ ≤ {available_water:,.0f} m³."}[lang])
                else:
                    st.error({"kk":"Берілген су көлемімен таңдалған дақыл саны/үлес шектеулері шеңберінде толық орындалатын құрылым табылмады.","ru":"При указанном объеме воды не найдено полностью выполнимой структуры при текущем числе культур и ограничениях долей.","en":"No fully feasible structure was found under the entered water volume and current crop/share constraints."}[lang])
            if user_level == "researcher":
                with st.expander({"kk":"Оңтайландыру әдістемесі","ru":"Методика оптимизации","en":"Optimization method"}[lang]):
                    st.write({
                        "kk":f"Алдымен климат пен су жүктемесі бойынша Парето басымдығына түспейтін нұсқалар анықталады. Одан кейін таңдалған басымдық салмақтары бойынша жиынтық пайдалылық есептеліп, бір дақыл үлесі {optimization_max_share*100:.0f}% шегінен аспайтындай етіп аудан бөлінеді. Су жүктемесі ресми немесе дерек болмаған жағдайда ашық белгіленген есептік м³/га нормаларына негізделеді; нарықтық бағаның жанама көрсеткіші қолданылмайды.",
                        "ru":f"Структура решается как задача линейного программирования: максимизируется ресурсно-климатическая полезность при равенстве суммарной площади, ограничении доли одной культуры не выше {optimization_max_share*100:.0f}% и, при заданном объеме воды, жестком водном ограничении. Уверенность в данных не входит в целевую функцию. Косвенный рыночный показатель цены исключен.",
                        "en":f"First, Pareto non-dominated options are identified across climate, water efficiency and evidence reliability. Utility is then computed with the selected weights and land is allocated with a single-crop cap of {optimization_max_share*100:.0f}%. Water pressure uses official/explicitly labelled fallback m³/ha norms; the market-price proxy is excluded."
                    }[lang])


    # v0.8 economic contour: transparent scenario, never a hidden-price profit claim.
    if crop is not None and selling_price_kzt_t > 0:
        econ_yield = expected_yield_c_ha if expected_yield_c_ha > 0 else (pred if "pred" in locals() else None)
        if econ_yield is not None:
            econ08 = economic_feasibility(
                yield_centners_ha=econ_yield,
                selling_price_kzt_t=selling_price_kzt_t,
                variable_cost_kzt_ha=variable_cost_kzt_ha,
                water_m3_ha=(effective_water_used/area_ha if effective_water_used > 0 and area_ha > 0 else 0.0),
                water_tariff_kzt_m3=water_tariff,
                energy_kwh_ha=(energy/area_ha if energy > 0 and area_ha > 0 else 0.0),
                electricity_tariff_kzt_kwh=electricity_tariff,
            )
            st.markdown("### " + {"kk":"Экономикалық орындылық","ru":"Экономическая целесообразность","en":"Economic feasibility"}[lang])
            e1,e2,e3=st.columns(3)
            e1.metric({"kk":"Жалпы түсім, тг/га","ru":"Валовая выручка, тг/га","en":"Gross revenue, KZT/ha"}[lang], f"{econ08['gross_revenue_kzt_ha']:,.0f}")
            e2.metric({"kk":"Ресурстық шығын, тг/га","ru":"Стоимость воды и энергии, тг/га","en":"Water + energy cost, KZT/ha"}[lang], f"{econ08['resource_cost_kzt_ha']:,.0f}")
            e3.metric({"kk":"Салым маржасы, тг/га","ru":"Маржинальный результат, тг/га","en":"Contribution margin, KZT/ha"}[lang], f"{econ08['contribution_margin_kzt_ha']:,.0f}")
            st.caption({
                "kk":"Бұл нәтиже таза пайда емес: ол енгізілген баға, айнымалы шығындар, су және энергия шығындары негізіндегі сценарийлік маржа.",
                "ru":"Этот результат не равен чистой прибыли: это сценарная маржа на основе введенной цены, переменных затрат и учтенных расходов на воду и энергию.",
                "en":"This is not net profit. It is a scenario contribution margin based on the entered price, variable costs, water and energy costs."
            }[lang])
            report_payload["summary"].append({"label":{"kk":"Маржиналды нәтиже, тг/га","ru":"Маржинальный результат, тг/га","en":"Contribution margin, KZT/ha"}[lang],"value":f"{econ08['contribution_margin_kzt_ha']:,.0f}"})
        else:
            st.info({"kk":"Экономикалық контур үшін күтілетін өнімділікті енгізіңіз.","ru":"Для экономического контура укажите ожидаемую урожайность.","en":"Enter expected yield to activate the economic contour."}[lang])

    if mode_key in ("mode1","mode2") and crop is not None:
        env = environmental_diagnostics(
            used_district, climate, area_ha, energy_kwh=energy,
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
        div = diversification_metrics(pd.to_numeric(out["share"], errors="coerce").fillna(0).tolist())
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
            _row("Есепте қолданылған мал саны, бас", "Поголовье в расчете, голов", "Herd used in calculation, head", livestock.get("heads")),
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
            report_payload["summary"].append({"label":t["baseline_label"], "value":f"{pred:.1f} {UNITS['centner_ha']}"})
        elif "scenario" in locals() and scenario is not None:
            report_payload["summary"].append({"label":{"kk":"QŪNAR бағасы","ru":"Оценка QŪNAR","en":"QŪNAR score"}[lang], "value":f"{float(scenario['QUNAR_score_0_100']):.1f}/100"})
        if "resource" in locals():
            if resource.get("farm_freshwater_m3") is not None: report_payload["summary"].append({"label":t["freshwater"],"value":f"{resource['farm_freshwater_m3']:,.0f} {UNITS['m3']}"})
            if resource.get("energy_kwh") is not None: report_payload["summary"].append({"label":t["energy_use"],"value":f"{resource['energy_kwh']:,.0f} {UNITS['kwh']}"})
            if resource.get("operational_co2e_kg") is not None: report_payload["summary"].append({"label":t["co2"],"value":f"{resource['operational_co2e_kg']:,.0f} {UNITS['kg']} CO₂e"})
        if "econ" in locals():
            report_payload["summary"].append({"label":t["total_saving"],"value":f"{econ['total_saving_kzt']:,.0f} {UNITS['currency']}"})
        report_payload["analysis"] = list(locals().get("analysis", []) or [])
        report_payload["recommendations"] = structured_recommendations(locals().get("recs", []) or [], report_payload["analysis"], lang)
        if "econ" in locals() and float(econ.get("total_saving_kzt", 0) or 0) > 0:
            report_payload["recommendations"].insert(0, {
                "title":{"kk":"Экономикалық және климаттық басымдық","ru":"Экономико-климатический приоритет","en":"Economic and climate priority"}[lang],
                "text":{"kk":"Жасыл энергия мен су үнемдеу сценарийін кезең-кезеңімен қарастыру ұсынылады.","ru":"Рекомендуется поэтапно рассмотреть сценарий зеленой энергии и водосбережения.","en":"Consider a phased green-energy and water-saving scenario."}[lang],
                "evidence":{"kk":f"Ағымдағы параметрлерде маусымдық әлеуетті үнем шамамен {econ['total_saving_kzt']:,.0f} тг: электр энергиясынан {econ.get('energy_saving_kzt',0):,.0f} тг және судан {econ.get('water_saving_kzt',0):,.0f} тг.","ru":f"При текущих параметрах потенциальная сезонная экономия составляет около {econ['total_saving_kzt']:,.0f} тг: {econ.get('energy_saving_kzt',0):,.0f} тг по электроэнергии и {econ.get('water_saving_kzt',0):,.0f} тг по воде.","en":f"Under the current inputs, potential seasonal savings are about {econ['total_saving_kzt']:,.0f} KZT: {econ.get('energy_saving_kzt',0):,.0f} KZT from electricity and {econ.get('water_saving_kzt',0):,.0f} KZT from water."}[lang],
                "effect":{"kk":f"Электр энергиясынан CO₂ төмендеуі шамамен {econ.get('co2_reduction_kg',0)/1000:.2f} т CO₂e және су үнемі {econ.get('water_saving_m3',0):,.0f} м³ болуы мүмкін. Бұл сценарийлік бағалау, нақты инвестициялық шешім алдында тарифтер мен жабдық құнын нақтылау керек.","ru":f"Потенциальное снижение выбросов от электроэнергии - около {econ.get('co2_reduction_kg',0)/1000:.2f} т CO₂e, экономия воды - {econ.get('water_saving_m3',0):,.0f} м³. Это сценарная оценка, поэтому перед инвестиционным решением следует уточнить тарифы и стоимость оборудования.","en":f"Potential electricity-related reduction is about {econ.get('co2_reduction_kg',0)/1000:.2f} t CO₂e and water saving {econ.get('water_saving_m3',0):,.0f} m³. This is a scenario estimate, so tariffs and equipment costs should be verified before investment."}[lang],
                "evidence_label":{"kk":"Сандық негіздеме","ru":"Количественное основание","en":"Quantitative evidence"}[lang],
                "effect_label":{"kk":"Күтілетін әсер","ru":"Ожидаемый эффект","en":"Expected effect"}[lang],
            })
        if "econ" in locals():
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
            report_payload["summary"] = [{"label":{"kk":"Күтілетін өнімділік","ru":"Ожидаемая урожайность","en":"Expected yield"}[lang],"value":f"{ml_pred:.1f} {UNITS['centner_ha']}"}]
    elif mode_key == "mode3" and "ranking" in locals():
        report_payload["table"] = ranking[keep].to_dict(orient="records")
        top_row = ranking.iloc[0]
        top_name = str(top_row.iloc[1])
        top_score = float(top_row[{'kk':'QŪNAR жалпы бағасы','ru':'Общий балл QŪNAR','en':'QŪNAR overall score'}[lang]])
        report_payload["recommendations"] = [{
            "title":{"kk":"Негізгі таңдау","ru":"Приоритетный выбор","en":"Priority choice"}[lang],
            "text":{"kk":f"{top_name} ағымдағы критерийлер бойынша бірінші орында. Оны автоматты шешім емес, бастапқы басым нұсқа ретінде қарастырыңыз.","ru":f"{top_name} занимает первое место по текущему набору критериев. Рассматривайте его как приоритетный вариант для дальнейшей проверки, а не как автоматическое решение.","en":f"{top_name} ranks first under the current criteria. Treat it as the priority option for further verification, not an automatic decision."}[lang],
            "evidence":{"kk":f"QŪNAR жалпы бағасы {top_score:.1f}/100; рейтинг климатты, су тиімділігін және дерек сенімділігін бірге салыстырады.","ru":f"Общий балл QŪNAR {top_score:.1f}/100; рейтинг учитывает климат, водную эффективность и надежность исходных данных.","en":f"QŪNAR overall score is {top_score:.1f}/100; the ranking combines climate, water efficiency and evidence reliability."}[lang],
            "effect":{"kk":"Келесі қадам - топ-3 нұсқаны су қолжетімділігі, технология және нарықтық жағдай бойынша салыстыру.","ru":"Следующий шаг - сопоставить три лучших варианта по доступности воды, технологии выращивания и рыночным условиям.","en":"Next, compare the top three options against water availability, production technology and market conditions."}[lang],
            "evidence_label":{"kk":"Негіздеме","ru":"Основание","en":"Evidence"}[lang],
            "effect_label":{"kk":"Келесі қадам","ru":"Следующий шаг","en":"Next step"}[lang],
        }]
        score_col={'kk':'QŪNAR жалпы бағасы','ru':'Общий балл QŪNAR','en':'QŪNAR overall score'}[lang]
        crop_col={'kk':'Дақыл','ru':'Культура','en':'Crop'}[lang]
        top5=ranking.head(5)
        report_payload["chart"]={"title":{"kk":"QŪNAR бойынша үздік 5 дақыл","ru":"5 лучших культур по QŪNAR","en":"QŪNAR top 5 crops"}[lang],"section_title":{"kk":"Салыстырмалы рейтинг","ru":"Сравнительный рейтинг","en":"Comparative ranking"}[lang],"categories":top5[crop_col].astype(str).tolist(),"values":pd.to_numeric(top5[score_col],errors='coerce').fillna(0).astype(float).tolist(),"value_label":"0-100","axis_label":"0-100"}
    elif mode_key == "mode4" and "out" in locals():
        report_payload["table"] = out.to_dict(orient="records")
        if "opt" in locals():
            report_payload["summary"] = [
                {"label":{"kk":"Құрылымның QŪNAR бағасы","ru":"Оценка структуры QŪNAR","en":"Structure QŪNAR score"}[lang],"value":f"{opt['weighted_qunar']:.1f}/100"},
                {"label":{"kk":"Климаттық тұрақтылық","ru":"Климатическая устойчивость","en":"Climate resilience"}[lang],"value":f"{opt['weighted_climate']:.1f}/100"},
                {"label":{"kk":"Ресурс тиімділігі","ru":"Ресурсоэффективность","en":"Resource efficiency"}[lang],"value":f"{opt['weighted_resource']:.1f}/100"},
                {"label":{"kk":"Бағалау сенімділігі","ru":"Уверенность в оценке","en":"Assessment confidence"}[lang],"value":f"{opt['weighted_reliability']:.1f}/100"},
                {"label":{"kk":"Есептік су қажеттілігі","ru":"Расчетная потребность в воде","en":"Modelled water demand"}[lang],"value":f"{opt['modelled_total_water_m3']:,.0f} м³"},
            ]
            first_crop=str(out.iloc[0,0]); first_share=float(out.iloc[0,1])
            report_payload["recommendations"]=[{
                "title":{"kk":"Ұсынылатын құрылым","ru":"Рекомендуемая структура","en":"Recommended structure"}[lang],
                "text":{"kk":f"Егістік ауданды {len(out)} дақыл арасында бөлу ұсынылады; ең ірі үлес {first_crop} үшін {first_share:.1f}%.","ru":f"Рекомендуется распределить посевную площадь между {len(out)} культурами; наибольшая доля {first_share:.1f}% приходится на {first_crop}.","en":f"Allocate the cultivated area across {len(out)} crops; the largest share is {first_share:.1f}% for {first_crop}."}[lang],
                "evidence":{"kk":f"Құрылымның QŪNAR бағасы {opt['weighted_qunar']:.1f}/100, климаттық тұрақтылығы {opt['weighted_climate']:.1f}/100 және ресурс тиімділігі {opt['weighted_resource']:.1f}/100.","ru":f"Оценка структуры QŪNAR {opt['weighted_qunar']:.1f}/100, климатическая устойчивость {opt['weighted_climate']:.1f}/100 и ресурсоэффективность {opt['weighted_resource']:.1f}/100.","en":f"Structure QŪNAR score {opt['weighted_qunar']:.1f}/100, climate resilience {opt['weighted_climate']:.1f}/100 and resource efficiency {opt['weighted_resource']:.1f}/100."}[lang],
                "effect":{"kk":"Бұл әртараптандыру бір дақылға тәуелділікті азайтып, климат, су жүктемесі және дерек сенімділігі арасындағы теңгерімді сақтауға бағытталған.","ru":"Такая диверсификация направлена на снижение зависимости от одной культуры и сохранение баланса между климатической устойчивостью, водной нагрузкой и надежностью данных.","en":"This diversification is intended to reduce single-crop dependence while balancing climate resilience, water demand and evidence reliability."}[lang],
                "evidence_label":{"kk":"Негіздеме","ru":"Основание","en":"Evidence"}[lang],
                "effect_label":{"kk":"Күтілетін әсер","ru":"Ожидаемый эффект","en":"Expected effect"}[lang],
            }]
            report_payload["chart"]={"title":{"kk":"Ұсынылатын егіс құрылымы","ru":"Рекомендуемая структура посевов","en":"Recommended cropping structure"}[lang],"section_title":{"kk":"Ауданның бөлінуі","ru":"Распределение площади","en":"Land allocation"}[lang],"categories":out.iloc[:,0].astype(str).tolist(),"values":pd.to_numeric(out.iloc[:,1],errors='coerce').fillna(0).astype(float).tolist(),"value_label":"%","axis_label":"%"}

    st.session_state["last_report_payload"] = report_payload
    st.markdown('<div class="qunar-export"></div>', unsafe_allow_html=True)
    render_export_panel(report_payload, lang)

    _timings["Total rerun"] = time.perf_counter() - _run_started
    if user_level == "researcher":
        with st.expander({"kk":"Өнімділік диагностикасы","ru":"Диагностика производительности","en":"Performance diagnostics"}[lang]):
            perf_df = pd.DataFrame([{"Этап":k, "Секунды":round(v,3)} for k,v in sorted(_timings.items(), key=lambda x:-x[1])])
            st.dataframe(perf_df, use_container_width=True, hide_index=True)
            st.caption({"kk":"Бұл блок лагтың нақты қай кезеңде пайда болатынын анықтауға көмектеседі.","ru":"Этот блок показывает, какой этап реально занимает время, чтобы не оптимизировать приложение наугад.","en":"This shows which stage actually takes time, so performance work can target the real bottleneck."}[lang])

st.divider()
st.caption(t["footer"])

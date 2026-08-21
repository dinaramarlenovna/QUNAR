
import pandas as pd
import streamlit as st
from .config import DATA_DIR
from .data import district_crop_context

@st.cache_data(show_spinner=False)
def _panel():
    return pd.read_csv(DATA_DIR / "analytical_panel.csv")

@st.cache_data(show_spinner=False)
def _yield_context():
    df = _panel()
    out = {}
    for (district, crop), g in df.groupby(["District", "Crop"]):
        s = pd.to_numeric(g["Yield, centners/ha"], errors="coerce").dropna()
        if len(s) >= 3:
            out[(district, crop)] = {
                "median": float(s.median()),
                "q25": float(s.quantile(.25)),
                "q75": float(s.quantile(.75)),
                "n": int(len(s)),
            }
    return out

@st.cache_data(show_spinner=False)
def _climate_context():
    df = _panel()
    cols = [
        "Apr-Sep temperature, °C",
        "Apr-Sep precipitation, mm",
    ]
    out = {}
    for district, g in df.groupby("District"):
        out[district] = {}
        for c in cols:
            s = pd.to_numeric(g[c], errors="coerce").dropna()
            if len(s) >= 5:
                out[district][c] = {
                    "mean": float(s.mean()),
                    "std": float(s.std(ddof=1)),
                }
    return out

def _pct_delta(v, b):
    return None if b in (None, 0) or v is None else (float(v)/float(b)-1)*100

def _z(v, mean, std):
    return None if v is None or mean is None or not std else (float(v)-float(mean))/float(std)

def _reliability_text(lang, reliability):
    flags = reliability.get("components", {})
    missing = [k for k, v in flags.items() if not v]
    maps = {
        "kk":{
            "field_geometry":"өрістің нақты шекарасы/орны",
            "live_climate":"өзекті климаттық деректер",
            "actual_water":"нақты су тұтыну",
            "actual_energy":"нақты энергия тұтыну",
            "emission_factor":"тексерілген эмиссия коэффициенті",
        },
        "ru":{
            "field_geometry":"точная граница/геопозиция поля",
            "live_climate":"актуальные климатические данные",
            "actual_water":"фактическое водопотребление",
            "actual_energy":"фактическое энергопотребление",
            "emission_factor":"проверенный коэффициент выбросов",
        },
        "en":{
            "field_geometry":"exact field boundary/location",
            "live_climate":"current climate data",
            "actual_water":"actual water use",
            "actual_energy":"actual energy use",
            "emission_factor":"verified emission factor",
        },
    }
    if lang == "kk":
        text = "Есептің сенімділігі"
        if missing:
            text += " мына деректердің болмауына байланысты төмендейді: " + ", ".join(maps.get(lang, maps["en"]).get(k, {"exact_location":{"kk":"өрістің нақты шекарасы","ru":"точная граница поля","en":"exact field boundary"}}.get(k, {}).get(lang, str(k).replace("_", " "))) for k in missing) + "."
        else:
            text += " жоғары, себебі негізгі бастапқы деректер тікелей алынған."
        if reliability.get("spatial_penalty", 0):
            text += f" WaPOR кеңістіктік қамтуы шектеулі болғандықтан сенімділік балынан {reliability['spatial_penalty']} тармақ шегерілді."
        return text
    if lang == "en":
        text = "Estimate reliability"
        if missing:
            text += " is reduced because these inputs are unavailable: " + ", ".join(maps.get(lang, maps["en"]).get(k, {"exact_location":{"kk":"өрістің нақты шекарасы","ru":"точная граница поля","en":"exact field boundary"}}.get(k, {}).get(lang, str(k).replace("_", " "))) for k in missing) + "."
        else:
            text += " is high because the main inputs are directly observed."
        if reliability.get("spatial_penalty", 0):
            text += f" {reliability['spatial_penalty']} points were deducted because WaPOR spatial support is limited."
        return text
    text = "Надежность оценки"
    if missing:
        text += " снижена из-за отсутствия следующих исходных данных: " + ", ".join(maps.get(lang, maps["en"]).get(k, {"exact_location":{"kk":"өрістің нақты шекарасы","ru":"точная граница поля","en":"exact field boundary"}}.get(k, {}).get(lang, str(k).replace("_", " "))) for k in missing) + "."
    else:
        text += " высокая, поскольку основные исходные данные получены непосредственно."
    if reliability.get("spatial_penalty", 0):
        text += f" Дополнительно вычтено {reliability['spatial_penalty']} баллов из-за ограниченного пространственного покрытия WaPOR."
    return text

def build_analysis(
    lang, district, crop_label, crop_code, pred_yield, climate, resource,
    reliability, available_water=None, wapor_result=None
):
    yctx = district_crop_context(district, crop_code)
    cctx = _climate_context().get(district, {})
    temp = climate.get("Apr-Sep temperature, °C")
    precip = climate.get("Apr-Sep precipitation, mm")
    tz = _z(temp, cctx.get("Apr-Sep temperature, °C", {}).get("mean"),
            cctx.get("Apr-Sep temperature, °C", {}).get("std"))
    pz = _z(precip, cctx.get("Apr-Sep precipitation, mm", {}).get("mean"),
            cctx.get("Apr-Sep precipitation, mm", {}).get("std"))

    fw = resource.get("farm_freshwater_m3")
    wt = resource.get("farm_water_total_m3")
    reused = resource.get("farm_water_reused_m3")
    energy = resource.get("energy_kwh")
    co2 = resource.get("operational_co2e_kg")
    wcw = resource.get("wapor_consumptive_water_total_m3")
    wwp = resource.get("modelled_water_productivity_kg_m3")
    parts = []

    # Productivity interpretation
    if yctx:
        d = _pct_delta(pred_yield, yctx["historical_yield_median"])
        if lang == "kk":
            if d is not None and d >= 10:
                parts.append(f"{crop_label} бойынша болжамды өнімділік {pred_yield:.1f} ц/га, бұл ауданның тарихи медианасынан шамамен {abs(d):.1f}% жоғары. Өндірістік әлеует жақсы көрінеді, бірақ ресурстық тиімділік су мен энергия көрсеткіштерімен бірге бағалануы тиіс.")
            elif d is not None and d <= -10:
                parts.append(f"{crop_label} бойынша болжамды өнімділік {pred_yield:.1f} ц/га, тарихи медианадан шамамен {abs(d):.1f}% төмен. Мұндай жағдайда ресурстарды көбейтуден бұрын климаттық және технологиялық шектеулерді тексеру маңызды.")
            else:
                parts.append(f"{crop_label} бойынша болжамды өнімділік {pred_yield:.1f} ц/га және ауданның тарихи медианасына жақын. Негізгі резерв су, энергия және климаттық тәуекелдерді басқаруда болуы мүмкін.")
        elif lang == "en":
            relation = "above" if d is not None and d >= 0 else "below"
            parts.append(f"Predicted yield for {crop_label} is {pred_yield:.1f} centners/ha, about {abs(d or 0):.1f}% {relation} the district's historical median. This is a productivity signal, not a complete resource-efficiency score.")
        else:
            if d is not None and d >= 10:
                parts.append(f"Прогнозируемая урожайность культуры «{crop_label}» составляет {pred_yield:.1f} ц/га, примерно на {abs(d):.1f}% выше исторической медианы по району. Производственный потенциал выглядит благоприятно, но ресурсоэффективность следует оценивать совместно с водой и энергией.")
            elif d is not None and d <= -10:
                parts.append(f"Прогнозируемая урожайность культуры «{crop_label}» составляет {pred_yield:.1f} ц/га, примерно на {abs(d):.1f}% ниже исторической медианы. В таком сценарии важно сначала проверить климатические и технологические ограничения, а не автоматически наращивать ресурсы.")
            else:
                parts.append(f"Прогнозируемая урожайность культуры «{crop_label}» составляет {pred_yield:.1f} ц/га и близка к исторической медиане района. Основной резерв эффективности вероятнее связан с водой, энергией и управлением климатическим риском.")
    else:
        if lang == "kk":
            parts.append(f"{crop_label} бойынша болжамды өнімділік {pred_yield:.1f} ц/га. Бұл аудан-дақыл жұбы үшін тарихи салыстыру шектеулі, сондықтан жүйе артық қорытынды жасамайды.")
        elif lang == "en":
            parts.append(f"Predicted yield for {crop_label} is {pred_yield:.1f} centners/ha. Historical comparison for this district-crop pair is limited, so the system avoids over-interpreting it.")
        else:
            parts.append(f"Прогнозируемая урожайность культуры «{crop_label}» составляет {pred_yield:.1f} ц/га. Историческая база для этой пары «район-культура» ограничена, поэтому система не делает избыточных выводов.")

    # Climate interpretation
    climate_notes = []
    if tz is not None and tz >= 1: climate_notes.append(("warm","жылырақ","теплее обычного"))
    elif tz is not None and tz <= -1: climate_notes.append(("cool","салқындау","прохладнее обычного"))
    if pz is not None and pz <= -1: climate_notes.append(("dry","жауын-шашын төмен","осадков меньше обычного"))
    elif pz is not None and pz >= 1: climate_notes.append(("wet","жауын-шашын жоғары","осадков больше обычного"))

    if lang == "kk":
        if climate_notes:
            parts.append("Климаттық профиль тарихи жағдайдан ауытқуды көрсетеді: " + ", ".join(x[1] for x in climate_notes) + ". Сондықтан нәтиже су қолжетімділігімен және климаттық тәуекелмен бірге қарастырылуы тиіс.")
        else:
            parts.append("Температура мен жауын-шашын ауданның тарихи диапазонынан күрт ауытқымайды; ағымдағы есепте экстремалды климаттық сигнал байқалмайды.")
    elif lang == "en":
        if climate_notes:
            parts.append("The climate profile departs from the district's historical pattern: " + ", ".join(x[0] for x in climate_notes) + ". Interpret the result together with water availability and climate risk.")
        else:
            parts.append("Temperature and precipitation do not show a large departure from the district's historical range; no strong climate-extreme signal is detected in this calculation.")
    else:
        if climate_notes:
            parts.append("Климатический профиль отклоняется от исторического режима района: " + ", ".join(x[2] for x in climate_notes) + ". Результат следует интерпретировать совместно с доступностью воды и климатическим риском.")
        else:
            parts.append("Температура и осадки не демонстрируют сильного отклонения от исторического диапазона района; выраженного климатического экстремума в текущем расчете не выявлено.")

    # Farm water balance
    if wt is not None:
        if lang == "kk":
            if reused and reused > 0:
                parts.append(f"Қайта пайдалану есебінен {reused:,.0f} м³ су айналымға қайтарылады, сондықтан тұщы суға есептік қажеттілік {fw:,.0f} м³ дейін төмендейді.")
            if available_water and fw is not None:
                bal = float(available_water) - float(fw)
                parts.append(f"Су балансы {'тапшылықты' if bal < 0 else 'резервті'} көрсетеді: {abs(bal):,.0f} м³.")
        elif lang == "en":
            if reused and reused > 0:
                parts.append(f"Water reuse returns {reused:,.0f} m³ to the farm water cycle, reducing calculated freshwater demand to {fw:,.0f} m³.")
            if available_water and fw is not None:
                bal = float(available_water) - float(fw)
                parts.append(f"The water balance shows a {'deficit' if bal < 0 else 'reserve'} of {abs(bal):,.0f} m³.")
        else:
            if reused and reused > 0:
                parts.append(f"Повторное использование возвращает в хозяйственный водный цикл {reused:,.0f} м³, поэтому расчетная потребность в свежей воде снижается до {fw:,.0f} м³.")
            if available_water and fw is not None:
                bal = float(available_water) - float(fw)
                parts.append(f"Водный баланс показывает {'дефицит' if bal < 0 else 'резерв'} около {abs(bal):,.0f} м³.")

    # WaPOR interpretation
    if wcw is not None:
        if lang == "kk":
            msg = f"FAO WaPOR бойынша маусымдық тұтынылған су шамамен {wcw:,.0f} м³."
            if wwp is not None: msg += f" Болжамды өніммен біріктірілген модельдік су өнімділігі {wwp:.2f} кг/м³."
            msg += " Бұл суару жүйесінен алынған су көлемі емес, нақты эвапотранспирацияға негізделген спутниктік көрсеткіш."
            parts.append(msg)
        elif lang == "en":
            msg = f"FAO WaPOR indicates about {wcw:,.0f} m³ of seasonal consumptive water use."
            if wwp is not None: msg += f" Combined with predicted production, modelled water productivity is {wwp:.2f} kg/m³."
            msg += " This is not irrigation withdrawal; it is a satellite-derived evapotranspiration indicator."
            parts.append(msg)
        else:
            msg = f"По FAO WaPOR сезонное потребительное водоиспользование составляет около {wcw:,.0f} м³."
            if wwp is not None: msg += f" При объединении с прогнозируемым выпуском модельная водная продуктивность составляет {wwp:.2f} кг/м³."
            msg += " Это не объем водозабора из канала или скважины, а спутниковая оценка на основе фактической эвапотранспирации."
            parts.append(msg)

    # Energy / carbon
    if energy is not None:
        if lang == "kk":
            parts.append(f"Энергия тұтынуы {energy:,.0f} кВт·сағ. " + (f"Енгізілген эмиссия коэффициентімен операциялық көміртек ізі {co2:,.0f} кг CO₂e." if co2 is not None else "Тексерілген эмиссия коэффициенті болмағандықтан CO₂e әдейі есептелмейді."))
        elif lang == "en":
            parts.append(f"Energy use is {energy:,.0f} kWh. " + (f"With the entered emission factor, operational carbon is {co2:,.0f} kg CO₂e." if co2 is not None else "CO₂e is intentionally not calculated because no verified emission factor is available."))
        else:
            parts.append(f"Энергопотребление составляет {energy:,.0f} кВт·ч. " + (f"При введенном коэффициенте эмиссии операционная углеродная нагрузка равна примерно {co2:,.0f} кг CO₂e." if co2 is not None else "CO₂e намеренно не рассчитывается, поскольку проверенный коэффициент эмиссии не задан."))

    parts.append(_reliability_text(lang, reliability))
    return parts


def build_recommendations(lang, pred_yield, historical_median, available_water, resource, t):
    recs = []
    fw = resource.get("farm_freshwater_m3")
    if available_water and fw is not None:
        if float(available_water) < float(fw):
            recs.append(t["rec_water_deficit"])
        else:
            recs.append(t["rec_water_ok"])
    if historical_median:
        delta = (float(pred_yield) / float(historical_median) - 1.0) * 100.0
        recs.append(t["rec_low_baseline"] if delta <= -10 else t["rec_baseline_ok"])
    if resource.get("energy_kwh") is not None and resource.get("operational_co2e_kg") is None:
        recs.append(t["rec_no_co2"])
    return recs

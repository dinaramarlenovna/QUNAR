
def explain(lang,crop,pred_yield,resource,reliability,climate_source):
    water=resource.get("water_m3_per_ha"); energy=resource.get("energy_kwh_per_ha")
    co2=resource.get("operational_co2e_kg_per_ha")
    if lang=="kk":
        p=[f"Жүйе {crop} үшін болжамды өнімділікті {pred_yield:.1f} ц/га деңгейінде бағалады.",
           f"Климаттық дерек көзі: {climate_source}.",
           f"Есептің сенімділік деңгейі: {reliability['level']}, {reliability['score']}/100."]
        if water is not None:p.append(f"Нақты су деректері бойынша жүктеме {water:,.0f} м³/га.")
        if energy is not None:p.append(f"Нақты энергия деректері бойынша жүктеме {energy:,.0f} кВт·сағ/га.")
        if co2 is not None:p.append(f"Операциялық көміртек жүктемесі {co2:,.1f} кг CO₂e/га.")
        return " ".join(p)
    if lang=="en":
        p=[f"The system estimates {pred_yield:.1f} centners/ha for {crop}.",
           f"Climate source: {climate_source}.",
           f"Input reliability: {reliability['level']} ({reliability['score']}/100)."]
        if water is not None:p.append(f"Actual water input equals {water:,.0f} m³/ha.")
        if energy is not None:p.append(f"Actual energy input equals {energy:,.0f} kWh/ha.")
        if co2 is not None:p.append(f"Operational carbon equals {co2:,.1f} kg CO₂e/ha.")
        return " ".join(p)
    p=[f"Система оценила прогнозируемую урожайность культуры {crop} на уровне {pred_yield:.1f} ц/га.",
       f"Источник климатических данных: {climate_source}.",
       f"Надежность исходных данных: {reliability['level']} ({reliability['score']}/100)."]
    if water is not None:p.append(f"Фактическая водная нагрузка составляет {water:,.0f} м³/га.")
    if energy is not None:p.append(f"Фактическое энергопотребление составляет {energy:,.0f} кВт·ч/га.")
    if co2 is not None:p.append(f"Операционная углеродная нагрузка составляет {co2:,.1f} кг CO₂e/га.")
    return " ".join(p)

"""Report-only presentation for irrigation economics; does not alter calculation results.

The irrigation-switch scenario is independent of generic water/energy savings
scenarios. A decline in contribution margin must never be described as a
profitable irrigation-switch recommendation.
"""


def irrigation_export(comp, *, area_ha, input_yield_centners_ha,
                      ml_yield_centners_ha, selling_price_kzt_t,
                      other_variable_cost_kzt_ha,
                      extra_technology_cost_kzt_ha, yield_change_pct,
                      evidence, lang="ru", available_water_m3=0.0, reuse_pct=0.0):
    languages = {
        "ru": {
            "area": "Сценарий смены полива: площадь, га",
            "yield": "Урожайность для расчёта маржи (ввод), ц/га",
            "ml": "Отдельный базовый прогноз ML, ц/га",
            "price": "Цена реализации для расчёта, тг/т",
            "cost": "Прочие переменные затраты, тг/га",
            "extra": "Дополнительные расходы новой технологии, тг/га",
            "source": "Основание сценарного изменения урожайности",
            "yield_change": "Изменение урожайности от полива, %",
            "water_base": "Смена полива: исходная подача воды, м³/га",
            "water_new": "Смена полива: новая подача воды, м³/га",
            "water_saving": "Смена полива: экономия подачи воды, м³ за сезон",
            "gross_total_base": "Смена полива: потребность исходной технологии, м³ за сезон",
            "gross_total_new": "Смена полива: потребность новой технологии, м³ за сезон",
            "fresh_total_base": "Смена полива: забор свежей воды исходной технологии, м³",
            "fresh_total_new": "Смена полива: забор свежей воды новой технологии, м³",
            "reuse": "Повторное использование воды, % (сценарное допущение)",
            "water_cap": "Доступный лимит свежей воды, м³",
            "base_water_status": "Водный лимит: исходная технология",
            "new_water_status": "Водный лимит: новая технология",
            "overall_margin": "Общий расчёт маржи и сравнение орошения имеют разные базы расхода воды",
            "yes": "соблюдён", "no": "превышен", "unknown": "лимит не введён",
            "margin_base": "Смена полива: исходная маржа, тг/га",
            "margin_new": "Смена полива: новая маржа, тг/га",
            "delta": "Смена полива: изменение маржи, тг за сезон",
            "stress_base": "Стресс-тест: маржа исходного полива, тг/га",
            "stress_new": "Стресс-тест: маржа нового полива, тг/га",
            "stress_delta": "Стресс-тест: изменение маржи, тг за сезон",
            "stress_note": "Стресс-тест: цена -10%, урожайность -10%, расходы +10% одновременно в обоих вариантах.",
            "separate": "Расчёт смены полива отделён от сценариев зелёной энергии и общего ресурсосбережения; их экономию нельзя складывать без единой совместной модели.",
            "title": "Результат смены орошения: вода и экономический риск",
            "bad": "Экономия воды есть, но новая технология снижает расчётную маржу. Не рекомендовать переход как способ увеличить доход при этих исходных условиях.",
            "good": "Новая технология в этом сценарии экономит воду и увеличивает расчётную маржу. Решение зависит от подтверждения цен, затрат и инвестиционной стоимости.",
            "neutral": "Сценарий показывает компромисс между водопотреблением и маржой; требуется проверить условия внедрения.",
            "evidence": "Экономическая модель с заданными пользователем параметрами и коэффициентами водопотребления.",
            "effect": "Стресс-тест одинаков для обеих технологий. Эффект не является фактически измеренной прибылью и не включает неуказанные капитальные вложения.",
        },
        "kk": {
            "area": "Суару сценарийінің ауданы, га",
            "yield": "Маржа есебіндегі пайдаланушы өнімділігі, ц/га",
            "ml": "ML базалық болжамы (бөлек), ц/га",
            "price": "Сату бағасы, тг/т",
            "cost": "Өзге айнымалы шығындар, тг/га",
            "extra": "Жаңа технологияның қосымша шығындары, тг/га",
            "source": "Өнімділік өзгерісінің дереккөзі немесе болжам",
            "yield_change": "Суаруға байланысты өнімділік өзгерісі, %",
            "water_base": "Суару: бастапқы су беру, м³/га",
            "water_new": "Суару: жаңа су беру, м³/га",
            "water_saving": "Суару: маусымдық су үнемі, м³",
            "gross_total_base": "Бастапқы суару: жалпы су беру, м³/маусым",
            "gross_total_new": "Жаңа суару: жалпы су беру, м³/маусым",
            "fresh_total_base": "Бастапқы суару: жаңа су алу, м³",
            "fresh_total_new": "Жаңа суару: жаңа су алу, м³",
            "reuse": "Суды қайта пайдалану, % (сценарий шарты)",
            "water_cap": "Қолжетімді жаңа су лимиті, м³",
            "base_water_status": "Бастапқы суару: су лимитінің сақталуы",
            "new_water_status": "Жаңа суару: су лимитінің сақталуы",
            "overall_margin": "Жалпы маржа есебі мен суару салыстыруының су негіздері бөлек",
            "yes": "сақталған", "no": "асқан", "unknown": "лимит енгізілмеді",
            "margin_base": "Суару: бастапқы маржа, тг/га",
            "margin_new": "Суару: жаңа маржа, тг/га",
            "delta": "Суару: маусымдық маржа өзгерісі, тг",
            "stress_base": "Стресс: бастапқы маржа, тг/га",
            "stress_new": "Стресс: жаңа маржа, тг/га",
            "stress_delta": "Стресс: маусымдық маржа өзгерісі, тг",
            "stress_note": "Стресс: баға -10%, өнімділік -10%, шығын +10%; екі нұсқаға да бірдей қолданылады.",
            "separate": "Суару ауыстыру есебі жасыл энергия және жалпы ресурс үнемдеу сценарийлерінен бөлек. Біріккен модельсіз олардың нәтижелерін қосуға болмайды.",
            "title": "Суаруды ауыстыру: су және экономикалық тәуекел",
            "bad": "Су үнемделеді, бірақ жаңа технология есептік маржаны төмендетеді. Осы шарттарда оны табысты арттыру тәсілі ретінде ұсынуға болмайды.",
            "good": "Сценарийде су үнемделіп, маржа өседі. Баға, шығын және инвестицияны растау қажет.",
            "neutral": "Су мен маржа арасында айырбас бар; іске асыру шарттарын тексеру қажет.",
            "evidence": "Енгізілген параметрлер мен сценарийлік су нормалары.",
            "effect": "Стресс екі тәсілге де бірдей. Бұл расталған пайда емес, енгізілмеген инвестициялар есепке алынбайды.",
        },
        "en": {
            "area": "Irrigation-switch scenario area, ha",
            "yield": "User-entered yield used for margin, c/ha",
            "ml": "Separate baseline ML prediction, c/ha",
            "price": "Sales price, KZT/t",
            "cost": "Other variable costs, KZT/ha",
            "extra": "Extra technology costs, KZT/ha",
            "source": "Evidence or assumption for yield change",
            "yield_change": "Irrigation-related yield change, %",
            "water_base": "Irrigation: baseline water delivery, m³/ha",
            "water_new": "Irrigation: proposed water delivery, m³/ha",
            "water_saving": "Irrigation: seasonal water saved, m³",
            "gross_total_base": "Baseline irrigation: total delivered water, m³/season",
            "gross_total_new": "Proposed irrigation: total delivered water, m³/season",
            "fresh_total_base": "Baseline irrigation: external freshwater demand, m³",
            "fresh_total_new": "Proposed irrigation: external freshwater demand, m³",
            "reuse": "Water reuse, % (scenario assumption)",
            "water_cap": "Available freshwater budget, m³",
            "base_water_status": "Baseline irrigation: water feasibility",
            "new_water_status": "Proposed irrigation: water feasibility",
            "overall_margin": "Generic margin and irrigation comparison use different water bases",
            "yes": "feasible", "no": "over budget", "unknown": "budget not entered",
            "margin_base": "Irrigation: baseline margin, KZT/ha",
            "margin_new": "Irrigation: proposed margin, KZT/ha",
            "delta": "Irrigation: seasonal margin change, KZT",
            "stress_base": "Stress test: baseline margin, KZT/ha",
            "stress_new": "Stress test: proposed margin, KZT/ha",
            "stress_delta": "Stress test: seasonal margin change, KZT",
            "stress_note": "Stress test applies price -10%, yield -10%, costs +10% equally to both scenarios.",
            "separate": "Irrigation-switch outcomes differ from green-energy and generic resource-saving scenarios. Savings must not be summed without a joint model.",
            "title": "Irrigation switch: water and economic risk",
            "bad": "The switch saves water but reduces calculated margin. Do not recommend it as a profit improvement under these assumptions.",
            "good": "The switch saves water and improves scenario margin; verify prices, costs, and investment before implementation.",
            "neutral": "The scenario shows a water-margin trade-off; confirm implementation conditions.",
            "evidence": "Entered economic parameters and scenario water coefficients.",
            "effect": "The stress test applies equally to both technologies. This is not verified profit and excludes capital costs not entered.",
        },
    }
    t = languages.get(lang, languages["ru"])
    n = float(area_ha)
    if n <= 0:
        raise ValueError("Scenario area must be positive")
    available = float(available_water_m3 or 0.0)
    if available < 0 or not 0 <= float(reuse_pct) <= 100:
        raise ValueError("Invalid water budget or reuse percentage")
    fraction = 1 - float(reuse_pct)/100
    base_gross = float(comp["baseline_water_m3_ha"]) * n
    new_gross = float(comp["proposed_water_m3_ha"]) * n
    base_fresh = base_gross * fraction
    new_fresh = new_gross * fraction
    base_feasible = None if available == 0 else base_fresh <= available + 1e-7
    new_feasible = None if available == 0 else new_fresh <= available + 1e-7
    change = float(comp["margin_change_kzt_ha"])
    water_change = float(comp["water_saving_m3_ha"])
    seasonal_change = change * n
    stress_change = float(comp["stress_margin_change_kzt_ha"]) * n
    def item(k, v):
        return {"label": t[k], "value": v}
    rows = [
        item("area", f"{n:,.2f}"),
        item("yield", f"{float(input_yield_centners_ha):,.2f}"),
        item("price", f"{float(selling_price_kzt_t):,.2f}"),
        item("cost", f"{float(other_variable_cost_kzt_ha):,.2f}"),
        item("extra", f"{float(extra_technology_cost_kzt_ha):,.2f}"),
        item("yield_change", f"{float(yield_change_pct):,.1f}"),
        item("source", str(evidence)),
        item("water_base", f"{float(comp['baseline_water_m3_ha']):,.0f}"),
        item("water_new", f"{float(comp['proposed_water_m3_ha']):,.0f}"),
        item("water_saving", f"{water_change * n:,.0f}"),
        item("gross_total_base", f"{base_gross:,.0f}"),
        item("gross_total_new", f"{new_gross:,.0f}"),
        item("fresh_total_base", f"{base_fresh:,.0f}"),
        item("fresh_total_new", f"{new_fresh:,.0f}"),
        item("reuse", f"{float(reuse_pct):,.1f}"),
        item("water_cap", f"{available:,.0f}" if available else t["unknown"]),
        item("base_water_status", t["unknown"] if base_feasible is None else t["yes"] if base_feasible else t["no"]),
        item("new_water_status", t["unknown"] if new_feasible is None else t["yes"] if new_feasible else t["no"]),
        item("margin_base", f"{float(comp['baseline_margin_kzt_ha']):,.0f}"),
        item("margin_new", f"{float(comp['proposed_margin_kzt_ha']):,.0f}"),
        item("delta", f"{seasonal_change:+,.0f}"),
        item("stress_base", f"{float(comp['stress_baseline_margin_kzt_ha']):,.0f}"),
        item("stress_new", f"{float(comp['stress_proposed_margin_kzt_ha']):,.0f}"),
        item("stress_delta", f"{stress_change:+,.0f}"),
        item("stress_note", t["stress_note"]),
        item("separate", t["separate"]),
    ]
    if ml_yield_centners_ha is not None:
        rows.insert(2, item("ml", f"{float(ml_yield_centners_ha):,.2f}"))
    conclusion = t["bad"] if change < 0 and water_change > 0 else (t["good"] if change > 0 and water_change > 0 else t["neutral"])
    # Water compliance comes before financial comparison: a high hypothetical margin
    # for a non-feasible technology is not an achievable baseline.
    if available and base_feasible is False and new_feasible is True:
        conclusion = {
            "ru": "Исходный способ полива превышает лимит свежей воды, а новый укладывается. Новый вариант может обеспечить соблюдение водного ограничения, но при заданных затратах маржа уменьшается. Исходная маржа является условным сравнением, а не достижимым результатом в текущем водном бюджете.",
            "kk": "Бастапқы суару жаңа су лимитінен асады, ал жаңа технология лимитке сәйкес келеді. Жаңа нұсқа су шектеуін орындауы мүмкін, бірақ енгізілген шығындарда маржа төмендейді. Бастапқы маржа қолжетімді бюджеттегі табыс емес, шартты салыстыру.",
            "en": "The baseline exceeds the available freshwater budget; the new method meets it. The switch may be necessary for water feasibility although the modeled margin declines. The baseline margin is hypothetical, not achievable under this water budget.",
        }[lang]
    elif available and new_feasible is False:
        conclusion = {
            "ru": "Новая технология также превышает водный лимит. Такой переход нельзя рекомендовать как водно допустимый или экономически реализуемый без изменения условий.",
            "kk": "Жаңа технология да су лимитінен асады. Шарттарды өзгертпей оны іске асыруға болатын нұсқа ретінде ұсынуға болмайды.",
            "en": "The proposed technology also exceeds the water budget. Do not present it as a feasible irrigation recommendation without changing the conditions.",
        }[lang]
    rec = {
        "title": t["title"],
        "text": conclusion,
        "evidence": t["evidence"] + " " + f"{water_change * n:,.0f} м³; {seasonal_change:+,.0f} тг" if lang != "en" else t["evidence"] + " " + f"{water_change * n:,.0f} m³; {seasonal_change:+,.0f} KZT",
        "effect": t["effect"] + " " + t["stress_note"],
        "evidence_label": {"ru": "Основание", "kk": "Негіздеме", "en": "Evidence"}[lang],
        "effect_label": {"ru": "Ожидаемый эффект", "kk": "Күтілетін әсер", "en": "Expected effect"}[lang],
    }
    return rows, rec

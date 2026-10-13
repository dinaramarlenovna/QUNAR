"""Report-only presentation for irrigation economics; does not alter calculation results.

The irrigation-switch scenario is independent of generic water/energy savings
scenarios. A decline in contribution margin must never be described as a
profitable irrigation-switch recommendation.
"""


def irrigation_export(comp, *, area_ha, input_yield_centners_ha,
                      ml_yield_centners_ha, selling_price_kzt_t,
                      other_variable_cost_kzt_ha,
                      extra_technology_cost_kzt_ha, yield_change_pct,
                      evidence, lang="ru"):
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
            "evidence": "Основание: экономическая модель с заданными пользователем параметрами и коэффициентами водопотребления.",
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
            "evidence": "Негізі: енгізілген параметрлер мен сценарийлік су нормалары.",
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
            "evidence": "Basis: entered economic parameters and scenario water coefficients.",
            "effect": "The stress test applies equally to both technologies. This is not verified profit and excludes capital costs not entered.",
        },
    }
    t = languages.get(lang, languages["ru"])
    n = float(area_ha)
    if n <= 0:
        raise ValueError("Scenario area must be positive")
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
    rec = {
        "title": t["title"],
        "text": conclusion,
        "evidence": t["evidence"] + " " + f"{water_change * n:,.0f} м³; {seasonal_change:+,.0f} KZT" if lang != "en" else t["evidence"] + " " + f"{water_change * n:,.0f} m³; {seasonal_change:+,.0f} KZT",
        "effect": t["effect"] + " " + t["stress_note"],
    }
    return rows, rec

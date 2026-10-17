"""Write methodological audit directly from reproducible Stage 2 outputs."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'examples'/'stage2_evidence'

def maketable(df):return df.to_markdown(index=False)

def run():
    mc=json.loads((OUT/'mcda_robustness_2026_10_18.json').read_text(encoding='utf-8'))
    ml=json.loads((OUT/'ml_multimodel_summary.json').read_text(encoding='utf-8'))
    districts=pd.read_csv(OUT/'mcda_topsis_by_district.csv')
    crops=pd.read_csv(OUT/'ml_rolling_by_crop.csv')
    raw=pd.read_csv(OUT/'ml_rolling_predictions_all.csv')
    bycrop=crops[crops.period=='late_exploratory'].pivot(index='crop',columns='model',values='MAE')
    rf='Pooled RF';ext='ExtraTrees'
    pivotal=raw[raw.year>=2021].pivot_table(index=['district','crop','year','observed_yield'],columns='model',values='predicted_yield',aggfunc='first').reset_index()
    assert len(pivotal)==326
    delta=(pivotal.observed_yield-pivotal[rf]).abs()-(pivotal.observed_yield-pivotal[ext]).abs()
    pivotal['delta']=delta
    years=sorted(pivotal.year.unique());rng=np.random.default_rng(20261018)
    boot=[]
    for _ in range(10000):
        sample=rng.choice(years,len(years),replace=True)
        boot.append(float(np.concatenate([pivotal.loc[pivotal.year.eq(y),'delta'].to_numpy() for y in sample]).mean()))
    ci=np.quantile(boot,[.025,.975])
    early=ml['earlier_metrics']; late=ml['late_metrics']
    earlytab=pd.DataFrame([{'Метод':x['model'],'MAE, ц/га':round(x['MAE'],2)} for x in early])
    latetab=pd.DataFrame([{'Метод':x['model'],'MAE, ц/га':round(x['MAE'],2)} for x in late])
    croptab=bycrop[[rf,ext,'Historical median','CatBoost','Ridge']].round(2).reset_index()
    distrdiff=districts.loc[~districts.same_top1,['district','baseline_top1','topsis_top1','score_gap_top1_to_top2']].copy()
    distrdiff['score_gap_top1_to_top2']=distrdiff['score_gap_top1_to_top2'].round(2)
    low_n=pivotal.groupby('district').size(); low_n=low_n[low_n<20].sort_values()
    report=f'''# QŪNAR v0.8.1 - ЭТАП 2: расширенная независимая методологическая проверка A6/A7

Дата протокола: 18 октября 2026. Рабочая копия: `qunar_stage1/QUNAR_v0_8_1`. Продукционный алгоритм и видимая маркировка версии НЕ изменены. Протокол исследовательский, а не доказательство точности хозяйственных прогнозов.

## 1. Весовая модель, происхождение, интерпретация

Использована в системе *ресурсно-климатическая* оценка `Score = 0.60 × Climate + 0.40 × WaterPressure`. Это НЕ полный индекс экономической эффективности хозяйства. Первоначальная архитектура имела веса климат/вода/надёжность 50/35/15; перенос последнего компонента в отдельный показатель достоверности даёт нормированные отношения 50/85≈58.82% и 35/85≈41.18%, округлённые до 60/40. Не утверждать, что отношение 60/40 было получено из опроса либо экспертного AHP.

Опрос 208 человек содержит отдельные вопросы Q3 (120 упоминаний водного дефицита) и Q7 (93 упоминания климатических рисков). Отношение 43.66/56.34 годится только как сценарий чувствительности: общая выборка НЕ даёт индивидуальных попарных предпочтений.

### AHP - демонстрация вычислительной совместимости, не эмпирическая экспертиза

Попарная матрица `[[1, 1.5], [2/3, 1]]` имеет приоритетный вектор `[0.60, 0.40]` и λmax=2. Однако значение 1.5 задано исходным отношением весов, поэтому это **не независимое получение весов**. Для 2×2 стандартный показатель CR не даёт содержательной проверки согласованности. Настоящий экспертный AHP требует фактического предъявления вопросов экспертам и фиксации ответов, без их имитации.

### Данные ориентированные методы

Энтропийное взвешивание, средний вес климата по 17 территориям: **{mc['entropy_weight_climate_mean']:.3f}**; CRITIC: **{mc['critic_weight_climate_mean']:.3f}**. Совпадение лидера с базой соответственно **{mc['entropy_same_top1']}/17** и **{mc['critic_same_top1']}/17**. Эти веса зависят от дисперсии показателей среди 15 культур, не от предпочтений фермеров. Они НЕ замещают весов модели, тем более пока климатическая пригодность частично использует прокси, а водное давление - min-max нормирование по альтернативам.

## 2. TOPSIS против линейной суммы

Для каждой территории используется один и тот же вектор из двух выгодных критериев и 15 альтернатив. Оба нормируются по векторной норме в TOPSIS; далее рассчитывается близость к идеалу. Сопоставимость входов обеспечена, но шкалы итогового значения TOPSIS и Weighted Sum не совпадают.

- Лидер совпадает: **{mc['topsis_same_top1']}/17**.
- Состав трёх лучших альтернатив совпадает: **{mc['topsis_same_top3_set']}/17**.
- Средний Kendall tau полных рейтингов: **{mc['topsis_mean_kendall_tau']:.3f}**.

Шесть территорий с разными лидерами:

{maketable(distrdiff)}

Вывод: рекомендацию единственного лидера нельзя называть инвариантной к выбору MCDA-метода. Стабильность множества трёх культур - более обоснованный вывод.

## 3. Монте-Карло и детерминированная чувствительность

Выполнено 10 000 воспроизводимых реализаций на территорию (seed 20261018), веса климата U(0.30,0.70). Отдельно добавлены модельные независимые возмущения климатического/водного баллов N(0, 3²), с усечением на [0,100]. Последняя величина - только сценарная допущенная неопределённость, НЕ оценённая статистически погрешность.

- Средняя доля сохранения исходного лидера при случайных весах: **{100*mc['mean_weight_only_baseline_winner_share']:.1f}%**.
- При случайных весах и условном шуме 3 балла: **{100*mc['mean_weight_and_3pt_baseline_winner_share']:.1f}%**.
- Детерминированный пересчёт 101 весовой комбинации ранее подтверждал 17/17 совпадений лидера при профиле анкеты 43.66/56.34, но частичное расхождение при более сильном изменении веса климата.

Частоты Монте-Карло нельзя выдавать за доверительные интервалы и за вероятность агрономического успеха. Результат зависит от сценария веса и искусственного шума.

## 4. Семь прогнозных методов и календарные окна

Выборка 1362 районно-культурных наблюдения 2004–2025, шесть культур, 17 территорий. Общие настройки и набор объясняющих переменных зафиксированы до сравнений этой серии. Схемы: обучение 2004–2010 → контроль 2011–2015; обучение 2004–2015 → контроль 2016–2020; обучение 2004–2020 → контроль 2021–2025. Временное перемешивание между train/test исключено, кодирует категориальные поля только на данных обучения.

Методы: Historical median, pooled RF, RF по культуре, Ridge, ExtraTrees, HistGradientBoosting, CatBoost. Параметры и исходные предсказания сохранены в `scripts/stage2_ml_multimodel_rolling.py` и `ml_rolling_predictions_all.csv`. Настройки моделей НЕ проходили exhaustive tuning.

**Более ранние контрольные окна (2011–2020), MAE:**

{maketable(earlytab)}

**Последнее окно (2021–2025), MAE:**

{maketable(latetab)}

**По культурам: 2021–2025, MAE, ц/га:**

{maketable(croptab)}

При сравнении ExtraTrees минус pooled RF разность ошибок в направлении «MAE RF - MAE ExtraTrees» равна **{float(delta.mean()):.3f} ц/га**. Описательный блочный bootstrap по пяти годам (10 000 повторов) даёт диапазон 2.5–97.5%: **[{ci[0]:.3f}; {ci[1]:.3f}] ц/га**. Это исследовательская оценка, а не подтверждённое улучшение по новым хозяйствам; 2021–2025 уже изучались в прошлых итерациях.

Нестабильность выбранного победителя: на ранних окнах лучшая MAE у pooled RF ({early[0]['MAE']:.2f}); на позднем - ExtraTrees ({late[0]['MAE']:.2f}), то есть **автоматическая замена RF не подтверждена**. Одинаковое название метода не гарантирует неизменную точность между годами.

В контрольном периоде 2021–2025 территорий с менее 20 наблюдений: {', '.join(f'{name}: {int(n)}' for name,n in low_n.items())}. По ним не выводить сильных заявлений по одному районному R².

### Интерпретация

Слабость R² отдельных культур не обнуляет задачу оптимизации водных и земельных ресурсов. Но маржа, использующая прогноз урожая, наследует его неопределённость. Входные Apr–Sep климатические характеристики включают погоду исследуемого года, поэтому проверяемая задача - сезонная оценка с известными климатическими условиями, не чисто предсезонный прогноз.

Возможный отдельный исследовательский кандидат - совмещение RF и ExtraTrees 50/50: исходя из сохранённых предсказаний MAE ранних контрольных лет ~9.74 (против 9.66 RF), поздних ~16.24 (против 16.71 RF). Нового подтверждающего тестового периода для доказательства превосходства ещё нет.

## 5. Решение для кода и диссертации

1. НЕ увеличивать число весов механически: вода/климат - агрегированные критерии пригодности, а экономические, углеродные и ресурсные ограничения уже находятся в иных модулях. При добавлении третьего критерия требуется независимый сопоставимый индекс, предотвращение двойного счёта и новая проверка диссертации.
2. Основной рейтинг оставить 60/40, раздел «обоснование» дополнить выводом 50/35→58.82/41.18→60/40, анкету указать как поддержку релевантности проблем, но НЕ источник этих численных приоритетов.
3. TOPSIS и MCDA альтернативы включить в приложение/раздел чувствительности как независимую диагностическую проверку. Для несовпадающих лидеров говорить о наборе устойчивых альтернатив, а не о безусловной лучшей культуре.
4. Продакшен RF не заменять до отдельного подтверждения преимуществ, сохранить слабые показатели на контроле и предостережения в трёхъязычных отчётах.
5. Диссертация: точечные изменения в методике весов, таблице сравнений ML, чувствительности и ограничениях, без переписывания всех глав; если реально заменить прогнозный двигатель, тогда необходимо обновить раздел методов, все таблицы/графики точности, зависимые прогнозы и результаты маржи.

## Источники методики

- OECD / JRC (2008), Handbook on Constructing Composite Indicators: https://doi.org/10.1787/9789264043466-en
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- TOPSIS rank reversal, Computers & Industrial Engineering (2019): https://doi.org/10.1016/j.cie.2019.04.023
- CatBoost categorical features: https://catboost.ai/docs/en/features/categorical-features

## QA и воспроизводимость

- Новый код: `scripts/stage2_mcda_full_validation.py`, `scripts/stage2_ml_multimodel_rolling.py`, `scripts/build_stage2_extended_protocol.py`.
- Добавлено 8 тестов: `tests/test_stage2_mcda_multimodel_2026_10_18.py`.
- Общее тестирование: 276 passed, 16.80 s (протокол `qunar_stage1/pytest_stage2_all_current.log`). Это проверка кода, не внешняя независимая валидация.
- Версия, исходные ZIP, основная обученная RF, публичные рейтинги и продукционные веса не менялись.
'''
    (ROOT/'STAGE2_EXTENDED_MCDA_ML_AUDIT_2026-10-18_RU.md').write_text(report,encoding='utf-8')
    (OUT/'ml_rf_vs_extratrees_year_bootstrap.json').write_text(json.dumps({'n':len(pivotal),'years':[int(y) for y in years],
       'rf_minus_extratrees_MAE':float(delta.mean()),'bootstrap_by_year_95_descriptive':[float(ci[0]),float(ci[1])],
       'caution':'Only 5 year blocks; late data has previously been used in exploratory method comparisons.'},ensure_ascii=False,indent=2),encoding='utf-8')
    print('report_chars',len(report),'bootstrap_ci',ci)
if __name__=='__main__':run()

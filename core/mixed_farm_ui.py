"""Sixth optional QŪNAR mode. Keep old crop and livestock calculators untouched."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import streamlit as st
import pandas as pd

from .mixed_farm import compare_mixed_farm
from .water_norms import CROP_TO_NORM
from .livestock import SPECIES_LABELS
from .config import CROP_LABELS

_EXTRA_CROP_NAMES={
 'Barley':('Арпа','Ячмень','Barley'), 'Forage':('Мал азығы','Кормовые культуры','Forage'),
 'OtherOilseeds':('Басқа майлы дақылдар','Прочие масличные','Other oilseeds'),
 'Onion':('Пияз','Лук','Onion'), 'Tomatoes':('Қызанақ','Томаты','Tomatoes'),
 'Cabbage':('Қырыққабат','Капуста','Cabbage'), 'Cucumbers':('Қияр','Огурцы','Cucumbers'),
 'Carrots':('Сәбіз','Морковь','Carrots'), 'Melons':('Бақша дақылдары','Бахчевые','Melons'),
 'PomeStone':('Жеміс ағаштары','Плодовые','Orchard fruit'),
 'FreshGrapes':('Жүзім','Виноград','Grapes'), 'OtherFruits':('Басқа жемістер','Прочие фрукты','Other fruit'),
}

def _get(ru,kk,en,lang): return {'ru':ru,'kk':kk,'en':en}[lang]

def _crop_label(c,lang):
    return CROP_LABELS[lang].get(c,_EXTRA_CROP_NAMES.get(c, (c,c,c))[{'kk':0,'ru':1,'en':2}[lang]])

def render_mixed_mode(*, lang: str, district: str, district_title: str,
                      assessment_year: int, render_export_panel):
    """Render self-contained comparative annual accounting and exportable results."""
    title=_get('Сравнить растениеводство и животноводство (бета-версия)',
               'Өсімдік және мал шаруашылығын салыстыру (бета-нұсқа)',
               'Compare crops and livestock (beta)', lang)
    st.header(title)
    st.caption(_get(
        'Экспериментальный сценарный модуль: научная апробация продолжается. Параметры примера являются допущениями. Сравнение не подтверждает фактическую экономию, полное экологическое превосходство или право изменить назначение земель.',
        'Эксперименттік сценарийлік модуль: ғылыми сынақ жалғасуда. Мысал деректері — болжамдар. Нәтиже нақты үнемді, толық экологиялық артықшылықты немесе жердің мақсатын өзгерту құқығын растамайды.',
        'Experimental scenario module under scientific evaluation. Example inputs are assumptions. Results do not establish realized savings, overall environmental superiority or permission to change land use.',lang))
    st.info(_get('Первый вариант сохраняет исходную структуру. В двух следующих можно перевести часть выбранной культуры в пастбище и задать поголовье КРС. Общая площадь при этом не меняется.',
        'Бастапқы нұсқа өзгеріссіз қалады. Кейінгі нұсқаларда дақыл жерінің бір бөлігін жайылым ретінде тексеруге болады. Жалпы аумақ өзгермейді.',
        'The first option is the unchanged baseline. In the following two, part of a crop area can be assessed as converted pasture; total land is conserved.',lang))

    st.subheader(_get('1. Текущая структура посевов', '1. Ағымдағы егіс құрылымы', '1. Current crop mix',lang))
    crop_n=st.select_slider(_get('Количество культур для сравнения','Салыстырылатын дақыл саны','Number of crop rows',lang),options=list(range(1,7)),value=4,key='qmix_crop_count')
    defaults=[('Cotton',30.,20.,310000.,540000.,950.,120.,140.),
              ('Wheat',40.,24.,100000.,195000.,300.,30.,80.),
              ('Sunflower',20.,14.,180000.,220000.,450.,40.,60.),
              ('Barley',10.,20.,90000.,165000.,350.,35.,70.),
              ('Corn',5.,30.,90000.,200000.,420.,40.,70.),
              ('Potato',5.,130.,75000.,500000.,650.,50.,100.)]
    all_crops=list(CROP_TO_NORM)
    rows=[]
    for idx in range(crop_n):
        d=defaults[idx]
        with st.expander(f"{idx+1}. {_crop_label(d[0],lang)}",expanded=(idx==0)):
            code=st.selectbox(_get('Культура','Дақыл','Crop',lang),all_crops,
                index=all_crops.index(d[0]),format_func=lambda x:_crop_label(x,lang),key=f'qmix_crop_{idx}')
            c1,c2,c3,c4=st.columns(4)
            area=c1.number_input(_get('Площадь, га','Аудан, га','Area, ha',lang),min_value=0.01,value=d[1],step=1.0,key=f'qmix_area_{idx}')
            yy=c2.number_input(_get('Урожайность, ц/га','Өнімділік, ц/га','Yield, c/ha',lang),min_value=0.0,value=d[2],step=1.0,key=f'qmix_yield_{idx}')
            price=c3.number_input(_get('Цена, тг/т','Баға, тг/т','Price, KZT/t',lang),min_value=0.0,value=d[3],step=1000.0,key=f'qmix_price_{idx}')
            cost=c4.number_input(_get('Прочие затраты, тг/га','Басқа шығын, тг/га','Other cost, KZT/ha',lang),min_value=0.0,value=d[4],step=1000.0,key=f'qmix_cost_{idx}',help=_get('Исключая воду, сетевое электричество и дизель - во избежание двойного учёта.','Су, желілік электр және дизель бөлек есептеледі.','Exclude water, grid electricity and diesel - accounted separately.',lang))
            d1,d2,d3=st.columns(3)
            power=d1.number_input(_get('Электроэнергия, кВт·ч/га','Электр, кВт·сағ/га','Grid, kWh/ha',lang),min_value=0.0,value=d[5],step=10.0,key=f'qmix_power_{idx}')
            diesel=d2.number_input(_get('Дизель, л/га','Дизель, л/га','Diesel, L/ha',lang),min_value=0.0,value=d[6],step=1.0,key=f'qmix_diesel_{idx}')
            n=d3.number_input(_get('Азот, кг N/га','Азот, кг N/га','Nitrogen, kg N/ha',lang),min_value=0.0,value=d[7],step=5.0,key=f'qmix_n_{idx}')
            rows.append({'crop':code,'area_ha':area,'yield_c_ha':yy,'price_kzt_t':price,
                         'other_cost_kzt_ha':cost,'grid_kwh_ha':power,
                         'diesel_l_ha':diesel,'nitrogen_kg_n_ha':n})
    crop_area=sum(r['area_ha'] for r in rows)
    st.caption(_get(f'Площадь посевов: {crop_area:,.2f} га. Нормы воды рассчитываются по выбранной культуре и району, а не по общей площади хозяйства.',
                  f'Егіс ауданы: {crop_area:,.2f} га. Су нормалары әр дақылға жеке алынады.',
                  f'Cropland: {crop_area:,.2f} ha. Reference water requirements are crop-specific.',lang))
    st.subheader(_get('2. Общие ресурсы и затраты','2. Жалпы ресурстар және шығындар','2. Resource and cost assumptions',lang))
    s1,s2,s3=st.columns(3)
    pasture=s1.number_input(_get('Существующие пастбища, га','Бар жайылым, га','Existing pasture, ha',lang),min_value=0.0,value=60.0,step=1.0,key='qmix_pasture')
    water=s2.number_input(_get('Лимит воды для посевов, м³/сезон','Егістің су лимиті, м³/маусым','Crop water cap, m³/season',lang),min_value=0.0,value=450000.0,step=1000.0,key='qmix_water')
    cattle_water_limit=s3.number_input(_get('Лимит воды для скота, м³/год (0 = неизвестно)','Мал суының шегі, м³/жыл (0 = белгісіз)','Livestock water cap, m³/year (0 = unknown)',lang),min_value=0.0,value=1200.0,step=100.0,key='qmix_cattle_water')
    w1,w2,w3=st.columns(3)
    w_tariff=w1.number_input(_get('Вода, тг/м³','Су, тг/м³','Water, KZT/m³',lang),min_value=0.0,value=1.16,step=0.1,key='qmix_water_tariff')
    e_tariff=w2.number_input(_get('Электроэнергия, тг/кВт·ч','Электр, тг/кВт·сағ','Grid, KZT/kWh',lang),min_value=0.0,value=41.06,step=1.0,key='qmix_power_tariff')
    d_tariff=w3.number_input(_get('Дизель, тг/л','Дизель, тг/л','Diesel, KZT/L',lang),min_value=0.0,value=300.0,step=10.0,key='qmix_diesel_tariff')
    st.subheader(_get('3. Варианты изменения деятельности','3. Бағытты өзгерту нұсқалары','3. Land-use alternatives',lang))
    crop_selected=st.selectbox(_get('Культура, площадь которой предлагается сократить','Қысқартылатын дақыл','Crop considered for reduction',lang),[r['crop'] for r in rows],format_func=lambda c:_crop_label(c,lang),key='qmix_convert_crop')
    c1,c2,c3,c4=st.columns(4)
    convert_b=c1.number_input(_get('Частичный переход, га','Ішінара ауысу, га','Partial transition, ha',lang),min_value=0.0,value=20.0,step=1.0,key='qmix_convert_b')
    heads_b=c2.number_input(_get('КРС в варианте B, голов','B нұсқасы: ірі қара, бас','Cattle B, heads',lang),min_value=0,value=25,step=1,key='qmix_heads_b')
    convert_c=c3.number_input(_get('Глубокий переход, га','Кең ауысу, га','Larger transition, ha',lang),min_value=0.0,value=30.0,step=1.0,key='qmix_convert_c')
    heads_c=c4.number_input(_get('КРС в варианте C, голов','C нұсқасы: ірі қара, бас','Cattle C, heads',lang),min_value=0,value=40,step=1,key='qmix_heads_c')
    st.caption(_get('Сокращается площадь только указанной культуры. Сохраняется общая территория предприятия. Переход проверяется как сценарий и не означает автоматическое изменение статуса земель.',
                    'Таңдалған дақылдың ғана ауданы қысқарады. Бұл жер мәртебесін автоматты өзгертпейді.',
                    'Only the selected crop area decreases. Land conversion is a hypothetical scenario, not automatic land-use authorization.',lang))
    c1,c2,c3=st.columns(3)
    meat_b=c1.number_input(_get('Производство мяса B, т/год','B: ет өндіру, т/жыл','Meat output B, t/year',lang),min_value=0.0,value=7.0,step=0.5,key='qmix_meat_b')
    meat_c=c2.number_input(_get('Производство мяса C, т/год','C: ет өндіру, т/жыл','Meat output C, t/year',lang),min_value=0.0,value=10.0,step=0.5,key='qmix_meat_c')
    meat_price=c3.number_input(_get('Цена мяса, тг/т живого веса','Ет бағасы, тг/т тірі салмақ','Live-weight meat price, KZT/t',lang),min_value=0.0,value=1300000.0,step=50000.0,key='qmix_meat_price')
    c1,c2,c3=st.columns(3)
    cattle_cost=c1.number_input(_get('Прочие затраты на КРС, тг/гол./год','Ірі қараға басқа шығын, тг/бас/жыл','Other cattle cost, KZT/head/year',lang),min_value=0.0,value=80000.0,step=1000.0,key='qmix_cattle_cost',help=_get('Без покупных кормов, воды, электричества и дизеля: они учитываются отдельно.','Сатып алынған жем, су, электр, дизель бөлек есептеледі.','Exclude purchased feed, water, grid and diesel: these are accounted separately.',lang))
    pasture_yield=c2.number_input(_get('Кормовая продуктивность пастбища, т сух. вещества/га/год','Жайылым өнімі, т құрғақ зат/га/жыл','Pasture fodder, t DM/ha/year',lang),min_value=0.0,value=0.35,step=0.05,key='qmix_pasture_yield')
    purchased_price=c3.number_input(_get('Цена покупных кормов, тг/т сухого вещества','Сатып алынатын жем, тг/т құрғақ зат','Purchased feed, KZT/t DM',lang),min_value=0.0,value=80000.0,step=1000.0,key='qmix_feed_price')
    c1,c2,c3=st.columns(3)
    max_stocking=c1.number_input(_get('Допустимая нагрузка пастбища, усл. ед./га (допущение)','Жайылым жүктемесі, ш. бірлік/га','Pasture stocking cap, LU/ha',lang),min_value=0.01,value=0.30,step=0.05,key='qmix_max_stocking')
    energy_cattle=c2.number_input(_get('КРС: электричество, кВт·ч/гол./год','Ірі қара: электр, кВт·сағ/бас/жыл','Livestock grid, kWh/head/year',lang),min_value=0.0,value=40.0,step=5.0,key='qmix_cattle_grid')
    diesel_cattle=c3.number_input(_get('КРС: дизель, л/гол./год','Ірі қара: дизель, л/бас/жыл','Livestock diesel, L/head/year',lang),min_value=0.0,value=16.0,step=2.0,key='qmix_cattle_diesel')
    agree_conversion=st.checkbox(_get('Сценарно допускаю изменение использования указанной земли; юридическая возможность требует отдельного подтверждения',
                        'Сценарийде жерді қайта пайдалануды қарастырамын; құқықтық тексеру қажет',
                        'Assume land conversion for scenario only; legal approval must be checked',lang),key='qmix_legal')
    agree_pasture=st.checkbox(_get('Пастбище условно пригодно (подтвердить почвой, водой, деградацией и нормами нагрузки)',
                        'Жайылым шартты жарамды (тексеру қажет)','Assume pasture suitability subject to verification',lang),key='qmix_suitable')
    allow_purchase=st.checkbox(_get('Разрешить покупку недостающих кормов по указанной цене',
                       'Жетіспейтін жемді белгіленген бағамен алуға рұқсат',
                       'Allow purchased feed for the shortfall at stated price',lang),value=True,key='qmix_allow_feed')
    with st.expander(_get('Дополнительно: ресурсы и выбросы покупных кормов и навоза',
                          'Қосымша: сатып алынатын жем мен көң шығарындылары',
                          'Advanced: feed supply-chain water/GHG and manure',lang)):
        st.caption(_get('Если данные неизвестны, оставьте выключенными. В модели они НЕ считаются нулевыми: экологическое сравнение останется частичным.',
                   'Дерек белгісіз болса өшіріңіз. Бұл нөлді білдірмейді.',
                   'Leave unchecked if unknown. Missing does not mean zero; climate comparison remains partial.',lang))
        known_feed_water=st.checkbox(_get('Известен водный след покупных кормов',
                                     'Сатып алынған жемнің су ізі белгілі','Purchased-feed embedded water known',lang),key='qmix_feed_water_known')
        feed_water=st.number_input(_get('Водный след покупных кормов, м³/т сухого вещества',
                               'Сатып алынған жем суы, м³/т құрғақ зат','Embedded water, m³/t dry matter',lang),value=0.,min_value=0.,step=10.,key='qmix_feed_water') if known_feed_water else None
        known_feed_ghg=st.checkbox(_get('Известны выбросы производства и доставки покупных кормов',
                                      'Жем өндірісі/тасымалы шығарындылары белгілі','Feed production and delivery emissions known',lang),key='qmix_feed_ghg_known')
        feed_ghg=st.number_input(_get('Выбросы покупных кормов, кг CO₂e/т сухого вещества',
                               'Жем шығарындылары, кг CO₂e/т құрғақ зат','Feed emissions, kg CO₂e/t dry matter',lang),value=0.,min_value=0.,step=10.,key='qmix_feed_ghg') if known_feed_ghg else None
        known_manure=st.checkbox(_get('Известна сценарная оценка выбросов навоза',
                                    'Көң шығарындылары сценарийі белгілі','Manure scenario emission estimate known',lang),key='qmix_manure_known')
        manure=st.number_input(_get('Навоз, кг CO₂e/гол./год','Көң, кг CO₂e/бас/жыл','Manure, kg CO₂e/head/year',lang),value=0.,min_value=0.,step=10.,key='qmix_manure') if known_manure else None
    st.caption(_get('Справочные коэффициенты: орошение по исторической зональной норме (приказ №108-НҚ; не доказан норматив 2027), питье КРС и корма FAO, прямой N₂O по IPCC; 0,813 кг CO₂/кВт·ч по Ember; метан пищеварения IPCC Tier 1 (54 кг CH₄/гол./год, GWP100=27).',
                   'Анықтамалық коэффициенттер: №108-НҚ тарихи нормасы, FAO, IPCC, Ember; нақты шаруашылық шығыны емес.',
                   'References: historic zonal irrigation order 108-NQ (not verified for 2027), FAO cattle water/feed, IPCC Tier 1 direct N₂O/enteric CH₄ (54 kg/head/year, GWP100=27), Ember 2025 grid factor 0.813 kg CO₂/kWh.',lang))
    signature_data={
        'district':district,'year':assessment_year,'crops':rows,'pasture':pasture,'water':water,
        'livestock_water':cattle_water_limit,'water_price':w_tariff,'power_price':e_tariff,
        'diesel_price':d_tariff,'source_crop':crop_selected,'convert_b':convert_b,
        'heads_b':heads_b,'convert_c':convert_c,'heads_c':heads_c,'meat_b':meat_b,
        'meat_c':meat_c,'meat_price':meat_price,'cattle_cost':cattle_cost,
        'pasture_yield':pasture_yield,'feed_price':purchased_price,'max_stocking':max_stocking,
        'cattle_power':energy_cattle,'cattle_diesel':diesel_cattle,'legal':agree_conversion,
        'pasture_suitable':agree_pasture,'feed_purchase_allowed':allow_purchase,
        'feed_water_factor':feed_water,'feed_ghg_factor':feed_ghg,'manure_factor':manure}
    input_signature=hashlib.sha256(json.dumps(signature_data,sort_keys=True,ensure_ascii=False).encode('utf8')).hexdigest()
    if st.button(_get('Сравнить три сценария','Үш сценарийді салыстыру','Compare three scenarios',lang),type='primary',use_container_width=True,key='qmix_calculate'):
        opts=[{'label':_get('A. Сохранить растениеводство','A. Егіншілікті сақтау','A. Keep crops',lang),'convert_ha':0,'heads':0,'meat_t_year':0},
              {'label':_get('B. Частичный переход','B. Ішінара ауысу','B. Partial shift',lang),'convert_ha':convert_b,'heads':heads_b,'meat_t_year':meat_b},
              {'label':_get('C. Более глубокий переход','C. Үлкен ауысу','C. Larger shift',lang),'convert_ha':convert_c,'heads':heads_c,'meat_t_year':meat_c}]
        try:
            _computed=compare_mixed_farm(
                district=district,crops=rows,pasture_ha=pasture,crop_water_limit_m3=water if water>0 else None,
                source_crop=crop_selected,alternatives=opts,crop_water_price=w_tariff,
                electricity_price=e_tariff,diesel_price=d_tariff,cattle_price_kzt_t=meat_price,
                cattle_other_cost_kzt_head=cattle_cost,dry_fodder_yield_t_ha_year=pasture_yield,
                purchased_feed_price_kzt_t=purchased_price,purchase_feed_allowed=allow_purchase,
                allowable_lu_ha=max_stocking,legal_conversion_allowed=agree_conversion,
                pasture_suitable=agree_pasture,livestock_grid_kwh_per_head_year=energy_cattle,
                livestock_diesel_l_per_head_year=diesel_cattle,feed_water_footprint_m3_t=feed_water,
                feed_ghg_footprint_kg_co2e_t=feed_ghg,manure_ghg_kg_co2e_head_year=manure,
                livestock_water_limit_m3_year=cattle_water_limit if cattle_water_limit>0 else None)
            st.session_state['qmix_last_result']=_computed
            st.session_state['qmix_result_signature']=input_signature
            st.session_state['qmix_result_at']=datetime.now().strftime('%Y-%m-%d %H:%M')
            st.session_state['qmix_result_inputs']=signature_data
        except (ValueError,KeyError) as exc:
            st.error(f'{_get("Невозможно сравнить сценарии: ","Салыстыру мүмкін емес: ","Cannot compare scenarios: ",lang)}{exc}')
            st.session_state.pop('qmix_last_result',None)
    result=st.session_state.get('qmix_last_result')
    if not result:
        return
    if st.session_state.get('qmix_result_signature') != input_signature:
        st.warning(_get('Параметры изменились: нажмите «Сравнить три сценария» повторно, чтобы обновить результат.',
                         'Параметрлер өзгерді: салыстыруды қайта орындаңыз.',
                         'Inputs changed; rerun the three-scenario comparison.',lang))
        return
    st.subheader(_get('Сравнительный результат','Салыстыру нәтижесі','Comparison result',lang))
    columns={
        'name':_get('Вариант','Нұсқа','Scenario',lang),
        'crop_area_ha':_get('Пашня, га','Егіс, га','Cropland, ha',lang),
        'pasture_ha':_get('Пастбища, га','Жайылым, га','Pasture, ha',lang),
        'heads':_get('КРС, голов','Ірі қара, бас','Cattle, heads',lang),
        'crop_water_m3':_get('Полив, м³/сезон','Суару, м³/маусым','Irrigation, m³/season',lang),
        'livestock_drinking_m3_year':_get('Питье КРС, м³/год','Мал суы, м³/жыл','Cattle water, m³/year',lang),
        'purchased_fodder_dm_t_year':_get('Покупные корма, т СВ/год','Сатып алу жем, т/жыл','Feed purchased, t DM/year',lang),
        'total_margin_kzt':_get('Расчётная маржа, тг/год','Есептік маржа, тг/жыл','Scenario margin, KZT/year',lang),
        'partial_onsite_ghg_kg_co2e':_get('Частичные выбросы на территории, кг CO₂e/год','Тікелей ішінара шығарындылар, кг CO₂e/жыл','Partial on-site GHG, kg CO₂e/year',lang),
        'feasible':_get('Ограничения выполнены','Шектеулер орындалған','Constraints satisfied',lang),
    }
    def _display_result(r):
        item={col:r.get(col) for col in columns}
        item['feasible']=(_get('Да','Иә','Yes',lang) if r['feasible']
                          else _get('Нет','Жоқ','No',lang))
        return item
    df=pd.DataFrame([_display_result(r) for r in result['scenarios']]).rename(columns=columns)
    st.dataframe(df,hide_index=True,use_container_width=True)
    failure_labels={
        'land_conversion_not_confirmed':_get('Не подтвержден перевод земель','Жер ауыстыру расталмаған','Land conversion not confirmed',lang),
        'pasture_suitability_not_confirmed':_get('Не подтверждена пригодность пастбища','Жайылым жарамдылығы расталмаған','Pasture suitability unconfirmed',lang),
        'crop_water_limit_unknown':_get('Не введён лимит полива','Суару лимиті белгісіз','Irrigation cap missing',lang),
        'crop_water_limit_exceeded':_get('Превышен лимит полива','Суару шегінен асты','Irrigation cap exceeded',lang),
        'livestock_water_limit_unknown':_get('Не введён лимит питьевой воды','Мал суы шегі белгісіз','Livestock water cap missing',lang),
        'livestock_water_limit_exceeded':_get('Превышен лимит питьевой воды','Мал суы шегі артқан','Livestock water cap exceeded',lang),
        'fodder_deficit_without_purchase':_get('Недостаток кормов','Жем тапшылығы','Feed deficit',lang),
        'purchased_feed_price_unknown':_get('Неизвестна стоимость покупки кормов','Сатып алу бағасы белгісіз','Purchased feed price unknown',lang),
        'pasture_capacity_unknown':_get('Не указана допустимая пастбищная нагрузка','Жайылым шегі белгісіз','Stocking cap missing',lang),
        'pasture_capacity_exceeded':_get('Превышена допустимая нагрузка пастбища','Жайылым жүктемесі асып кетті','Stocking cap exceeded',lang),
        'pasture_fodder_yield_unknown':_get('Нет продуктивности пастбища','Жайылым өнімі белгісіз','Pasture fodder yield unknown',lang),
        'economic_data_incomplete':_get('Экономические данные неполны','Экономикалық дерек толық емес','Economic inputs incomplete',lang),
    }
    for r in result['scenarios']:
        if r['constraints']:
            st.warning(r['name']+': '+ '; '.join(failure_labels.get(k,k) for k in r['constraints']))
    st.caption(_get('Вывод: повышение маржи при сокращении полива не означает полного экологического улучшения. Кормопроизводство, навоз, изменение углерода почвы, капиталовложения и рыночные риски могут изменить предпочтительный вариант. Экологически лучшего варианта при неполной инвентаризации программа НЕ объявляет.',
        'Маржаның артуы экологиялық жақсаруды толық дәлелдемейді. Жем, көң, топырақ көміртегі және күрделі шығындар қажет.',
        'A higher margin and lower on-site irrigation do not prove overall environmental superiority: feed supply chains, manure, soil carbon, capex and market risk are incomplete.',lang))
    feasible=[r for r in result['scenarios'] if r['feasible']]
    if feasible:
        best=max(feasible,key=lambda x:x['total_margin_kzt'] if x['total_margin_kzt'] is not None else -1e100)
        st.info(_get('Среди вариантов, прошедших введённые ограничения, наибольшая расчётная маржа у: ',
                     'Шектеулерден өткен нұсқалардың ең үлкен маржасы: ',
                     'Highest scenario margin among variants passing entered constraints: ',lang)+best['name']+_get('. Это не рекомендация без проверки полных выбросов и земельной пригодности.',
                       '. Бұл толық экологиялық қорытынды емес.',
                       '. This is not an environmental recommendation without complete inventories.',lang))
    else:
        st.warning(_get('Ни один сценарий не подтвердил выполнение всех введённых ограничений. Рекомендация не выдаётся.',
                        'Еш сценарий барлық шектеулерден өтпеді. Ұсыным берілмейді.',
                        'No scenario passed all constraints; no recommendation can be issued.',lang))
    generated=st.session_state['qmix_result_at']
    # Export a legible eight-column table (generic PDF renderer limits to eight).
    _report_col_labels={
        'ru':('Сценарий','Пашня, га','Пастбища, га','КРС, голов','Полив, м³','Корм, т СВ','Маржа, тг','Частичн. CO₂e, кг'),
        'kk':('Сценарий','Егіс, га','Жайылым, га','Ірі қара, бас','Суару, м³','Жем, т құрғақ зат','Маржа, тг','Ішінара CO₂e, кг'),
        'en':('Scenario','Crops, ha','Pasture, ha','Cattle, head','Water, m³','Feed, t DM','Margin, KZT','Partial CO₂e, kg'),
    }[lang]
    rows_out=[]
    for r in result['scenarios']:
        vals=(r['name'],r['crop_area_ha'],r['pasture_ha'],r['heads'],
              r['crop_water_m3'],r['purchased_fodder_dm_t_year'],
              r['total_margin_kzt'],r['partial_onsite_ghg_kg_co2e'])
        rows_out.append({key:(value if i==0 else ('—' if value is None else f'{value:,.2f}'.rstrip('0').rstrip('.')))
                         for i,(key,value) in enumerate(zip(_report_col_labels,vals))})
    inputs=[[ _get('Район','Аудан','District',lang),district_title, 'User district'],
            [_get('Год','Жыл','Year',lang),str(assessment_year),'Scenario year'],
            [_get('Пашня до перехода, га','Бастапқы егіс, га','Baseline cropland, ha',lang),f'{crop_area:.2f}','User-entered scenario'],
            [_get('Пастбища до перехода, га','Бастапқы жайылым, га','Baseline pasture, ha',lang),f'{pasture:.2f}','User-entered scenario'],
            [_get('Исходный лимит орошения, м³/сезон','Суару лимиті, м³/маусым','Crop water cap, m³/season',lang),f'{water:.2f}','User-entered scenario'],
            [_get('Культура для изменения','Ауыстырылатын дақыл','Conversion crop',lang),_crop_label(crop_selected,lang),'User-entered scenario']]
    _input_names={
      'ru':{'district':'Район','year':'Год','pasture':'Исходные пастбища, га','water':'Лимит полива, м³/сезон',
        'livestock_water':'Лимит питьевой воды КРС, м³/год','water_price':'Цена воды, тг/м³',
        'power_price':'Цена электроэнергии, тг/кВт·ч','diesel_price':'Цена дизеля, тг/л',
        'source_crop':'Сокращаемая культура','convert_b':'Переход B, га','convert_c':'Переход C, га',
        'heads_b':'Поголовье B, голов','heads_c':'Поголовье C, голов',
        'meat_b':'Выпуск мяса B, т/год','meat_c':'Выпуск мяса C, т/год',
        'meat_price':'Цена мяса, тг/т живого веса','cattle_cost':'Прочие расходы на КРС, тг/гол./год',
        'pasture_yield':'Кормовая продуктивность пастбища, т СВ/га/год',
        'feed_price':'Цена покупных кормов, тг/т СВ','max_stocking':'Лимит нагрузки пастбища, усл. ед./га',
        'cattle_power':'Электроэнергия КРС, кВт·ч/гол./год',
        'cattle_diesel':'Дизель КРС, л/гол./год','legal':'Перевод земель (сценарное допущение)',
        'pasture_suitable':'Пригодность пастбища (допущение)',
        'feed_purchase_allowed':'Покупные корма разрешены в сценарии',
        'feed_water_factor':'Вода покупных кормов, м³/т СВ',
        'feed_ghg_factor':'Выбросы покупных кормов, кг CO₂e/т СВ',
        'manure_factor':'Выбросы навоза, кг CO₂e/гол./год'},
      'kk':{'district':'Аудан','year':'Жыл','pasture':'Жайылым, га','water':'Суару шегі, м³/маусым',
        'livestock_water':'Ірі қара су шегі, м³/жыл','water_price':'Су бағасы, тг/м³',
        'power_price':'Электр бағасы, тг/кВт·сағ','diesel_price':'Дизель бағасы, тг/л',
        'source_crop':'Ауыстырылатын дақыл','convert_b':'B ауысуы, га','convert_c':'C ауысуы, га',
        'heads_b':'B мал саны, бас','heads_c':'C мал саны, бас','meat_b':'B ет, т/жыл','meat_c':'C ет, т/жыл',
        'meat_price':'Ет бағасы, тг/т','cattle_cost':'Ірі қара шығыны, тг/бас/жыл',
        'pasture_yield':'Жайылым жемі, т құрғақ зат/га/жыл',
        'feed_price':'Жем бағасы, тг/т','max_stocking':'Жайылым шегі, мал бірлігі/га',
        'cattle_power':'Ірі қара электрі, кВт·сағ/бас/жыл','cattle_diesel':'Ірі қара дизелі, л/бас/жыл',
        'legal':'Жер мәртебесі (жорамал)','pasture_suitable':'Жайылым жарамды (жорамал)',
        'feed_purchase_allowed':'Жемді сатып алу мүмкін','feed_water_factor':'Жем су ізі, м³/т',
        'feed_ghg_factor':'Жем шығарындылары, кг CO₂e/т','manure_factor':'Көң, кг CO₂e/бас/жыл'},
      'en':{'district':'District','year':'Year','pasture':'Baseline pasture, ha',
        'water':'Irrigation cap, m³/season','livestock_water':'Cattle water cap, m³/year',
        'water_price':'Water, KZT/m³','power_price':'Grid, KZT/kWh','diesel_price':'Diesel, KZT/L',
        'source_crop':'Converted crop','convert_b':'Transition B, ha','convert_c':'Transition C, ha',
        'heads_b':'Cattle B, heads','heads_c':'Cattle C, heads','meat_b':'Meat B, t/year',
        'meat_c':'Meat C, t/year','meat_price':'Live-weight price, KZT/t',
        'cattle_cost':'Other cattle cost, KZT/head/year',
        'pasture_yield':'Pasture forage, t DM/ha/year','feed_price':'Feed price, KZT/t DM',
        'max_stocking':'Stocking limit, LU/ha','cattle_power':'Cattle grid, kWh/head/year',
        'cattle_diesel':'Cattle diesel, L/head/year','legal':'Land conversion (assumption)',
        'pasture_suitable':'Pasture suitability (assumption)','feed_purchase_allowed':'Purchase feed allowed',
        'feed_water_factor':'Embedded feed water, m³/t DM',
        'feed_ghg_factor':'Embedded feed GHG, kg CO₂e/t DM',
        'manure_factor':'Manure GHG, kg CO₂e/head/year'},
    }[lang]
    for key,value in st.session_state.get('qmix_result_inputs', {}).items():
        if key == 'crops':
            continue
        if key == 'source_crop':
            display_value=_crop_label(value,lang)
        elif isinstance(value,bool):
            display_value=(_get('Да','Иә','Yes',lang) if value else _get('Нет','Жоқ','No',lang))
        elif value is None:
            display_value=_get('неизвестно','белгісіз','unknown',lang)
        else:
            display_value=str(value)
        inputs.append([_input_names.get(key,str(key)), display_value,
            _get('Учебное допущение пользователя; не измерение','Пайдаланушының сценарийлік болжамы','User-provided scenario assumption, not measured',lang)])
    for r in result['baseline_crops']:
        inputs.append([_crop_label(r['crop'],lang)+' '+_get('площадь / цена / затраты','аудан / баға / шығын','area / price / cost',lang),
            f"{r['area_ha']:.2f} ha; {r['price_kzt_t']:.0f} KZT/t; {r['other_cost_kzt_ha']:.0f} KZT/ha",
            r['water_reference']])
        for field, unit in [('yield_c_ha','ц/га'),('grid_kwh_ha','кВт·ч/га'),('diesel_l_ha','л/га'),('nitrogen_kg_n_ha','кг N/га')]:
            inputs.append([_crop_label(r['crop'],lang)+' · '+field, f'{r[field]:.4g} {unit}',
                           _get('Учебный ввод пользователя','Пайдаланушы болжамы','User scenario input',lang)])
    for a in result['scenarios']:
        inputs.append([a['name'],_get(f"Перевод {a['conversion_ha']:g} га; КРС {a['heads']:g} голов; мясо {a['meat_t_year']:g} т/год",
                                             f"Жер {a['conversion_ha']:g} га; мал {a['heads']:g} бас; ет {a['meat_t_year']:g} т/жыл",
                                             f"Conversion {a['conversion_ha']:g} ha; cattle {a['heads']:g}; meat {a['meat_t_year']:g} t/year",lang),
                       _get('Допущение пользователя','Пайдаланушы жорамалы','User scenario assumption',lang)])
    _margin_chart=None
    if all(r['total_margin_kzt'] is not None for r in result['scenarios']):
        _margin_chart={
            'title':_get('Расчётная маржа по сценариям, тг/год',
                         'Сценарий маржасы, тг/жыл','Scenario margin, KZT/year',lang),
            'section_title':_get('Сравнение экономических сценариев',
                                 'Экономикалық сценарий салыстыруы','Economic scenario comparison',lang),
            'categories':[r['name'] for r in result['scenarios']],
            'values':[r['total_margin_kzt'] for r in result['scenarios']],
            'axis_label':_get('тг/год','тг/жыл','KZT/year',lang),
            'value_label':_get('тг/год','тг/жыл','KZT/year',lang)}
    report={
        'mode_key':'mode6','mode_label':title,'lang':lang,'brand_translation':title,'generated_label':_get('Дата расчета','Есеп уақыты','Generated',lang),'generated_at':generated,
        'assessment_year':assessment_year,'summary_title':_get('Ключевые результаты','Негізгі нәтижелер','Key results',lang),
        'recommendations_title':_get('Сценарная рекомендация','Сценарий ұсынымы','Scenario recommendation',lang),
        'analysis_title':_get('Методические ограничения','Әдістемелік шектеулер','Methodological limits',lang),
        'table_title':_get('Сравнение направлений производства','Өндіріс бағыттарын салыстыру','Production-path comparison',lang),
        'inputs_title':_get('Условия, ограничения и источники','Шарттар мен дереккөздер','Assumptions and sources',lang),
        'parameter_label':_get('Показатель','Көрсеткіш','Parameter',lang),'source_label':_get('Источник / роль','Дереккөз','Source / role',lang),
        'summary':[{'label':_get('Общая территория, га','Барлық аумақ, га','Total area, ha',lang),'value':f'{result["total_farm_ha"]:,.2f}'},
                   {'label':_get('Допустимые сценарии','Рұқсат етілген нұсқалар','Feasible scenarios',lang),'value':f'{len(feasible)} / {len(result["scenarios"])}'}],
        'table':rows_out,
        'chart':_margin_chart,
        'recommendations':[{'title':_get('Сравнение при заданных ограничениях','Берілген шектеулермен салыстыру','Comparison under supplied limits',lang),
              'text':_get('Предпочтение по расчётной марже условно, только среди допустимых сценариев.',
                          'Маржа бойынша таңдау шартты, тек жарамды нұсқалар ішінде.',
                          'Margin-based preference is conditional and only among feasible scenarios.',lang),
              'evidence':(best['name'] if feasible else _get('Нет допустимых сценариев','Жарамды нұсқа жоқ','No feasible scenario',lang)),
              'effect':_get('Экологическое превосходство не подтверждено без данных о покупных кормах, навозе, почве и затратах на изменение деятельности.',
                             'Толық экологиялық қорытынды үшін жем, көң, топырақ, шығын деректері қажет.',
                             'Environmental superiority unconfirmed without complete feed, manure, soil and transition costs.',lang)}],
        'analysis':[_get('Справочно-сценарный расчёт ex ante. Орошение на посевы - по историческому зональному нормативу, не фактический водозабор. Питье КРС - отдельная годовая величина. Внешняя вода на корма НЕ входит в показатели воды на территории и остаётся неизвестной, если пользователь её не задал.',
                    'Алдын ала сценарийлік есеп. Жемнің сыртқы су шығыны автоматты нөл болмайды.',
                    'Ex-ante scenario. Crop irrigation is an historic zonal norm, not measured abstraction. Cattle drinking water is annual. Purchased-feed embedded water remains unknown unless entered.',lang),
                    _get('Выбросы - частичный прямой перечень: азотные удобрения, сжигание дизеля, сетевой CO₂, энтеральный метан. Навоз, цепочки кормов, изменение почвенного углерода и капитальные затраты могут изменить сравнение. Показатели не являются углеродной нейтральностью.',
                    'Шығарындылар ішінара есептелген: тыңайтқыш, дизель, электр, метан. Толық көміртек бейтараптығын білдірмейді.',
                    'Partial emissions cover direct fertilizer N₂O, on-site diesel, grid generation CO₂, enteric methane. Manure, feed supply chains, soil-carbon change and capex are not complete; not carbon neutrality.',lang)],
        'inputs':inputs,
    }
    st.session_state['last_report_payload']=report
    render_export_panel(report,lang)

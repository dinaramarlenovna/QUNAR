"""Integrated farm intervention scenarios embedded in Streamlit main workflow.

One calculation feeds user metrics AND the existing PDF/Word/Excel report payload.
All underlying hard water constraints remain unchanged unless separately opted in.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
from .integrated_scenarios import (
    FIELD_ETA, FAO_IRRIGATION, FAO_WATER_ACCOUNTING, IPCC_AFOLU,
    irrigation_reference, linked_pump_electricity, compare_farm_scenario,
)
from .water_norms import default_water_requirement, PUMPING_REFERENCE_KWH_PER_M3
from .producer_prices import reference_producer_price
from .irrigation_evidence import mixed_efficiency

L10N={
    'ru':{'head':'Единый сценарный расчёт: сейчас → после изменений',
          'intro':'Общий сценарий связывает воду, насосную энергию, выбросы и экономику. Это предварительные расчётные эффекты, а не подтверждённая экономия хозяйства.',
          'crop':'Растениеводство','livestock':'Животноводство',
          'now':'Сейчас','after':'После изменения','delta':'Изменение (после − сейчас)',
          'water':'Подача воды, м³','power':'Электроэнергия, кВт·ч',
          'co2':'Учтённые выбросы, кг CO₂e','cost':'Учтённые расходы, тг','margin':'Сценарная маржа, тг',
          'missing':'Недостаточно данных для показателя','sources':'Исходные данные и допущения',
          'warning':'Сокращение подачи воды не равно доказанной экономии безвозвратного потребления в бассейне.',
          'fallback':'Отсутствие фактического ввода не трактуется как ноль.',
          'button':'Рассчитать единый сценарий','figure':'Сценарный результат; не фактический эффект внедрения'},
    'en':{'head':'Integrated scenarios: baseline → proposed','intro':'One scenario links field water, pumping electricity, partial GHG and economics. Estimates are conditional, not observed achievements.',
          'crop':'Crop farming','livestock':'Livestock','now':'Baseline','after':'Proposed',
          'delta':'Change (proposed − baseline)','water':'Water delivered, m³','power':'Electricity, kWh',
          'co2':'Included emissions, kg CO₂e','cost':'Cost of known items','margin':'Indicative margin',
          'missing':'Insufficient data','sources':'Inputs and assumptions','warning':'Lower field delivery does not prove reduced basin consumption.',
          'fallback':'Missing data are not set to zero.','button':'Calculate integrated scenario',
          'figure':'Conditional scenario, not a verified achieved impact'},
    'kk':{'head':'Біріктірілген сценарий: бастапқы → жаңа жағдай','intro':'Сценарий су, сорғы энергиясын, ішінара шығарындыларды және экономиканы біріктіреді. Бұл нақты іске асыру әсері емес.',
          'crop':'Өсімдік шаруашылығы','livestock':'Мал шаруашылығы','now':'Бастапқы','after':'Сценарий',
          'delta':'Өзгеріс (сценарий − бастапқы)','water':'Берілетін су, м³','power':'Электр энергиясы, кВт·сағ',
          'co2':'Есепке алынған шығарындылар, кг CO₂e','cost':'Белгілі шығындар, тг','margin':'Сценарийлік маржа, тг',
          'missing':'Деректер жеткіліксіз','sources':'Бастапқы деректер мен жорамалдар',
          'warning':'Судың берілуін қысқарту бассейндегі нақты тұтынуды азайтуды дәлелдемейді.',
          'fallback':'Жоқ деректер нөл деп есептелмейді.','button':'Біріктірілген сценарийді есептеу',
          'figure':'Нақты әсер емес, сценарийлік есеп'},
}
METHODS={
 'ru':{'furrow':'Бороздовой','sprinkler':'Дождевание','drip':'Капельное','mixed':'Смешанный'},
 'en':{'furrow':'Furrow / surface','sprinkler':'Sprinkler','drip':'Drip','mixed':'Mixed'},
 'kk':{'furrow':'Бороздалап','sprinkler':'Жаңбырлатып','drip':'Тамшылатып','mixed':'Аралас'},
}

def _label(ru, en, kk, lang):
    return {'ru':ru,'en':en,'kk':kk}[lang]

def _m(value):
    return '—' if value is None else f'{float(value):,.1f}'


def _number(label, value=0.0, key='', step=1.0, maximum=None, help=None):
    kw={'min_value':0.0,'value':float(value or 0.0),'step':float(step),'key':key,'help':help}
    if maximum is not None: kw['max_value']=float(maximum)
    return st.number_input(label, **kw)


def render_integrated_scenario(*, lang, mode_key, district, crop, area_ha, irrigation_type,
                               observed_water_m3, observed_energy_kwh, grid_factor,
                               water_tariff, electricity_tariff, expected_yield_c_ha,
                               selling_price_kzt_t, other_cost_kzt_ha,
                               livestock_heads, livestock_species, livestock_production_amount,
                               livestock_production_kind, livestock_reference=None,
                               assessment_year=2026, crop_label=None):
    """Return report fragment or None. Values are recomputed on every rerun.

    This is a stand-alone counterfactual; it never writes crop-optimizer budgets
    or changes the existing model's calibrated coefficients.
    """
    tr=L10N.get(lang,L10N['ru'])
    kind='livestock' if mode_key=='mode5' else 'crop'
    with st.expander(tr['head'], expanded=False):
        st.caption(tr['intro'])
        if kind=='crop':
            crop_code = crop
            from .config import CROPS
            if crop_code is None:
                crop_code=st.selectbox(_label('Культура для сценария','Scenario crop','Сценарий дақылы',lang),
                                       list(CROPS),key='integrated_crop')
            if crop_code=='Rice':
                st.warning(_label('Для затопляемого риса простая замена КПД полива некорректна: нужен отдельный баланс слоя воды и фильтрации. Сценарий будет доступен после такой калибровки.',
                                  'Paddy rice requires a flooded-water and percolation balance; a generic efficiency switch is invalid.',
                                  'Күрішке су қабаты мен сүзілуді есептейтін бөлек баланс қажет.',lang))
                return None
            default_method=irrigation_type if irrigation_type in (*FIELD_ETA,'mixed') else 'furrow'
            if irrigation_type not in (*FIELD_ETA,'mixed'):
                st.caption(_label('Тек для сценария исходным способом принят бороздовой полив; это НЕ установленная технология хозяйства.',
                                  'Furrow is an assumed baseline, NOT observed irrigation method.',
                                  'Бастапқы әдіс ретінде бороздалап суару болжанды; бұл шаруашылықта расталмаған.',lang))
            p1,p2=st.columns(2)
            methods=list(FIELD_ETA)+['mixed']
            with p1:
                method_before=st.selectbox(_label('Сейчас: способ полива','Current irrigation method','Қазіргі суару тәсілі',lang),
                                          methods,index=methods.index(default_method),
                                          format_func=lambda m:METHODS[lang][m],key='integrated_before_method')
            with p2:
                method_after=st.selectbox(_label('Предлагаемый способ','Proposed method','Ұсынылатын әдіс',lang),
                                         methods,index=2,
                                         format_func=lambda m:METHODS[lang][m],key='integrated_after_method')
            def _mix_input(side):
                st.caption(_label('Доли площади по способам орошения должны давать 100%:',
                                  'Area shares must sum to 100%:',
                                  'Суару тәсілдерінің ауданы 100% болуы қажет:',lang))
                cc=st.columns(3)
                defaults=(60.,20.,20.)
                shares={}
                for context,key_m,def_pct in zip(cc,FIELD_ETA,defaults):
                    with context:
                        shares[key_m]=_number(METHODS[lang][key_m]+' (%)',def_pct,
                                              f'integrated_mix_{side}_{key_m}',maximum=100.,step=5.)/100
                return mixed_efficiency(shares)
            try:
                eta_b=_mix_input('baseline') if method_before=='mixed' else FIELD_ETA[method_before]
                eta_p=_mix_input('proposed') if method_after=='mixed' else FIELD_ETA[method_after]
            except ValueError as exc:
                st.warning(str(exc))
                return None
            surface_norm=default_water_requirement(district,crop_code,'furrow')
            supported=surface_norm.norm_crop is not None and surface_norm.source_tier!='regional_fallback'
            base_net=surface_norm.m3_ha*FIELD_ETA['furrow'] if supported else 0.0
            water_origin=_label('Справочный сценарий: норма поверхностного полива 108-НҚ × 0,60 (FAO), либо ввод своих данных',
                                'Reference: surface irrigation norm × FAO 0.60, or enter own net demand',
                                'Анықтамалық: беткі суару нормасы × FAO 0,60 немесе деректі енгізіңіз',lang)
            if not supported:
                st.warning(_label('Для этой культуры/района нет непосредственно сопоставимой нормы: введите чистую потребность в поливе по FAO-56 или данным хозяйства.',
                                  'No directly comparable norm for this crop/district. Provide independently estimated net irrigation.',
                                  'Дақыл/аудан үшін салыстырмалы норма жоқ, таза суару қажеттілігін енгізіңіз.',lang))
            net=_number(_label('Чистая потребность в поливе, м³/га (за сезон)','Net irrigation requirement, m³/ha (season)',
                               'Таза суару қажеттілігі, м³/га',lang),base_net,
                        f'integrated_net_{district}_{crop_code}',step=100.0,help=water_origin)
            measured_field=False
            if observed_water_m3 and observed_water_m3>0:
                measured_field=st.checkbox(_label('Использовать введённый ранее ФАКТИЧЕСКИЙ объём как подачу на поле, м³ (только если граница учёта подтверждена)',
                                                 'Use earlier OBSERVED water as delivered to field (confirm meter boundary)',
                                                 'Енгізілген нақты су көлемін танапқа берілген су ретінде қолдану',lang),
                                           value=False,key='integrated_use_metered_field')
                if measured_field:
                    net=observed_water_m3*eta_b/area_ha
                    st.caption(_label('Чистая потребность получена из фактической подачи × предполагаемый КПД. Это сценарная реконструкция, не измеренная ETc.',
                                      'Net demand inferred from observed field delivery x assumed efficiency, not observed ETc.',
                                      'Таза қажеттілік нақты суды берудің КПД-мен жорамалды есебінен алынды.',lang))
            if net<=0:
                st.info(_label('Без ненулевой и обоснованной потребности в воде расчёт смены орошения невозможен.',
                               'A sourced positive net irrigation requirement is needed.',
                               'Негізделген оң суару мөлшері қажет.',lang))
                return None
            baseline=irrigation_reference(net_m3_ha=net,area_ha=area_ha,before_method=method_before,
                                          after_method=method_after,
                                          before_efficiency=eta_b if method_before=='mixed' else None,
                                          after_efficiency=eta_p if method_after=='mixed' else None,
                                          water_reference=('User observed FIELD delivery, inferred net using FAO eta' if measured_field else (surface_norm.source_label+'; inferred net from surface reference') if supported and abs(net-base_net)<1e-6 else 'User-entered net irrigation'))
            w=baseline
            bw,pw=w['baseline_field_m3'],w['scenario_field_m3']
            period=_label('Полный сезон выбранной культуры','Full crop season','Дақылдың толық маусымы',lang)
            water_note=w['evidence']
            st.caption(_label('Сравнение относится к ПОДАЧЕ НА ПОЛЕ; потери в каналах и возвратные воды здесь не оценены.',
                              'The comparison covers FIELD delivery; conveyance loss and return flows are not estimated here.',
                              'Бұл танапқа БЕРІЛЕТІН су; арна шығыны мен қайтарымды су есептелмеген.',lang))
        else:
            method_before=method_after=None
            crop_code=None
            ref = (livestock_reference or {}).get('reference_water_m3_year')
            knownwater=observed_water_m3 if observed_water_m3 and observed_water_m3>0 else ref
            bw = _number(_label('Текущее потребление воды, м³/год','Baseline water, m³/year','Жылдық су тұтыну, м³',lang),
                         knownwater,'integrated_livestock_water',step=50.0)
            water_cut=_number(_label('Сокращение расхода воды по сценарию, %','Water-use reduction assumption, %',
                                    'Су тұтынуын төмендету жорамалы, %',lang),10.,'integrated_livestock_water_cut',
                              step=5.,maximum=90.)
            pw=bw*(1-water_cut/100) if bw>0 else None
            bw=bw if bw>0 else None
            water_note='User-entered/mode observation' if observed_water_m3 and observed_water_m3>0 else 'Species reference; not actual observed consumption'
            st.caption(_label('Для животноводства сценарий сокращения воды задаётся отдельно: FAO-эффективность полива не применяется к питьевой воде животных.',
                              'Livestock water saving requires a separate assumption; irrigation efficiencies do not apply to drinking water.',
                              'Мал ішетін суға суару тиімділігінің коэффициенттері қолданылмайды.',lang))
            period=_label('Один календарный год','One calendar year','Бір жыл',lang)
        st.markdown('**'+_label('Энергия и ресурсы','Energy and resources','Энергия мен ресурстар',lang)+'**')
        pump_share = _number(
            _label('Доля воды, которую подают НАСОСОМ, % (0 = не подтверждена/самотёк)',
                   'Share of delivered water PUMPED, % (0 = unknown/gravity)',
                   'СОРҒЫМЕН жеткізілетін су үлесі, % (0 = белгісіз/өздігінен ағу)',lang),
            0.,'integrated_pumped_share',step=10.,maximum=100.)
        if pump_share==0:
            st.caption(_label('Без подтверждения насосной подачи снижение электроэнергии из экономии воды НЕ предполагается.',
                              'Water savings do not imply electricity savings without pumping evidence.',
                              'Сорғы көрсетілмесе, су үнемінен электр үнемі есептелмейді.',lang))
        c1,c2,c3=st.columns(3)
        with c1:
            pump_b=_number(_label('Насос сейчас, кВт·ч/м³','Current pump, kWh/m³','Қазіргі сорғы, кВт·сағ/м³',lang),
                           PUMPING_REFERENCE_KWH_PER_M3 if kind=='crop' else 0.,'integrated_pump_b',step=.05,
                           help='Scenario engineering assumption, not a farm meter reading.')
        with c2:
            pump_p=_number(_label('Насос после, кВт·ч/м³','Proposed pump, kWh/m³','Жаңа сорғы, кВт·сағ/м³',lang),
                           PUMPING_REFERENCE_KWH_PER_M3 if kind=='crop' else 0.,'integrated_pump_p',step=.05)
        with c3:
            efficiency_pct=_number(_label('Экономия прочей электроэнергии, %','Other electricity efficiency improvement, %',
                                          'Басқа электр энергиясын үнемдеу, %',lang),10. if kind=='livestock' else 0.,'integrated_power_cut',step=5.,maximum=90.)
        observed_kwh=observed_energy_kwh if observed_energy_kwh and observed_energy_kwh>0 else None
        if pump_share==0 or bw is None:
            pb=observed_kwh
            pp=observed_kwh*(1-efficiency_pct/100) if observed_kwh is not None else None
            energy_boundary='observed electricity; pumping savings not inferred'
        else:
            try:
                elect=linked_pump_electricity(baseline_total_kwh=observed_kwh,
                                              baseline_water_m3=(bw or 0.)*pump_share/100,
                                              scenario_water_m3=(pw or 0.)*pump_share/100,
                                              before_kwh_m3=pump_b,after_kwh_m3=pump_p,
                                              other_energy_reduction_pct=efficiency_pct)
                pb,pp=elect['baseline_kwh'],elect['scenario_kwh']
                energy_boundary=elect['boundary']
                if kind=='livestock' and observed_kwh is None and pump_b==0 and pump_p==0:
                    pb=pp=None
                if energy_boundary=='pumping_only':
                    st.caption(_label('Электроэнергия рассчитана ТОЛЬКО для насосов. Прочие затраты энергии не входят.',
                                      'Electricity is for PUMPS ONLY, not the whole enterprise.',
                                      'Энергия тек СОРҒЫЛАР үшін есептелді.',lang))
            except ValueError as exc:
                st.warning(str(exc))
                return None
        st.markdown('##### '+_label('Выбросы и экономика: уточнение допущений',
                                  'Emissions and economics assumptions',
                                  'Шығарындылар және экономикалық жорамалдар',lang))
        with st.container():
            grid_before=_number(_label('Доля сетевой электроэнергии сейчас, %','Current grid share, %','Электр желісінің бастапқы үлесі, %',lang),
                                100.,'integrated_grid_b',maximum=100.,step=5.)
            grid_after=_number(_label('Доля сетевой электроэнергии после, %','Proposed grid share, %','Электр желісінің жаңа үлесі, %',lang),
                               100.,'integrated_grid_p',maximum=100.,step=5.)
            green_cost=None
            if grid_before<100. or grid_after<100.:
                green_cost=_number(_label('Себестоимость собственной электроэнергии, тг/кВт·ч','On-site electricity running cost, KZT/kWh',
                                         'Өз электрінің пайдалану құны, тг/кВт·сағ',lang),0.,'integrated_green_cost',step=1.)
                st.caption(_label('0 можно указывать только при доказанном отсутствии текущих расходов. Капитальные затраты отдельно не учитываются.',
                                  'Zero is only valid if there are no running costs; no capital costs included.',
                                  '0 тек шынымен шығын болмағанда; күрделі шығындар енгізілмейді.',lang))
            diesel_known=st.checkbox(_label('Есть нормы расхода дизеля для обоих вариантов','Diesel activity known for both scenarios',
                                             'Дизель шығыны екі нұсқада белгілі',lang),value=False,key='integrated_diesel_known')
            db=dp=dp_price=None; diesel_in_other_cost=False
            if diesel_known:
                d1,d2,d3=st.columns(3)
                with d1: db=_number(_label('Дизель сейчас, л','Diesel baseline, L','Дизель бастапқы, л',lang),0.,'integrated_diesel_b',step=50.)
                with d2: dp=_number(_label('Дизель после, л','Diesel proposed, L','Дизель жаңа, л',lang),0.,'integrated_diesel_p',step=50.)
                with d3: dp_price=_number(_label('Дизель, тг/л (если отдельно от прочих затрат)','Diesel price KZT/L (only if not in other costs)',
                                                   'Дизель бағасы, тг/л (басқа шығынға кірмесе)',lang),0.,'integrated_diesel_price',step=10.)
                diesel_in_other_cost=st.checkbox(_label('Дизель уже включён в прочие расходы; отдельно повторно НЕ считать',
                                                       'Diesel is already included in other costs (no double count)',
                                                       'Дизель басқа шығындарда қамтылған, қайта есептемеңіз',lang),
                                                value=False,key='integrated_diesel_in_other')
            n_known=False; nb=np_=None
            if kind=='crop':
                n_known=st.checkbox(_label('Известна норма внесения азота в обоих вариантах','Nitrogen fertilizer is known for both scenarios',
                                               'Азот тыңайтқышы екі нұсқада белгілі',lang),value=False,key='integrated_n_known')
                if n_known:
                    n1,n2=st.columns(2)
                    with n1: nb=_number(_label('Азот сейчас, кг N за хозяйство','Baseline N, kg','Бастапқы N, кг',lang),0.,'integrated_n_b',step=10.)
                    with n2: np_=_number(_label('Азот после, кг N за хозяйство','Proposed N, kg','Жаңа N, кг',lang),0.,'integrated_n_p',step=10.)
            methane_on=False; mb=mp=None; methane_evidence=''
            if kind=='livestock':
                methane_on=st.checkbox(_label('Рассчитать метан пищеварения, если есть коэффициенты IPCC/исследования',
                                              'Include enteric methane with sourced factors',
                                              'Дереккөз болса күйіс метанын есептеу',lang),value=False,key='integrated_ch4_enable')
                if methane_on:
                    m1,m2=st.columns(2)
                    with m1: mb=_number(_label('Сейчас, кг CH₄/голову/год','CH4 baseline kg/head/yr',
                                              'CH₄ бастапқы кг/бас/жыл',lang),0.,'integrated_ch4_b',step=1.)
                    with m2: mp=_number(_label('После, кг CH₄/голову/год','CH4 proposed kg/head/yr',
                                              'CH₄ жаңа кг/бас/жыл',lang),0.,'integrated_ch4_p',step=1.)
                    methane_evidence=st.text_input(_label('Основание изменения фактора метана','Methane factor evidence',
                                                        'Метан факторының дереккөзі',lang),key='integrated_ch4_evidence')
                    st.caption(_label('Поголовье сохраняется; снижение выбросов не назначается автоматически.',
                                      'Herd remains constant; methane reduction is not assigned automatically.',
                                      'Мал саны өзгермейді; метан төмендеуі автоматты емес.',lang))
            manure_on=False; manure_b=manure_p=None; manure_evidence=''
            if kind=='livestock':
                manure_on=st.checkbox(_label('Добавить CH₄ навоза по сопоставимым коэффициентам',
                                             'Include manure methane with matched factors',
                                             'Көң метанын есептеу',lang),value=False,key='integrated_manure_enable')
                if manure_on:
                    mm1,mm2=st.columns(2)
                    with mm1: manure_b=_number(_label('Навоз сейчас, кг CH₄/голову/год',
                                                      'Manure CH4 baseline, kg/head/year',
                                                      'Көң CH₄ бастапқы, кг/бас/жыл',lang),0.,'integrated_manure_b',step=1.)
                    with mm2: manure_p=_number(_label('Навоз после, кг CH₄/голову/год',
                                                      'Manure CH4 proposed, kg/head/year',
                                                      'Көң CH₄ жаңа, кг/бас/жыл',lang),0.,'integrated_manure_p',step=1.)
                    manure_evidence=st.text_input(_label('Основание изменения фактора CH₄ навоза',
                                                         'Evidence for manure CH4 factor',
                                                         'Көң метаны факторының дереккөзі',lang),
                                                   key='integrated_manure_evidence')
            other_b=other_p=revenue_b=revenue_p=None
            crop_price=0.
            if kind=='crop':
                y=_number(_label('Урожайность, ц/га','Yield, centners/ha','Өнімділік, ц/га',lang),
                          expected_yield_c_ha,'integrated_yield',step=1.)
                try:
                    regional_price=reference_producer_price(crop_code,as_of_year=min(int(assessment_year)-1,2025))
                except (ValueError,OSError):
                    regional_price=None
                suggested_price=(selling_price_kzt_t if selling_price_kzt_t and selling_price_kzt_t>0
                                 else (regional_price.price_kzt_t if regional_price else 0.))
                if regional_price and not (selling_price_kzt_t and selling_price_kzt_t>0):
                    st.caption(regional_price.source_label)
                crop_price=_number(_label('Цена продажи, тг/т','Selling price, KZT/t','Сату бағасы, тг/т',lang),
                                   suggested_price,f'integrated_price_{crop_code}',step=100.)
                ydelta=_number(_label('Изменение урожайности, % (гипотеза)','Yield change assumption, %',
                                        'Өнімділік өзгерісі болжамы, %',lang),0.,'integrated_yield_change',maximum=100.,step=5.)
                unit_cost=_number(_label('Прочие полные переменные затраты БЕЗ воды, энергии и дизеля, тг/га',
                                         'Other variable costs excluding water/energy/diesel, KZT/ha',
                                         'Басқа шығындар (су, энергия, дизельсіз), тг/га',lang),
                                  other_cost_kzt_ha,'integrated_cost',step=1000.)
                if y>0 and crop_price>0:
                    revenue_b=area_ha*y/10*crop_price
                    revenue_p=revenue_b*(1+ydelta/100)
                if unit_cost>0:
                    proposed_unit_cost=_number(_label('Прочие переменные затраты ПОСЛЕ изменения, тг/га',
                                                      'Proposed other variable costs, KZT/ha',
                                                      'Өзгергеннен кейінгі басқа шығын, тг/га',lang),
                                               unit_cost,f'integrated_cost_after_{crop_code}',step=1000.)
                    other_b=unit_cost*area_ha
                    other_p=proposed_unit_cost*area_ha
            else:
                unit=_label('т продукции / тыс. яиц','tonnes of output / thousand eggs',
                            'өнім тоннасы / мың жұмыртқа',lang)
                unit_price=_number(_label('Цена за единицу '+unit,'Price per output unit','Өнім бірлігінің бағасы',lang),
                                   0.,'integrated_livestock_price',step=1000.)
                revenue_b=(livestock_production_amount*unit_price if livestock_production_amount>0 and unit_price>0 else None)
                revenue_p=revenue_b  # no invented yield benefit
                other_cost=_number(_label('Прочие годовые расходы (без воды, энергии, дизеля), тг',
                                         'Other annual farm costs (excl. water, energy, diesel), KZT',
                                         'Басқа жылдық шығындар, тг',lang),0.,'integrated_livestock_cost',step=10000.)
                if other_cost>0:
                    new_other_cost=_number(_label('Прочие годовые расходы ПОСЛЕ изменений, тг',
                                                   'Proposed other annual costs, KZT',
                                                   'Өзгергеннен кейінгі жылдық шығын, тг',lang),
                                           other_cost,'integrated_livestock_cost_after',step=10000.)
                    other_b=other_cost
                    other_p=new_other_cost
            after_extra=_number(_label('Дополнительные сезонные/годовые текущие затраты после изменения, тг',
                                       'Additional proposed recurring operating costs, KZT',
                                       'Жаңа ағымдағы шығындар, тг',lang),0.,'integrated_extra_cost',step=1000.)
            completed=st.checkbox(_label('Подтверждаю: все переменные затраты учтены, прочие статьи не дублируют воду/энергию/дизель',
                                         'I confirm all relevant variable costs are covered and non-overlapping',
                                         'Айнымалы шығындардың толықтығын растаймын',lang),value=False,key='integrated_costs_complete')
            evidence=st.text_input(_label('Основание допущений/источник (при необходимости уточните)','Assumptions and evidence',
                                           'Дереккөз және жорамалдар',lang),
                                   value='FAO reference irrigation; user-entered scenario assumptions',
                                   key='integrated_evidence')
        if not evidence.strip():
            st.warning(_label('Нужно указать источник или допущение.','Evidence/assumption is required.',
                              'Дереккөз немесе болжам қажет.',lang))
            return None
        if kind=='livestock' and (methane_on or manure_on) and livestock_heads<=0:
            st.warning(_label('Для метана необходимо поголовье, введённое пользователем. Районный ориентир не подходит для конкретной фермы.',
                              'User-entered farm herd size is needed for enteric methane.',
                              'Метан үшін нақты мал саны қажет.',lang))
            return None
        try:
            results=compare_farm_scenario(
                farm_kind=kind,period=period,evidence=evidence,
                water_before_m3=bw,water_after_m3=pw,water_boundary='field_delivery' if kind=='crop' else 'metered_total',
                electricity_before_kwh=pb,electricity_after_kwh=pp,electricity_boundary=energy_boundary,
                grid_fraction_before=grid_before/100,grid_fraction_after=grid_after/100,
                grid_emission_kgco2e_kwh=grid_factor if grid_factor>0 else None,
                water_tariff_kzt_m3=water_tariff,electricity_tariff_kzt_kwh=electricity_tariff,
                renewable_operating_kzt_kwh=green_cost if green_cost is not None else 0.,
                diesel_before_l=db,diesel_after_l=dp,diesel_kzt_l=dp_price if dp_price else None,
                diesel_in_other_cost=diesel_in_other_cost,
                n_before_kg=nb,n_after_kg=np_,
                enteric_heads=livestock_heads if methane_on else None,
                enteric_ch4_before_kg_head_year=mb if methane_on else None,
                enteric_ch4_after_kg_head_year=mp if methane_on else None,
                methane_change_evidence=methane_evidence,
                include_manure=manure_on,
                manure_ch4_before_kg_head_year=manure_b,
                manure_ch4_after_kg_head_year=manure_p,
                manure_change_evidence=manure_evidence,
                revenue_before_kzt=revenue_b,revenue_after_kzt=revenue_p,
                other_cost_before_kzt=other_b,other_cost_after_kzt=other_p,
                costs_complete=completed,include_nitrogen=(kind=='crop'),include_enteric=methane_on,
                extra_cost_after_kzt=after_extra)
        except ValueError as exc:
            st.warning(str(exc))
            return None
        rows=[]
        def add(label,a,b,unit=''):
            if a is not None and b is not None:
                rows.append({'':label,tr['now']:_m(a)+unit,tr['after']:_m(b)+unit,
                             tr['delta']:_m(b-a)+unit})
        add(tr['water'],results['water_before_m3'],results['water_after_m3'])
        add(tr['power'],results['energy_before_kwh'],results['energy_after_kwh'])
        add(tr['co2'],results['ghg_before_kgco2e'],results['ghg_after_kgco2e'])
        # known spend is *not* a complete spend when costs_complete=False
        known=results['known_cost_components_kzt']
        add(tr['cost']+' ('+_label('известные статьи','known items','белгілі баптар',lang)+')',
            sum(x[0] for x in known.values()) if known else None,
            sum(x[1] for x in known.values()) if known else None)
        add(tr['margin'],results['margin_before_kzt'],results['margin_after_kzt'])
        add(_label('Маржа, стресс-сценарий: выручка −10%, затраты +10%',
                   'Stress margin: revenue −10%, costs +10%',
                   'Стресс-маржа: түсім −10%, шығын +10%',lang),
            results['stress_margin_before_kzt'],results['stress_margin_after_kzt'])
        if rows:
            st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
        if results['margin_increase_kzt'] is None:
            st.caption(_label('Полная маржа не выводится: не подтверждена полнота цен, выпуска и производственных затрат. Показана только разница известных расходов.',
                              'No full margin: revenue or variable cost completeness unverified. Known spending difference only.',
                              'Толық маржа анықталмаған: өнім, баға немесе шығындар жеткіліксіз.',lang))
        if kind=='crop':
            st.caption(water_note)
        st.caption(tr['warning'])
        st.caption(tr['figure'])
        if results['ghg_components_kgco2e']:
            st.markdown('##### '+_label('Какие источники выбросов учтены',
                                        'Emission-source breakdown','Шығарынды көздері',lang))
            with st.container():
                st.dataframe(pd.DataFrame([
                    {'Компонент / Component':key,tr['now']:_m(pair[0]),tr['after']:_m(pair[1]),
                     tr['delta']:_m(pair[1]-pair[0])}
                    for key,pair in results['ghg_components_kgco2e'].items()
                ]),hide_index=True,use_container_width=True)
        st.caption(_label('Выбросы охватывают только показанные компоненты. Неизвестное не означает 0. Электрическая доля — операционные, не жизненные выбросы.',
                          'Only displayed emission components are covered. Missing is not zero. Electricity accounting is operational.',
                          'Тек көрсетілген шығарындылар қамтылған. Жоқ дерек нөл емес.',lang))
        st.caption('FAO: '+FAO_IRRIGATION+' | '+FAO_WATER_ACCOUNTING+' | IPCC: '+IPCC_AFOLU)
        summary=[]
        for tag,a,b,unit in [
            ('Integrated field water',results['water_before_m3'],results['water_after_m3'],'m3'),
            ('Integrated electricity',results['energy_before_kwh'],results['energy_after_kwh'],'kWh'),
            ('Integrated partial operational GHG',results['ghg_before_kgco2e'],results['ghg_after_kgco2e'],'kg CO2e'),
            ('Integrated indicative margin',results['margin_before_kzt'],results['margin_after_kzt'],'KZT'),
        ]:
            if a is not None:
                summary.extend([
                    {'label':tag+' baseline, '+unit,'value':f'{a:.2f}', 'note':tr['figure']},
                    {'label':tag+' after, '+unit,'value':f'{b:.2f}', 'note':tr['figure']},
                    {'label':tag+' difference after-baseline, '+unit,'value':f'{b-a:+.2f}','note':tr['figure']},
                ])
        for source,(bkg,pkg) in results['ghg_components_kgco2e'].items():
            summary.append({'label':'Integrated GHG source: '+source+' difference after-baseline, kg CO2e',
                            'value':f'{pkg-bkg:+.2f}',
                            'note':'Partial IPCC-based scenario only; not full life-cycle or observed emissions'})
        if results['stress_margin_increase_kzt'] is not None:
            summary.append({'label':'Integrated stress margin difference after-baseline, KZT',
                            'value':f"{results['stress_margin_increase_kzt']:+.2f}",
                            'note':'Stylized sensitivity: revenue −10%, costs +10%; not a probabilistic interval'})
        if results['known_cost_components_kzt']:
            summary.append({'label':'Integrated known operating cost reduction, KZT',
                            'value':f"{results['known_cost_reduction_kzt']:+.2f}",
                            'note':'Only priced components; not necessarily full contribution margin'})
        inputs=[['Integrated intervention period',period,tr['figure']],
                ['Integrated scenario methods',f'{method_before} → {method_after}' if kind=='crop' else 'livestock user assumption',
                 water_note],
                ['Integrated scenario electricity boundary',energy_boundary,'Pump source and total split'],
                ['Integrated emission components',', '.join(results['ghg_components_kgco2e']) or 'none',
                 'IPCC partial boundary; none = unavailable, not 0'],
                ['Integrated scenario economic cost confirmation',str(bool(completed)),'User confirmation'],
                ['Integrated water source and volume',f'{water_note}; before={bw}, after={pw}',
                 'FAO normative reconstruction or user scenario; field delivery for crop'],
                ['Integrated pumping parameters',f'pumped_fraction={pump_share}%; before={pump_b}, after={pump_p} kWh/m3',
                 'Editable engineering assumptions, not instrument measurements'],
                ['Integrated unit prices',f'water={water_tariff} KZT/m3; grid electricity={electricity_tariff} KZT/kWh; EF={grid_factor} kgCO2e/kWh',
                 'Editable reference assumptions; verify applicable billing point and reporting year'],
                ['Integrated scenario evidence',evidence,'FAO / IPCC / user assumptions'],
                ['Integrated reference links',f'{FAO_IRRIGATION}; {FAO_WATER_ACCOUNTING}; {IPCC_AFOLU}','Scientific sources']]
        return {'summary':summary,'inputs':inputs,
                'recommendation':{'title':tr['head'],
                                  'text':tr['intro'],
                                  'evidence':f"{results['scope']}; {evidence}; water={water_note}; energy={energy_boundary}",
                                  'effect':f"Water field delivery Δ {_m(results['water_reduction_m3'])} m3 saved; energy Δ {_m(results['energy_reduction_kwh'])} kWh saved; partial GHG Δ {_m(results['partial_ghg_reduction_kgco2e'])} kg CO2e potentially reduced; margin change {_m(results['margin_increase_kzt'])} KZT. Not actual achieved effects."}}

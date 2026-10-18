"""Output-only translation of known technical labels from older QŪNAR modules.

Same normalised payload is consumed by XLSX, PDF, DOCX, including combined reports.
Identifiers, references, numeric values and URLs remain unchanged.
"""
from copy import deepcopy
import re
import math

# Exact internal captions found in deployed versions and the sample user PDF.
EXACT={
 'Тариф: electricity':('Тариф электроэнергии','Электр энергиясы тарифі','Electricity tariff'),
 'Тариф: water':('Тариф подачи воды','Су жеткізу тарифі','Water delivery tariff'),
 'tariff: electricity':('Тариф электроэнергии','Электр энергиясы тарифі','Electricity tariff'),
 'tariff: water':('Тариф подачи воды','Су жеткізу тарифі','Water delivery tariff'),
 'Indicator':('Показатель','Көрсеткіш','Indicator'),
 'Value':('Значение','Мәні','Value'),
 'Note':('Примечание','Ескертпе','Note'),
 'Crop':('Культура','Дақыл','Crop'),
 'District':('Район','Аудан','District'),
 'Area, ha':('Площадь, га','Аудан, га','Area, ha'),
 'Water, m³':('Вода, м³','Су, м³','Water, m³'),
 'Electricity, kWh':('Электроэнергия, кВт·ч','Электр энергиясы, кВт·сағ','Electricity, kWh'),
 'Margin, KZT':('Маржа, тг','Маржа, тг','Margin, KZT'),
 'Partial GHG, kg CO₂e':('Учтённые выбросы, кг CO₂e','Есептелген шығарындылар, кг CO₂e','Partial GHG, kg CO₂e'),
 'Status':('Статус','Мәртебе','Status'),
 'FAO-56 ET0 baseline Apr-Sep, mm':('FAO-56: исходное испарение ET₀ (апрель-сентябрь), мм','FAO-56: бастапқы ET₀ (сәуір-қыркүйек), мм','FAO-56 baseline ET₀ Apr-Sep, mm'),
 'FAO-56 evidence and assumptions':('FAO-56: источники и допущения','FAO-56: дереккөздер мен жорамалдар','FAO-56 evidence and assumptions'),
 'Daily FAO-56 field delivery scenario m³/ha':('Суточный расчёт FAO-56: подача воды на поле, м³/га','FAO-56 тәуліктік есеп: танапқа берілген су, м³/га','Daily FAO-56 field delivery, m³/ha'),
 'Daily root-zone soil scenario':('Суточный сценарий влажности корневой зоны','Тамыр аймағының тәуліктік ылғал сценарийі','Daily root-zone soil scenario'),
 'Optimizer water-accounting boundary':('Границы водного баланса оптимизатора','Оңтайландырудағы су теңгерімі шекарасы','Optimizer water-accounting boundary'),
 'Farm crop-mix water scenario assumptions':('Допущения водного сценария по культурам хозяйства','Шаруашылық дақылдарының су сценарийі жорамалдары','Farm crop-mix water scenario assumptions'),
 'A1 crop-level GHG assumptions':('A1: допущения по выбросам отдельных культур','A1: дақылдар бойынша шығарынды жорамалдары','A1 crop-level GHG assumptions'),
 'FAO-56 historical baseline':('FAO-56: историческая климатическая база','FAO-56: тарихи климаттық база','FAO-56 historical baseline'),
 'physical_model':('Расчётная физическая модель','Физикалық есептік модель','Physics-based estimate'),
 'zone_fallback':('Подстановка по официальной водохозяйственной зоне','Ресми су шаруашылығы аймағы бойынша мән','Official water-zone fallback'),
 'regional_fallback':('Среднее по региону, не измерение','Өңірлік орташа, өлшенбеген','Regional reference, not measured'),
 'user_observed':('Фактические данные пользователя','Пайдаланушының нақты деректері','User observed data'),
 'unknown_electricity_no_estimate':('Энергопотребление неизвестно: оценка не выполнена','Электр энергиясы белгісіз: есеп жоқ','Electricity unknown, no estimate'),
 'observed electricity; pumping savings not inferred':('Измеренное электричество; экономия насосов не предполагается','Өлшенген электр; сорғы үнемі болжанбады','Measured electricity; pumping savings not inferred'),
 'pumping_only':('Только насосы; остальная энергия не учтена','Тек сорғы; қалған энергия есептелмейді','Pumps only; other energy excluded'),
 'none':('не установлено','анықталмаған','none'),
 'False':('Нет','Жоқ','No'),
 'True':('Да','Иә','Yes'),
 'Scenario engineering assumption, not a farm meter reading.':('Инженерное допущение сценария, не показание прибора учёта.','Сценарийлік инженерлік болжам, өлшеу құралының дерегі емес.','Scenario engineering assumption, not a meter reading.'),
 'Integrated field water baseline, m3':('Единый сценарий: подача воды до изменений, м³','Біріктірілген сценарий: бастапқы су, м³','Integrated scenario: water before, m³'),
 'Integrated field water after, m3':('Единый сценарий: подача воды после изменений, м³','Біріктірілген сценарий: жаңа су, м³','Integrated scenario: water after, m³'),
 'Integrated field water difference after-baseline, m3':('Единый сценарий: разница подачи воды, м³','Біріктірілген сценарий: су айырмасы, м³','Integrated scenario: water difference, m³'),
 'Integrated known operating cost reduction, KZT':('Единый сценарий: сокращение известных текущих затрат, тг','Біріктірілген сценарий: белгілі шығын үнемі, тг','Integrated scenario: known cost reduction, KZT'),
 'Integrated intervention period':('Единый сценарий: период','Біріктірілген сценарий: кезең','Integrated scenario: period'),
 'Integrated scenario methods':('Способы орошения в сценарии','Сценарийдегі суару тәсілдері','Integrated scenario: irrigation methods'),
 'Integrated scenario electricity boundary':('Границы учёта электроэнергии','Электр есебінің шекарасы','Integrated electricity boundary'),
 'Integrated emission components':('Учтённые компоненты выбросов','Есептелген шығарынды көздері','Included emission components'),
 'Integrated scenario economic cost confirmation':('Подтверждение полноты затрат','Шығын толықтығын растау','Costs completeness confirmation'),
 'Integrated water source and volume':('Единый сценарий: вода и основание расчёта','Біріктірілген сценарий: су негізі','Integrated scenario: water reference'),
 'Integrated pumping parameters':('Сценарий: параметры насосов','Сценарий: сорғы параметрлері','Integrated scenario: pumping inputs'),
 'Integrated unit prices':('Сценарий: цены и коэффициенты','Сценарий: баға мен коэффициент','Integrated scenario: unit prices'),
 'Integrated scenario evidence':('Основания сценария','Сценарий дереккөздері','Integrated scenario: evidence'),
 'Integrated reference links':('Ссылки на методики','Әдістемелерге сілтемелер','Integrated scenario: source links'),
 'Scientific sources':('Научные источники','Ғылыми дереккөздер','Scientific sources'),
 'Editable reference assumptions; verify applicable billing point and reporting year':('Редактируемые справочные значения; проверьте поставщика и год тарифа','Өзгертілетін анықтамалық мәндер; жеткізуші мен тариф жылын тексеріңіз','Editable reference assumptions; verify supplier and tariff year'),
 'Editable engineering assumptions, not instrument measurements':('Инженерные допущения, не измерения прибора','Инженерлік болжам, аспап өлшемі емес','Engineering assumptions, not meter readings'),
 'User confirmation':('Подтверждение пользователя','Пайдаланушы растауы','User confirmation'),
 'FAO normative reconstruction or user scenario; field delivery for crop':('Нормативный расчёт FAO или сценарий пользователя; подача на поле','FAO нормасы немесе пайдаланушы сценарийі; танапқа берілген су','FAO reference or user scenario; field delivery'),
 'IPCC partial boundary; none = unavailable, not 0':('Частичный учёт IPCC; отсутствие данных не равно нулю','IPCC ішінара есебі; дерек жоқтығы нөл емес','Partial IPCC boundary; missing is not zero'),
 'FAO / IPCC / user assumptions':('FAO / IPCC / допущения пользователя','FAO / IPCC / пайдаланушы жорамалдары','FAO / IPCC / user assumptions'),
 'Documented November 2025 non-household tariff, VAT-removed for comparable costing; NOT independently confirmed for October 2026':('Тариф для коммерческих потребителей, ноябрь 2025; без НДС. Применимость к октябрю 2026 не подтверждена.','Коммерциялық тариф, 2025 қараша, ҚҚС-сыз. 2026 қазан үшін расталмаған.','Business tariff, Nov 2025 excl. VAT; not confirmed for Oct 2026.'),
 'Mechanized canal supply for agricultural producers; service fee, not electricity kWh':('Механизированная подача воды; стоимость перекачки входит в тариф услуги. Не добавляйте её повторно.','Механикаландырылған су беру; сорғы құны қызмет тарифіне кіреді, қайта қоспаңыз.','Mechanized water delivery: supplier pumping included. Do not add it twice.'),
 'Gravity canal supply for agricultural producers, only with that provider and supply method':('Самотечная подача; тариф только для данного поставщика и способа подачи.','Өздігінен ағу тарифі тек осы жеткізуші мен тәсіл үшін.','Gravity delivery; only for this supplier and method.'),
 'Reference need, NOT measured water; check soil/method and crop mapping':('Расчётная потребность, не измеренный расход; проверьте почвы, метод орошения и категорию культуры.','Есептік қажеттілік, нақты өлшем емес; топырақ пен суару тәсілін тексеріңіз.','Reference need, not observed; verify soils, irrigation and crop mapping.'),
 'Ember Yearly Electricity Data 2025, Kazakhstan generation intensity; 0.813 kg CO2/kWh':('Данные международной платформы Ember за 2025 год: средняя углеродоёмкость генерации Казахстана 0,813 кг CO₂/кВт·ч.','Ember халықаралық деректері, 2025: Қазақстан генерациясы 0,813 кг CO₂/кВт·сағ.','Ember 2025 Kazakhstan generation intensity: 0.813 kg CO₂/kWh.'),
}

# Fragments that may appear alongside numeric values, URLs and scientific symbols.
FRAGMENTS={
 'ru': [
    ('physical_model:', 'Расчётная физическая модель:'),('zone_fallback:', 'Подстановка по водохозяйственной зоне:'),('regional_fallback:', 'Среднее по региону:'),
    ('user_observed:', 'Показания пользователя:'), ('No verified pumping system and head', 'Параметры насосной системы не подтверждены'),
    ('water=','вода='), ('grid electricity=','сетевая электроэнергия='), ('EF=','коэффициент выбросов='),
    ('before=','до='), ('after=','после='), ('pumped_fraction=','доля насосной воды='),
    ('kgCO2e/kWh','кг CO₂e/кВт·ч'), ('kWh/m3','кВт·ч/м³'), ('KZT/kWh','тг/кВт·ч'), ('KZT/m3','тг/м³'),
    ('No observed', 'Нет подтверждённых'), ('geographic fallback to official zone','географическая подстановка по официальной зоне'),
    ('inferred net from surface reference','чистая потребность оценена по норме поверхностного полива'),
    ('baseline eta=','исходный КПД='),('proposed eta=','предлагаемый КПД='),
    ('FAO reference efficiencies','справочные коэффициенты КПД FAO'),
    ('Observed electricity; pumping savings not inferred','Учтена измеренная электроэнергия; экономия насоса не рассчитана'),
    ('Ember Yearly Electricity Data 2025, Kazakhstan generation intensity', 'Ember, ежегодная статистика генерации Казахстана за 2025 год'),
    ('(secondary display)','(справочный источник)'),
    ('generation-average CO2 factor, not full CO2e or a contractual grid factor', 'средний коэффициент генерации CO₂; не полный CO₂e и не договорной коэффициент'),
    ('Full crop season','Полный сезон культуры'), ('User-entered net irrigation','Введённая чистая потребность в поливе'),
    ('User-entered/mode observation','Данные пользователя/режима оценки'),
    ('Species reference; not actual observed consumption','Справочник по виду животных; не фактический расход'),
    ('Scenario result; not an observed effect','Сценарный результат; не измеренный эффект'),
    ('Reference price','Справочная цена'),
    ('unavailable:', 'нет данных:'),
    ('Crop not specified', 'культура не выбрана'),
    ('No animals counted', 'поголовье хозяйства не введено'),
    ('KZT/m³', 'тг/м³'), ('KZT/m3', 'тг/м³'),
    ('None = unavailable, not 0', 'нет данных не означает ноль'),
    ('district benchmark', 'районная справочная статистика'),
    ('regional reference', 'региональная справочная оценка'),
    ('not farm observations', 'не измерения хозяйства'),
    ('No observations', 'Нет наблюдений'),

 ],
 'kk': [
    ('physical_model:', 'Физикалық есептік модель:'),('zone_fallback:', 'Су шаруашылық аймағы бойынша мән:'),('user_observed:', 'Пайдаланушы өлшемі:'),
    ('water=','су='), ('grid electricity=','желілік электр='), ('EF=','шығарынды коэффициенті='),
    ('before=','дейін='), ('after=','кейін='), ('pumped_fraction=','сорғы суының үлесі='),
    ('kgCO2e/kWh','кг CO₂e/кВт·сағ'), ('kWh/m3','кВт·сағ/м³'), ('KZT/kWh','тг/кВт·сағ'), ('KZT/m3','тг/м³'),
    ('geographic fallback to official zone','ресми аймақ бойынша мән'),
    ('inferred net from surface reference','беткі суару нормасы бойынша таза қажеттілік'),
    ('baseline eta=','бастапқы ПӘК='),('proposed eta=','ұсынылатын ПӘК='),
    ('FAO reference efficiencies','FAO анықтамалық ПӘК көрсеткіштері'),
    ('Ember Yearly Electricity Data 2025, Kazakhstan generation intensity', 'Ember, Қазақстан генерациясының 2025 жылғы статистикасы'),
    ('Full crop season','Дақылдың толық маусымы'),
    ('unavailable:', 'дерек жоқ:'),
    ('Crop not specified', 'дақыл таңдалмаған'),
    ('No animals counted', 'шаруашылықтың мал саны енгізілмеген'),
    ('KZT/m³', 'тг/м³'),

 ],
 'en': [],
}


def localize_string(obj, lang):
    if not isinstance(obj, str):
        return obj
    if lang not in ('ru','kk','en'):
        lang='en'
    text=obj
    if text.strip().lower() in ('nan', 'none', 'null', 'n/a'):
        return {'ru':'нет данных', 'kk':'дерек жоқ', 'en':'not available'}[lang]
    pair=EXACT.get(text)
    if pair:
        return pair[{'ru':0,'kk':1,'en':2}[lang]]
    # Never translate URL internals; split on URL tokens and leave them intact.
    chunks=re.split(r'(https?://[^\s;]+)',text)
    for i in range(0,len(chunks),2):
        part=chunks[i]
        for before,after in FRAGMENTS[lang]:
            part=part.replace(before,after)
        chunks[i]=part
    return ''.join(chunks)


def _report_value(value, lang):
    """Format missing numeric evidence without inventing zero; keep legitimate 0."""
    if isinstance(value, float):
        if not math.isfinite(value):
            return {'ru':'нет данных', 'kk':'дерек жоқ', 'en':'not available'}[lang]
        return round(value, 3) if abs(value) < 1e12 else value
    return localize_string(value, lang) if isinstance(value, str) else value


def prepare_report(payload):
    """Return isolated localized snapshot; do not modify Streamlit session state."""
    out=deepcopy(payload)
    lang=out.get('lang','en')
    defaults={
        'ru':{'generated_label':'Дата расчёта','summary_title':'Ключевые результаты','recommendations_title':'Рекомендации','analysis_title':'Анализ результата','inputs_title':'Входные данные и источники','indicator_label':'Показатель','value_label':'Значение','note_label':'Примечание','parameter_label':'Параметр','source_label':'Источник / роль','table_title':'Подробные результаты','evidence_label':'Основание','effect_label':'Ожидаемый эффект','chart_section_title':'Аналитический график'},
        'kk':{'generated_label':'Есептеу күні','summary_title':'Негізгі нәтижелер','recommendations_title':'Ұсыныстар','analysis_title':'Нәтижелерді талдау','inputs_title':'Бастапқы деректер мен дереккөздер','indicator_label':'Көрсеткіш','value_label':'Мәні','note_label':'Ескертпе','parameter_label':'Параметр','source_label':'Дереккөз / рөл','table_title':'Толық нәтижелер','evidence_label':'Негіздеме','effect_label':'Күтілетін әсер','chart_section_title':'Талдау диаграммасы'},
        'en':{'generated_label':'Calculation date','summary_title':'Key results','recommendations_title':'Recommendations','analysis_title':'Results analysis','inputs_title':'Inputs and sources','indicator_label':'Indicator','value_label':'Value','note_label':'Note','parameter_label':'Parameter','source_label':'Source / role','table_title':'Detailed results','evidence_label':'Evidence','effect_label':'Expected effect','chart_section_title':'Analytical chart'},
    }[lang if lang in ('ru','kk','en') else 'en']
    for key in ('generated_label','summary_title','recommendations_title','analysis_title','inputs_title',
                'indicator_label','value_label','note_label','parameter_label','source_label','table_title'):
        out.setdefault(key,defaults[key])
    for rec in out.get('recommendations',[]):
        if isinstance(rec,dict):
            rec.setdefault('evidence_label',defaults['evidence_label'])
            rec.setdefault('effect_label',defaults['effect_label'])
    if out.get('chart') and isinstance(out['chart'],dict):
        out['chart'].setdefault('section_title',defaults['chart_section_title'])
    if isinstance(out.get('table'),list):
        out['table']=[{localize_string(k,lang):_report_value(v,lang)
                       for k,v in row.items()} if isinstance(row,dict) else row
                      for row in out['table']]
    for field in ('summary','recommendations','analysis','inputs','chart'):
        if field not in out:
            continue
        def walk(node):
            if isinstance(node,(str,float)): return _report_value(node,lang)
            if isinstance(node,list): return [walk(v) for v in node]
            if isinstance(node,tuple): return tuple(walk(v) for v in node)
            if isinstance(node,dict): return {k:walk(v) for k,v in node.items()}
            return node
        out[field]=walk(out[field])
    return out

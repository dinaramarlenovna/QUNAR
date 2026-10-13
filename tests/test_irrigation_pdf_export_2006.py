import sys
from pathlib import Path
import importlib.util
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.irrigation_economics import irrigation_comparison
from core.irrigation_report import irrigation_export


def test_pdf_contains_feasibility_and_local_labels(tmp_path):
    module = Path('/mnt/data/_qreview_full/QUNAR_v0_8_1_FIXED/core/reporting.py')
    spec = importlib.util.spec_from_file_location('qunar_reporting_test', module)
    r = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r)
    comp=irrigation_comparison(baseline_yield_centners_ha=50,
      price_kzt_t=105000,other_variable_cost_kzt_ha=326000,
      baseline_water_m3_ha=6450,proposed_water_m3_ha=5160,
      baseline_energy_kwh_ha=420,proposed_energy_kwh_ha=420,
      water_tariff_kzt_m3=.845,electricity_tariff_kzt_kwh=45.9872,
      yield_change_pct=0,extra_technology_cost_kzt_ha=15000,
      evidence='Контрольный сценарий 0%')
    rows,rec=irrigation_export(comp,area_ha=20,
      input_yield_centners_ha=50,ml_yield_centners_ha=63.94,
      selling_price_kzt_t=105000,other_variable_cost_kzt_ha=326000,
      extra_technology_cost_kzt_ha=15000,yield_change_pct=0,
      evidence='Контрольный сценарий 0%',lang='ru',
      available_water_m3=107000,reuse_pct=0)
    b=r.build_pdf_report({"mode_label":"Оценить мое хозяйство",
      "brand_translation":"Тест", "generated_label":"Дата расчета",
      "generated_at":"2026-10-13", "summary_title":"Ключевые результаты",
      "summary":rows, "recommendations_title":"Ключевые рекомендации",
      "recommendations":[rec]})
    out=tmp_path/'test.pdf'
    out.write_bytes(b)
    import fitz
    doc=fitz.open(stream=b,filetype='pdf')
    whole='\n'.join(p.get_text() for p in doc)
    for token in ('129,000', '103,200', '107,000', 'превышен', 'соблюдён', 'Основание', 'Ожидаемый эффект'):
        assert token in whole, token
    assert 'Evidence:' not in whole and 'Expected effect:' not in whole

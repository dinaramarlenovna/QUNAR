from __future__ import annotations

from io import BytesIO
from datetime import datetime
import html
import re
import pandas as pd
from .report_localization import prepare_report
from .report_variants import compared_variants, condensed_variants
import math


def _clean(v):
    """Export missing numbers as missing, not NaN text or fictional zero."""
    if v is None:
        return "—"
    if isinstance(v, float) and not math.isfinite(v):
        return "—"
    if isinstance(v, str) and v.strip().lower() in {"nan", "none", "null", "n/a"}:
        return "—"
    return str(v)


def _safe_sheet_name(name: str, fallback: str = "Report") -> str:
    name = re.sub(r"[\\/*?:\[\]]", " ", str(name or fallback)).strip()
    return (name[:31] or fallback)


def _num(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value or "").replace("\u00a0", " ").replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def _unique_inputs(payloads):
    seen = set()
    out = []
    for payload in payloads:
        for row in payload.get("inputs", []) or []:
            if len(row) < 3:
                continue
            key = (str(row[0]), str(row[1]), str(row[2]))
            if key not in seen:
                seen.add(key)
                out.append(list(row[:3]))
    return out


def _xlsx_formats(wb):
    return {
        "brand": wb.add_format({"bold": True, "font_size": 24, "font_color": "#1F5135"}),
        "subtitle": wb.add_format({"bold": True, "font_size": 11, "font_color": "#52665A"}),
        "section": wb.add_format({"bold": True, "font_size": 16, "font_color": "#20372A", "bottom": 2, "bottom_color": "#8BAD96"}),
        "header": wb.add_format({"bold": True, "bg_color": "#EAF3EC", "font_color": "#234F36", "border": 1, "border_color": "#D7E3DA", "text_wrap": True, "valign": "vcenter"}),
        "cell": wb.add_format({"valign": "top", "text_wrap": True, "border": 1, "border_color": "#E5EAE6"}),
        "key": wb.add_format({"bold": True, "bg_color": "#F1F7F2", "font_color": "#234F36", "text_wrap": True, "border": 1, "border_color": "#D7E3DA", "valign": "top"}),
        "recommend": wb.add_format({"bold": True, "bg_color": "#EEF7F0", "font_color": "#183A25", "text_wrap": True, "border": 1, "border_color": "#BFD5C5", "valign": "top"}),
        "small": wb.add_format({"font_size": 9, "font_color": "#66736B", "text_wrap": True}),
        "money": wb.add_format({"num_format": '#,##0', "border": 1, "border_color": "#E5EAE6"}),
        "pct": wb.add_format({"num_format": '0.0', "border": 1, "border_color": "#E5EAE6"}),
    }


def _write_payload_sheet(writer, sheet_name: str, payload: dict, include_inputs: bool = True):
    wb = writer.book
    fm = _xlsx_formats(wb)
    ws = wb.add_worksheet(_safe_sheet_name(sheet_name))
    writer.sheets[ws.name] = ws
    ws.hide_gridlines(2)
    ws.freeze_panes(5, 0)
    ws.set_column("A:A", 30)
    ws.set_column("B:B", 28)
    ws.set_column("C:C", 58)
    ws.set_row(0, 34)

    ws.write("A1", "QŪNAR", fm["brand"])
    ws.merge_range("B1:C1", payload.get("mode_label", ""), fm["section"])
    ws.merge_range("A2:C2", payload.get("brand_translation", ""), fm["subtitle"])
    ws.write("A3", payload.get("generated_label", "Generated"), fm["small"])
    ws.write("B3", payload.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M")), fm["small"])

    row = 5
    summary = payload.get("summary", []) or []
    if summary:
        ws.merge_range(row, 0, row, 2, payload.get("summary_title", "Key results"), fm["section"]); row += 2
        ws.write_row(row, 0, [payload.get("indicator_label", "Indicator"), payload.get("value_label", "Value"), payload.get("note_label", "Note")], fm["header"]); row += 1
        for item in summary:
            ws.write(row, 0, _clean(item.get("label")), fm["key"])
            value = item.get("value", "")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                ws.write_number(row, 1, float(value), fm["money"] if item.get("kind") == "money" else fm["cell"])
            else:
                ws.write(row, 1, _clean(value), fm["cell"])
            ws.write(row, 2, _clean(item.get("note")), fm["cell"])
            row += 1

    recommendations = payload.get("recommendations", []) or []
    if recommendations:
        row += 1
        ws.merge_range(row, 0, row, 2, payload.get("recommendations_title", "Recommendations"), fm["section"]); row += 2
        for i, rec in enumerate(recommendations, 1):
            if isinstance(rec, dict):
                title = rec.get("title") or f"{i}."
                text = rec.get("text") or rec.get("recommendation") or ""
                evidence = rec.get("evidence") or rec.get("why") or ""
                effect = rec.get("effect") or ""
                ws.write(row, 0, f"{i}. {title}", fm["recommend"])
                ws.write(row, 1, _clean(text), fm["recommend"])
                ws.write(row, 2, "\n".join(x for x in [_clean(evidence), _clean(effect)] if x), fm["cell"])
            else:
                ws.write(row, 0, f"{i}.", fm["recommend"])
                ws.merge_range(row, 1, row, 2, _clean(rec), fm["recommend"])
            row += 1

    analysis = payload.get("analysis", []) or []
    if analysis:
        row += 1
        ws.merge_range(row, 0, row, 2, payload.get("analysis_title", "Analysis"), fm["section"]); row += 2
        for text in analysis:
            ws.merge_range(row, 0, row, 2, _clean(text), fm["cell"])
            row += 1

    table = payload.get("table")
    if table:
        row += 1
        ws.merge_range(row, 0, row, 2, payload.get("table_title", "Detailed results"), fm["section"]); row += 2
        table_df = pd.DataFrame(table)
        if not table_df.empty:
            start = row
            table_df.to_excel(writer, sheet_name=ws.name, startrow=start, startcol=0, index=False)
            for c, col in enumerate(table_df.columns):
                ws.write(start, c, col, fm["header"])
                ws.set_column(c, c, min(max(14, len(str(col)) + 2), 25))
            row += len(table_df) + 2

    # Analytical chart in Excel: only where a meaningful numeric comparison exists.
    chart = payload.get("chart") or {}
    if chart.get("categories") and chart.get("values"):
        row += 1
        chart_start = row
        ws.write_row(chart_start, 0, [chart.get("category_label", "Category"), chart.get("value_label", "Value")], fm["header"])
        for i, (cat, val) in enumerate(zip(chart["categories"], chart["values"]), 1):
            ws.write(chart_start + i, 0, _clean(cat), fm["cell"])
            ws.write_number(chart_start + i, 1, float(val), fm["pct"])
        ch = wb.add_chart({"type": "bar"})
        ch.add_series({
            "name": chart.get("title", "QŪNAR"),
            "categories": [ws.name, chart_start + 1, 0, chart_start + len(chart["categories"]), 0],
            "values": [ws.name, chart_start + 1, 1, chart_start + len(chart["values"]), 1],
            "data_labels": {"value": True},
        })
        ch.set_title({"name": chart.get("title", "QŪNAR analytical view")})
        ch.set_legend({"none": True})
        ch.set_style(10)
        ch.set_size({"width": 720, "height": 380})
        ws.insert_chart(chart_start, 3, ch)
        row += max(len(chart["categories"]) + 2, 20)

    if include_inputs and payload.get("inputs"):
        row += 1
        ws.merge_range(row, 0, row, 2, payload.get("inputs_title", "Inputs and sources"), fm["section"]); row += 2
        ws.write_row(row, 0, [payload.get("parameter_label", "Parameter"), payload.get("value_label", "Value"), payload.get("source_label", "Source")], fm["header"]); row += 1
        for p, v, s in payload["inputs"]:
            ws.write(row, 0, _clean(p), fm["cell"])
            ws.write(row, 1, _clean(v), fm["cell"])
            ws.write(row, 2, _clean(s), fm["cell"])
            row += 1
    return ws


def build_excel_report(payload: dict) -> bytes:
    payload = prepare_report(payload)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        _write_payload_sheet(writer, "QUNAR_Report", payload, include_inputs=True)
    output.seek(0)
    return output.getvalue()


def build_combined_excel_report(payloads: list[dict]) -> bytes:
    comparisons = compared_variants(payloads)
    payloads = [prepare_report(p) for p in condensed_variants(payloads) if p]
    for _p in payloads:
        _n = _p.get('variant_number', 1)
        if _n > 1:
            _tag = {'ru':'вариант','kk':'нұсқа','en':'variant'}.get(_p.get('lang','ru'),'variant')
            _p['mode_label'] = f"{_p.get('mode_label','')} ({_tag} {_n}; отличия)" if _p.get('lang') == 'ru' else f"{_p.get('mode_label','')} ({_tag} {_n})"
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        wb = writer.book
        fm = _xlsx_formats(wb)
        lang = (payloads[0].get('lang') if payloads else 'en') or 'en'
        title = {'kk':'Біріктірілген аналитикалық есеп','ru':'Сводный аналитический отчет',
                 'en':'Integrated analytical report'}.get(lang, 'Integrated analytical report')
        summary_ws = wb.add_worksheet('Summary')
        writer.sheets['Summary'] = summary_ws
        summary_ws.hide_gridlines(2)
        summary_ws.set_column('A:A', 34)
        summary_ws.set_column('B:B', 72)
        summary_ws.set_column('C:C', 28)
        summary_ws.write('A1','QŪNAR', fm['brand'])
        summary_ws.merge_range('B1:C1',title,fm['section'])
        summary_ws.write('A3', {'ru':'Включённые расчёты', 'kk':'Таңдалған есептер', 'en':'Selected calculations'}.get(lang), fm['section'])
        for i,payload in enumerate(payloads,1):
            idx=i+4
            summary_ws.write(idx,0,f"{i}. {payload.get('mode_label','')}",fm['key'])
            recs=payload.get('recommendations') or []
            first = recs[0] if recs else ''
            if isinstance(first,dict): first=first.get('text') or first.get('title') or ''
            summary_ws.write(idx,1,_clean(first),fm['recommend'])
            summary_ws.write(idx,2,_clean(payload.get('generated_at','')),fm['cell'])
        for i,payload in enumerate(payloads,1):
            _write_payload_sheet(writer,f"{i}_{payload.get('mode_label','Mode')}", payload,include_inputs=True)
        if comparisons:
            sh=wb.add_worksheet('Comparisons')
            writer.sheets['Comparisons']=sh
            sh.hide_gridlines(2)
            sh.set_column('A:A',60);sh.set_column('B:C',36)
            sh.write_row(0,0,[{'ru':'Показатель','kk':'Көрсеткіш','en':'Indicator'}[lang],
                               {'ru':'Вариант 1','kk':'1-нұсқа','en':'Variant 1'}[lang],
                               {'ru':'Сравниваемый вариант','kk':'Салыстырылатын нұсқа','en':'Compared variant'}[lang]],fm['header'])
            row=1
            for comp in comparisons:
                sh.merge_range(row,0,row,2,f"{comp['mode_label']}: #1 → #{comp['candidate']}",fm['section']);row+=1
                for label, rows in [({'ru':'Изменённые исходные условия','kk':'Өзгерген кіріс деректер','en':'Changed inputs'}[lang],comp['inputs']),
                                    ({'ru':'Изменённые результаты','kk':'Өзгерген нәтижелер','en':'Changed results'}[lang],comp['results'])]:
                    sh.merge_range(row,0,row,2,label,fm['key']);row+=1
                    for field,a,b in rows[:35]:
                        sh.write(row,0,_clean(field),fm['cell']);sh.write(row,1,_clean(a),fm['cell']);sh.write(row,2,_clean(b),fm['cell']);row+=1
                row+=2
    output.seek(0)
    return output.getvalue()


def _register_pdf_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    try:
        from matplotlib import font_manager
        regular = font_manager.findfont("DejaVu Sans")
        bold = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans", weight="bold"))
        pdfmetrics.registerFont(TTFont("QunarSans", regular))
        pdfmetrics.registerFont(TTFont("QunarSansBold", bold))
        return "QunarSans", "QunarSansBold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def _pdf_styles(regular, bold):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("QunarTitle", parent=styles["Title"], fontName=bold, fontSize=25, leading=29, textColor=colors.HexColor("#1F5135"), alignment=TA_CENTER, spaceAfter=8),
        "subtitle": ParagraphStyle("QunarSubtitle", parent=styles["BodyText"], fontName=bold, fontSize=10.5, leading=15, textColor=colors.HexColor("#53675A"), alignment=TA_CENTER, spaceAfter=15),
        "h2": ParagraphStyle("QunarH2", parent=styles["Heading2"], fontName=bold, fontSize=15, leading=19, textColor=colors.HexColor("#24342A"), spaceBefore=13, spaceAfter=8),
        "h3": ParagraphStyle("QunarH3", parent=styles["Heading3"], fontName=bold, fontSize=11.5, leading=15, textColor=colors.HexColor("#234F36"), spaceBefore=7, spaceAfter=4),
        "body": ParagraphStyle("QunarBody", parent=styles["BodyText"], fontName=regular, fontSize=10.3, leading=15, textColor=colors.HexColor("#202722"), spaceAfter=6),
        "key": ParagraphStyle("QunarKey", parent=styles["BodyText"], fontName=bold, fontSize=10.6, leading=15, textColor=colors.HexColor("#183A25"), backColor=colors.HexColor("#EEF7F0"), borderColor=colors.HexColor("#BFD5C5"), borderWidth=.7, borderPadding=8, spaceAfter=8),
        "small": ParagraphStyle("QunarSmall", parent=styles["BodyText"], fontName=regular, fontSize=8.4, leading=11.5, textColor=colors.HexColor("#67736B")),
    }


def _chart_image(chart: dict):
    if not chart or not chart.get("categories") or not chart.get("values"):
        return None
    import matplotlib.pyplot as plt
    cats = [str(x) for x in chart["categories"]]
    vals = [float(x) for x in chart["values"]]
    # Keep charts analytical and readable, not decorative.
    fig_h = max(2.6, min(5.2, 0.42 * len(cats) + 1.3))
    fig, ax = plt.subplots(figsize=(7.4, fig_h))
    y = list(range(len(cats)))
    ax.barh(y, vals)
    ax.set_yticks(y, labels=cats)
    ax.invert_yaxis()
    ax.set_title(chart.get("title", "QŪNAR analytical view"))
    ax.set_xlabel(chart.get("axis_label", chart.get("value_label", "")))
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=.18)
    for yi, v in zip(y, vals):
        ax.text(v, yi, f" {v:.1f}", va="center", fontsize=9)
    fig.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def _append_payload_pdf(story, payload: dict, styles, include_inputs: bool = True, include_brand: bool = True):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    body, h2, h3, key, small = styles["body"], styles["h2"], styles["h3"], styles["key"], styles["small"]
    if include_brand:
        story.append(Paragraph("QŪNAR", styles["title"]))
        story.append(Paragraph(html.escape(payload.get("brand_translation", "")), styles["subtitle"]))
    story.append(Paragraph(html.escape(payload.get("mode_label", "")), h2))
    story.append(Paragraph(html.escape(f"{payload.get('generated_label','Generated')}: {payload.get('generated_at','')}"), small))

    summary = payload.get("summary", []) or []
    if summary:
        story.append(Paragraph(html.escape(payload.get("summary_title", "Key results")), h2))
        # 2-column KPI table, compact and readable.
        data = []
        for x in summary:
            label = Paragraph(f"<b>{html.escape(str(x.get('label','')))}</b>", body)
            value = Paragraph(f"<b>{html.escape(str(x.get('value','')))}</b>", body)
            data.append([label, value])
        tbl = Table(data, colWidths=[76*mm, 84*mm], hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("VALIGN",(0,0),(-1,-1),"TOP"), ("GRID",(0,0),(-1,-1),.35,colors.HexColor("#DCE5DE")),
            ("BACKGROUND",(0,0),(0,-1),colors.HexColor("#F6F9F7")), ("LEFTPADDING",(0,0),(-1,-1),7),
            ("RIGHTPADDING",(0,0),(-1,-1),7), ("TOPPADDING",(0,0),(-1,-1),7), ("BOTTOMPADDING",(0,0),(-1,-1),7)
        ]))
        story += [tbl, Spacer(1, 4*mm)]

    chart_buf = _chart_image(payload.get("chart") or {})
    if chart_buf:
        story.append(Paragraph(html.escape((payload.get("chart") or {}).get("section_title", "Analytical visualization")), h2))
        from reportlab.lib.utils import ImageReader
        iw, ih = ImageReader(chart_buf).getSize()
        chart_buf.seek(0)
        w = 166*mm
        h = w * (ih / iw)
        story.append(Image(chart_buf, width=w, height=h))
        story.append(Spacer(1, 2*mm))

    recommendations = payload.get("recommendations", []) or []
    if recommendations:
        story.append(Paragraph(html.escape(payload.get("recommendations_title", "Recommendations")), h2))
        for i, rec in enumerate(recommendations, 1):
            if isinstance(rec, dict):
                title = rec.get("title") or f"Recommendation {i}"
                text = rec.get("text") or rec.get("recommendation") or ""
                evidence = rec.get("evidence") or rec.get("why") or ""
                effect = rec.get("effect") or ""
                story.append(Paragraph(f"{i}. {html.escape(str(title))}", h3))
                story.append(Paragraph(html.escape(str(text)), key))
                if evidence:
                    story.append(Paragraph(f"<b>{html.escape(str(rec.get('evidence_label','Evidence')))}:</b> {html.escape(str(evidence))}", body))
                if effect:
                    story.append(Paragraph(f"<b>{html.escape(str(rec.get('effect_label','Expected effect')))}:</b> {html.escape(str(effect))}", body))
            else:
                story.append(Paragraph(f"{i}. {html.escape(str(rec))}", key))

    analysis = payload.get("analysis", []) or []
    if analysis:
        story.append(Paragraph(html.escape(payload.get("analysis_title", "Analysis")), h2))
        for text in analysis:
            story.append(Paragraph(html.escape(str(text)), body))

    table = payload.get("table")
    if table:
        story.append(Paragraph(html.escape(payload.get("table_title", "Detailed results")), h2))
        df = pd.DataFrame(table)
        if not df.empty:
            df = df.iloc[:, :8]
            data = [[Paragraph(f"<b>{html.escape(str(c))}</b>", small) for c in df.columns]]
            for _, row in df.head(15).iterrows():
                data.append([Paragraph(html.escape(_clean(v)), small) for v in row.tolist()])
            widths = [170*mm/len(df.columns)] * len(df.columns)
            tbl = Table(data, colWidths=widths, repeatRows=1)
            tbl.setStyle(TableStyle([
                ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF3EC")), ("GRID",(0,0),(-1,-1),.3,colors.HexColor("#D7E0D9")),
                ("VALIGN",(0,0),(-1,-1),"TOP"), ("LEFTPADDING",(0,0),(-1,-1),3), ("RIGHTPADDING",(0,0),(-1,-1),3),
                ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4)
            ]))
            story.append(tbl)

    if include_inputs and payload.get("inputs"):
        story += [PageBreak(), Paragraph(html.escape(payload.get("inputs_title", "Inputs and sources")), h2)]
        data = [[Paragraph(f"<b>{html.escape(payload.get('parameter_label','Parameter'))}</b>", small), Paragraph(f"<b>{html.escape(payload.get('value_label','Value'))}</b>", small), Paragraph(f"<b>{html.escape(payload.get('source_label','Source'))}</b>", small)]]
        for p,v,s in payload["inputs"]:
            data.append([Paragraph(html.escape(_clean(p)), small), Paragraph(html.escape(_clean(v)), small), Paragraph(html.escape(_clean(s)), small)])
        tbl = Table(data, colWidths=[52*mm, 42*mm, 76*mm], repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAF3EC")), ("GRID",(0,0),(-1,-1),.3,colors.HexColor("#D7E0D9")),
            ("VALIGN",(0,0),(-1,-1),"TOP"), ("LEFTPADDING",(0,0),(-1,-1),4), ("RIGHTPADDING",(0,0),(-1,-1),4),
            ("TOPPADDING",(0,0),(-1,-1),4), ("BOTTOMPADDING",(0,0),(-1,-1),4)
        ]))
        story.append(tbl)


def build_pdf_report(payload: dict) -> bytes:
    payload = prepare_report(payload)
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate
    regular, bold = _register_pdf_fonts()
    styles = _pdf_styles(regular, bold)
    out = BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=14*mm, bottomMargin=14*mm, title="QŪNAR report", author="QŪNAR")
    story = []
    _append_payload_pdf(story, payload, styles, include_inputs=True, include_brand=True)
    doc.build(story)
    out.seek(0)
    return out.getvalue()


def build_combined_pdf_report(payloads: list[dict]) -> bytes:
    comparisons = compared_variants(payloads)
    payloads = [prepare_report(p) for p in condensed_variants(payloads) if p]
    for _p in payloads:
        _n = _p.get('variant_number', 1)
        if _n > 1:
            _tag = {'ru':'вариант','kk':'нұсқа','en':'variant'}.get(_p.get('lang','ru'),'variant')
            _p['mode_label'] = f"{_p.get('mode_label','')} ({_tag} {_n}; отличия)" if _p.get('lang') == 'ru' else f"{_p.get('mode_label','')} ({_tag} {_n})"
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, LongTable, TableStyle
    regular,bold=_register_pdf_fonts()
    styles=_pdf_styles(regular,bold)
    out=BytesIO()
    doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=16*mm,leftMargin=16*mm,
        topMargin=14*mm,bottomMargin=14*mm,title='QŪNAR integrated report',author='QŪNAR')
    lang=(payloads[0].get('lang') if payloads else 'en') or 'en'
    title={'ru':'Сводный аналитический отчёт','kk':'Біріктірілген аналитикалық есеп',
           'en':'Integrated analytical report'}[lang]
    story=[Paragraph('QŪNAR',styles['title']),Paragraph(title,styles['subtitle']),
           Paragraph({'ru':'Структура отчёта','kk':'Есеп құрылымы','en':'Report structure'}[lang],styles['h2'])]
    for i,p in enumerate(payloads,1):
        story.append(Paragraph(f"{i}. {html.escape(_clean(p.get('mode_label','')))}",styles['key']))
    if comparisons:
        story.append(Paragraph({'ru':'Сравнение вариантов одного режима','kk':'Бір режим нұсқаларын салыстыру',
                                'en':'Comparison of scenarios within the same mode'}[lang],styles['h2']))
        story.append(Paragraph({'ru':'Отображаются только изменившиеся исходные условия и показатели. Неизменные данные приведены в базовом варианте.',
                                'kk':'Тек өзгерген кіріс деректер мен нәтижелер көрсетіледі. Өзгермегендері бастапқы нұсқада берілген.',
                                'en':'Only changed inputs and results are listed. Unchanged material remains in the baseline variant.'}[lang],styles['small']))
        for comp in comparisons:
            story.append(Paragraph(f"{html.escape(_clean(comp['mode_label']))}: #1 → #{comp['candidate']}",styles['h3']))
            for section, rows in [({'ru':'Изменённые исходные условия','kk':'Өзгерген кіріс деректер','en':'Changed inputs'}[lang],comp['inputs']),
                                  ({'ru':'Изменённые результаты','kk':'Өзгерген нәтижелер','en':'Changed results'}[lang],comp['results'])]:
                if not rows: continue
                story.append(Paragraph(section,styles['key']))
                cells=[[Paragraph(html.escape(_clean(x)),styles['small']) for x in line] for line in
                       [[{'ru':'Показатель','kk':'Көрсеткіш','en':'Indicator'}[lang],
                         {'ru':'Вариант 1','kk':'1-нұсқа','en':'Variant 1'}[lang],
                         f"#{comp['candidate']}"]] + rows[:35]]
                tbl=LongTable(cells,colWidths=[74*mm,48*mm,48*mm],repeatRows=1,hAlign='LEFT')
                tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EAF3EC')),
                    ('GRID',(0,0),(-1,-1),.3,colors.HexColor('#D7E0D9')),
                    ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),
                    ('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),4),
                    ('BOTTOMPADDING',(0,0),(-1,-1),4)]))
                story.append(tbl)
    for payload in payloads:
        story.append(PageBreak())
        _append_payload_pdf(story,payload,styles,include_inputs=True,include_brand=False)
    doc.build(story)
    out.seek(0)
    return out.getvalue()


def _word_add_payload(doc, payload: dict, include_inputs: bool = True, include_brand: bool = True):
    from docx.shared import Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    def shade(cell, fill):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:fill'), fill)
        tcPr.append(shd)

    def add_heading(text, level=1):
        p = doc.add_paragraph()
        p.style = doc.styles[f'Heading {min(level, 3)}']
        r = p.add_run(_clean(text))
        r.font.color.rgb = None
        return p

    if include_brand:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run('QŪNAR')
        r.bold = True; r.font.size = Pt(24)
        if payload.get('brand_translation'):
            p2 = doc.add_paragraph(_clean(payload.get('brand_translation')))
            p2.alignment = WD_ALIGN_PARAGRAPH.CENTER

    add_heading(payload.get('mode_label', ''), 1)
    meta = doc.add_paragraph()
    meta.add_run(f"{payload.get('generated_label','Generated')}: ").bold = True
    meta.add_run(_clean(payload.get('generated_at','')))
    if payload.get('assessment_year'):
        meta.add_run(f" | { {'kk':'Есептік жыл','ru':'Расчётный год','en':'Calculation year'}.get(payload.get('lang','en'),'Calculation year')}: {payload.get('assessment_year')}")
    if payload.get('assessment_type'):
        meta.add_run(f" | {_clean(payload.get('assessment_type'))}")

    summary = payload.get('summary', []) or []
    if summary:
        add_heading(payload.get('summary_title','Key results'), 2)
        table = doc.add_table(rows=1, cols=3)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = 'Table Grid'
        hdr = table.rows[0].cells
        for i, txt in enumerate([payload.get('indicator_label','Indicator'), payload.get('value_label','Value'), payload.get('note_label','Note')]):
            hdr[i].text = _clean(txt); shade(hdr[i], 'EAF3EC')
        for item in summary:
            cells = table.add_row().cells
            cells[0].text = _clean(item.get('label'))
            cells[1].text = _clean(item.get('value'))
            cells[2].text = _clean(item.get('note'))
            for c in cells: c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP

    recommendations = payload.get('recommendations', []) or []
    if recommendations:
        add_heading(payload.get('recommendations_title','Recommendations'), 2)
        for i, rec in enumerate(recommendations, 1):
            if isinstance(rec, dict):
                p = doc.add_paragraph(style='List Number')
                p.add_run(_clean(rec.get('title') or f'Recommendation {i}')).bold = True
                if rec.get('text') or rec.get('recommendation'):
                    doc.add_paragraph(_clean(rec.get('text') or rec.get('recommendation')))
                if rec.get('evidence'):
                    p = doc.add_paragraph(); p.add_run(f"{_clean(rec.get('evidence_label','Evidence'))}: ").bold = True; p.add_run(_clean(rec.get('evidence')))
                if rec.get('effect'):
                    p = doc.add_paragraph(); p.add_run(f"{_clean(rec.get('effect_label','Expected effect'))}: ").bold = True; p.add_run(_clean(rec.get('effect')))
            else:
                doc.add_paragraph(_clean(rec), style='List Number')

    analysis = payload.get('analysis', []) or []
    if analysis:
        add_heading(payload.get('analysis_title','Analysis'), 2)
        for text in analysis:
            doc.add_paragraph(_clean(text))

    table_data = payload.get('table')
    if table_data:
        add_heading(payload.get('table_title','Detailed result'), 2)
        df = pd.DataFrame(table_data)
        if not df.empty:
            df = df.iloc[:, :8].head(25)
            table = doc.add_table(rows=1, cols=len(df.columns))
            table.style = 'Table Grid'
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for j, col in enumerate(df.columns):
                table.rows[0].cells[j].text = _clean(col); shade(table.rows[0].cells[j], 'EAF3EC')
            for _, rr in df.iterrows():
                cells = table.add_row().cells
                for j, val in enumerate(rr.tolist()): cells[j].text = _clean(val)

    if include_inputs and payload.get('inputs'):
        doc.add_page_break()
        add_heading(payload.get('inputs_title','Inputs and sources'), 2)
        table = doc.add_table(rows=1, cols=3)
        table.style = 'Table Grid'; table.alignment = WD_TABLE_ALIGNMENT.CENTER
        labels = [payload.get('parameter_label','Parameter'), payload.get('value_label','Value'), payload.get('source_label','Source')]
        for j, txt in enumerate(labels): table.rows[0].cells[j].text = _clean(txt); shade(table.rows[0].cells[j], 'EAF3EC')
        for p_, v_, s_ in payload['inputs']:
            cells = table.add_row().cells
            cells[0].text = _clean(p_); cells[1].text = _clean(v_); cells[2].text = _clean(s_)


def _word_document_base(title='QŪNAR report'):
    from docx import Document
    from docx.shared import Pt, Cm
    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(1.8); section.bottom_margin = Cm(1.8); section.left_margin = Cm(2.0); section.right_margin = Cm(2.0)
    styles = doc.styles
    styles['Normal'].font.name = 'Arial'; styles['Normal'].font.size = Pt(10.5)
    for name, size in [('Heading 1', 16), ('Heading 2', 13), ('Heading 3', 11)]:
        styles[name].font.name = 'Arial'; styles[name].font.size = Pt(size); styles[name].font.bold = True
    doc.core_properties.title = title
    doc.core_properties.author = 'QŪNAR'
    return doc


def build_word_report(payload: dict) -> bytes:
    payload = prepare_report(payload)
    doc = _word_document_base('QŪNAR report')
    _word_add_payload(doc, payload, include_inputs=True, include_brand=True)
    out = BytesIO(); doc.save(out); out.seek(0); return out.getvalue()


def build_combined_word_report(payloads: list[dict]) -> bytes:
    comparisons=compared_variants(payloads)
    payloads=[prepare_report(p) for p in condensed_variants(payloads) if p]
    for _p in payloads:
        _n=_p.get('variant_number',1)
        if _n > 1:
            _tag={'ru':'вариант','kk':'нұсқа','en':'variant'}.get(_p.get('lang','ru'),'variant')
            _p['mode_label']=f"{_p.get('mode_label','')} ({_tag} {_n})"
    lang=(payloads[0].get('lang') if payloads else 'en') or 'en'
    title={'ru':'Сводный аналитический отчёт','kk':'Біріктірілген аналитикалық есеп',
           'en':'Integrated analytical report'}[lang]
    doc=_word_document_base('QŪNAR integrated report')
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER;r=p.add_run('QŪNAR');r.bold=True
    p=doc.add_paragraph(title);p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    doc.add_heading({'ru':'Структура отчёта','kk':'Есеп құрылымы','en':'Report structure'}[lang],level=1)
    for i,payload in enumerate(payloads,1):doc.add_paragraph(f"{i}. {_clean(payload.get('mode_label',''))}")
    if comparisons:
        doc.add_heading({'ru':'Сравнение вариантов одного режима','kk':'Бір режим нұсқаларын салыстыру',
                         'en':'Comparing scenarios in the same mode'}[lang],level=1)
        doc.add_paragraph({'ru':'Приведены различающиеся исходные значения и результаты; неизменные данные доступны в первом варианте.',
                           'kk':'Тек өзгерген кіріс деректер мен нәтижелер; өзгермегендері бірінші нұсқада.',
                           'en':'Only changed inputs and results are shown; unchanged details remain in variant 1.'}[lang])
        for comp in comparisons:
            doc.add_heading(f"{comp['mode_label']}: #1 → #{comp['candidate']}",level=2)
            for section,rows in [({'ru':'Изменённые исходные условия','kk':'Өзгерген кіріс деректер','en':'Changed inputs'}[lang],comp['inputs']),
                                 ({'ru':'Изменённые результаты','kk':'Өзгерген нәтижелер','en':'Changed results'}[lang],comp['results'])]:
                if not rows:continue
                doc.add_heading(section,level=3)
                tbl=doc.add_table(rows=1,cols=3);tbl.style='Table Grid'
                for j,x in enumerate([{'ru':'Показатель','kk':'Көрсеткіш','en':'Indicator'}[lang],
                                      {'ru':'Вариант 1','kk':'1-нұсқа','en':'Variant 1'}[lang],
                                      f"#{comp['candidate']}"]):tbl.rows[0].cells[j].text=x
                for field,a,b in rows[:35]:
                    cells=tbl.add_row().cells
                    for j,x in enumerate([field,a,b]):cells[j].text=_clean(x)
    for payload in payloads:
        doc.add_page_break()
        _word_add_payload(doc,payload,include_inputs=True,include_brand=False)
    out=BytesIO();doc.save(out);out.seek(0)
    return out.getvalue()

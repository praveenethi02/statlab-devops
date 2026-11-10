"""Paginated PDF analysis reports generated from saved, owned snapshots."""
import io
import json
import math
from xml.sax.saxutils import escape

from reportlab import rl_config
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def display(value):
    if value is None:
        return 'Undefined'
    if isinstance(value, float):
        return f'{value:.7g}'
    if isinstance(value, (dict, list)):
        if len(value) > 40:
            short = list(value.items())[:20] if isinstance(value, dict) else value[:20]
            return display(short) + f' ... ({len(value)} entries; full detail in CSV export)'
        if isinstance(value, list):
            return '[' + ', '.join(display(v) for v in value) + ']'
        return '; '.join(f'{k}: {display(v)}' for k, v in value.items())
    return str(value)


def compact(value, limit=600):
    text = display(value)
    return text if len(text) <= limit else text[:limit] + ' ... (full detail in CSV export)'


def timestamp(value):
    from datetime import datetime
    return datetime.fromisoformat(value).strftime('%Y-%m-%d %H:%M UTC')


def methodology_text(value):
    return value.replace('x̄', 'xbar').translate(str.maketrans({'Σ':'sum ', '√':'sqrt ', 'μ':'mu', 'σ':'sigma', '−':'-', '×':'*', '²':'^2', '³':'^3', '…':'...', '–':'-'}))


def histogram(values):
    drawing = Drawing(470, 195)
    count = min(15, max(1, math.ceil(math.sqrt(len(values)))))
    low, high = min(values), max(values)
    width = (high-low)/count if high != low else 1
    bins = [0]*count
    for value in values:
        position = min(count-1, int((value-low)/width)) if high != low else 0
        bins[position] += 1
    drawing.add(String(40, 176, 'Distribution of included observations', fontName='Helvetica-Bold', fontSize=11))
    drawing.add(Line(40, 30, 450, 30, strokeColor=colors.HexColor('#b5bdc8')))
    drawing.add(Line(40, 30, 40, 160, strokeColor=colors.HexColor('#b5bdc8')))
    for i, frequency in enumerate(bins):
        h = frequency/max(bins)*115
        drawing.add(Rect(41+i*400/count, 30, 400/count-2, h, fillColor=colors.HexColor('#496fde'), strokeColor=None))
    drawing.add(String(40, 14, f'{low:.5g}', fontSize=9))
    drawing.add(String(415, 14, f'{high:.5g}', fontSize=9))
    drawing.add(String(225, 0, 'Value', fontSize=9))
    drawing.add(String(2, 160, str(max(bins)), fontSize=9))
    drawing.add(String(2, 135, 'Count', fontSize=8))
    return drawing


def analysis_pdf(analysis, username):
    output = io.BytesIO()
    # ReportLab ships a Unicode-capable sans serif font; no host-specific font dependency.
    if 'WorkspaceSans' not in pdfmetrics.getRegisteredFontNames():
        from pathlib import Path
        import reportlab
        font = Path(reportlab.__file__).parent / 'fonts' / 'Vera.ttf'
        pdfmetrics.registerFont(TTFont('WorkspaceSans', str(font)))
    styles = getSampleStyleSheet()
    for name in ('Normal', 'BodyText'):
        styles[name].fontName = 'WorkspaceSans'
        styles[name].fontSize = 8.5
        styles[name].leading = 12
    styles['Title'].textColor = colors.HexColor('#203250')
    styles['Heading2'].textColor = colors.HexColor('#496fde')
    styles['Heading2'].spaceBefore = 15
    styles['Heading2'].keepWithNext = True
    def p(value):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), styles['BodyText'])
    story = [Paragraph('STATISTICAL WORKSPACE', styles['Heading2']),
             Paragraph(escape(analysis['name']), styles['Title']),
             p(f"Dataset: {analysis['snapshot']['name']} | Author: {username}"),
             p(f"Analysis date: {timestamp(analysis['created_at'])} | Dataset revision: {analysis['dataset_revision']}"),
             p('Historical result: the source dataset has since changed.' if analysis['historical'] else 'Current result: matches the current dataset revision.'),
             Spacer(1, 12)]
    calculation = analysis['calculation']
    summary = calculation['summary']
    story += [p(f"Observations: {summary['count']} | Column: {summary['column']} | Missing rows excluded: {summary['excluded_rows']}"),
              p('CLASS-INTERVAL ESTIMATES: results use class midpoints.' if summary['estimated'] else 'Exact numerical observations (subject to floating-point precision).'),
              p(analysis['snapshot']['description']), Spacer(1, 12), histogram(calculation['chart_data']['values'])]
    sections = {}
    for key, value in calculation['results'].items():
        if key == 'frequency':
            continue
        metric = calculation['catalog'][key]
        formula = methodology_text(metric['formula'])
        description = methodology_text(calculation['issues'].get(key, metric['description']))
        sections.setdefault(metric['section'], []).append([p(metric['name']), p(compact(value)), p(formula + '\n' + description)])
    def table(rows, widths):
        result = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
        result.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eef2fb')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LINEBELOW', (0, 0), (-1, -1), 0.4, colors.HexColor('#dce3ee')),
            ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        return result
    for section, rows in sections.items():
        story += [Paragraph(section, styles['Heading2']), table([[p('Parameter'), p('Value'), p('Method and interpretation')], *rows], [125, 135, 210])]
    if 'frequency' in calculation['results']:
        frequency = calculation['results']['frequency']
        story.append(Paragraph('Frequency distribution', styles['Heading2']))
        rows = [[p('Value'), p('Frequency'), p('Relative frequency'), p('Cumulative frequency')]]
        rows.extend([p(display(f['value'])), p(f['frequency']), p(display(f['relative'])), p(f['cumulative'])] for f in frequency[:40])
        story.append(table(rows, [85, 95, 135, 155]))
        if len(frequency) > 40:
            story.append(p(f'First 40 of {len(frequency)} distinct values shown; full distribution is in the CSV export.'))
    story.append(Paragraph('Manually entered parameters', styles['Heading2']))
    parameter_note = p('These editable values are separate from calculated results and reflect their latest saved state at export time.')
    parameter_note.keepWithNext = True
    story.append(parameter_note)
    if analysis['parameters']:
        rows = [[p('Parameter'), p('Value / unit'), p('Notes')]]
        for item in analysis['parameters']:
            notes = '\n'.join(v for v in (item['formula'], item['description']) if v)
            notes = compact(notes, 700)
            notes += ('\n' if notes else '') + f"Updated: {timestamp(item['updated_at'])}"
            rows.append([p(item['name']), p(f"{compact(item['value'], 400)} {item['unit']}"), p(notes)])
        story.append(table(rows, [125, 135, 210]))
    else:
        story.append(p('No custom parameters saved.'))
    story += [Paragraph('Methodology and reproducibility', styles['Heading2']),
              p(f"Algorithm version: {calculation['algorithm_version']}"),
              p('Settings: ' + json.dumps(calculation['settings'], ensure_ascii=False))]
    story.extend(p(f'{key}: {value}') for key, value in calculation['conventions'].items())
    def footer(canvas, document):
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#718095'))
        canvas.drawString(0.7*inch, 0.4*inch, 'Statistical Workspace | Saved analysis report')
        canvas.drawRightString(7.5*inch, 0.4*inch, f'Page {document.page}')
    document = SimpleDocTemplate(output, pagesize=rl_config.defaultPageSize, rightMargin=0.7*inch,
                                 leftMargin=0.7*inch, topMargin=0.6*inch, bottomMargin=0.65*inch,
                                 title=analysis['name'], author=username)
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    output.seek(0)
    return output

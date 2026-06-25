from pathlib import Path
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

REPORTS = Path('reports'); REPORTS.mkdir(exist_ok=True)

def make_report(student_label, result):
    path = REPORTS / f"report_{student_label.replace(' ','_')}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    y = h - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "SEU Academic Registration Assistant Report")
    y -= 30
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Student: {student_label}")
    y -= 20
    c.drawString(40, y, f"Generated: {datetime.utcnow().isoformat()} UTC")
    y -= 30
    analysis = result.get('analysis', {})
    c.setFont("Helvetica-Bold", 12); c.drawString(40, y, "Summary"); y -= 20
    c.setFont("Helvetica", 10)
    for line in [f"Progress: {analysis.get('progress_percent',0)}%", f"Passed: {len(analysis.get('passed',[]))}", f"Failed: {len(analysis.get('failed',[]))}", f"Eligible: {len(analysis.get('eligible',[]))}", f"Blocked: {len(analysis.get('blocked',[]))}"]:
        c.drawString(50, y, line); y -= 16
    y -= 10
    c.setFont("Helvetica-Bold", 12); c.drawString(40, y, "Recommended Balanced Plan"); y -= 20
    c.setFont("Helvetica", 9)
    for item in analysis.get('recommendations', {}).get('balanced', []):
        txt = f"{item.get('code')} - {item.get('name','')[:65]} | {item.get('reason','')}"
        c.drawString(50, y, txt[:110]); y -= 14
        if y < 60:
            c.showPage(); y = h-50; c.setFont("Helvetica", 9)
    y -= 10
    c.setFont("Helvetica-Bold", 12); c.drawString(40, y, "Blocked Courses"); y -= 20
    c.setFont("Helvetica", 9)
    for item in analysis.get('blocked', [])[:60]:
        c.drawString(50, y, f"{item.get('code')} - {item.get('reason','')}"[:110]); y -= 14
        if y < 60:
            c.showPage(); y = h-50; c.setFont("Helvetica", 9)
    c.save()
    return str(path)

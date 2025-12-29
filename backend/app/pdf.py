from io import BytesIO
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas


def text_to_pdf_bytes(title: str, body: str) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    c.setTitle(title)
    y = height - 72
    c.setFont("Helvetica-Bold", 14)
    c.drawString(72, y, title)
    y -= 28
    c.setFont("Helvetica", 10)
    for line in body.splitlines():
        if y < 72:
            c.showPage()
            y = height - 72
            c.setFont("Helvetica", 10)
        c.drawString(72, y, line[:120])
        y -= 14
    c.save()
    return buf.getvalue()

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


def resume_to_pdf_bytes(*, title: str, summary: str, experiences: list[dict]) -> bytes:
    """Very simple resume PDF renderer using reportlab.

    This does NOT attempt to perfectly match the DOCX template; it is a clean, readable export.
    """
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    c.setTitle(title or "Resume")

    x = 72
    y = height - 72

    def line(text: str, font="Helvetica", size=10, dy=14):
        nonlocal y
        if y < 72:
            c.showPage()
            y = height - 72
        c.setFont(font, size)
        c.drawString(x, y, (text or "")[:160])
        y -= dy

    # Header
    line(title or "Resume", font="Helvetica-Bold", size=16, dy=22)

    # Summary
    if (summary or "").strip():
        line("Summary", font="Helvetica-Bold", size=12, dy=18)
        for s in (summary or "").splitlines():
            for chunk in _wrap_text(s, max_len=110):
                line(chunk, font="Helvetica", size=10, dy=14)
        y -= 6

    # Experience
    line("Experience", font="Helvetica-Bold", size=12, dy=18)
    for exp in experiences or []:
        header = exp.get("header") or exp.get("title") or ""
        company = exp.get("company") or ""
        if company and header and company.lower() not in header.lower():
            header = f"{header} — {company}"
        if header:
            line(header, font="Helvetica-Bold", size=10, dy=14)
        for b in exp.get("bullets") or []:
            for chunk in _wrap_text(f"• {b}", max_len=110):
                line(chunk, font="Helvetica", size=10, dy=14)
        y -= 6

    c.save()
    return buf.getvalue()


def _wrap_text(s: str, max_len: int = 100) -> list[str]:
    s = (s or "").strip()
    if len(s) <= max_len:
        return [s] if s else []
    out = []
    cur = ""
    for w in s.split(" "):
        if not cur:
            cur = w
            continue
        if len(cur) + 1 + len(w) <= max_len:
            cur = cur + " " + w
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out

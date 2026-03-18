from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    CondPageBreak,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfgen import canvas
import re


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


def build_resume_pdf_bytes(resume: dict) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ResumeTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=20,
        spaceAfter=4,
        alignment=1,
    )
    sub_title_style = ParagraphStyle(
        "ResumeSubTitle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        spaceAfter=8,
        alignment=1,
        textColor=colors.HexColor("#333333"),
    )
    contact_style = ParagraphStyle(
        "ResumeContact",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=11,
        spaceAfter=8,
        alignment=1,
        textColor=colors.HexColor("#555555"),
    )
    header_style = ParagraphStyle(
        "ResumeHeader",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=14,
        spaceAfter=4,
        textTransform="uppercase",
    )
    body_style = ParagraphStyle(
        "ResumeBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=12.5,
        spaceAfter=2,
    )
    right_style = ParagraphStyle(
        "ResumeRight",
        parent=body_style,
        alignment=2,
        textColor=colors.HexColor("#444444"),
    )
    company_style = ParagraphStyle(
        "ResumeCompany",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=10.2,
        leading=12,
        spaceAfter=0,
    )
    bullet_style = ParagraphStyle(
        "ResumeBullet",
        parent=body_style,
        leftIndent=0.14 * inch,
        firstLineIndent=-0.14 * inch,
        leading=12.5,
        spaceAfter=2,
    )

    candidate = resume.get("candidate") or {}
    candidate_name = _pdf_escape((candidate.get("name") or "").strip())
    contact_items = candidate.get("contact_items") or []

    story = []
    if candidate_name:
        story.append(Paragraph(candidate_name.upper(), title_style))
    if contact_items:
        story.append(Paragraph(_contact_items_to_pdf(contact_items), contact_style))
    story.append(Paragraph(_pdf_escape(resume.get("job_title") or "Software Engineer"), sub_title_style))

    story.extend(_section_header("Summary", header_style))
    story.append(Paragraph(_pdf_escape_with_bold(resume.get("summary") or ""), body_style))

    story.append(Spacer(1, 0.08 * inch))
    story.extend(_section_header("Skills", header_style))
    for item in resume.get("skills") or []:
        category = _pdf_escape(str(item.get("category") or "").strip())
        values = ", ".join(
            _pdf_escape(str(v).strip()) for v in (item.get("items") or []) if str(v).strip()
        )
        line = f"- <b>{category}</b>: {values}" if category else f"- {values}"
        story.append(Paragraph(line, body_style))

    story.append(Spacer(1, 0.08 * inch))
    story.extend(_section_header("Experience", header_style))
    for exp in resume.get("experiences") or []:
        story.append(CondPageBreak(1.6 * inch))
        company = _pdf_escape(str(exp.get("company") or "").strip())
        location = _pdf_escape(str(exp.get("location") or "").strip())
        title = _pdf_escape(str(exp.get("job_title") or "").strip())
        left_parts = [title, company]
        if location:
            left_parts.append(location)
        company_line = " | ".join([part for part in left_parts if part])
        duration = _pdf_escape(str(exp.get("duration") or "").strip())
        header_table = Table(
            [[Paragraph(company_line, company_style), Paragraph(duration, right_style)]],
            colWidths=[doc.width - 1.35 * inch, 1.35 * inch],
        )
        header_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        bullets = [
            Paragraph(f"- {_pdf_escape_with_bold(str(sentence))}", bullet_style)
            for sentence in (exp.get("sentences") or [])
        ]
        if bullets:
            story.append(KeepTogether([header_table, bullets[0]]))
            story.extend(bullets[1:])
        else:
            story.append(KeepTogether([header_table]))
        story.append(Spacer(1, 0.07 * inch))

    story.append(Spacer(1, 0.08 * inch))
    story.extend(_section_header("Education", header_style))
    for item in resume.get("education") or []:
        story.append(Paragraph(_pdf_escape(str(item.get("school") or "").strip()), body_style))
        story.append(Paragraph(_pdf_escape(str(item.get("degree") or "").strip()), body_style))
        story.append(Paragraph(_pdf_escape(str(item.get("duration") or "").strip()), body_style))

    doc.build(story)
    return buf.getvalue()


def _section_header(title: str, style: ParagraphStyle) -> list:
    return [Paragraph(_pdf_escape(title), style), Spacer(1, 0.05 * inch)]


def _pdf_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _pdf_escape_with_bold(text: str) -> str:
    escaped = _pdf_escape(_normalize_bold_markup(text))
    escaped = escaped.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    return escaped


def _normalize_bold_markup(text: str) -> str:
    text = (text or "").replace("<br>", " ").replace("<br/>", " ").strip()
    text = re.sub(r"<\s*/\s*b\s*>", "</b>", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*b\s*>", "<b>", text, flags=re.IGNORECASE)
    open_count = len(re.findall(r"<b>", text, flags=re.IGNORECASE))
    close_count = len(re.findall(r"</b>", text, flags=re.IGNORECASE))
    if close_count > open_count:
        diff = close_count - open_count
        for _ in range(diff):
            text = re.sub(r"</b>", "", text, count=1, flags=re.IGNORECASE)
    elif open_count > close_count:
        text += "</b>" * (open_count - close_count)
    return text


def _contact_items_to_pdf(items: list) -> str:
    out = []
    for item in items:
        if isinstance(item, dict):
            text = _pdf_escape(str(item.get("text") or item.get("label") or "").strip())
            url = str(item.get("url") or "").strip()
            if text and url:
                out.append(f'<a href="{_pdf_escape(url)}" color="blue">{text}</a>')
            elif text:
                out.append(text)
        else:
            raw = _pdf_escape(str(item).strip())
            if raw:
                out.append(raw)
    return " | ".join(out)

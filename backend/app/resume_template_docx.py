from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from typing import Any, Dict, List

from docx import Document
from docx.text.paragraph import Paragraph


def render_resume_template_docx_bytes(
    template_bytes: bytes,
    resume: Dict[str, Any],
) -> bytes:
    doc = Document(BytesIO(template_bytes))

    candidate = resume.get("candidate") or {}
    contact_items = candidate.get("contact_items") or []
    experiences = _normalize_experiences(resume.get("experiences") or [])
    skills = _normalize_skills(resume.get("skills") or [])
    education = _normalize_education(resume.get("education") or [])

    replacements = {
        "[NAME]": str(candidate.get("name") or "").strip(),
        "[phone_number]": _contact_text(contact_items, 0),
        "[email]": _contact_text(contact_items, 1),
        "[adress]": _contact_text(contact_items, 2),
        "[Total Role]": str(resume.get("job_title") or "").strip(),
        "[SUMMARY]": str(resume.get("summary") or "").strip(),
        "[SKILLS]": "SKILLS",
        "[EXPERIENCE]": "EXPERIENCE",
        "[EDUCATION]": "EDUCATION",
    }

    for paragraph in doc.paragraphs:
        _replace_paragraph_tokens(paragraph, replacements)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _replace_paragraph_tokens(paragraph, replacements)

    _render_skill_block(doc, skills)
    _render_experience_block(doc, experiences)
    _render_education_block(doc, education)

    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def _replace_paragraph_tokens(paragraph: Paragraph, replacements: Dict[str, str]) -> None:
    text = paragraph.text or ""
    new_text = text
    for src, dst in replacements.items():
        new_text = new_text.replace(src, dst)
    if new_text != text:
        _set_paragraph_text(paragraph, new_text)


def _set_paragraph_text(paragraph: Paragraph, text: str) -> None:
    runs = list(paragraph.runs)
    if runs:
        runs[0].text = text
        for run in runs[1:]:
            try:
                run._r.getparent().remove(run._r)
            except Exception:
                pass
    else:
        paragraph.add_run(text)


def _insert_paragraph_after(paragraph: Paragraph) -> Paragraph:
    new_p = deepcopy(paragraph._p)
    paragraph._p.addnext(new_p)
    return Paragraph(new_p, paragraph._parent)


def _insert_table_after_paragraph(paragraph: Paragraph, template_table):
    new_tbl = deepcopy(template_table._tbl)
    paragraph._p.addnext(new_tbl)
    return template_table.__class__(new_tbl, template_table._parent)


def _normalize_experiences(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in items:
        bullets = item.get("sentences") or item.get("bullets") or []
        out.append(
            {
                "role": str(item.get("job_title") or item.get("title") or "").strip(),
                "company": str(item.get("company") or "").strip(),
                "location": str(item.get("location") or "").strip(),
                "duration": str(item.get("duration") or "").strip(),
                "bullets": [str(x).strip() for x in bullets if str(x).strip()],
            }
        )
    return out


def _normalize_skills(items: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for item in items:
        category = str(item.get("category") or "").strip()
        values = [str(v).strip() for v in (item.get("items") or []) if str(v).strip()]
        if category and values:
            out.append(f"- {category}: {', '.join(values)}")
        elif values:
            out.append(f"- {', '.join(values)}")
        elif category:
            out.append(f"- {category}")
    return out


def _normalize_education(items: List[Dict[str, Any]]) -> List[List[str]]:
    out: List[List[str]] = []
    for item in items:
        out.append(
            [
                str(item.get("school") or "").strip(),
                str(item.get("degree") or "").strip(),
                str(item.get("duration") or "").strip(),
            ]
        )
    return out


def _contact_text(items: List[Any], index: int) -> str:
    if index >= len(items):
        return ""
    item = items[index]
    if isinstance(item, dict):
        return str(item.get("text") or item.get("label") or "").strip()
    return str(item).strip()


def _render_skill_block(doc: Document, skills: List[str]) -> None:
    marker = _find_paragraph_containing(doc, "[Category1]")
    if marker is None:
        return
    lines = skills or [""]
    _set_paragraph_text(marker, lines[0])
    cursor = marker
    for line in lines[1:]:
        cursor = _insert_paragraph_after(cursor)
        _set_paragraph_text(cursor, line)


def _render_experience_block(doc: Document, experiences: List[Dict[str, Any]]) -> None:
    table = _find_table_with_text(doc, "[Role1]")
    bullet_marker = _find_paragraph_containing(doc, "[Description]")
    if table is None or bullet_marker is None:
        return

    exps = experiences or [{"role": "", "company": "", "location": "", "duration": "", "bullets": [""]}]
    first = exps[0]
    _fill_experience_table(table, first)
    bullets = first.get("bullets") or [""]
    _set_paragraph_text(bullet_marker, f"- {bullets[0]}".rstrip())
    bullet_cursor = bullet_marker
    for bullet in bullets[1:]:
        bullet_cursor = _insert_paragraph_after(bullet_cursor)
        _set_paragraph_text(bullet_cursor, f"- {bullet}".rstrip())

    insert_after = bullet_cursor
    for exp in exps[1:]:
        new_table = _insert_table_after_paragraph(insert_after, table)
        _fill_experience_table(new_table, exp)
        first_bullet = _insert_paragraph_after(insert_after)
        exp_bullets = exp.get("bullets") or [""]
        _set_paragraph_text(first_bullet, f"- {exp_bullets[0]}".rstrip())
        insert_after = first_bullet
        for bullet in exp_bullets[1:]:
            insert_after = _insert_paragraph_after(insert_after)
            _set_paragraph_text(insert_after, f"- {bullet}".rstrip())


def _fill_experience_table(table, exp: Dict[str, Any]) -> None:
    if not table.rows:
        return
    row = table.rows[0]
    left = _experience_header_left(exp)
    right = str(exp.get("duration") or "").strip()
    if len(row.cells) > 0 and row.cells[0].paragraphs:
        _set_paragraph_text(row.cells[0].paragraphs[0], left)
    if len(row.cells) > 1 and row.cells[1].paragraphs:
        _set_paragraph_text(row.cells[1].paragraphs[0], right)


def _experience_header_left(exp: Dict[str, Any]) -> str:
    parts = [
        str(exp.get("role") or "").strip(),
        str(exp.get("company") or "").strip(),
        str(exp.get("location") or "").strip(),
    ]
    return " | ".join([part for part in parts if part])


def _render_education_block(doc: Document, education: List[List[str]]) -> None:
    first = _find_paragraph_containing(doc, "[University_name]")
    if first is None:
        return
    second = _find_paragraph_containing(doc, "[Degree]")
    third = _find_paragraph_containing(doc, "[Education_date_ramge]")
    if second is None or third is None:
        return
    items = education or [["", "", ""]]
    _set_paragraph_text(first, items[0][0])
    _set_paragraph_text(second, items[0][1])
    _set_paragraph_text(third, items[0][2])
    cursor = third
    for school, degree, duration in items[1:]:
        p1 = _insert_paragraph_after(cursor)
        _set_paragraph_text(p1, school)
        p2 = _insert_paragraph_after(p1)
        _set_paragraph_text(p2, degree)
        p3 = _insert_paragraph_after(p2)
        _set_paragraph_text(p3, duration)
        cursor = p3


def _find_paragraph_containing(doc: Document, token: str) -> Paragraph | None:
    for paragraph in doc.paragraphs:
        if token in (paragraph.text or ""):
            return paragraph
    return None


def _find_table_with_text(doc: Document, token: str):
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if token in (paragraph.text or ""):
                        return table
    return None

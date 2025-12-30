from __future__ import annotations

import re
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple, Set

from docx import Document
from docx.oxml import OxmlElement
from docx.text.paragraph import Paragraph


# ---------------------------
# Helpers
# ---------------------------


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _is_bullet_prefix_text(txt: str) -> bool:
    t = (txt or "").lstrip()
    return t.startswith(("•", "-", "*", "\u2022", "‣", "▪", "–", "—"))


def _has_numbering(p: Paragraph) -> bool:
    # numPr indicates paragraph is in a numbered/bulleted list
    try:
        pPr = p._p.pPr
        return bool(pPr is not None and pPr.numPr is not None)
    except Exception:
        return False

def _style_looks_like_list(p: Paragraph) -> bool:
    try:
        name = (p.style.name or "").lower()
        # common Word styles: "List Paragraph", "List Bullet", etc.
        return ("list" in name) or ("bullet" in name)
    except Exception:
        return False


def _is_bullet_paragraph(p: Paragraph) -> bool:
    txt = (p.text or "").strip()
    if not txt:
        return False

    # 1) Bullet glyph in visible text
    if _is_bullet_prefix_text(txt):
        return True

    # 2) Style suggests list/bullet
    if _style_looks_like_list(p):
        return True

    # 3) Numbering properties set
    if _has_numbering(p):
        return True

    return False


def _strip_visible_bullet_prefix(t: str) -> str:
    # Remove common bullet characters/prefixes if they are literally present in text
    s = (t or "").strip()
    s = re.sub(r"^(?:[•\u2022‣▪\-\*\–\—]\s+)", "", s)
    return s.strip()


# ---------------------------
# DOCX -> JSON extraction
# ---------------------------


def extract_resume_json_from_docx(docx_bytes: bytes) -> Dict[str, Any]:
    """
    Best-effort DOCX -> structured resume JSON.

    Extracts bullet blocks and groups them into "experiences".
    Stores bullet paragraph indices so we can replace them later.
    """
    doc = Document(BytesIO(docx_bytes))  # IMPORTANT: bytes -> BytesIO
    paragraphs = list(doc.paragraphs)

    experiences: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    prev_nonbullet_text = ""

    for idx, p in enumerate(paragraphs):
        t = _norm(p.text)
        if not t:
            # blank line ends an experience block if we were in one
            if current and current.get("bullets"):
                experiences.append(current)
                current = None
            continue

        if _is_bullet_paragraph(p):
            if current is None:
                header = prev_nonbullet_text
                current = {
                    "header": header,
                    "company": None,
                    "title": None,
                    "start": None,
                    "end": None,
                    "location": None,
                    "bullets": [],
                    "bullet_para_idxs": [],
                }

            current["bullets"].append(_strip_visible_bullet_prefix(t))
            current["bullet_para_idxs"].append(idx)
        else:
            # close any running block when we hit non-bullet after bullets
            if current and current.get("bullets"):
                experiences.append(current)
                current = None
            prev_nonbullet_text = t

    if current and current.get("bullets"):
        experiences.append(current)

    return {
        "schema": "resume_json_v1",
        "experiences": experiences,
    }


# ---------------------------
# Paragraph ops
# ---------------------------


def _set_paragraph_text_preserve_format(p: Paragraph, text: str) -> None:
    """
    Replace paragraph text while preserving paragraph-level formatting (list/numPr/style).

    Strategy:
    - If runs exist: set first run text; remove remaining runs.
    - Else: add a run.
    This preserves bullet/list formatting because that lives on the paragraph (numPr), not the run.
    """
    text = text or ""
    runs = list(p.runs)

    if runs:
        runs[0].text = text
        for r in runs[1:]:
            try:
                r._r.getparent().remove(r._r)
            except Exception:
                pass
    else:
        p.add_run(text)


# ---------------------------
# Bullet replacement
# ---------------------------


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _tokenize(s: str) -> List[str]:
    s = _norm(s)
    s = re.sub(r"[^a-z0-9+#/.-]+", " ", s)
    return [t for t in s.split(" ") if t]


def _has_numpr(p: Paragraph) -> bool:
    try:
        pPr = p._p.pPr
        return bool(pPr is not None and pPr.numPr is not None)
    except Exception:
        return False


def _style_looks_like_list(p: Paragraph) -> bool:
    try:
        name = (p.style.name or "").lower()
        return ("list" in name) or ("bullet" in name)
    except Exception:
        return False


def _is_bullet_paragraph(p: Paragraph) -> bool:
    txt = (p.text or "").strip()
    if not txt:
        return False
    # Many resumes use real Word list numbering without "•" in text:
    return (
        _has_numpr(p)
        or _style_looks_like_list(p)
        or txt.startswith(("•", "-", "*", "\u2022", "●"))
    )


def _set_paragraph_text_preserve_format(p: Paragraph, text: str) -> None:
    """
    Replace text while preserving paragraph list formatting (numPr).
    Keep first run formatting, remove extra runs.
    """
    text = text or ""
    runs = list(p.runs)
    if runs:
        runs[0].text = text
        for r in runs[1:]:
            try:
                r._r.getparent().remove(r._r)
            except Exception:
                pass
    else:
        p.add_run(text)


def _find_target_idxs_by_matching_text(
    paragraphs: List[Paragraph],
    original_bullets: List[str],
) -> List[int]:
    """
    If bullet_para_idxs isn't available, locate the bullet paragraphs by matching
    the original bullet texts against paragraph texts in the doc.

    Strategy:
    - Normalize text and match exact normalized string first.
    - If not found, fallback to token-overlap match (>= 70% overlap) among bullet-like paragraphs.
    """
    norm_to_idxs: Dict[str, List[int]] = {}
    for i, p in enumerate(paragraphs):
        t = _norm(p.text)
        if not t:
            continue
        norm_to_idxs.setdefault(t, []).append(i)

    target: List[int] = []
    used: Set[int] = set()

    # Pass 1: exact normalized matches (best)
    for b in original_bullets:
        nb = _norm(b)
        found = None
        for idx in norm_to_idxs.get(nb, []):
            if idx not in used:
                found = idx
                break
        if found is not None:
            target.append(found)
            used.add(found)

    # Pass 2: fuzzy token overlap for any misses
    if len(target) < len(original_bullets):
        # Candidates are only bullet-like paragraphs to reduce false hits
        candidates = [
            (i, set(_tokenize(paragraphs[i].text)))
            for i in range(len(paragraphs))
            if _is_bullet_paragraph(paragraphs[i])
        ]
        for b in original_bullets[len(target) :]:
            btoks = set(_tokenize(b))
            best = None
            best_score = 0.0
            for i, ptoks in candidates:
                if i in used:
                    continue
                if not btoks or not ptoks:
                    continue
                overlap = len(btoks & ptoks) / max(1, len(btoks))
                if overlap > best_score:
                    best_score = overlap
                    best = i
            # require strong overlap to avoid wrong replacements
            if best is not None and best_score >= 0.70:
                target.append(best)
                used.add(best)

    return sorted(target)


def replace_bullets_in_docx(
    docx_bytes: bytes,
    bullet_blocks: List[Dict[str, Any]],
    new_bullets_by_block_index: Dict[int, List[str]],
) -> bytes:
    """
    Replace bullet paragraphs in-place while keeping the original template.

    Works even if bullet_para_idxs is missing by matching original bullet text.
    Enforces SAME bullet count as original block.
    """
    doc = Document(BytesIO(docx_bytes))

    # doc.paragraphs is enough for your uploaded resume (no tables),
    # but if you later support tables, you should flatten them too.
    def get_paragraphs() -> List[Paragraph]:
        return list(doc.paragraphs)

    # Build work list
    work: List[Tuple[int, List[int]]] = []
    for block_idx, block in enumerate(bullet_blocks):
        if block_idx not in new_bullets_by_block_index:
            continue

        raw_idxs = block.get("bullet_para_idxs") or []
        target_idxs: List[int] = []
        for i in raw_idxs:
            try:
                target_idxs.append(int(i))
            except Exception:
                pass

        # Fallback: if missing, try to match by original bullet texts
        if not target_idxs:
            original_bullets = [
                str(x).strip() for x in (block.get("bullets") or []) if str(x).strip()
            ]
            if original_bullets:
                paragraphs = get_paragraphs()
                target_idxs = _find_target_idxs_by_matching_text(
                    paragraphs, original_bullets
                )

        target_idxs = [i for i in target_idxs if i >= 0]
        if target_idxs:
            work.append((block_idx, sorted(target_idxs)))

    # Process from bottom to top (safer if anything shifts)
    work.sort(key=lambda x: x[1][-1], reverse=True)

    for block_idx, target in work:
        paragraphs = get_paragraphs()
        target = [i for i in target if 0 <= i < len(paragraphs)]
        if not target:
            continue

        new_bullets = [
            (b or "").strip()
            for b in (new_bullets_by_block_index.get(block_idx) or [])
            if (b or "").strip()
        ]
        if not new_bullets:
            continue

        # Enforce SAME count as the original block
        original_texts = [(paragraphs[i].text or "").strip() for i in target]
        if len(new_bullets) < len(original_texts):
            new_bullets = new_bullets + original_texts[len(new_bullets) :]
        elif len(new_bullets) > len(original_texts):
            new_bullets = new_bullets[: len(original_texts)]

        # Overwrite 1:1
        for j, idx in enumerate(target):
            paragraphs = get_paragraphs()
            if 0 <= idx < len(paragraphs):
                _set_paragraph_text_preserve_format(paragraphs[idx], new_bullets[j])

    out = BytesIO()
    doc.save(out)
    return out.getvalue()

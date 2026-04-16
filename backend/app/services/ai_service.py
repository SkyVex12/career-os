from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

DEFAULT_JD_MODEL = os.getenv("OPENAI_JD_MODEL", "gpt-5-mini")
DEFAULT_RESUME_MODEL = os.getenv("OPENAI_RESUME_MODEL", "gpt-5.2")


class AIService:
    """Single place for OpenAI calls used by the API (service layer)."""

    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))


_TAILOR_RESUME_SCHEMA = {
    "name": "resume_tailor_summary_and_bullets_v1",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "cover_letter": {"type": "string"},
            "experiences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "exp_index": {"type": "integer", "minimum": 0},
                        "rewrites": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "source_index": {"type": "integer", "minimum": 0},
                                    "rewritten": {"type": "string"},
                                },
                                "required": ["source_index", "rewritten"],
                            },
                        },
                    },
                    "required": ["exp_index", "rewrites"],
                },
            },
        },
        "required": ["summary", "cover_letter", "experiences"],
    },
}


class Rewrite(BaseModel):
    source_index: int = Field(ge=0)
    rewritten: str = ""


class TailoredExperience(BaseModel):
    exp_index: int = Field(ge=0)
    rewrites: List[Rewrite] = Field(default_factory=list)


class TailorResumeResult(BaseModel):
    summary: str
    cover_letter: str = ""
    experiences: List[TailoredExperience] = Field(default_factory=list)


def _build_generate_resume_schema(include_cover_letter: bool) -> Dict[str, Any]:
    properties: Dict[str, Any] = {
        "blocked": {"type": "boolean"},
        "block_reason": {"type": "string"},
        "job_title": {"type": "string"},
        "summary": {"type": "string"},
        "skills": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "category": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["category", "items"],
            },
        },
        "experiences": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "company": {"type": "string"},
                    "location": {"type": "string"},
                    "job_title": {"type": "string"},
                    "duration": {"type": "string"},
                    "sentences": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "company",
                    "location",
                    "job_title",
                    "duration",
                    "sentences",
                ],
            },
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "school": {"type": "string"},
                    "degree": {"type": "string"},
                    "duration": {"type": "string"},
                },
                "required": ["school", "degree", "duration"],
            },
        },
    }
    required = [
        "blocked",
        "block_reason",
        "job_title",
        "summary",
        "skills",
        "experiences",
        "education",
    ]
    if include_cover_letter:
        properties["cover_letter"] = {"type": "string"}
        required.append("cover_letter")
    return {
        "name": "resume_generate_from_scratch_v2",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": properties,
            "required": required,
        },
    }


class ResumeSkillCategory(BaseModel):
    category: str
    items: List[str] = Field(default_factory=list)


class ResumeExperience(BaseModel):
    company: str
    location: str = ""
    job_title: str
    duration: str
    sentences: List[str] = Field(default_factory=list)


class ResumeEducation(BaseModel):
    school: str
    degree: str
    duration: str


class GeneratedResumeResult(BaseModel):
    blocked: bool = False
    block_reason: str = ""
    job_title: str
    summary: str
    skills: List[ResumeSkillCategory] = Field(default_factory=list)
    experiences: List[ResumeExperience] = Field(default_factory=list)
    education: List[ResumeEducation] = Field(default_factory=list)
    cover_letter: str = ""


def tailor_rewrite_resume(
    *,
    summary_text: str,
    experiences: List[List[str]],
    core_hard: List[str],
    core_soft: List[str],
    required_phrases: List[str],
    include_cover_letter: bool = False,
    cover_letter_instructions: str = "",
    model: str = "gpt-4.1-mini",
) -> Dict[str, Any]:
    """ONE OpenAI call to rewrite summary + bullets and optionally produce a cover letter.

    cover_letter is ALWAYS returned. If include_cover_letter=False, the model should return "".
    This keeps the number of OpenAI requests the same as before.
    """

    svc = AIService()

    model_input = {
        "task": "Rewrite the resume summary and each bullet to better match JD keys while staying strictly truthful. Optionally draft a cover letter.",
        "constraints": [
            "Do NOT add new tools, employers, years, certifications, metrics, scope, outcomes, or responsibilities not present in the original text.",
            "Summary: 3-4 sentences. Target <= 350 chars; hard cap <= 420 chars.",
            "Bullets: rewrite EVERY bullet. Do not drop bullets and do not add bullets.",
            "Bullets must keep same count and same order as provided. source_index must match.",
            "Bullets: target <= 200 chars, hard cap <= 250 chars (10pt, max ~3 lines). Past tense. Strong verb first.",
            "MUST Use all JD keywords as verbatim in total",
            # "Cover letter: if cover_letter.include is true, 180-260 words, professional tone, no fabricated claims, no addresses; otherwise return empty string.",
            "Cover letter:180-260 words, professional tone, no fabricated claims, no addresses",
        ],
        "jd": {
            "core_hard_skills": core_hard,
            "core_soft_skills": core_soft,
            "required_phrases": required_phrases,
        },
        "summary_original": summary_text or "",
        "experiences": [
            {
                "exp_index": i,
                "bullets": [
                    {"source_index": j, "text": b} for j, b in enumerate(bullets)
                ],
            }
            for i, bullets in enumerate(experiences)
        ],
        "cover_letter": {
            "include": bool(include_cover_letter),
            "instructions": cover_letter_instructions or "",
        },
    }

    resp = svc.client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": json.dumps(model_input)}],
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": _TAILOR_RESUME_SCHEMA["name"],
                "schema": _TAILOR_RESUME_SCHEMA["schema"],
            }
        },
    )
    raw = resp.output_text or ""
    data = json.loads(raw)
    try:
        validated = TailorResumeResult.model_validate(data)
        return validated.model_dump()
    except ValidationError as e:
        repair = svc.client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Return VALID JSON that matches the provided JSON Schema exactly. Fix any issues and return only the corrected JSON.",
                        }
                    ],
                },
                {"role": "user", "content": [{"type": "input_text", "text": raw}]},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": _TAILOR_RESUME_SCHEMA["name"],
                    "schema": _TAILOR_RESUME_SCHEMA["schema"],
                }
            },
        )
        repaired_raw = repair.output_text or ""
        repaired = json.loads(repaired_raw)
        validated2 = TailorResumeResult.model_validate(repaired)
        return validated2.model_dump()


_RESUME_GENERATION_PROMPT_TEMPLATE = """
Generate resume JSON only. Match the provided schema exactly.

Target:
- company: {company}
- role: {position}

Candidate profile:
- identity: Senior Software Engineer
- total_experience: 10 years
- career:
  - Xendit | Jan 2022 - Sep 2025 | Senior Software Engineer
  - Evolve | Oct 2018 - Nov 2021 | Software Engineer
  - Melechain Solutions | Jun 2016 - Aug 2018 | Software Engineer
  - Propine | Mar 2015 - May 2016 | Software Engineer

Block generation:
- clearance required
- hybrid required
- on-site required
- specific location required
- if blocked, set blocked=true and explain briefly in block_reason

Role alignment:
- top Market Title must come from the target role but seniority can be adjusted based on experience and JD language
- use only common market job titles
- keep all experience titles in the same role family as the target role unless the JD explicitly requires otherwise
- Stepful should reflect current-role seniority aligned to the target roles
- later roles should stay in the same family with natural seniority by timeline

Content structure:
- sections represented in JSON: job_title, summary, skills, experiences, optional cover_letter
- experience order must be: Stepful, Checkly, Adesso Solutions, Ai2
- each experience must include company relevance and industry relevance

Experience rules:
- Stepful: 8+ sentences
- Checkly: 8+ sentences
- Adesso Solutions: 7+ sentences
- Ai2: 5+ sentences
- each sentence should be 150-220 chars when possible
- no parentheses or brackets anywhere
- use JD phrases verbatim when truthful
- bold only JD-relevant words in experience sentences using <b>...</b>
- use ownership language: owned, led, primary responsibility, end-to-end delivery
- emphasize JD-relevant technologies and reduce unrelated emphasis

Skills rules:
- 30-35 total skills
- grouped by category
- no bold tags in skills
- order by JD importance, not general strength

ATS rules(IMPORTANT):
- repeat required skills/tools across summary, experience, and skills when truthful
- ensure ATS score is 100 percent based on JD keywords when truthful
- match the JD responsibility language closely
- keep formatting ATS-safe and simple

Output rules:
- omit cover_letter unless explicitly requested
- no fabricated claims, clearance, or location compliance

Job Description:
{jd}
""".strip()


def generate_resume_from_scratch(
    *,
    jd_text: str,
    company: str = "",
    position: str = "",
    include_cover_letter: bool = True,
    model: str = DEFAULT_RESUME_MODEL,
) -> Dict[str, Any]:
    svc = AIService()
    schema = _build_generate_resume_schema(include_cover_letter)
    prompt = _RESUME_GENERATION_PROMPT_TEMPLATE.format(
        jd=jd_text or "",
        company=company or "Unknown company",
        position=position or "Software Engineer",
    )
    if include_cover_letter:
        prompt += "\nReturn a concise professional cover letter."

    resp = svc.client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ],
        reasoning={"effort": "low"},
        text={
            "verbosity": "medium",
            "format": {
                "type": "json_schema",
                "name": schema["name"],
                "schema": schema["schema"],
            },
        },
    )

    raw = resp.output_text or ""
    data = json.loads(raw)
    data.setdefault("cover_letter", "")
    validated = GeneratedResumeResult.model_validate(data)
    return _normalize_generated_resume(
        validated.model_dump(),
        position=position,
    )


def normalize_imported_resume(
    *,
    resume_data: Dict[str, Any],
    position: str = "",
    include_cover_letter: bool = True,
) -> Dict[str, Any]:
    data = dict(resume_data or {})
    data.setdefault("blocked", False)
    data.setdefault("block_reason", "")
    data.setdefault("summary", "")
    data.setdefault("skills", [])
    data.setdefault("experiences", [])
    data.setdefault("job_title", position or "Software Engineer")
    if include_cover_letter:
        data.setdefault("cover_letter", "")
    else:
        data.pop("cover_letter", None)
    validated = GeneratedResumeResult.model_validate(
        {**data, "cover_letter": data.get("cover_letter", "")}
    )
    imported = validated.model_dump()
    if not include_cover_letter:
        imported.pop("cover_letter", None)
    return imported


def _normalize_generated_resume(
    resume: Dict[str, Any],
    *,
    position: str,
) -> Dict[str, Any]:
    aligned_title = _normalize_market_title(position or resume.get("job_title") or "")
    if aligned_title:
        resume["job_title"] = aligned_title

    family_base = _base_role_family(aligned_title or resume.get("job_title") or "")
    seniority_by_index = ["Senior", "", "", ""]
    normalized = []
    for idx, exp in enumerate(resume.get("experiences") or []):
        item = dict(exp)
        desired = _compose_experience_title(
            family_base,
            seniority_by_index[idx] if idx < len(seniority_by_index) else "",
        )
        current = _normalize_market_title(item.get("job_title") or "")
        item["job_title"] = desired or current or "Software Engineer"
        item["sentences"] = [
            _normalize_bold_markup(str(sentence))
            for sentence in (item.get("sentences") or [])
        ]
        normalized.append(item)
    resume["experiences"] = normalized
    resume["summary"] = _normalize_bold_markup(str(resume.get("summary") or ""))
    return resume


def _normalize_market_title(title: str) -> str:
    text = " ".join((title or "").replace("/", " ").replace("-", " ").split()).strip()
    if not text:
        return "Software Engineer"
    lower = text.lower()
    families = [
        "backend engineer",
        "full stack engineer",
        "frontend engineer",
        "platform engineer",
        "software engineer",
        "python engineer",
        "api engineer",
    ]
    for family in families:
        if family in lower:
            senior = (
                "Senior "
                if any(
                    word in lower for word in ("senior", "staff", "lead", "principal")
                )
                else ""
            )
            return senior + " ".join(word.capitalize() for word in family.split())
    return " ".join(word.capitalize() for word in text.split())


def _base_role_family(title: str) -> str:
    lower = (title or "").lower()
    for family in [
        "backend engineer",
        "full stack engineer",
        "frontend engineer",
        "platform engineer",
        "software engineer",
        "python engineer",
        "api engineer",
    ]:
        if family in lower:
            return " ".join(word.capitalize() for word in family.split())
    return _normalize_market_title(title)


def _compose_experience_title(base_family: str, seniority: str) -> str:
    base_family = (base_family or "Software Engineer").strip()
    seniority = (seniority or "").strip()
    return f"{seniority} {base_family}".strip()


def _normalize_bold_markup(text: str) -> str:
    text = (text or "").replace("<br>", " ").replace("<br/>", " ").strip()
    text = re.sub(r"<\s*b\s*>", "<b>", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/\s*b\s*>", "</b>", text, flags=re.IGNORECASE)

    out: List[str] = []
    i = 0
    open_tag = False
    while i < len(text):
        if text[i : i + 3].lower() == "<b>":
            if not open_tag:
                out.append("<b>")
                open_tag = True
            i += 3
            continue
        if text[i : i + 4].lower() == "</b>":
            if open_tag:
                out.append("</b>")
                open_tag = False
            i += 4
            continue
        out.append(text[i])
        i += 1

    if open_tag:
        out.append("</b>")
    return "".join(out)

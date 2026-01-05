from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


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
            "Bullets: target <= 150 chars, hard cap <= 170 chars (10pt, max ~3 lines). Past tense. Strong verb first.",
            "Use JD keywords only when supported by the original bullet/summary content.",
            "Cover letter: if requested, 180-260 words, professional tone, no fabricated claims, no addresses; otherwise return empty string.",
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
        temperature=0.2,
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
    print(data)
    try:
        validated = TailorResumeResult.model_validate(data)
        return validated.model_dump()
    except ValidationError as e:
        print("TAILOR VALIDATION ERROR:", e)
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
            temperature=0.0,
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

import os, json, re, time
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from typing import Dict, List, Any

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ================= OPENAI RESPONSE PARSING ================= #


def extract_text(response) -> str:
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text.strip()

    texts = []
    for message in getattr(response, "output", []):
        for block in getattr(message, "content", []):
            t = getattr(block, "text", None)
            if t:
                texts.append(t)
    return "\n".join(texts).strip()


def call_openai_json(
    prompt: str,
    model: str = "gpt-4.1-mini",
    temperature: float = 0.3,
    max_retries: int = 4,
    retry_sleep: float = 2.0,
) -> dict:
    """
    Calls OpenAI and guarantees a parsed JSON object or raises.
    Designed for ATS / resume generation (strict JSON).
    """

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.responses.create(
                model=model,
                input=prompt,
                temperature=temperature,
                timeout=90,
            )

            raw = extract_text(response)
            if not raw:
                raise ValueError("Empty response")

            # --- Fast path: valid JSON ---
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass

            # --- Recovery path: extract first JSON object ---
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                candidate = match.group(0)
                try:
                    return candidate
                except json.JSONDecodeError:
                    pass

            raise ValueError("Model returned invalid JSON")

        except OpenAIError as e:
            last_error = e
            # Rate-limit or transient error → retry
            if "rate limit" in str(e).lower() or "timeout" in str(e).lower():
                time.sleep(retry_sleep * attempt)
                continue
            raise

        except Exception as e:
            last_error = e
            time.sleep(retry_sleep * attempt)

    raise RuntimeError(
        f"OpenAI JSON call failed after {max_retries} attempts: {last_error}"
    )


def build_prompt_compress_jd(jd_text: str) -> str:
    return f"""
Return ONLY valid JSON.

TASK:
Compress this Job Description into an ATS_PACKAGE JSON object with:
- core_hard: list of hard skills/tech/phrases that must be present (20-35 max), something like 
- core_soft: list of soft skills phrases verbatim from JD (10-20 max)
- required_phrases: important long phrases (5-15 max)

RULES:
- Use phrases verbatim from JD when possible.
- Do NOT invent technologies not in JD.
- Output JSON only.

JOB DESCRIPTION:
{jd_text}
""".strip()


# ---------------------------
# OpenAI tailoring (rewrite)
# ---------------------------

# Structured Outputs JSON schema. :contentReference[oaicite:2]{index=2}
_TAILOR_RESUME_SCHEMA = {
    "name": "resume_tailor_summary_and_bullets_v1",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
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
        "required": ["summary", "experiences"],
    },
}


def tailor_rewrite_resume(
    *,
    summary_text: str,
    experiences: List[List[str]],  # list of exp bullets; each exp is list[str]
    core_hard: List[str],
    core_soft: List[str],
    required_phrases: List[str],
    model: str = "gpt-4.1-mini",
) -> Dict[str, Any]:
    """
    Single OpenAI call:
    - rewrite summary
    - rewrite EVERY bullet (same count, same order) for each experience
    """

    model_input = {
        "task": "Rewrite the resume summary and each bullet to better match JD keys while staying strictly truthful.",
        "constraints": [
            "Do NOT add new tools, employers, years, certifications, metrics, scope, outcomes, or responsibilities not present in the original text.",
            "Summary: 3-4 sentences. Target <= 350 chars; hard cap <= 420 chars.",
            "Bullets: rewrite EVERY bullet. Do not drop bullets and do not add bullets.",
            "Bullets must keep same count and same order as provided. source_index must match.",
            "Bullets: target <= 150 chars, hard cap <= 170 chars (10pt, max ~3 lines). Past tense. Strong verb first.",
            "Use JD keywords only when supported by the original bullet/summary content.",
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
    }

    resp = client.responses.create(
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

    return json.loads(resp.output_text)

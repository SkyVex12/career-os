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
Compress this Job Description into an JSON object with:
- core_hard: list of hard skills/tech/phrases that must be present (20-35 max) 
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
# OpenAI tailoring (rewrite) - SERVICE LAYER
# ---------------------------

# Kept for backward compatibility: the router imports from app.ai
from .services.ai_service import tailor_rewrite_resume  # noqa: E402

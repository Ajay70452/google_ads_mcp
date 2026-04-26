"""Ad copy generation using OpenAI API."""
import json
import os
import re
from datetime import datetime, timezone

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MAX_HEADLINE_LEN = 30
MAX_DESC_LEN = 90
NUM_HEADLINES = 15
NUM_DESCRIPTIONS = 4

_MODEL = "gpt-4o-mini"


def _truncate(text: str, max_len: int) -> str:
    return text[:max_len] if len(text) > max_len else text


def generate_ad_copy(
    service: str,
    location: str,
    unique_selling_points: list[str] | None = None,
) -> dict:
    """
    Call OpenAI API to generate RSA-ready ad copy.
    Returns validated headlines and descriptions.
    """
    usp_block = ""
    if unique_selling_points:
        usp_block = "\nUnique selling points:\n" + "\n".join(
            f"- {u}" for u in unique_selling_points
        )

    prompt = f"""You are a Google Ads copywriter specialising in dental clinics.

Generate ad copy for a Responsive Search Ad (RSA) for the following:
- Service: {service}
- Location: {location}{usp_block}

Rules (STRICT — these are Google Ads character limits):
- Headlines: exactly {NUM_HEADLINES}, each MAX {MAX_HEADLINE_LEN} characters (including spaces)
- Descriptions: exactly {NUM_DESCRIPTIONS}, each MAX {MAX_DESC_LEN} characters (including spaces)
- Do NOT use exclamation marks in headlines (Google policy)
- Include the location naturally in at least 2 headlines
- Include the service naturally in at least 3 headlines
- Vary tone: informational, urgency, trust/credibility, benefit-focused
- Do NOT repeat the same phrase across multiple lines

Return ONLY valid JSON in this exact format, no explanation:
{{
  "headlines": [
    "headline 1",
    "headline 2",
    ...
  ],
  "descriptions": [
    "description 1",
    "description 2",
    "description 3",
    "description 4"
  ]
}}"""

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if present
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    parsed = json.loads(raw)

    headlines = parsed.get("headlines", [])
    descriptions = parsed.get("descriptions", [])

    # Validate + truncate to limits
    validated_headlines = []
    violations = []
    for i, h in enumerate(headlines[:NUM_HEADLINES]):
        if len(h) > MAX_HEADLINE_LEN:
            violations.append(f"Headline {i+1} truncated ({len(h)} chars): '{h}'")
            h = _truncate(h, MAX_HEADLINE_LEN)
        validated_headlines.append(h)

    validated_descriptions = []
    for i, d in enumerate(descriptions[:NUM_DESCRIPTIONS]):
        if len(d) > MAX_DESC_LEN:
            violations.append(f"Description {i+1} truncated ({len(d)} chars): '{d}'")
            d = _truncate(d, MAX_DESC_LEN)
        validated_descriptions.append(d)

    return {
        "service": service,
        "location": location,
        "headlines": validated_headlines,
        "descriptions": validated_descriptions,
        "headline_count": len(validated_headlines),
        "description_count": len(validated_descriptions),
        "violations": violations,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

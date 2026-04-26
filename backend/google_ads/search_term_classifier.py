"""OpenAI-powered search term classifier for dental PPC negative keyword review."""
import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_MODEL = "gpt-4o-mini"  # fast + cheap for bulk classification
_MAX_TERMS_PER_CALL = 50


def classify_search_terms(
    search_terms: list[dict],
    account_name: str,
) -> list[dict]:
    """Identify irrelevant or low-intent search terms for a dental clinic.

    Args:
        search_terms: List of dicts with keys: search_term, cost, clicks, conversions.
        account_name: Clinic name used in the prompt for context.

    Returns:
        List of dicts: [{term, reason, priority}] where priority is HIGH/MEDIUM/LOW.
        Returns [] if nothing to flag or if input is empty.
    """
    if not search_terms:
        return []

    terms_sample = search_terms[:_MAX_TERMS_PER_CALL]
    terms_text = "\n".join(
        f"- \"{t['search_term']}\" "
        f"(spend: ${t['cost']:.2f}, clicks: {t['clicks']}, conversions: {t['conversions']:.1f})"
        for t in terms_sample
    )

    prompt = f"""You are a dental PPC expert reviewing Google Ads search terms for {account_name}, a dental clinic.

Identify search terms that are irrelevant or low-intent and should be added as negative keywords.

Search terms to review:
{terms_text}

DO NOT flag terms that are clearly relevant dental searches (e.g. "dentist near me", "teeth cleaning cost", "dental implants", "emergency dentist").

DO flag terms that are:
- Completely unrelated to dental services (e.g. "hair salon", "vet clinic")
- DIY/home remedy intent unlikely to convert (e.g. "how to pull your own tooth at home")
- Non-commercial informational (e.g. "history of dentistry", "dental school programs")
- Wrong profession (e.g. "veterinary dentist", "dental assistant salary")
- Freebie seekers unlikely to convert (e.g. "free dental care charity", "dental grants")
- Job seekers (e.g. "dental receptionist jobs", "dentist job openings")

Return ONLY valid JSON, no explanation:
{{
  "flagged_terms": [
    {{"term": "the exact search term", "reason": "one-sentence reason", "priority": "HIGH|MEDIUM|LOW"}},
    ...
  ]
}}

Priority: HIGH = clearly irrelevant/harmful, MEDIUM = unlikely to convert, LOW = borderline.
If nothing should be flagged, return {{"flagged_terms": []}}."""

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.chat.completions.create(
        model=_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    parsed = json.loads(raw)
    return parsed.get("flagged_terms", [])

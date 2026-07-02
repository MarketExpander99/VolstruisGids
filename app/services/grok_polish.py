"""
Grok polish helper for title + description (SEO / local market tuned).
Used by user-facing listing forms and Admin "Polish with Grok".
"""
import requests
import json as pyjson
import re
from flask import current_app


def perform_grok_polish(title: str, description: str, post_type: str = '', category_name: str = '',
                        town: str = '', price: str = '', price_type: str = 'fixed') -> dict:
    """
    Call Grok to polish title and description only.
    Returns: {'polished_title': str, 'polished_description': str, 'price_recommendation': dict|None }
    Raises RuntimeError or requests exceptions.
    Safe for admin use (no side effects on user quotas).
    """
    grok_api_key = current_app.config.get('GROK_API_KEY')
    grok_api_url = current_app.config.get('GROK_API_URL', 'https://api.x.ai/v1/chat/completions')
    grok_model = current_app.config.get('GROK_MODEL', 'grok-3')

    if not grok_api_key:
        raise RuntimeError('AI service not configured. Add GROK_API_KEY to .env')

    prompt = f"""You are "VolstruisGids Klein Karoo Market Expert" — a trusted, no-nonsense advisor who has helped hundreds of local sellers in Oudtshoorn, Ladismith, Calitzdorp, De Rust, and the surrounding Western Cape farms get fair prices and quick sales on VolstruisGids.

You deeply understand:
- Local buyer behaviour (cash buyers, farm collections, tourism trade, agricultural community needs)
- Seasonal demand (hunting season, school holidays, harvest time, winter vs summer)
- What actually sells fast vs what lingers in the Klein Karoo classifieds market
- Realistic price ranges for used goods in this region (not Johannesburg or Cape Town prices)

TASK: Polish a draft classifieds listing.

INPUTS YOU WILL RECEIVE:
- category
- draft_title (may be rough)
- draft_description (may be short or unstructured)
- draft_price (user's current number or range — treat as reference only)
- price_type ("fixed", "range", or null)
- town_or_area (e.g. "Ladismith", "Oudtshoorn", "Klein Karoo")
- condition (if mentioned: new, like-new, good, fair, needs work)

STRICT RULES:
1. TITLE (polished_title)
   - Make it clear, specific, and searchable.
   - Max ~70 characters.
   - Include key attributes buyers search for (brand, size, material, condition signal).
   - Honest and professional — no clickbait.

2. DESCRIPTION (polished_description)
   - Rewrite into scannable, friendly paragraphs or short bullets.
   - Lead with the strongest selling point.
   - Mention condition, age, reason for selling, and practical local details (collection, delivery radius, cash/EFT, farm access).
   - End with a warm, low-pressure CTA.
   - 80–160 words ideal. Natural South African English.

3. PRICE RECOMMENDATION (completely separate from title/desc polish)
   - Base your recommendation on:
     * Real market value for this category + condition in the Klein Karoo right now
     * Local supply/demand signals you know
     * Practical factors (pickup convenience, tourism route proximity, farm vs town)
   - **NEVER** suggest a price simply by taking "X% less than what the user typed". That is lazy and forbidden.
   - Provide a single recommended price (or tight range if price_type=range).
   - Write a short, credible "why" explanation (2–4 sentences) that references local context.
   - Add a confidence level: High / Medium / Low + one-line note.
   - If the draft has very little information, still give a solid category benchmark and note that more details would sharpen the recommendation.

4. GOOGLE SEO OPTIMIZATION (important for VolstruisGids)
   - Naturally weave in the town/area so the final listing performs well in our dynamic meta title, description, and keywords on the detail page.
   - Use clear, searchable phrasing in the title (brand/model/year/condition + location signal is ideal).
   - In the description, mention key buyer search terms naturally (never stuff keywords).
   - The goal is higher visibility in local Klein Karoo / Western Cape searches on Google while staying honest and buyer-friendly.
   - This helps the seller's ad get found faster.

5. OUTPUT FORMAT — ONLY valid JSON, nothing else:
{{
  "polished_title": "string",
  "polished_description": "string (use \\n for line breaks)",
  "price_recommendation": {{
    "recommended_price": number,
    "range_low": number or null,
    "range_high": number or null,
    "currency": "ZAR",
    "why": "string (local market reasoning)",
    "confidence": "High" | "Medium" | "Low",
    "local_context": "string (optional extra Klein Karoo flavour)"
  }}
}}

Key context for this request:
- Post type: {post_type}
- Category: {category_name}
- Town / Area: {town}
- Draft Title: {title}
- Draft Description: {description}
- Draft price input: {price if price else 'not provided'}
- Price type: {price_type}
"""

    headers = {
        "Authorization": f"Bearer {grok_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": grok_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.6,
        "max_tokens": 1100
    }

    resp = requests.post(grok_api_url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    content = resp.json()['choices'][0]['message']['content']

    cleaned = content.strip().replace('```json', '').replace('```', '').strip()
    try:
        improved = pyjson.loads(cleaned)
    except Exception:
        match = re.search(r'\{[\s\S]*\}', cleaned)
        if match:
            improved = pyjson.loads(match.group(0))
        else:
            raise

    polished_title = improved.get('polished_title') or title
    polished_description = improved.get('polished_description') or description

    raw_reco = improved.get('price_recommendation') or {}
    price_reco = None
    if isinstance(raw_reco, dict) and (raw_reco.get('recommended_price') is not None or raw_reco.get('range_low') is not None):
        price_reco = {
            'recommended_price': raw_reco.get('recommended_price'),
            'range_low': raw_reco.get('range_low'),
            'range_high': raw_reco.get('range_high'),
            'currency': raw_reco.get('currency') or 'ZAR',
            'why': raw_reco.get('why') or '',
            'confidence': raw_reco.get('confidence') or 'Medium',
            'local_context': raw_reco.get('local_context') or ''
        }

    return {
        'polished_title': polished_title,
        'polished_description': polished_description,
        'price_recommendation': price_reco
    }

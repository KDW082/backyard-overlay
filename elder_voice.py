import os
import json
import random
import urllib.request
import urllib.error

XAI_API_KEY = os.getenv("XAI_API_KEY")

FALLBACK_LINES = [
    "Still.",
    "Nothing obvious right now.",
    "Wind picked up.",
    "Could stay like this.",
    "Pressure dropped. Usually changes things.",
    "Same as earlier.",
    "Sky changed some.",
    "Water's probably flat.",
]

BANNED_WORDS = {
    "beautiful", "peaceful", "perfect", "magical", "serene",
    "escape", "getaway", "experience", "stunning", "breathtaking"
}

MODE_HINTS = {
    "field_observation": "Only describe current visible-feeling conditions. No wildlife claims. No fake sensing.",
    "behavior_insight": "Interpret patterns conservatively. No guarantees. No fake movement.",
    "northern_context": "Use local geography naturally. Grayling, Roscommon, Houghton Lake are close. Traverse City, Petoskey, Mackinac are day trips.",
    "lifestyle_trigger": "Subtle human-use lines only. Low-key. No ad language.",
    "quiet_narrative": "Short, understated, slightly mysterious. Incomplete thoughts allowed."
}


def json_response(status_code: int, payload: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload)
    }


def tokenize(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    return {t for t in cleaned.split() if t}


def similarity(a: str, b: str) -> float:
    ta = tokenize(a)
    tb = tokenize(b)
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb)
    union = len(ta | tb)
    return overlap / union if union else 0.0


def line_is_bad(line: str, recent_lines: list[str], season_name: str, period_name: str) -> bool:
    if not line:
        return True

    s = line.strip()
    if len(s) < 4 or len(s) > 110:
        return True

    lower = s.lower()

    if any(word in lower for word in BANNED_WORDS):
        return True

    banned_claims = [
        "movement detected",
        "detected movement",
        "sensor",
        "motion event",
        "feeder quiet for",
        "wildlife detected",
        "something moved",
        "heard something earlier",
        "not visible long enough to call it"
    ]
    if any(p in lower for p in banned_claims):
        return True

    season_conflicts = {
        "spring": ["rut", "fall color", "deep winter", "ski", "fresh snow", "ice formation"],
        "summer": ["rut", "fall color", "deep winter", "fresh snow", "ski", "ice formation", "ice-out"],
        "autumn": ["deep winter", "fresh snow", "ski", "ice formation", "spring warbler", "ice-out"],
        "winter": ["dock coffee", "boating", "golf", "fireflies", "morel", "warbler", "fawn season", "fall color"],
    }
    period_conflicts = {
        "dawn": ["midday", "after dark", "night runs", "last light", "dusk"],
        "morning": ["after dark", "night runs", "last light", "dusk"],
        "midday": ["after dark", "night runs", "first light", "dawn"],
        "afternoon": ["after dark", "night runs", "first light", "dawn"],
        "dusk": ["first light", "midday", "morning settles"],
        "night": ["first light", "dock coffee", "midday", "afternoon starts"],
    }

    if any(k in lower for k in season_conflicts.get(season_name, [])):
        return True
    if any(k in lower for k in period_conflicts.get(period_name, [])):
        return True

    for old in recent_lines[-30:]:
        if similarity(s, old) > 0.42:
            return True

    return False


def clean_lines(lines: list[str], recent_lines: list[str], season_name: str, period_name: str) -> list[str]:
    out: list[str] = []
    for line in lines:
        line = " ".join(str(line).split()).strip()
        if not line:
            continue
        if not line.endswith((".", "!", "?")):
            line += "."
        if line_is_bad(line, recent_lines + out, season_name, period_name):
            continue
        out.append(line)
    return out


def build_prompt(body: dict) -> str:
    weather = body.get("weather", {}) or {}
    forecast = body.get("forecast", []) or []
    phenology = body.get("phenology", []) or []
    recent_lines = body.get("recent_lines", []) or []
    memory_callbacks = body.get("memory_callbacks", []) or []

    season_name = body.get("season", "unknown")
    period_name = body.get("period", "unknown")

    # Server chooses mode mix so model does not freestyle endlessly
    requested_modes = [
        "field_observation",
        "behavior_insight",
        "quiet_narrative",
        "northern_context",
        "lifestyle_trigger",
        "quiet_narrative",
    ]

    mode_block = "\n".join(f"- {m}: {MODE_HINTS[m]}" for m in requested_modes)

    return f"""
You are writing short marquee lines for a live outdoor stream in Northern Michigan near Higgins Lake.

REALITY RULES:
- You are NOT detecting movement.
- Do NOT invent events.
- Do NOT imply sensors, tracking, timestamps, or feeder measurements.
- Only write lines grounded in supplied conditions and reasonable local knowledge.

PERSONALITY:
- Calm, experienced local
- Minimal words
- Slightly dry
- Observant
- Not poetic
- Not trying to impress anyone
- Understatement beats explanation

STYLE:
- 6 to 14 words per line
- Short lines
- Slightly incomplete is fine
- If it sounds written for an audience, reject it

AVOID:
- beautiful, peaceful, perfect, magical, serene
- tourism copy
- ad language
- generic inspiration
- fake wildlife activity
- "feeder quiet for X minutes"
- "movement detected"
- anything not true right now

CURRENT CONTEXT:
- location: Higgins Lake / Roscommon County, Michigan
- season: {season_name}
- time_of_day: {period_name}
- weather: {json.dumps(weather, ensure_ascii=False)}
- forecast: {json.dumps(forecast, ensure_ascii=False)}
- phenology: {json.dumps(phenology, ensure_ascii=False)}
- memory_callbacks: {json.dumps(memory_callbacks, ensure_ascii=False)}

LOCAL GEOGRAPHY RULES:
- Grayling, Roscommon, and Houghton Lake are close-in
- Traverse City, Petoskey, and Mackinac are day trips

MODE PLAN:
{mode_block}

Generate exactly 8 lines total.
Make them varied across the requested modes.
Only include lesson-like lines if directly relevant to current conditions.
Recent lines to avoid repeating:
{json.dumps(recent_lines[-30:], ensure_ascii=False)}

Return strict JSON only:
{{
  "lines": [
    "line 1",
    "line 2",
    "line 3",
    "line 4",
    "line 5",
    "line 6",
    "line 7",
    "line 8"
  ]
}}
""".strip()


def call_xai(prompt: str) -> list[str]:
    if not XAI_API_KEY:
        raise RuntimeError("Missing XAI_API_KEY")

    payload = {
        "model": "grok-4.20-reasoning",
        "input": [
            {
                "role": "system",
                "content": "You write terse, grounded observational lines and always return valid JSON."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7
    }

    req = urllib.request.Request(
        "https://api.x.ai/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {XAI_API_KEY}"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")

    data = json.loads(raw)

    text = ""
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text += content.get("text", "")

    if not text.strip():
        raise RuntimeError("Empty model output")

    parsed = json.loads(text)
    lines = parsed.get("lines", [])
    if not isinstance(lines, list):
        raise RuntimeError("Invalid lines payload")

    return [str(x).strip() for x in lines if str(x).strip()]


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        body = {}

    recent_lines = body.get("recent_lines", []) or []
    season_name = body.get("season", "unknown")
    period_name = body.get("period", "unknown")

    try:
        prompt = build_prompt(body)
        lines = call_xai(prompt)
        lines = clean_lines(lines, recent_lines, season_name, period_name)

        if len(lines) < 4:
            fallback = clean_lines(FALLBACK_LINES, recent_lines, season_name, period_name)
            lines.extend(fallback)

        return json_response(200, {"lines": lines[:8]})

    except Exception as e:
        fallback = clean_lines(FALLBACK_LINES, recent_lines, season_name, period_name)
        return json_response(200, {
            "lines": fallback[:8],
            "fallback": True,
            "error": str(e)
        })

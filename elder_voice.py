import os
import json
import random
import urllib.request
import urllib.error

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

BANNED_WORDS = {
    "beautiful", "peaceful", "perfect", "magical", "serene",
    "escape", "getaway", "experience", "stunning", "breathtaking"
}

BANNED_PHRASES = [
    "movement detected",
    "detected movement",
    "sensor",
    "motion event",
    "wildlife detected",
    "feeder quiet for",
    "something moved",
    "heard something earlier",
    "not visible long enough to call it",
]

FALLBACK_BY_MODE = {
    "field_observation": [
        "Still.",
        "Nothing obvious right now.",
        "Wind picked up.",
        "Sky changed some.",
        "Not much.",
    ],
    "behavior_insight": [
        "Pressure dropped. Usually changes things.",
        "Wind like this hides more than it shows.",
        "Midday usually flattens things.",
        "This light window usually does more with less.",
    ],
    "northern_context": [
        "Grayling is an easy run from here.",
        "Roscommon and Houghton Lake stay close-in.",
        "Traverse City takes more of the day.",
        "Mackinac is worth the day. Not a quick stop.",
    ],
    "lifestyle_trigger": [
        "Water's probably flat.",
        "Good night for a fire.",
        "Could sit here a while.",
        "Up here, the right spot saves time.",
    ],
    "quiet_narrative": [
        "Quiet again.",
        "Same as earlier.",
        "Hard to tell.",
        "Could stay like this.",
        "Still.",
    ],
}

MODE_SEQUENCE = [
    "field_observation",
    "behavior_insight",
    "quiet_narrative",
    "northern_context",
    "lifestyle_trigger",
    "quiet_narrative",
    "field_observation",
    "behavior_insight",
]

SEASON_CONFLICTS = {
    "spring": ["rut", "fall color", "deep winter", "ski", "fresh snow", "ice formation"],
    "summer": ["rut", "fall color", "deep winter", "fresh snow", "ski", "ice formation", "ice-out"],
    "autumn": ["deep winter", "fresh snow", "ski", "ice formation", "spring warbler", "ice-out"],
    "winter": ["dock coffee", "boating", "golf", "fireflies", "morel", "warbler", "fawn season", "fall color"],
}

PERIOD_CONFLICTS = {
    "dawn": ["midday", "after dark", "night runs", "last light", "dusk"],
    "morning": ["after dark", "night runs", "last light", "dusk"],
    "midday": ["after dark", "night runs", "first light", "dawn"],
    "afternoon": ["after dark", "night runs", "first light", "dawn"],
    "dusk": ["first light", "midday", "morning settles"],
    "night": ["first light", "dock coffee", "midday", "afternoon starts"],
}

def json_response(payload: dict, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload)
    }

def normalize_space(text: str) -> str:
    return " ".join(str(text).split()).strip()

def tokenize(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    return {t for t in cleaned.split() if t}

def opener(text: str) -> str:
    return " ".join(list(tokenize(text))[:2])

def similarity(a: str, b: str) -> float:
    ta = tokenize(a)
    tb = tokenize(b)
    if not ta or not tb:
        return 0.0
    overlap = len(ta & tb)
    union = len(ta | tb)
    return overlap / union if union else 0.0

def line_fits_context(line: str, season_name: str, period_name: str) -> bool:
    lower = line.lower()
    if any(k in lower for k in SEASON_CONFLICTS.get(season_name, [])):
        return False
    if any(k in lower for k in PERIOD_CONFLICTS.get(period_name, [])):
        return False
    return True

def line_is_bad(line: str, recent_lines: list[str], season_name: str, period_name: str, accepted: list[str]) -> bool:
    s = normalize_space(line)
    if not s:
        return True
    if len(s) < 4 or len(s) > 110:
        return True

    lower = s.lower()

    if any(word in lower for word in BANNED_WORDS):
        return True
    if any(phrase in lower for phrase in BANNED_PHRASES):
        return True
    if not line_fits_context(s, season_name, period_name):
        return True

    # repeated opener
    op = opener(s)
    recent_openers = [opener(x) for x in (recent_lines[-20:] + accepted[-8:])]
    if op and op in recent_openers:
        return True

    # repeated idea
    for old in recent_lines[-35:] + accepted:
        if similarity(s, old) > 0.40:
            return True

    return False

def fallback_lines(recent_lines: list[str], season_name: str, period_name: str) -> list[str]:
    raw = []
    for mode in MODE_SEQUENCE:
        pool = FALLBACK_BY_MODE.get(mode, [])
        raw.extend(random.sample(pool, k=min(2, len(pool))))
    out = []
    for line in raw:
        if not line_is_bad(line, recent_lines, season_name, period_name, out):
            if not line.endswith((".", "!", "?")):
                line += "."
            out.append(line)
        if len(out) >= 8:
            break
    return out[:8]

def build_prompt(body: dict, mode: str, recent_lines: list[str]) -> str:
    weather = body.get("weather", {}) or {}
    forecast = body.get("forecast", []) or []
    phenology = body.get("phenology", []) or []
    memory_callbacks = body.get("memory_callbacks", []) or []

    mode_rules = {
        "field_observation": "Only current conditions. No wildlife claims. No fake events.",
        "behavior_insight": "Interpret patterns conservatively. No guarantees. No fake movement.",
        "northern_context": "Use local geography naturally. Grayling, Roscommon, Houghton Lake are close. Traverse City, Petoskey, Mackinac are day trips.",
        "lifestyle_trigger": "Low-key human-use lines only. No ad language.",
        "quiet_narrative": "Short, understated, slightly incomplete. Slightly mysterious, never theatrical.",
    }[mode]

    return f"""
You are writing one short marquee line for a live outdoor stream near Higgins Lake in Northern Michigan.

REALITY RULES:
- You are NOT detecting movement.
- Do NOT invent events.
- Do NOT imply sensors, tracking, timestamps, feeders, or wildlife detections.
- Only write what fits the supplied conditions and grounded local knowledge.

PERSONALITY:
- Calm, experienced local
- Minimal words
- Slightly dry
- Observant
- Understated
- If it sounds written for an audience, reject it

STYLE:
- 6 to 14 words
- One line only
- Incomplete is okay
- No poetry
- No tourism tone
- No ad language

MODE:
{mode}
{mode_rules}

CURRENT CONTEXT:
season: {body.get("season", "unknown")}
time_of_day: {body.get("period", "unknown")}
weather: {json.dumps(weather, ensure_ascii=False)}
forecast: {json.dumps(forecast[:4], ensure_ascii=False)}
phenology: {json.dumps(phenology[:2], ensure_ascii=False)}
memory_callbacks: {json.dumps(memory_callbacks[:4], ensure_ascii=False)}

AVOID REPEATING THESE:
{json.dumps(recent_lines[-20:], ensure_ascii=False)}

Return JSON only:
{{"line":"..."}}
""".strip()

def groq_call(prompt: str) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("Missing GROQ_API_KEY")

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Return strict JSON only. No markdown. No explanation."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.8,
        "max_tokens": 120,
        "response_format": {"type": "json_object"}
    }

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")

    data = json.loads(raw)
    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return normalize_space(parsed.get("line", ""))

def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        body = {}

    recent_lines = body.get("recent_lines", []) or []
    season_name = body.get("season", "unknown")
    period_name = body.get("period", "unknown")

    accepted: list[str] = []

    try:
        for mode in MODE_SEQUENCE:
            prompt = build_prompt(body, mode, recent_lines + accepted)
            line = groq_call(prompt)

            if not line:
                continue
            if not line.endswith((".", "!", "?")):
                line += "."

            if line_is_bad(line, recent_lines, season_name, period_name, accepted):
                continue

            accepted.append(line)

        if len(accepted) < 5:
            for line in fallback_lines(recent_lines + accepted, season_name, period_name):
                if not line_is_bad(line, recent_lines, season_name, period_name, accepted):
                    accepted.append(line)
                if len(accepted) >= 8:
                    break

        return json_response({"lines": accepted[:8]})

    except Exception as e:
        return json_response({
            "lines": fallback_lines(recent_lines, season_name, period_name),
            "fallback": True,
            "error": str(e)
        })

import json
import os
import re
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

BANNED = [
    "beautiful", "amazing", "magical", "perfect", "peaceful", "serene",
    "stunning", "breathtaking", "incredible", "wonderful", "escape",
    "getaway", "paradise", "hidden gem",
    "detected", "movement detected", "feeder quiet", "sensor", "unresolved",
    "something moved", "peripheral motion",
]

# Opener patterns that indicate voiceover / template tone
BAD_OPENERS = [
    r'^this is ',
    r'^this part ',
    r'^this window ',
    r'^this place ',
    r'^this light ',
    r'^this weather ',
    r'^northern michigan ',
    r'^higgins lake ',
    r'^the woods ',
    r'^current conditions ',
]

MODE_PROMPTS = {
    "field_observation": """Write one line about current conditions — temperature, sky, wind, or light.
Sound like someone checking outside, not filing a report.
Short is fine. Fragments allowed. "Wind's up." is better than "Wind speeds have increased."
No clinical readings. No "conditions are." Just what it feels like right now.""",

    "behavior_insight": """Write one line about what the current conditions tend to mean — for the woods, lake, or wildlife patterns.
Only write this if something real is worth saying. Pressure, wind, rain, cold, heat, dusk — specific triggers only.
Short and dry. "Falling pressure usually shifts things." "Wind like this hides more than it shows."
If nothing specific applies, write: SKIP""",

    "northern_context": """Write one line about the regional geography — nearby towns, distances, what's close and what's a longer run.
Keep it grounded. Like something a local would say, not a tourism pamphlet.
"Grayling sits about half an hour from here." "Traverse City's a longer run west." """,

    "lifestyle_trigger": """Write one line suggesting something someone might actually do here — lake, fire, trail, dock, paddle — only if the season and conditions make it feel natural.
Understated. Not a pitch. "Fire would make sense tonight." "Lake's probably still right now."
If conditions don't suggest anything specific, write: SKIP""",

    "quiet_narrative": """Write one short line that feels like a quiet, slightly dry observation about this place or this kind of place.
Not poetic. Not explained. Like something you'd think but not necessarily say out loud.
Very short is fine: "Still not giving much away." "Could stay like this." "Hard to tell yet."
No hype. No audience. One thought.""",
}

SYSTEM_PROMPT = """You are a longtime Northern Michigan local who lives near Higgins Lake. You are not a narrator, not a guide, not a host.

Voice: grounded, dry, minimal, observant. Like someone who notices things without announcing them.
Think Sam Elliott restraint — but no cowboy gimmick. Just sparse, honest attention.

Hard rules:
- Never invent animal sightings, events, or movement.
- Never use: beautiful, amazing, magical, perfect, peaceful, serene, stunning, breathtaking, incredible, wonderful.
- No sensor language: detected, movement detected, unresolved, something moved, peripheral.
- No feeder timing. No fake event timestamps.
- No "This is..." openers. No "Northern Michigan is..." No "Higgins Lake is..."
- Do not start lines with "The woods" or "Current conditions."
- Write one line only. No explanation. No preamble.
- Sound like one person noticing something, not a system generating content.
- If the task says SKIP is acceptable and there's nothing real to say, write exactly: SKIP

Rhythm rules (very important):
- Vary sentence length. Short lines are good. Fragments are allowed.
- Do not always write complete sentences.
- Mix: 3-word lines, 8-word lines, 12-word lines.
- Good: "Wind picked up." / "Didn't settle." / "Pressure's been off all day."
- Bad: "The current conditions indicate that wind speeds have increased significantly."
- One idea per line. Never compound two observations into one sentence."""


def clean_line(line: str) -> str | None:
    line = re.sub(r'^\s*[\d]+[.)]\s*', '', line)
    line = re.sub(r'^\s*[-•*]\s*', '', line)
    line = line.strip()

    if not line or line.upper() == 'SKIP':
        return None

    words = line.split()
    if len(words) < 3:
        return None

    # Hard cap at 18 words
    if len(words) > 18:
        line = ' '.join(words[:18])
        for punct in ['. ', '— ', ', ']:
            idx = line.rfind(punct)
            if idx > 20:
                line = line[:idx].rstrip(',—').strip()
                break

    if line and line[-1] not in '.!?':
        line += '.'
    if line:
        line = line[0].upper() + line[1:]

    lc = line.lower()

    for banned in BANNED:
        if banned in lc:
            return None

    for pattern in BAD_OPENERS:
        if re.match(pattern, lc):
            return None

    return line


def too_similar(line: str, recent: list) -> bool:
    """Lightweight semantic repetition check."""
    lc = line.lower()
    toks_new = set(re.sub(r'[^a-z0-9\s]', ' ', lc).split())

    for prev in recent[-20:]:
        plc = prev.lower()
        toks_prev = set(re.sub(r'[^a-z0-9\s]', ' ', plc).split())
        if not toks_new or not toks_prev:
            continue
        overlap = len(toks_new & toks_prev)
        jaccard = overlap / (len(toks_new) + len(toks_prev) - overlap)
        if jaccard > 0.45:
            return True
        # Same first 3 words
        new_open = ' '.join(list(toks_new)[:3])
        prev_open = ' '.join(list(toks_prev)[:3])
        if new_open == prev_open:
            return True

    # Suppress structural overuse
    usually_count = sum(1 for l in recent[-4:] if 'usually' in l.lower())
    if usually_count >= 2 and 'usually' in lc:
        return True

    return False


def generate_line(mode: str, ctx: dict, recent: list, retries: int = 3) -> str | None:
    mode_instruction = MODE_PROMPTS.get(mode, MODE_PROMPTS["quiet_narrative"])

    weather = ctx.get("weather", {})
    weather_summary = ""
    if weather:
        parts = []
        if weather.get("temp_f") is not None:
            parts.append(f"{weather['temp_f']:.0f}F")
        if weather.get("wind_mph") is not None:
            w = f"{weather['wind_mph']:.0f} mph"
            if weather.get("wind_dir"):
                w += f" {weather['wind_dir']}"
            parts.append(w)
        if weather.get("sky"):
            parts.append(weather["sky"])
        if weather.get("pressure_trend"):
            parts.append(f"pressure {weather['pressure_trend']}")
        weather_summary = ", ".join(parts)

    context_block = f"""Location: Higgins Lake, Roscommon County, Michigan
Time of day: {ctx.get("period", "unknown")}
Season: {ctx.get("season", "unknown")}
Conditions: {weather_summary}"""

    if ctx.get("memory_callbacks"):
        context_block += "\nEarlier: " + " / ".join(ctx["memory_callbacks"][-3:])

    if ctx.get("phenology"):
        context_block += "\nSeasonal: " + ctx["phenology"][0] if ctx["phenology"] else ""

    if recent:
        context_block += "\nAvoid lines similar to: " + " | ".join(recent[-10:])

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"{context_block}\n\nTask: {mode_instruction}"}
                ],
                temperature=0.88 + (attempt * 0.05),  # slight temp increase on retry
                max_tokens=60
            )
            raw = response.choices[0].message.content.strip()
            # Take first line only
            raw = raw.split('\n')[0].strip()
            cleaned = clean_line(raw)
            if cleaned and not too_similar(cleaned, recent):
                return cleaned
        except Exception:
            pass

    return None


def handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))

        recent_lines = body.get("recent_lines", [])

        # More lines per call = larger pool on the frontend = less repetition
        # Weighted toward the modes that carry the voice
        modes = [
            "field_observation",
            "quiet_narrative",
            "behavior_insight",
            "quiet_narrative",
            "northern_context",
            "quiet_narrative",
            "lifestyle_trigger",
            "field_observation",
            "quiet_narrative",
            "behavior_insight",
            "quiet_narrative",
            "northern_context",
        ]

        lines = []
        session_recent = list(recent_lines)

        for mode in modes:
            if len(lines) >= 12:
                break
            line = generate_line(mode, body, session_recent)
            if line:
                lines.append(line)
                session_recent.append(line)

        if len(lines) < 4:
            raise ValueError(f"Too few valid lines: {len(lines)}")

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"lines": lines})
        }

    except Exception as e:
        fallback = [
            "Wind hasn't settled since earlier.",
            "Pressure's been doing something all afternoon.",
            "Light is changing faster than the air is.",
            "Feels like the place is between things right now.",
            "Nothing is showing itself yet.",
            "Sky looks like it's still making up its mind.",
            "Worth watching a little longer.",
            "Didn't really settle after that."
        ]
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "lines": fallback,
                "fallback": True,
                "error": str(e)
            })
        }

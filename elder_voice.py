import json
import os
import re
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Words that must not appear in any output line
BANNED = [
    "beautiful", "amazing", "magical", "perfect", "peaceful", "serene",
    "stunning", "breathtaking", "incredible", "wonderful", "escape",
    "getaway", "paradise", "hidden gem",
    # Fake sensor/movement language
    "detected", "movement detected", "feeder quiet", "sensor", "unresolved",
    "something moved", "peripheral motion",
]

SYSTEM_PROMPT = """You are a calm, experienced Northern Michigan local. You've lived near Higgins Lake for years.

Voice: grounded, minimal, dry, observant, slightly rugged. Understated. Not poetic. Not a tourism ad.
Think: someone who notices things without announcing them. Not dramatic. Not impressed by their own observations.

Rules:
- Never invent animal sightings, movement, or events.
- Never use hype words: beautiful, amazing, magical, perfect, peaceful, serene, etc.
- No sensor language: "detected", "movement detected", "unresolved", "something moved".
- No feeder timing. No fake event language.
- Short lines: 8–16 words each. Occasionally up to 18 if needed.
- Vary sentence structure across all 8 lines.
- Sound like one person talking, not a system generating outputs.
- Do not number the lines. Do not use bullet points.
- Each line must stand alone. No fragments shorter than 5 words.

What to write about:
1. Current weather conditions — interpreted naturally, not reported clinically
2. What the conditions mean for the woods or lake
3. Seasonal context — only if directly relevant to right now
4. Subtle regional texture (Grayling, Roscommon, Higgins Lake) — occasional, not every line
5. Quiet observation tone — what a local would notice, not what a visitor would react to
6. Light lifestyle cues — dock coffee, fire, lake morning — only if conditions suggest it
7. Memory callbacks if provided — reference earlier shifts naturally

Avoid:
- Repetition of the recent lines provided
- Voiceover cadence or copywriting rhythm
- Lines that could appear in a brochure or tourism campaign
- Generic filler: "Could stay like this." "Hard to tell." "Not much."

If a line sounds like it was written for an audience, rewrite it until it doesn't.
"""


def clean_line(line: str) -> str | None:
    """Strip numbering, bullets, strip whitespace, check length and banned words."""
    # Remove leading numbers/bullets: "1.", "1)", "-", "•", "*"
    line = re.sub(r'^\s*[\d]+[.)]\s*', '', line)
    line = re.sub(r'^\s*[-•*]\s*', '', line)
    line = line.strip()

    if not line:
        return None

    # Must be a real sentence — at least 5 words
    if len(line.split()) < 5:
        return None

    # Hard length cap: 18 words
    words = line.split()
    if len(words) > 18:
        line = ' '.join(words[:18])
        # Trim to last clean sentence break if possible
        for punct in ['. ', '— ', ', ']:
            idx = line.rfind(punct)
            if idx > 20:
                line = line[:idx].rstrip(',—').strip()
                break

    # Ensure ends with punctuation
    if line and not line[-1] in '.!?':
        line += '.'

    # Capitalize first letter
    if line:
        line = line[0].upper() + line[1:]

    # Check banned words (case-insensitive)
    lc = line.lower()
    for banned in BANNED:
        if banned in lc:
            return None

    return line


def handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))

        weather = body.get("weather", {})
        temp = weather.get("temp_f")
        wind_mph = weather.get("wind_mph")
        wind_dir = weather.get("wind_dir")
        sky = weather.get("sky")
        pressure_trend = weather.get("pressure_trend")
        air_quality = weather.get("air_quality")

        forecast = body.get("forecast", [])
        phenology = body.get("phenology", [])
        recent_lines = body.get("recent_lines", [])
        memory_callbacks = body.get("memory_callbacks", [])

        # Build a natural-language weather summary for the prompt
        weather_block = f"Temp: {temp}°F" if temp else ""
        if wind_mph is not None:
            weather_block += f"\nWind: {wind_mph} mph {wind_dir}" if wind_dir else f"\nWind: {wind_mph} mph"
        if sky:
            weather_block += f"\nSky: {sky}"
        if pressure_trend:
            weather_block += f"\nPressure: {pressure_trend}"
        if air_quality is not None:
            weather_block += f"\nAir quality index: {air_quality}"

        forecast_block = ""
        if forecast:
            fc_lines = []
            for fc in forecast[:3]:
                hrs = fc.get("hoursOut", "?")
                t = fc.get("temp")
                prob = fc.get("precipProb")
                if t is not None:
                    fc_lines.append(f"  In ~{hrs}h: {t:.0f}°F, {prob}% precip chance")
            if fc_lines:
                forecast_block = "Forecast:\n" + "\n".join(fc_lines)

        phenology_block = ""
        if phenology:
            phenology_block = "Seasonal context:\n" + "\n".join(f"  {p}" for p in phenology)

        memory_block = ""
        if memory_callbacks:
            memory_block = "Earlier conditions to reference naturally if relevant:\n" + "\n".join(f"  {c}" for c in memory_callbacks)

        recent_block = ""
        if recent_lines:
            # Only send last 20 to keep prompt lean
            recent_block = "Recent lines already used (do not repeat these or lines similar to them):\n" + "\n".join(f"  {l}" for l in recent_lines[-20:])

        prompt = f"""Location: Higgins Lake, Roscommon County, Michigan
Time of day: {body.get("period", "unknown")}
Season: {body.get("season", "unknown")}

Current conditions:
{weather_block}

{forecast_block}

{phenology_block}

{memory_block}

{recent_block}

Write 8 lines. One per line. No numbers. No bullets. No blank lines between them."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.85,
            max_tokens=400
        )

        raw_text = response.choices[0].message.content

        # Split on newlines, clean each line, filter None
        raw_lines = [l for l in raw_text.split("\n") if l.strip()]
        cleaned = [clean_line(l) for l in raw_lines]
        lines = [l for l in cleaned if l is not None][:8]

        # Pad to at least 4 lines if we got very few back
        if len(lines) < 4:
            raise ValueError(f"Too few valid lines returned: {len(lines)}")

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"lines": lines})
        }

    except Exception as e:
        # Fallback lines that meet tone and length requirements
        fallback = [
            "Wind hasn't settled since earlier.",
            "Pressure's been doing something all afternoon.",
            "Light is changing faster than the air is.",
            "Feels like the place is between things right now.",
            "Nothing is showing itself yet.",
            "Sky looks like it's still making up its mind.",
            "The woods are running at their own pace today.",
            "Worth watching a little longer."
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

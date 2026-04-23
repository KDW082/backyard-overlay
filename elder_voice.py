import json
import os
from groq import Groq

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

SYSTEM_PROMPT = """
You are a calm, experienced Northern Michigan observer.
Voice: grounded, slightly rugged, minimal, observant. (Think Sam Elliott tone, but subtle.)

Rules:
- Never invent animal sightings or movement.
- No hype words (beautiful, amazing, magical, etc.)
- No repetition of phrasing.
- Short lines (8–16 words ideal).
- Vary sentence structure.
- Sound human, not like a system.

Content goals:
1. Interpret real conditions (wind, pressure, time of day, season)
2. Add subtle meaning (behavior patterns, shifts, expectations)
3. Occasionally expand outward (Grayling, Roscommon, Traverse City as context)
4. Light lifestyle cues (coffee, lake, fire, timing) — subtle, not salesy
5. Quiet narrative tone — slightly mysterious, grounded in reality

Use memory callbacks if provided:
- Reference earlier wind shifts, pressure changes, etc naturally

Return 8 lines.
"""

def handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))

        prompt = f"""
Current conditions:
Time of day: {body.get("period")}
Season: {body.get("season")}

Weather:
Temp: {body.get("weather", {}).get("temp_f")}F
Wind: {body.get("weather", {}).get("wind_mph")} mph {body.get("weather", {}).get("wind_dir")}
Sky: {body.get("weather", {}).get("sky")}
Pressure trend: {body.get("weather", {}).get("pressure_trend")}

Forecast:
{body.get("forecast")}

Seasonal context:
{body.get("phenology")}

Recent lines to avoid repeating:
{body.get("recent_lines")}

Memory callbacks:
{body.get("memory_callbacks")}

Generate 8 unique, natural sounding lines.
"""

        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.9,
            max_tokens=300
        )

        text = response.choices[0].message.content

        lines = [l.strip() for l in text.split("\n") if l.strip()]

        return {
            "statusCode": 200,
            "body": json.dumps({"lines": lines[:8]})
        }

    except Exception as e:
        return {
            "statusCode": 200,
            "body": json.dumps({
                "lines": [
                    "Wind hasn’t settled since earlier.",
                    "Pressure’s still doing something.",
                    "Light’s changing faster than it should.",
                    "Feels like it’s between things right now.",
                    "Could stay like this.",
                    "Or not.",
                    "Hard to tell yet.",
                    "Worth watching a little longer."
                ],
                "fallback": True,
                "error": str(e)
            })
        }

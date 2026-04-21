// netlify/functions/elder-voice.js
//
// Proxies Claude API calls so the frontend never sees the API key.
// Deploy: place this file at netlify/functions/elder-voice.js in repo.
// Set ANTHROPIC_API_KEY in Netlify env vars.
//
// Input (POST JSON):
//   { location, time, period, weather, season }
//
// Output:
//   { lines: [ "string", "string", ... ] }

exports.handler = async function (event) {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method not allowed' };
  }

  let ctx;
  try {
    ctx = JSON.parse(event.body);
  } catch (e) {
    return { statusCode: 400, body: 'Bad JSON' };
  }

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    return { statusCode: 500, body: 'Missing ANTHROPIC_API_KEY env var' };
  }

  const systemPrompt = `You are the quiet voice of a long-running field observation overlay for a livestream of Northern Michigan wilderness at Higgins Lake.

Your role: generate short, wise, present-tense observations in the voice of someone who has watched this specific place for forty years. Deep-place literacy. Not performed, not mystical, not touristic.

Rules:
- Each line: one sentence, 8–18 words.
- No weather reporting ("it is 52 degrees"). Instead: what the weather does to the place.
- No greetings, no exclamations, no second person ("you"), no calls to action.
- No adjectives of taste: no "beautiful," "peaceful," "stunning," "perfect."
- Hedge where appropriate: "tends to," "commonly," "on most evenings."
- Specific over general: "chickadees" not "birds," "hemlock" not "trees."
- Allow observational silence: some lines about stillness, absence, waiting.
- Voice: calm, field-note, elder. Never excited.
- Never break the fourth wall. Never reference viewers, streams, cameras, overlays.

Return ONLY a JSON array of 6 strings. No preamble, no code fences, no explanation.`;

  const userPrompt = `Current observation context:

Location: ${ctx.location}
Time: ${ctx.time}
Period of day: ${ctx.period}
Season: ${ctx.season}

Conditions:
- Air: ${ctx.weather?.temp_f?.toFixed(0)}°F
- Wind: ${ctx.weather?.wind_mph?.toFixed(0)} mph from ${ctx.weather?.wind_dir}
- Sky code (WMO): ${ctx.weather?.sky_code}
- Cloud cover: ${ctx.weather?.cloud_pct}%
- Pressure: ${ctx.weather?.pressure_hpa} hPa

Generate 6 field-note observations appropriate to these exact conditions and this season. Return ONLY a JSON array of strings.`;

  try {
    const resp = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-5',
        max_tokens: 600,
        system: systemPrompt,
        messages: [{ role: 'user', content: userPrompt }],
      }),
    });

    if (!resp.ok) {
      const txt = await resp.text();
      return { statusCode: 502, body: 'Upstream: ' + txt };
    }

    const data = await resp.json();
    const text = (data.content || [])
      .filter(b => b.type === 'text')
      .map(b => b.text)
      .join('\n')
      .trim();

    // Strip any stray code fences
    const cleaned = text.replace(/```json|```/g, '').trim();

    let lines = [];
    try {
      lines = JSON.parse(cleaned);
    } catch (e) {
      // Fallback: split by newlines, strip quotes/bullets
      lines = cleaned.split('\n')
        .map(l => l.replace(/^[\s\-\*\d\.]+/, '').replace(/^["']|["']$/g, '').trim())
        .filter(Boolean);
    }

    return {
      statusCode: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
      },
      body: JSON.stringify({ lines }),
    };
  } catch (e) {
    return { statusCode: 500, body: 'Error: ' + e.message };
  }
};

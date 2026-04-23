import os, json, urllib.request

API_KEY = os.getenv("GROQ_API_KEY")

def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except:
        body = {}

    prompt = f"""
You are a calm Northern Michigan local observing Higgins Lake.

Rules:
- No fake events
- No "movement detected"
- No tourism language
- Keep lines short, real, understated

Context:
{json.dumps(body)}

Return JSON:
{{"lines":["...","...","...","...","...","..."]}}
"""

    try:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps({
                "model": "llama3-70b-8192",
                "messages": [
                    {"role": "system", "content": "Write short grounded observational lines."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7
            }).encode(),
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            }
        )

        res = urllib.request.urlopen(req)
        data = json.loads(res.read().decode())

        text = data["choices"][0]["message"]["content"]

        lines = [l.strip() for l in text.split("\n") if len(l.strip()) > 3]

        return {
            "statusCode": 200,
            "body": json.dumps({"lines": lines[:8]})
        }

    except:
        return {
            "statusCode": 200,
            "body": json.dumps({
                "lines": [
                    "Still.",
                    "Wind picked up.",
                    "Nothing obvious."
                ]
            })
        }

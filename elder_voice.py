#!/usr/bin/env python3
"""
Northern Michigan's Backyard — Elder Voice TTS
================================================
Runs on your OBS machine. Polls the overlay for new elder quote lines
and speaks them aloud using Microsoft Edge TTS (free, no API key).
OBS picks up the audio via desktop audio capture.

SETUP (one time):
  pip install edge-tts pygame requests

RUN:
  python elder_voice.py

The script watches for the overlay to update its quote, then speaks
the new line in a calm, unhurried voice. Stays silent between lines.
"""

import asyncio
import io
import time
import hashlib
import requests
import edge_tts
import pygame

# ── CONFIG ──────────────────────────────────────────────────────
OVERLAY_URL = "https://keen-mandazi-301fc1.netlify.app"  # your Netlify URL
VOICE       = "en-US-GuyNeural"   # calm male voice
SPEED       = "-8%"               # slightly slower than default
VOLUME      = "+0%"
POLL_INTERVAL = 15                # seconds between checks
MIN_SILENCE   = 240               # minimum seconds between spoken lines (4 min)
# ────────────────────────────────────────────────────────────────

last_spoken_hash = None
last_spoken_at   = 0

def extract_quote(html: str) -> str | None:
    """Pull the current quote text from the overlay HTML."""
    import re
    # Match the quote div content
    match = re.search(r'id="quote"[^>]*>([^<]+)<', html)
    if match:
        text = match.group(1).strip()
        if text and text != '—':
            return text
    return None

async def speak(text: str):
    """Generate and play TTS audio."""
    communicate = edge_tts.Communicate(
        text,
        voice=VOICE,
        rate=SPEED,
        volume=VOLUME,
    )
    # Stream to bytes buffer
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    buf.seek(0)

    # Play via pygame
    pygame.mixer.music.load(buf)
    pygame.mixer.music.play()
    # Wait for playback to finish
    while pygame.mixer.music.get_busy():
        await asyncio.sleep(0.1)

async def main():
    global last_spoken_hash, last_spoken_at

    pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
    print(f"Elder Voice TTS running · voice: {VOICE} · polling every {POLL_INTERVAL}s")
    print(f"Overlay: {OVERLAY_URL}")
    print("Press Ctrl+C to stop.\n")

    while True:
        try:
            resp = requests.get(OVERLAY_URL, timeout=8)
            quote = extract_quote(resp.text)

            if quote:
                quote_hash = hashlib.md5(quote.encode()).hexdigest()
                now = time.time()
                elapsed = now - last_spoken_at

                if quote_hash != last_spoken_hash and elapsed >= MIN_SILENCE:
                    print(f"Speaking: {quote}")
                    # Brief pause before speaking — feels more natural
                    await asyncio.sleep(1.5)
                    await speak(quote)
                    last_spoken_hash = quote_hash
                    last_spoken_at   = time.time()
                else:
                    if quote_hash == last_spoken_hash:
                        print(f"Same quote — waiting for change")
                    else:
                        remaining = int(MIN_SILENCE - elapsed)
                        print(f"Quote changed — waiting {remaining}s before next line")

        except requests.RequestException as e:
            print(f"Network error: {e}")
        except Exception as e:
            print(f"Error: {e}")

        await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())

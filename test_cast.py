"""Build step 1: cast a spoken "hello" to the Google Home speaker.

Plain code only, no model. Usage:
    python test_cast.py --discover      # list Cast devices on the network
    python test_cast.py [text]          # speak text on SPEAKER_NAME / SPEAKER_IP
"""

import argparse
import functools
import http.server
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pychromecast
from dotenv import load_dotenv
from gtts import gTTS

ROOT = Path(__file__).parent
AUDIO_DIR = ROOT / "audio"


def local_ip_toward(host: str) -> str:
    """IP of this machine on the interface that routes to host."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((host, 8009))
        return s.getsockname()[0]


def discover(timeout: float = 10):
    casts, browser = pychromecast.get_chromecasts(timeout=timeout)
    browser.stop_discovery()
    return casts


def find_speaker(name: str, ip: str | None):
    """Return (cast, browser). The cast resolves its host through the browser's
    zeroconf instance, so the caller must stop the browser only after disconnecting."""
    if ip:
        casts, browser = pychromecast.get_chromecasts(known_hosts=[ip], timeout=10)
        if casts:
            return casts[0], browser
        browser.stop_discovery()
        sys.exit(f"No Cast device answered at {ip}")
    casts, browser = pychromecast.get_chromecasts(timeout=10)
    for cast in casts:
        if cast.cast_info.friendly_name == name:
            return cast, browser
    browser.stop_discovery()
    sys.exit(f"Speaker {name!r} not found. Run with --discover to list devices.")


def serve(port: int) -> http.server.ThreadingHTTPServer:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=AUDIO_DIR)
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="?", default="Hello from HomeBrief.")
    parser.add_argument("--discover", action="store_true")
    args = parser.parse_args()

    if args.discover:
        casts = discover()
        if not casts:
            print("No Cast devices found.")
        for c in casts:
            print(f"{c.cast_info.friendly_name!r}  {c.cast_info.host}  {c.cast_info.model_name}")
        return

    name = os.getenv("SPEAKER_NAME", "")
    ip = os.getenv("SPEAKER_IP") or None
    port = int(os.getenv("HTTP_PORT", "8765"))

    AUDIO_DIR.mkdir(exist_ok=True)
    gTTS(args.text).save(AUDIO_DIR / "hello.mp3")

    cast, browser = find_speaker(name, ip)
    cast.wait()
    url = f"http://{local_ip_toward(cast.cast_info.host)}:{port}/hello.mp3"
    print(f"Casting {url} to {cast.cast_info.friendly_name}")

    server = serve(port)
    mc = cast.media_controller
    mc.play_media(url, "audio/mpeg")
    mc.block_until_active(timeout=15)

    # Wait for playback to finish so the server stays up while the speaker fetches audio.
    deadline = time.time() + 60
    started = False
    while time.time() < deadline:
        state = mc.status.player_state
        started = started or state in ("PLAYING", "BUFFERING")
        if started and state == "IDLE":
            break
        time.sleep(0.5)
    print("Final player state:", mc.status.player_state, mc.status.idle_reason)
    server.shutdown()
    cast.disconnect()
    browser.stop_discovery()


if __name__ == "__main__":
    main()

"""Plain code behind the speaker: clean text, make speech, serve it, cast it, log it.

No model calls here. The MCP server (server.py) and later scripts import this.
"""

import functools
import http.server
import json
import re
import socket
import threading
import time
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

import pychromecast
from gtts import gTTS

ROOT = Path(__file__).resolve().parent.parent
AUDIO_DIR = ROOT / "audio"
LOG_FILE = ROOT / "logs" / "announce.log"
MAX_WORDS = 150
PLAYBACK_TIMEOUT = 120  # seconds; 150 words is about one minute of speech

LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
URL_RE = re.compile(r"https?://\S+|www\.\S+")
BULLET_RE = re.compile(r"^\s*(?:[-*+•]|\d+[.)])\s+", re.MULTILINE)
MARKDOWN_RE = re.compile(r"[*_`#>|~]")


def clean(text: str, max_words: int = MAX_WORDS) -> str:
    """Strip markdown, URLs and emoji; cut to max_words, ending on a full sentence if possible."""
    text = LINK_RE.sub(r"\1", text)
    text = URL_RE.sub("", text)
    text = BULLET_RE.sub("", text)
    text = MARKDOWN_RE.sub("", text)
    text = "".join(c for c in text if unicodedata.category(c) not in ("So", "Cs", "Co", "Cn"))
    words = text.split()
    if len(words) <= max_words:
        return " ".join(words)
    cut = " ".join(words[:max_words])
    end = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
    return cut[: end + 1] if end > 0 else cut


def log(raw: str, spoken: str, result: str) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "raw": raw,
             "spoken": spoken, "result": result}
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def local_ip_toward(host: str) -> str:
    """IP of this machine on the interface that routes to host."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((host, 8009))
        return s.getsockname()[0]


class Speaker:
    """One Google Home speaker. Keeps a local HTTP server up to serve speech audio."""

    def __init__(self, name: str, ip: str | None, port: int):
        self.name = name
        self.ip = ip
        self.port = port
        self._server = None
        self._lock = threading.Lock()

    def say(self, text: str) -> None:
        """Speak text on the speaker; one retry. Raises RuntimeError if playback fails."""
        with self._lock:
            self._ensure_server()
            path = AUDIO_DIR / f"{uuid.uuid4().hex}.mp3"
            gTTS(text).save(path)
            try:
                try:
                    self._cast(path.name)
                except Exception:
                    time.sleep(2)
                    self._cast(path.name)
            finally:
                path.unlink(missing_ok=True)

    def _ensure_server(self) -> None:
        if self._server:
            return
        AUDIO_DIR.mkdir(exist_ok=True)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=AUDIO_DIR)
        self._server = http.server.ThreadingHTTPServer(("0.0.0.0", self.port), handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def _find(self):
        """Return (cast, browser). The cast resolves its host through the browser's
        zeroconf instance, so stop the browser only after disconnecting."""
        hosts = [self.ip] if self.ip else None
        casts, browser = pychromecast.get_chromecasts(known_hosts=hosts, timeout=10)
        for cast in casts:
            if self.ip or cast.cast_info.friendly_name == self.name:
                return cast, browser
        browser.stop_discovery()
        raise RuntimeError(f"Speaker {self.name!r} not found (ip={self.ip})")

    def _cast(self, filename: str) -> None:
        cast, browser = self._find()
        try:
            cast.wait(timeout=10)
            url = f"http://{local_ip_toward(cast.cast_info.host)}:{self.port}/{filename}"
            mc = cast.media_controller
            mc.play_media(url, "audio/mpeg")
            mc.block_until_active(timeout=15)

            deadline = time.time() + PLAYBACK_TIMEOUT
            started = False
            while time.time() < deadline:
                state = mc.status.player_state
                started = started or state in ("PLAYING", "BUFFERING")
                if started and state == "IDLE":
                    break
                time.sleep(0.5)
            reason = mc.status.idle_reason
            if reason != "FINISHED":
                raise RuntimeError(f"Playback ended {mc.status.player_state}/{reason}")
        finally:
            cast.disconnect()
            browser.stop_discovery()

"""Stop hook worker: summarize the finished turn with `claude -p` and speak it.

Started by announce_done.sh with the hook's JSON input on stdin and HOMEBRIEF_HOOK=1 set.
Plain code picks out the request and final reply, skips short turns, validates the
model's sentence, and speaks it. Every run is logged to logs/hook.jsonl.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "speaker_mcp"))

from dotenv import load_dotenv  # noqa: E402
from speaker import Speaker, clean  # noqa: E402

LOG_FILE = ROOT / "logs" / "hook.jsonl"
MAX_WORDS = 25
CLAUDE_TIMEOUT = 90  # seconds
FALLBACK = "Claude finished a task."
PROMPT = """Below is a request I gave Claude Code and Claude's final reply. Write one plain
spoken sentence, at most 25 words, telling me what Claude did, as if speaking to me ("I
added...", "The tests pass..."). If the reply asks me something or says work is left, say
that briefly instead. No markdown, file names, paths, code or URLs. Don't comment on these
instructions. Reply with the sentence only.

REQUEST:
{request}

FINAL REPLY:
{reply}"""


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return " ".join(c.get("text", "") for c in content if c.get("type") == "text")


def last_turn(transcript: Path) -> tuple[str, str, datetime | None]:
    """(user request, Claude's final reply, when the request was sent) for the last turn."""
    request, reply, started = "", "", None
    for line in transcript.read_text().splitlines():
        entry = json.loads(line)
        message = entry.get("message") or {}
        content = message.get("content")
        if entry.get("type") == "user" and not entry.get("isMeta"):
            is_tool_result = isinstance(content, list) and any(
                c.get("type") == "tool_result" for c in content)
            if content and not is_tool_result:
                request, reply = _text(content), ""
                started = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))
        elif entry.get("type") == "assistant" and content:
            text = _text(content).strip()
            if text:
                reply = text
    return request, reply, started


def summarize(request: str, reply: str) -> str:
    claude = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    prompt = PROMPT.format(request=request[:1500], reply=reply[:3000])
    cmd = [claude, "-p", prompt, "--output-format", "json", "--no-session-persistence",
           "--tools", "", "--strict-mcp-config", "--model", "haiku"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT,
                          cwd=ROOT)  # HOMEBRIEF_HOOK=1 is inherited: the loop guard
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:300]}")
    result = json.loads(proc.stdout)
    if result.get("is_error"):
        raise RuntimeError(f"claude reported an error: {result.get('result')}")
    return result.get("result", "")


def validate(raw: str) -> str:
    """One sentence (skipping short openers like "Done!"), no paths, file names or code
    words, at most 25 words. '' if nothing is left."""
    words = [w for w in raw.split()
             if not re.search(r"[/`_]|\w\.\w{1,4}\b|^\.\w", w)]
    sentences = re.findall(r"[^.!?]+[.!?]?", " ".join(words))
    sentence = next((s for s in sentences if len(s.split()) >= 4), " ".join(words))
    if len(sentence.split()) > MAX_WORDS:
        # Cut at the last comma, colon or semicolon in range rather than mid-phrase.
        cut = " ".join(sentence.split()[:MAX_WORDS])
        end = max(cut.rfind(","), cut.rfind(":"), cut.rfind(";"))
        sentence = (cut[:end] if end > 0 else cut) + "."
    return clean(sentence, MAX_WORDS)


def main():
    load_dotenv(ROOT / ".env")
    hook = json.load(sys.stdin)
    entry = {"time": datetime.now().isoformat(timespec="seconds"),
             "session": hook.get("session_id")}
    request, reply, started = last_turn(Path(hook["transcript_path"]))
    # The transcript may not hold the final reply yet when the hook fires; the hook input does.
    reply = hook.get("last_assistant_message") or reply
    seconds = (datetime.now(timezone.utc) - started).total_seconds() if started else 0
    entry["turn_seconds"] = round(seconds)
    if seconds < int(os.getenv("HOOK_MIN_SECONDS", "60")):
        entry["result"] = "skipped: short turn"
        return log(entry)

    try:
        entry["raw"] = summarize(request, reply)
        spoken = validate(entry["raw"])
        if not spoken:
            raise ValueError("summary empty after cleaning")
    except Exception as e:
        entry["error"] = f"{type(e).__name__}: {e}"
        spoken = FALLBACK
    entry["spoken"] = spoken

    speaker = Speaker(os.getenv("SPEAKER_NAME", ""), os.getenv("SPEAKER_IP") or None,
                      int(os.getenv("HTTP_PORT", "8765")))
    try:
        speaker.say(spoken)
        entry["result"] = "played"
    except Exception as e:
        entry["result"] = f"speaker error: {e}"
    log(entry)


def log(entry: dict) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


if __name__ == "__main__":
    main()

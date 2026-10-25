"""Build step 4: the scheduled morning briefing.

Plain code fetches today's events, asks `claude -p` to plan the day and write the
briefing (it may add [claude] focus blocks through the calendar MCP server), validates
the text, and plays it on the speaker. Every run is logged to logs/briefings.jsonl.

Usage:
    python morning_briefing.py                # real run
    python morning_briefing.py --dry-run      # no focus blocks, print instead of speaking
    python morning_briefing.py --date 2026-10-21
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / "speaker_mcp"), str(ROOT / "calendar_mcp")]

from gcal import EARLIEST, TZ, day_events, earliest_start  # noqa: E402
from speaker import MAX_WORDS, Speaker, clean  # noqa: E402

PROMPT = ROOT / "prompts" / "morning_briefing.md"
LOG_FILE = ROOT / "logs" / "briefings.jsonl"
QUEUE_FILE = ROOT / "logs" / "hook_queue.jsonl"  # Stop hook sentences held back overnight
MAX_QUEUED = 3  # overnight task sentences read out after the briefing
CLAUDE_TIMEOUT = 300  # seconds
FOCUS_ON = ("You may add one focus block with create_tagged_event, at least 60 "
            "minutes, only in free time after now, starting no earlier than {earliest} and "
            "ending by 10 PM. Skip this if the day is already full or already has events with "
            "\"claude\": true. If the tool rejects the block, accept the reason and do not retry "
            "it more than once.")
FOCUS_OFF = "Focus blocks are turned off for this run. Do not call create_tagged_event."

ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen").split()
TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty"}
STOPWORDS = {"a", "an", "the", "my", "your", "and", "with", "for", "to", "of", "at", "on", "in"}


def spoken_time(iso: str) -> str:
    """'2026-10-21T10:30-07:00' -> 'ten thirty'; noon and midnight by name."""
    t = datetime.fromisoformat(iso).astimezone(TZ)
    if t.minute == 0 and t.hour in (0, 12):
        return "midnight" if t.hour == 0 else "noon"
    hour = ONES[t.hour % 12 or 12]
    if t.minute == 0:
        return hour
    if t.minute < 10:
        return f"{hour} oh {ONES[t.minute]}"
    if t.minute < 20:
        return f"{hour} {ONES[t.minute]}"
    tens, ones = divmod(t.minute, 10)
    return f"{hour} {TENS[tens]}" + (f" {ONES[ones]}" if ones else "")


def describe(event: dict) -> str:
    if event["all_day"]:
        return f"{event['title']}, all day"
    return f"{event['title']} at {spoken_time(event['start'])}"


def _words(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9']+", text.lower())
            if w not in STOPWORDS and len(w) > 1}


def mentioned(title: str, text: str) -> bool:
    """True if at least half the title's meaningful words appear in text."""
    title_words = _words(title)
    return not title_words or 2 * len(title_words & _words(text)) >= len(title_words)


def fallback(events: list[dict]) -> str:
    if not events:
        return "Good morning. Your calendar is empty today."
    return ("Good morning. I couldn't write today's briefing, so here is your calendar. "
            + " ".join(describe(e) + "." for e in events))


def earliest_text(day: date) -> str:
    """When focus blocks may start today, with the reason on class days."""
    first = earliest_start(day)
    if first == EARLIEST:
        return f"{first:%-I:%M %p}"
    return f"{first:%-I:%M %p} (an hour after my last class today; never during or near a class)"


def overnight_text() -> str:
    """The Stop hook sentences queued overnight, as one spoken paragraph ('' if none).
    Each sentence was already validated by the hook."""
    if not QUEUE_FILE.exists():
        return ""
    items = [json.loads(line)["spoken"] for line in QUEUE_FILE.read_text().splitlines() if line]
    if not items:
        return ""
    head = "Overnight, Claude finished " + ("one task." if len(items) == 1 else f"{len(items)} tasks.")
    more = [f"And {len(items) - MAX_QUEUED} more in the log."] if len(items) > MAX_QUEUED else []
    return " ".join([head, *items[:MAX_QUEUED], *more])


def prompt_events(events: list[dict]) -> str:
    """Events as compact JSON with plain HH:MM local times for the model."""
    rows = []
    for e in events:
        row = {"title": e["title"], "claude": e["claude"]}
        if e["all_day"]:
            row["all_day"] = True
        else:
            row["start"] = datetime.fromisoformat(e["start"]).strftime("%H:%M")
            row["end"] = datetime.fromisoformat(e["end"]).strftime("%H:%M")
        if e["location"]:
            row["location"] = e["location"]
        rows.append(row)
    return json.dumps(rows, indent=1) if rows else "(none)"


def run_claude(prompt: str, allow_writes: bool) -> dict:
    """Run claude -p with only the calendar tools. Returns its JSON result."""
    claude = shutil.which("claude") or str(Path.home() / ".local/bin/claude")
    mcp_config = {"mcpServers": {"calendar": {
        "command": sys.executable, "args": [str(ROOT / "calendar_mcp" / "server.py")],
        # The briefing adds at most one focus block a day; more only when I ask in a session.
        "env": {"HOMEBRIEF_MAX_CLAUDE_PER_DAY": "1"}}}}
    tools = ["mcp__calendar__list_events"]
    if allow_writes:
        tools.append("mcp__calendar__create_tagged_event")
    cmd = [claude, "-p", prompt, "--output-format", "json", "--no-session-persistence",
           "--tools", "", "--mcp-config", json.dumps(mcp_config), "--strict-mcp-config",
           "--allowedTools", *tools]
    env = {**os.environ, "HOMEBRIEF_HOOK": "1"}  # keep the Stop hook (step 5) from firing
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=CLAUDE_TIMEOUT,
                          cwd=ROOT, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:500]}")
    result = json.loads(proc.stdout)
    if result.get("is_error"):
        raise RuntimeError(f"claude reported an error: {result.get('result')}")
    return result


def validate(raw: str, events: list[dict]) -> tuple[str, list[str]]:
    """Clean the model's text, check every event is mentioned, append any that are missing.
    Returns (spoken text, warnings). Raises ValueError if nothing usable is left."""
    warnings = []
    text = clean(raw)
    if not text:
        raise ValueError("briefing empty after cleaning")
    if len(raw.split()) > MAX_WORDS:
        warnings.append(f"model wrote {len(raw.split())} words; cut to {MAX_WORDS}")
    missing = [e for e in events if not mentioned(e["title"], text)]
    if missing:
        warnings.append("missing events: " + ", ".join(e["title"] for e in missing))
        extra = "Also on your calendar: " + "; ".join(describe(e) for e in missing) + "."
        text = clean(raw, MAX_WORDS - len(extra.split())) + " " + extra
    return text, warnings


def log(entry: dict) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run and os.getenv("HOMEBRIEF_SCHEDULER") != "1":
        sys.exit("HOMEBRIEF_SCHEDULER=1 is not set in .env: this machine doesn't run the briefing")

    now = datetime.now(TZ)
    day = args.date or now.date()
    entry = {"time": now.isoformat(timespec="seconds"), "day": day.isoformat(),
             "dry_run": args.dry_run}

    events = day_events(day)
    entry["events"] = events
    try:
        prompt = Template(PROMPT.read_text()).substitute(
            today=day.strftime("%A, %B %-d, %Y"),
            now=now.strftime("%-I:%M %p") if day == now.date() else "the night before",
            events=prompt_events(events),
            focus_rule=FOCUS_OFF if args.dry_run else FOCUS_ON.format(earliest=earliest_text(day)),
        )
        result = run_claude(prompt, allow_writes=not args.dry_run)
        entry["raw"] = result.get("result", "")
        entry["cost_usd"] = result.get("total_cost_usd")
        spoken, entry["warnings"] = validate(entry["raw"], events)
    except Exception as e:
        entry["error"] = f"{type(e).__name__}: {e}"
        spoken = fallback(events)
    entry["spoken"] = spoken
    # Re-read so the log shows any focus blocks Claude added.
    entry["events_after"] = [e for e in day_events(day) if e["claude"]]

    overnight = overnight_text()
    entry["overnight"] = overnight
    if args.dry_run:
        print(spoken)
        if overnight:
            print(overnight)
        entry["result"] = "printed"
    else:
        speaker = Speaker(os.getenv("SPEAKER_NAME", ""), os.getenv("SPEAKER_IP") or None,
                          int(os.getenv("HTTP_PORT", "8765")))
        try:
            speaker.say(spoken)
            if overnight:
                speaker.say(overnight)
                QUEUE_FILE.unlink()  # only once heard; otherwise they wait for the next briefing
            entry["result"] = "played"
        except Exception as e:
            entry["result"] = f"speaker error: {e}"
    log(entry)
    for w in entry.get("warnings", []):
        print("warning:", w, file=sys.stderr)
    if "error" in entry:
        print("error:", entry["error"], file=sys.stderr)
    print("result:", entry["result"], file=sys.stderr)
    return 0 if entry["result"] in ("played", "printed") else 1


if __name__ == "__main__":
    sys.exit(main())

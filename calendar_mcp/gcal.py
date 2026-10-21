"""Plain code for Google Calendar: auth, read a day's events, create [claude]-tagged events.

The calendar write rules from CLAUDE.md are enforced here, not left to the model.
There is deliberately no update or delete function.

One-time setup:  .venv/bin/python calendar_mcp/gcal.py --auth
Check access:    .venv/bin/python calendar_mcp/gcal.py [YYYY-MM-DD]
"""

import json
import os
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS = ROOT / "credentials.json"
TOKEN = ROOT / "token.json"
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
TAG = "[claude]"
EARLIEST = time(8, 0)
LATEST = time(22, 0)
MAX_TITLE = 100
MAX_CLAUDE_PER_DAY = 3  # cap on [claude] events per day, so repeated runs can't pile up

load_dotenv(ROOT / ".env")
TZ = ZoneInfo(os.getenv("TIME_ZONE", "America/Los_Angeles"))
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")


def authorize() -> None:
    """Interactive OAuth: prints a URL to open in the browser, saves token.json."""
    sys.stdout.reconfigure(line_buffering=True)  # show the URL even when output isn't a terminal
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS, SCOPES)
    creds = flow.run_local_server(port=0, open_browser=False)
    TOKEN.write_text(creds.to_json())
    print(f"Saved {TOKEN.name}")


def _service():
    if not TOKEN.exists():
        raise RuntimeError("No token.json. Run: .venv/bin/python calendar_mcp/gcal.py --auth")
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds.valid:
        if not (creds.expired and creds.refresh_token):
            raise RuntimeError("Calendar token is invalid. Rerun gcal.py --auth")
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _local(value: str) -> datetime:
    """Parse an ISO datetime; naive values are taken as local time."""
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def _normalize(event: dict) -> dict:
    start, end = event["start"], event["end"]
    all_day = "date" in start
    return {
        "id": event["id"],
        "title": event.get("summary", "(no title)"),
        "start": start["date"] if all_day else _local(start["dateTime"]).isoformat(timespec="minutes"),
        "end": end["date"] if all_day else _local(end["dateTime"]).isoformat(timespec="minutes"),
        "all_day": all_day,
        "location": event.get("location", ""),
        "claude": TAG in event.get("description", ""),
    }


def _declined(event: dict) -> bool:
    return any(a.get("self") and a.get("responseStatus") == "declined"
               for a in event.get("attendees", []))


def day_events(day: date) -> list[dict]:
    """Events on the calendar for one local day, in start order, skipping declined ones."""
    start = datetime.combine(day, time.min, TZ)
    items = _service().events().list(
        calendarId=CALENDAR_ID,
        timeMin=start.isoformat(),
        timeMax=(start + timedelta(days=1)).isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute().get("items", [])
    return [_normalize(e) for e in items if e.get("status") != "cancelled" and not _declined(e)]


def check_new_event(start: datetime, end: datetime, existing: list[dict]) -> list[str]:
    """Return the CLAUDE.md write rules this new event would break (empty if none)."""
    errors = []
    if end <= start:
        errors.append("end must be after start")
    if start.date() != end.date():
        errors.append("event must start and end on the same day")
    if start.time() < EARLIEST or end.time() > LATEST:
        errors.append("event must fall between 8:00 AM and 10:00 PM")
    if sum(e["claude"] for e in existing) >= MAX_CLAUDE_PER_DAY:
        errors.append(f"already {MAX_CLAUDE_PER_DAY} Claude events that day")
    for e in existing:
        if e["all_day"]:
            continue
        if _local(e["start"]) < end and start < _local(e["end"]):
            span = f"{_local(e['start']):%H:%M}-{_local(e['end']):%H:%M}"
            errors.append(f"overlaps {e['title']!r} ({span})")
    return errors


def create_tagged_event(title: str, start: str, end: str, note: str = "") -> dict:
    """Create an event tagged [claude] after checking the write rules. Raises ValueError."""
    title = " ".join(title.split())
    if not title or len(title) > MAX_TITLE:
        raise ValueError(f"title must be 1-{MAX_TITLE} characters")
    s, e = _local(start), _local(end)
    errors = check_new_event(s, e, day_events(s.date()))
    if errors:
        raise ValueError("; ".join(errors))
    body = {
        "summary": title,
        "description": f"{note.strip()}\n\n{TAG}".strip(),
        "start": {"dateTime": s.isoformat(), "timeZone": str(TZ)},
        "end": {"dateTime": e.isoformat(), "timeZone": str(TZ)},
    }
    created = _service().events().insert(calendarId=CALENDAR_ID, body=body).execute()
    return _normalize(created)


if __name__ == "__main__":
    if sys.argv[1:] == ["--auth"]:
        authorize()
    else:
        day = date.fromisoformat(sys.argv[1]) if sys.argv[1:] else datetime.now(TZ).date()
        print(json.dumps(day_events(day), indent=2))

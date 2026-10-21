"""MCP server giving Claude Code read access to the calendar and one guarded write.

Run as a script (stdio transport): .venv/bin/python calendar_mcp/server.py
There is no update or delete tool; the write rules are enforced in gcal.py.
"""

from datetime import date, datetime

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from gcal import TZ, create_tagged_event as _create, day_events

mcp = MCPServer("calendar")


@mcp.tool()
def list_events(day: str = "") -> list[dict]:
    """List the user's calendar events for one day (YYYY-MM-DD; default today).

    Times are local. Events with "claude": true were created by Claude.
    """
    try:
        d = date.fromisoformat(day) if day else datetime.now(TZ).date()
        return day_events(d)
    except Exception as e:
        raise ToolError(f"Could not read the calendar: {e}") from e


@mcp.tool()
def create_tagged_event(title: str, start: str, end: str, note: str = "") -> dict:
    """Add an event (for example a focus block) to the user's calendar.

    start and end are local times as YYYY-MM-DDTHH:MM. The event must be between
    8:00 AM and 10:00 PM on a single day and must not overlap any existing event;
    otherwise it is rejected with the reason. The event is tagged [claude]
    automatically. Use note for a short reason the block was suggested.
    """
    try:
        return _create(title, start, end, note)
    except ValueError as e:
        raise ToolError(f"Event rejected: {e}") from e
    except Exception as e:
        raise ToolError(f"Could not create the event: {e}") from e


if __name__ == "__main__":
    mcp.run("stdio")

"""MCP server exposing announce(text) to Claude Code.

Run as a script (stdio transport): .venv/bin/python speaker_mcp/server.py
Stdout carries the MCP protocol; all logging goes to stderr and logs/announce.log.
"""

import os

from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer

from speaker import MAX_WORDS, ROOT, Speaker, clean, log

load_dotenv(ROOT / ".env")
speaker = Speaker(
    name=os.getenv("SPEAKER_NAME", ""),
    ip=os.getenv("SPEAKER_IP") or None,
    port=int(os.getenv("HTTP_PORT", "8765")),
)
mcp = MCPServer("speaker")


@mcp.tool()
def announce(text: str) -> str:
    """Speak text aloud on the Google Home speaker in the user's home.

    Write plain spoken sentences: no markdown, bullet symbols, emoji, URLs or code.
    Say times the way a person would ("ten thirty", "at noon"), with no time zones.
    At most 150 words; longer text is cut at the last full sentence.
    """
    spoken = clean(text, MAX_WORDS)
    if not spoken:
        log(text, spoken, "rejected: empty after cleaning")
        raise ValueError("Nothing left to say after removing markdown, URLs and emoji.")
    try:
        speaker.say(spoken)
    except Exception as e:
        log(text, spoken, f"error: {e}")
        raise RuntimeError(f"Could not play on the speaker: {e}") from e
    log(text, spoken, "played")
    return f"Played on {speaker.name}: {spoken}"


if __name__ == "__main__":
    mcp.run("stdio")

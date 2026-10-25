# HomeBrief — future plans

Features that aren't built yet. What exists today is in `README.md`; how it got there is in
`LOG.md`.

## Update and delete focus blocks

**Goal:** let Claude move, shorten or remove a focus block it created ("push my CS372 block
to 2 PM", "cancel tonight's focus block"), instead of only creating new ones.

**How:** through the claude.ai Google Calendar connector, which already offers `update_event`
and `delete_event`. HomeBrief's own calendar server (`calendar_mcp/`) stays create-only.

**Rules it has to keep** (from `CLAUDE.md`):
- Only events with `[claude]` in the description. Never my own events.
- A changed event still follows the focus block rules: 11:30 AM to 10 PM, class-day start
  times, no overlaps.
- Interactive sessions show me the change and ask before writing.
- The headless morning briefing never deletes anything, and doesn't get these tools.

**Open problem:** the connector edits any event, and none of the rules above are checked in
code there; only the prompt asks for them. That breaks the project's "rules in code, not in the
prompt" idea. Before building this, decide between:
- Checking each connector change in code first (for example, a `PreToolUse` hook on the
  connector's update and delete tools that reads the event and blocks it unless it carries
  `[claude]` and the new time passes `check_new_event()`), or
- Adding guarded `update_tagged_event` / `delete_tagged_event` tools to `calendar_mcp/`
  instead, which would mean the calendar server is no longer create-only.

**Related safeguard:** a separate "HomeBrief" calendar with Google's `calendar.app.created`
permission would make my own events unreachable for any code using HomeBrief's token,
whichever of the above is chosen.

## Play on the PC speakers when the Google Home is unavailable

**Goal:** if the Google Home can't be reached (unplugged, off Wi-Fi, casting fails), play the
briefing or announcement on the PC's own speakers instead of only logging a speaker error.

**How:** in `speaker_mcp/speaker.py`, when `say()` still fails after its one retry, play the
same gTTS audio file on Windows. WSL has no direct sound output, so the playback would go
through `powershell.exe` (for example the Windows media player), the same way Discord presence
reaches Windows through `presence/discord_relay.ps1`. Plain code only; the model isn't involved.
Log which output was used in `announce.log`, `briefings.jsonl` and `hook.jsonl`.

**Open problems:**
- The 7:30 briefing runs with nobody logged in to Windows, and a task with no one logged in
  has no sound output. The fallback would only work for the briefing if I'm already signed in;
  otherwise the overnight queue should be kept for later instead of being cleared.
- Decide whether the fallback should apply at all hours, or stay off at night like the Stop
  hook's quiet hours, so the PC doesn't start talking at 2 AM.

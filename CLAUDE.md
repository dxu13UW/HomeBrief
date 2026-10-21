# CLAUDE.md — HomeBrief (Artifact 3: AI Inside It)

## What this project is

HomeBrief is a daily scheduler that uses my Google Home speaker as its voice. Claude plans and
writes what gets said; plain code fetches data, checks Claude's output, turns text
into speech, and casts it to the speaker.

Course: Artifact 3 ("AI Inside It"). Due Sunday, October 25, 11:59 PM.
Requirement: a model does real work every time this runs, the repo keeps a log of
plans and changes (LOG.md), and the model's part stays small and clear.

## Hard constraints (do not work around these)

- **Hardware:** this computer + one Google Home speaker. No Raspberry Pi, no extra
  microphones or speakers.
- **No Claude API.** Every model call goes through Claude Code (interactive or
  headless `claude -p`). Never add the Anthropic SDK, an API key, or direct calls to
  api.anthropic.com. The API bills per call and needs instructor approval.
- **The speaker is output-only.** Its mic and wake word belong to Gemini; Google
  provides no way to route speech from it to our code. Do not build voice input.
  I talk to Gemini directly; it reads the Google Calendar that Claude writes to.
- The computer must be awake and on the same Wi-Fi as the speaker for casting.

## Architecture

```
Google Calendar ──read──▶ morning_briefing.py ──▶ claude -p ──▶ announce() ──▶ speaker
                                                      │
                          Claude Code session ────────┤ (speaker MCP server)
                          Stop hook (announce_done) ──┘
Claude ──writes tagged events──▶ Google Calendar ◀──reads── Gemini on the speaker
```

Components:
1. `speaker_mcp/` — MCP server exposing `announce(text)`. Generates speech audio,
   serves it on a local HTTP port, casts it to the speaker.
2. `morning_briefing.py` — scheduled job. Collects today's events, runs `claude -p`
   with the speaker MCP server attached, validates the result, announces it.
3. `hooks/announce_done.sh` — Claude Code Stop hook. Asks `claude -p` for a
   one-sentence summary of what was finished and announces it.

## Who is responsible for what

This split is the core of the project. Keep it true in code.

**Claude (the model) is responsible for:**
- Reading the day's events and deciding what matters (order, conflicts, gaps).
- Suggesting focus blocks and writing them to the calendar (rules below).
- Writing the spoken text: the morning briefing and one-sentence task summaries.

**Plain code is responsible for:**
- Fetching calendar data and passing it to Claude.
- Validating everything Claude produces before it is spoken or saved.
- Text-to-speech, the local HTTP server, casting, retries, and logging.
- Scheduling (cron / Task Scheduler) and the hook loop guard.

When something goes wrong, first decide which side failed: check the raw model
output in `logs/` before changing any code.

## Rules for spoken text (Claude's output)

- Plain sentences only: no markdown, bullet symbols, emoji, URLs, or code.
- Morning briefing: at most 150 words (about one minute spoken).
- Task-finished summary: one sentence, at most 25 words.
- Say times the way a person would ("ten thirty", "at noon"), with no time zones.
- Mention only events that exist in the input. Never invent events or details.
- If the day is empty, say so briefly instead of padding.

## Validation code must perform before announcing

- Reject or truncate text over the word limit.
- Strip markdown characters and URLs.
- Check that every event in the input appears in the briefing; if not, log a
  warning and append a plain list of the missing events.
- On any failure, log the raw model output and announce a short fallback message
  rather than nothing.

## Calendar write rules

- Claude may only create events whose description contains the tag `[claude]`.
- Claude may edit or delete only events carrying that tag. Never touch my own events.
- No new events before 8:00 AM or after 10:00 PM, and none overlapping existing events.
- Headless runs (`claude -p`) may create tagged events but never delete anything.
  Interactive sessions must show me the change and ask before writing.

## Hook loop guard

The Stop hook runs `claude -p`, which can trigger the Stop hook again. Before
calling `claude -p`, the hook sets `HOMEBRIEF_HOOK=1`; the hook exits
immediately if that variable is already set. Do not remove this guard.

## Configuration and secrets

- Settings live in `.env` (gitignored): speaker name, local HTTP port, time zone,
  briefing time. Keep `.env.example` up to date with placeholder values.
- Never commit tokens, OAuth credentials, or calendar exports.
- Default stack: Python 3, `pychromecast` (or `catt`) for casting, `gTTS` or the
  OS's built-in speech for TTS. Ask before adding other dependencies.

## The log (required by the assignment)

Keep `LOG.md` updated as we work. After any planning decision or meaningful change,
add an entry at the bottom:

```
## YYYY-MM-DD — short title
Plan: what we intended to do and why
Changed: what actually changed (files, behavior)
Problems: what broke, and whether it was the model or the code
Next: what comes next
```

Record dead ends too (for example, why voice input through the speaker was dropped).

## Build order

- [x] 1. Cast a test "hello" to the speaker from a plain Python script (riskiest step).
- [x] 2. Wrap casting in the speaker MCP server; register it with Claude Code; test.
- [x] 3. Calendar access for Claude Code (read events, write tagged events).
- [ ] 4. `morning_briefing.py` with validation; schedule it.
- [ ] 5. Stop hook with loop guard.
- [ ] 6. README describing the model/code split; portfolio card with reflection.

Update these checkboxes as steps are finished.

## Working style

- Keep changes small and test each one against the real speaker.
- Prefer plain code over model calls for anything deterministic.
- If a request conflicts with the constraints above, point it out instead of
  working around it.

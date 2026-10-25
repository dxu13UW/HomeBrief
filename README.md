# HomeBrief

A daily scheduler that talks through my Google Home speaker. Every morning Claude reads my
calendar, plans the day, may add focus blocks, and writes a short spoken briefing; plain code
checks what Claude wrote and plays it on the speaker. When a Claude Code session finishes a
long task, in any project, the speaker says what was done in one sentence (held until the
morning briefing if it's the middle of the night).

CS490 Artifact 3 ("AI Inside It"). Runs entirely on Claude Code (`claude -p` and MCP servers);
there is no Claude API key and no per-call billing.

## What it does

| Part | When it runs | What happens |
| --- | --- | --- |
| Morning briefing (`morning_briefing.py`) | Daily at 7:30 AM (Windows Task Scheduler) | Code fetches today's events → `claude -p` plans the day, may add focus blocks, writes the briefing → code validates it → speaker |
| Speaker MCP server (`speaker_mcp/`) | Whenever Claude Code calls `announce(text)` | Code cleans the text, makes speech with gTTS, casts it to the speaker |
| Calendar MCP server (`calendar_mcp/`) | Whenever Claude Code calls `list_events` / `create_tagged_event` | Code reads events, or checks the write rules and creates a `[claude]` event |
| Stop hook (`hooks/announce_done.sh`) | End of every Claude Code turn, in any project, that takes 60 s or more, on the scheduling machine only | `claude -p` writes one sentence about what was done → code validates it → speaker. From 11 PM until the 7:30 briefing it's queued instead, and the briefing reads out up to three after the day's plan |
| Discord presence (`presence/`) | Always, while I'm logged in to Windows on the PC | During a `[claude]` focus block, Discord shows "Playing HomeBrief", the block's title, its time span and a countdown; cleared when it ends. No model: Claude already chose the blocks |

## Focus blocks

A focus block is a calendar event with `[claude]` in its description. Claude creates them
through `create_tagged_event`: the morning briefing may add one, and I can ask for more in any
Claude Code session in this repo (on the PC, or on my MacBook when I'm away). Code enforces the
rules, whoever asks:

| Rule | Value |
| --- | --- |
| Time window | 11:30 AM to 10 PM, on one day, never overlapping another event |
| Class days | Not before an hour after the last class: Mon 6:40 PM, Tue/Thu 1:10 PM, Wed 11:50 AM |
| Per day | 1 from the morning briefing; up to 5 when I ask |
| Changes | Claude can't edit or delete events; there is no such function |

My class schedule (TCSS 372 M/W 9:30–10:50, TMATH 126 T/Th 10:10–12:10, TCSS 490 M 3:40–5:40)
is `CLASSES` in `calendar_mcp/gcal.py`, because the classes aren't on the calendar. Voice-created
events from "Hey Google" can't carry the tag, so they never count as focus blocks.

## Who is responsible for what

The model's part is kept small so that when something goes wrong I can tell which side failed.

**Claude (the model) decides and writes:**
- What matters today: order of events, overlaps, free gaps.
- Whether to add a focus block, and when (at most one per briefing; more only when I ask in a session).
- The words of the morning briefing and of the one-sentence task summaries.

The model's whole job for the briefing is in one file: [`prompts/morning_briefing.md`](prompts/morning_briefing.md).
The summary prompt is at the top of [`hooks/announce_done.py`](hooks/announce_done.py).

**Plain code does everything else, and checks the model's output:**

| Check | Where |
| --- | --- |
| Strip markdown, URLs and emoji before speaking | `speaker_mcp/speaker.py` `clean()` |
| Briefing at most 150 words, cut at a sentence end | `clean()` |
| Every calendar event is mentioned; any missing ones are appended as a plain list and logged as a warning | `morning_briefing.py` `validate()` |
| If `claude -p` fails, speak a plain list of the day's events instead of nothing | `morning_briefing.py` `fallback()` |
| Summary is one sentence, at most 25 words, no file names, paths or code words, cut at a comma if too long | `hooks/announce_done.py` `validate()` |
| Focus block rules above (time window, class days, per-day cap) | `calendar_mcp/gcal.py` `check_new_event()`, `earliest_start()` |
| Every event Claude creates is tagged `[claude]` (added by code, not trusted to the model) | `gcal.py` `create_tagged_event()` |
| Claude can't edit or delete anything: no such function exists | `gcal.py` |
| The headless briefing run has no built-in tools (`--tools ""`), only the two calendar tools | `morning_briefing.py` `run_claude()` |
| Loop guard: the hook's own `claude -p` can't trigger the hook again (`HOMEBRIEF_HOOK=1`) | `hooks/announce_done.sh` |

Code also does the fetching, text-to-speech, the local HTTP server, casting with one retry,
scheduling, and logging.

## How it fits together

```
Google Calendar ──read (code)──▶ morning_briefing.py ──events──▶ claude -p ──text──▶ validate ──▶ speaker
                                                                     │
                                                    calendar MCP ◀───┘ create_tagged_event
                                                    (rules checked in code)

Claude Code session ──Stop hook──▶ claude -p (one sentence) ──▶ validate ──▶ speaker
Claude Code session ──announce(text)──▶ speaker MCP ──▶ clean ──▶ speaker

Gemini on the speaker reads the same Google Calendar, so I can ask it about focus blocks.
```

The speaker is output only. Its microphone belongs to Gemini and Google offers no way to send
speech from it to my code, so HomeBrief has no voice input.

## When something goes wrong

Check the raw model output first, then decide which side failed:

| Log | Contains |
| --- | --- |
| `logs/briefings.jsonl` | Each briefing: the events, Claude's raw text, warnings, what was spoken, focus blocks after the run, errors |
| `logs/hook.jsonl` | Each hook run: turn length, Claude's raw sentence, what was spoken or queued, or why it was skipped |
| `logs/hook_queue.jsonl` | Sentences held overnight; the briefing plays them and deletes the file only once they're heard |
| `logs/announce.log` | Each `announce()` call: raw text, spoken text, result |
| `logs/hook.err` | Errors from the background hook worker |
| `logs/presence.log` | When presence starts and why it exits, each presence change, and errors (logged once until they change) |

If the raw text is fine but the speech is wrong, it's the code. If the raw text breaks the
rules, it's the model, and the validator should have caught it.

## Setup

Requirements: Python 3.12, Claude Code, a Google Home speaker on the same Wi-Fi, and a
computer that is awake at briefing time.

```zsh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # speaker name/IP, port, time zone, calendar, hook threshold
.venv/bin/python test_cast.py   # should say "Hello from HomeBrief." on the speaker
```

**WSL only:** the speaker has to reach the audio server running inside WSL.
1. Set `networkingMode=mirrored` under `[wsl2]` in `%USERPROFILE%\.wslconfig`, then `wsl --shutdown`.
2. Allow the audio port through the Hyper-V firewall (admin PowerShell):
   ```powershell
   New-NetFirewallHyperVRule -Name HomeBrief8765 -DisplayName "HomeBrief audio (WSL)" `
     -Direction Inbound -VMCreatorId '{40E0AC32-46A5-438A-A0B2-2B479E8F2E90}' `
     -Protocol TCP -LocalPorts 8765 -Action Allow
   ```

**Google Calendar:** create a Google Cloud project, enable the Calendar API, create a
Desktop OAuth client, save it as `credentials.json`, then run
`.venv/bin/python calendar_mcp/gcal.py --auth` and open the printed URL. Publish the app
("In production") or the login expires every 7 days. `credentials.json` and `token.json` are
gitignored.

**MCP servers and hook:** `.mcp.json` registers both servers; Claude Code asks to approve them
the first time. The paths are relative to the repo, so start `claude` from the repo folder. The
Stop hook covers every project, so it's registered in my user settings (`~/.claude/settings.json`)
as a Stop hook running `<repo>/hooks/announce_done.sh` by its full path, not in the repo.
Quiet hours run from `HOOK_QUIET_START` (default 23:00) to `BRIEFING_TIME` in `.env`.

**Two machines:** the repo is on my PC (WSL) and my MacBook, synced through GitHub (pull
before working, push after). The PC is the scheduling machine: it runs the briefing, Discord
presence and the Stop hook, and its `.env` has `HOMEBRIEF_SCHEDULER=1`. The Mac leaves that
unset, so there `morning_briefing.py` (except `--dry-run`) and `focus_presence.py` exit at once
and the Stop hook skips; I use it to create focus blocks when I'm away. Each machine has its own
gitignored `.env`, `credentials.json` and `token.json`.

**Schedule (Windows):** a Task Scheduler task runs daily at 7:30 AM with "wake the computer"
on and "Run whether user is logged on or not" (it stores the Windows password; a PIN won't
work, and if the password was changed online, sign in once with it so Windows updates its
local copy):
`wsl.exe -d Debian --cd <repo> -- .venv/bin/python morning_briefing.py`
"Wake the computer" only works from sleep. To also cover a full shutdown, my BIOS powers the
PC on at 7:15 AM (Advanced → APM → Power On By RTC).

**Discord presence (optional):** create an application at discord.com/developers, put its
Application ID in `.env` as `DISCORD_CLIENT_ID` (it isn't a secret), and add a logon task:
`conhost.exe --headless wsl.exe -d Debian --cd <repo> -- .venv/bin/python presence/focus_presence.py`.
WSL can't open the Discord client's named pipe, so `presence/discord_relay.ps1` relays the
messages through PowerShell. No extra Python packages. Others only see the status if
Discord's "Share your detected activities" is on.

## Running by hand

```zsh
.venv/bin/python morning_briefing.py --dry-run               # print, no focus blocks, no speaker
.venv/bin/python morning_briefing.py --date 2026-10-21       # real run for a given day
.venv/bin/python calendar_mcp/gcal.py 2026-10-21             # list a day's events (no model)
.venv/bin/python test_cast.py "Any text"                     # speak text (no model)
```

## Cost

Nothing is billed per call. Every model call is `claude -p` signed in with my claude.ai account
(no `ANTHROPIC_API_KEY`), so it counts toward my plan's usage limits instead of charging money.
The `cost_usd` in `logs/briefings.jsonl` (about $0.05–0.07 per briefing) is Claude Code's estimate
of what the run would cost at API prices, a rough measure of its size, not a charge. The Stop hook
uses Haiku for its one sentence to keep that small. If an API key were ever set where Claude Code
reads it, Claude Code would use it and bill it, so it stays unset.

## Design decisions

- **No voice input.** Google shut down Conversational Actions, and the speaker's mic only feeds
  Gemini, so there's no supported way to send my speech to Claude.
- **Google Calendar is the bridge to Gemini.** Claude writes to the calendar and Gemini reads it;
  Claude never prompts Gemini, since two models in a chain would hide which one failed.
- **The model returns text; code acts on it.** The briefing is validated before it's spoken, and
  every calendar rule is checked in code rather than trusted to the prompt.
- **`claude -p` and MCP only, never the Claude API**, which bills per call.
- **Discord Rich Presence, not my online status.** Changing my status or custom status from code
  would need a self-bot, which Discord bans.

`CLAUDE.md` holds the full constraints and rules every session follows. The plan, every change
and the dead ends are in [`LOG.md`](LOG.md); features not built yet are in
[`PLANS.md`](PLANS.md); the planning conversation that came before any
code is in [`docs/planning-conversation.md`](docs/planning-conversation.md).

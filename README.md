# HomeBrief

A daily scheduler that talks through my Google Home speaker. Every morning Claude reads my
calendar, plans the day, may add focus blocks, and writes a short spoken briefing; plain code
checks what Claude wrote and plays it on the speaker. When a Claude Code session finishes a
long task, the speaker says what was done in one sentence.

CS490 Artifact 3 ("AI Inside It"). Runs entirely on Claude Code (`claude -p` and MCP servers);
there is no Claude API key and no per-call billing.

## What it does

| Part | When it runs | What happens |
| --- | --- | --- |
| Morning briefing (`morning_briefing.py`) | Daily at 7:30 AM (Windows Task Scheduler) | Code fetches today's events → `claude -p` plans the day, may add focus blocks, writes the briefing → code validates it → speaker |
| Speaker MCP server (`speaker_mcp/`) | Whenever Claude Code calls `announce(text)` | Code cleans the text, makes speech with gTTS, casts it to the speaker |
| Calendar MCP server (`calendar_mcp/`) | Whenever Claude Code calls `list_events` / `create_tagged_event` | Code reads events, or checks the write rules and creates a `[claude]` event |
| Stop hook (`hooks/announce_done.sh`) | End of every Claude Code turn in this project that takes 60 s or more | `claude -p` writes one sentence about what was done → code validates it → speaker |
| Discord presence (`presence/`) | Always, while I'm logged in to Windows | During a `[claude]` focus block, Discord shows "Playing HomeBrief", the block's title, its time span and a countdown; cleared when it ends. No model: Claude already chose the blocks |

## Who is responsible for what

The model's part is kept small so that when something goes wrong I can tell which side failed.

**Claude (the model) decides and writes:**
- What matters today: order of events, overlaps, free gaps.
- Whether to add focus blocks, and when (at most two per briefing).
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
| New events only between 8 AM and 10 PM, on one day, never overlapping, at most 5 Claude events per day | `calendar_mcp/gcal.py` `check_new_event()` |
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
| `logs/hook.jsonl` | Each hook run: turn length, Claude's raw sentence, what was spoken, or why it was skipped |
| `logs/announce.log` | Each `announce()` call: raw text, spoken text, result |
| `logs/hook.err` | Errors from the background hook worker |
| `logs/presence.log` | Each Discord presence change, and errors (logged once until they change) |

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

**MCP servers and hook:** `.mcp.json` registers both servers and `.claude/settings.json`
registers the Stop hook. Claude Code asks to approve them the first time. The paths in
`.mcp.json` are relative to the repo, so start `claude` from the repo folder.

**One scheduling machine:** set `HOMEBRIEF_SCHEDULER=1` in `.env` only on the machine that
runs the scheduled briefing, Discord presence and the Stop hook (my PC). Without it,
`morning_briefing.py` (except `--dry-run`) and `focus_presence.py` exit at once and the Stop hook
skips without calling `claude -p`, so a second machine can't double up.

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

Everything goes through Claude Code. Claude Code reports about $0.05 of usage per briefing,
which is covered by the course's Claude Code access; the hook uses Haiku for its one sentence.

## Project history

**Planning first (October 18–19).** Before any code was written, I planned the project in
Claude Desktop: I asked it many questions and chose from the options it gave me. The full
conversation is in [`docs/planning-conversation.md`](docs/planning-conversation.md). The main
decisions:
- **No voice input.** Google shut down Conversational Actions, and the speaker's mic only feeds
  Gemini, so there's no supported way to send my speech to Claude.
- **Claude doesn't prompt Gemini.** Two models in a chain would make it impossible to tell which
  one failed. Instead, Google Calendar is the bridge: Claude writes to it and Gemini reads it.
- **Three shapes out of seven options:** the morning briefing (`claude -p`), the speaker MCP
  server, and the task-finished hook as an add-on. I dropped the phone-as-microphone relay
  (too many endpoints) and a "Hey Jarvis" wake-word assistant once I limited the hardware to
  just this computer and the speaker.
- **`claude -p`, never the Claude API**, which bills per call.
- **The name:** Claude suggested "Herald"; I picked HomeBrief (like Homebrew, and homebrewed).

Those decisions became `CLAUDE.md`, which existed before the first line of code and has guided
every session since: the hard constraints, the model/code split, the rules for spoken text and
calendar writes, the validation code must do, the hook loop guard, and a build order with the
riskiest step (casting to the speaker) first.

**Building (October 20 onward).** `LOG.md` records every plan, change and problem from then
on, including dead ends (voice input through the speaker, and changing my Discord online
status or custom status, which would need a banned self-bot; Rich Presence is the allowed
alternative).

# HomeBrief log

## 2026-10-20 — Plan and repo setup
Plan: Build HomeBrief for Artifact 3 using only free shapes (an MCP server, a headless
`claude -p` pipeline, a Stop hook); no Claude API. Must-haves are build steps 1, 2 and 4
(casting, MCP server, morning briefing). Calendar writes (3) and the Stop hook (5) are
optional if time runs short. If casting fails, fall back to the computer's own speakers.
Voice input through the speaker was ruled out from the start: its mic belongs to Gemini
and Google offers no way to route speech to our code.
Changed: git init; added .gitignore (keeps out .env, credentials, logs/, audio/, .venv/,
Zone.Identifier files, course docs), .env.example, requirements.txt (pychromecast, gTTS,
python-dotenv), and test_cast.py (step 1: gTTS -> local HTTP server -> cast).
Problems: Discovery found no Cast devices. Code, not model: WSL2 runs in NAT mode
(172.20.111.49) while the Wi-Fi is 192.168.0.x, so mDNS can't reach the speaker and
the speaker can't reach our HTTP server.
Next: Enable mirrored networking in WSL (networkingMode=mirrored in .wslconfig, then
`wsl --shutdown`), or run casting with Windows Python. Then rerun test_cast.py.

## 2026-10-20 — Direct connection to the speaker
Plan: Skip discovery by connecting straight to the speaker's IP (192.168.0.127, saved in .env).
Changed: .env now has SPEAKER_NAME=Bedroom speaker and SPEAKER_IP. No code changes.
Problems: Control works from WSL NAT: we connect to "Bedroom speaker" (Google Home Speaker,
volume 0.32). Playback fails with IDLE/ERROR because the speaker is told to fetch
http://172.20.111.49:8765/hello.mp3, an address only reachable inside the PC. Code/network
side, not the model.
Next: Mirrored WSL networking, so the audio server is reachable at 192.168.0.123.

## 2026-10-20 — Switch WSL to mirrored networking
Plan: Let the speaker reach the local audio server by giving WSL the PC's Wi-Fi address.
Changed: Added networkingMode=mirrored under [wsl2] in C:\Users\turtl\.wslconfig (outside
the repo). Needs `wsl --shutdown` to take effect.
Problems: None yet; untested until WSL restarts.
Next: After restart, rerun test_cast.py --discover and test_cast.py; allow Python / port
8765 through Windows Firewall on private networks if prompted.

## 2026-10-20 — Retest casting after mirrored networking
Plan: Rerun test_cast.py now that WSL uses mirrored networking.
Changed: Nothing in code. WSL now has the Wi-Fi address 192.168.0.251 (not .123 as assumed).
Problems: Still IDLE/ERROR; the speaker is told to fetch http://192.168.0.251:8765/hello.mp3
but can't reach it. Network, not model: the Hyper-V firewall for WSL blocks all inbound
traffic by default and has no rule for port 8765; the Wi-Fi profile is also "Public".
Separately, a harmless zeroconf thread traceback appears because test_cast.py stops the
discovery browser before the cast connection is done using it (code bug, now visible
because mDNS works under mirrored mode).
Next: Add an inbound Hyper-V firewall rule for TCP 8765 (admin PowerShell), rerun.
Fix the early stop_discovery() call.

## 2026-10-20 — Casting works
Plan: Allow the speaker through the WSL Hyper-V firewall and retest step 1.
Changed: Added Hyper-V firewall rule HomeBrief8765 (inbound TCP 8765 to the WSL VM, run by
hand in admin PowerShell; outside the repo). No code changes.
Problems: None. Confirmed audible on the speaker. It (192.168.0.127) fetched /hello.mp3 (HTTP 200) and playback ended
IDLE/FINISHED. The zeroconf traceback did not appear this run, so it is intermittent, but
the early stop_discovery() call is still there.
Next: Fix the early stop_discovery(), then step 2 (speaker MCP server).

## 2026-10-20 — Fix early stop of Cast discovery
Plan: Remove the intermittent "Zeroconf instance loop must be running" traceback before
reusing the casting code in the MCP server.
Changed: test_cast.py: find_speaker() now returns (cast, browser) and main() stops the
browser only after cast.disconnect(). The cast's connection thread resolves the speaker
through the browser's zeroconf instance, so stopping it early broke that lookup.
Problems: Code, not model. Three test runs after the fix all played (IDLE/FINISHED) with
no traceback; it was intermittent before, so this lowers the risk but doesn't prove it's gone.
Next: Step 2, speaker MCP server built on the same casting code.

## 2026-10-20 — Step 2: speaker MCP server
Plan: Wrap casting in an MCP server so Claude Code can call announce(text). Added the `mcp`
package (official MCP Python SDK; no API key, no billing) after asking. It installed as 2.3.0,
where FastMCP is renamed MCPServer.
Changed: speaker_mcp/speaker.py (plain code: clean() strips markdown/URLs/emoji and cuts to
150 words at a sentence end; Speaker keeps one HTTP server up, makes a unique mp3 per call,
casts with one retry, deletes the file; every call logged to logs/announce.log as raw text,
spoken text and result). speaker_mcp/server.py (MCP tool announce, stdio). .mcp.json registers
it at project scope. requirements.txt gains mcp.
Problems: None so far. Tested three ways: clean() on markdown/emoji/long input; a plain MCP
client calling announce (played, FINISHED); headless `claude -p` choosing what to say and
calling announce itself (played). Lists lose their punctuation when bullets are stripped
("Standup at ten thirty Lunch at noon"), so the model must write sentences, as the tool
description says.
Next: Both announcements confirmed audible. Step 3 (calendar access).

## 2026-10-20 — Step 3: calendar access (code written, awaiting OAuth setup)
Plan: Considered the claude.ai Google Calendar connector (works in claude -p, no setup) but
chose our own Google Calendar API access: with the connector, plain code couldn't fetch events
itself and Claude would hold edit/delete on every event, with overlap checks impossible to
enforce in code. Added google-api-python-client and google-auth-oauthlib (asked first).
Changed: calendar_mcp/gcal.py (plain code: OAuth, day_events(), check_new_event() enforcing
8 AM-10 PM, same day, no overlap; create_tagged_event() always appends [claude]; no update
or delete function exists). calendar_mcp/server.py exposes list_events and
create_tagged_event; registered in .mcp.json. .env.example gains CALENDAR_ID.
Problems: Code, found in testing: mcp 2.x hides any exception other than ToolError from the
model ("Error executing tool"), so Claude would never see why an event was rejected. Both
servers now raise ToolError with the reason. Rule checks pass offline tests (overlap,
back-to-back allowed, before 8, after 10, reversed times, UTC input).
Next: Create a Google Cloud OAuth client, run gcal.py --auth, test against the real calendar.

## 2026-10-20 — Step 3: Google login
Plan: Authorize calendar access with the OAuth client the user created.
Changed: credentials.json (renamed from the downloaded client_secret_*.json) and token.json,
both gitignored; .gitignore also covers client_secret*.json. gcal.py --auth now line-buffers
stdout so the login URL shows even when output goes to a file.
Problems: Code: the first --auth run never showed its URL (Python buffered stdout, not a
terminal) and then hit the 2-minute limit on `!` commands; running it in the background fixed
that. A second run failed with MismatchingStateError (the approval came from a different
login's link); a fresh run worked. The localhost redirect into WSL works under mirrored mode.
Reading works, but the primary calendar returned no events from 7 days back to 30 days ahead.
Next: Confirm the right Google account was used, add test events, then test focus-block creation.

## 2026-10-20 — Step 3: calendar access works
Plan: Test reads and guarded writes against the real calendar (the user's account was empty;
they added an all-day "water my cactus" on 10/21).
Changed: No code changes. With the user's approval, created "HomeBrief test focus block"
10/21 10:00-10:30 through the MCP server (tagged [claude]); the user will delete it by hand.
Problems: None. Results: list_events works through MCP and headless claude -p (it described
both events correctly in plain speech style); a 7:00 AM event was rejected; an overlapping
10:15-10:45 event was rejected with the reason "overlaps 'HomeBrief test focus block'
(10:00-10:30)"; all-day events don't block focus blocks, by design.
Next: Commit, then step 4 (morning_briefing.py with validation; schedule it).

## 2026-10-20 — Step 4: morning_briefing.py (dry runs)
Plan: Plain code fetches events, `claude -p` plans the day and writes the briefing, code
validates and speaks it. Design change from the architecture sketch: Claude returns the text
instead of calling announce() itself, because CLAUDE.md requires validation before speaking.
The headless run gets no built-in tools (--tools "") and only the calendar MCP tools.
Changed: morning_briefing.py (spoken_time(), coverage check that tolerates "my"/"your",
validate() strips markdown/URLs/emoji, cuts to 150 words, appends missing events; plain
fallback when claude fails; logs every run to logs/briefings.jsonl; --dry-run, --date;
sets HOMEBRIEF_HOOK=1 for step 5). prompts/morning_briefing.md holds the model's whole job.
gcal.py: at most 3 [claude] events per day, so repeated runs can't pile up.
Problems: Model, minor: the first dry run said "water my cactus" because the prompt said to use
titles; the prompt now says to switch "my" to "your". Otherwise the dry run for 10/21 passed
validation with no warnings (Claude Code reported $0.05 for the run). The simulated claude
failure produced the fallback list.
Next: First real run (speaker, focus blocks allowed), then scheduling.

## 2026-10-20 — Step 4: first real briefing
Plan: Full run for 10/21 with the speaker and focus blocks allowed (user approved).
Changed: Nothing in code.
Problems: None. Briefing played (passed validation, no warnings; "your cactus" now). Claude
added no focus blocks: the prompt says to skip them when the day already has a [claude]
event, and the 10:00 test block counts. That is the prompt working as written, not a failure;
to see a focus block get created, delete the test block and rerun.
Next: Schedule the daily run.

## 2026-10-20 — Step 4: scheduled
Plan: Run the briefing daily at 7:30 AM. Chose Windows Task Scheduler over cron in WSL: cron
only runs while WSL is already up, while Task Scheduler starts WSL and can wake the PC.
Changed: Windows task "HomeBrief Morning Briefing" (outside the repo): daily 7:30 AM, wake to
run, start when available if missed, 15-minute limit, runs as the user when logged on:
`wsl.exe -d Debian --cd <repo> -- .venv/bin/python morning_briefing.py`. The time lives in
the task, not .env; changing BRIEFING_TIME means updating the task.
Problems: None. Tested the exact launch path from Windows with --dry-run (exit 0; Claude
said "Good evening" and that the day was empty). Did not start the real task by hand, since
it would brief today and likely add focus blocks to tonight's empty calendar.
Next: First scheduled run tomorrow 7:30; check logs/briefings.jsonl. Then step 5 (Stop hook).

## 2026-10-20 — Discord status for focus blocks (planned, deferred)
Plan: User asked for Discord to show Do Not Disturb and a "focus block (start to end)" status
during focus blocks. Setting a user's own status or custom status from code needs the account
token (a "self-bot"), which Discord's Terms of Service ban, so that part was dropped. Agreed
alternative: Discord Rich Presence (the activity line, e.g. "Focus block 2:00 to 3:30 PM")
through the desktop client's local RPC, via pypresence and a free application ID, no token.
It must run on Windows Python because the Discord client is on Windows. Switching presence at
block start/end is deterministic, so it belongs to plain code, not the model.
Changed: Nothing yet.
Next: Optional extra after steps 5 and 6.

## 2026-10-20 — Step 5: Stop hook
Plan: Speak a one-sentence summary when a Claude Code turn finishes, without looping.
Changed: hooks/announce_done.sh (loop guard: exits if HOMEBRIEF_HOOK is set, otherwise sets
it; starts the worker in the background so the session isn't held up). hooks/announce_done.py
(plain code reads the last request and final reply from the transcript; skips turns shorter
than HOOK_MIN_SECONDS, default 60, so quick answers stay silent; asks `claude -p --model
haiku` with no tools for one sentence; validates: drops paths and file names, keeps the
first sentence of 4+ words, max 25 words; falls back to "Claude finished a task."; logs to
logs/hook.jsonl). Registered in .claude/settings.json. speaker.py now holds port 8765 only
while playing and waits if another HomeBrief process has it: the MCP server used to keep the
port open after its first announce, which would have blocked the hook and the briefing.
Problems: Model: tested mid-turn, the summary talked about the request instead of summarizing
("I'll report what the request actually asks for"); the prompt now asks for a first-person
summary and forbids commenting on instructions. Haiku also tends to write two sentences; the
code keeps the first. Code: the first validator kept only "Done!" from "Done! Committed...";
it now skips openers shorter than 4 words. Guard, short-turn skip and a finished-turn summary
all tested; the summary played on the speaker.
Next: Confirm the hook fires at the end of a real interactive turn; commit; step 6.

## 2026-10-20 — Step 5: first real hook firing, two fixes
Plan: Check the hook at the end of a real interactive turn.
Changed: announce_done.py uses the hook input's last_assistant_message (Claude Code provides
it for Stop hooks) and only falls back to the transcript. The validator now drops whole words
containing backticks, underscores, slashes or file extensions instead of squashing them.
Problems: The hook fired on time, but it said "Stopped mid-task: the reply ends before the
hook is registered or HOOKMINSECONDS is added to ." Code: when the hook ran, the transcript
didn't yet contain the final reply, so the model summarized an earlier progress note (the
model did what it was asked with the wrong input). Model, then code: the model wrote code
words despite the prompt, and the validator turned them into "HOOKMINSECONDS" and a bare
"to ." Both fixed and tested offline.
Next: Confirm a correct summary at the end of the next long turn, tick step 5, commit.

## 2026-10-20 — Step 5: clean cut for long summaries
Plan: Retest the fixed hook.
Changed: announce_done.py: a sentence over 25 words is now cut at the last comma, colon or
semicolon within the limit (plus a period) instead of mid-phrase.
Problems: The user heard the old broken sentence again, but that was a manual replay; the real
hook for that turn logged "skipped: short turn" (59 s, just under the 60 s minimum). Rerunning
the worker with the previous final reply in last_assistant_message summarized the right reply,
but the model wrote 36 words and the 25-word cut stopped mid-phrase ("...the next run has to").
Model ignored the length limit; code now handles it. Tested offline.
Next: Confirm a clean summary from a real long turn, tick step 5, commit.

## 2026-10-20 — Step 5 done
Plan: Confirm the hook on a real long turn.
Changed: Nothing in code.
Problems: None. The hook fired at the end of a real interactive turn and spoke one clean
sentence about the comma cut; the user confirmed it was what they heard.
Next: Step 6 (README with the model/code split, portfolio card with reflection). Then optional
Discord Rich Presence.

## 2026-10-20 — Step 6: README and Obsidian note
Plan: Document the model/code split, as the assignment asks ("write down exactly what the
model is responsible for and what the surrounding code checks").
Changed: README.md: what each part does, a table of every check the code performs on the
model's output (with the function that does it), architecture, which log to read when
something goes wrong, setup (WSL networking and firewall, Google OAuth, scheduling), cost.
Also wrote the Obsidian note "Artifact 3.md" (outside the repo) in the same style as Artifact 2,
with a draft reflection for the user to rewrite.
Problems: None.
Next: Push the repo to GitHub, fill in the portfolio card, submit. Optional Discord Rich Presence.

## 2026-10-20 — Record the planning phase (Oct 18-19)
Plan: The log starts on 10/20, but the project was planned on 10/18-10/19 in Claude Desktop:
the user asked it many questions and chose from the options it offered. Those decisions became
CLAUDE.md (constraints, model/code split, spoken-text and calendar rules, loop guard, build
order) before any code was written.
Changed: README.md "Project history" and the Obsidian note now describe the planning phase.
Problems: None. The Desktop chat itself isn't on this machine; details stay general until it's
exported.
Next: Export the Claude Desktop planning chat and add it to the repo.

## 2026-10-20 — Add the planning conversation
Plan: Keep the Claude Desktop planning chat in the repo as the record of how CLAUDE.md was made.
Changed: docs/planning-conversation.md (the user's exported text, converted to Markdown with
the wording unchanged; checked by diff). README "Project history" now lists the planning
decisions: no voice input, Calendar as the bridge instead of Claude prompting Gemini, options
1+3+4 chosen out of 7, claude -p instead of the API, the name. Same added to the Obsidian note,
plus a separate vault note "Artifact 3 Planning Conversation".
Problems: The export's header says October 20, but the user remembers planning on Oct 18-19;
kept Oct 18-19 and asked the user to confirm.
Next: Commit, push to GitHub, portfolio card.

## 2026-10-20 — Focus block for Discord Rich Presence
Plan: User asked to move tomorrow's focus block to 7:00-8:30 for working on Discord Rich
Presence. 7:00 AM would break the 8 AM rule, so asked; user chose 7:00-8:30 PM, moving the
10:00 test block.
Changed: Created "Focus: Discord Rich Presence" 10/21 19:00-20:30 (tagged [claude]) through
gcal.create_tagged_event. The code has no edit or delete, so the user deletes the 10:00 test
block by hand.
Problems: None.
Next: Rich Presence work during that block; it needs pypresence (ask first) and Windows Python.

## 2026-10-21 — First scheduled briefing didn't run
Plan: Check the 7:30 AM run.
Changed: Nothing.
Problems: Not the model, not the code: the PC was shut down at 12:42 AM and booted at 9:10 AM.
"Wake the computer" only works from sleep or hibernate, not from a full shutdown (wake timers
are enabled in the power plan). "Start when available" should have run the missed briefing
after boot but didn't; Task Scheduler history is turned off, so the reason isn't recorded.
The task has never run (LastTaskResult 267011).
Next: User decides: sleep instead of shutting down, and/or a logon backup trigger with a
once-a-day guard in code.

## 2026-10-21 — Power on by BIOS clock; run without a login
Plan: Make the 7:30 briefing work even after a full shutdown.
Changed: User enabled RTC power-on in the BIOS (Advanced > APM) for 7:15 AM daily (outside
the repo). Decided to switch the task to "Run whether user is logged on or not", since after
an RTC power-on Windows sits at the login screen and an "only when logged on" task never
starts. Chosen over Windows auto-login (unlocked desktop) and sleep-only.
Problems: Not yet tested. Risk: WSL may not start without a desktop session; if so, fall back
to auto-login or sleep.
Next: User sets the option and enters their Windows password in Task Scheduler; then start
the task by hand to test the non-interactive path.

## 2026-10-21 — Scheduled task works without a login
Plan: Test the task in "Run whether user is logged on or not" mode.
Changed: The task now stores the user's Windows password (LogonType Password). The PIN was
rejected, and so was the newly reset Microsoft account password at first: Windows checks a
locally cached copy of the password, which only updates after one sign-in with the password
instead of the PIN. After that, saving worked.
Problems: None. Started the task by hand at 7:33 PM: exit 0, briefing for 10/21 played and
passed validation with no warnings. WSL runs fine without a desktop session. Claude used the
current time well ("you're in it now and have about an hour left") and added no focus blocks
(two [claude] events already that day). With RTC power-on at 7:15 AM, a full shutdown no longer
stops the 7:30 briefing. If the Windows password changes, the task must be updated.
Next: Confirm the real 7:30 AM run on 10/22 after a shutdown; then step 6 (portfolio card).

## 2026-10-21 — Planning dates settled
Plan: Settle the planning dates for the README and the Obsidian note.
Changed: Nothing; both already say October 18-19. The user had been thinking the project
through since the 18th and 19th; the Claude Desktop chat itself may have been on the 20th
(as the export header says), still before any code.
Problems: None.
Next: Discord Rich Presence.

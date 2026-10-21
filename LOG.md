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

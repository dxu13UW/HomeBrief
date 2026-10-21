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

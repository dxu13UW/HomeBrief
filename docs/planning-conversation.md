# HomeBrief: Artifact 3 planning conversation with Claude

> Planning chat in Claude Desktop that produced `CLAUDE.md` before any code was written.
> Exported by the user as plain text; converted to Markdown with the wording unchanged.

Date: October 20, 2026
(Tool steps such as file creation are noted in brackets. The CLAUDE.md file itself is saved separately.)

---

### Me
For artifact 3, I was thinking I have the perfect new piece of hardware to implement AI on top of it. Specifically, I have gotten this new Google Home speaker recently and haven't been doing much with it. I think I should integrate Claude Code to make it a daily scheduler and integrate Claude to elevate it.
[Attached: Artifact 3 assignment document]

### Claude
This could make a good Artifact 3. Before you commit, there's one constraint to plan around: getting audio out to a Google Home is easy, but getting your voice in to your own code is hard.

Why voice input is the hard part. Google shut down Conversational Actions in 2023, which was the old way to say "Hey Google, talk to my app." There's no supported way anymore to route a spoken request from the speaker to a custom backend like Claude. Workarounds exist, such as Home Assistant with webhook routines or Google Home's automation script editor triggering a URL. They're fiddly, though, and you could spend most of your 8-12 hours on plumbing before Claude does anything. Google has also been moving the speakers from Assistant to Gemini, so what works may depend on your device's current software.

What works well: a one-way morning briefing. Your computer pushes audio to the speaker, and casting to a Google Home on your local network is straightforward:
1. A cron job or scheduled task runs a script each morning.
2. The script pulls your day's events from Google Calendar, plus to-dos, deadlines from Canvas, or whatever else you want.
3. It calls `claude -p` headless with that data and a prompt like: "Write a 60-second spoken briefing. Flag conflicts, suggest when to fit in focus time, and keep it conversational."
4. The script checks the output (length, no markdown, mentions every event), converts it to speech, and casts it to the speaker with something like `pychromecast` or `catt`.

This fits the assignment:
- It costs nothing extra. It's the "headless claude -p in a pipeline" shape, so it runs on the Claude Code access you already have.
- The model's part is small and clear. Claude does the judgment work; plain code does the fetching, validation, speech, and casting.
- Claude really does work every run.

If you finish early, you could add a lightweight return channel (a small web page or phone shortcut), or a midday check-in. Treat two-way voice as a stretch goal.

Practical notes: the script has to run on a machine on the same Wi-Fi as the speaker when it fires. Keep your log going from day one in a LOG.md.

---

### Me
Since the Google speaker assistant has been moved to Gemini, can Claude command the speaker by prompting the speaker's Gemini?

### Claude
Not reliably, and I'd steer you away from building on it.

Playing "Hey Google..." through the speaker itself almost certainly won't work. Smart speakers use echo cancellation to filter out their own playback. Playing it from a separate device next to the speaker sometimes works as a hack, but it breaks easily.

Sending text commands programmatically used to be possible through the Google Assistant SDK. I'm not sure whether that path still works now that the speakers run Gemini; search for current reports before relying on it. Google's developer "Home APIs" are for controlling devices from your own app, not for prompting the on-device Gemini.

Design reason to avoid it: if Claude prompts Gemini, you have two models in the chain, and you won't know whether Claude wrote a bad command or Gemini misread a good one.

Cleaner approach: let Google Calendar be the bridge. Claude writes events and reminders to your calendar through a calendar MCP server; Gemini on the speaker already reads your calendar natively.
- Claude plans.
- Your code validates.
- The speaker keeps doing what it's good at, plus the morning briefing.

If you still want to test the Gemini-command idea, timebox it to an hour and record the result in your log.

---

### Me
What's the other approaches?

### Claude
Ordered roughly from least to most setup:

1. Morning briefing cast to the speaker. A scheduled `claude -p` run writes a spoken summary; your code turns it into speech and casts it.
2. Calendar as the bridge. Claude writes time blocks into Google Calendar; Gemini reads them natively.
3. A custom MCP server for the speaker. A small Python server using `pychromecast` exposing tools like `announce(text)`. Claude decides what to say; your tool handles getting it to the speaker.
4. A Claude Code hook that announces. When Claude Code finishes a task, the hook runs `claude -p` to summarize it in one sentence and casts it to the speaker.
5. Phone as the input, speaker as the output. Dictate into a phone shortcut or bot, which triggers `claude -p` on your machine, and the speaker announces the result.
6. Your own voice assistant, with the Google Home as its speaker. A mic on your laptop or a Raspberry Pi listens for a wake word, Whisper transcribes, `claude -p` responds, and the reply is cast to the speaker.
7. Home Assistant as a hub, with its MCP server integration.

Suggestion for one week: combine 1 and 3, with 5 as a stretch goal.

---

### Me
I think 1, 3 is a good starting point, and 4 as an add-on is amazing. I don't understand 5, and I don't really like the phone to PC to Google Home speaker idea, too many endpoints.

### Claude
Dropping 5 is reasonable. It just meant using your phone as the microphone, since the speaker can't pass your voice to Claude.

How 1, 3, and 4 fit together: the MCP server (`announce(text)`) is the shared core, used by:
- Your interactive Claude Code sessions.
- The morning briefing script (`claude -p` with your MCP config).
- The hook, which summarizes finished tasks in one sentence.

Gotchas:
- Casting needs an audio file at a URL. Generate an mp3 (gTTS, Piper, or OS speech), serve it over a local HTTP server, and tell the speaker to play it. `catt` handles serving for you.
- The hook can loop. Guard with an environment variable.
- The machine must be awake and on the same Wi-Fi.
- The briefing needs calendar access (MCP server or export).

Build order, riskiest first:
1. Make the speaker say "hello" from a Python script.
2. Wrap that in an MCP server and register it with Claude Code.
3. Write the morning script with output checks, then schedule it.
4. Add the hook with the loop guard.
5. Write the README and fill in your portfolio card.

Start a LOG.md before step 1.

---

### Me
So for 5, do you mean if I'm not in range of Google Home, say I'm at a class in school, I use my phone to pass a message to Claude, then Claude hooks it to Google Home while I'm not home?

### Claude
Close, but not quite. Option 5 was mainly about input while you're at home: your phone acts as the microphone, and the reply plays on the speaker in the same room.

Your version works technically, but announcing while you're in class means the speaker talks to an empty room. The remote version that makes sense is planning ahead: you message a change, Claude updates your calendar, and it shows up when you're home. That's the calendar bridge with a phone trigger, and it has the same extra endpoints you didn't like. Leaving it out still seems right.

---

### Me
If I'm home, why should I use my phone to relay to Google Home if Google Home is built for home with big enough range to cover most of the house?

### Claude
That's the weakness of option 5. The phone was a workaround: the speaker can hear you, but it can only pass what you say to Gemini, not to Claude.

For everything else, just talk to the speaker. Claude plans, writes to your calendar, and announces through your MCP server. You talk to Gemini for everyday things: "what's next on my calendar," "set a timer," "remind me at 6." For talking to Claude by voice you'd need option 6, which is much bigger. For this week, skipping input is the right scope.

---

### Me
Number 6, I really like the idea of implementing a Claude/my-own style plugin to Google Home, like if I use a different trigger word, instead of "Hey Google," I can say "Jarvis, give me my Claude activities" and it would go through the Google Home, send the prompt to a Claude-made server, and make a Claude API call based on the speech.

### Claude
You can build something close to that, but a different device does the listening.

The Google Home can't listen for "Jarvis." Google doesn't let third-party code access the speaker's mic or change its wake word. "Jarvis" has to be heard by a mic you control (laptop, USB mic, or Raspberry Pi), and the Google Home is still the voice that answers:
1. Your mic listens for "Hey Jarvis" (openWakeWord has a pretrained "hey jarvis" model).
2. Your code records and transcribes locally with Whisper (faster-whisper).
3. The transcript goes to `claude -p` with calendar access and the speaker MCP server.
4. Claude calls `announce` and the Google Home speaks the answer.

Use `claude -p`, not a direct API call; the API bills per call and needs instructor approval.

Option 6 builds on 1 + 3. If Jarvis answers wrong, check the transcript first: right transcript means Claude misunderstood; garbled means Whisper misheard.

Expect: several seconds of latency, a listening machine that has to stay on in the room, and a feedback loop risk (pause listening while announcing).

Scope: 1 + 3 is the core; pick either 4 or 6 as the add-on.

---

### Me
Can you explain to me that chip on Google Home and other home speaker appliances that listens for a specific trigger word?

### Claude
What's listening all the time: smart speakers typically have a small, low-power processor (often a DSP or small neural accelerator) separate from the main chip. It runs a tiny neural network trained on thousands of recordings of one phrase. Its only job is to output a confidence score many times per second. That narrowness is why it can run nonstop on very little power.

What happens when it fires: audio flows into a short rolling buffer (a second or two) that keeps overwriting itself. When the score crosses a threshold, the device wakes its main processor and starts sending audio, including the buffered wake word, to the cloud, where a bigger model often double-checks it. Cheap, trigger-happy local detector plus expensive occasional checker.

Why you can't change it to "Jarvis": the model is trained by Google and built into the firmware.

Connection to your project: openWakeWord is the same kind of tiny model, running in software on your laptop.

Question: what would you trade off by running that always-on listener on your laptop's main CPU instead of a dedicated low-power chip?

---

### Me
I think I'd rather constrain hardware to just my Google Home speaker, so we'll have to abandon the idea that we have a Raspberry Pi or another speaker.

### Claude
Reasonable, and it makes the plan simpler.

Your computer stays in the system no matter what: Claude Code, the MCP server, and the morning script all run on it. Its built-in mic could technically be the Jarvis listener, but only if the laptop sits in the room, awake.

If the speaker is your only voice interface, voice input to Claude is off the table; the speaker's mic only feeds Gemini.

The setup:
- Claude to the speaker: morning briefing (1), on-demand announcements via MCP (3), task-finished announcements (4).
- You to the speaker: talk to Gemini; Claude's plan is in Google Calendar.

That's still a complete Artifact 3. Explaining in your README why voice input wasn't possible shows architectural analysis, which matches the course objectives.

---

### Me
Okay, can you draft me a CLAUDE.md that has all the persistent instructions needed for artifact 3?

### Claude
[Created CLAUDE.md, saved as a separate file]
It covers the hard constraints (only Claude Code, no API, speaker is output-only), the architecture, the split between what Claude does and what your code checks, rules for spoken text, calendar write safety rules, the hook loop guard, the LOG.md format, and the build order as a checklist.

Things to adjust: calendar hours (8 AM-10 PM assumed), spoken length limits (150 words / 25 words), and the [claude] tag that keeps Claude away from your own events. Confirm the current hook and MCP config format at docs.claude.com.

---

### Me
What should the project name be?

### Claude
Descriptive: Home Briefing, Speaker Scheduler, Morning Cast.
With personality: Herald, Town Crier, Cue.
Pick: Herald, since the system announces but doesn't listen. Avoid Jarvis (Marvel's name, and it implies a voice assistant you can talk to).

---

### Me
What about HomeBrief, like homebrew?

### Claude
I like it: short, descriptive, and the pun works two ways (Homebrew the developer tool, and "homebrewed" meaning you built it yourself). Small risk of confusion with the macOS package manager, but fine for a portfolio.
[Updated CLAUDE.md: title, description, and hook variable renamed to HOMEBRIEF_HOOK]
Portfolio subtitle idea: "HomeBrief: Claude-planned daily briefings on a Google Home speaker."

---

### Me
Question, how do I make a Claude Code session show up here in Claude desktop, or are they not synced?

### Claude
As far as I know, they're separate: Claude Code sessions don't show up as conversations in this chat, and this chat doesn't carry into Claude Code. The desktop app has Claude Code built in, but those sessions stay separate. See support.claude.com for syncing specifics.

It doesn't matter much for HomeBrief, because CLAUDE.md carries the context. Put it in the root of your homebrief repo and every Claude Code session will read it automatically. LOG.md does the same for progress.

---

### Me
Can I convert this conversation to a text file?

### Claude
[Created this file]

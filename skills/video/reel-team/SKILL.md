---
name: reel-team
description: Run a recurring short-video pipeline with a team of agents instead of one long session. Use when setting up or fixing a multi-agent reel build (a manager plus script, audio, picture, footage and assembly agents), when agents invent their own tools or drift from the owner's decisions, or when a weekly video process needs to run unattended up to a draft in the scheduler.
---

# Running a reel team

These are the rules that survived two real pipelines: a weekly news series voiced by its owner, and
a product series recorded from a live web app with [`build-reel`](../build-reel/SKILL.md). Each one
was learned by getting it wrong first. They apply to any orchestrator that hands tasks to agents.

## The shape

- One **manager** agent owns a build from start to finish. It writes the tasks, runs the checks and
  reports. It does not do the stage work.
- One agent per **stage**, in order, each handing off on the same issue or ticket:
  audio (or voiceover) → pictures and footage (these two can run together) → assembly → delivery.
- One **build per video**. If three videos are due, three builds run at once, each with its own
  instances of the agents. That only works with the folder rule below.

## Rules that hold everything up

1. **Every agent gets a tool for its mechanical work, and is told not to write another.**
   Transcribing, cutting, measuring, recording, captioning and uploading belong in a script with a
   `--help`. The agent makes the judgement calls (which take is the retake, which ad lib is the
   funniest) and passes them to the tool as a small plan file or flags. An agent left to "transcribe
   and cut the audio" spent thirty minutes reinventing silence detection, badly. Say it in the brief:
   "Do not write your own script to record, cut, caption or measure. If the tool fails, post its exact
   error and stop."
2. **One check command between stages.** `check.py <name> <stage>` prints one line per check
   (`ok` / `FAIL` with the measured value) and exits non-zero on any failure. The manager runs it and
   never takes an agent's word that something is the right length or exists. Measure what the owner
   cares about: frame size, length against the limit, the fixed opening and closing lines, and that no
   picture holds still for more than five seconds (`ffmpeg freezedetect` on the area above the captions).
3. **One folder per video, and nothing outside it.** `videos/<week>/<video>/` holds the recordings,
   transcripts, plan, voice track, locked script, pictures, clips, render and scratch files. A video's
   name (`<week>-<video>`) is the only argument most tools need. Agents working on different videos
   then cannot touch each other's files. Mirror the same split in the shared drive the owner drops
   files into.
4. **A standing-notes file the owner's decisions go into, dated, in their words.** Every agent reads
   it before every task, and it wins over the agent's own instructions. When a note changes an earlier
   decision, the manager says so. This is what stops the fifth video from repeating the first one's
   mistake.
5. **When output is off, name the one thing that is wrong.** Piling on rules makes an agent slower
   and often worse. Fix the tool or the one sentence of the brief that caused it.
6. **No approval stops inside the build; a hard stop at money and at publishing.** The run goes
   straight through to a finished file and a draft. Spending, publishing and anything outside the
   project are the owner's decisions, and the tools enforce it: the uploader can only create drafts,
   and it reads the result back to confirm the status.
7. **A brief says four things:** what is already done for you, which tool to run, what to decide,
   and exactly what to report. End with the fixed rules (keys are never opened or printed; never
   invent a fact, number or status; say plainly when a tool, file or connection is missing).
8. **Make every outward step safe to run twice.** The uploader writes the post id beside the video
   and refuses to run again. A retried task must not produce a second draft.
9. **Agents run in a bare environment.** They may have a temporary home folder and no login shell, so
   pass config paths explicitly and test a tool once with an empty environment before handing it over.

## When the owner records the voice

- Scripts are **facts only and leave nothing out**. The owner ad libs off the facts, so a missing
  fact removes material. Lead each story with what changes for the viewer, put one number in a
  sentence, and end on the strangest true fact so the ad lib has a setup. Have the script writer keep
  a coverage list: every source fact is either in the script or in an "extra context" note.
- The **locked script is what was actually said**, taken from the transcript, never the draft.
  Captions come from it, so fix transcription errors in the transcript and rebuild.
- **A retake is cut, an ad lib never is.** A retake repeats a scripted passage; an ad lib is new
  material, even when it trails off. When unsure, keep it.
- Give the owner a **spoken marker for instructions** ("video notes … end video notes"). Those spans
  are cut from the audio and passed to the picture agent as notes tied to the passage before them.
- A **length rule with an order of sacrifice**: facts, then comedy, then natural speed. The tool
  speeds the track up first (15% at most, pitch kept), then whole ad libs go, weakest first. Facts
  never go.
- Trim pauses in two tiers: tight inside scripted reading, looser around ad libs, where the pause is
  part of the timing.

## When the footage is a live app

- Record against **sample data only**, and make the recorder prove it: `app.guard` in the storyboard
  is checked before and after every take, and a take that fails is discarded.
- **Recording never writes.** No Save, Delete, Send or Generate. If a feature cannot be shown without
  writing, the agent reports that instead of recording something else.
- An old branch runs against today's database. If the "before" errors or shows nothing, make an
  after-only video and say so.

## Making it watchable

- Nothing on screen holds still for five seconds. Numbers, places and dates become short moving
  graphics (a vote bar, a map, a timeline) rather than a static source page.
- Open with each story's headline as it is named, for viewers with the sound off; show a story
  counter; mark the end of a story with one stamp and one sound.
- A host or mascot **pops up** for the intro and the ad libs. On all the time, or switching sides
  every beat, it is noise. It faces into the frame.
- Keep every label and caption inside the platform's safe zone, and keep graphics clear of the
  corner the host stands in.

## Delivery and the feedback loop

- Put every finished file for the week in **one folder with plain names** ("legislation - full
  video.mp4", "legislation - 90 second reel.mp4"), locally and in the shared drive. Working folders
  are for agents; people look in one place.
- Meta takes reels up to 90 seconds. A longer video ships twice: the full cut as a video post, and
  a reel cut made from the same render (the opening, the top one or two stories with the strongest
  ad lib, the closing). Drop the line that lists every story, and any "sources in the comments" line,
  from the reel cut. Keep the strongest ad lib even when it costs a later story.
- The scheduler facts (draft creation, media links, edits) are in
  [`social-analyst/docs/learnings.md`](../../../social-analyst/docs/learnings.md).
- A weekly **analyst** agent reads two weeks of post numbers and writes one short report the builders
  read before they start. It needs four comparable posts and three days of age before it calls
  anything a finding, it says "not enough data" when that is true, and it never overrides the
  standing notes: anything that would goes in a section addressed to the owner.

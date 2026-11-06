# Descript route reference

Sources: Descript's official MCP plugin (descriptinc/descript-mcp: skills create-video, edit-project, publish-project, export-transcript, export-timeline), Descript's API docs (help.descript.com/developers, OpenAPI v1.2), and the production notes in alexaiarchitect/descript-skills (Underlord prompt patterns and limits, verified 2026-10-29). Adapted for build-reel.

## Two ways in

| | Official MCP plugin (OAuth) | REST token (`reel descript`) |
|---|---|---|
| Install | `/plugin marketplace add descriptinc/descript-mcp` then `/plugin install descript@descript` | Descript > Settings > API tokens, put `DESCRIPT_TOKEN=...` in `.env.reel` |
| Upload | agent calls `import_media`, then `reel descript-put --urls <file>` | `reel descript` does it all |
| Underlord | `prompt_project_agent` (continues the conversation by default) | `reel descript-polish --yes` |
| Publish | `publish_project` (ask the user first) | in Descript, or MCP |
| Timeline export | `export_timeline` (EDL, FCPXML, Premiere, DaVinci Resolve, AAF, Audition) | not available over REST |

Do not add a second Descript MCP server by hand next to the plugin: duplicate servers expose every tool twice and split the sign-in.

## What `reel export` gives Descript

- One clip per beat, 1080x1920, no captions, each carrying its slice of the voiceover. Laid end to end they are the reel, frame for frame. Descript transcribes them, so the transcript is the script, and editing words edits video.
- `descript-import.json`: `project_name`, `add_media` (name, `content_type`, `file_size` per clip) and `add_compositions` (one 1080x1920 composition with the clips in order). Strip `local_path` before sending (build-reel does this).
- `underlord-prompt.md`: a caption pass in the reel's caption style, with hard rules so Underlord does not touch timing.
- Also in the package for manual work: `raw/` takes (clean browser footage at real speed, no frame or cursor), `voiceover.*`, `captions.srt`, `reel-nocaptions.mp4`, `plan.md`.

## MCP import, step by step

1. Read `out/<slug>-package/descript-import.json`. Call `import_media` with `project_name`, `add_media` (each entry: `content_type` + `file_size` only) and `add_compositions` exactly as in the file.
2. The result has `job_id`, `project_id`, `project_url` and `upload_urls`. Show the `project_url`. Write `upload_urls` to `out/<slug>-package/upload_urls.json` and run `reel descript-put STORYBOARD --urls out/<slug>-package/upload_urls.json`. Signed URLs expire after 3 hours.
3. If an upload fails, call `report_upload_status` with the `job_id`, that media's name and `status: "failed"`, wait for the job to stop, then retry. A second import into the project is rejected while the first job runs.
4. Poll `wait_for_job` (`wait_seconds: 20`) until terminal. Never re-import on a timeout; poll the same job again.
5. Optional polish: `prompt_project_agent` with the project and composition IDs and the text of `underlord-prompt.md`. Confirm with the user first: it spends AI credits. Save the `conversation_id` for follow-ups.

## Underlord rules that held up in production

- Describe the end state with exact specs (fonts, hex colors, positions, durations, media names). API runs never ask follow-up questions; they assume and finish.
- Scope line first: edit ONLY the named composition, import or delete nothing.
- State HARD RULES explicitly: keep cuts, words and runtime; no music, sound effects, transitions, layout packs or stock media unless asked. Underlord can generate music and find layout packs on its own.
- Give the spoken cue for every timecode; it catches off-by-one mistakes.
- Ask for a report back, per clip, and verify in Descript anyway: a successful job is not proof (it may cut mid-word or skip checks it was asked for).
- One complete prompt beats several small ones. Follow-ups: reuse the conversation and name exact clips and times.
- Never run two agent jobs on the same composition at once. Before the first agent edit of a valuable composition, duplicate it in Descript as a backup.

## Costs and limits

- Imports use media minutes (roughly the video length). Underlord uses AI credits; a caption pass is small, a from-scratch build is 50 to 130 credits.
- Studio Sound and filler-word removal are capped at 30 credits per file. Do not run filler-word removal on a scripted VO you want kept as recorded.
- No REST endpoint reads or edits the timeline; placement is by import order or Underlord. Rendered files leave Descript only by publishing (the job returns a `download_url`).
- YouTube URLs cannot be imported. URL imports need HTTP Range support.

---
name: craft
description: Use the Craft apps for real image and video editing work without opening a window. PhotoCraft (a Photoshop-style editor) for cut-outs, background removal, compositing, layers, masks, text on images and format conversion. FilmCraft (a Premiere-style editor) for timeline edits. Use when a picture needs a clean cut-out or a proper composite, or when asked to edit in PhotoCraft or FilmCraft.
---

# Craft apps: PhotoCraft and FilmCraft

Two open-source editors from the [ArtCraft](https://getartcraft.com) project, each with a headless
engine an agent can drive. Use them when a job needs real editing (a clean cut-out, removing a
background, layers and masks, type on an image) and your project's own scripts do not already do it.
Both must be installed on the machine; this skill installs nothing.

| App | Use it for | Headless command |
|---|---|---|
| PhotoCraft | pixels, layers, masks, cut-outs, PSD | `photocraft-cli` |
| FilmCraft | sequences, timeline, export | `filmcraft-cli` (its makers label it "in development": check every export by eye) |

## Two ways to drive an app

**1. As an MCP server.** `photocraft-cli mcp --automation-read-root DIR --automation-write-root DIR`
and `filmcraft-cli mcp` speak MCP over stdio. Give PhotoCraft the narrowest folders that work: read
the project, write only the output folder. The pattern is always the same: `doc_open` a file,
`command_list` with a `filter` to find the command and its parameters, `command_run` (or
`command_batch`) to apply it, `render_preview` to look at the result, `doc_export` to write it.
PhotoCraft's engine has about a thousand commands; never guess a command id, look it up.

**2. From the command line.**
- `photocraft-cli commands | grep -i <word>` finds an engine command.
- `photocraft-cli info FILE` prints a document as JSON (size, layers).
- `photocraft-cli convert IN OUT` converts between formats (webp, heic, png, jpg, psd, tif).
- `photocraft-cli run --help` shows how to open a file, run commands in order and save in one go.
- `filmcraft-cli commands [filter]` and `filmcraft-cli describe <id>` find a command; `inspect` shows
  the project and sequence; `import <file>...` brings media in; `run script.jsonl` runs commands in
  order; `export OUT.mp4` renders the active sequence.

Check `--help` for exact flags before the first use; they change between releases. PhotoCraft's own
MCP notes ship with it (on Linux, `/usr/share/doc/photocraft/mcp.md`).

Commands worth knowing in PhotoCraft: `layer.removeBackground` and `select.subject` (cut a person
or object out of its background), `select.inverse`, `image.trim`, `image.duplicate` (work on a copy).

## Rules

- Never edit an original in place: open it, change it, export to a new file name.
- Look at what you made. `render_preview` or view the exported file before you report it; a
  successful command is not a correct picture.
- A flat PNG or JPEG export is the deliverable; save the layered document beside it only if someone
  will need the layers again.
- If a command fails or a tool is missing, say exactly which one and fall back to the project's own
  scripts. Do not install or download anything, do not start the desktop app or its control port,
  and do not use `--bridge`.
- A real person's face is only ever their real photos. The apps may cut out, place, scale and mask
  them; they must not generate or redraw a face.
- FilmCraft has no folder limits: it can read and write anywhere your user can. Keep its work inside
  the project folder and never use `media.makeOffline` with `deleteFiles`.

"""Code beats: a diff between two branches (or a snippet) rendered as a card.

Pre-renders the whole card once; animation (added lines typing in, scroll)
is done with cheap masks at compose time.
"""
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont

from common import die, find_font, hex_rgb


def _ref(sb, name):
    if name in sb.targets:
        br = sb.targets[name].get("branch")
        if not br:
            die(f"target '{name}' has no branch to diff")
        return br
    return name


def _repo(sb, beat):
    repo = sb.resolve(beat.get("repo")) if beat.get("repo") else sb.repo
    if not repo:
        die(f"code beat '{beat['id']}' needs top-level 'repo:' (path to the git repo)")
    return repo


def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if r.returncode != 0:
        die(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def diff_rows(sb, beat):
    spec = beat["diff"]
    repo = _repo(sb, beat)
    f = spec["file"]
    a = _ref(sb, spec.get("from", "before"))
    b = spec.get("to", "after")
    ctx = str(spec.get("context", 3))
    if b == "@worktree" or (b in sb.targets and sb.targets[b].get("branch") == "@worktree"):
        out = _git(repo, "diff", f"--unified={ctx}", a, "--", f)
        b_label = "working tree"
    else:
        b = _ref(sb, b)
        out = _git(repo, "diff", f"--unified={ctx}", a, b, "--", f)
        b_label = b
    if not out.strip():
        die(f"code beat '{beat['id']}': no differences in {f} between {a} and {b_label}")
    hunks, cur = [], None
    old_no = new_no = 0
    for line in out.splitlines():
        if line.startswith("@@"):
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)", line)
            old_no, new_no = int(m.group(1)), int(m.group(2))
            cur = []
            hunks.append(cur)
            continue
        if cur is None or line.startswith("\\"):
            continue
        k = line[:1]
        text = line[1:]
        if k == "+":
            cur.append(("+", None, new_no, text))
            new_no += 1
        elif k == "-":
            cur.append(("-", old_no, None, text))
            old_no += 1
        else:
            cur.append((" ", old_no, new_no, text))
            old_no += 1
            new_no += 1
    pick = spec.get("hunks")
    if pick:
        hunks = [hunks[i - 1] for i in pick if 0 < i <= len(hunks)]
    rows = []
    for i, h in enumerate(hunks):
        if i:
            rows.append(("~", None, None, ""))
        rows.extend(h)
    maxl = int(spec.get("max_lines", 40))
    if len(rows) > maxl:
        rows = rows[:maxl]
    adds = sum(1 for r in rows if r[0] == "+")
    dels = sum(1 for r in rows if r[0] == "-")
    return rows, f, f"{a} → {b_label}", adds, dels


def snippet_rows(sb, beat):
    spec = beat["snippet"]
    f = spec["file"]
    ref = spec.get("ref", "after")
    if ref in sb.targets and sb.targets[ref].get("branch") == "@worktree":
        ref = "@worktree"
    if ref == "@worktree":
        text = (_repo(sb, beat) / f).read_text()
        label = "working tree"
    else:
        ref = _ref(sb, ref)
        text = _git(_repo(sb, beat), "show", f"{ref}:{f}")
        label = ref
    lines = text.splitlines()
    lo, hi = 1, len(lines)
    if spec.get("lines"):
        lo, hi = [int(x) for x in str(spec["lines"]).split("-")]
    hl = set()
    if spec.get("highlight"):
        for part in str(spec["highlight"]).split(","):
            a, _, b = part.partition("-")
            hl.update(range(int(a), int(b or a) + 1))
    rows = [("*" if n in hl else " ", None, n, lines[n - 1]) for n in range(lo, min(hi, len(lines)) + 1)]
    return rows, f, label, 0, 0


def build(sb, beat, k):
    """Returns dict with the rendered card body and geometry, in output pixels."""
    from pygments import lex
    from pygments.lexers import TextLexer, get_lexer_for_filename
    from pygments.styles import get_style_by_name
    from pygments.util import ClassNotFound

    rows, fname, refs, adds, dels = diff_rows(sb, beat) if beat.get("diff") else snippet_rows(sb, beat)
    style_name = beat.get("theme", "github-dark")
    try:
        style = get_style_by_name(style_name)
    except ClassNotFound:
        style = get_style_by_name("monokai")
    try:
        lexer = get_lexer_for_filename(fname, stripnl=False)
    except ClassNotFound:
        lexer = TextLexer()
    bg = hex_rgb(style.background_color or "#0d1117")
    default_fg = (230, 237, 243)

    size = int(beat.get("font_size", 26) * k)
    font = ImageFont.truetype(find_font("mono", sb.style), size)
    cw = font.getlength("M")
    lh = int(size * 1.55)
    nums = [r[2] or r[1] or 0 for r in rows]
    gutter_chars = max(3, len(str(max(nums) if nums else 0)))
    gutter = int(cw * (gutter_chars + 3))
    pad = int(28 * k)
    width = int(1000 * k)
    max_chars = int((width - gutter - pad * 1.2) / cw)

    # tokenize all rows together per side for correct lexer state
    def colorize(lines):
        out, cur = [], []
        for ttype, val in lex("\n".join(lines) + "\n", lexer):
            st = style.style_for_token(ttype)
            col = hex_rgb(st["color"]) if st.get("color") else default_fg
            parts = val.split("\n")
            for j, part in enumerate(parts):
                if part:
                    cur.append((part, col))
                if j < len(parts) - 1:
                    out.append(cur)
                    cur = []
        return out

    colored = colorize([r[3].expandtabs(4) for r in rows])
    height = pad + len(rows) * lh + pad
    img = Image.new("RGB", (width, height), bg)
    d = ImageDraw.Draw(img)
    add_bg = tuple(int(c * 0.78 + g * 0.22) for c, g in zip(bg, (46, 160, 67)))
    del_bg = tuple(int(c * 0.78 + g * 0.22) for c, g in zip(bg, (248, 81, 73)))
    hl_bg = tuple(int(c * 0.8 + g * 0.2) for c, g in zip(bg, hex_rgb(sb.style["accent"])))
    muted = (110, 118, 129)
    row_meta = []
    for i, (kind, on, nn, _t) in enumerate(rows):
        y = pad + i * lh
        rbg = {"+": add_bg, "-": del_bg, "*": hl_bg}.get(kind, bg)
        if rbg != bg:
            d.rectangle([0, y, width, y + lh], fill=rbg)
        if kind == "~":
            d.text((gutter, y + (lh - size) / 2), "⋯", font=font, fill=muted)
            row_meta.append({"kind": kind, "y": y, "chars": 0, "bg": rbg})
            continue
        num = nn if nn is not None else on
        d.text((pad * 0.5, y + (lh - size) / 2), f"{num:>{gutter_chars}}", font=font, fill=muted)
        sign = {"+": "+", "-": "−"}.get(kind, "")
        if sign:
            sc = (63, 185, 80) if kind == "+" else (248, 81, 73)
            d.text((pad * 0.5 + cw * (gutter_chars + 1), y + (lh - size) / 2), sign, font=font, fill=sc)
        x = gutter
        n = 0
        for text, col in (colored[i] if i < len(colored) else []):
            if n >= max_chars:
                break
            text = text[: max_chars - n]
            d.text((x, y + (lh - size) / 2), text, font=font, fill=col)
            x += cw * len(text)
            n += len(text)
        row_meta.append({"kind": kind, "y": y, "chars": n, "bg": rbg})
    return {"img": img, "rows": row_meta, "lh": lh, "cw": cw, "gutter": gutter, "bg": bg,
            "file": fname, "refs": refs, "adds": adds, "dels": dels, "width": width, "height": height,
            "typing": beat.get("diff") is not None and beat.get("animate", "type") == "type"}

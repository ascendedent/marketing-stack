"""Fit the storyboard to the voiceover.

Each beat covers the VO line in its `say` field. With faster-whisper
installed, the VO is transcribed with word timestamps and each beat starts
where its line starts. Without it, beats are placed by word count and snapped
to pauses found with ffmpeg silencedetect. A beat's `at:` (seconds) always wins.

Caption words keep the script's spelling (product names stay right) but take
their timing from the transcript.
"""
import difflib
import os
import re
import subprocess

from common import ffprobe_duration, info, write_json

LEAD = 0.12  # start visuals a hair before the word lands


def norm(w):
    return re.sub(r"[^a-z0-9']+", "", w.lower())


def tokens(text):
    raw = text.split()
    return [w for w in raw if norm(w)]


def transcribe(path, model_name="base.en"):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return None
    info(f"transcribing voiceover with faster-whisper ({model_name})...")

    def load(device):
        # Use the cached model without touching the network (the hub's update check
        # can hang); download only when it isn't cached yet.
        try:
            return WhisperModel(model_name, device=device, compute_type="int8", local_files_only=True)
        except Exception:
            return WhisperModel(model_name, device=device, compute_type="int8")

    def run(device):
        model = load(device)
        segs, _ = model.transcribe(str(path), word_timestamps=True, vad_filter=False,
                                   condition_on_previous_text=False)
        words = []
        for s in segs:
            for w in s.words or []:
                if norm(w.word):
                    words.append({"w": w.word.strip(), "n": norm(w.word), "s": float(w.start), "e": float(w.end)})
        return words

    # "auto" picks CUDA whenever a GPU is present, even if the CUDA 12 libraries
    # (libcublas/cudnn) are not installed; fall back to CPU instead of giving up.
    device = os.environ.get("REEL_WHISPER_DEVICE", "auto")
    try:
        return run(device)
    except Exception as e:
        if device != "cpu":
            info(f"  whisper on {device} failed ({e}); retrying on CPU")
            try:
                return run("cpu")
            except Exception as e2:
                e = e2
        info(f"  whisper failed ({e}); falling back to pause detection")
        return None


def silences(path, noise="-35dB", min_d=0.22):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
                        f"silencedetect=noise={noise}:d={min_d}", "-f", "null", "-"],
                       capture_output=True, text=True)
    out, start = [], None
    for line in r.stderr.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", line)
        if m:
            start = float(m.group(1))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            out.append((start, float(m.group(1))))
            start = None
    return out


def speech_bounds(sil, dur):
    """First and last moment of speech."""
    first, last = 0.0, dur
    if sil and sil[0][0] <= 0.05:
        first = sil[0][1]
    if sil and sil[-1][1] >= dur - 0.05:
        last = sil[-1][0]
    return first, last


def match_beats(beats, words):
    """Find each beat's first transcript word index (monotonic)."""
    seq = [w["n"] for w in words]
    idx, cursor = {}, 0
    for b in beats:
        if not b.get("say"):
            continue
        s = [norm(w) for w in tokens(b["say"])][:8]
        if not s:
            continue
        best, best_j, best_r = 0.0, None, 0.0
        for j in range(cursor, min(len(seq), cursor + 80)):
            r = difflib.SequenceMatcher(None, s, seq[j:j + len(s)]).ratio()
            score = r + (0.15 if seq[j] == s[0] else 0.0)  # prefer windows that start on the line's first word
            if score > best + 1e-6:
                best, best_j, best_r = score, j, r
            if r >= 0.999:
                break
        if best_j is not None and best_r >= 0.45:
            idx[b["id"]] = (best_j, best_r)
            cursor = best_j + 1
    return idx


def caption_words_from_transcript(beat, words, i0, i1):
    """Script spelling with transcript timing."""
    script = tokens(beat.get("caption") or beat["say"])
    sn = [norm(w) for w in script]
    tw = words[i0:i1]
    tn = [w["n"] for w in tw]
    times = [None] * len(script)
    sm = difflib.SequenceMatcher(None, sn, tn, autojunk=False)
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == "equal":
            for k in range(a1 - a0):
                times[a0 + k] = (tw[b0 + k]["s"], tw[b0 + k]["e"])
        elif tag == "replace" and b1 > b0:
            s, e = tw[b0]["s"], tw[b1 - 1]["e"]
            n = a1 - a0
            for k in range(n):
                times[a0 + k] = (s + (e - s) * k / n, s + (e - s) * (k + 1) / n)
    # interpolate gaps
    known = [i for i, t in enumerate(times) if t]
    if not known:
        return None
    for i in range(len(times)):
        if times[i]:
            continue
        prev = max([k for k in known if k < i], default=None)
        nxt = min([k for k in known if k > i], default=None)
        if prev is not None and nxt is not None:
            a, b = times[prev][1], times[nxt][0]
            span = nxt - prev
            f0, f1 = (i - prev - 0.5) / span, (i - prev + 0.5) / span
            times[i] = (a + (b - a) * max(0, f0), a + (b - a) * min(1, f1))
        elif prev is not None:
            times[i] = (times[prev][1], times[prev][1] + 0.25)
        else:
            times[i] = (max(0, times[nxt][0] - 0.25), times[nxt][0])
    return [{"w": w, "s": round(t[0], 3), "e": round(t[1], 3)} for w, t in zip(script, times)]


def spread_words(text, start, end):
    """Distribute words across [start, end] weighted by length."""
    ws = tokens(text)
    if not ws:
        return []
    weights = [len(norm(w)) + 2 for w in ws]
    total = sum(weights)
    out, t = [], start
    for w, k in zip(ws, weights):
        d = (end - start) * k / total
        out.append({"w": w, "s": round(t, 3), "e": round(t + d * 0.9, 3)})
        t += d
    return out


def align(sb, model_name=None):
    vo = sb.voiceover
    dur = ffprobe_duration(vo)
    extend = float(sb.data.get("extend", 0))
    total = dur + extend
    beats = sb.beats
    words = None if sb.data.get("whisper") is False else transcribe(vo, model_name or sb.data.get("whisper_model", "base.en"))
    sil = silences(vo)
    method = "whisper" if words else "pauses"

    starts = {}
    if words:
        found = match_beats(beats, words)
        for b in beats:
            if b["id"] in found:
                j, score = found[b["id"]]
                starts[b["id"]] = max(0.0, words[j]["s"] - LEAD)
                if score < 0.7:
                    info(f"  low-confidence match for beat '{b['id']}' ({score:.2f}); check it or set 'at'")
    else:
        # Proportional by spoken words between first and last speech, snapped to pauses.
        s0, s1 = speech_bounds(sil, dur)
        counts = [len(tokens(b.get("say", ""))) for b in beats]
        tot = sum(counts) or 1
        acc = 0
        pauses = [(a + b) / 2 for a, b in sil if a > s0 + 0.1 and b < s1 - 0.1]
        for b, c in zip(beats, counts):
            est = s0 + (s1 - s0) * acc / tot
            if c:
                near = min(pauses, key=lambda p: abs(p - est), default=None)
                if near is not None and abs(near - est) < 1.6:
                    est = near
                starts[b["id"]] = max(0.0, est)
            acc += c
    for b in beats:  # explicit `at` wins
        if b.get("at") is not None:
            starts[b["id"]] = float(b["at"])
    # first beat starts at 0; fill unknown starts by splitting gaps evenly
    ids = [b["id"] for b in beats]
    starts[ids[0]] = 0.0
    i = 0
    while i < len(ids):
        if ids[i] in starts:
            i += 1
            continue
        j = i
        while j < len(ids) and ids[j] not in starts:
            j += 1
        a = starts[ids[i - 1]]
        z = starts[ids[j]] if j < len(ids) else total
        n = j - i + 1
        for k in range(i, j):
            starts[ids[k]] = a + (z - a) * (k - i + 1) / n
        i = j
    # enforce order
    prev = 0.0
    rows = []
    for k, bid in enumerate(ids):
        s = max(starts[bid], prev + 0.3 if k else 0.0)
        starts[bid] = s
        prev = s
    for k, b in enumerate(beats):
        s = starts[b["id"]]
        e = starts[ids[k + 1]] if k + 1 < len(ids) else total
        rows.append({"id": b["id"], "type": b["type"], "start": round(s, 3), "end": round(e, 3),
                     "dur": round(e - s, 3), "say": (b.get("say") or "")[:70]})

    # caption words
    cap = []
    if words:
        bounds = []
        for k, r in enumerate(rows):
            i0 = next((n for n, w in enumerate(words) if w["s"] >= r["start"] - 0.05), len(words))
            i1 = next((n for n, w in enumerate(words) if w["s"] >= r["end"] - 0.05), len(words))
            bounds.append((i0, i1))
        for b, r, (i0, i1) in zip(beats, rows, bounds):
            if not b.get("say") or b.get("captions") is False:
                continue
            cw = caption_words_from_transcript(b, words, i0, i1)
            cap.extend(cw or spread_words(b.get("caption") or b["say"], r["start"] + LEAD, r["end"] - 0.2))
    else:
        s0, s1 = speech_bounds(sil, dur)
        for b, r in zip(beats, rows):
            if not b.get("say") or b.get("captions") is False:
                continue
            a = max(r["start"], s0) + (LEAD if r["start"] > 0 else 0)
            z = min(r["end"], s1)
            # trim trailing pause inside the beat
            for ps, pe in sil:
                if a < ps < z and pe >= z - 0.05:
                    z = ps
            cap.extend(spread_words(b.get("caption") or b["say"], a, max(a + 0.4, z)))

    result = {"method": method, "vo_duration": round(dur, 3), "total": round(total, 3),
              "beats": rows, "words": cap, "transcript": [w["w"] for w in words] if words else None}
    write_json(sb.work / "align.json", result)
    info(f"aligned {len(rows)} beats to {dur:.1f}s of voiceover ({method})")
    for r in rows:
        info(f"  {r['start']:6.2f} - {r['end']:6.2f}  ({r['dur']:4.1f}s)  {r['id']:<16} {r['say']}")
    if method == "pauses":
        info("  note: no word timestamps (install faster-whisper for exact alignment). Check the table;\n"
             "        set 'at: <seconds>' on any beat that starts in the wrong place.")
    return result

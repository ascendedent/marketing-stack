"""Branch worktrees and dev servers for before/after targets.

Each target with a `branch` gets a detached git worktree under .reel/worktrees
(so it never fights with the branch you have checked out), your untracked env
files copied in, dependencies installed, and its dev server started on its own
port. `branch: "@worktree"` uses the repo folder as is (uncommitted changes
included). A target with only a `url` is assumed to be running already.
"""
import os
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from common import die, info, read_json, write_json

DEFAULT_COPY = [".env", ".env.local", ".env.development", ".env.development.local"]


def _git(repo, *args, check=True):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        die(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r


def _wait_ready(url, timeout, proc, log):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            tail = Path(log).read_text()[-1500:] if Path(log).exists() else ""
            die(f"dev server exited early (code {proc.returncode}). Log tail:\n{tail}")
        try:
            urllib.request.urlopen(url, timeout=3)
            return True
        except urllib.error.HTTPError:
            return True  # server answered (401/404 still means it is up)
        except Exception:
            time.sleep(1)
    return False


def worktree_path(sb, name):
    return sb.work / "worktrees" / name


def up(sb, names=None):
    state = read_json(sb.work / "servers.json", {})
    for name in names or list(sb.targets):
        t = sb.target(name)
        branch = t.get("branch")
        if not branch:
            info(f"{name}: no branch, expecting it to already run at {t['url']}")
            continue
        if not sb.repo:
            die("set top-level 'repo:' to the app's git repo to run branch targets")
        if branch == "@worktree":
            cwd = sb.repo
        else:
            cwd = worktree_path(sb, name)
            if cwd.exists():
                _git(cwd, "fetch", "--quiet", check=False)
                _git(cwd, "checkout", "--quiet", "--detach", branch)
                info(f"{name}: worktree updated to {branch}")
            else:
                cwd.parent.mkdir(parents=True, exist_ok=True)
                _git(sb.repo, "worktree", "add", "--quiet", "--detach", str(cwd), branch)
                info(f"{name}: worktree for {branch} at {cwd}")
            for f in t.get("copy", DEFAULT_COPY):
                src = sb.repo / f
                if src.exists() and not (cwd / f).exists():
                    (cwd / f).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, cwd / f)
                    info(f"{name}: copied {f}")
        sub = t.get("dir")
        run_dir = cwd / sub if sub else cwd
        if t.get("install") and not (run_dir / ".reel-installed").exists() and branch != "@worktree":
            info(f"{name}: installing ({t['install']})")
            r = subprocess.run(t["install"], shell=True, cwd=run_dir)
            if r.returncode != 0:
                die(f"{name}: install failed")
            (run_dir / ".reel-installed").write_text("ok")
        prev = state.get(name)
        if prev and _alive(prev["pid"]):
            info(f"{name}: already running (pid {prev['pid']}) at {t['url']}")
            continue
        if not t.get("start"):
            die(f"target '{name}' needs a 'start' command (use {{port}} for its port)")
        cmd = t["start"].format(port=t.get("port", ""))
        log = sb.work / "logs" / f"server-{name}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        if t.get("port"):
            env["PORT"] = str(t["port"])
        env.update({k: str(v) for k, v in (t.get("env") or {}).items()})
        proc = subprocess.Popen(cmd, shell=True, cwd=run_dir, env=env, stdout=open(log, "w"),
                                stderr=subprocess.STDOUT, start_new_session=True)
        state[name] = {"pid": proc.pid, "url": t["url"], "cwd": str(run_dir)}
        write_json(sb.work / "servers.json", state)
        ready = t["url"] + t.get("ready_path", "/")
        info(f"{name}: starting `{cmd}` (log: {log.relative_to(sb.dir)})")
        if not _wait_ready(ready, int(t.get("ready_timeout", 120)), proc, log):
            die(f"{name}: not answering at {ready} after waiting. Check {log}")
        info(f"{name}: up at {t['url']}")


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def down(sb, clean=False):
    state = read_json(sb.work / "servers.json", {})
    for name, s in state.items():
        if _alive(s["pid"]):
            try:
                os.killpg(os.getpgid(s["pid"]), signal.SIGTERM)
                info(f"{name}: stopped")
            except OSError:
                pass
    write_json(sb.work / "servers.json", {})
    if clean and sb.repo:
        for name in sb.targets:
            p = worktree_path(sb, name)
            if p.exists():
                _git(sb.repo, "worktree", "remove", "--force", str(p), check=False)
                info(f"{name}: worktree removed")
        _git(sb.repo, "worktree", "prune", check=False)

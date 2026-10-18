"""Stage 2: drive manga-image-translator over the split pages, survivably.

Two failure modes have to be handled differently:

  Soft failure - one page throws inside the translator (bad detection, an OCR
  region that blows up, a translator hiccup).  ``--ignore-errors`` lets the
  worker log it and move to the next page, so the run keeps going.

  Hard failure - the worker process itself dies: CUDA OOM that poisons the
  context, a native crash in onnxruntime/opencv, the machine rebooting.
  ``--ignore-errors`` cannot catch that, so this supervisor restarts the worker.

Resume is free: the worker skips any page whose output already exists (that is
its own ``--overwrite`` logic, mode/local.py:205), so a restart picks up exactly
where the last one stopped.  Nothing already translated is ever recomputed.

The supervisor adds the part the worker cannot do for itself: if a restart makes
no progress at all, the first still-pending page is the one killing the process,
so it gets quarantined and the next restart steps over it.  That way a single
poisonous page costs one page, not the whole book.

Pages reach the worker through a queue folder of hardlinks rather than by
pointing it at work/pages directly, which keeps the split output immutable and
makes quarantining a page a matter of not linking it.

State lives in work/state.json and is rewritten after every round, so killing
this script at any moment loses at most the round in flight.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
UPSTREAM = HERE / "manga-image-translator"
VENV_PY = HERE / ".venv" / "Scripts" / "python.exe"

WORK = HERE / "work"
PAGES = WORK / "pages"
QUEUE = WORK / "queue"
OUT = WORK / "out"
LOGS = WORK / "logs"
STATE_PATH = WORK / "state.json"
LOCK_PATH = WORK / "run.lock"


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------- state


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            backup = STATE_PATH.with_suffix(".json.corrupt")
            shutil.copy2(STATE_PATH, backup)
            print(f"[warn] state.json was unreadable, kept a copy at {backup} and started fresh")
    return {"pages": {}, "rounds": [], "created": now()}


def save_state(state: dict) -> None:
    state["updated"] = now()
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)  # atomic, so a kill mid-write cannot truncate state


@contextlib.contextmanager
def exclusive_run():
    """Refuse to start while another run holds the lock.

    Two supervisors would clobber each other: they share one queue folder, which
    each rebuilds from scratch every round, and they would interleave writes to
    state.json.  O_EXCL makes the check atomic.
    """
    WORK.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        holder = ""
        with contextlib.suppress(OSError):
            holder = LOCK_PATH.read_text(encoding="utf-8").strip()
        sys.exit(f"another run is already in progress ({holder or 'unknown'})\n"
                 f"if that is stale, delete {LOCK_PATH}")
    try:
        os.write(fd, f"pid {os.getpid()} started {now()}".encode())
        os.close(fd)
        yield
    finally:
        LOCK_PATH.unlink(missing_ok=True)


def page_entry(state: dict, name: str) -> dict:
    return state["pages"].setdefault(
        name, {"status": "pending", "rounds_seen": 0, "quarantine_reason": None, "done_at": None}
    )


# --------------------------------------------------------------------------- queue


def build_queue(pending: list[str]) -> None:
    """Fill the queue folder with links to exactly the pages this round should try."""
    if QUEUE.exists():
        shutil.rmtree(QUEUE)
    QUEUE.mkdir(parents=True)
    for name in pending:
        src, dst = PAGES / name, QUEUE / name
        try:
            os.link(src, dst)          # NTFS hardlink: no copy, no extra disk
        except OSError:
            shutil.copy2(src, dst)     # different volume or no link support


# --------------------------------------------------------------------------- worker


def worker_cmd(args) -> list[str]:
    cmd = [
        str(VENV_PY), "-m", "manga_translator",
        "local",
        "-i", str(QUEUE),
        "-o", str(OUT),
        "-f", "png",
        "--config-file", str(HERE / "config.json"),
        "--model-dir", str(HERE / "models"),
        # Font is a CLI arg, not a config key; without it the renderer falls
        # back to a generic sans.
        "--font-path", str(UPSTREAM / "fonts" / args.font),
        "--attempts", str(args.attempts),
        "--ignore-errors",
    ]
    if args.verbose:
        # Writes a debug folder per page (bboxes, masks, inpaint stages) into
        # manga-image-translator/result - roughly 10 MB each, so ~4 GB over the
        # whole book. Worth it on a single page, not on a full run.
        cmd.append("--verbose")
    if args.use_gpu:
        cmd.append("--use-gpu")
    if args.dump_text_only:
        # Not an extra output: manga_translator.py:1105 dumps the translations
        # and calls exit(-1) before anything is rendered or saved.
        cmd.append("--save-text")
    return cmd


def run_worker(args, round_no: int) -> tuple[int, Path]:
    """Run one worker pass, teeing output to a per-round log. Returns (exit code, log)."""
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"round-{round_no:03d}.log"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(UPSTREAM)          # import manga_translator from the clone
    env["PYTHONUNBUFFERED"] = "1"
    env["HF_HOME"] = str(HERE / "hf-cache")    # manga-ocr + HF weights stay on D:
    env["TORCH_HOME"] = str(HERE / "models" / "torch")
    env["PYTHONIOENCODING"] = "utf-8"

    cmd = worker_cmd(args)
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write(f"# round {round_no}  started {now()}\n# cwd {UPSTREAM}\n# {' '.join(cmd)}\n\n")
        log.flush()
        proc = subprocess.Popen(
            cmd, cwd=str(UPSTREAM), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        try:
            for line in proc.stdout:
                log.write(line)
                log.flush()
                sys.stdout.write(line)
                sys.stdout.flush()
        except KeyboardInterrupt:
            proc.terminate()
            raise
        code = proc.wait()
        log.write(f"\n# exit {code} at {now()}\n")
    return code, log_path


def log_tail(log_path: Path, lines: int = 25) -> str:
    try:
        return "".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)[-lines:])
    except OSError:
        return ""


# --------------------------------------------------------------------------- supervisor


def translate(args) -> int:
    if not VENV_PY.exists():
        sys.exit(f"venv missing: {VENV_PY}\nrun setup_env.ps1 first")
    if not PAGES.exists() or not any(PAGES.glob("*.png")):
        sys.exit(f"no split pages in {PAGES}\nrun split_pages.py first")

    OUT.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    state = load_state()

    all_pages = sorted(p.name for p in PAGES.glob("*.png"))
    for name in all_pages:
        page_entry(state, name)

    # Reconcile with what is actually on disk; outputs may exist from an
    # earlier run whose state was lost.
    for name in all_pages:
        e = state["pages"][name]
        if (OUT / name).exists() and e["status"] != "done":
            e["status"] = "done"
            e["done_at"] = e["done_at"] or now()
    save_state(state)

    only = {n.strip() for n in args.only.split(",") if n.strip()} if args.only else None
    budget: set[str] | None = None
    if only:
        unknown = only - set(all_pages)
        if unknown:
            sys.exit(f"no such page(s) in {PAGES}: {', '.join(sorted(unknown))}")
        # An explicit page list means "do these", including retrying a page that
        # was quarantined or already finished. The worker skips any page whose
        # output exists, so a finished one has to have its output cleared first.
        for n in only:
            state["pages"][n].update(status="pending", quarantine_reason=None)
            (OUT / n).unlink(missing_ok=True)

    def pending_pages() -> list[str]:
        p = [n for n in all_pages if state["pages"][n]["status"] in ("pending", "failed")]
        if only:
            p = [n for n in p if n in only]
        if budget is not None:
            p = [n for n in p if n in budget]
        return p

    if args.limit:
        # Fixed once, not per round: pending shrinks as pages finish, so
        # re-slicing each round would let a run of R rounds do limit*R pages.
        budget = set(pending_pages()[: args.limit])

    started = time.time()
    stalls = 0

    for round_no in range(1, args.max_rounds + 1):
        pending = pending_pages()
        done_before = sum(1 for n in all_pages if state["pages"][n]["status"] == "done")

        if not pending:
            print(f"\nnothing pending - {done_before}/{len(all_pages)} pages done")
            break

        print(f"\n{'=' * 70}\nround {round_no}: {len(pending)} pending, "
              f"{done_before} done, "
              f"{sum(1 for n in all_pages if state['pages'][n]['status'] == 'quarantined')} quarantined"
              f"\n{'=' * 70}")

        for n in pending:
            state["pages"][n]["rounds_seen"] += 1
        build_queue(pending)
        save_state(state)

        code, log_path = run_worker(args, round_no)

        newly_done = []
        for name in pending:
            if (OUT / name).exists():
                state["pages"][name]["status"] = "done"
                state["pages"][name]["done_at"] = now()
                newly_done.append(name)

        state["rounds"].append({
            "round": round_no, "at": now(), "exit_code": code,
            "attempted": len(pending), "completed": len(newly_done),
            "log": log_path.name,
        })

        if newly_done:
            stalls = 0
            print(f"\nround {round_no}: +{len(newly_done)} pages (exit {code})")
        else:
            stalls += 1
            victim = pending[0]
            tail = log_tail(log_path)
            print(f"\nround {round_no}: no progress (exit {code}, stall {stalls})")
            if stalls >= args.stall_tolerance:
                state["pages"][victim].update(
                    status="quarantined",
                    quarantine_reason=f"no progress across {stalls} rounds; worker exit {code}",
                    quarantine_log=log_path.name,
                    quarantine_log_tail=tail,
                )
                print(f"quarantined {victim} - it is blocking the queue; see {log_path}")
                stalls = 0
            else:
                state["pages"][victim]["last_exit_code"] = code

        save_state(state)

    scope = sorted(only or budget) if (only or budget) else all_pages
    done = sum(1 for n in scope if state["pages"][n]["status"] == "done")
    quarantined = [n for n in scope if state["pages"][n]["status"] == "quarantined"]
    left = [n for n in scope if state["pages"][n]["status"] in ("pending", "failed")]

    if QUEUE.exists():
        shutil.rmtree(QUEUE, ignore_errors=True)
    save_state(state)

    mins = (time.time() - started) / 60
    print(f"\n{'=' * 70}")
    print(f"translated  : {done}/{len(scope)}")
    print(f"quarantined : {len(quarantined)}" + (f"  {', '.join(quarantined)}" if quarantined else ""))
    print(f"still open  : {len(left)}" + (f"  {', '.join(left[:10])}" if left else ""))
    print(f"elapsed     : {mins:.1f} min")
    print(f"logs        : {LOGS}")
    print(f"state       : {STATE_PATH}")
    if left:
        print("\nre-run this command to keep going; finished pages are not redone")
    return 0 if not left else 1


# --------------------------------------------------------------------------- cli


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=0,
                    help="only work on the first N pending pages; for smoke tests (default: all)")
    ap.add_argument("--only", default="",
                    help="comma-separated page names to (re)do, e.g. 0009.png,0010.png. "
                         "Clears their existing output first, so it also retries "
                         "quarantined or already-finished pages.")
    ap.add_argument("--attempts", type=int, default=2,
                    help="retries the worker makes on a page before giving up on it (default 2)")
    ap.add_argument("--max-rounds", type=int, default=40,
                    help="worker restarts the supervisor will perform (default 40)")
    ap.add_argument("--stall-tolerance", type=int, default=2,
                    help="rounds with zero progress before the blocking page is quarantined (default 2)")
    ap.add_argument("--verbose", action="store_true",
                    help="have the worker dump per-page debug images (bboxes, masks, "
                         "inpaint stages); ~10 MB per page, use on single pages only")
    ap.add_argument("--font", default="anime_ace.ttf",
                    help="font file from manga-image-translator/fonts (default anime_ace.ttf)")
    ap.add_argument("--cpu", dest="use_gpu", action="store_false",
                    help="run on CPU instead of CUDA")
    ap.add_argument("--dump-text-only", action="store_true",
                    help="pass --save-text: writes the translations as JSON and exits "
                         "without rendering any image. Produces no translated pages.")
    ap.set_defaults(use_gpu=True)
    args = ap.parse_args()

    with exclusive_run():
        sys.exit(translate(args))


if __name__ == "__main__":
    main()

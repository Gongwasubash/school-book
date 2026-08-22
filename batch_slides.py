"""Batch generate NotebookLM slide decks for every chapter of a textbook and
upload them to Google Drive.

Usage:
  python batch_slides.py --book "Class 10 Science.pdf" --class 10 --start 0

Requires:
  - `notebooklm` CLI installed (uv tool install "notebooklm-py[browser]") and logged in
  - Project venv with google-api-python-client (for Drive upload)
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = r"E:\rag sys\medical-chatbot-refactored"
TEXTBOOK_ROOT = r"E:\class  1 to 10 book\Nepal Textbooks Grade 1-10"
PROJECT_VENV_PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
TEMP_DIR = r"C:\Users\acer\AppData\Local\Temp\opencode\batch_slides"
STATE_FILE = os.path.join(TEMP_DIR, "state.json")
NOTEBLM = "notebooklm"

DRIVE_SCRIPT = os.path.join(TEMP_DIR, "drive_upload.py")

# NotebookLM rate limiting: generous sleeps between API operations
SLEEP_AFTER_CREATE = 15
SLEEP_AFTER_SOURCE = 15
SLEEP_AFTER_GENERATE = 20
RETRY_WAIT = 45
MAX_RETRIES = 5


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(cmd, timeout=300, capture=True):
    r = subprocess.run(cmd, capture_output=capture, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    return r


def run_json(cmd, timeout=300):
    for attempt in range(1, MAX_RETRIES + 1):
        r = run(cmd, timeout=timeout)
        out = (r.stdout or "").strip()
        if r.returncode != 0 or not out:
            err = (r.stderr or r.stdout or "")[-300:]
            if "RATE_LIMIT" in (r.stderr or "") or "Rate limited" in (r.stdout or ""):
                log(f"  rate limited, waiting {RETRY_WAIT * attempt}s...")
                time.sleep(RETRY_WAIT * attempt)
                continue
            log(f"  cmd failed rc={r.returncode}: {cmd} :: {err}")
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            pass
        log(f"  bad JSON output, retrying...")
        time.sleep(RETRY_WAIT)
    return None


def extract_chapter_text(book_path, chapter, out_path):
    code = (
        "import sys, json;"
        "sys.path.insert(0, r'%s');"
        "from textbook_indexer import load_chapter;"
        "docs = load_chapter(r'%s', %s);"
        "text = chr(10).join(d.page_content for d in docs);"
        "open(r'%s', 'w', encoding='utf-8').write(text);"
        "print(len(text))"
    ) % (ROOT, book_path, json.dumps(chapter), out_path)
    r = run([PROJECT_VENV_PY, "-c", code], timeout=300)
    if r.returncode != 0:
        log(f"  extract failed: {r.stderr[-300:]}")
        return False
    return True


def upload_to_drive(filepath, folder_path, drive_root="AI Books Slides"):
    code = (
        "import sys; sys.path.insert(0, r'%s');"
        "import drive_upload;"
        "creds = drive_upload.get_creds();"
        "r = drive_upload.upload_file(creds, r'%s', folder_path=%s, drive_root=%s);"
        "print(r.get('webViewLink',''))"
    ) % (TEMP_DIR, filepath, json.dumps(folder_path), json.dumps(drive_root))
    r = run([PROJECT_VENV_PY, "-c", code], timeout=300)
    if r.returncode != 0:
        log(f"  upload failed: {r.stderr[-300:]}")
        return None
    out = (r.stdout or "").strip()
    return out.splitlines()[-1] if out else None


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"completed": [], "notebooks": {}}


def save_state(state):
    os.makedirs(TEMP_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def make_safe(name):
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()[:80]


def process_chapter(book_path, idx, chapter, drive_folder, state):
    title = chapter["title"]
    safe_title = make_safe(title)
    log(f"[{idx + 1}] Chapter: {title}")

    nb_id = state["notebooks"].get(str(idx))
    if not nb_id:
        log(f"  creating notebook...")
        res = run_json([NOTEBLM, "create", f"Ch{idx + 1} - {title}", "--json"])
        if not res or "notebook" not in res:
            log("  notebook create failed")
            return False
        nb_id = res["notebook"]["id"]
        state["notebooks"][str(idx)] = nb_id
        save_state(state)
        time.sleep(SLEEP_AFTER_CREATE)
    else:
        log(f"  reusing notebook {nb_id}")

    txt_path = os.path.join(TEMP_DIR, f"ch{idx + 1}.txt")
    if not extract_chapter_text(book_path, chapter, txt_path):
        return False

    log(f"  adding source...")
    res = run_json([NOTEBLM, "source", "add", "--type", "text",
                    "--title", f"Chapter {idx + 1} - {title}",
                    "-n", nb_id, txt_path, "--json"], timeout=120)
    if not res or "source" not in res:
        log("  source add failed")
        return False
    time.sleep(SLEEP_AFTER_SOURCE)

    out_pptx = os.path.join(TEMP_DIR, f"ch{idx + 1}.pptx")
    if not os.path.exists(out_pptx) or os.path.getsize(out_pptx) == 0:
        log(f"  generating slide deck (this can take several minutes)...")
        ok = False
        for attempt in range(1, MAX_RETRIES + 1):
            r = run([NOTEBLM, "generate", "slide-deck", "-n", nb_id,
                     "--wait", "--timeout", "300", "--json"], timeout=360)
            if r.returncode == 0:
                chk = run([NOTEBLM, "download", "slide-deck", "-n", nb_id, "--all", "--dry-run", "--json"], timeout=60)
                if chk.returncode == 0 and '"count"' in (chk.stdout or "") and '"count": 0' not in (chk.stdout or ""):
                    ok = True
                    break
            if "rate" in ((r.stderr or "") + (r.stdout or "")).lower() or r.returncode != 0:
                log(f"  generate attempt {attempt} failed/rate-limited, waiting {RETRY_WAIT * attempt}s...")
                time.sleep(RETRY_WAIT * attempt)
            else:
                time.sleep(10)
        if not ok:
            log("  giving up on this chapter after retries")
            return False
        time.sleep(SLEEP_AFTER_GENERATE)

        dl = run([NOTEBLM, "download", "slide-deck", "-n", nb_id, "--latest", "--format", "pptx",
                  "--force", out_pptx], timeout=180)
        if dl.returncode != 0 or not os.path.exists(out_pptx) or os.path.getsize(out_pptx) == 0:
            log("  download failed")
            return False
    else:
        log(f"  reusing downloaded pptx ({os.path.getsize(out_pptx)} bytes)")

    log(f"  uploading to Drive...")
    link = upload_to_drive(out_pptx, f"{drive_folder}/Chapter {idx + 1} - {safe_title}")
    if link:
        state["completed"].append({"idx": idx, "title": title, "link": link, "notebook": nb_id})
        save_state(state)
        log(f"  done -> {link}")
        return True
    log("  upload failed")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", default="Class 10 Science.pdf")
    ap.add_argument("--class", dest="cls", type=int, default=10)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--max-chapters", type=int, default=1000)
    ap.add_argument("--book-dir", default=TEXTBOOK_ROOT)
    args = ap.parse_args()

    os.makedirs(TEMP_DIR, exist_ok=True)
    if not os.path.exists(DRIVE_SCRIPT):
        import shutil
        src = os.path.join(r"C:\Users\acer\AppData\Local\Temp\opencode", "drive_upload.py")
        shutil.copy(src, DRIVE_SCRIPT)

    sys.path.insert(0, ROOT)
    from textbook_indexer import get_chapters

    book_dir = os.path.join(args.book_dir, f"Class {args.cls}")
    book_path = os.path.join(book_dir, args.book)
    if not os.path.exists(book_path):
        log(f"Book not found: {book_path}")
        sys.exit(1)

    chapters = get_chapters(book_path)
    log(f"{len(chapters)} chapters detected in {args.book}")

    state = load_state()
    drive_folder = f"Class {args.cls}/{make_safe(args.book.replace('.pdf', ''))}"
    completed = {c["idx"] for c in state["completed"]}

    for idx in range(args.start, min(len(chapters), args.start + args.max_chapters)):
        if idx in completed:
            log(f"[{idx + 1}] already done, skipping")
            continue
        process_chapter(book_path, idx, chapters[idx], drive_folder, state)

    log("Batch complete.")
    log(f"Total completed: {len(state['completed'])}")
    for c in state["completed"]:
        log(f"  {c['title']} -> {c['link']}")


if __name__ == "__main__":
    main()
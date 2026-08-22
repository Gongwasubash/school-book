import concurrent.futures
import difflib
import hashlib
import json
import os
import re
from collections import Counter

import pymupdf
from langchain_core.documents import Document

from nepali_font_loader import convert_span, font_to_mode, looks_legacy


CACHE_DIR = "chapter_cache"

NEPALI_DIGITS = "०१२३४५६७८९"
ROMAN_NUMERAL_RE = re.compile(
    r"^(?=[MDCLXVI])M{0,4}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$", re.I
)

# ---- front matter / chapter-marker helpers (used by detect_chapters) ----

_CTRL_RE = re.compile(r"[\x00-\x1f]")

_TOC_RE = re.compile(r"विषयसूची|table\s*of\s*contents|\bcontents\b", re.I)

# Some CDC books title the contents page "विषयवस्तु" (subject matter) instead of
# "विषयसूची". That word also appears in ordinary body text, so it is only treated
# as a TOC when it is the standalone first line of the page.
_TOC_HEADING_RE = re.compile(r"^\s*(?:विषयसूची|विषयवस्तु)\s*$")


def _looks_like_toc(text):
    """True when a page is a table of contents.

    Accepts the standard "विषयसूची"/"table of contents"/"contents" markers, plus
    CDC books whose contents heading is "विषयवस्तु" — but only when that heading is
    the page's first content line and the page lists unit/lesson entries.
    """
    if _TOC_RE.search(text or ""):
        return True
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if not lines:
        return False
    if not _TOC_HEADING_RE.match(lines[0]):
        return False
    rest = "\n".join(lines[1:])
    if "क्र" in rest and "पृष्ठ" in rest:
        return True
    if _TOC_ENTRY_RE.search(rest):
        return True
    return bool(re.search(r"(एकाइ|unit|पाठ|lesson|chapter)", rest, re.I))

_FRONT_WORDS = (
    "पाठ्यक्रम विकास केन्द्र",
    "सानोठिमी",
    "भक्तपुर",
    "शिक्षा मन्त्रालय",
    "प्रस्तावना",
    "हाम्रो भनाइ",
    "कृतज्ञता",
    "प्रकाशक",
    "कपीराइट",
    "©",
    "acknowledg",
    "preface",
    "foreword",
    "copyright",
    "nepal government",
    "ministry of education",
    "curriculum development centre",
)


def _norm(text):
    """Strip digits, whitespace and control chars so front-matter words still
    match even when the PDF contains OCR noise like 'पा७्यक्रम' or '\\x03'."""
    return _CTRL_RE.sub("", re.sub(r"[0-9०-९\s]", "", text or ""))


_FRONT_RE = re.compile("|".join(re.escape(_norm(w)) for w in _FRONT_WORDS), re.I)

_CHAPTER_START_RE = re.compile(
    r"^\s*(?:unit|chapter|lesson|एकाइ|पाठ|अध्याय|section)", re.I
)

# a lone marker word on a line (optionally followed by a number word), e.g.
# "एकाइ" / "Unit" / "एकाइ पाँच" / "Lesson Five" — but NOT "पाठमा" / "पाठ्यक्रम".
_BARE_MARKER_RE = re.compile(
    r"^\s*(?:unit|chapter|lesson|एकाइ|पाठ|अध्याय|section)\s*"
    r"(?:(?:one|two|three|four|five|six|seven|eight|nine|ten|"
    r"एक|दुई|दुइ|तीन|चार|पाँच|पाच|छ|सात|आठ|नौ|दश)\b\s*)?[.\-–:]*$",
    re.I,
)

_CHAPTER_NUM_RE = re.compile(
    r"^\s*(?:unit|chapter|lesson|एकाइ|पाठ|अध्याय|section)\s*[0-9०-९]+", re.I
)

_TOC_ENTRY_RE = re.compile(
    r"^\s*(?:पाठ|एकाइ|unit|lesson|chapter|section)\s*[0-9०-९]+", re.I
)

_CHAPTER_SECTION_RE = re.compile(r"^\s*\d+\.\d+\s*\S", re.I)

_INTRO_MARKER_RE = re.compile(r"^\s*(\d{1,2})\.\d+\s+Introduction\b", re.I)

_TOC_NUM_ENTRY_RE = re.compile(r"^\s*\d+[.)]\s*\S")


def _chapter_start(text):
    return bool(_CHAPTER_START_RE.search(_CTRL_RE.sub("", text or "")))


def _marker_key(title):
    m = _CHAPTER_NUM_RE.search(title or "")
    return re.sub(r"\s+", "", m.group(0)) if m else re.sub(r"\s+", "", title or "")


def _parse_toc_lesson_names(toc_texts):
    """Extract {lesson_number: name} from table-of-contents pages.

    Handles "3. Linear Programming 26-35" and "3.\\nLinear Programming\\n26-35"
    layouts. Only pages that look like a TOC (contain contents/lesson/unit
    keywords) are scanned, so prefaces with stray "1." lines are ignored.
    """
    names = {}
    for text in toc_texts:
        if not re.search(r"\bcontents\b|विषयसूची|lesson|पाठ|एकाइ|unit", text or "", re.I):
            continue
        lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
        for idx, ln in enumerate(lines):
            a = _deva_digits_to_ascii(ln)
            m = re.match(r"^(\d{1,2})\s*[.)]\s*$", a)
            if m:
                nxt = lines[idx + 1] if idx + 1 < len(lines) else ""
                if re.match(r"^[0-9०-९\s\-–—]+$", nxt):
                    continue  # page-range line, not a title
                if nxt and len(nxt) < 45:
                    names[int(m.group(1))] = _clean_deva_title(nxt)
                continue
            m2 = re.match(
                r"^(\d{1,2})[.)]\s+(.+?)\s+(\d+\s*[–—-]\s*\d+|\d+)\s*$", a
            )
            if m2:
                nm = _clean_deva_title(m2.group(2)).strip()
                if nm and len(nm) < 45:
                    names[int(m2.group(1))] = nm
    return names


def _page_title_line(text, marker):
    """First title-like line on a page (used when a section/unit opener page
    does not contain a heading-size desc, e.g. Optional English sections whose
    names are printed at body size)."""
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln or _CTRL_RE.sub("", ln) == "":
            continue
        if ln == marker:
            continue
        if re.match(r"^[0-9०-९\-–.,]+$", ln):
            continue
        if re.match(r"^[a-zA-Z०-९\d][.)]\s*$", ln):
            continue
        if re.search(
            r"grade\s*-?\s*\d+|कक्षा\s*[०-९\dA-Za-z\u0900-\u097F]{1,2}|sIff\s*[!@#$%^&*()०-९\d]+",
            ln,
            re.I,
        ):
            continue
        if re.match(r"^(this|in|the|it|that|a|an|section|unit|lesson)\b", ln, re.I) and len(ln) > 40:
            continue
        if len(ln) > 60 or len(ln) < 3:
            continue
        if _CHAPTER_NUM_RE.match(ln) or _BARE_MARKER_RE.match(ln) or _CHAPTER_SECTION_RE.match(ln):
            continue
        return _clean_title(ln)
    return None


_NUM_WORDS = {
    "एक": "१", "दुई": "२", "दुइ": "२", "तीन": "३", "चार": "४",
    "पाँच": "५", "पाच": "५", "छ": "६", "सात": "७", "आठ": "८",
    "नौ": "९", "दश": "१०",
}


def _num_word_digit(text):
    """Return Devanagari digit for a heading that is a number word (एक, दुई...)."""
    t = _CTRL_RE.sub("", text or "")
    t = re.sub(r"[^\u0900-\u097F]", "", t)  # strip OCR noise (quotes etc.)
    return _NUM_WORDS.get(t)


_STANDALONE_DIGIT_RE = re.compile(r"^\s*[0-9०-९]{1,2}\s*$")


def _marker_with_number(page_text, marker):
    """Some PDFs print the unit number on its own line right after the marker
    word ("एकाइ\\n२"). Attach that number so the marker becomes "एकाइ २";
    otherwise every unit collapses onto the same dedup key and is dropped."""
    if _CHAPTER_NUM_RE.search(marker):
        return marker
    lines = [l.strip() for l in (page_text or "").splitlines() if l.strip()]
    for j, ln in enumerate(lines):
        if ln != marker:
            continue
        for k in (j + 1, j + 2):
            if k < len(lines) and _STANDALONE_DIGIT_RE.match(lines[k]):
                return f"{marker} {lines[k]}"
    return marker


def scan_library(root):
    books = []
    if not root or not os.path.isdir(root):
        return books
    for cls_dir in sorted(os.listdir(root)):
        cls_path = os.path.join(root, cls_dir)
        if not os.path.isdir(cls_path):
            continue
        m = re.match(r"^Class\s+(\d+)$", cls_dir, re.I)
        if not m:
            continue
        cls_num = int(m.group(1))
        # Check for PDF files
        for f in sorted(os.listdir(cls_path)):
            if f.lower().endswith(".pdf"):
                full = os.path.join(cls_path, f)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                books.append({"class": cls_num, "file": f, "path": full, "size": size})
        # Check for MD files in a "markdown" subfolder
        md_sub = os.path.join(cls_path, "markdown")
        if os.path.isdir(md_sub):
            for f in sorted(os.listdir(md_sub)):
                if f.lower().endswith(".md"):
                    full = os.path.join(md_sub, f)
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = 0
                    books.append({"class": cls_num, "file": f, "path": full, "size": size})
    books.sort(key=lambda b: (b["class"], b["file"]))
    return books


def _convert_span(text, font_name):
    return convert_span(text, font_name)


def _looks_numeric(text):
    t = text.strip().replace(".", "").replace(",", "").replace(" ", "")
    if t.isdigit():
        return True
    if t and all(c in NEPALI_DIGITS for c in t):
        return True
    return bool(ROMAN_NUMERAL_RE.match(text.strip()))


def _clean_title(text):
    t = _CTRL_RE.sub("", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    t = t.strip(" \t\r\n-–—.:|")
    return t or "Untitled"


_FORMULA_RE = re.compile(r"[=+\-×÷]|^\(?\d[\d.)]*\s*$|\(\s*\)")


def _looks_like_formula(title):
    if _FORMULA_RE.search(title):
        return True
    letters = sum(c.isalpha() or 0x0900 <= ord(c) <= 0x097F for c in title)
    return letters == 0


def _estimate_body_size(doc, sample_pages=80):
    counts = Counter()
    n = doc.page_count
    step = max(1, n // sample_pages)
    for i in range(0, n, step):
        try:
            dd = doc[i].get_text("dict")
        except Exception:
            continue
        for b in dd.get("blocks", []):
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    size = round(s.get("size", 0) * 2) / 2
                    if size > 0:
                        counts[size] += len(s.get("text", ""))
    if not counts:
        return 14.0
    return counts.most_common(1)[0][0]


def _page_heading_candidates(doc, page_index, body_size, threshold_mult=1.2):
    page = doc[page_index]
    dd = page.get_text("dict")
    ph = page.rect.height
    threshold = max(body_size * threshold_mult, body_size + 4)
    candidates = []
    for b in dd.get("blocks", []):
        for l in b.get("lines", []):
            spans = l.get("spans", [])
            if not spans:
                continue
            max_size = max(s.get("size", 0) for s in spans)
            if max_size < threshold:
                continue
            text = "".join(_convert_span(s.get("text", ""), s.get("font", "")) for s in spans).strip()
            if len(text) < 3 or _looks_numeric(text) or _looks_like_formula(text):
                continue
            y0 = l.get("bbox", [0, 0, 0, 0])[1]
            if y0 > 0.9 * ph:
                continue
            candidates.append((_clean_title(text), max_size, y0))
    return candidates


def detect_chapters(pdf_path):
    """Detect real chapters, skipping front matter (cover, preface, TOC).

    A chapter boundary is a page whose dominant heading looks like a chapter
    start: "Unit 1", "पाठ १", "Lesson 1", "एकाइ २", "Chapter 3", "अध्याय २"
    or a similarly large standalone heading on a sparse page. Everything
    before the first real chapter (cover / preface / table of contents) is
    dropped so chapter lists always begin at the actual chapter 1.
    """
    with pymupdf.open(pdf_path) as doc:
        n = doc.page_count
        body = _estimate_body_size(doc)
        page_texts = []
        cands = []
        for i in range(n):
            page_texts.append(_page_text(doc, i))
            for text, size, y0 in _page_heading_candidates(doc, i, body):
                cands.append((i, text, size, y0))

        # drop running headers/footers repeated across the book
        title_count = Counter(t for _, t, _, _ in cands)
        running = {t for t, c in title_count.items() if c > max(2, int(n * 0.15))}
        cands = [(p, t, s, y) for p, t, s, y in cands if t not in running]

        cands_by_page = {}
        for p, t, s, y in cands:
            cands_by_page.setdefault(p, []).append((t, s, y))

        def _front(i):
            # front matter (cover / preface / TOC) only occurs in the opening pages
            if i > max(5, int(n * 0.12)):
                return False
            t = page_texts[i] or ""
            if _looks_like_toc(t):
                return True
            if i > 5:
                return False
            return bool(_FRONT_RE.search(_norm(t)))

        def _toc_continuation(i):
            # pages continuing the table of contents: dense lists of entries
            lines = [l.strip() for l in page_texts[i].splitlines() if l.strip()]
            if len(lines) < 12:
                return False
            entries = sum(1 for l in lines if _TOC_ENTRY_RE.search(l))
            numbered = sum(1 for l in lines if _TOC_NUM_ENTRY_RE.match(l))
            return entries >= 2 or (entries >= 1 and numbered >= 3)

        # body starts after all front matter (incl. multi-page TOC)
        front_last = -1
        for i in range(n):
            if _front(i):
                front_last = i
        j = front_last + 1
        while j < n and _toc_continuation(j):
            front_last = j
            j += 1
        body_start = front_last + 1

        def _find_marker(i):
            for t, s, y in cands_by_page.get(i, []):
                if _chapter_start(t):
                    return t
            return None




def _page_text(doc, page_index):
    page = doc[page_index]
    dd = page.get_text("dict")
    page_lines = []
    for b in dd.get("blocks", []):
        for l in b.get("lines", []):
            line_parts = []
            for s in l.get("spans", []):
                line_parts.append(_convert_span(s.get("text", ""), s.get("font", "")))
            page_lines.append("".join(line_parts))
    return "\n".join(page_lines)


def load_chapter(pdf_path, chapter, chapter_title=None):
    docs = []
    title = (chapter_title or chapter.get("title", "Untitled")).strip()
    ocr_texts = None
    with pymupdf.open(pdf_path) as doc:
        end = min(chapter.get("end", doc.page_count - 1), doc.page_count - 1)
        for i in range(chapter.get("start", 0), end + 1):
            content = _page_text(doc, i)
            if not content.strip():
                if ocr_texts is None:
                    ocr_texts = _ocr_texts(pdf_path)
                if ocr_texts and i < len(ocr_texts):
                    content = ocr_texts[i]
            if content.strip():
                docs.append(
                    Document(
                        page_content=content,
                        metadata={
                            "source": pdf_path,
                            "page": i,
                            "chapter": title,
                        },
                    )
                )
    return docs


# -------------------------- Markdown file support --------------------------

_MD_CHAPTER_RE = re.compile(r"^##\s+(.+?)(?:\s+\(Pages?\s+(\d+)-(\d+)\))?\s*$", re.I)


def parse_md_chapters(md_path):
    """Parse ## headers from a markdown file into a chapter list.

    Expected format:  ## Title (Pages 1-10)  or  ## Title
    Returns the same format as get_chapters() for PDFs.
    """
    chapters = []
    with open(md_path, encoding="utf-8") as f:
        for line in f:
            m = _MD_CHAPTER_RE.match(line.rstrip())
            if m:
                title = m.group(1).strip()
                start = int(m.group(2)) - 1 if m.group(2) else len(chapters)
                end = int(m.group(3)) - 1 if m.group(3) else start
                chapters.append({"title": title, "start": start, "end": end})
    if not chapters:
        chapters = [{"title": "Whole Book", "start": 0, "end": -1}]
    return chapters


def load_chapter_from_md(md_path, chapter, chapter_title=None):
    """Extract text content between chapter headers in a markdown file.

    Returns a list of Document objects with the same metadata format as load_chapter().
    """
    title = (chapter_title or chapter.get("title", "Untitled")).strip()
    with open(md_path, encoding="utf-8") as f:
        lines = f.readlines()

    in_section = False
    section_lines = []
    for line in lines:
        m = _MD_CHAPTER_RE.match(line.rstrip())
        if m:
            if in_section:
                break
            if m.group(1).strip() == title:
                in_section = True
                continue
        elif in_section:
            section_lines.append(line)

    content = "".join(section_lines).strip()
    if not content:
        return []
    return [
        Document(
            page_content=content,
            metadata={
                "source": md_path,
                "page": 0,
                "chapter": title,
            },
        )
    ]


_CACHE_VERSION = "3"

def _cache_key(pdf_path):
    st = os.stat(pdf_path)
    return hashlib.sha1(
        f"{_CACHE_VERSION}|{pdf_path}|{st.st_size}|{st.st_mtime}".encode()
    ).hexdigest()[:16]


# -------------------------- OCR for scanned (image-only) PDFs --------------------------

# Tesseract is needed for OCR; add its install dir to PATH so PyMuPDF can find it.
_TESSERACT_DIR = r"C:\Program Files\Tesseract-OCR"
if os.path.isdir(_TESSERACT_DIR):
    os.environ["PATH"] = _TESSERACT_DIR + os.pathsep + os.environ.get("PATH", "")

OCR_CACHE_DIR = os.path.join(CACHE_DIR, "ocr")
# Project-local Tesseract language data (eng + nep) so scanned Devanagari books
# can be OCR'd with the Nepali model without needing admin rights in Program Files.
_TESSDATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), CACHE_DIR, "tessdata")
if os.path.isdir(_TESSDATA_DIR):
    os.environ.setdefault("TESSDATA_PREFIX", _TESSDATA_DIR)
else:
    _TESSDATA_DIR = None
_OCR_CACHE_VERSION = "5"


def _ocr_available() -> bool:
    return os.path.isfile(os.path.join(_TESSERACT_DIR, "tesseract.exe"))


def _ocr_cache_key(pdf_path):
    st = os.stat(pdf_path)
    return hashlib.sha1(
        f"{_OCR_CACHE_VERSION}|{pdf_path}|{st.st_size}|{st.st_mtime}".encode()
    ).hexdigest()[:16]


def _detect_ocr_lang(tesseract, pdf_path):
    """Pick the Tesseract language model for a scanned book: Devanagari books need
    -l nep, English books -l eng. Falls back to eng when the Nepali model is not
    installed."""
    if not _TESSDATA_DIR or not os.path.isfile(os.path.join(_TESSDATA_DIR, "nep.traineddata")):
        return "eng"
    import subprocess
    import tempfile

    txt = ""
    with pymupdf.open(pdf_path) as doc:
        page = doc[1] if doc.page_count > 1 else doc[0]
        pix = page.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            pix.save(tmp)
            r = subprocess.run(
                [tesseract, tmp, "stdout", "-l", "nep"],
                capture_output=True,
                timeout=120,
                env={**os.environ, "TESSDATA_PREFIX": _TESSDATA_DIR},
            )
            txt = (r.stdout or b"").decode("utf-8", errors="replace")
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass
    dev = sum(1 for c in txt if 0x0900 <= ord(c) <= 0x097F)
    return "nep" if dev > 20 else "eng"


def _ocr_texts(pdf_path, dpi=200, workers=6):
    """OCR every page of a scanned (no text layer) PDF into plain text.

    Uses the Tesseract CLI directly (PyMuPDF's built-in OCR proved unreliable on
    some scanned CDC books). Results are cached on disk under chapter_cache/ocr/
    so the expensive OCR pass only runs once per file. Each worker opens its own
    Document because PyMuPDF documents are not thread-safe.
    """
    if not _ocr_available():
        return []
    cache_file = None
    try:
        os.makedirs(OCR_CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(OCR_CACHE_DIR, _ocr_cache_key(pdf_path) + ".json")
        if os.path.exists(cache_file):
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        cache_file = None

    import subprocess
    import tempfile

    tesseract = os.path.join(_TESSERACT_DIR, "tesseract.exe")
    lang = _detect_ocr_lang(tesseract, pdf_path)
    ocr_env = os.environ.copy()
    if _TESSDATA_DIR:
        ocr_env["TESSDATA_PREFIX"] = _TESSDATA_DIR

    def _one(i):
        with pymupdf.open(pdf_path) as doc:
            page = doc[i]
            native = page.get_text() or ""
            if native.strip():
                return i, native
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
            fd, tmp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            try:
                pix.save(tmp)
                r = subprocess.run(
                    [tesseract, tmp, "stdout", "-l", lang],
                    capture_output=True,
                    timeout=180,
                    env=ocr_env,
                )
                return i, (r.stdout or b"").decode("utf-8", errors="replace")
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    with pymupdf.open(pdf_path) as doc:
        n = doc.page_count
    if n == 0:
        return []
    texts = [""] * n
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_one, i) for i in range(n)]
        for fut in concurrent.futures.as_completed(futs):
            try:
                i, t = fut.result()
                texts[i] = t
            except Exception:
                pass
    try:
        if cache_file:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(texts, f, ensure_ascii=False)
    except Exception:
        pass
    return texts


# Preeti/Kantipur fonts render the digits 0-9 with distinct glyphs that
# nepali_converter turns into these Devanagari letters/conjuncts. Several CDC
# Nepali books are typeset in such a font, so their TOC rows ("१. नाप १")
# arrive in this encoding and must be mapped back to ASCII digits.
_PREETI_DIGITS = (
    ("ज्ञ", "1"),  # 1
    ("द्ध", "4"),  # 4
    ("द्द", "2"),  # 2
    ("घ", "3"),
    ("छ", "5"),
    ("ट", "6"),
    ("ठ", "7"),
    ("ड", "8"),
    ("ढ", "9"),
    ("ण्", "0"),  # 0
    ("ञ", "1"),   # alternate 1 (for "जञ" etc.)
    ("ट्ट", "6"),  # alternate
)

# Preeti "पाठ" (lesson) markers appear as "PsfO" etc.
# "PsfO" -> "पाठ" (प + ा + ठ)
_PREETI_LESSON = "PsfO"


def _deva_digits_to_ascii(s):
    """Map Devanagari + Preeti-font digit glyphs in a line to ASCII digits."""
    s = str(s or "")
    for d, a in zip("०१२३४५६७८९", "0123456789"):
        s = s.replace(d, a)
    for k, v in _PREETI_DIGITS:
        s = s.replace(k, v)
    # Handle Preeti page range separators (–, -) and lesson markers
    s = s.replace("–", "-").replace("—", "-")
    # Normalize Preeti "पाठ" markers
    s = s.replace(_PREETI_LESSON, "पाठ")
    return s


def _ocr_toc_units(toc_text):
    """Parse a contents page into a list of (title, printed_page) pairs.

    Handles three layouts:
    1. Column layout: a "Topic"/"शीर्षक" header, then the names (possibly with
       a "विधा" column), then a "Page"/"पृष्ठ..." header, then the numbers.
    2. Row layout: one row per unit, flattened onto lines as
       "<number>. <title> <page>" -- the number, title and page each occupy
       their own line (or are separated by tabs). Section headers such as
       "(Physics)" may appear between rows. Numbers and pages may be ASCII,
       Devanagari digits, or Preeti-font glyphs.
    3. Interleaved layout: unit number / name / page alternating on separate
       lines.
    Unit numbers are re-assigned in order of appearance because OCR often
    mangles them (15 -> "45").
    """
    def _tok(line):
        return (line or "").strip(" \t\r\n.·—_|,.«»")

    lines = [_tok(l) for l in (toc_text or "").splitlines() if _tok(l)]
    units = []  # (name, printed_page)

    # Layout: Nepali "पा७ :N" TOC (e.g. Class 6 Nepali). Unit markers are
    # "पा७ :N" (Preeti digits), followed by title, genre, page. Return unit entries.
    if any("विषयसूची" in l for l in lines[:3]) and any(
        re.match(r"^पा[०-९7]\s*:\s*\S", _deva_digits_to_ascii(l)) for l in lines
    ):
        out = []
        i = 0
        # skip header rows
        while i < len(lines) and not re.match(
            r"^पा[०-९7]\s*:\s*\S", _deva_digits_to_ascii(lines[i])
        ):
            i += 1
        while i < len(lines):
            a = _deva_digits_to_ascii(lines[i])
            m = re.match(r"^पा[०-९7]\s*:\s*(\S+)", a)
            if not m:
                i += 1
                continue
            i += 1
            title_parts = []
            while i < len(lines):
                a2 = _deva_digits_to_ascii(lines[i])
                if re.match(r"^पा[०-९7]\s*:", a2):
                    break
                if re.fullmatch(r"\d{1,3}", a2):
                    break
                if lines[i] in ("कविता", "कथा", "निबन्ध", "जीवनी", "वादविवाद", "निवेदन", "संवाद", "प्रबन्ध"):
                    i += 1
                    continue
                title_parts.append(lines[i])
                i += 1
            title = " ".join(title_parts).strip()
            if not title:
                continue
            page = None
            j = i
            while j < len(lines):
                a3 = _deva_digits_to_ascii(lines[j])
                if re.fullmatch(r"\d{1,3}", a3):
                    page = int(a3)
                    break
                if re.match(r"^पा[०-९7]\s*:", a3):
                    break
                j += 1
            out.append((_clean_deva_title(title), page))
        if out:
            return out

    # Layout: Nepali "एकाइ : N" TOC (e.g. Class 6 Science Nepali).
    # Unit lines: "एकाइ : N\t Title" followed by page range "N–M" on next line.
    if any("विषयसूची" in l for l in lines[:3]) and any(
        re.match(r"^एकाइ\s*:\s*[०-९\d]+", _deva_digits_to_ascii(l)) for l in lines
    ):
        out = []
        i = 0
        while i < len(lines):
            a = _deva_digits_to_ascii(lines[i])
            m = re.match(r"^एकाइ\s*:\s*[०-९\d]+\s*[:\t]?\s*(.+)$", a)
            if not m:
                i += 1
                continue
            title = m.group(1).strip()
            # next line is page range like "१–२०" - get start page
            page = None
            if i + 1 < len(lines):
                a2 = _deva_digits_to_ascii(lines[i + 1])
                m2 = re.match(r"^([०-९\d]+)[–-]", a2)
                if m2:
                    try:
                        page = int(m2.group(1))
                    except ValueError:
                        pass
            out.append((_clean_deva_title(title), page))
            i += 1
        if out:
            return out

    # Layout: Nepali Social Studies table TOC with "एकाइ : <word>" unit headers
    # followed by "पा७ <digit>" lesson markers, title, page.
    # e.g. "एकाइ : एक  आफू, आफ्नो परिवार र परिवार\nद्द–ज्ञज्ञ\nपा७ ज्ञ\nमेरा परिवारको पेसा\nद्द"
    if any(
        re.match(r"^एकाइ\s*:\s*(एक|दुई|तीन|चार|पाँच|छ|सात|आठ|नौ|दश)", l) for l in lines
    ) and any(
        re.match(r"^पा[०-९7]\s+\S", _deva_digits_to_ascii(l)) for l in lines
    ):
        out = []
        i = 0
        while i < len(lines):
            l = lines[i]
            mu = re.match(r"^एकाइ\s*:\s*(एक|दुई|तीन|चार|पाँच|छ|सात|आठ|नौ|दश)\s*(.*)", l)
            if mu:
                i += 1
                # Skip page range lines, unit title lines, etc. until we hit lessons
                # or the next unit header
                while i < len(lines):
                    al = _deva_digits_to_ascii(lines[i])
                    ml = re.match(r"^पा[०-९7]\s+(\S+)", al)
                    # Stop if we hit the next unit header
                    if re.match(r"^एकाइ\s*:", lines[i]):
                        break
                    if ml:
                        # Found a lesson marker
                        i += 1
                        # Next line is the title
                        if i < len(lines):
                            title = _clean_deva_title(lines[i].strip())
                            i += 1
                            # Next line is page number
                            page = None
                            if i < len(lines):
                                ap = _deva_digits_to_ascii(lines[i])
                                if re.fullmatch(r"\d{1,3}", ap):
                                    page = int(ap)
                                    i += 1
                                else:
                                    i += 1
                            out.append((title, page))
                        else:
                            break
                    else:
                        # Not a lesson marker (could be unit title, page range, etc.)
                        i += 1
                continue
            i += 1
        if out:
            return out

    # Layout: Nepali "पा७ N :" TOC (e.g. Class 5/6 Science/Math Nepali).
    # Unit lines: "पा७ N :" on one line, title on next line, page on following line.
    if any("विषय सूची" in l for l in lines[:3]) and any(
        re.match(r"^पा[०-९7]\s+\d+\s*:", _deva_digits_to_ascii(l)) for l in lines
    ):
        out = []
        i = 0
        while i < len(lines):
            a = _deva_digits_to_ascii(lines[i])
            m = re.match(r"^पा[०-９7]\s+(\d+)\s*:", a)
            if not m:
                i += 1
                continue
            # Title is on next line
            if i + 1 < len(lines):
                title = _clean_deva_title(lines[i + 1].strip())
            else:
                i += 1
                continue
            # Page is on line after title
            page = None
            if i + 2 < len(lines):
                a2 = _deva_digits_to_ascii(lines[i + 2])
                if re.fullmatch(r"\d{1,3}", a2):
                    page = int(a2)
            out.append((title, page))
            i += 3  # skip unit line, title line, page line
        if out:
            return out

    # Column layout with explicit title and page headers.
    topic_idx = next(
        (k for k, l in enumerate(lines) if l.lower() in ("topic", "subject", "शीर्षक")),
        None,
    )
    page_idx = None
    if topic_idx is not None:
        page_idx = next(
            (k for k in range(topic_idx + 1, len(lines))
             if lines[k].lower() == "page"
             or re.match(r"^पृष्ठ?", lines[k])),
            None,
        )
    if topic_idx is not None and page_idx is not None and page_idx > topic_idx + 1:
        stop = {"contents", "unit", "topic", "page", "विधा", "क्र.स."}
        names = []
        for l in lines[topic_idx + 1:page_idx]:
            if l.lower() in stop:
                break
            names.append(l)
        pages = []
        for l in lines[page_idx + 1:]:
            a = _deva_digits_to_ascii(_tok(l))
            if re.fullmatch(r"\d{1,3}", a):
                pages.append(int(a))
        for k, name in enumerate(names):
            units.append((name, pages[k] if k < len(pages) else None))
        return units

    # Layout: English "CONTENTS / Unit / Topic / Page" with "Unit One / Lesson N"
    # pattern (e.g. Class 5 Social Studies English). Unit lines are "Unit N"
    # followed by title, then page range, then "Lesson N" sub-items.
    if any(l.lower() == "contents" for l in lines[:5]) and any(
        l.lower() == "topic" for l in lines[:10]
    ) and any(l.lower() == "page" for l in lines[:10]):
        out = []
        i = 0
        # Map word numbers to digits
        unit_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
        expected_unit = 1
        i = 0
        while i < len(lines):
            l = lines[i]
            a = _deva_digits_to_ascii(l)
            # Match "Unit N" or "Unit N:" where N can be digit or word
            # Also handle concatenated "Unit ThreeSocial" by taking first word
            m = re.match(r"^Unit\s+(\w+):?", a, re.I)
            if m:
                unit_num_str = m.group(1).lower()
                # Handle concatenated words like "ThreeSocial" -> "Three"
                if not unit_num_str.isdigit():
                    for w in unit_words:
                        if unit_num_str.startswith(w):
                            unit_num_str = w
                            break
                unit_num = int(unit_num_str) if unit_num_str.isdigit() else unit_words.get(unit_num_str, 0)
                if unit_num != expected_unit and unit_num > 0:
                    # Skip if out of order
                    i += 1
                    continue
                # Next non-empty line is the unit title
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    title = lines[j].strip()
                    # Next non-empty line after title is page range
                    page = None
                    k = j + 1
                    while k < len(lines):
                        a = _deva_digits_to_ascii(lines[k])
                        m2 = re.match(r"^(\d{1,3})[–-]", a)
                        if m2:
                            page = int(m2.group(1))
                            break
                        if re.fullmatch(r"\d{1,3}", a):
                            page = int(a)
                            break
                        k += 1
                    out.append((title, page))
                    expected_unit += 1
                    i = k
                else:
                    i += 1
            else:
                i += 1
        if out:
            return out

# Layout: English hierarchical "Unit One / Title / Page / Lesson N / Title /
    # Page" (e.g. Class 8 Moral Education English). Return units with lessons.
    # Single-pass sequential parser that groups lessons under their units.
    if any(re.match(r"^Unit\s+\w+", l, re.I) for l in lines) and any(
        re.match(r"^Lesson\s+\d+", l, re.I) for l in lines
    ):
        out = []
        current_unit = 0
        current_unit_title = None
        current_unit_page = None
        current_unit_lessons = []
        i = 0
        while i < len(lines):
            l = lines[i]
            # Check for unit header
            m = re.match(r"^Unit\s+(\w+)(.*)$", l, re.I)
            if m:
                # Finalize previous unit with its lessons
                if current_unit > 0 and current_unit_title:
                    out.append((f"Unit {current_unit}: {current_unit_title}", current_unit_page))
                    out.extend(current_unit_lessons)
                    current_unit_lessons = []
                # Start new unit
                current_unit += 1
                if m.group(2).strip():
                    # Concatenated format: "Unit ThreeSocial Problems..."
                    current_unit_title = m.group(2).strip()
                else:
                    # Standard format: title on next line
                    current_unit_title = lines[i + 1].strip() if i + 1 < len(lines) else None
                # Remove "Unit N: " prefix if present in title (from garbled OCR with Preeti digits)
                current_unit_title = _deva_digits_to_ascii(current_unit_title)
                current_unit_title = re.sub(r"^Unit\s+\d+\s*:\s*", "", current_unit_title, flags=re.I)
                current_unit_page = None
                # Find page range (handles both single page and ranges like "2-11")
                page_search_start = i + 1
                for j in range(page_search_start, len(lines)):
                    a = _deva_digits_to_ascii(lines[j])
                    if re.fullmatch(r"\d{1,3}", a):
                        current_unit_page = int(a)
                        break
                    # Check for page range pattern (e.g., "2-11", "12-21")
                    m_range = re.match(r"^(\d{1,3})[–-]\d{1,3}$", a)
                    if m_range:
                        current_unit_page = int(m_range.group(1))
                        break
                    if re.match(r"^Lesson\s", lines[j], re.I):
                        break
                i += 1
                continue
            # Check for lesson (only add to current unit's lessons)
            lesson_match = re.match(r"^Lesson\s+(\d+)", _deva_digits_to_ascii(l), re.I)
            if lesson_match and current_unit > 0:
                lesson_num = lesson_match.group(1)
                lesson_title = lines[i + 1].strip() if i + 1 < len(lines) else ""
                lesson_page = None
                for k in range(i + 2, len(lines)):
                    a = _deva_digits_to_ascii(lines[k])
                    if re.fullmatch(r"\d{1,3}", a):
                        lesson_page = int(a)
                        break
                    if re.match(r"^Lesson\s", _deva_digits_to_ascii(lines[k]), re.I):
                        break
                    if re.match(r"^Unit\s+\w+", lines[k], re.I):
                        break
                current_unit_lessons.append((f"  Lesson {lesson_num}: {lesson_title}", lesson_page))
            i += 1
        # Add final unit with its lessons
        if current_unit > 0 and current_unit_title:
            out.append((f"Unit {current_unit}: {current_unit_title}", current_unit_page))
            out.extend(current_unit_lessons)
        if out:
            return out

    # Layout: Nepali hierarchical "एकाइ एक / Title / Page-range / पाठ N / Title /
    # Page" (e.g. Class 8 Moral Education Nepali, Preeti digits). Return units with lessons.
    if any("विषयसूची" in l for l in lines[:3]) and any(
        re.match(r"^एकाइ\s+\S+", l) for l in lines
    ):
        out = []
        for i, l in enumerate(lines):
            if not re.match(r"^एकाइ\s+\S+", l):
                continue
            unit_title = _clean_deva_title(lines[i + 1].strip()) if i + 1 < len(lines) else None
            if not unit_title:
                continue
            unit_page = None
            for j in range(i + 2, len(lines)):
                a = _deva_digits_to_ascii(lines[j])
                if re.fullmatch(r"\d+(-\d+)?", a):
                    unit_page = int(a.split("-")[0])
                    break
                if re.match(r"^(एकाइ\s|पा)", lines[j]):
                    break
            # Add unit
            out.append(("एकाइ " + str(len([x for x in out if x[0].startswith("एकाइ ")]) + 1) + ": " + unit_title, unit_page))
            # Extract lessons (पाठ N) under this unit
            for j in range(i + 2, len(lines)):
                lesson_match = re.match(r"^पा७\s+(\d+)", lines[j]) or re.match(r"^पाठ\s+(\d+)", lines[j])
                if not lesson_match:
                    continue
                lesson_num = lesson_match.group(1)
                lesson_title = lines[j + 1].strip() if j + 1 < len(lines) else ""
                lesson_page = None
                for k in range(j + 2, len(lines)):
                    a = _deva_digits_to_ascii(lines[k])
                    if re.fullmatch(r"\d{1,3}", a):
                        lesson_page = int(a)
                        break
                    if re.match(r"^(पा७|पाठ|एकाइ)", lines[k]):
                        break
                out.append((f"  पाठ {lesson_num}: {lesson_title}", lesson_page))
        if out:
            return out

    # Layout: Nepali "विषय सूची" hierarchical unit/lesson TOC where units are
    # "<number> : <title>" (colon) and lessons are "<number>. <title>" (period),
    # e.g. Class 8 Vocational Technical Education. Pages are standalone numbers
    # (possibly Preeti glyphs) after each lesson. Return the UNIT entries, each
    # anchored at the first lesson page that follows it.
    if (lines and "विषय" in lines[0] and "सूची" in lines[0] and any(
        re.match(r"^\d{1,3}\s*:\s*\S", _deva_digits_to_ascii(l)) for l in lines
    )):
        out = []
        i = 0
        # skip the header rows ("विषय सूची / एकाइ / शीर्षक / पृष्७ सङ्ख्या")
        while i < len(lines) and not re.match(
            r"^\d{1,3}\s*:\s*\S", _deva_digits_to_ascii(lines[i])
        ):
            i += 1
        while i < len(lines):
            m = re.match(
                r"^(\d{1,3})\s*:\s*(.+)$", _deva_digits_to_ascii(lines[i])
            )
            if not m:
                i += 1
                continue
            title = m.group(2).strip()
            i += 1
            # collect continuation lines (titles that wrap, e.g. "सुक्खा तरकारी,
            # फलफुल" + "तथा विभिन्न खाद्य परिकार") until the next lesson/unit
            while i < len(lines):
                a = _deva_digits_to_ascii(lines[i])
                if re.match(r"^\d{1,3}\s*[:.]", a):
                    break  # next unit or lesson
                if re.fullmatch(r"\d{1,3}", a):
                    break  # a page number
                title += " " + lines[i].strip()
                i += 1
            # first standalone page number following the unit header
            page = None
            j = i
            while j < len(lines):
                a = _deva_digits_to_ascii(lines[j])
                if re.fullmatch(r"\d{1,3}", a):
                    page = int(a)
                    break
                if re.match(r"^\d{1,3}\s*:\s*\S", a):
                    break  # next unit header without a page
                j += 1
            out.append((_clean_deva_title(title), page))
        if out:
            return out

    # Layout: Nepali "पा७ :N" TOC (e.g. Class 6 Nepali). Unit markers are
    # "पा७ :N" (Preeti digits), followed by title, genre, page. Return unit entries.
    if any("विषयसूची" in l for l in lines[:3]) and any(
        re.match(r"^पा[०-९7]\s*:\s*\S", _deva_digits_to_ascii(l)) for l in lines
    ):
        out = []
        i = 0
        # skip header rows
        while i < len(lines) and not re.match(
            r"^पा[०-९7]\s*:\s*\S", _deva_digits_to_ascii(lines[i])
        ):
            i += 1
        while i < len(lines):
            a = _deva_digits_to_ascii(lines[i])
            m = re.match(r"^पा[०-९7]\s*:\s*(\S+)", a)
            if not m:
                i += 1
                continue
            # unit number in m.group(1) (Preeti digit already converted)
            # title is next line(s) until genre/page
            i += 1
            title_parts = []
            while i < len(lines):
                a2 = _deva_digits_to_ascii(lines[i])
                if re.match(r"^पा[०-९7]\s*:", a2):
                    break  # next unit
                if re.fullmatch(r"\d{1,3}", a2):
                    break  # page number
                # genre lines like "कविता", "कथा", "निबन्ध", "जीवनी", "वादविवाद", "निवेदन", "संवाद", "प्रबन्ध"
                if lines[i] in ("कविता", "कथा", "निबन्ध", "जीवनी", "वादविवाद", "निवेदन", "संवाद", "प्रबन्ध"):
                    i += 1
                    continue
                title_parts.append(lines[i])
                i += 1
            title = " ".join(title_parts).strip()
            if not title:
                continue
            # find page number after title
            page = None
            j = i
            while j < len(lines):
                a3 = _deva_digits_to_ascii(lines[j])
                if re.fullmatch(r"\d{1,3}", a3):
                    page = int(a3)
                    break
                if re.match(r"^पा[०-९7]\s*:", a3):
                    break
                j += 1
            out.append((_clean_deva_title(title), page))
        if out:
            return out

    # Layout: English "CONTENTS / Unit / Topic / Page" with "Unit One / Lesson N"
    # pattern (e.g. Class 5 Social Studies English). Unit lines are "Unit N"
    # followed by title, then page range, then "Lesson N" sub-items.
    if any(l.lower() == "contents" for l in lines[:5]) and any(
        l.lower() == "topic" for l in lines[:10]
    ) and any(l.lower() == "page" for l in lines[:10]):
        out = []
        i = 0
        # Map word numbers to digits
        unit_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
        expected_unit = 1
        i = 0
        while i < len(lines):
            l = lines[i]
            a = _deva_digits_to_ascii(l)
            # Match "Unit N" or "Unit N:" where N can be digit or word
            m = re.match(r"^Unit\s+(\d+|[a-z]+):?", a, re.I)
            if m:
                unit_num_str = m.group(1).lower()
                unit_num = int(unit_num_str) if unit_num_str.isdigit() else unit_words.get(unit_num_str, 0)
                if unit_num != expected_unit and unit_num > 0:
                    # Skip if out of order
                    i += 1
                    continue
                # Next non-empty line is the unit title
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    title = lines[j].strip()
                    # Next non-empty line after title is page range
                    page = None
                    k = j + 1
                    while k < len(lines):
                        a = _deva_digits_to_ascii(lines[k])
                        m2 = re.match(r"^(\d{1,3})[–-]", a)
                        if m2:
                            page = int(m2.group(1))
                            break
                        if re.fullmatch(r"\d{1,3}", a):
                            page = int(a)
                            break
                        k += 1
                    out.append((title, page))
                    expected_unit += 1
                    i = k
                else:
                    i += 1
            else:
                i += 1
        if out:
            return out

    # Layout: Nepali "सामाजिक अध्ययन / पाठ / शीर्षक / पृष्ठसङ्ख्या" with
    # "एकाइ : N" unit headers and "पा७ N" lesson markers
    # (e.g. Class 5 Social Studies Nepali)
    if any("विषयसूची" in l for l in lines[:5]) and any(
        "एकाइ" in l for l in lines[:20]
    ) and any("पा७" in l for l in lines[:50]):
        out = []
        i = 0
        while i < len(lines):
            a = _deva_digits_to_ascii(lines[i])
            # Match "एकाइ : N" or "एकाइ N" patterns
            if re.match(r"^एकाइ\s*:\s*[०-९\d]+", a) or re.match(r"^एकाइ\s+[०-९\d]+", a):
                # Next non-empty line is the unit title
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines):
                    title = _clean_deva_title(lines[j].strip())
                    # Next non-empty line after title is page range
                    page = None
                    k = j + 1
                    while k < len(lines):
                        a2 = _deva_digits_to_ascii(lines[k])
                        m2 = re.match(r"^([०-९\d]+)[–-]", a2)
                        if m2:
                            try:
                                page = int(m2.group(1))
                            except ValueError:
                                pass
                            break
                        if re.fullmatch(r"[०-९\d]+", a2):
                            try:
                                page = int(a2)
                            except ValueError:
                                pass
                            break
                        k += 1
                    out.append((title, page))
                    i = k
                else:
                    i += 1
            else:
                i += 1
        if out:
            return out

    # Layout: English multi-column table "Unit / Reading / Speaking / Listening /
    # Grammar / Writing / Project work / Page" (e.g. Class 7/8 English). The unit
    # name is the first cell (Reading) after each unit number; the remaining
    # cells are activity names and must not be joined into the title. Unit
    # numbers appear in order 1, 2, 3, ... while printed page numbers do not,
    # so a bare number equal to the next expected unit number is a unit, and
    # any other bare number is the previous unit's page.
    low0 = " ".join((toc_text or "").lower().split())
    if (
        "table of contents" in low0 or "contents" in low0
    ) and "reading" in low0 and "unit" in low0 and "page" in low0:
        out = []
        expected = 1
        i = 0
        # skip header cells until the first unit number
        while i < len(lines) and not re.fullmatch(r"\d{1,3}", _deva_digits_to_ascii(lines[i])):
            i += 1
        last_page = None
        while i < len(lines):
            a = _deva_digits_to_ascii(lines[i])
            if re.fullmatch(r"\d{1,3}", a):
                n = int(a)
                if n == expected:
                    # unit number -> name is the Reading cell (first column);
                    # the cell may wrap, so merge continuation lines that start
                    # with a lowercase letter or follow a connector word.
                    if i + 1 < len(lines) and lines[i + 1]:
                        name_parts = [lines[i + 1]]
                        j = i + 2
                        while j < len(lines) and lines[j]:
                            a2 = _deva_digits_to_ascii(lines[j])
                            if re.fullmatch(r"\d{1,3}", a2):
                                break  # page / next unit number
                            joined = " ".join(name_parts)
                            if (
                                lines[j][0].islower()
                                or re.search(
                                    r"\b(of|in|the|to|a|and|with|for|on)\s*$",
                                    joined,
                                    re.I,
                                )
                            ):
                                name_parts.append(lines[j])
                                j += 1
                            else:
                                break
                        name = " ".join(name_parts)
                        if last_page is not None and out:
                            out[-1] = (out[-1][0], last_page)
                            last_page = None
                        out.append((name, None))
                        expected += 1
                        i = j - 1
                    else:
                        break
                else:
                    last_page = n
            i += 1
        if last_page is not None and out:
            out[-1] = (out[-1][0], last_page)
        if out:
            return out

    # Row layout: rows of <number.> <title> <page> (number, title and page on
    # their own lines, with section headers interleaved). Skip header lines up
    # to the first row number.
    i = 0
    while i < len(lines) and not re.search(r"\d", _deva_digits_to_ascii(lines[i])):
        i += 1
    # Handle Nepali "विषयसूची" (table of contents) header style
    if i < len(lines) and "विषयसूची" in lines[0]:
        # Skip header lines until first data row
        while i < len(lines) and not re.search(r"\d", _deva_digits_to_ascii(lines[i])):
            i += 1
    while i < len(lines):
        tok = lines[i]
        a = _deva_digits_to_ascii(tok)
        # handle "17.\t Coordinates" on one line (number + title)
        m = re.match(r"^(\d{1,2})\.?\s+(.+)$", a)
        if m:
            title_parts = [m.group(2).strip()]
            i += 1
        elif re.fullmatch(r"\d{1,3}\.?$", a):
            i += 1
            title_parts = []
        else:
            i += 1
            continue
        page = None
        while i < len(lines):
            ta = _deva_digits_to_ascii(lines[i])
            if re.fullmatch(r"\d{1,3}", ta):
                page = int(ta)
                i += 1
                break
            if re.fullmatch(r"\d{1,3}\.$", ta):
                break  # next row
            title_parts.append(lines[i])
            i += 1
        name = " ".join(title_parts).strip()
        if name and not re.search(r"(उत्तरमाला|answers|answer\s*key)", name, re.I):
            units.append((name, page))
    if units:
        return units

    # Fallback: interleaved layout (Nepali TOCs)
    i = 0
    # skip header ("Contents", "Unit", "Topic", "Page") until the first bare number
    while i < len(lines):
        if re.fullmatch(r"\d{1,2}", _deva_digits_to_ascii(lines[i])):
            break
        i += 1
    while i < len(lines):
        if not re.fullmatch(r"\d{1,2}", _deva_digits_to_ascii(lines[i])):
            i += 1
            continue
        i += 1  # consume unit number
        name_parts = []
        while i < len(lines):
            if re.fullmatch(r"\d{1,3}", _deva_digits_to_ascii(lines[i])):
                break  # page number column
            if lines[i]:
                name_parts.append(lines[i])
            i += 1
        page = None
        if i < len(lines):
            page = int(_deva_digits_to_ascii(lines[i]))
            i += 1
        name = " ".join(name_parts).strip()
        if name:
            units.append((name, page))
    return units


def detect_chapters_ocr(pdf_path, texts=None):
    """Detect chapters for scanned PDFs from OCR text + the table of contents.

    Uses the printed page numbers on the contents page as chapter boundaries.
    Some CDC books print the page where each unit *ends* rather than starts, so
    each unit's opener is located near the *previous* unit's printed page (the
    first unit opens on the first content page). Each boundary page is verified
    to actually contain the unit title. Falls back to a single "Whole Book"
    chapter when the TOC or openers cannot be located.
    """
    if texts is None:
        texts = _ocr_texts(pdf_path)
    if not texts:
        return []
    n = len(texts)

    toc_idx = None
    for i in range(min(n, 12)):
        low = " ".join((texts[i] or "").lower().split())
        if "contents" in low and "unit" in low and "page" in low:
            toc_idx = i
            break
        # "शीर्षक" + a page-number header ("पृष्ठ...", often OCR-mangled to
        # "पृष्७सङ्ख्या" when ठ is mis-read as the digit ७).
        if "शीर्षक" in low and ("पृष्ठ" in low or "पृष्" in low):
            toc_idx = i
            break
    if toc_idx is None:
        return []

    units = _ocr_toc_units(texts[toc_idx])
    if not units:
        return []

    def _norm(t):
        return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()

    def _top_lines(idx, max_lines=2):
        """First content lines of a page (standalone page-number line dropped)."""
        if idx < 0 or idx >= n:
            return ""
        lines = [l.strip() for l in (texts[idx] or "").splitlines() if l.strip()]
        while lines and re.fullmatch(r"[\d०-९]{1,3}", lines[0]):
            lines.pop(0)
        return " ".join(lines[:max_lines])

    def _is_marker(idx):
        """A page whose top content line is a short "पाठ N" lesson marker.

        Nepali books start each lesson with a line like "पाठ १" (often OCR'd as
        "षाठ ७", "6० ११", "0 17" etc.), which carries no title text. The line
        must be short and contain a digit -- "मुल पाठ" (main text) and exercise
        headers like "१०." are excluded. English books never have such markers,
        so this stays False for them."""
        if idx < 0 or idx >= n:
            return False
        lines = [l.strip() for l in (texts[idx] or "").splitlines() if l.strip()]
        while lines and re.fullmatch(r"[\d०-९]{1,3}", lines[0]):
            lines.pop(0)
        if not lines:
            return False
        top = lines[0]
        if len(top) > 7:
            return False
        if top.endswith("."):
            return False
        return bool(re.search(r"[०-९0-9]", top))

    def _title_score(idx, name):
        """How strongly page `idx` opens unit `name` (0..1). The unit title must
        appear near the top of the page -- matching anywhere in the page text
        would flag content pages that merely mention the unit name."""
        low = _norm(_top_lines(idx))
        if not low:
            return 0.0
        nm = _norm(name)
        if not nm:
            return 0.0
        if nm in low:
            return 1.0
        # OCR-mangled titles: compare word-by-word (e.g. "Automic" vs "Atomic",
        # "Not metals" vs "Non-metals", title split across two lines).
        title_words = [w for w in nm.split(" ") if w]
        if title_words:
            hit = sum(1 for w in title_words if w in low)
            if hit / len(title_words) >= 0.6:
                return 0.7
        # fuzzy match against a leading line (OCR may mangle letters)
        for line in low.split(" ")[:24]:
            if difflib.SequenceMatcher(None, line, nm).ratio() >= 0.6:
                return 0.6
        return 0.0

    def _opener_title(idx, toc_name):
        """Prefer the clean title printed on the opener page over the OCR'd TOC
        name (fixes TOC typos like "Automic" or "Not metals"). Only used when the
        opener page actually carries the title near the top."""
        if _title_score(idx, toc_name) < 0.6:
            return toc_name
        lines = [l.strip() for l in (texts[idx] or "").splitlines() if l.strip()]
        while lines and re.fullmatch(r"[\d०-९]{1,3}", lines[0]):
            lines.pop(0)
        strip_chars = " \t\r\n=—-–_|·•*:;"
        head = [l.strip(strip_chars) for l in lines[:3]]
        head = [l for l in head if l]
        if not head:
            return toc_name
        parts = [head[0]]
        if re.search(r"\b(and|of|the|to|in|at|for)\s*$", parts[-1], re.I):
            for extra in head[1:]:
                parts.append(extra)
                break
        title = " ".join(parts).strip(strip_chars)
        low = title.lower()
        if any(h in low for h in (
            "activity", "exercise", "fig", "discuss", "observe", "question",
            "objective", "materials required", "method", "introduction", "answer",
        )) or len(title) > 60:
            return toc_name
        return title

    # Locate the opener page for each unit. English books print the unit title
    # at the top of the opener page, which sits near the *previous* unit's
    # printed page; Nepali books print a "पाठ N" marker instead and the title
    # appears a few pages later. So first do a tight top-line title search
    # around the previous unit's printed page; if nothing strong matches, fall
    # back to the next "पाठ" marker page or the first page that mentions the
    # unit title.
    boundaries = []
    prev = -1
    prev_printed = None
    for name, page in units:
        # Skip units whose title never appears in the book (TOC OCR artifacts
        # like a misplaced "विषयसूची" entry). Exact substring matches cover
        # Devanagari titles (whose _norm would strip the script); fuzzy
        # top-line matches tolerate OCR typos in English TOC titles
        # ("Automic" vs the page's "Atomic").
        if not any(
            i != toc_idx
            and (name in (texts[i] or "") or _title_score(i, name) >= 0.7)
            for i in range(n)
        ):
            continue
        if prev_printed is None:
            lo, hi = 1, min(n, (page or 8) + 2)
        else:
            lo = max(1, prev_printed - 3)
            hi = min(n, prev_printed + 3)
        best, best_score = None, 0.0
        for cand in range(lo, hi):
            if cand == toc_idx:
                continue
            s = _title_score(cand, name)
            if s > best_score:
                best, best_score = cand, s
        if best is None or best_score < 0.7:
            # no strong top-line match near the anchor: fall back to the next
            # "पाठ" marker page or the first page that mentions the title
            best = None
            for cand in range(prev + 1, n):
                if cand == toc_idx:
                    continue
                if _is_marker(cand) or name in (texts[cand] or ""):
                    best = cand
                    break
        if best is None:
            continue  # cannot locate this unit's opener; skip it
        boundaries.append((best, _opener_title(best, name)))
        prev = best
        prev_printed = page

    if not boundaries:
        return []

    boundaries.sort(key=lambda b: b[0])
    seen = set()
    unique = []
    for opener, name in boundaries:
        if opener in seen:
            continue
        seen.add(opener)
        unique.append((opener, name))

    chapters = []
    for k, (idx, name) in enumerate(unique):
        end = unique[k + 1][0] - 1 if k + 1 < len(unique) else n - 1
        chapters.append({"title": f"Unit {k + 1}: {name}", "start": idx, "end": end})
    return chapters


# ---------------------------------------------------------------------------
# Text-layer books typeset in a legacy (Preeti/Kantipur) font convert to
# Devanagari via _page_text, but their chapter openers often carry no unit
# marker and only some pages have a dominant heading -- so the generic heading
# scan above returns a fraction of the real units (e.g. Class 8 Maths/Science
# 2080). Their table of contents, however, lists every unit with a printed page
# number, so we can rebuild the chapter list from it directly.
# ---------------------------------------------------------------------------


def _clean_deva_title(title):
    """Repair common nepali_converter artifacts in Preeti-sourced titles.

    The Preeti font encodes Devanagari consonants in ASCII keys; nepali_converter
    maps some of them onto the wrong Devanagari glyph (e.g. ण -> "०ा",
    ठ -> "७", घ -> "३", ड -> "८"), so a title read off such a page may show
    "पूर्०ा सङ्ख्याहरू" for "पूर्ण सङ्ख्याहरू". Undo those mappings."""
    t = str(title or "")
    # Handle both Devanagari digits and ASCII digits (Preeti artifacts)
    for k, v in (
        ("०ा", "ण"),  # ण -> "०ा"
        ("०", "ण"),   # ण -> "०"
        ("७", "ठ"),   # ठ -> ७
        ("३", "घ"),   # घ -> ३
        ("१", "ज्ञ"),  # ज्ञ -> १
        ("८", "ड"),   # ड -> ८
        ("५", "छ"),   # छ -> ५
        ("२", "ड"),   # ड -> २ (direct, not intermediate द्द)
        ("४", "ध"),   # ध -> ४ (direct, not intermediate द्ध)
        ("६", "ट"),   # ट -> ६
        ("९", "ढ"),   # ढ -> ९
        ("0ा", "ण"),  # ASCII 0ा -> ण
        ("0", "ण"),   # ASCII 0 -> ण
        ("7", "ठ"),   # ASCII 7 -> ठ
        ("3", "घ"),   # ASCII 3 -> घ
        ("1", "ज्ञ"),  # ASCII 1 -> ज्ञ
        ("8", "ड"),   # ASCII 8 -> ड
        ("5", "छ"),   # ASCII 5 -> छ
        ("2", "ड"),   # ASCII 2 -> ड (direct)
        ("4", "ध"),   # ASCII 4 -> ध (direct)
        ("6", "ट"),   # ASCII 6 -> ट
        ("9", "ढ"),   # ASCII 9 -> ढ
        ("\u201c", "ं"),  # Preeti anusvara glyph -> U+201C artifact (e.g. बुझौ" -> बुझौं)
        ("Œ", "त्त्"),  # Preeti "Œ" ligature -> त्त् (e.g. महŒव -> महत्त्व)
        ("णड", "ण्ड"),  # split conjunct ण्+ड -> ण्ड (e.g. गणडकी -> गण्डकी)
    ):
        t = t.replace(k, v)
    return t


def _fix_lesson_numbers(title):
    """Fix lesson numbers that were converted to Preeti digits by _clean_deva_title.

    _clean_deva_title converts ASCII digits 1-9 to Preeti equivalents:
      1->\u091e(\u091e\u094d\u091e), 2->\u0926\u094d\u0926, 3->\u0918,
      4->\u0926\u094d\u0927, 5->\u091b, 6->\u091f, 7->\u0920,
      8->\u0921, 9->\u0922

    This function reverses that for the lesson number part only.
    """
    import re
    # Map Preeti digit strings (in longest-first order) back to ASCII digits
    # These are the sequences _clean_deva_title produces from ASCII digits
    preeti_to_ascii = [
        ("\u091c\u094d\u091e", "1"),   # jnya -> 1 (3 chars: ja+virama+nya)
        ("\u0926\u094d\u0926", "2"),   # dd -> 2 (3 chars: da+virama+da)
        ("\u0918", "3"),               # gha -> 3 (single char)
        ("\u0926\u094d\u0927", "4"),   # ddh -> 4 (3 chars: da+virama+dha)
        ("\u091b", "5"),               # chha -> 5 (single char)
        ("\u091f", "6"),               # tta -> 6 (single char)
        ("\u0920", "7"),               # ttha -> 7 (single char)
        ("\u0921", "8"),               # dda -> 8 (single char)
        ("\u0922", "9"),               # ddha -> 9 (single char)
    ]

    def _replace_deva_digits(digits_str):
        """Replace Preeti digit characters in a string with ASCII digits."""
        result = digits_str
        for preeti, ascii_d in preeti_to_ascii:
            result = result.replace(preeti, ascii_d)
        return result

    # Match "Lesson <deva digits>: <rest>" and replace
    # Character class must include all chars from Preeti digit sequences:
    # \u091c\u094d\u091e (jnya=1), \u0926\u094d\u0926 (dd=2), \u0918 (gha=3),
    # \u0926\u094d\u0927 (ddh=4), \u091b (chha=5), \u091f (tta=6),
    # \u0920 (ttha=7), \u0921 (dda=8), \u0922 (ddha=9)
    result = re.sub(
        r"(Lesson\s*)([\u091c\u091e\u0926\u094d\u0927\u0918\u091b\u091f\u0920\u0921\u0922]+)(:.*)",
        lambda m: m.group(1) + _replace_deva_digits(m.group(2)) + m.group(3),
        title,
    )
    # Fix double colons: "Lesson N::" -> "Lesson N:"
    result = re.sub(r"(Lesson\s*\d+)::", r"\1:", result)
    return result


def _deva_skeleton(s):
    """Consonant skeleton of a Devanagari string for tolerant matching.

    Fixes the Preeti digit artifacts, then drops vowel signs, viramas, digits
    and punctuation so "मिश्र०ा" and "मिश्रण" (or "ग०िात" and "गणित") compare
    equal."""
    s = _clean_deva_title(s)
    return re.sub(
        r"[ािीुूृेैोौंः्॰०-९0-9\s\.\-–—_()\"'`\/\\]",
        "",
        s,
    )


def _parse_toc_units(texts, limit=12):
    """Return the parsed (title, printed_page) units from the contents page of
    a text-layer book, or None when no parseable contents page is found."""
    for i in range(min(len(texts), limit)):
        low = " ".join((texts[i] or "").lower().split())
        # English: "Table of Content(s)" + "Subject"/"Topic" + "Page"
        # Nepali: "शीर्षक" + "पृष्ठ..." (or "विषय सूची" + "पृष्...")
        has_toc = ("contents" in low or "content" in low) and (
            "unit" in low or "subject" in low or "topic" in low
        ) and "page" in low
        has_nepali_toc = (
            "शीर्षक" in low or "विषयसूची" in low or "विषय सूची" in low
        ) and ("पृष्ठ" in low or "पृष्" in low)
        if has_toc or has_nepali_toc:
            # combine this TOC page with any following pages that continue it
            # (multi-page contents: the rest of the entries follow immediately)
            merged = texts[i] or ""
            j = i + 1
            while j < len(texts) and j < i + 5:
                nxt = (texts[j] or "").strip()
                nxt_low = " ".join(nxt.lower().split())
                first_line = nxt.splitlines()[0] if nxt.splitlines() else ""
                first_a = _deva_digits_to_ascii(first_line.strip())
                if (
                    "contents" in nxt_low or "content" in nxt_low
                    or "विषय" in nxt_low or "एकाइ" in nxt_low
                    or re.search(r"^\s*\d{1,3}\s*[:.)]", nxt_low)
                    or re.match(r"^\s*\d{1,3}\s*[:.)]", first_a)
                    or re.match(r"^\s*\d{1,3}\s*$", first_a)
                ):
                    merged += "\n" + nxt
                    j += 1
                else:
                    break
            units = _ocr_toc_units(merged)
            if units:
                return units
    return None


def _looks_legacy_title(title):
    """True when a detected title is still raw Preeti bytes (no Devanagari).

    Raw Preeti text is ASCII letters/figures (possibly with apostrophes,
    backslashes, braces or '>' markers) whose preeti-mode conversion yields
    Devanagari. English titles never satisfy this (they convert to a mix that
    still contains Latin letters)."""
    if not title:
        return False
    if any("\u0900" <= c <= "\u097f" for c in title):
        return False
    letters = re.findall(r"[A-Za-z\u0900-\u097f]", title)
    if not letters:
        return False
    # Preeti marker characters (apostrophe, backslash, braces, '>', ...) make a
    # title strongly legacy even when it also contains plain letters.
    if re.search(r"[{}'\\|<>~;!]", title):
        try:
            from nepali_converter import convert
            out = convert(title, "preeti")
            return any("\u0900" <= c <= "\u097f" for c in out)
        except Exception:
            return True
    # a vowel-less pure-ASCII run ("rfk", "Wjlg") is a Preeti consonant string
    if re.fullmatch(r"[A-Za-z]+", title) and not re.search(r"[aeiouAEIOU]", title):
        return True
    return False


def _converted_texts(pdf_path):
    """Converted text layer for every page of a text-layer book."""
    texts = []
    with pymupdf.open(pdf_path) as doc:
        for i in range(doc.page_count):
            texts.append(_page_text(doc, i))
    return texts


def detect_chapters_toc_text(pdf_path, texts=None):
    """Detect chapters for text-layer books from their table of contents.

    Some CDC Nepali books are typeset in a legacy Preeti/Kantipur font and are
    converted to Devanagari by _page_text. Their openers rarely carry a "पाठ N"
    marker and only a few pages have a dominant heading, so the generic heading
    scan returns far fewer chapters than the book really has. This function
    instead reads the printed page numbers from the contents page and anchors
    each unit's opener near its own printed page.

    Falls back to a single "Whole Book" chapter when the TOC or openers cannot
    be located.
    """
    if texts is None:
        texts = _converted_texts(pdf_path)
    units = _parse_toc_units(texts)
    if not units:
        return []
    n = len(texts)

    toc_idx = None
    for i in range(min(n, 12)):
        low = " ".join((texts[i] or "").lower().split())
        has_toc = ("contents" in low or "content" in low) and (
            "unit" in low or "subject" in low or "topic" in low
        ) and "page" in low
        has_nepali_toc = (
            "शीर्षक" in low or "विषयसूची" in low or "विषय सूची" in low
        ) and ("पृष्ठ" in low or "पृष्" in low)
        if has_toc or has_nepali_toc:
            toc_idx = i
            break
    if toc_idx is None:
        return []

    offset = None
    for i in range(toc_idx + 1, min(toc_idx + 30, n)):
        lines = [l.strip() for l in texts[i].splitlines() if l.strip()]
        if lines and re.fullmatch(r"\d{1,3}", lines[0]):
            offset = i - int(lines[0])
            break
    if offset is None:
        offset = toc_idx + 1

    def page_has_title(idx, name):
        """How strongly page idx opens unit `name` (0..1) using Devanagari
        consonant skeletons so TOC/page spelling artifacts cancel out."""
        if idx < 0 or idx >= n:
            return 0.0
        sk_name = _deva_skeleton(name)
        if not sk_name:
            return 0.0
        pg = _deva_skeleton(texts[idx])
        if not pg:
            return 0.0
        if sk_name in pg:
            return 1.0
        words = [w for w in sk_name.split() if len(w) >= 2]
        if words:
            hits = sum(1 for w in words if w in pg)
            if hits / len(words) >= 0.6:
                return 0.6
        return 0.0

    boundaries = []
    prev = -1
    for name, page in units:
        if page is None:
            continue
        expected = page + offset
        lo = max(toc_idx + 1, expected - 3)
        hi = min(n, expected + 5)
        best, best_score = None, 0.0
        for cand in range(lo, hi):
            if cand == toc_idx:
                continue
            s = page_has_title(cand, name)
            if s > best_score:
                best, best_score = cand, s
        if best is None or best_score < 0.5:
            # Expanding window search around expected page (tight -> wider)
            best = None
            for radius in (5, 10, 15, 20):
                lo = max(toc_idx + 1, expected - radius)
                hi = min(n, expected + radius)
                for cand in range(lo, hi):
                    if cand == toc_idx:
                        continue
                    if page_has_title(cand, name) >= 0.5:
                        best = cand
                        break
                if best is not None:
                    break
            if best is None:
                # Last resort: forward scan from prev
                for cand in range(max(toc_idx + 1, prev + 1), n):
                    if cand == toc_idx:
                        continue
                    if page_has_title(cand, name) >= 0.5:
                        best = cand
                        break
            if best is None:
                # Ultimate fallback: use expected page directly
                best = max(toc_idx + 1, min(expected, n - 1))
        boundaries.append((best, _clean_deva_title(name)))
        prev = best

    if not boundaries:
        return []

    # Keep boundaries in TOC order but enforce monotonically increasing page indices.
    for i in range(1, len(boundaries)):
        if boundaries[i][0] <= boundaries[i - 1][0]:
            boundaries[i] = (boundaries[i - 1][0] + 1, boundaries[i][1])
    seen = set()
    unique = []
    unique = []
    for opener, name in boundaries:
        if opener in seen:
            continue
        seen.add(opener)
        unique.append((opener, name))

    chapters = []
    unit_counter = 0
    for k, (idx, name) in enumerate(unique):
        end = unique[k + 1][0] - 1 if k + 1 < len(unique) else n - 1
        # If name already indicates a lesson, use it directly; otherwise prefix with unit number
        # Strip any existing "Unit N: " prefix from the name (added by _parse_toc_units)
        clean_name = _deva_digits_to_ascii(name.strip())
        clean_name = _clean_deva_title(clean_name)
        clean_name = re.sub(r"^Unit\s+\d+\s*:\s*", "", clean_name, flags=re.I)
        if name.strip().startswith("Lesson"):
            # Fix lesson numbers that were converted to Preeti by _clean_deva_title
            lesson_title = name.strip()
            lesson_title = _fix_lesson_numbers(lesson_title)
            title = lesson_title
        else:
            unit_counter += 1
            title = f"Unit {unit_counter}: {clean_name}"
        chapters.append({"title": title, "start": idx, "end": end})
    print(f"DEBUG_BC: returning {len(chapters)} chapters")
    return chapters


def get_chapters(pdf_path, force=False):
    os.makedirs(CACHE_DIR, exist_ok=True)
    # Handle markdown files directly
    if pdf_path.lower().endswith(".md"):
        cache_file = os.path.join(CACHE_DIR, _cache_key(pdf_path) + ".json")
        if not force and os.path.exists(cache_file):
            try:
                with open(cache_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        chapters = parse_md_chapters(pdf_path)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(chapters, f, ensure_ascii=False, indent=2)
        return chapters
    cache_file = os.path.join(CACHE_DIR, _cache_key(pdf_path) + ".json")
    if not force and os.path.exists(cache_file):
        try:
            with open(cache_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    chapters = detect_chapters(pdf_path)
    if not chapters:
        chapters = [{"title": "Whole Book", "start": 1, "end": -1}]
    texts = None
    if len(chapters) == 1 and chapters[0]["title"] == "Whole Book":
        needs_toc = True
    else:
        # A text-layer book typeset in a legacy (Preeti) font may only expose a
        # few heading pages (Class 8 Maths/Science 2080) or keep raw font bytes
        # in its titles; rebuild it from the table of contents when the TOC
        # lists more units than the heading scan found, or when a title is
        # still raw Preeti.
        texts = _converted_texts(pdf_path)
        n_units = len(_parse_toc_units(texts) or [])
        legacy_titles = any(_looks_legacy_title(c["title"]) for c in chapters)
        needs_toc = bool(
            n_units
            and (
                n_units > len(chapters)
                or legacy_titles
            )
        )
        # Also fix garbled titles (e.g., English books with font spacing artifacts)
        # by matching TOC titles to detected boundaries when counts match.
        if not needs_toc and n_units == len(chapters) and n_units >= 4:
            toc_titles = [u[0] for u in (_parse_toc_units(texts) or [])]
            if toc_titles:
                for i, c in enumerate(chapters):
                    if i < len(toc_titles):
                        c["title"] = f"Unit {i + 1}: {toc_titles[i]}"
    # Prefer TOC-driven result when heading scan is at lesson granularity
    # but TOC provides unit-level structure (fewer chapters with unit titles).
    # This handles cases like Class 6 Nepali where heading scan finds "पाठ N"
    # lesson markers but TOC lists proper units.
    if texts is None:
        texts = _converted_texts(pdf_path)
    toc_chapters = detect_chapters_toc_text(pdf_path, texts=texts)
    # Detect lesson markers: "पाठ N", "पा७" (Preeti), "अभ्यास" (exercise),
    # English "X.Y" sub-lessons, "Lesson X.Y", "Exercise X.Y",
    # measurement units (cm, mm, kg, l, ml), fractions, long descriptions,
    # common math sub-topic keywords
    lesson_markers = sum(1 for c in chapters if re.search(
        r"\bपाठ\s*\d|पा[०-९7]!|अभ्यास\s*\d|\b\d+\.\d+\b|Lesson\s+\d+\.\d+|Exercise\s+\d+\.\d+"
        r"|\b\d+\s*(cm|mm|kg|g|l|ml)\b|fraction|improper|exercise|capacity"
        r"|area|volume|weight|percentage|perimeter|distance|time|geometry|number|operation"
        r"|simple\s+interest|unitary\s+method|set|algebra|statics|bill|budget|statistics"
        r"|fundamental|concept|measurement|money|angle", c["title"], re.I))
    long_descriptive = sum(1 for c in chapters if len(c["title"]) > 60)
    prefer_toc = (
        toc_chapters
        and len(toc_chapters) >= 4
        and (
            len(toc_chapters) >= len(chapters)
            or legacy_titles
            or (
                len(toc_chapters) < len(chapters)
                and (lesson_markers + long_descriptive) >= len(chapters) // 2
            )
        )
    )
    if prefer_toc:
        chapters = toc_chapters
    elif needs_toc:
        if len(chapters) == 1 and chapters[0]["title"] == "Whole Book":
            ocr_chapters = detect_chapters_ocr(pdf_path)
            if ocr_chapters:
                chapters = ocr_chapters
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(chapters, f, ensure_ascii=False, indent=2)
    return chapters


def find_book(books, class_num, file_name):
    for b in books:
        if b["class"] == class_num and b["file"] == file_name:
            return b
    return None
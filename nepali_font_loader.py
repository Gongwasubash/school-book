import pymupdf
import warnings

from langchain_core.documents import Document
from nepali_converter import convert
from nepali_converter.detector import detect_font

warnings.filterwarnings("ignore")

LEGACY_FONT_MODES = {
    "preeti": "preeti",
    "nagarik": "preeti",
    "ganess": "preeti",
    "ganesh": "preeti",
    "arap": "preeti",
    "himalayabold": "preeti",
    "himalaya": "preeti",
    "aakriti": "preeti",
    "sun": "preeti",
    "kruti": "preeti",
    "shangrila": "preeti",
    "pathyakram": "preeti",
    "tt7": "preeti",
    "tte2": "preeti",
    "adarsa": "preeti",
    "adarsha": "preeti",
    "himali": "himalb",
    "himal": "himalb",
    "sagarmatha": "sagarmatha",
    "kantipur": "kantipur",
    "pcs": "pcs",
}

# Characters that are strong indicators of legacy-encoded (non-Unicode) Nepali
_LEGACY_SPECIAL = set("{}[]|\\")


def font_to_mode(font_name):
    lower = (font_name or "").lower()
    for key, mode in LEGACY_FONT_MODES.items():
        if key in lower:
            return mode
    return None


def looks_legacy(text):
    if not text or not text.strip():
        return False
    if any("\u0900" <= ch <= "\u097f" for ch in text):
        return False
    if any(ch in _LEGACY_SPECIAL for ch in text):
        return True
    for ch in text:
        code = ord(ch)
        if 0x80 <= code <= 0xFF:
            return True
    return False


def convert_span(text, font_name):
    mode = font_to_mode(font_name)
    if mode:
        try:
            return convert(text, mode)
        except Exception:
            return text
    if looks_legacy(text):
        try:
            detected = detect_font(text) or "preeti"
            return convert(text, detected)
        except Exception:
            return text
    return text


def load_pdf_documents(path):
    documents = []
    doc = pymupdf.open(path)
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            blocks = page.get_text("dict").get("blocks", [])
            page_lines = []
            for block in blocks:
                for line in block.get("lines", []):
                    line_parts = []
                    for span in line.get("spans", []):
                        text = convert_span(span.get("text", ""), span.get("font", ""))
                        line_parts.append(text)
                    page_lines.append("".join(line_parts))
            content = "\n".join(page_lines)
            if content.strip():
                documents.append(
                    Document(page_content=content, metadata={"source": path, "page": page_index})
                )
    finally:
        doc.close()
    return documents
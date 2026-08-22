"""Slide generation for NotebookLM-style chapter decks.

Tries providers in order (whichever has credentials):
  1. Google Gemini (OAuth or x-goog-api-key)
  2. Mistral (Bearer API key)

Secrets live in google_credentials.json / google_tokens.json /
google_api_key.json / mistral_api_key.json (gitignored).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import webbrowser
from urllib.parse import urlencode

import requests

from textbook_indexer import load_chapter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CREDS_FILE = os.path.join(HERE, "google_credentials.json")
TOKENS_FILE = os.path.join(HERE, "google_tokens.json")
API_KEY_FILE = os.path.join(HERE, "google_api_key.json")
MISTRAL_KEY_FILE = os.path.join(HERE, "mistral_api_key.json")
FAL_KEY_FILE = os.path.join(HERE, "fal_api_key.json")
HF_KEY_FILE = os.path.join(HERE, "hf_api_key.json")

SCOPE = "https://www.googleapis.com/auth/generative-language"
MODEL = "gemini-3.6-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-large-latest"
REDIRECT_PATH = "/api/google/callback"

# Free image generation via Pollinations.ai (no API key, cartoon style).
POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
IMAGE_STYLE = (
    "colorful cartoon illustration for a children's school textbook, "
    "animated style, friendly characters, flat vector, high quality"
)
IMAGE_WIDTH = 1024
IMAGE_HEIGHT = 768

# Google Gemini image generation (saves PNGs locally per slide).
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
GEMINI_IMAGE_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent"
)
SLIDE_IMAGE_DIR = os.path.join(HERE, "slide_images")
SLIDE_IMAGE_PREFIX = "/images"

# FAL AI image generation (text-to-image, cartoon style).
FAL_MODEL = "fal-ai/fast-sdxl"
FAL_QUEUE_URL = f"https://queue.fal.run/{FAL_MODEL}"

# Hugging Face Inference API image generation (FLUX.1-schnell, free tier).
HF_IMAGE_MODEL = "black-forest-labs/FLUX.1-schnell"
HF_IMAGE_URL = f"https://api-inference.huggingface.co/models/{HF_IMAGE_MODEL}"

_tokens = {"access_token": None, "refresh_token": None, "expires_at": 0.0}


def _load_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    try:
        with open(API_KEY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("api_key") or data.get("key")
    except (OSError, ValueError):
        return None


def has_api_key() -> bool:
    return bool(_load_api_key())


def _load_mistral_key():
    key = os.environ.get("MISTRAL_API_KEY")
    if key:
        return key
    try:
        with open(MISTRAL_KEY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("api_key") or data.get("key")
    except (OSError, ValueError):
        return None


def has_mistral_key() -> bool:
    return bool(_load_mistral_key())


def _load_fal_key():
    key = os.environ.get("FAL_KEY")
    if key:
        return key
    try:
        with open(FAL_KEY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("api_key") or data.get("key")
    except (OSError, ValueError):
        return None


def has_fal_key() -> bool:
    return bool(_load_fal_key())


def _load_hf_key():
    key = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if key:
        return key
    try:
        with open(HF_KEY_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("token") or data.get("api_key") or data.get("key")
    except (OSError, ValueError):
        return None


def has_hf_key() -> bool:
    return bool(_load_hf_key())


def is_authorized() -> bool:
    if has_api_key() or has_mistral_key() or has_fal_key() or has_hf_key():
        return True
    _load_tokens()
    return bool(_tokens.get("refresh_token") or _tokens.get("access_token"))


def _load_creds():
    with open(CREDS_FILE, encoding="utf-8") as f:
        return json.load(f)["installed"]


def _save_tokens():
    with open(TOKENS_FILE, "w", encoding="utf-8") as f:
        json.dump(_tokens, f)


def _load_tokens():
    global _tokens
    try:
        with open(TOKENS_FILE, encoding="utf-8") as f:
            _tokens = json.load(f)
    except (OSError, ValueError):
        _tokens = {"access_token": None, "refresh_token": None, "expires_at": 0.0}


def auth_url(port: int = 8000) -> str:
    """Build the OAuth authorization URL using the loopback redirect."""
    creds = _load_creds()
    redirect = f"http://localhost:{port}{REDIRECT_PATH}"
    params = {
        "client_id": creds["client_id"],
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{creds['auth_uri']}?{urlencode(params)}"


def open_auth_browser(port: int = 8000) -> str:
    url = auth_url(port)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    return url


def exchange_code(code: str, port: int = 8000) -> None:
    """Exchange the OAuth authorization code for tokens and persist them."""
    creds = _load_creds()
    redirect = f"http://localhost:{port}{REDIRECT_PATH}"
    resp = requests.post(
        creds["token_uri"],
        data={
            "code": code,
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "redirect_uri": redirect,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"OAuth token exchange failed: {data}")
    _tokens["access_token"] = data["access_token"]
    _tokens["refresh_token"] = data.get("refresh_token", _tokens.get("refresh_token"))
    _tokens["expires_at"] = time.time() + data.get("expires_in", 3600) - 60
    _save_tokens()


def _get_access_token() -> str:
    _load_tokens()
    if _tokens.get("access_token") and _tokens.get("expires_at", 0) > time.time():
        return _tokens["access_token"]
    refresh = _tokens.get("refresh_token")
    if not refresh:
        raise RuntimeError("Google account not authorized yet")
    creds = _load_creds()
    resp = requests.post(
        creds["token_uri"],
        data={
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"OAuth refresh failed: {data}")
    _tokens["access_token"] = data["access_token"]
    _tokens["expires_at"] = time.time() + data.get("expires_in", 3600) - 60
    _save_tokens()
    return _tokens["access_token"]


SYSTEM_PROMPT = (
    "You are a study assistant that builds NotebookLM-style slide decks for "
    "Nepali school textbooks. You ALWAYS respond with a single valid JSON "
    "object and nothing else."
)


def _system_prompt(language: str = "") -> str:
    lang = (language or "").lower()
    if lang in ("english", "en"):
        return (
            "You are a study assistant that builds NotebookLM-style slide decks for "
            "Nepali school textbooks. This is an ENGLISH-medium textbook. "
            "You ALWAYS respond with a single valid JSON object and nothing else. "
            "Write the deck title, slide titles, bullets, and speaker notes in ENGLISH only."
        )
    if lang in ("nepali", "ne"):
        return (
            "You are a study assistant that builds NotebookLM-style slide decks for "
            "Nepali school textbooks. This is a NEPALI-medium textbook. "
            "You ALWAYS respond with a single valid JSON object and nothing else. "
            "Write the deck title, slide titles, bullets, and speaker notes in NEPALI only."
        )
    return (
        "You are a study assistant that builds NotebookLM-style slide decks for "
        "Nepali school textbooks. Default language is NEPALI. "
        "You ALWAYS respond with a single valid JSON object and nothing else. "
        "Write the deck title, slide titles, bullets, and speaker notes in NEPALI only."
    )

SLIDE_SCHEMA = (
    '{"title": "<chapter/lesson title>", "slides": ['
    '{"title": "<slide title>", "bullets": ["...", "..."], "note": "<short speaker note>"}]} '
    "- 8-12 slides: slide 1 = chapter overview; slides 2-5 = key concepts with 3-5 bullets each; "
    "slide 6 = key terms & definitions; slide 7 = study questions (3-4 questions); "
    "slide 8 = chapter summary; "
    "slide 9+ = additional concepts/examples if needed. "
    "Each bullet concise (1-2 lines). Speaker notes 1-2 sentences per slide. "
    "Output JSON only."
)

# Keywords that mark the start of the exercise section in a chapter.
EXERCISE_MARKERS = (
    "अभ्यास",
    "Exercise",
    "Exercises",
    "Exercise Time",
    "Practice",
    "Practice Time",
    "Questions",
    "Question Bank",
    "स्वाध्याय",
)

EXERCISE_SCHEMA = (
    '{"title": "<chapter/lesson title>", "questions": ['
    '{"question": "...", "answer": "...", "explanation": "..."}]} '
    "- Extract EVERY question from the exercise verbatim, and solve each one "
    "with a clear answer and a short explanation. Answer in the same language "
    "as the textbook."
)


def _extract_exercise(text: str) -> str:
    """Return the exercise section of a chapter (from first marker to end)."""
    start = None
    for marker in EXERCISE_MARKERS:
        idx = text.find(marker)
        if idx != -1 and (start is None or idx < start):
            start = idx
    if start is None:
        return ""
    return text[start:]


def solve_exercise(pdf_path: str, chapter: dict, max_chars: int = 14000, language: str = "") -> dict:
    """Extract the chapter's exercise questions and solve them."""
    docs = load_chapter(pdf_path, chapter, chapter_title=chapter.get("title"))
    if not docs:
        raise ValueError("No extractable text in this chapter")
    text = "\n\n".join(d.page_content for d in docs)
    text = _clean(text)[:max_chars]
    exercise_text = _extract_exercise(text)
    if not exercise_text:
        exercise_text = text
    title = chapter.get("title") or "Chapter"
    prompt = (
        f"Chapter title: {title}\n\n"
        f"{EXERCISE_SCHEMA}\n\n"
        f"Exercise section:\n{exercise_text}"
    )
    errors = []
    for name, call in (("Gemini", _call_gemini), ("Mistral", _call_mistral)):
        try:
            answer = call(prompt, language)
            parsed = _extract_json(answer)
            if not parsed or not parsed.get("questions"):
                raise RuntimeError(f"{name} did not return valid exercise solutions")
            parsed.setdefault("title", title)
            return parsed
        except RuntimeError as e:
            errors.append(str(e))
    raise RuntimeError("All providers failed: " + " | ".join(errors))


def _extract_json(text: str):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.I)
    text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def _clean(text: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text or "")


def _image_prompt(slide_title: str, chapter_title: str = "") -> str:
    topic = slide_title or chapter_title or "school lesson"
    prompt = f"{topic}, {IMAGE_STYLE}"
    return prompt.replace(" ", "%20").replace(",", "%2C")


def _slide_image_url(slide_title: str, chapter_title: str = "", seed: int = 0) -> str:
    prompt = _image_prompt(slide_title, chapter_title)
    return (
        f"{POLLINATIONS_URL.format(prompt=prompt)}"
        f"?width={IMAGE_WIDTH}&height={IMAGE_HEIGHT}"
        f"&nologo=true&seed={seed}"
    )


def _call_gemini(prompt: str, language: str = "") -> str:
    """Call Google Gemini; returns raw model text. Raises RuntimeError on failure."""
    key = _load_api_key()
    headers = {"Content-Type": "application/json"}
    if key:
        headers["x-goog-api-key"] = key
    else:
        headers["Authorization"] = f"Bearer {_get_access_token()}"
    resp = requests.post(
        GEMINI_URL,
        headers=headers,
        json={
            "contents": [{"parts": [{"text": f"{_system_prompt(language)}\n\n{prompt}"}]}],
            "generationConfig": {"temperature": 0.4},
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"Gemini returned no content: {data}")


def _call_mistral(prompt: str, language: str = "") -> str:
    """Call Mistral chat completions; returns raw model text."""
    key = _load_mistral_key()
    if not key:
        raise RuntimeError("Mistral API key not configured")
    resp = requests.post(
        MISTRAL_URL,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MISTRAL_MODEL,
            "messages": [
                {"role": "system", "content": _system_prompt(language)},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.4,
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Mistral API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"Mistral returned no content: {data}")


def _call_gemini_image(prompt: str) -> bytes:
    """Generate an image via Google Gemini image model. Returns PNG bytes."""
    key = _load_api_key()
    if not key:
        raise RuntimeError("Google API key not configured for image generation")
    resp = requests.post(
        GEMINI_IMAGE_URL,
        headers={
            "x-goog-api-key": key,
            "Content-Type": "application/json",
        },
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]},
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini image API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        parts = data["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"Gemini image returned no content: {data}")
    for part in parts:
        inline = part.get("inlineData", {})
        if inline.get("data"):
            return base64.b64decode(inline["data"])
    raise RuntimeError("Gemini image returned no image data")


def _call_fal_image(prompt: str) -> bytes:
    """Generate an image via FAL AI text-to-image. Returns PNG/JPEG bytes.

    FAL returns a queue with a result URL; we poll until the image is ready,
    then download the generated image bytes.
    """
    key = _load_fal_key()
    if not key:
        raise RuntimeError("FAL API key not configured")
    headers = {
        "Authorization": f"Key {key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "image_size": "landscape_4_3",
        "num_images": 1,
    }
    resp = requests.post(FAL_QUEUE_URL, headers=headers, json=payload, timeout=120)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"FAL API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    status_url = data.get("status_url") or data.get("response_url")
    if not status_url:
        raise RuntimeError(f"FAL returned no status URL: {data}")
    for _ in range(60):
        time.sleep(2)
        sr = requests.get(status_url, headers=headers, timeout=30)
        if sr.status_code != 200:
            continue
        sdata = sr.json()
        if sdata.get("status") == "COMPLETED":
            images = sdata.get("images") or (sdata.get("data") or {}).get("images")
            if not images:
                raise RuntimeError(f"FAL completed but no images: {sdata}")
            img_url = images[0].get("url")
            if not img_url:
                raise RuntimeError(f"FAL image missing url: {images[0]}")
            ir = requests.get(img_url, timeout=60)
            if ir.status_code != 200:
                raise RuntimeError(f"FAL image download failed {ir.status_code}")
            return ir.content
        if sdata.get("status") in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"FAL job failed: {sdata}")
    raise RuntimeError("FAL image generation timed out")


def _call_hf_image(prompt: str) -> bytes:
    """Generate an image via Hugging Face Inference API (FLUX.1-schnell).

    The HF endpoint returns the raw image bytes directly, or a JSON error
    (e.g. model still loading -> 503 with retry-after).
    """
    key = _load_hf_key()
    if not key:
        raise RuntimeError("Hugging Face token not configured")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    payload = {"inputs": prompt, "parameters": {"width": 1024, "height": 768}}
    resp = requests.post(HF_IMAGE_URL, headers=headers, json=payload, timeout=120)
    if resp.status_code == 200:
        return resp.content
    if resp.status_code == 503:
        raise RuntimeError(f"HF model is loading: {resp.text[:200]}")
    raise RuntimeError(f"HF Inference API error {resp.status_code}: {resp.text[:300]}")


def _image_cache_path(chapter_title: str, slide_title: str) -> str:
    """Deterministic local filename for a slide image (reused across runs)."""
    key = hashlib.sha1(f"{chapter_title}|{slide_title}".encode("utf-8")).hexdigest()[:20]
    return os.path.join(SLIDE_IMAGE_DIR, f"{key}.png")


def _slide_image(chapter_title: str, slide_title: str, seed: int = 0) -> str:
    """Return a URL for a slide image.

    Tries providers in order (all saved to slide_images/ and served at
    /images/...): FAL AI -> Google Gemini -> Pollinations URL fallback.
    Cached files are reused without re-generating.
    """
    os.makedirs(SLIDE_IMAGE_DIR, exist_ok=True)
    topic = slide_title or chapter_title or "school lesson"

    path = _image_cache_path(chapter_title, slide_title)
    if os.path.exists(path):
        return f"{SLIDE_IMAGE_PREFIX}/{os.path.basename(path)}"

    prompt = f"{topic}, {IMAGE_STYLE}"
    for name, call in (
        ("FAL", _call_fal_image),
        ("HuggingFace", _call_hf_image),
        ("Gemini", _call_gemini_image),
    ):
        try:
            data = call(prompt)
            with open(path, "wb") as f:
                f.write(data)
            return f"{SLIDE_IMAGE_PREFIX}/{os.path.basename(path)}"
        except Exception:
            continue
    return _slide_image_url(topic, chapter_title, seed)


def generate_notebook_slides(pdf_path: str, chapter: dict, max_chars: int = 18000, language: str = "") -> dict:
    """Generate a NotebookLM-style slide deck from a whole chapter."""
    docs = load_chapter(pdf_path, chapter, chapter_title=chapter.get("title"))
    if not docs:
        raise ValueError("No extractable text in this chapter")
    text = "\n\n".join(d.page_content for d in docs)
    text = _clean(text)[:max_chars]
    title = chapter.get("title") or "Chapter"
    prompt = (
        f"Chapter title: {title}\n\n"
        f"{SLIDE_SCHEMA}\n\nChapter content:\n{text}"
    )
    errors = []
    for name, call in (("Gemini", _call_gemini), ("Mistral", _call_mistral)):
        try:
            answer = call(prompt, language)
            parsed = _extract_json(answer)
            if not parsed or not parsed.get("slides"):
                raise RuntimeError(f"{name} did not return a valid slide deck")
            for i, slide in enumerate(parsed.get("slides", [])):
                slide["image"] = _slide_image(
                    title,
                    slide.get("title") or f"Slide {i + 1}",
                    seed=i + 1,
                )
            return parsed
        except Exception as e:
            errors.append(str(e))
    raise RuntimeError("All providers failed: " + " | ".join(errors))
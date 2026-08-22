"""RAG engine for the AI Books portal.

Wraps textbook_indexer (chapter detection + Nepali font conversion) to build an
in-memory FAISS store on demand, then powers both the RAG chat and the LLM-generated
learning resources from the actual textbook content.
"""

from __future__ import annotations

import json
import os
import re

import streamlit as st

from dotenv import load_dotenv

load_dotenv()

from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI

from textbook_indexer import scan_library, find_book, get_chapters, load_chapter, load_chapter_from_md

TEXTBOOK_ROOT = os.environ.get(
    "TEXTBOOK_ROOT", r"E:\class  1 to 10 book\Nepal Textbooks Grade 1-10"
)
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL")
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "none")
QWEN_MODEL_NAME = os.environ.get("QWEN_MODEL_NAME", "Qwen/Qwen3.8-27B")

MISTRAL_KEY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mistral_api_key.json")
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
MISTRAL_MODEL_NAME = "mistral-large-latest"


def _load_mistral_key():
    key = os.environ.get("MISTRAL_API_KEY")
    if key:
        return key
    try:
        with open(MISTRAL_KEY_FILE, encoding="utf-8") as f:
            return json.load(f).get("api_key") or ""
    except Exception:
        return ""


PROVIDERS = ["Mistral (free)", "Groq (openai/gpt-oss-20b)", "Qwen (free HF endpoint)"]


# --------------------------------------------------------------------------- LLM


def get_llm(provider):
    if provider == "Mistral (free)":
        return ChatOpenAI(
            model=MISTRAL_MODEL_NAME,
            temperature=0.3,
            max_tokens=1024,
            base_url=MISTRAL_BASE_URL,
            api_key=_load_mistral_key(),
        )
    if provider == "Qwen (free HF endpoint)":
        return ChatOpenAI(
            model=QWEN_MODEL_NAME,
            temperature=0.3,
            max_tokens=1024,
            base_url=QWEN_BASE_URL,
            api_key=QWEN_API_KEY,
            model_kwargs={"reasoning_effort": "low"},
        )
    return ChatGroq(
        model="openai/gpt-oss-20b",
        temperature=0.3,
        max_tokens=1024,
        api_key=os.environ.get("GROQ_API_KEY"),
    )


@st.cache_resource(show_spinner=False)
def get_embedding_model():
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


# --------------------------------------------------------------- library / index


@st.cache_data(show_spinner=False)
def cached_scan_library(root):
    return scan_library(root)


@st.cache_data(show_spinner=False)
def cached_get_chapters(path):
    return get_chapters(path)


def available_classes(books):
    return sorted({b["class"] for b in books})


def build_store(book, selected_chapters):
    """Load the chapter pages, split into chunks and embed them into a FAISS index."""
    documents = []
    is_md = book["path"].lower().endswith(".md")
    for chapter in selected_chapters:
        if is_md:
            docs = load_chapter_from_md(book["path"], chapter, chapter_title=chapter.get("title"))
        else:
            docs = load_chapter(book["path"], chapter, chapter_title=chapter.get("title"))
        documents.extend(docs)
    if not documents:
        return None, 0
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    chunks = splitter.split_documents(documents)
    if not chunks:
        return None, 0
    store = FAISS.from_documents(chunks, get_embedding_model())
    return store, len(chunks)


def format_selection(book, chapters):
    pages = "; ".join(
        f"{c['title']} (pp.{c['start'] + 1}-{c['end'] + 1})" for c in chapters
    )
    return f"{book['file']} — {pages}"


# ------------------------------------------------------------------------- chat


CHAT_PROMPT_TEMPLATE = """You are a friendly, personal study assistant for school students in Nepal.
You explain topics in a natural, conversational tone as if you are teaching the student personally.
IMPORTANT: You must ALWAYS answer in the same language as the question. If the question is in
Nepali (Devanagari), answer in Nepali (नेपालीमा उत्तर देऊ). If the question is in English, answer
in English. Never switch to Hindi just because the text uses the Devanagari script.
You base your answers ONLY on the provided context from the student's selected textbook chapters,
but you do NOT just quote or copy the text — you explain it in your own words, give clear examples,
and keep it engaging and easy to understand. For mathematics and science, show clear step-by-step
reasoning. If the context does not contain the answer, say so honestly and suggest related topics
that ARE in the chapters, rather than guessing.

Context:
{context}

Question: {input}

Helpful, personal answer:"""


def chat_answer(store, question, provider):
    """Run RAG over the store and return (answer, sources)."""
    llm = get_llm(provider)
    prompt_template = PromptTemplate(
        template=CHAT_PROMPT_TEMPLATE, input_variables=["context", "input"]
    )
    combine_docs_chain = create_stuff_documents_chain(llm, prompt_template)
    rag_chain = create_retrieval_chain(
        store.as_retriever(search_kwargs={"k": 5}),
        combine_docs_chain,
    )
    response = rag_chain.invoke({"input": question})
    answer = response["answer"]
    sources = []
    for i, doc in enumerate(response.get("context", []), 1):
        meta = doc.metadata
        src = os.path.basename(meta.get("source", "unknown"))
        page = meta.get("page", 0) + 1
        chapter = meta.get("chapter", "?")
        sources.append(f"[{i}] {src} | Ch: {chapter} | p.{page}: {doc.page_content[:150]}...")
    return answer, sources


# ---------------------------------------------------- LLM resource generation


RESOURCE_SCHEMAS = {
    "Summary": (
        '{"overview": "<short paragraph>", "concepts": ["...", "..."], '
        '"takeaways": ["...", "..."]} — 3-5 concepts and 3 takeaways.'
    ),
    "Key Points": '{"points": ["...", "..."]} — 5-8 concise key points.',
    "Key Terms": '{"terms": [{"term": "...", "definition": "..."}]} — 6-10 terms.',
    "Vocabulary": (
        '{"items": [{"term": "...", "meaning": "...", "example": "..."}]} — 5-8 items.'
    ),
    "Flashcards": (
        '{"cards": [{"front": "<question or term>", "back": "<answer or definition>"}]} '
        "— 6-10 cards."
    ),
    "MCQ": (
        '{"questions": [{"q": "...", "options": ["a", "b", "c", "d"], "answer": "<one option>", '
        '"explanation": "..."}]} — 5 questions with 4 options each.'
    ),
    "Questions": '{"questions": [{"q": "...", "a": "..."}]} — 4-5 short answer questions.',
    "Real-Life Examples": (
        '{"examples": [{"title": "...", "description": "..."}]} — 3-4 real-life examples.'
    ),
    "Fun Facts": '{"facts": ["...", "..."]} — 3-5 interesting facts.',
    "Group Activity": (
        '{"activity": {"title": "...", "description": "...", "steps": ["...", "..."]}} '
        "— 4-5 steps."
    ),
    "Project Work": (
        '{"project": {"title": "...", "objective": "...", "activities": ["...", "..."]}} '
        "— 3-4 activities."
    ),
    "Mind Map": '{"center": "<main topic>", "branches": ["...", "..."]} — 6 branches.',
    "Slides": (
        '{"slides": [{"title": "...", "subtitle": "...", "bullets": ["...", "..."]}]} '
        "— 6-8 slides."
    ),
    "Points to Remember": '{"points": ["...", "..."]} — 5-8 points.',
    "Videos": (
        '{"videos": [{"title": "...", "url": "", "desc": "..."}]} — 2-3 suggested videos.'
    ),
}

SYSTEM_PROMPT = (
    "You are a study assistant that builds learning resources for Nepali school textbooks. "
    "You ALWAYS respond with a single valid JSON object and nothing else. "
    "Answer in the same language as the provided textbook text (Nepali if Devanagari, "
    "otherwise English). "
    "GROUNDING RULE: Every fact, question, term, example and answer you produce MUST be "
    "taken directly from the TEXTBOOK CONTEXT below. Never invent, guess or add information "
    "that is not present in the context. If the context does not contain enough material for "
    "an item, omit that item rather than making something up."
)

EXPECTED = {
    "Summary": {"overview": str, "concepts": list, "takeaways": list},
    "Key Points": {"points": list},
    "Key Terms": {"terms": list},
    "Vocabulary": {"items": list},
    "Flashcards": {"cards": list},
    "MCQ": {"questions": list},
    "Questions": {"questions": list},
    "Real-Life Examples": {"examples": list},
    "Fun Facts": {"facts": list},
    "Group Activity": {"activity": dict},
    "Project Work": {"project": dict},
    "Mind Map": {"center": str, "branches": list},
    "Slides": {"slides": list},
    "Points to Remember": {"points": list},
    "Videos": {"videos": list},
}


def _extract_json(text):
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


def _repair(resource_type, data):
    if not isinstance(data, dict):
        return None
    expected = EXPECTED.get(resource_type)
    if expected is None:
        return None
    for key, typ in expected.items():
        if not isinstance(data.get(key), typ):
            return None
        if typ is list and not data[key]:
            return None
        if typ is str and not str(data[key]).strip():
            return None
    return data


def _retrieve(store, query, k=8):
    try:
        return store.as_retriever(search_kwargs={"k": k}).invoke(query)
    except Exception:
        return []


def generate_resource(resource_type, store, label, provider):
    """Generate a learning resource from the real textbook content via LLM.

    Falls back to a text-derived resource if the LLM call fails or returns invalid JSON.
    """
    schema = RESOURCE_SCHEMAS.get(resource_type)
    if schema is None or store is None:
        return _text_fallback(resource_type, label)

    docs = _retrieve(store, f"{resource_type}: {label or resource_type}", k=10)
    context = "\n\n".join(d.page_content for d in docs)[:9000]
    if not context.strip():
        return _text_fallback(resource_type, label, store)

    prompt = (
        f"RESOURCE TYPE: {resource_type}\n"
        f"SELECTED CHAPTER: {label}\n\n"
        f"TEXTBOOK CONTEXT (base ALL content strictly on this):\n{context}\n\n"
        f"Return ONLY valid JSON matching this shape:\n{schema}\n"
        f"Do not wrap in markdown. Do not add text before or after the JSON."
    )
    try:
        llm = get_llm(provider)
        response = llm.invoke(
            [("system", SYSTEM_PROMPT), ("human", prompt)]
        )
        data = _repair(resource_type, _extract_json(response.content))
        if data:
            data["type"] = resource_type
            data["topic"] = label
            return data
    except Exception:
        pass
    return _text_fallback(resource_type, label, store)


# ------------------------------------------------------------ text fallback


def _sentences(text, limit=200):
    parts = re.split(r"[।\n]+|(?<=[.!?])\s+", text)
    out = []
    for p in parts:
        p = re.sub(r"\s+", " ", p).strip(" \t\r\n-–—.:|")
        if len(p) >= 12:
            out.append(p[: limit].rstrip())
        if len(out) >= 8:
            break
    return out


def _clean_docs(store, label):
    if store is None:
        return ""
    parts = [d.page_content for d in _retrieve(store, label or "summary", k=10)]
    return "\n".join(parts)[:6000]


def _text_fallback(resource_type, label, store=None):
    """Deterministic resource built from the actual retrieved chapter text (no LLM)."""
    text = label if isinstance(label, str) else ""
    if store is not None:
        docs = _retrieve(store, text or resource_type, k=10)
        if docs:
            text = "\n".join(d.page_content for d in docs)
    sentences = _sentences(text) or ["This topic is covered in the selected chapter."]
    points = sentences[:6]
    overview = text[:600].strip() or "Summary of the selected chapter."
    if resource_type == "Summary":
        return {"type": "Summary", "topic": label, "overview": overview,
                "concepts": points[:5], "takeaways": points[:3]}
    if resource_type == "Key Points":
        return {"type": "Key Points", "topic": label, "points": points}
    if resource_type == "Points to Remember":
        return {"type": "Points to Remember", "topic": label, "points": points}
    if resource_type == "Key Terms":
        return {"type": "Key Terms", "topic": label, "terms": [
            {"term": p.split(" ")[0], "definition": p} for p in points[:5]]}
    if resource_type == "Vocabulary":
        return {"type": "Vocabulary", "topic": label, "items": [
            {"term": p.split(" ")[0], "meaning": p, "example": ""} for p in points[:5]]}
    if resource_type == "Flashcards":
        return {"type": "Flashcards", "topic": label, "cards": [
            {"front": p.split(" ")[0], "back": p} for p in points[:6]]}
    if resource_type == "MCQ":
        qs = []
        for p in points[:3]:
            distractors = [s for s in points if s != p][:3]
            while len(distractors) < 3:
                distractors.append("The answer is not present in the chapter text.")
            qs.append({
                "q": f"According to the chapter, which of these is correct?",
                "options": [p] + distractors,
                "answer": p,
                "explanation": p,
            })
        return {"type": "MCQ", "topic": label, "questions": qs}
    if resource_type == "Questions":
        return {"type": "Questions", "topic": label, "questions": [
            {"q": f"Explain: {p}", "a": p} for p in points[:4]]}
    if resource_type == "Real-Life Examples":
        return {"type": "Real-Life Examples", "topic": label, "examples": [
            {"title": f"Example {i + 1}", "description": p} for i, p in enumerate(points[:3])]}
    if resource_type == "Fun Facts":
        return {"type": "Fun Facts", "topic": label, "facts": points[:4]}
    if resource_type == "Mind Map":
        return {"type": "Mind Map", "topic": label, "center": label,
                "branches": points[:6]}
    if resource_type == "Slides":
        slides = [{"title": f"Slide {i + 1}", "subtitle": "Selected Chapter", "bullets": [p]}
                  for i, p in enumerate(points[:6])]
        return {"type": "Slides", "topic": label, "slides": slides}
    if resource_type == "Group Activity":
        return {"type": "Group Activity", "topic": label, "activity": {
            "title": f"Activity on {label}", "description": overview,
            "steps": points[:4]}}
    if resource_type == "Project Work":
        return {"type": "Project Work", "topic": label, "project": {
            "title": f"Project: {label}", "objective": overview,
            "activities": points[:3]}}
    if resource_type == "Videos":
        return {"type": "Videos", "topic": label, "videos": [
            {"title": f"Video: {label}", "url": "", "desc": "Watch this topic explained."}]}
    return {"type": resource_type, "topic": label, "note": "Not implemented yet."}


def teacher_resource(resource_type, label):
    """Deterministic teacher scaffolding (pedagogical, not content-grounded)."""
    return {
        "type": resource_type,
        "topic": label,
        "content": [
            {
                "heading": resource_type,
                "text": (
                    f"Teacher guide for the selected chapter: {label}. Adapt to your "
                    "classroom, differentiate by student level, and connect to the "
                    "chapter's learning objectives and exercises."
                ),
            }
        ],
    }


def progress_insight(stats, provider, lang="en"):
    """Short AI study-coach report built from the learner's progress stats.

    Uses the configured LLM; falls back to a warm template when the call fails.
    """
    summary = (
        f"Topics viewed: {stats.get('topics_viewed', 0)}; "
        f"Flashcards completed: {stats.get('flashcards_completed', 0)}; "
        f"MCQs answered: {stats.get('mcqs_completed', 0)}; "
        f"Quiz average score: {stats.get('quiz_avg', 0)}%; "
        f"Projects started: {stats.get('projects', 0)}; "
        f"Learning streak: {stats.get('streak', 0)} days; "
        f"Overall progress: {stats.get('overall', 0)}%."
    )
    language_note = (
        "Answer in Nepali (नेपालीमा उत्तर देऊ)." if lang == "ne"
        else "Answer in English."
    )
    prompt = (
        "You are an encouraging AI study coach for a school student in Nepal. Based on the "
        "learner stats below, write a short warm progress report (2-3 sentences) followed by "
        "ONE specific, actionable next-step recommendation. "
        f"{language_note} Reply with the report only.\n\nLEARNER STATS:\n{summary}"
    )
    try:
        llm = get_llm(provider)
        response = llm.invoke(
            [("system", "You are a warm, concise study coach. Reply with the report only."),
             ("human", prompt)]
        )
        return response.content.strip()
    except Exception:
        return (
            f"Nice work! You have explored {stats.get('topics_viewed', 0)} topic(s), completed "
            f"{stats.get('flashcards_completed', 0)} flashcards, answered {stats.get('mcqs_completed', 0)} "
            f"MCQs and started {stats.get('projects', 0)} project(s) with a {stats.get('streak', 0)}-day "
            "streak. Keep it up — open a Flashcard deck or the Summary next to build momentum!"
        )

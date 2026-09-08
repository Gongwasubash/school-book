"""FastAPI backend for Fly.io deployment — uses Google Drive PDFs + Pinecone + Mistral/Groq."""
from __future__ import annotations

import json
import os
import re
import asyncio
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

# Import Google Drive service (optional — fallback to Supabase Storage on Vercel)
try:
    from gdrive_service import (
        get_all_curriculum,
        search_pdfs_by_class,
        get_chapter_pdf_context,
        list_available_pdfs,
        get_drive_service,
    )
    HAS_GDRIVE = True
except ImportError:
    HAS_GDRIVE = False
    import cloud_services as _supabase

    async def get_all_curriculum():
        return await _supabase.build_curriculum_from_supabase()

    async def list_available_pdfs(class_num: int):
        groups = await _supabase.build_curriculum_from_supabase()
        for g in groups:
            if g.get("class_num") == class_num:
                return g.get("subjects", [])
        return []

    async def search_pdfs_by_class(class_num: int):
        return await list_available_pdfs(class_num)

    async def get_chapter_pdf_context(class_num: int, file_name: str, title: str) -> str:
        chapters = await _supabase.fetch_chapters(class_num, file_name)
        if not chapters:
            raise Exception(f"No chapters found for {file_name} in class {class_num}")
        target = None
        for ch in chapters:
            t = ch.get("title", "")
            if title.lower() in t.lower() or t.lower() in title.lower():
                target = ch
                break
        if not target and chapters:
            target = chapters[0]
        if not target:
            raise Exception(f"Chapter '{title}' not found in {file_name}")
        content = await _supabase.fetch_chapter_content(target["id"])
        if not content or len(content) < 50:
            return ""
        return content

app = FastAPI(title="AI Books RAG API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROVIDERS = ["Groq (openai/gpt-oss-20b)", "OpenCode Zen (minimax-m2.5-free, kimi-k2.5-free)", "Mistral (free)"]

_kb: Dict[str, Any] = {
    "built": False,
    "docs": [],
    "label": None,
    "chunks": 0,
    "book": None,
    "chapters": [],
}


# --- Pydantic Models ---

class ChapterReq(BaseModel):
    class_num: int
    file: str
    chapters: List[Dict[str, Any]]


class ResourceReq(BaseModel):
    type: str
    provider: str = PROVIDERS[0]
    class_num: int = None
    file: str = None
    chapter: str = None
    exclude: List[str] = []


class ChatReq(BaseModel):
    message: str
    provider: str = PROVIDERS[0]
    class_num: int = None
    file: str = None
    chapter: str = None


class ProgressReq(BaseModel):
    action: str
    n: int = 1
    correct: bool = True
    score: int = 0
    total: int = 0
    title: str = ""
    topic: str = ""


class NotebookReq(BaseModel):
    class_num: int
    file: str
    chapter: Dict[str, Any]
    language: str = ""
    provider: str = PROVIDERS[0]


class LoginReq(BaseModel):
    username: str
    password: str


class ExerciseReq(BaseModel):
    class_num: int
    file: str
    chapter: Dict[str, Any]
    language: str = ""
    provider: str = PROVIDERS[0]
    exclude: List[str] = []


# --- Error streaming helper ---

async def _error_stream(message: str):
    yield f"data: {json.dumps({'error': message})}\n\n"


# --- Health & Providers ---

@app.get("/api/health")
def health():
    return {"ok": True, "version": "3.0.0", "backend": "vercel", "source": "Supabase Storage"}


@app.get("/api/providers")
def providers():
    return {"providers": PROVIDERS}


@app.post("/api/login")
async def login(req: LoginReq):
    import httpx
    supabase_url = os.environ.get("SUPABASE_URL", "")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not supabase_url or not service_key:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{supabase_url}/rest/v1/rpc/login",
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
                "Content-Type": "application/json",
            },
            json={"p_username": req.username, "p_password": req.password},
            timeout=10,
        )
        data = resp.json()
        if isinstance(data, dict) and data.get("success"):
            return {"ok": True, "user": data["user"]}
        error_msg = data.get("error", "Login failed") if isinstance(data, dict) else "Login failed"
        raise HTTPException(status_code=401, detail=error_msg)


@app.get("/api/kb/status")
def kb_status():
    return {
        "built": _kb["built"],
        "label": _kb["label"],
        "chunks": _kb["chunks"],
    }


# --- Books/Curriculum ---

@app.get("/api/books")
async def books():
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        groups = await asyncio.get_event_loop().run_in_executor(pool, lambda: asyncio.run(get_all_curriculum()))
    return {
        "root": "gdrive",
        "source": "SchoolBooks folder on Google Drive",
        "groups": groups,
    }


@app.get("/api/books/{group_id}/subjects")
async def subjects(group_id: str):
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        groups = await asyncio.get_event_loop().run_in_executor(pool, lambda: asyncio.run(get_all_curriculum()))
    for g in groups:
        if g["id"] == group_id:
            return g
    raise HTTPException(status_code=404, detail="Group not found")


# --- Chapters ---

@app.get("/api/chapters")
async def chapters(class_num: int, file: str):
    """List chapters for a book from Supabase chapters table."""
    try:
        ch_list = await _supabase.fetch_chapters(class_num, file)
        return {"chapters": ch_list}
    except Exception:
        return {"chapters": []}


# --- KB Build ---

@app.post("/api/kb/build")
async def kb_build(req: ChapterReq):
    chapter_titles = [c.get("title", "") for c in req.chapters]
    
    # Fetch context from Google Drive PDFs
    contexts = []
    for title in chapter_titles:
        try:
            ctx = await get_chapter_pdf_context(req.class_num, req.file, title)
            if ctx:
                contexts.append({"title": title, "content": ctx})
        except Exception as e:
            continue
    
    if not contexts:
        raise HTTPException(status_code=422, detail="No extractable text in selected chapters")
    
    _kb["built"] = True
    _kb["docs"] = contexts
    _kb["chunks"] = len(contexts)
    _kb["book"] = {"class": req.class_num, "file": req.file}
    _kb["chapters"] = req.chapters
    _kb["label"] = f"Class {req.class_num} — {req.file}"
    if chapter_titles:
        _kb["label"] += f" ({', '.join(chapter_titles[:3])})"
    
    return {"built": True, "chunks": len(contexts), "label": _kb["label"]}


async def _stream_kb_build(class_num: int, file: str, chapters: List[Dict]):
    chapter_titles = [c.get("title", "") for c in chapters]
    yield f"data: {json.dumps({'step': 'fetch', 'message': 'Fetching chapters from Google Drive…'})}\n\n"
    
    contexts = []
    for title in chapter_titles:
        try:
            ctx = await get_chapter_pdf_context(class_num, file, title)
            if ctx:
                contexts.append({"title": title, "content": ctx})
                yield f"data: {json.dumps({'step': 'fetched', 'chapter': title})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'step': 'error', 'chapter': title, 'error': str(e)})}\n\n"
    
    if not contexts:
        yield f"data: {json.dumps({'error': 'No extractable text in chapters'})}\n\n"
        return
    
    _kb["built"] = True
    _kb["docs"] = contexts
    _kb["chunks"] = len(contexts)
    _kb["book"] = {"class": class_num, "file": file}
    _kb["chapters"] = chapters
    _kb["label"] = f"Class {class_num} — {file}"
    
    yield f"data: {json.dumps({'complete': True, 'chunks': len(contexts), 'label': _kb['label']})}\n\n"


@app.post("/api/kb/build/stream")
async def kb_build_stream(req: ChapterReq):
    return StreamingResponse(
        _stream_kb_build(req.class_num, req.file, req.chapters),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# --- Resource Generation (MCQ, Quiz, etc.) ---

TEACHER_RESOURCES = [
    "Lesson Plan", "Teaching Notes", "Classroom Activity",
    "Assignment", "Quiz", "Discussion Questions", "Assessment Rubric",
]


def _teacher_resource(type_: str, label: str) -> dict:
    templates = {
        "Lesson Plan": {"type": "Lesson Plan", "objective": f"Students will learn key concepts from {label}", "duration": "45 minutes", "materials": ["Textbook", "Whiteboard"], "activities": [{"name": "Introduction", "time": "10 min", "description": "Review previous lesson"}, {"name": "Main Activity", "time": "25 min", "description": f"Teach concepts from {label}"}, {"name": "Assessment", "time": "10 min", "description": "Quick quiz"}]},
        "Teaching Notes": {"type": "Teaching Notes", "chapter": label, "key_points": [], "common_misconceptions": [], "extension_activities": []},
        "Classroom Activity": {"type": "Classroom Activity", "chapter": label, "activity_name": "", "instructions": "", "materials_needed": []},
        "Assignment": {"type": "Assignment", "chapter": label, "questions": [], "due_date": ""},
        "Quiz": {"type": "Quiz", "chapter": label, "questions": []},
        "Discussion Questions": {"type": "Discussion Questions", "chapter": label, "questions": []},
        "Assessment Rubric": {"type": "Assessment Rubric", "chapter": label, "criteria": []},
    }
    return templates.get(type_, {"type": type_, "chapter": label})


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1:]
        if t.endswith("```"):
            t = t[:-3].strip()
    return t


def _try_parse_json(result: str):
    text = _strip_fences(result)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise


def _detect_language(text: str) -> str:
    """Detect if content is Nepali (Devanagari) or English."""
    sample = text[:3000]
    devanagari_count = sum(1 for c in sample if '\u0900' <= c <= '\u097f')
    latin_count = sum(1 for c in sample if 'a' <= c.lower() <= 'z')
    total = devanagari_count + latin_count
    if total == 0:
        return "en"
    devanagari_ratio = devanagari_count / total
    return "ne" if devanagari_ratio > 0.3 else "en"


async def _generate_from_text(type_: str, context: str, label: str, provider: str) -> dict:
    lang = _detect_language(context)
    lang_hint = " Respond in Nepali (Devanagari script). Match the language of the source content." if lang == "ne" else " Respond in English. Match the language of the source content."
    schemas = {
        "MCQ": '{"multiple_choice_questions":[{"question":"...","options":["A","B","C","D"],"correct_answer":"A"}]}',
        "Summary": '{"overview":"...","concepts":["..."],"takeaways":["..."]}',
        "Key Points": '{"points":["..."]}',
        "Points to Remember": '{"points":["..."]}',
        "Key Terms": '{"terms":[{"term":"...","definition":"..."}]}',
        "Vocabulary": '{"items":[{"term":"...","meaning":"...","example":"..."}]}',
        "Flashcards": '{"cards":[{"front":"...","back":"..."}]}',
        "Questions": '{"questions":[{"q":"...","a":"..."}]}',
        "Real-Life Examples": '{"examples":[{"title":"...","description":"..."}]}',
        "Fun Facts": '{"facts":["..."]}',
        "Group Activity": '{"activity":{"title":"...","description":"...","steps":["..."]}}',
        "Project Work": '{"project":{"title":"...","objective":"...","activities":["..."]}}',
        "Mind Map": '{"root":{"id":"root-1","title":"...","summary":"...","branches":[{"id":"branch-1","label":"...","summary":"...","children":[{"id":"sub-1-1","label":"...","details":"...","sourceQuote":"..."}]}]}}',
    }
    schema_hint = schemas.get(type_, "")
    prompt = (
        f"Generate a {type_} based ONLY on the following textbook content.{lang_hint}\n\n"
        f"Chapter: {label}\n\nContent:\n{context[:12000]}\n\n"
        f"Return ONLY valid JSON in this exact format: {schema_hint}"
    )
    result = await _llm_complete(prompt, "You are an educational content generator. Use ONLY the provided content.", provider)
    try:
        return _try_parse_json(result)
    except (json.JSONDecodeError, ValueError):
        return {"type": type_, "chapter": label, "raw": result}


async def _stream_from_text(type_: str, context: str, label: str, provider: str, exclude: List[str] = None):
    lang = _detect_language(context)
    lang_hint = " Respond in Nepali (Devanagari script). Match the language of the source content." if lang == "ne" else " Respond in English. Match the language of the source content."
    exclude_hint = ""
    if exclude:
        exclude_list = "\n".join(f"- {item[:80]}" for item in exclude[:30])
        exclude_hint = f"\n\nDO NOT repeat these already-generated items:\n{exclude_list}\nGenerate NEW and DIFFERENT content only."
    schemas = {
        "MCQ": '{"multiple_choice_questions":[{"question":"...","options":["A","B","C","D"],"correct_answer":"A"}]}',
        "Summary": '{"overview":"...","concepts":["..."],"takeaways":["..."]}',
        "Key Points": '{"points":["..."]}',
        "Points to Remember": '{"points":["..."]}',
        "Key Terms": '{"terms":[{"term":"...","definition":"..."}]}',
        "Vocabulary": '{"items":[{"term":"...","meaning":"...","example":"..."}]}',
        "Flashcards": '{"cards":[{"front":"...","back":"..."}]}',
        "Questions": '{"questions":[{"q":"...","a":"..."}]}',
        "Real-Life Examples": '{"examples":[{"title":"...","description":"..."}]}',
        "Fun Facts": '{"facts":["..."]}',
        "Group Activity": '{"activity":{"title":"...","description":"...","steps":["..."]}}',
        "Project Work": '{"project":{"title":"...","objective":"...","activities":["..."]}}',
        "Mind Map": '{"root":{"id":"root-1","title":"...","summary":"...","branches":[{"id":"branch-1","label":"...","summary":"...","children":[{"id":"sub-1-1","label":"...","details":"...","sourceQuote":"..."}]}]}}',
        "Lesson Plan": '{"lesson_plan":{"title":"...","grade_level":"...","subject":"...","duration":"45 minutes","learning_objectives":["..."],"materials":["..."],"previous_knowledge":"...","phases":[{"name":"Warm-up / Introduction","time":"10 min","teacher_activity":"...","student_activity":"..."},{"name":"Presentation","time":"15 min","teacher_activity":"...","student_activity":"..."},{"name":"Guided Practice","time":"10 min","teacher_activity":"...","student_activity":"..."},{"name":"Assessment / Evaluation","time":"5 min","teacher_activity":"...","student_activity":"..."},{"name":"Homework / Closure","time":"5 min","teacher_activity":"...","student_activity":"..."}],"differentiation":{"struggling_students":"...","advanced_students":"..."}}}',
        "Teaching Notes": '{"notes":{"chapter":"...","key_points":["..."],"common_misconceptions":[{"misconception":"...","correction":"..."}],"teaching_tips":["..."],"difficult_topics":["..."],"board_work_suggestions":["..."]}}',
        "Classroom Activity": '{"activity_plan":{"title":"...","objective":"...","duration":"30 minutes","group_size":"...","materials_needed":["..."],"setup_instructions":["..."],"steps":["..."],"debrief_questions":["..."]}}',
        "Assignment": '{"assignment":{"title":"...","instructions":"...","total_marks":20,"due_date":"...","questions":[{"q":"...","marks":5}]}}',
        "Quiz": '{"quiz":{"title":"...","duration":"20 minutes","total_marks":20,"questions":[{"q":"...","options":["A","B","C","D"],"answer":"A","marks":2}]}}',
        "Discussion Questions": '{"discussion":{"topic":"...","questions":[{"q":"...","hint":"..."}]}}',
        "Assessment Rubric": '{"rubric":{"task":"...","criteria":[{"criterion":"...","excellent":"...","good":"...","satisfactory":"...","needs_improvement":"...","weight":"25%"}]}}',
    }
    schema_hint = schemas.get(type_, "")
    min_counts = {
        "MCQ": "at least 5 multiple choice questions",
        "Summary": "a detailed overview plus at least 5 concepts and at least 5 takeaways",
        "Key Points": "at least 8 key points",
        "Points to Remember": "at least 8 points",
        "Key Terms": "at least 6 terms with definitions",
        "Vocabulary": "at least 6 vocabulary items",
        "Flashcards": "at least 6 flashcards",
        "Questions": "at least 5 questions with answers",
        "Real-Life Examples": "at least 5 real-life examples",
        "Fun Facts": "at least 6 fun facts",
        "Group Activity": "an activity with at least 5 steps",
        "Project Work": "a project with at least 5 activities",
        "Mind Map": "a hierarchical tree with 3-5 main branches, each with 2-4 sub-nodes containing details and source quotes",
        "Lesson Plan": "a complete lesson plan with at least 3 learning objectives and all 5 teaching phases (Warm-up, Presentation, Guided Practice, Assessment, Homework) with detailed teacher and student activities for each phase",
        "Teaching Notes": "at least 6 key points, at least 3 common misconceptions with corrections, at least 4 teaching tips, at least 3 difficult topics and at least 3 board work suggestions",
        "Classroom Activity": "a complete activity plan with objective, materials, setup instructions, at least 6 steps and at least 3 debrief questions",
        "Assignment": "an assignment with clear instructions and at least 8 questions with marks",
        "Quiz": "a quiz with at least 10 questions each having 4 options, an answer and marks",
        "Discussion Questions": "at least 8 discussion questions each with a hint for the teacher",
        "Assessment Rubric": "a rubric with at least 5 criteria each rated across excellent, good, satisfactory and needs improvement levels",
    }
    min_hint = min_counts.get(type_, "")
    prompt = (
        f"Generate a {type_} based ONLY on the following textbook content.{lang_hint}{exclude_hint}\n\n"
        f"You MUST generate {min_hint}. Do not return fewer items.\n\n"
        f"Chapter: {label}\n\nContent:\n{context[:12000]}\n\n"
        f"Return ONLY valid JSON in this exact format: {schema_hint}"
    )
    async for event in _stream_llm(
        [{"role": "user", "content": prompt}],
        "You are an educational content generator. Use ONLY the provided content.",
        done_key="complete",
    ):
        yield event


@app.post("/api/resource")
async def make_resource(req: ResourceReq):
    if req.type == "Progress":
        return {"insight": "No progress data in serverless mode."}
    
    chapter_title = req.chapter or req.type
    context = ""
    if req.class_num and req.file:
        try:
            context = await get_chapter_pdf_context(req.class_num, req.file, chapter_title)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch chapter: {e}")
    
    if not context:
        raise HTTPException(status_code=422, detail="Could not fetch chapter content")
    
    return await _generate_from_text(req.type, context, chapter_title, req.provider)


@app.post("/api/resource/stream")
async def resource_stream(req: ResourceReq):
    if req.type == "Progress":
        payload = {"insight": "No progress data in serverless mode."}
        return StreamingResponse(
            _yield_complete(payload),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    
    chapter_title = req.chapter or req.type
    context = ""
    try:
        if req.class_num and req.file:
            context = await get_chapter_pdf_context(req.class_num, req.file, chapter_title)
    except Exception as e:
        return StreamingResponse(
            _error_stream(f"Failed to fetch chapter: {e}"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    
    if not context:
        return StreamingResponse(
            _error_stream("Could not fetch chapter content"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    
    return StreamingResponse(
        _stream_from_text(req.type, context, chapter_title, req.provider, req.exclude),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# --- Notebook Generation ---

@app.post("/api/notebook")
async def notebook(req: NotebookReq):
    try:
        context = await get_chapter_pdf_context(req.class_num, req.file, req.chapter.get("title", ""))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chapter: {e}")
    if not context:
        raise HTTPException(status_code=422, detail="Could not fetch chapter content")
    
    prompt = (
        f"Generate study notes / slide deck for this chapter.\n\n"
        f"Chapter: {req.chapter.get('title', '')}\n\nContent:\n{context[:12000]}\n\n"
        f"Return JSON: {{\"title\": \"...\", \"slides\": [{{\"heading\": \"...\", \"bullets\": [\"...\"], \"notes\": \"...\"}}]}}"
    )
    result = await _llm_complete(
        prompt, 
        "You are an educational content generator. Create concise, student-friendly study notes.", 
        req.provider
    )
    try:
        return _try_parse_json(result)
    except (json.JSONDecodeError, ValueError):
        return {"title": req.chapter.get("title", ""), "slides": [{"heading": "Notes", "bullets": [], "notes": result}]}


@app.post("/api/notebook/stream")
async def notebook_stream(req: NotebookReq):
    try:
        context = await get_chapter_pdf_context(req.class_num, req.file, req.chapter.get("title", ""))
    except Exception as e:
        return StreamingResponse(
            _error_stream(f"Failed to fetch chapter: {e}"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    if not context:
        return StreamingResponse(
            _error_stream("Could not fetch chapter content"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    
    prompt = (
        f"Generate study notes / slide deck for this chapter.\n\n"
        f"Chapter: {req.chapter.get('title', '')}\n\nContent:\n{context[:12000]}\n\n"
        f"Return JSON: {{\"title\": \"...\", \"slides\": [{{\"heading\": \"...\", \"bullets\": [\"...\"], \"notes\": \"...\"}}]}}"
    )
    return StreamingResponse(
        _stream_llm(
            [{"role": "user", "content": prompt}],
            "You are an educational content generator. Output ONLY valid JSON, no markdown fences, no explanations.",
            done_key="complete",
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# --- Exercise Generation ---

@app.post("/api/exercise")
async def exercise(req: ExerciseReq):
    try:
        context = await get_chapter_pdf_context(req.class_num, req.file, req.chapter.get("title", ""))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chapter: {e}")
    if not context:
        raise HTTPException(status_code=422, detail="Could not fetch chapter content")
    
    lang_hint = f" in {req.language}" if req.language else ""
    if not lang_hint:
        lang = _detect_language(context)
        lang_hint = " Respond in Nepali (Devanagari script)." if lang == "ne" else " Respond in English."
    exclude_hint = ""
    if req.exclude:
        exclude_list = "\n".join(f"- {q}" for q in req.exclude[:20])
        exclude_hint = f"\n\nDO NOT repeat these already-generated questions:\n{exclude_list}\nGenerate NEW and DIFFERENT questions only."
    prompt = (
        f"Below is the FULL TEXT of a textbook chapter. Your task is to find every exercise, question, problem, "
        f"activity, and assignment that appears in this chapter text, and solve each one with a complete detailed answer. "
        f"If there are NO exercises in the chapter, create 5 practice questions based on the content and answer them.{lang_hint}{exclude_hint}\n\n"
        f"Chapter: {req.chapter.get('title', '')}\n\n"
        f"=== CHAPTER TEXT START ===\n{context[:8000]}\n=== CHAPTER TEXT END ===\n\n"
        f"IMPORTANT: Use the chapter text above. Generate exactly 5 NEW questions. Extract actual exercises if present, otherwise create practice questions from the content.\n"
        f'Return JSON: {{"title": "...", "questions": [{{"question": "the exercise or practice question", "answer": "detailed solution", "explanation": "why this answer"}}]}}'
    )
    result = await _llm_complete(prompt, "You are an educational exercise solver. Generate exactly 5 NEW questions with answers. Never repeat previously generated questions. Output ONLY valid JSON.", req.provider)
    try:
        return _try_parse_json(result)
    except (json.JSONDecodeError, ValueError):
        return {"title": req.chapter.get("title", ""), "questions": [{"question": "Exercise", "answer": result, "explanation": ""}]}


@app.post("/api/exercise/stream")
async def exercise_stream(req: ExerciseReq):
    try:
        context = await get_chapter_pdf_context(req.class_num, req.file, req.chapter.get("title", ""))
    except Exception as e:
        return StreamingResponse(
            _error_stream(f"Failed to fetch chapter: {e}"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    if not context:
        return StreamingResponse(
            _error_stream("Could not fetch chapter content"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    
    lang_hint = f" in {req.language}" if req.language else ""
    if not lang_hint:
        lang = _detect_language(context)
        lang_hint = " Respond in Nepali (Devanagari script)." if lang == "ne" else " Respond in English."
    exclude_hint = ""
    if req.exclude:
        exclude_list = "\n".join(f"- {q}" for q in req.exclude[:20])
        exclude_hint = f"\n\nDO NOT repeat these already-generated questions:\n{exclude_list}\nGenerate NEW and DIFFERENT questions only."
    prompt = (
        f"Below is the FULL TEXT of a textbook chapter. Your task is to find every exercise, question, problem, "
        f"activity, and assignment that appears in this chapter text, and solve each one with a complete detailed answer. "
        f"If there are NO exercises in the chapter, create 5 practice questions based on the content and answer them.{lang_hint}{exclude_hint}\n\n"
        f"Chapter: {req.chapter.get('title', '')}\n\n"
        f"=== CHAPTER TEXT START ===\n{context[:8000]}\n=== CHAPTER TEXT END ===\n\n"
        f"IMPORTANT: Use the chapter text above. Generate exactly 5 NEW questions. Extract actual exercises if present, otherwise create practice questions from the content.\n"
        f'Return JSON: {{"title": "...", "questions": [{{"question": "the exercise or practice question", "answer": "detailed solution", "explanation": "why this answer"}}]}}'
    )
    return StreamingResponse(
        _stream_llm(
            [{"role": "user", "content": prompt}],
            "You are an educational exercise solver. Generate exactly 5 NEW questions with answers. Never repeat previously generated questions. Output ONLY valid JSON, no markdown fences.",
            done_key="complete",
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# --- Chat ---

@app.post("/api/chat")
async def chat(req: ChatReq):
    docs = _kb["docs"]
    # Stateless fallback: fetch from PDF if no in-memory KB
    if not docs and req.class_num and req.file and req.chapter:
        try:
            context = await get_chapter_pdf_context(req.class_num, req.file, req.chapter)
            if context:
                docs = [{"title": req.chapter, "content": context}]
        except Exception:
            pass
    
    if not docs:
        raise HTTPException(status_code=409, detail="No knowledge base built yet")
    
    context = "\n\n".join(d.get("content", "") for d in docs[:20])[:12000]
    lang = _detect_language(context)
    lang_hint = " Respond in Nepali (Devanagari script)." if lang == "ne" else " Respond in English."
    answer = await _llm_complete(
        f"Based on this textbook content:\n{context}\n\nQuestion: {req.message}{lang_hint}",
        "You are a friendly study assistant for students. Always respond in the same language as the source content.",
        req.provider,
    )
    return {"answer": answer, "sources": []}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatReq):
    docs = _kb["docs"]
    if not docs and req.class_num and req.file and req.chapter:
        try:
            context = await get_chapter_pdf_context(req.class_num, req.file, req.chapter)
            if context:
                docs = [{"title": req.chapter, "content": context}]
        except Exception:
            pass
    
    if not docs:
        return StreamingResponse(
            _error_stream("No knowledge base built yet"),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    
    context = "\n\n".join(d.get("content", "") for d in docs[:20])[:12000]
    return StreamingResponse(
        _stream_chat(docs, req.message, req.provider),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# --- Math ---

@app.post("/api/math/stream")
async def math_stream(req: ChatReq):
    return StreamingResponse(
        _stream_math(req.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# --- Progress ---

@app.get("/api/progress")
def get_progress():
    return {"topics": 0, "cards": 0, "mcqs": 0, "quizzes": 0, "projects": 0}


@app.post("/api/progress/record")
def record_progress(req: ProgressReq):
    return {"ok": True}


@app.post("/api/progress/reset")
def reset_progress():
    return {"ok": True}


# --- Google Auth (placeholder) ---

@app.get("/api/google/auth")
def google_auth():
    return {"authorized": False, "method": "none", "auth_url": None}


@app.get("/api/google/callback")
def google_callback(code: str):
    return {"ok": False, "message": "OAuth not supported in this deployment"}


# --- Not implemented endpoints ---

@app.post("/api/google-slides/create")
async def create_google_slides(req: NotebookReq):
    return {"ok": False, "message": "Google Slides integration requires OAuth setup", "data": None}


# --- LLM Helpers ---

async def _stream_chat(docs: list, question: str, provider: str):
    context = "\n\n".join(d.get("content", "") for d in docs[:20])[:12000]
    lang = _detect_language(context)
    lang_hint = " Respond in the same language as the content (Nepali/Devanagari)." if lang == "ne" else " Respond in English."
    prompt = f"Based on this textbook content:\n{context}\n\nQuestion: {question}\n\nAnswer concisely.{lang_hint}"
    async for event in _stream_llm(
        [{"role": "user", "content": prompt}],
        "You are a friendly study assistant for students. Always respond in the same language as the source content.",
        done_key="complete",
    ):
        yield event


async def _stream_math(question: str):
    prompt = (
        f"Solve step by step: {question}\n\n"
        "Return JSON: {\"steps\": [...], \"answer\": \"...\", \"explanation\": \"...\"}"
    )
    async for event in _stream_llm(
        [{"role": "user", "content": prompt}],
        "You are a precise math tutor. Be concise.",
        done_key="complete",
    ):
        yield event


async def _yield_complete(payload):
    yield f"data: {json.dumps({'complete': True, 'text': json.dumps(payload, ensure_ascii=False)})}\n\n"


async def _stream_llm(messages, system_prompt: str, done_key: str = "done"):
    """Stream LLM response as SSE via Groq (preferred) or Mistral."""
    import aiohttp
    import re
    import asyncio

    def _strip_fences(text):
        text = re.sub(r'^```(?:json)?\s*\n?', '', text.strip())
        text = re.sub(r'\n?```\s*$', '', text.strip())
        return text

    mistral_key = os.environ.get("MISTRAL_API_KEY", "")
    groq_key = os.environ.get("GROQ_API_KEY", "")
    opencode_key = os.environ.get("OPENCODE_API_KEY", "")

    providers = []
    if groq_key:
        providers.append(("https://api.groq.com/openai/v1/chat/completions", groq_key, "openai/gpt-oss-20b"))
    if opencode_key:
        providers.append(("https://opencode.ai/zen/v1/chat/completions", opencode_key, "minimax-m2.5-free"))
        providers.append(("https://opencode.ai/zen/v1/chat/completions", opencode_key, "kimi-k2.5-free"))
    if mistral_key:
        providers.append(("https://api.mistral.ai/v1/chat/completions", mistral_key, "mistral-large-latest"))

    if not providers:
        yield f"data: {json.dumps({'error': 'No LLM API key configured'})}\n\n"
        return

    for url, key, model in providers:
        for attempt in range(2):
            buffer = ""
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json={
                            "model": model,
                            "messages": [{"role": "system", "content": system_prompt}, *messages],
                            "temperature": 0.4,
                            "stream": True,
                        },
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as resp:
                        if resp.status == 429:
                            if attempt == 0:
                                await asyncio.sleep(3)
                                continue
                            break
                        if resp.status != 200:
                            body = (await resp.text())[:300]
                            yield f"data: {json.dumps({'error': f'LLM API error {resp.status}: {body}'})}\n\n"
                            return
                        async for raw in resp.content:
                            line = raw.decode("utf-8", "ignore").strip()
                            if not line.startswith("data: "):
                                continue
                            payload = line[6:]
                            if payload == "[DONE]":
                                break
                            try:
                                chunk = json.loads(payload)
                            except json.JSONDecodeError:
                                continue
                            delta = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content", "")
                            if delta:
                                buffer += delta
                                yield f"data: {json.dumps({'delta': delta})}\n\n"
                yield f"data: {json.dumps({done_key: True, 'text': buffer})}\n\n"
                return
            except Exception as e:
                if attempt == 0:
                    await asyncio.sleep(2)
                    continue
                break

    yield f"data: {json.dumps({'error': 'LLM rate limit exceeded. Please try again shortly.'})}\n\n"


async def _llm_call(url, key, model, prompt, system, timeout_sec=60):
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "temperature": 0.4,
            },
            timeout=aiohttp.ClientTimeout(total=timeout_sec),
        ) as resp:
            data = await resp.json()
            if resp.status == 429:
                raise Exception(f"rate_limited:{resp.status}")
            if resp.status != 200:
                return f"LLM error {resp.status}: {str(data)[:200]}"
            choices = data.get("choices")
            if not choices:
                return f"LLM returned no choices: {str(data)[:200]}"
            return choices[0]["message"]["content"]


async def _llm_complete(prompt: str, system: str, provider: str = "") -> str:
    """Non-streaming LLM call with fallback."""
    import aiohttp

    mistral_key = os.environ.get("MISTRAL_API_KEY", "")
    groq_key = os.environ.get("GROQ_API_KEY", "")
    opencode_key = os.environ.get("OPENCODE_API_KEY", "")

    providers = []
    if groq_key:
        providers.append(("https://api.groq.com/openai/v1/chat/completions", groq_key, "openai/gpt-oss-20b"))
    if opencode_key:
        providers.append(("https://opencode.ai/zen/v1/chat/completions", opencode_key, "minimax-m2.5-free"))
        providers.append(("https://opencode.ai/zen/v1/chat/completions", opencode_key, "kimi-k2.5-free"))
    if "mistral" in provider.lower() and mistral_key:
        providers.append(("https://api.mistral.ai/v1/chat/completions", mistral_key, "mistral-large-latest"))
        if groq_key:
            providers.append(("https://api.groq.com/openai/v1/chat/completions", groq_key, "openai/gpt-oss-20b"))
    elif groq_key:
        providers.append(("https://api.groq.com/openai/v1/chat/completions", groq_key, "openai/gpt-oss-20b"))
        if mistral_key:
            providers.append(("https://api.mistral.ai/v1/chat/completions", mistral_key, "mistral-large-latest"))
    elif mistral_key:
        providers.append(("https://api.mistral.ai/v1/chat/completions", mistral_key, "mistral-large-latest"))
    else:
        return "No LLM API key configured."

    for url, key, model in providers:
        for attempt in range(3):
            try:
                return await _llm_call(url, key, model, prompt, system)
            except Exception as e:
                if "rate_limited" in str(e) and attempt < 2:
                    import asyncio
                    await asyncio.sleep(3)
                    continue
                break
    return "LLM rate limit exceeded. Please try again shortly."


@app.post("/api/mindmap/expand")
async def expand_mindmap_node(payload: dict):
    """Generate sub-nodes for a specific mind map branch."""
    class_num = payload.get("class_num", 7)
    file = payload.get("file", "")
    chapter = payload.get("chapter", "")
    parent_label = payload.get("parent_label", "")
    depth = payload.get("depth", 1)
    exclude = payload.get("exclude", [])

    # Get context from KB
    context = ""
    try:
        kb_key = f"kb_{class_num}_{file}"
        kb = _kb_store.get(kb_key)
        if kb and kb.get("vectors"):
            # Search for relevant content
            results = _search_kb(kb, parent_label, top_k=5)
            context = "\n\n".join([r.get("text", "") for r in results])
    except Exception:
        pass

    if not context:
        context = f"Topic: {parent_label}"

    exclude_hint = ""
    if exclude:
        exclude_list = "\n".join(f"- {item[:60]}" for item in exclude[:20])
        exclude_hint = f"\n\nDO NOT repeat these already-generated items:\n{exclude_list}"

    prompt = f"""You are a knowledge-extraction AI. Generate 3-4 child nodes for the mind map topic: "{parent_label}"

The parent topic is at depth {depth}. Generate child nodes that are more specific and detailed.

Return ONLY valid JSON in this exact format:
{{
  "children": [
    {{
      "id": "unique-id",
      "label": "Sub-topic Name",
      "summary": "Brief 1-sentence summary",
      "details": "Detailed explanation with key facts",
      "sourceQuote": "Optional quote from the source material"
    }}
  ]
}}

{exclude_hint}

Context from source material:
{context[:8000]}

Generate 3-4 child nodes:"""

    provider = payload.get("provider", "groq")
    result = await _llm_complete(prompt, "You are an educational content generator. Output valid JSON only.", provider)

    try:
        parsed = _try_parse_json(result)
        if isinstance(parsed, dict) and "children" in parsed:
            return parsed
        return {"children": []}
    except Exception:
        return {"children": []}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("rag_api:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=False)
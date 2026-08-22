"""Supabase + Pinecone service layer for the Vercel-deployed backend.

Uses new books/chapters tables for Nepal textbooks.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
from langchain_core.documents import Document

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lixjwweoxuzwjajyzqvr.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON = os.environ.get("SUPABASE_ANON_KEY", "")
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
PINECONE_INDEX = os.environ.get("PINECONE_INDEX", "nepal-textbooks")

STORAGE_BASE = f"{SUPABASE_URL}/storage/v1/object/textbooks"
API_BASE = f"{SUPABASE_URL}/rest/v1"


def _headers(key: str = None) -> dict:
    k = key or SUPABASE_KEY or SUPABASE_ANON
    if not k:
        raise RuntimeError("Supabase API key is not configured. Set SUPABASE_SERVICE_KEY env var.")
    return {
        "apikey": k,
        "Authorization": f"Bearer {k}",
        "Content-Type": "application/json",
    }


async def fetch_books() -> List[Dict[str, Any]]:
    """Fetch all books from the books table."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}/books",
            headers=_headers(),
            params={
                "select": "id,class_num,file_name,subject,title,chapter_count,storage_path",
                "order": "class_num,file_name",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_chapters(class_num: int, file_name: str) -> List[Dict[str, Any]]:
    """Fetch chapter titles for a book from the chapters table."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}/chapters",
            headers=_headers(),
            params={
                "select": "id,title,line_start,line_end,page_start,page_end",
                "class_num": f"eq.{class_num}",
                "file_name": f"eq.{file_name}",
                "order": "line_start",
            },
            timeout=15,
        )
        resp.raise_for_status()
        rows = resp.json()
        return [{"id": r["id"], "title": r["title"], "start": r["line_start"], "end": r["line_end"],
                 "start_page": r.get("page_start"), "end_page": r.get("page_end")} for r in rows]


async def fetch_chapter_content(chapter_id: str) -> str:
    """Fetch full content for a single chapter."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{API_BASE}/chapters",
            headers=_headers(),
            params={
                "select": "content",
                "id": f"eq.{chapter_id}",
            },
            timeout=30,
        )
        resp.raise_for_status()
        rows = resp.json()
        if rows and rows[0].get("content"):
            return rows[0]["content"]
        return ""


async def fetch_chapters_by_class_and_file(class_num: int, file_name: str, chapter_title: str = None) -> List[Dict[str, Any]]:
    """Fetch chapters with content for content generation."""
    async with httpx.AsyncClient() as client:
        params = {
            "select": "id,title,content,line_start",
            "class_num": f"eq.{class_num}",
            "file_name": f"eq.{file_name}",
            "order": "line_start",
        }
        if chapter_title:
            params["title"] = f"ilike.*{chapter_title}*"
        resp = await client.get(
            f"{API_BASE}/chapters",
            headers=_headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_documents_for_chapters(
    class_num: int, file: str, chapter_titles: List[str]
) -> List[Document]:
    """Fetch chapter content for selected chapters (Pinecone integration)."""
    all_docs = []
    for title in chapter_titles:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{API_BASE}/chapters",
                headers=_headers(),
                params={
                    "select": "title,content",
                    "class_num": f"eq.{class_num}",
                    "file_name": f"eq.{file}",
                    "title": f"ilike.*{title}*",
                },
                timeout=30,
            )
            resp.raise_for_status()
            rows = resp.json()
            for r in rows:
                if r.get("content"):
                    all_docs.append(Document(
                        page_content=r["content"],
                        metadata={"chapter": r["title"], "source": file, "class_num": class_num},
                    ))
    return all_docs


async def fetch_md_from_storage(storage_path: str) -> str:
    """Download an MD file from Supabase Storage."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/storage/v1/object/textbooks/{storage_path}",
            headers=_headers(SUPABASE_KEY),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.text


async def list_storage_files(folder: str = "") -> List[Dict[str, Any]]:
    """List files in a Supabase Storage folder."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{SUPABASE_URL}/storage/v1/object/list/textbooks",
            headers=_headers(),
            json={"prefix": folder, "limit": 200, "offset": 0},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


def parse_md_chapters(md_text: str) -> List[Dict[str, Any]]:
    """Parse chapter headings from MD text (## headings)."""
    chapters = []
    for i, line in enumerate(md_text.split("\n")):
        m = re.match(r"^##\s+(.+?)(?:\s+\(Pages?\s+(\d+)-(\d+)\))?\s*$", line)
        if m:
            chapters.append({
                "title": m.group(1).strip(),
                "start_page": int(m.group(2)) if m.group(2) else None,
                "end_page": int(m.group(3)) if m.group(3) else None,
                "line": i,
            })
    return chapters


async def fetch_pinecone_chapters(class_num: int, file: str) -> List[Document]:
    """Fetch all chunks for a book from Pinecone."""
    if not PINECONE_API_KEY:
        return []
    try:
        from pinecone import Pinecone as _PC
    except ImportError:
        return []

    pc = _PC(api_key=PINECONE_API_KEY)
    index = pc.Index(PINECONE_INDEX)

    docs = []
    try:
        resp = index.query(
            vector=[0.0] * 1024,
            filter={"class_num": {"$eq": class_num}, "file": {"$eq": file}},
            top_k=10000,
            include_metadata=True,
        )
        for match in resp.matches:
            meta = match.metadata or {}
            docs.append(Document(
                page_content=meta.get("content", ""),
                metadata={
                    "chapter": meta.get("chapter_title", ""),
                    "chunk_index": meta.get("chunk_index", 0),
                    "source": file,
                    "class_num": class_num,
                },
            ))
        docs.sort(key=lambda d: d.metadata.get("chunk_index", 0))
    except Exception:
        pass
    return docs


async def fetch_pinecone_chapters_filtered(
    class_num: int, file: str, chapter_titles: List[str]
) -> List[Document]:
    """Fetch filtered chunks from Pinecone by chapter titles."""
    all_docs = await fetch_pinecone_chapters(class_num, file)
    if not chapter_titles:
        return all_docs
    title_set = set(chapter_titles)
    return [d for d in all_docs if d.metadata.get("chapter") in title_set]


async def query_pinecone(
    query_text: str,
    class_num: int = None,
    file: str = None,
    k: int = 5,
) -> List[Document]:
    """Query Pinecone with a text query."""
    if not PINECONE_API_KEY:
        return []
    mistral_key = os.environ.get("MISTRAL_API_KEY", "")
    if not mistral_key:
        return []

    try:
        import httpx as _httpx
        from pinecone import Pinecone as _PC

        async with _httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.mistral.ai/v1/embeddings",
                headers={"Authorization": f"Bearer {mistral_key}", "Content-Type": "application/json"},
                json={"model": "mistral-embed", "input": query_text},
                timeout=30,
            )
            resp.raise_for_status()
            query_embedding = resp.json()["data"][0]["embedding"]

        pc = _PC(api_key=PINECONE_API_KEY)
        index = pc.Index(PINECONE_INDEX)

        query_filter = {}
        if class_num is not None:
            query_filter["class_num"] = {"$eq": class_num}
        if file:
            query_filter["file"] = {"$eq": file}

        result = index.query(
            vector=query_embedding,
            filter=query_filter if query_filter else None,
            top_k=k,
            include_metadata=True,
        )

        docs = []
        for match in result.matches:
            meta = match.metadata or {}
            docs.append(Document(
                page_content=meta.get("content", ""),
                metadata={
                    "chapter": meta.get("chapter_title", ""),
                    "chunk_index": meta.get("chunk_index", 0),
                    "source": meta.get("file", ""),
                    "class_num": meta.get("class_num"),
                    "score": match.score,
                },
            ))
        return docs
    except Exception:
        return []


async def build_curriculum_from_supabase() -> List[Dict[str, Any]]:
    """Build curriculum structure from the books table."""
    books = await fetch_books()
    groups = {}

    for b in books:
        cn = b["class_num"]
        grade_key = f"Class {cn}"
        if grade_key not in groups:
            groups[grade_key] = {
                "id": grade_key.lower().replace(" ", ""),
                "label": grade_key,
                "class_num": cn,
                "subjects": [],
            }
        groups[grade_key]["subjects"].append({
            "file": b["file_name"],
            "subject": b["subject"],
            "class_num": cn,
            "available": True,
            "chapter_count": b.get("chapter_count", 0),
        })

    return sorted(groups.values(), key=lambda g: g["class_num"])

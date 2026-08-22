"""Populate Pinecone with real embeddings from Mistral API. Resumable per-file."""
import re
import time
import json
import os
from openai import OpenAI
from pinecone import Pinecone

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
INDEX_NAME = "nepal-textbooks"
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
EMBEDDING_MODEL = "mistral-embed"
CHUNK_BATCH = 10
EMBED_DIM = 1024
PROGRESS_FILE = "pinecone_progress.json"

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(INDEX_NAME)
mistral = OpenAI(api_key=MISTRAL_API_KEY, base_url="https://api.mistral.ai/v1")

def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed_files": [], "total_vectors": 0}

def save_progress(progress):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f)

def list_storage_files(prefix):
    import httpx
    resp = httpx.post(
        f"{SUPABASE_URL}/storage/v1/object/list/textbooks",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        json={"prefix": prefix, "limit": 200, "offset": 0}, timeout=15,
    )
    resp.raise_for_status()
    return resp.json()

def download_from_storage(path):
    import httpx
    resp = httpx.get(
        f"{SUPABASE_URL}/storage/v1/object/textbooks/{path}",
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text

def parse_md_chapters(md_text):
    chapters = []
    for i, line in enumerate(md_text.split("\n")):
        m = re.match(r"^##\s+(.+?)(?:\s+\(Pages?\s+(\d+)-(\d+)\))?\s*$", line)
        if m:
            chapters.append({"title": m.group(1).strip(), "line_index": i})
    return chapters

def chunk_text(text, chunk_size=500, overlap=50):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks

def get_embeddings(texts):
    all_embs = []
    for i in range(0, len(texts), CHUNK_BATCH):
        batch = texts[i:i + CHUNK_BATCH]
        resp = mistral.embeddings.create(model=EMBEDDING_MODEL, input=batch)
        all_embs.extend([e.embedding for e in resp.data])
        time.sleep(0.15)
    return all_embs

progress = load_progress()
completed = set(progress["completed_files"])
total_vectors = progress["total_vectors"]

# Get all files
all_files = []
for class_num in range(1, 11):
    try:
        files = list_storage_files(f"Class {class_num}/md/")
        for f in files:
            if f["name"].endswith(".md"):
                all_files.append((class_num, f["name"]))
    except Exception as e:
        print(f"Error listing Class {class_num}: {e}")

print(f"Total files: {len(all_files)}, already done: {len(completed)}, vectors so far: {total_vectors}")

for class_num, fname in all_files:
    storage_path = f"Class {class_num}/md/{fname}"
    if storage_path in completed:
        continue

    book_name = fname.replace(".md", "")
    print(f"Processing: {storage_path}")

    try:
        md_text = download_from_storage(storage_path)
    except Exception as e:
        print(f"  Error downloading: {e}")
        continue

    chapters = parse_md_chapters(md_text)
    lines = md_text.split("\n")

    all_chunks = []
    chunk_meta = []

    if not chapters:
        chunks = chunk_text(md_text)
        for i, chunk in enumerate(chunks):
            all_chunks.append(chunk)
            chunk_meta.append({"class_num": class_num, "file": fname, "chapter_title": "Full Book", "chunk_index": i, "content": chunk[:500]})
    else:
        chunk_counter = 0
        for ci, ch in enumerate(chapters):
            start = ch["line_index"]
            end = chapters[ci + 1]["line_index"] if ci + 1 < len(chapters) else len(lines)
            chapter_text = "\n".join(lines[start:end])
            chunks = chunk_text(chapter_text)
            for i, chunk in enumerate(chunks):
                all_chunks.append(chunk)
                chunk_meta.append({"class_num": class_num, "file": fname, "chapter_title": ch["title"], "chunk_index": chunk_counter, "content": chunk[:500]})
                chunk_counter += 1

    if not all_chunks:
        print(f"  No chunks")
        progress["completed_files"].append(storage_path)
        save_progress(progress)
        continue

    # Get embeddings
    try:
        embeddings = get_embeddings(all_chunks)
    except Exception as e:
        print(f"  Error embeddings: {e}")
        break

    # Upsert in batches of 100
    vectors = []
    for i, emb in enumerate(embeddings):
        vectors.append({
            "id": f"{class_num}_{book_name}_{chunk_meta[i]['chunk_index']}",
            "values": emb,
            "metadata": chunk_meta[i],
        })

    file_vectors = 0
    for i in range(0, len(vectors), 100):
        batch = vectors[i:i + 100]
        try:
            index.upsert(vectors=batch)
            file_vectors += len(batch)
        except Exception as e:
            print(f"  Error upserting: {e}")

    total_vectors += file_vectors
    progress["completed_files"].append(storage_path)
    progress["total_vectors"] = total_vectors
    save_progress(progress)
    print(f"  OK: {file_vectors} vectors (total: {total_vectors})")
    time.sleep(0.2)

print(f"\n=== DONE === {total_vectors} total vectors")
print("Stats:", index.describe_index_stats())

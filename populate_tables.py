"""Populate Supabase books and chapters tables from MD files."""
import os
import re
import json
import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
MD_DIR = os.path.join(os.path.dirname(__file__), "textbooks_md")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def parse_subject_from_filename(filename: str) -> str:
    """Extract subject name from filename like 'Class 9 English 2079.md'."""
    name = filename.replace(".md", "")
    # Remove 'Class X - Class X ' prefix
    m = re.match(r"Class \d+ - Class \d+ (.+?)(?:\s+\d{4})?$", name)
    if m:
        return m.group(1).strip()
    # Fallback: remove class prefix
    name = re.sub(r"^Class \d+\s*-?\s*", "", name)
    name = re.sub(r"\s+\d{4}$", "", name)
    return name.strip()


def parse_md_file(filepath: str, class_num: int, file_name: str):
    """Parse an MD file into book + chapters data."""
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    content = "".join(lines)

    # Book title from first # heading
    title_match = re.match(r"^#\s+(.+)$", lines[0].strip() if lines else "", re.MULTILINE)
    title = title_match.group(1).strip() if title_match else file_name.replace(".md", "")

    subject = parse_subject_from_filename(file_name)

    # Parse chapters (## headings)
    chapters = []
    for i, line in enumerate(lines):
        m = re.match(r"^##\s+(.+?)(?:\s+\(Pages?\s+(\d+)-(\d+)\))?\s*$", line)
        if m:
            ch_title = m.group(1).strip()
            page_start = int(m.group(2)) if m.group(2) else None
            page_end = int(m.group(3)) if m.group(3) else None
            chapters.append({
                "title": ch_title,
                "line_start": i,
                "page_start": page_start,
                "page_end": page_end,
            })

    # Set line_end for each chapter
    for j, ch in enumerate(chapters):
        if j + 1 < len(chapters):
            ch["line_end"] = chapters[j + 1]["line_start"]
        else:
            ch["line_end"] = len(lines)

    # Extract content for each chapter
    for ch in chapters:
        start = ch["line_start"]
        end = ch["line_end"]
        ch["content"] = "".join(lines[start:end]).strip()

    storage_path = f"Class {class_num}/md/{file_name}"

    return {
        "class_num": class_num,
        "file_name": file_name,
        "subject": subject,
        "title": title,
        "chapter_count": len(chapters),
        "storage_path": storage_path,
        "chapters": chapters,
    }


def insert_books(books_data):
    """Insert books into Supabase."""
    rows = []
    for b in books_data:
        rows.append({
            "class_num": b["class_num"],
            "file_name": b["file_name"],
            "subject": b["subject"],
            "title": b["title"],
            "chapter_count": b["chapter_count"],
            "storage_path": b["storage_path"],
        })

    # Batch insert
    with httpx.Client() as client:
        resp = client.post(
            f"{SUPABASE_URL}/rest/v1/books",
            headers={**HEADERS, "Prefer": "return=representation"},
            json=rows,
            timeout=30,
        )
        if resp.status_code not in (200, 201):
            print(f"Error inserting books: {resp.status_code} {resp.text[:200]}")
            return []
        return resp.json()


def insert_chapters(chapters_data, book_id_map):
    """Insert chapters in batches."""
    rows = []
    for b in chapters_data:
        book_id = book_id_map.get(f"{b['class_num']}|{b['file_name']}")
        if not book_id:
            continue
        for ch in b["chapters"]:
            rows.append({
                "book_id": book_id,
                "class_num": b["class_num"],
                "file_name": b["file_name"],
                "title": ch["title"],
                "line_start": ch["line_start"],
                "line_end": ch["line_end"],
                "page_start": ch["page_start"],
                "page_end": ch["page_end"],
                "content": ch["content"],
            })

    # Batch insert (50 at a time to avoid payload limits)
    with httpx.Client() as client:
        for i in range(0, len(rows), 50):
            batch = rows[i:i+50]
            resp = client.post(
                f"{SUPABASE_URL}/rest/v1/chapters",
                headers={**HEADERS, "Prefer": "return=minimal"},
                json=batch,
                timeout=60,
            )
            if resp.status_code not in (200, 201):
                print(f"Error inserting chapters batch {i}: {resp.status_code} {resp.text[:200]}")
            else:
                print(f"  Inserted chapters {i+1}-{min(i+50, len(rows))} of {len(rows)}")


def main():
    all_books = []

    for class_dir in sorted(os.listdir(MD_DIR)):
        class_path = os.path.join(MD_DIR, class_dir)
        if not os.path.isdir(class_path):
            continue
        md_path = os.path.join(class_path, "markdown")
        if not os.path.isdir(md_path):
            continue

        cn = int(class_dir.split()[-1])

        for fname in sorted(os.listdir(md_path)):
            if not fname.endswith(".md"):
                continue
            filepath = os.path.join(md_path, fname)
            book_data = parse_md_file(filepath, cn, fname)
            all_books.append(book_data)
            print(f"Parsed: Class {cn} - {book_data['subject']} ({book_data['chapter_count']} chapters)")

    print(f"\nTotal: {len(all_books)} books, {sum(b['chapter_count'] for b in all_books)} chapters")

    # Insert books
    print("\nInserting books...")
    inserted_books = insert_books(all_books)
    print(f"  Inserted {len(inserted_books)} books")

    # Build book_id map
    book_id_map = {}
    for b in inserted_books:
        key = f"{b['class_num']}|{b['file_name']}"
        book_id_map[key] = b["id"]

    # Insert chapters
    print("\nInserting chapters...")
    insert_chapters(all_books, book_id_map)

    print("\nDone!")


if __name__ == "__main__":
    main()

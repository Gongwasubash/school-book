import sys, os, json, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, r'E:\rag sys\medical-chatbot-refactored')

import pymupdf
import textbook_indexer as ti

BOOK_DIR = r'E:\class  1 to 10 book\Nepal Textbooks Grade 1-10'
CACHE_DIR = r'E:\rag sys\medical-chatbot-refactored\chapter_cache'
OUTPUT_DIR = r'E:\rag sys\medical-chatbot-refactored\textbooks_md'

os.makedirs(OUTPUT_DIR, exist_ok=True)

stats = {"books": 0, "chapters": 0, "pages": 0, "skipped": 0}

for cls in range(1, 11):
    cls_dir = os.path.join(BOOK_DIR, f"Class {cls}")
    if not os.path.isdir(cls_dir):
        continue
    for fname in sorted(os.listdir(cls_dir)):
        if not fname.endswith('.pdf'):
            continue
        pdf_path = os.path.join(cls_dir, fname)
        book_name = fname.replace('.pdf', '')
        md_path = os.path.join(OUTPUT_DIR, f"Class {cls} - {book_name}.md")

        if os.path.exists(md_path):
            stats["skipped"] += 1
            continue

        key = ti._cache_key(pdf_path)
        cache_file = os.path.join(CACHE_DIR, f'{key}.json')
        if not os.path.exists(cache_file):
            continue

        with open(cache_file, encoding='utf-8') as f:
            chapters = json.load(f)

        if len(chapters) == 1 and chapters[0]['title'] == 'Whole Book':
            continue

        print(f"Class {cls} - {book_name} ({len(chapters)} chapters)...", end=" ", flush=True)

        md_lines = [f"# Class {cls} - {book_name}\n"]
        md_lines.append(f"*{len(chapters)} chapters*\n")

        book_pages = 0
        for ch in chapters:
            title = ch['title']
            start = ch.get('start', 0)
            end = ch.get('end', 0)
            md_lines.append(f"\n## {title} (Pages {start+1}-{end+1})\n")

            try:
                with pymupdf.open(pdf_path) as doc:
                    end_idx = min(ch.get('end', doc.page_count - 1), doc.page_count - 1)
                    for i in range(ch.get('start', 0), end_idx + 1):
                        try:
                            text = ti._page_text(doc, i)
                        except Exception:
                            text = ""
                        if text.strip():
                            md_lines.append(text.strip())
                            md_lines.append("")
                            book_pages += 1
            except Exception as e:
                md_lines.append(f"[Error loading pages: {e}]\n")

        with open(md_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_lines))

        stats["books"] += 1
        stats["chapters"] += len(chapters)
        stats["pages"] += book_pages
        print(f"OK ({book_pages} pages)")

        time.sleep(0.1)

print(f"\n=== DONE ===")
print(f"Books: {stats['books']} generated, {stats['skipped']} skipped")
print(f"Chapters: {stats['chapters']}")
print(f"Pages: {stats['pages']}")
print(f"Output: {OUTPUT_DIR}")

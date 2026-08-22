"""Upload all MD files from textbooks_md/ to Supabase Storage."""
import os
import sys
import glob
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

MD_ROOT = r"E:\rag sys\medical-chatbot-refactored\nepal_textbooks"

def main():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Find all MD files
    md_files = glob.glob(os.path.join(MD_ROOT, "Class *", "md", "*.md"))
    print(f"Found {len(md_files)} MD files")

    uploaded = 0
    skipped = 0
    errors = 0

    for md_path in sorted(md_files):
        # Build storage path: Class N/markdown/filename.md
        rel = os.path.relpath(md_path, MD_ROOT).replace("\\", "/")
        storage_path = rel

        try:
            with open(md_path, "rb") as f:
                content = f.read()

            # Upload with upsert
            sb.storage.from_("textbooks").upload(
                storage_path,
                content,
                {"content-type": "text/markdown", "upsert": "true"}
            )
            uploaded += 1
            print(f"  Uploaded: {storage_path} ({len(content)} bytes)")
        except Exception as e:
            errors += 1
            print(f"  ERROR: {storage_path}: {e}")

    print(f"\nDone: {uploaded} uploaded, {skipped} skipped, {errors} errors")

if __name__ == "__main__":
    main()

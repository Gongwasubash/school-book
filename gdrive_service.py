"""Google Drive service for fetching PDF files and extracting text."""
import os
import io
import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional
from functools import lru_cache

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# PDF text extraction
import pdfplumber
import fitz  # pymupdf

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CREDENTIALS_FILE = os.environ.get("GDRIVE_CREDENTIALS", "gdrive_credentials.json")
TOKEN_FILE = os.environ.get("GDRIVE_TOKEN", "gdrive_token.json")
ROOT_FOLDER_NAME = "SchoolBooks"
CACHE_DIR = Path(os.environ.get("GDRIVE_CACHE", "gdrive_cache"))

CACHE_DIR.mkdir(exist_ok=True)


def get_drive_service():
    """Get authenticated Google Drive service."""
    from google.oauth2.credentials import Credentials
    
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as token:
            token_data = json.load(token)
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            # Save as JSON
            with open(TOKEN_FILE, 'w') as token:
                json.dump({
                    'token': creds.token,
                    'refresh_token': creds.refresh_token,
                    'token_uri': creds.token_uri,
                    'client_id': creds.client_id,
                    'client_secret': creds.client_secret,
                    'scopes': creds.scopes,
                    'universe_domain': creds.universe_domain,
                }, token)
    
    return build('drive', 'v3', credentials=creds)


def find_root_folder(service) -> Optional[str]:
    """Find the SchoolBooks root folder ID."""
    results = service.files().list(
        q=f"name='{ROOT_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)",
        spaces='drive'
    ).execute()
    folders = results.get('files', [])
    return folders[0]['id'] if folders else None


def list_files_in_folder(service, folder_id: str) -> List[Dict]:
    """List all files in a folder (handles pagination)."""
    files = []
    page_token = None
    while True:
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, parents)",
            pageToken=page_token,
            pageSize=1000
        ).execute()
        files.extend(results.get('files', []))
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    return files


def get_all_pdf_files(service) -> List[Dict]:
    """Recursively get all PDF files from SchoolBooks folder."""
    root_id = find_root_folder(service)
    if not root_id:
        raise ValueError(f"Root folder '{ROOT_FOLDER_NAME}' not found")
    
    all_pdfs = []
    
    def traverse(folder_id: str, path: str = ""):
        files = list_files_in_folder(service, folder_id)
        for f in files:
            full_path = f"{path}/{f['name']}" if path else f['name']
            if f['mimeType'] == 'application/vnd.google-apps.folder':
                traverse(f['id'], full_path)
            elif f['name'].lower().endswith('.pdf'):
                all_pdfs.append({
                    'id': f['id'],
                    'name': f['name'],
                    'path': full_path,
                    'size': int(f.get('size', 0)),
                    'modified': f.get('modifiedTime'),
                    'parents': f.get('parents', [])
                })
    
    traverse(root_id)
    return all_pdfs


@lru_cache(maxsize=128)
def download_pdf_cached(file_id: str) -> bytes:
    """Download PDF file from Google Drive with caching."""
    cache_file = CACHE_DIR / f"{file_id}.pdf"
    if cache_file.exists():
        return cache_file.read_bytes()
    
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    
    pdf_bytes = fh.getvalue()
    cache_file.write_bytes(pdf_bytes)
    return pdf_bytes


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from PDF using pdfplumber (better for structured text)."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            texts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    texts.append(text)
            return "\n\n".join(texts)
    except Exception:
        # Fallback to PyMuPDF
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            texts = [page.get_text() for page in doc]
            doc.close()
            return "\n\n".join(texts)
        except Exception:
            return ""


def extract_chapters_from_pdf_text(pdf_text: str) -> List[Dict]:
    """Parse chapter headings from PDF text (similar to MD parsing)."""
    chapters = []
    for i, line in enumerate(pdf_text.split("\n")):
        line = line.strip()
        # Match patterns like "Chapter 1", "Unit 1", "## Heading", etc.
        import re
        # Common chapter patterns in textbooks
        patterns = [
            r'^(?:Chapter|Unit|Lesson|Section)\s+\d+[:\s]*(.+)$',
            r'^##\s+(.+)$',
            r'^#{1,3}\s+(.+)$',
            r'^(\d+\.\d+\s+.+)$',
            r'^([A-Z][A-Z\s]{3,})$',  # ALL CAPS headings
        ]
        for pattern in patterns:
            m = re.match(pattern, line, re.IGNORECASE)
            if m:
                title = m.group(1).strip() if m.lastindex else line
                chapters.append({
                    "title": title,
                    "line_index": i
                })
                break
    return chapters


def get_pdf_chapter_content(pdf_bytes: bytes, chapter_title: str) -> str:
    """Extract specific chapter content from PDF text."""
    full_text = extract_text_from_pdf(pdf_bytes)
    chapters = extract_chapters_from_pdf_text(full_text)
    lines = full_text.split("\n")
    
    for ci, ch in enumerate(chapters):
        if chapter_title.lower() in ch["title"].lower() or ch["title"].lower() in chapter_title.lower():
            start = ch["line_index"]
            end = chapters[ci + 1]["line_index"] if ci + 1 < len(chapters) else len(lines)
            return "\n".join(lines[start:end])[:15000]
    
    # Fallback: return first 15000 chars
    return full_text[:15000]


async def search_pdfs_by_class(service, class_num: int) -> List[Dict]:
    """Search for PDFs belonging to a specific class."""
    all_pdfs = get_all_pdf_files(service)
    class_pdfs = []
    for pdf in all_pdfs:
        # Match patterns like "Class 5", "Grade 5", "5 " in path
        import re
        if re.search(rf'(?:Class|Grade)\s*{class_num}\b', pdf['path'], re.IGNORECASE):
            class_pdfs.append(pdf)
    return class_pdfs


async def get_chapter_pdf_context(class_num: int, pdf_name: str, chapter_title: str) -> str:
    """Get chapter content from a specific PDF in Google Drive."""
    service = get_drive_service()
    class_pdfs = await search_pdfs_by_class(service, class_num)
    
    # Find matching PDF
    pdf_file = None
    for pdf in class_pdfs:
        if pdf_name.lower() in pdf['name'].lower() or pdf['name'].lower() in pdf_name.lower():
            pdf_file = pdf
            break
    
    if not pdf_file and class_pdfs:
        pdf_file = class_pdfs[0]  # Fallback to first class PDF
    
    if not pdf_file:
        raise ValueError(f"No PDF found for class {class_num}")
    
    pdf_bytes = download_pdf_cached(pdf_file['id'])
    return get_pdf_chapter_content(pdf_bytes, chapter_title)


async def list_available_pdfs(class_num: int) -> List[Dict]:
    """List available PDFs for a class."""
    service = get_drive_service()
    class_pdfs = await search_pdfs_by_class(service, class_num)
    return [{
        "file": pdf['name'],
        "class_num": class_num,
        "available": True,
        "size": pdf.get('size', 0),
        "modified": pdf.get('modified'),
        "path": pdf.get('path')
    } for pdf in class_pdfs]


async def get_all_curriculum() -> List[Dict]:
    """Build curriculum structure from Google Drive PDFs."""
    service = get_drive_service()
    root_id = find_root_folder(service)
    if not root_id:
        return []
    
    all_pdfs = get_all_pdf_files(service)
    
    # Group by class
    classes = {}
    for pdf in all_pdfs:
        import re
        match = re.search(r'(?:Class|Grade)\s*(\d+)', pdf['path'], re.IGNORECASE)
        if match:
            cn = int(match.group(1))
            if cn not in classes:
                classes[cn] = {
                    "id": f"class{cn}",
                    "label": f"Class {cn}",
                    "class_num": cn,
                    "subjects": []
                }
            classes[cn]["subjects"].append({
                "file": pdf['name'],
                "class_num": cn,
                "available": True,
                "size": pdf.get('size', 0)
            })
    
    return sorted(classes.values(), key=lambda x: x['class_num'])


if __name__ == "__main__":
    # Test the service
    import asyncio
    async def test():
        service = get_drive_service()
        print("Service authenticated")
        curriculum = await get_all_curriculum()
        for c in curriculum:
            print(f"{c['label']}: {len(c['subjects'])} PDFs")
            for s in c['subjects'][:3]:
                print(f"  - {s['file']} ({s.get('size', 0)} bytes)")
    
    asyncio.run(test())
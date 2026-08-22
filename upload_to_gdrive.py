import sys, os, json, time
sys.stdout.reconfigure(encoding='utf-8')

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDS_FILE = r'E:\rag sys\medical-chatbot-refactored\gdrive_credentials.json'
TOKEN_FILE = r'E:\rag sys\medical-chatbot-refactored\gdrive_token.json'

PDF_DIR = r'E:\class  1 to 10 book\Nepal Textbooks Grade 1-10'
MD_DIR = r'E:\rag sys\medical-chatbot-refactored\textbooks_md'

FOLDER_MIME = 'application/vnd.google-apps.folder'
CHUNK_SIZE = 10 * 1024 * 1024

# Track created folders to avoid duplicate API calls
folder_cache = {}

def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

def find_or_create_folder(service, name, parent_id='root'):
    cache_key = f"{parent_id}/{name}"
    if cache_key in folder_cache:
        return folder_cache[cache_key]

    query = f"name='{name}' and mimeType='{FOLDER_MIME}' and '{parent_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields='files(id, name)').execute()
    files = results.get('files', [])
    if files:
        folder_id = files[0]['id']
    else:
        metadata = {'name': name, 'mimeType': FOLDER_MIME, 'parents': [parent_id]}
        folder = service.files().create(body=metadata, fields='id').execute()
        folder_id = folder['id']

    folder_cache[cache_key] = folder_id
    return folder_id

def file_exists(service, filename, parent_id):
    query = f"name='{filename}' and '{parent_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields='files(id, name)').execute()
    return len(results.get('files', [])) > 0

def upload_file(service, filepath, parent_id, retries=3):
    filename = os.path.basename(filepath)
    filesize = os.path.getsize(filepath)

    if file_exists(service, filename, parent_id):
        print(f" [SKIP - exists]")
        return {"skipped": True}

    metadata = {'name': filename, 'parents': [parent_id]}
    media = MediaFileUpload(filepath, resumable=True, chunksize=CHUNK_SIZE)

    for attempt in range(retries):
        try:
            request = service.files().create(
                body=metadata,
                media_body=media,
                fields='id, name, size'
            )
            response = None
            while response is None:
                status, response = request.next_chunk()
            size_str = response.get('size', str(filesize))
            print(f" [{int(int(size_str)/1024)}KB]")
            return response
        except Exception as e:
            if attempt < retries - 1:
                print(f" retry{attempt+1}", end="", flush=True)
                time.sleep(2 ** attempt)
            else:
                print(f" FAILED: {e}")
                return None

def main():
    print("Authenticating with Google Drive...")
    service = get_service()
    print("OK\n")

    # Root folder: SchoolBooks
    root_id = find_or_create_folder(service, "SchoolBooks")
    print(f"Root: https://drive.google.com/drive/folders/{root_id}\n")

    uploaded = 0
    failed = 0

    for cls in range(1, 11):
        cls_pdf_dir = os.path.join(PDF_DIR, f"Class {cls}")
        if not os.path.isdir(cls_pdf_dir):
            continue

        print(f"Class {cls}/")
        cls_folder_id = find_or_create_folder(service, f"Class {cls}", root_id)

        # PDF subfolder
        pdf_folder_id = find_or_create_folder(service, "PDF", cls_folder_id)
        for fname in sorted(os.listdir(cls_pdf_dir)):
            if not fname.endswith('.pdf'):
                continue
            filepath = os.path.join(cls_pdf_dir, fname)
            print(f"  PDF/{fname}", end="", flush=True)
            result = upload_file(service, filepath, pdf_folder_id)
            if result and result.get('skipped'):
                pass
            elif result:
                uploaded += 1
            else:
                failed += 1
            time.sleep(0.3)

        # Markdown subfolder
        md_folder_id = find_or_create_folder(service, "Markdown", cls_folder_id)
        for fname in sorted(os.listdir(MD_DIR)):
            if not fname.endswith('.md'):
                continue
            # Only MD files for this class
            if not fname.startswith(f"Class {cls} - "):
                continue
            book_name = fname.replace(f"Class {cls} - ", "")
            filepath = os.path.join(MD_DIR, fname)
            print(f"  Markdown/{book_name}", end="", flush=True)
            result = upload_file(service, filepath, md_folder_id)
            if result and result.get('skipped'):
                pass
            elif result:
                uploaded += 1
            else:
                failed += 1
            time.sleep(0.3)

        print()

    print(f"=== DONE ===")
    print(f"Uploaded: {uploaded}, Failed: {failed}")
    print(f"URL: https://drive.google.com/drive/folders/{root_id}")

if __name__ == '__main__':
    main()

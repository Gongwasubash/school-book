import os
import json
from typing import Optional, List, Dict, Any
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_SLIDES_AVAILABLE = True
except ImportError:
    GOOGLE_SLIDES_AVAILABLE = False

SCOPES = [
    'https://www.googleapis.com/auth/presentations',
    'https://www.googleapis.com/auth/drive.file',
]

TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'google_slides_token.json')
CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'google_credentials.json')


def get_slides_credentials() -> Optional[Credentials]:
    """Get valid Google Slides API credentials."""
    if not GOOGLE_SLIDES_AVAILABLE:
        return None

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                raise RuntimeError("Google credentials file not found: google_credentials.json")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    return creds


def create_presentation(creds: Credentials, title: str) -> str:
    """Create a new blank presentation and return its ID."""
    service = build('slides', 'v1', credentials=creds)
    presentation = service.presentations().create(body={'title': title}).execute()
    return presentation.get('presentationId')


def add_slides(creds: Credentials, presentation_id: str, slides: List[Dict], images_dir: str = "slide_images") -> None:
    """Add slides to the presentation with content and images."""
    service = build('slides', 'v1', credentials=creds)
    drive_service = build('drive', 'v3', credentials=creds)

    requests = []

    for i, slide in enumerate(slides):
        slide_title = slide.get('title', f'Slide {i + 1}')
        bullets = slide.get('bullets', [])
        notes = slide.get('notes', '')

        # Create new slide
        slide_id = f'slide_{i}'
        requests.append({
            'createSlide': {
                'objectId': slide_id,
                'slideLayoutReference': {'predefinedLayout': 'TITLE_AND_BODY'},
            }
        })

        # Set title
        requests.append({
            'insertText': {
                'objectId': f'{slide_id}_title',
                'text': slide_title,
            }
        })

        # Add bullets to body
        if bullets:
            bullet_text = '\n'.join(f'• {b}' for b in bullets)
            requests.append({
                'insertText': {
                    'objectId': f'{slide_id}_body',
                    'text': bullet_text,
                }
            })

        # Add image if available
        image_name = f"{slide.get('image', '').split('/')[-1]}" if slide.get('image') else None
        if image_name:
            image_path = os.path.join(images_dir, image_name)
            if os.path.exists(image_path):
                # Upload image to Drive first
                from googleapiclient.http import MediaFileUpload
                file_metadata = {'name': image_name, 'parents': ['root']}
                media = MediaFileUpload(image_path, mimetype='image/png', resumable=True)
                drive_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                file_id = drive_file.get('id')
                drive_service.permissions().create(fileId=file_id, body={'role': 'reader', 'type': 'anyone'}).execute()

                image_url = f"https://drive.google.com/uc?id={file_id}"
                requests.append({
                    'createImage': {
                        'objectId': f'{slide_id}_img_{i}',
                        'url': image_url,
                        'elementProperties': {
                            'pageObjectId': slide_id,
                            'size': {'width': {'magnitude': 4000000, 'unit': 'EMU'}, 'height': {'magnitude': 3000000, 'unit': 'EMU'}},
                            'transform': {'scaleX': 1, 'scaleY': 1, 'translateX': 3000000, 'translateY': 1500000, 'unit': 'EMU'},
                        }
                    }
                })

    if requests:
        service.presentations().batchUpdate(presentationId=presentation_id, body={'requests': requests}).execute()


def create_google_slides_presentation(slides: List[Dict], title: str, images_dir: str = "slide_images") -> Dict[str, Any]:
    """
    Create a complete Google Slides presentation from slide data.
    Returns dict with presentation_id and URL.
    """
    if not GOOGLE_SLIDES_AVAILABLE:
        return {'error': 'Google Slides API libraries not installed. Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib'}

    try:
        creds = get_slides_credentials()
        presentation_id = create_presentation(creds, title)
        add_slides(creds, presentation_id, slides, images_dir)

        url = f"https://docs.google.com/presentation/d/{presentation_id}/edit"
        return {'presentation_id': presentation_id, 'url': url, 'title': title}
    except HttpError as e:
        return {'error': f'Google Slides API error: {e}'}
    except Exception as e:
        return {'error': str(e)}


def is_google_slides_available() -> bool:
    return GOOGLE_SLIDES_AVAILABLE
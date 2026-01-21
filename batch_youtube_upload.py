import os
import sys
import logging
from youtube_uploader import schedule_uploads
import socket
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, HttpError
from googleapiclient.errors import HttpError


def upload_folder(folder_path):
    youtube = get_youtube_service()
    files = [f for f in os.listdir(folder_path) if f.lower().endswith('.mp4')]
    files.sort()  # Sorts by filename (lexicographically)
    for filename in files:
        if not filename.lower().endswith('.mp4'):
            continue
        file_path = os.path.join(folder_path, filename)
        title = os.path.splitext(filename)[0]
        description = f"Uploaded : {filename}"
        print(f"Uploading: {file_path}")
        video_id = schedule_uploads(file_path, title, description,"","",youtube)
        if video_id:
            print(f"Uploaded successfully: {video_id}")
        else:
            print(f"Failed to upload: {file_path}")

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
CLIENT_SECRETS_FILE = 'config/client_secrets.json'
def get_youtube_service(service_name='youtube'):
    """Get authenticated YouTube service"""
    creds = None
    
    # The file token.json stores the user's access and refresh tokens
    if os.path.exists(f'{service_name}_credentials.json'):
        creds = Credentials.from_authorized_user_file(f'{service_name}_credentials.json', SCOPES)
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.token:
            creds.refresh(Request())
        else:
            port = find_available_port()
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=port,access_type='offline',
    prompt='consent')
        
        # Save the credentials for the next run
        with open(f'{service_name}_credentials.json', 'w') as token:
            token.write(creds.to_json())
    
    # Build and return the YouTube service
    return build('youtube', 'v3', credentials=creds)

def find_available_port(start_port=8081, max_port=8090):
    """Find an available port in the given range"""
    for port in range(start_port, max_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"No available ports found between {start_port} and {max_port}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python batch_youtube_upload.py <folder_path>")
        sys.exit(1)
    upload_folder(sys.argv[1])
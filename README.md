# Instagram Reels to YouTube Uploader

This project consists of two main scripts that work together to download Instagram reels and upload them to YouTube with scheduling capabilities.

## Features

- Download Instagram reels from public accounts
- Automatic session management with Instagram
- Upload videos to YouTube with scheduling
- Progress tracking and error handling
- Detailed logging
- Configurable upload intervals

## Prerequisites

- Python 3.7 or higher
- Instagram account (for downloading)
- Google Cloud Project with YouTube Data API enabled
- OAuth 2.0 credentials from Google Cloud Console

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd instagram
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
pip install -r youtube_requirements.txt
```

// Uplaod
python src/upload_local_sheet.py sheet/FlutterNik.xlsx flutternik
python src/upload_local_sheet.py sheet/poojahegde.xlsx poojahegde



mrbeast
python src/download_all_video.py mrbeast mrbeast

## Setup

### Instagram Setup

1. Run the session creation script:
```bash
python create_session.py
```

2. Enter your Instagram credentials when prompted
3. Complete any verification steps if required
4. The script will create a session file for future use

### YouTube Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the YouTube Data API v3
4. Create OAuth 2.0 credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Choose "Desktop app" as application type
   - Download the client secrets file and save it as `client_secrets.json`
5. Add your Google account as a test user:
   - Go to "APIs & Services" > "OAuth consent screen"
   - Under "Test users", add your Google email address
   - Click "Save"

## Usage

### Downloading Instagram Reels

1. Run the download script with a username:
```bash
python download_reels.py username
```

The script will:
- Load the saved Instagram session
- Count available reels
- Download reels with progress tracking
- Save videos with metadata in filenames

### Uploading to YouTube

1. Run the upload script:
```bash
python youtube_uploader.py
```

The script will:
- Authenticate with YouTube API
- Find all downloaded videos
- Schedule uploads starting from 10 AM the next day
- Upload videos with 2-hour intervals (configurable)
- Set videos as private initially

## Configuration

### Instagram Downloader

- `MAX_RETRIES`: Maximum number of retry attempts (default: 3)
- `DELAY_BETWEEN_REQUESTS`: Delay between API requests (default: 60 seconds)
- `DELAY_BETWEEN_DOWNLOADS`: Delay between video downloads (default: 5 seconds)

### YouTube Uploader

- `VIDEO_DIR`: Directory containing downloaded videos (default: current directory)
- `upload_interval_hours`: Time between uploads (default: 24 hours)
- `privacy_status`: Initial video privacy ('private', 'public', or 'unlisted')

## File Naming Convention

Downloaded videos follow this format:
```
username_1_postcode_timestamp.mp4
```

Where:
- `username`: Instagram username
- `1`: Fixed identifier
- `post_code`: Instagram post code
- `timestamp`: Unix timestamp

## Error Handling

Both scripts include comprehensive error handling:
- Rate limit detection and handling
- Session expiration management
- Network error recovery
- Detailed logging of all operations

## Logging

Logs are printed to the console with timestamps and include:
- Operation progress
- Success/failure messages
- Error details
- Upload/download statistics

## Troubleshooting

### Instagram Issues

1. If you get "401 Unauthorized" errors:
   - Wait a few minutes before trying again
   - Run `create_session.py` to create a fresh session
   - Check if your account has any restrictions

2. If downloads fail:
   - Check your internet connection
   - Verify the account is public
   - Ensure you have sufficient disk space

### YouTube Issues

1. If authentication fails:
   - Verify your `client_secrets.json` file is present
   - Ensure you're added as a test user
   - Check if the OAuth consent screen is configured correctly

2. If uploads fail:
   - Check your internet connection
   - Verify video file integrity
   - Ensure you have sufficient quota in your YouTube API project

## Contributing

Feel free to submit issues and enhancement requests!

## License

This project is licensed under the MIT License - see the LICENSE file for details.



python convert_to_portrait.py --input input1.mkv --output outputvideos.mp4 --crop_left 200 --crop_right 200

python convert_to_portrait.py --input Panchayat_S04_E02.mkv --output Panchayat_S04_E02_p.mkv --crop_left 110 --crop_right 110

python split_video.py -f input.mp4 -s 30 -o my_videos/ -v libx264 -a aac

python split_video.py -f outputvideos.mp4 -s 20 -o my_videos/ -v libx264 -a aac --top-text "South movie 2025" --bottom-text "Part {part}" --top-fontsize 48 --font "/System/Library/Fonts/Kohinoor.ttc" --bg-music background_music.mp3 --parts 1-5


python split_into_two.py outputvideos.mp4 --minutes 30 1

python split_video.py -f outputvideos.mp4 -s 60 -o my_videos/ -v libx264 -a aac --top-text "Money" --bottom-text "Part {part}" --top-fontsize 48 --font "/System/Library/Fonts/Kohinoor.ttc" --bg-music background_music.mp3 --parts 6-10 --flip horizontal

python split_video.py -f outputvideos.mp4 -s 20 -o my_videos/ -v libx264 -a aac --top-text "Money" --top-icon "dollor.png" --top-icon-height 64 --top-icon-x 20 --top-icon-y 200 --top-text-x 120 --bottom-text "Part {part}" --bg-music background_music.mp3 --parts 1-5


python split_video.py -f outputvideos.mp4 -s 60 -o my_videos/ -v libx264 -a aac --top-text "Money" --top-icon "dollor.png" --top-icon-height 64 --top-icon-x 300 --top-icon-y 200 --top-text-x 120 --bottom-text "Part {part}" --metadata "title=Money Part {part} Flick Series,comment=Flick Series {part} of {total}"

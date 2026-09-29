import subprocess
import os
import re
import glob
import textwrap
import sys

def get_transcript(url):
    cmd = [
        'yt-dlp',
        '--write-subs',
        '--write-auto-subs',
        '--sub-langs', 'en,bn',
        '--sub-format', 'vtt',
        '--skip-download',
        '--ignore-errors',
        '--output', 'temp_transcript',
        url
    ]

    # Facebook extractor needs the logged-in Chrome session
    if 'facebook.com' in url or 'fb.watch' in url:
        cmd[1:1] = ['--cookies-from-browser', 'chrome']

    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError:
        # Fallback to English only if multi-lang fails
        cmd_fallback = [
            'yt-dlp',
            '--write-subs',
            '--write-auto-subs',
            '--sub-langs', 'en',
            '--sub-format', 'vtt',
            '--skip-download',
            '--output', 'temp_transcript',
            url
        ]
        try:
            subprocess.run(cmd_fallback, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            print("Error: yt-dlp failed to download subtitles. Check the URL.")
            return

    vtt_files = glob.glob('temp_transcript*.vtt')
    if not vtt_files:
        print("No subtitles available for this video. Nothing to transcribe.")
        return

    clean_text = []
    last_line = ""

    for vtt_file in vtt_files:
        with open(vtt_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            line = re.sub(r'<[^>]*>', '', line)
            if not line or line == 'WEBVTT' or '-->' in line or line.startswith('Kind:'):
                continue
            if line.isdigit():
                continue
            if line != last_line:
                clean_text.append(line)
                last_line = line
        os.remove(vtt_file)

    full_text = ' '.join(clean_text)
    full_text = re.sub(r'\s+', ' ', full_text)
    print(textwrap.fill(full_text, width=80))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python yt_vid_transcript.py <VIDEO_URL>")
    else:
        get_transcript(sys.argv[1])

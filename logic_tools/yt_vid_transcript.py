import subprocess
import os
import re
import glob
import textwrap
import sys

def run_ytdlp(base_cmd):
    attempts = [
        [],
        ['--cookies-from-browser', 'edge'],
        ['--cookies-from-browser', 'chrome'],
        ['--cookies-from-browser', 'firefox']
    ]
    for extra in attempts:
        cmd = [base_cmd[0]] + extra + base_cmd[1:]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            if res.returncode == 0:
                files = glob.glob('temp_transcript*.vtt')
                if files:
                    return True
        except Exception:
            continue
    return False

def get_transcript(url):
    base_cmd = [
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

    success = run_ytdlp(base_cmd)
    if not success:
        fallback_cmd = [
            'yt-dlp',
            '--write-subs',
            '--write-auto-subs',
            '--sub-langs', 'en',
            '--sub-format', 'vtt',
            '--skip-download',
            '--output', 'temp_transcript',
            url
        ]
        success = run_ytdlp(fallback_cmd)

    vtt_files = glob.glob('temp_transcript*.vtt')
    if not vtt_files:
        print("No subtitles available or failed to fetch transcript. Check URL or cookies.")
        return

    clean_text = []
    last_line = ""

    for vtt_file in vtt_files:
        with open(vtt_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        for line in lines:
            line = line.strip()
            line = re.sub(r'<[^>]*>', '', line)
            if not line or line == 'WEBVTT' or '-->' in line or line.startswith('Kind:') or line.startswith('Language:'):
                continue
            if line.isdigit():
                continue
            if line != last_line:
                clean_text.append(line)
                last_line = line
        try:
            os.remove(vtt_file)
        except OSError:
            pass

    full_text = ' '.join(clean_text)
    full_text = re.sub(r'\s+', ' ', full_text)
    print(textwrap.fill(full_text, width=80))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python yt_vid_transcript.py <VIDEO_URL>")
    else:
        get_transcript(sys.argv[1])

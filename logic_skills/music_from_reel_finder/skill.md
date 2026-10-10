# music_from_reel_finder

## Purpose
Extract audio from a video/reel link (Facebook, YouTube, etc.) entirely in-memory (zero disk footprint) and identify the track using `shazamio`.

## Script Location & Invocation
- Script path: D:\Ai\logic\logic_skills\music_from_reel_finder\find_music.py
- Run via: python D:\Ai\logic\logic_skills\music_from_reel_finder\find_music.py <video_url>

## Procedure
1. Pipe `yt-dlp` audio output directly into `ffmpeg` to transcode to mp3 in memory.
2. Feed the raw byte buffer directly into `Shazam().recognize(audio_bytes)`.
3. Output track title and artist without writing any intermediate files to disk.

## What NOT to do
- Do NOT save temporary audio files (`.mp3`, `.wav`) to disk unless explicitly requested.
- Do NOT use visual `check_screen` tools for audio identification.
- Do NOT rely on superficial text metadata or caption tags without audio fingerprint verification.

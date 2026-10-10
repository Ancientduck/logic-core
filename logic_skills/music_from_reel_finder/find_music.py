import asyncio
import sys
import subprocess
from shazamio import Shazam

async def recognize_url(url):
    p1 = subprocess.Popen(["yt-dlp", "-f", "bestaudio", "-o", "-", url], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    p2 = subprocess.Popen(["ffmpeg", "-i", "pipe:0", "-f", "mp3", "-acodec", "libmp3lame", "pipe:1"], stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    p1.stdout.close()
    audio_bytes = p2.stdout.read()
    
    shazam = Shazam()
    out = await shazam.recognize(audio_bytes)
    track = out.get('track', {})
    print(f"Title: {track.get('title')}")
    print(f"Artist: {track.get('subtitle')}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python find_music.py <url>")
        sys.exit(1)
    asyncio.run(recognize_url(sys.argv[1]))

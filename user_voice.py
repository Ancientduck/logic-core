import webrtcvad
import collections
import sounddevice as sd
import numpy as np
import io
import wave
import time
import os
from dotenv import load_dotenv
load_dotenv()
from scipy import signal
from groq import Groq

import logic_voice   # your existing module

# ============================================================
# CONFIG  (tuned for better accuracy)
# ============================================================

SAMPLE_RATE          = 16000
FRAME_DURATION_MS    = 30
FRAME_SAMPLES        = SAMPLE_RATE * FRAME_DURATION_MS // 1000

VAD_AGGRESSIVENESS   = 2          # 1–3. 2 is usually the sweet spot

START_TIMEOUT_SEC    = 12
MAX_SPEECH_SEC       = 45

# How much continuous speech is required to start recording
START_SPEECH_MS      = 120        # slightly longer → fewer false starts

# How much silence ends the utterance (humans pause)
END_SILENCE_MS       = 700

PRE_ROLL_MS          = 400
MIN_SPEECH_MS        = 300

# Adaptive energy
NOISE_MULTIPLIER     = 2.2
MIN_RMS              = 35.0

# Optional debug
SAVE_TEST_AUDIO      = False
TEST_AUDIO_FILE      = "vad_test.wav"


# ============================================================
# GROQ  (never hard-code keys)
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    raise RuntimeError("Set GROQ_API_KEY environment variable")

client = Groq(api_key=GROQ_API_KEY)
vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)


# ============================================================
# Helpers
# ============================================================

def stop_all_audio():
    logic_voice.interrupted = True
    try:
        logic_voice.speak_queue.queue.clear()
    except Exception:
        pass
    sd.stop()


def frame_rms(audio_bytes: bytes) -> float:
    audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(audio * audio)))


def calibrate_noise(stream, duration_ms: int = 600) -> float:
    frames = max(1, duration_ms // FRAME_DURATION_MS)
    levels = []
    for _ in range(frames):
        chunk, _ = stream.read(FRAME_SAMPLES)
        levels.append(frame_rms(chunk))
    if not levels:
        return MIN_RMS
    # Use a high percentile so sudden spikes don't ruin the threshold
    return max(float(np.percentile(levels, 75)), MIN_RMS)


def apply_voicing_bandpass(audio_bytes: bytes) -> bytes:
    """Bandpass 100Hz-8kHz: kills boost hiss above 8k and rumble below 100."""
    audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
    if len(audio) < 10:
        return audio_bytes
    sos = signal.butter(3, [100, 7500], btype="bandpass", fs=SAMPLE_RATE, output="sos")
    filtered = signal.sosfilt(sos, audio)
    filtered = np.clip(filtered, -32768, 32767)
    return filtered.astype(np.int16).tobytes()



def _frame_bandpass(audio_bytes: bytes) -> bytes:
    """Filter a single 30ms frame: kill boost static above 8k before VAD sees it."""
    audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
    if len(audio) < 10:
        return audio_bytes
    sos = signal.butter(3, [100, 7500], btype="bandpass", fs=SAMPLE_RATE, output="sos")
    filtered = signal.sosfilt(sos, audio)
    return np.clip(filtered, -32768, 32767).astype(np.int16).tobytes()

def pcm_to_wav_buffer(pcm_bytes: bytes) -> io.BytesIO:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    buf.seek(0)
    return buf


# ============================================================
# Main VAD listener
# ============================================================

def listen_with_vad() -> bytes | None:
    pre_roll_frames          = PRE_ROLL_MS // FRAME_DURATION_MS
    start_frames_required    = max(1, START_SPEECH_MS // FRAME_DURATION_MS)
    end_silence_frames       = max(1, END_SILENCE_MS // FRAME_DURATION_MS)
    min_speech_frames        = max(1, MIN_SPEECH_MS // FRAME_DURATION_MS)

    pre_roll = collections.deque(maxlen=pre_roll_frames)
    recorded = []

    triggered = False
    speech_count = 0
    silence_count = 0
    voiced_frames = 0
    voiced_frames = 0
    start_time = time.monotonic()
    speech_start = None

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=FRAME_SAMPLES,
        dtype="int16",
        channels=1,
    ) as stream:

        noise_rms = calibrate_noise(stream)
        energy_threshold = max(MIN_RMS, noise_rms * NOISE_MULTIPLIER)

        while True:
            now = time.monotonic()
            chunk, _ = stream.read(FRAME_SAMPLES)
            audio_bytes = _frame_bandpass(bytes(chunk))

            rms = frame_rms(audio_bytes)
            energetic = rms >= energy_threshold

            try:
                is_speech = vad.is_speech(audio_bytes, SAMPLE_RATE)
            except Exception:
                is_speech = False

            # ---------- waiting for speech ----------
            if not triggered:
                pre_roll.append(audio_bytes)

                # More permissive start: either VAD or energy
                if is_speech or energetic:
                    speech_count += 1
                else:
                    speech_count = max(0, speech_count - 1)

                if speech_count >= start_frames_required:
                    triggered = True
                    speech_start = now
                    recorded.extend(pre_roll)
                    pre_roll.clear()
                    silence_count = 0
                    continue

                if now - start_time >= START_TIMEOUT_SEC:
                    return None
                continue

            # ---------- already speaking ----------
            recorded.append(audio_bytes)

            # End condition: both VAD and energy agree it's quiet
            actually_silent = (not is_speech) and (not energetic)

            if actually_silent:
                silence_count += 1
            else:
                silence_count = 0
                voiced_frames += 1
                voiced_frames += 1

            duration = now - speech_start

            # Enough speech + enough trailing silence → finish
            if (len(recorded) >= min_speech_frames and
                    silence_count >= end_silence_frames):
                # trim trailing silence
                trim = min(silence_count, len(recorded))
                if trim:
                    del recorded[-trim:]
                break

            if duration >= MAX_SPEECH_SEC:
                break

    if not recorded:
        return None

    total_frames = len(recorded)
    voiced_ratio = voiced_frames / max(1, total_frames)
    # If less than 35% of frames were actually voiced, it's noise
    if voiced_ratio < 0.35:
        return None

    audio = b"".join(recorded)
    audio = apply_voicing_bandpass(audio)

    if SAVE_TEST_AUDIO:
        with open(TEST_AUDIO_FILE, "wb") as f:
            f.write(pcm_to_wav_buffer(audio).getvalue())

    return audio


# ============================================================
# Voice → text
# ============================================================

def get_voice() -> str | None:
    speech = listen_with_vad()
    if speech is None:
        return None

    audio = np.frombuffer(speech, dtype=np.int16).astype(np.float32)
    duration_sec = len(audio) / SAMPLE_RATE
    rms = float(np.sqrt(np.mean(audio ** 2)))
    peak = float(np.max(np.abs(audio)))

    # ---------- Quality gate ----------
    # Reject obvious garbage before even calling Whisper
    if duration_sec < 0.50:
        return None
    if rms < 350 or peak < 1500:
        return None
    # ----------------------------------

    stop_all_audio()

    wav_buf = pcm_to_wav_buffer(speech)

    for attempt in range(2):
        try:
            wav_buf.seek(0)
            result = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                language="en",
                file=("audio.wav", wav_buf),
                prompt="LOGIC",
                temperature=0.0,
            )
            text = (result.text or "").strip()

            if not text:
                return None

            # Only reject the common hallucination
            # when the audio itself was weak / short
            lowered = text.lower().rstrip(".")
            is_hallucination = lowered in {
                "thank you", "thanks", "thank you for watching",
                "thanks for watching", "thanks for listening",
                "silen", "silent", "siren", "giclec", "mmh",
                "ehm", "mm", "vroom", "season 6", "this time",
                "gracias", "silence", "shh",
            }

            if is_hallucination and (duration_sec < 1.1 or rms < 320):
                # This was almost certainly a hallucination
                return None

            return text

        except Exception as e:
            if attempt == 1:
                print(f"Whisper error: {e}")
                return None
            time.sleep(0.4)

    return None


# ============================================================
# Test loop
# ============================================================

if __name__ == "__main__":
    print("LOGIC voice test — say 'voice off' to exit.")
    while True:
        text = get_voice()
        if text is None:
            continue
        print(f"> {text}")
        if text.lower().strip() in {"voice off", "stop listening"}:
            break
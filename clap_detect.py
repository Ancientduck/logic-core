import os
import sounddevice as sd
import numpy as np
import subprocess
import time
import psutil
from plyer import notification

# Constants
THRESHOLD_MULTIPLIER = 2.0
TIME_WINDOW = 2.0
SENSITIVITY = 1
COOLDOWN = 0.15
FREQ_THRESHOLD = 2000

clap_count = 0
last_clap_time = 0

def is_process_running(process_name):
    for proc in psutil.process_iter(['name']):
        if process_name.lower() in proc.info['name'].lower():
            return True
    return False

def callback(indata, frames, time_info, status):
    global clap_count, last_clap_time
    volume_norm = np.linalg.norm(indata) * 10
    if volume_norm <= (SENSITIVITY * THRESHOLD_MULTIPLIER):
        return

    audio_data = indata[:, 0]
    print(audio_data)
    fft_data = np.abs(np.fft.rfft(audio_data))
    freqs = np.fft.rfftfreq(len(audio_data), d=1/44100)

    high_freq_energy = np.sum(fft_data[freqs > FREQ_THRESHOLD])
    total_energy = np.sum(fft_data)
    ratio = high_freq_energy / total_energy
    
    current_time = time.time()
    if ratio > 0.3:        
        if current_time - last_clap_time < COOLDOWN:
            return
        if current_time - last_clap_time < TIME_WINDOW:
            clap_count += 1
        else:
            clap_count = 1
        last_clap_time = current_time
        print(f"Clap detected! Ratio: {ratio:.2f} | Count: {clap_count}")

def get_to_work():
    print("Activation threshold reached. Launching systems...")
    urls = ['facebook.com', 'youtube.com', 'torn.com']
    chrome_path = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    
    if not is_process_running("WindowsTerminal.exe"):
        print("Launching Windows Terminal...")
        subprocess.Popen(
            ["wt", "python", r"D:\Ai\logic\logic.py"],
            cwd=r"D:\Ai\logic",
        )
    else:
        print("Terminal already active. Skipping.")
    
    if not is_process_running("chrome.exe"):
        print("Launching Chrome...")
        subprocess.Popen([chrome_path, "--start-maximized", *urls])
    else:
        print("Chrome already active. Skipping.")

notification.notify(
    title="LOGIC",
    message="Clap detection is now active",
    app_name="LOGIC",
    timeout=5
)

try:
    print('Listening for claps...')
    with sd.InputStream(callback=callback, samplerate=44100):
        while True:
            if clap_count >= 2:
                get_to_work()
                break
            time.sleep(0.1)
except KeyboardInterrupt:
    pass

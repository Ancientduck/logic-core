import os
import time

def shut_pc_down(delay: int = 5):
    print(f"Shutting down in {delay} seconds. Say your prayers.")
    for i in range(delay, 0, -1):
        print(f"{i}...")
        time.sleep(1)
    print("Goodbye, sir.")
    os.system("shutdown /s /t 0")

def cancel_shutdown():
    os.system("shutdown /a")
    print("Shutdown cancelled, sir.")

def restart():
    print("Restarting...")
    os.system("shutdown /r /t 0")

def sleep_pc():
    print("Going to sleep, sir.")
    os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

if __name__ == "__main__":
    shut_pc_down()
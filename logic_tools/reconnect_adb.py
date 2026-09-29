import subprocess

def reconnect():
    ip = "192.168.0.103:5555"
    subprocess.run(["adb", "disconnect"], capture_output=True)
    res = subprocess.run(["adb", "connect", ip], capture_output=True, text=True)
    print(res.stdout.strip())

if __name__ == "__main__":
    reconnect()

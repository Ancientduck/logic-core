import os
import json
import sys
from datetime import datetime

BASE_DIR = r"D:\Ai\logic\logic_tools\oauth_token_files"
DATA_FILE = os.path.join(BASE_DIR, "exercise_data.json")

def load_data():
    defaults = {"daily_logs": {}, "skills": {}, "profile": {"xp": 0, "level": "Beginner"}}
    if not os.path.exists(DATA_FILE):
        return defaults
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
            for k, v in defaults.items():
                if k not in data:
                    data[k] = v
            return data
    except (json.JSONDecodeError, FileNotFoundError):
        return defaults

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def update_level(data):
    xp = data["profile"]["xp"]
    if xp >= 1000:
        data["profile"]["level"] = "Master"
    elif xp >= 600:
        data["profile"]["level"] = "Elite"
    elif xp >= 300:
        data["profile"]["level"] = "Advanced"
    elif xp >= 100:
        data["profile"]["level"] = "Intermediate"
    else:
        data["profile"]["level"] = "Beginner"
    return data

def log_ex(name, intensity):
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    name = name.lower().replace(" ", "_")
    if today not in data["daily_logs"]:
        data["daily_logs"][today] = []
    if name in data["daily_logs"][today]:
        print(f"Already logged {name} for today.")
        return
    data["daily_logs"][today].append(name)
    save_data(data)
    print(f"Logged {name} (Intensity {intensity}) for today.")

def clear_today():
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    if today in data["daily_logs"]:
        del data["daily_logs"][today]
        save_data(data)
        print(f"Cleared all logs for {today}.")
    else:
        print(f"No logs found for {today} to clear.")

def update_skill(name, description, xp=0):
    data = load_data()
    name = name.lower().replace(" ", "_")
    xp = int(xp)
    exists = name in data["skills"]
    data["skills"][name] = {"description": description, "date": datetime.now().strftime("%Y-%m-%d")}
    if xp != 0:
        data["profile"]["xp"] += xp
        data = update_level(data)
    save_data(data)
    action = "Updated" if exists else "Registered"
    msg = f"{action} skill {name}: {description}."
    if xp != 0:
        msg += f" +{xp} XP. Total XP: {data['profile']['xp']} (Level: {data['profile']['level']})"
    print(msg)

def get_summary():
    data = load_data()
    today = datetime.now().strftime("%Y-%m-%d")
    today_logs = data.get("daily_logs", {}).get(today, [])
    output = ["--- Daily Status ---"]
    if today_logs:
        output.append(f"Exercises done: {', '.join(today_logs)}")
    else:
        output.append("Exercises not done yet.")
    output.append("\n--- Profile ---")
    output.append(f"Level: {data['profile']['level']} | Total XP: {data['profile']['xp']}")
    output.append("\n--- Achievements (Skills) ---")
    if not data["skills"]:
        output.append("No achievements yet.")
    for name, info in data["skills"].items():
        output.append(f"{name.replace('_', ' ').title()}: {info['description']}")
    return "\n".join(output)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python exercise_logger.py [log_ex|update_skill|summary|clear_today] [args...]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "log_ex":
        if len(sys.argv) < 4:
            print("Error: Usage: log_ex [name] [intensity 1-3]")
        else:
            log_ex(sys.argv[2], sys.argv[3])
    elif cmd == "update_skill":
        if len(sys.argv) < 4:
            print("Error: Usage: update_skill [name] [description] [xp(optional)]")
        else:
            xp = sys.argv[4] if len(sys.argv) > 4 else 0
            update_skill(sys.argv[2], sys.argv[3], xp)
    elif cmd == "summary":
        print(get_summary())
    elif cmd == "clear_today":
        clear_today()

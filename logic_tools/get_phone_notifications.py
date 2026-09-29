import subprocess
import re
from collections import defaultdict


def get_notifications_from_adb():
    """Run ADB and get raw notification dump."""
    try:
        result = subprocess.run(
            ["adb", "shell", "dumpsys", "notification", "--noredact"],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
    except FileNotFoundError:
        print("Error: ADB is not installed or not in your system PATH.")
        return None

    if result.returncode != 0:
        print("Error running ADB command. Check your phone connection.")
        return None

    return result.stdout


def parse_notifications(raw_text):
    """Parse raw ADB output into structured notifications."""
    notifications = []

    # Split into blocks, each starting with "tickerText="
    blocks = re.split(r'(?=tickerText=)', raw_text)

    for block in blocks:
        block = block.strip()
        if not block or not block.startswith('tickerText='):
            continue

        # Get basic fields
        ticker_match = re.search(r'tickerText=(.*?)(?=\n|$)', block)
        title_match = re.search(r'android\.title=String \((.*?)\)', block)
        text_match = re.search(r'android\.text=String \((.*?)\)', block)
        text_spannable_match = re.search(r'android\.text=SpannableString \((.*?)\)', block)

        ticker = ticker_match.group(1).strip() if ticker_match else None
        title = title_match.group(1).strip() if title_match else None

        # Get main text (SpannableString or regular String)
        if text_spannable_match:
            text = text_spannable_match.group(1).strip()
        elif text_match:
            text = text_match.group(1).strip()
        else:
            text = None

        # Detect app name
        app = detect_app(ticker, title)

        # Extract all messages from Bundle entries (individual chat messages)
        bundle_lines = re.findall(r'^\s+\[\d+\] Bundle\[\{.*\}\]', block, re.MULTILINE)

        bundle_messages = []
        for bundle_line in bundle_lines:
            sender_match = re.search(r'sender=([^,\]]+)', bundle_line)
            text_match = re.search(r'text=([^,\]]+)', bundle_line)

            if text_match:
                msg_text = text_match.group(1).strip()
                sender = sender_match.group(1).strip() if sender_match else None
                bundle_messages.append({'sender': sender, 'text': msg_text})

        # Add bundle messages
        for msg in bundle_messages:
            notifications.append({
                'app': app,
                'sender': msg['sender'],
                'message': msg['text']
            })

        # If no bundle found, use top-level text
        if not bundle_messages and text and text != 'null':
            sender = extract_sender_from_ticker(ticker)
            notifications.append({
                'app': app,
                'sender': sender,
                'message': text
            })

    return notifications


def detect_app(ticker, title):
    """Figure out which app the notification is from."""
    if ticker and 'Messenger' in ticker:
        return 'Messenger'
    if title == 'Facebook':
        return 'Facebook'
    if title == 'Instagram':
        return 'Instagram'
    if title == 'Upcoming alarm':
        return 'Clock/Alarm'
    if title == '1 new message':
        return 'Messages'

    return 'Unknown'


def extract_sender_from_ticker(ticker):
    """Try to get sender name from the ticker text."""
    if ticker and 'Messenger. Message from ' in ticker:
        match = re.search(r'Messenger\. Message from ([^:]+):', ticker)
        if match:
            return match.group(1).strip()
    return None


def group_by_app_and_sender(notifications):
    """Group notifications: app -> sender -> list of messages."""
    result = defaultdict(lambda: defaultdict(list))

    for n in notifications:
        app = n['app']
        sender = n['sender'] if n['sender'] else 'null'
        result[app][sender].append(n['message'])

    return dict(result)


def print_pretty(data):
    """Print the result in a clean, readable way."""
    import json
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main():
    # Step 1: Get raw data from phone
    raw_text = get_notifications_from_adb()
    if raw_text is None:
        return

    # Step 2: Parse into structured data
    notifications = parse_notifications(raw_text)

    # Step 3: Group by app and sender
    organized = group_by_app_and_sender(notifications)

    # Step 4: Print result
    print_pretty(organized)


if __name__ == "__main__":
    main()
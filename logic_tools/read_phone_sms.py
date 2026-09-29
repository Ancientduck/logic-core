import subprocess
import re

def get_latest_sms():
    try:
        cmd = 'adb shell content query --uri content://sms/inbox --projection address:body:date'
        result = subprocess.check_output(cmd, shell=True).decode('utf-8', errors='ignore')

        lines = result.strip().split('\n')
        rows = [line for line in lines if 'Row:' in line]

        if not rows:
            print("No messages found.")
            return

        parsed_rows = []
        for row in rows:
            # Use regex to find fields and their values accurately
            address = re.search(r'address=([^ ]+)', row)
            body = re.search(r'body=(.*?) date=', row)
            date = re.search(r'date=(\d+)', row)

            parsed_rows.append({
                'address': address.group(1) if address else "Unknown",
                'body': body.group(1) if body else "Empty",
                'date': int(date.group(1)) if date else 0
            })

        latest = max(parsed_rows, key=lambda x: x['date'])
        print(f"Latest SMS: Address={latest['address']}, Body={latest['body']}, Date={latest['date']}")

    except Exception as e:
        print(f"Error: {e}")

get_latest_sms()
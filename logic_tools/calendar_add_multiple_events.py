import json
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone


def add_calendar_events(events_list, utc_offset_hours=6):
    cred_path = 'logic_tools/oauth_token_files/google_oauth.json'
    with open(cred_path, 'r') as f:
        info = json.load(f)

    creds = Credentials(
        token=info['token'],
        refresh_token=info['refresh_token'],
        token_uri=info['token_uri'],
        client_id=info['client_id'],
        client_secret=info['client_secret'],
        scopes=info['scopes']
    )

    service = build('calendar', 'v3', credentials=creds)
    local_tz = timezone(timedelta(hours=utc_offset_hours))

    added_count = 0
    for event_data in events_list:
        try:
            # Expected format: [date, time_range, name, color_id]
            if len(event_data) < 3:
                print(f"Skipping malformed event (need at least 3 elements): {event_data}")
                continue

            date_str = event_data[0]
            time_range = event_data[1]
            name = event_data[2]
            color_id = str(event_data[3]) if len(event_data) > 3 else '1'

            start_time_str, end_time_str = time_range.split('-')
            
            # Pad single-digit hours if needed (e.g. "5:00" -> "05:00")
            start_time_str = ':'.join(p.zfill(2) for p in start_time_str.strip().split(':'))
            end_time_str = ':'.join(p.zfill(2) for p in end_time_str.strip().split(':'))

            # Build timezone-aware local datetimes, convert to UTC
            start_local = datetime.fromisoformat(f"{date_str}T{start_time_str}:00").replace(tzinfo=local_tz)
            end_local = datetime.fromisoformat(f"{date_str}T{end_time_str}:00").replace(tzinfo=local_tz)
            
            utc_start = start_local.astimezone(timezone.utc)
            utc_end = end_local.astimezone(timezone.utc)

            event = {
                'summary': name,
                'start': {'dateTime': utc_start.isoformat(), 'timeZone': 'UTC'},
                'end': {'dateTime': utc_end.isoformat(), 'timeZone': 'UTC'},
                'colorId': color_id,
            }

            event = service.events().insert(calendarId='primary', body=event).execute()
            added_count += 1
            print(f"Added: {name}")
        except Exception as e:
            print(f"Error adding event {event_data}: {e}")

    return added_count


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python script.py '[['YYYY-MM-DD', 'HH:MM-HH:MM', 'Event Name', 'color_id'], ...]'")
        print("Example: python script.py '[['2026-07-05', '12:00-17:00', 'Meeting', '1']]'")
        sys.exit(1)

    # sys.argv[1] is the JSON string of events
    try:
        events = json.loads(sys.argv[1])
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        sys.exit(1)

    if not isinstance(events, list) or not all(isinstance(e, list) for e in events):
        print("Error: Expected a list of lists.")
        sys.exit(1)

    added = add_calendar_events(events)
    print(f"Successfully added {added} event(s).")
import datetime
from pathlib import Path
DAY_START_HOUR = 0
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def get_local_day_schedule(date_arg='today'):
    try:
        creds = Credentials.from_authorized_user_file(str(Path(__file__).resolve().parent / "oauth_token_files" / "google_calendar_drive_oauth.json"))
        service = build('calendar', 'v3', credentials=creds)
        
        local_tz = datetime.timezone(datetime.timedelta(hours=6))
        local_now = datetime.datetime.now(local_tz)
        
        if date_arg:
            target = datetime.datetime.fromisoformat(date_arg).replace(tzinfo=local_tz)
        else:
            target = local_now
        start_of_day = target.replace(hour=DAY_START_HOUR, minute=0, second=0, microsecond=0)
            
        end_of_day = start_of_day + datetime.timedelta(days=1, seconds=-1)
        
        events_result = service.events().list(calendarId='primary', 
                                              timeMin=start_of_day.isoformat(), 
                                              timeMax=end_of_day.isoformat(), 
                                              singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])
        
        if not events:
            return "Your schedule is empty for this cycle."
        
        past_events = []
        future_events = []
        
        for event in events:
            if 'date' in event['start'] and 'dateTime' not in event['start']:
                start_date = event['start'].get('date')
                sd = datetime.datetime.fromisoformat(start_date).replace(tzinfo=local_tz)
                
                # All-day event: consider it "done" only when the day is fully over
                # (i.e., local_now is past the end of that day)
                end_of_event_day = sd + datetime.timedelta(days=1)
                
                desc = event.get('description', '').strip()
                line = f"- All day ({sd.strftime('%B %d')}): {event['summary']}\n"
                if desc:
                    line += f"    Summary: {desc}\n"
                if local_now >= end_of_event_day:
                    past_events.append(line)
                else:
                    future_events.append(line)
                    
            else:
                start_raw = event['start'].get('dateTime', event['start'].get('date'))
                end_raw = event['end'].get('dateTime', event['end'].get('date'))
                try:
                    start_dt = datetime.datetime.fromisoformat(start_raw).astimezone(local_tz)
                    end_dt = datetime.datetime.fromisoformat(end_raw).astimezone(local_tz)
                    
                    start_str = start_dt.strftime('%I:%M %p')
                    end_str = end_dt.strftime('%I:%M %p')
                    
                    desc = event.get('description', '').strip()
                    line = f"- {start_str} to {end_str} ({start_dt.strftime('%B %d')}): {event['summary']}\n"
                    if desc:
                        line += f"    Summary: {desc}\n"
                    
                    if start_dt < local_now:
                        past_events.append(line)
                    else:
                        future_events.append(line)
                except Exception:
                    future_events.append(f"- {start_raw} to {end_raw}: {event['summary']}\n")
        
        schedule = f"Schedule for {start_of_day.date()}:\n"
        
        if future_events:
            schedule += "\nUpcoming:\n" + "".join(future_events)
        else:
            schedule += "\nNothing upcoming.\n"
            
        if past_events:
            schedule += "\nAlready done:\n" + "".join(past_events)
            
        local_time_str = local_now.strftime("%I:%M %p")
        local_date_str = local_now.strftime("%B %d, %Y")
        return f"{schedule}\nCurrent Local Time: {local_time_str}\nDate: {local_date_str}"
    except Exception as e:
        return f"Error retrieving local schedule: {e}"

if __name__ == '__main__':
    import sys
    print(get_local_day_schedule(sys.argv[1] if len(sys.argv) > 1 else None))

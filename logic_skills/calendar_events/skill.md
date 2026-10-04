# Calendar Events

## Add Events
- Script: `D:/Ai/logic/logic_tools/calendar_add_multiple_events.py`
- Args: single JSON string as sys.argv[1]
- Format: `'[["YYYY-MM-DD","HH:MM-HH:MM","Name","color_id"]]'`
- Uses relative cred path: `logic_tools/oauth_token_files/google_calendar_drive_oauth.json`

## Direct API Access
- Cred file: `D:/Ai/logic/logic_tools/oauth_token_files/google_calendar_drive_oauth.json`
- Load with json, use google.oauth2.credentials.Credentials with token, refresh_token, token_uri, client_id, client_secret, scopes fields.

## Notes
- Script output prints "Added: X" + "Successfully added N event(s)." — looks like double but isn't.
- UTC+6 offset handled internally.

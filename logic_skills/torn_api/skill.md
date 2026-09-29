# Torn API

Key file: D:\Ai\logic\logic_tools\torn_api.json  ->  {"token": "<key>"}
Never search memory or find_file for it. Open that path directly.

Request pattern:
  url = f"https://api.torn.com/{section}/{id}?selections={sel}&key={key}"
  req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

CRITICAL: bare urllib gets 403. Always send a browser User-Agent.

Endpoints:
- /torn/{warID}?selections=rankedwarreport   -> full per-member war stats (use this, not screen scraping)
- /faction/?selections=rankedwars            -> your faction's war history
- /faction/?selections=attacks|attacksfull&from=TS&to=TS  -> all attacks in a window

Always check `if "error" in data` before parsing.
Save large reports to a .json file; do not rely on console output (it truncates).

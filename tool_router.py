"""
logic_tool_router.py — minimal tool guesser for LOGIC integration.

Usage:
    from logic_tool_router import guess_tool

    tool = guess_tool(prompt)   # → "search_net" | "find_file.py" | None
"""
import re
from collections import defaultdict


class ToolRouter:
    def __init__(self):
        self.rules = [
            # ─── YT / SCRAPE ────────────────────────────────────────────
            (r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+',
             'yt_vid_transcript.py', 2),
            # Action intent for video content (not "got the summary?" / meta talk)
            (r'(youtube\.com|youtu\.be).{0,200}\b(summarize|summari[sz]e|this video|about this|summary (this|that|it|the video)|get (the )?transcript|fetch (the )?transcript|what does (this|the) (vid|video|song|clip)|what (is|does) (this|the) (vid|video)|lyrics|what.?s (this|the) (vid|video|song) (about|say))\b',
             'yt_vid_transcript.py', 6),
            (r'\b(summarize|summari[sz]e|this video|about this|summary (this|that|it|the video)|get (the )?transcript|fetch (the )?transcript|what does (this|the) (vid|video|song|clip)|what (is|does) (this|the) (vid|video)|lyrics|what.?s (this|the) (vid|video|song) (about|say))\b.{0,200}(youtube\.com|youtu\.be)',
             'yt_vid_transcript.py', 6),
            # Intent alone (monitor may supply the YT url)
            (r'\bwhat does (this|the) (vid|video|song|clip)\b',
             'yt_vid_transcript.py', 5),
            (r'\bwhat (is|does) (this|the) (vid|video)\b',
             'yt_vid_transcript.py', 5),
            (r'\b(get|fetch|pull|extract|show|grab)\b.{0,25}\btranscript\b',
             'yt_vid_transcript.py', 6),
            (r'\btranscript\b.{0,20}\b(of|for|from)\b',
             'yt_vid_transcript.py', 5),
            (r'\bsummari[sz]e\b.{0,40}\b(video|yt|youtube|clip)\b',
             'yt_vid_transcript.py', 5),
            (r'\bsummary\b.{0,15}\b(this|that|it|the video)\b',
             'yt_vid_transcript.py', 3),

            # Scrape — URL/domain + page intent
            (r'https?://\S+',
             'scrape_site.py', 2),
            (r'\bscrape\b',
             'scrape_site.py', 5),
            (r'https?://\S+.{0,100}\b(scrape|fetch|get (the )?page|read (this )?page|what does (this|the) (site|page)|what.?s on (this|the) (site|page))\b',
             'scrape_site.py', 5),
            (r'\b(scrape|fetch)\b.{0,100}https?://',
             'scrape_site.py', 5),
            (r'\bwhat does (this|the) (site|page)\b',
             'scrape_site.py', 5),
            (r'\bwhat.?s on (this|the) (site|page)\b',
             'scrape_site.py', 5),
            (r'\b(read|open|check)\b.{0,20}\b(this|the)\b.{0,15}\b(site|page|website)\b',
             'scrape_site.py', 4),
            # bare domain in monitor (example.com / thedailystar.net) — weak alone
            (r'\b[a-z0-9-]+\.(com|net|org|io|co|info|edu|gov|bd|uk|ai)(/|\s|\]|$)',
             'scrape_site.py', 2),

            # ─── MESSENGER ──────────────────────────────────────────────
            (r'\b(send|text|message|msg|dm)\b.{0,40}\b(to|saying|that)\b',
             'send_message_to_messenger.py', 5),
            (r'\b(reply|respond)\b.{0,30}\b(to|on)\b.{0,20}\b(messenger|inbox|chat)\b',
             'send_message_to_messenger.py', 5),
            (r'\b(messenger|inbox)\b.{0,25}\b(message|text|reply|msg|send)\b',
             'send_message_to_messenger.py', 4),
            (r'\btell\b.{0,20}\b(that|him|her|them)\b.{0,30}\b(via|on|through)\b.{0,15}\bmessenger\b',
             'send_message_to_messenger.py', 5),
            (r'\btell\b\s+\w+.{0,50}\b(that|he|she|they|him|her|them)\b',
             'send_message_to_messenger.py', 5),
            (r'\btell\b\s+\w+\s+(to\s+)?["\']',
             'send_message_to_messenger.py', 4),
            # "tell <name> <message>" — not "tell me ..."
            (r'\btell\b\s+(?!me\b)\w+\s+\S+',
             'send_message_to_messenger.py', 5),

            # ─── CHAT MONITOR ───────────────────────────────────────────
            (r'\b(monitor|watch|connect\s+to|start\s+watching)\b.{0,25}\b(inbox|messenger|chat)\b',
             'chat_monitor', 6),
            (r'\bwatch\b.{0,20}\b(messenger|inbox)\b',
             'chat_monitor', 5),

            # ─── SCREEN ─────────────────────────────────────────────────
            (r'\b(check|look\s+at|see|read|what.?s?\s+on|what.?s?\s+in)\b.{0,20}\b(screen|monitor|display)\b',
             'check_screen', 5),
            (r'\b(screenshot|screen\s*shot|grab\s+screen)\b',
             'check_screen', 5),
            (r'\b(error|popup|notification|dialog)\b.{0,20}\b(on\s+)?(screen|monitor|display)?\b',
             'check_screen', 3),
            (r'\bwhat\b.{0,15}\b(on|in)\b.{0,10}\b(my\s+)?(screen|monitor)\b',
             'check_screen', 5),

            # ─── FILE FIND ──────────────────────────────────────────────
            (r'\b(find|locate|where\s+is|where\'s)\b.{0,35}\b(file|folder|document|pdf|docx?|xlsx?|pptx?)\b',
             'find_file.py', 5),
            (r'\b(read|open|show|get)\b.{0,25}\b(file|folder)\b',
             'find_file.py', 4),
            (r"\bwhere('s| is)\b.{0,25}\bmy\b.{0,20}\b\S+\.(pdf|docx?|xlsx?|pptx?|txt|py|json|zip)\b",
             'find_file.py', 5),
            (r'\b(find|locate|open|read|where)\b.{0,40}\S+\.(pdf|docx?|xlsx?|pptx?|mp[34]|mkv|zip|txt|py|json|exe|msi|lnk|ini|cfg|sav)\b',
             'find_file.py', 5),
            (r'\S+\.(pdf|docx?|xlsx?|pptx?|mp[34]|mkv|zip|txt|py|json|exe)\b',
             'find_file.py', 2),

            # ─── CALENDAR ───────────────────────────────────────────────
            (r'\b(add|create|schedule|set\s+up|book|put|make)\b.{0,45}\b(event|meeting|reminder|appointment|calendar)\b',
             'calendar_add_multiple_events.py', 5),
            (r'\b(what do i have|what\'s on|what is on|my schedule|my plans?|calendar)\b.{0,25}\b(today|tomorrow|this week)\b',
             'calendar_add_multiple_events.py', 5),
            (r'\b(schedule|plans?|calendar)\b.{0,15}\b(for\s+)?(today|tomorrow)\b',
             'calendar_add_multiple_events.py', 4),
            (r"\bwhat'?s?\b(?:(?!weather|temperature|forecast|temp).){0,20}\b(tomorrow|today)\b",
             'calendar_add_multiple_events.py', 4),
            (r'\b(tomorrow|today)\b.{0,25}\b(at\s+\d|am|pm|\d{1,2}:\d{2})\b',
             'calendar_add_multiple_events.py', 3),

            # ─── EXERCISE ───────────────────────────────────────────────
            (r'\blog\b.{0,25}\b(workout|exercise|push\s?ups?|pull\s?ups?|squats?|run|cardio|reps?)\b',
             'exercise_logger.py', 5),
            (r'\b(exercise|workout)\b.{0,20}\b(summary|log|history|today)\b',
             'exercise_logger.py', 5),
            (r'\bupdate\b.{0,20}\bskill\b',
             'exercise_logger.py', 4),
            (r'\b(log|record)\b.{0,15}\b(sets?|reps?|intensity)\b',
             'exercise_logger.py', 4),

            # ─── PHONE ──────────────────────────────────────────────────
            (r'\b(phone|mobile|adb)\b.{0,35}\b(click|tap|press|button)\b',
             'click_phone_button.py', 5),
            (r'\b(click|tap|press)\b.{0,25}\b(phone|mobile)\b.{0,15}\bbutton\b',
             'click_phone_button.py', 5),

            # ─── MUSIC ──────────────────────────────────────────────────
            (r'\bplay\b.{0,45}\b(song|music|track|album|playlist)\b',
             'play_yt_music.py', 5),
            (r'\b(play|put on)\b\s+["\'][^"\']+["\']',
             'play_yt_music.py', 3),
            (r'\b(play|queue)\b\s+\S.{5,60}$',
             'play_yt_music.py', 2),

            # ─── SEARCH ─────────────────────────────────────────────────
            (r'\b(search|look\s?up|find\s+(info|information|out)|look\s+for\s+info)\b',
             'search_net', 4),
            # "google X" but not "Google Chrome" / "Google Search" (window titles)
            (r'\bgoogle\b(?!\s*(chrome|search)\b)',
             'search_net', 4),
            (r'\b(what is|who is|who was|when (is|was|did|does)|where (is|was|can)|how (do|does|did|can|to|much|many|old|long))\b',
             'search_net', 4),
            # "why is/does/did X" but not "why did you" (meta about the assistant)
            (r'\bwhy (is|does|did)\b(?!\s+you\b)',
             'search_net', 4),
            (r'\b(latest|news on|info on|tell me about|explain)\b',
             'search_net', 4),
            (r'\bfind me\b(?!.{0,20}\b(file|folder)\b)',
             'search_net', 4),
            (r'\b(weather|forecast|temperature)\b',
             'search_net', 4),
            # status questions: "still free?", "not anymore?", "is X down?"
            (r'\b(is|are|does|did|can|will)\b.{0,50}\b(still|anymore|available|free|down|working|supported)\b',
             'search_net', 4),
            (r'\b(not|no longer)\b.{0,30}\b(free|available|supported|working)\b',
             'search_net', 4),
            (r'\b(anymore|still free|still available)\b',
             'search_net', 4),

            # ─── SAVE ───────────────────────────────────────────────────
            (r'\bsave\b.{0,20}\b(this|that|the)\s+(code|script|as)\b',
             'save', 5),
            (r'\bsave\s+(it|this|that)\s+as\b',
             'save', 4),

            # ─── CODE MAPPER ────────────────────────────────────────────
            (r'\b(code\s*map|map\s+code|code_mapper)\b',
             'code_mapper.py', 6),
            (r'\b(map|analyze)\b.{0,25}\b(codebase|code\s+structure|file\s+structure)\b',
             'code_mapper.py', 4),
        ]

        self.compiled = [
            (re.compile(p, re.IGNORECASE | re.DOTALL), tool, weight)
            for p, tool, weight in self.rules
        ]
        # bare "no"/"not" are too aggressive (cancels hits after "[MONITOR] No activity...")
        self.negation = re.compile(
            r"\b(don'?t|do\s+not|never|stop|without|avoid|skip)\b",
            re.IGNORECASE,
        )
        self.name_prefix = re.compile(
            r'^\s*(hey\s+)?logic[,!]?\s*',
            re.IGNORECASE,
        )
        self.min_score = 4.0
        self.min_margin = 1.5
        self.exclusive = {
            'yt_vid_transcript.py': ['scrape_site.py', 'search_net', 'play_yt_music.py', 'find_file.py'],
            'scrape_site.py': ['search_net'],
            'send_message_to_messenger.py': ['chat_monitor', 'search_net'],
            'chat_monitor': ['check_screen', 'send_message_to_messenger.py'],
            'check_screen': ['chat_monitor'],
            'find_file.py': ['search_net'],
            'play_yt_music.py': ['yt_vid_transcript.py', 'search_net'],
            'calendar_add_multiple_events.py': ['search_net'],
            'exercise_logger.py': ['search_net'],
        }

    def _strip_name(self, prompt: str) -> str:
        return self.name_prefix.sub('', prompt).strip()

    def _prepare_prompt(self, prompt: str) -> str:
        prompt = re.sub(r'relevant_memory:\[[^\]]*\]', ' ', prompt, flags=re.IGNORECASE)
        prompt = re.sub(r'SCRIPT_RESULT:\s*', ' ', prompt, flags=re.IGNORECASE)
        prompt = re.sub(r'^\s*system:\s*', '', prompt, flags=re.IGNORECASE)
        prompt = re.sub(r'\[+MONITOR\]\s*', ' ', prompt, flags=re.IGNORECASE)
        return re.sub(r'\s+', ' ', prompt).strip()

    def _negated(self, prompt: str, match_start: int) -> bool:
        window = prompt[max(0, match_start - 35):match_start]
        return bool(self.negation.search(window))

    def route(self, prompt: str):
        """Returns (tool_name | None, scores_dict)."""
        if not prompt or not isinstance(prompt, str):
            return None, {}

        # System feedback loops must never trigger a tool
        if re.search(r'\bSCRIPT_RESULT\s*:', prompt, re.IGNORECASE):
            return None, {}
        if str(prompt).strip().lower().startswith('system:'):
            return None, {}

        clean = self._strip_name(self._prepare_prompt(prompt))
        lowered = clean.lower()
        scores = defaultdict(float)

        for pattern, tool, weight in self.compiled:
            for m in pattern.finditer(lowered):
                if self._negated(lowered, m.start()):
                    continue
                scores[tool] += weight
                break

        if not scores:
            return None, {}

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        best_tool, best_score = ranked[0]
        if best_score >= self.min_score and best_tool in self.exclusive:
            for rival in self.exclusive[best_tool]:
                if rival in scores and scores[rival] <= best_score:
                    scores[rival] *= 0.3

        ranked = sorted(scores.items(), key=lambda x: -x[1])
        best_tool, best_score = ranked[0]
        second_score = ranked[1][1] if len(ranked) > 1 else 0.0

        if best_score >= self.min_score and (best_score - second_score) >= self.min_margin:
            return best_tool, dict(scores)
        return None, dict(scores)


# singleton for import use
_router = ToolRouter()


def guess_tool(prompt: str):
    """
    Return the best tool name for this prompt, or None if the model should decide.

    Examples:
        guess_tool("check my screen")           → "check_screen"
        guess_tool("tell hamim that he is late") → "send_message_to_messenger.py"
        guess_tool("hello")                      → None
    """
    tool, _ = _router.route(prompt)
    return tool
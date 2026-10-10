"""
tool_router.py — minimal tool router for LOGIC integration.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import NamedTuple


class Rule(NamedTuple):
    pattern: re.Pattern[str]
    tool: str
    weight: float


def format_tool_sequence(steps: list[tuple[int, str]]) -> str:
    """Format a list of (step_num, tool_name) into a natural sequence string."""
    if not steps:
        return ""
    if len(steps) == 1:
        return steps[0][1]
    if len(steps) == 2:
        return f"first {steps[0][1]}, then {steps[1][1]}"

    parts: list[str] = []
    total = len(steps)
    for i, (_, tool) in enumerate(steps):
        if i == 0:
            parts.append(f"first {tool}")
        elif i == total - 1:
            parts.append(f"finally {tool}")
        else:
            parts.append(f"then {tool}")
    return ", ".join(parts)


class ToolRouter:
    def __init__(self) -> None:
        self.min_score: float = 4.0
        self.min_margin: float = 1.5

        raw_rules: list[tuple[str, str, float]] = [
            # ─── YT / TRANSCRIPT ─────────────────────────────────────────
            (r'(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+', 'yt_vid_transcript.py', 2.0),
            (
                r'(youtube\.com|youtu\.be).{0,150}\b(summarize|summari[sz]e|this video|about this|'
                r'summary (this|that|it|the video)|get (the )?transcript|fetch (the )?transcript|'
                r'what does (this|the) (vid|video|song|clip)|what (is|does) (this|the) (vid|video)|'
                r'lyrics|what.?s (this|the) (vid|video|song) (about|say))\b',
                'yt_vid_transcript.py',
                6.0,
            ),
            (
                r'\b(summarize|summari[sz]e|this video|about this|summary (this|that|it|the video)|'
                r'get (the )?transcript|fetch (the )?transcript|what does (this|the) (vid|video|song|clip)|'
                r'what (is|does) (this|the) (vid|video)|lyrics|what.?s (this|the) (vid|video|song) (about|say))\b'
                r'.{0,150}(youtube\.com|youtu\.be)',
                'yt_vid_transcript.py',
                6.0,
            ),
            (r'\bwhat does (this|the) (vid|video|song|clip)\b', 'yt_vid_transcript.py', 5.0),
            (r'\bwhat (is|does) (this|the) (vid|video)\b', 'yt_vid_transcript.py', 5.0),
            (r'\b(get|fetch|pull|extract|show|grab)\b.{0,25}\btranscript\b', 'yt_vid_transcript.py', 6.0),
            (r'\btranscript\b.{0,20}\b(of|for|from)\b', 'yt_vid_transcript.py', 5.0),
            (r'\bsummari[sz]e\b.{0,40}\b(video|yt|youtube|clip)\b', 'yt_vid_transcript.py', 5.0),
            (r'\bsummary\b.{0,15}\b(this|that|it|the video)\b', 'yt_vid_transcript.py', 3.0),

            # ─── SCRAPE / WEB PAGE ──────────────────────────────────────
            (r'https?://\S+', 'scrape_site.py', 2.0),
            (r'\bscrape\b', 'scrape_site.py', 5.0),
            (
                r'https?://\S+.{0,100}\b(scrape|fetch|get (the )?page|read (this )?page|'
                r'what does (this|the) (site|page)|what.?s on (this|the) (site|page))\b',
                'scrape_site.py',
                5.0,
            ),
            (r'\b(scrape|fetch)\b.{0,100}https?://', 'scrape_site.py', 5.0),
            (r'\bwhat does (this|the) (site|page)\b', 'scrape_site.py', 5.0),
            (r'\bwhat.?s on (this|the) (site|page)\b', 'scrape_site.py', 5.0),
            (r'\b(read|open|check)\b.{0,20}\b(this|the)\b.{0,15}\b(site|page|website)\b', 'scrape_site.py', 4.0),
            (r'\b[a-z0-9-]+\.(com|net|org|io|co|info|edu|gov|bd|uk|ai)(/|\s|\]|$)', 'scrape_site.py', 2.0),

            # ─── MESSENGER ──────────────────────────────────────────────
            (r'''\b(send|dm|text|msg)\b\s+(me|him|her|them|\w+)\s+["'][^"']+["']''', 'send_message_to_messenger.py', 6.0),
            (r'^\s*(if\s+.{1,30}\s+)?(please\s+)?(send|text|dm|msg)\b\s+(?!a\b|the\b)(me|him|her|them|\w+)\b\s+\S+', 'send_message_to_messenger.py', 6.0),
            (r'\b(send|forward|dm|text)\b.{0,40}\b(to|into)\b.{0,20}\b(inbox|messenger|chat)\b', 'send_message_to_messenger.py', 6.0),
            (r'\b(send|forward|dm|text)\b.{0,25}\b(to\s+my\s+inbox|to\s+messenger)\b', 'send_message_to_messenger.py', 6.0),
            (r'^\s*(please\s+)?(can|could|will|would)\s+you\s+(send|text|dm)\b.{0,40}\b(to|saying|that)\b', 'send_message_to_messenger.py', 6.0),
            (r'^\s*(send|text|dm)\b.{0,40}\b(to|saying|that)\b', 'send_message_to_messenger.py', 6.0),
            (r'\b(reply|respond)\b.{0,30}\b(to|on)\b.{0,20}\b(messenger|inbox|chat)\b', 'send_message_to_messenger.py', 5.0),
            (r'\b(messenger|inbox)\b.{0,25}\b(message|text|reply|msg|send)\b', 'send_message_to_messenger.py', 4.0),
            (r'\btell\b.{0,20}\b(that|him|her|them)\b.{0,30}\b(via|on|through)\b.{0,15}\bmessenger\b', 'send_message_to_messenger.py', 5.0),
            (r'\btell\b\s+(?!me\b)(?!us\b)(?!him\b)(?!her\b)(?!them\b)(?!you\b)\w+\s+\S+', 'send_message_to_messenger.py', 5.0),

            # ─── CHAT MONITOR ───────────────────────────────────────────
            (r'\b(read|check|see|look\s+at|any)\b.{0,30}\b(unread|new|incoming)\s+(msgs?|messages?|inbox|dms?|texts?|chats?)\b', 'chat_monitor', 6.0),
            (r'\b(read|check)\b.{0,20}\b(msgs?|messages?|inbox|dms?)\b', 'chat_monitor', 5.0),
            (r'\b(see|check)\s+if\b.{0,25}\b(msgs?|messaged|texted|dmed|wrote|replied)\b', 'chat_monitor', 6.0),
            (r'\b(monitor|watch|connect\s+to|start\s+watching)\b.{0,25}\b(inbox|messenger|chat)\b', 'chat_monitor', 6.0),
            (r'\bmonitor\b\s+(me|my\s+\w+)\b', 'chat_monitor', 5.0),
            (r'\bwatch\b.{0,20}\b(messenger|inbox)\b', 'chat_monitor', 5.0),

            # ─── SCREEN ─────────────────────────────────────────────────
            (r'\b(check|look\s+at|see|read|what.?s?\s+on|what.?s?\s+in)\b.{0,20}\b(screen|monitor|display)\b', 'check_screen', 5.0),
            (r'\b(screenshot|screen\s*shot|grab\s+screen)\b', 'check_screen', 5.0),
            (r'\b(error|popup|notification|dialog)\b.{0,20}\b(on\s+)?(screen|monitor|display)?\b', 'check_screen', 3.0),
            (r'\bwhat\b.{0,15}\b(on|in)\b.{0,10}\b(my\s+)?(screen|monitor)\b', 'check_screen', 5.0),

            # ─── FILE FIND ──────────────────────────────────────────────
            (r'\b(find|locate|where\s+is|where\'s)\b.{0,35}\b(file|folder|document|pdf|docx?|xlsx?|pptx?)\b', 'find_file.py', 5.0),
            (r'\b(read|open|show|get)\b.{0,25}\b(file|folder)\b', 'find_file.py', 4.0),
            (r"\bwhere('s| is)\b.{0,25}\bmy\b.{0,20}\b\S+\.(pdf|docx?|xlsx?|pptx?|txt|py|json|zip)\b", 'find_file.py', 5.0),
            (r'\b(find|locate|open|read|where)\b.{0,40}\S+\.(pdf|docx?|xlsx?|pptx?|mp[34]|mkv|zip|txt|py|json|exe|msi|lnk|ini|cfg|sav)\b', 'find_file.py', 5.0),
            (r'\b(find|locate|open|read|where)\b.{0,40}\S+\.(txg|pfd|doc|xlx|ppt|jso)\b', 'find_file.py', 4.0),
            (r'\S+\.(pdf|docx?|xlsx?|pptx?|mp[34]|mkv|zip|txt|py|json|exe)\b', 'find_file.py', 2.0),

            # ─── CALENDAR ───────────────────────────────────────────────
            (r'\b(add|create|schedule|set\s+up|book|put|make)\b.{0,45}\b(event|meeting|reminder|appointment|calendar)\b', 'calendar_add_multiple_events.py', 5.0),
            (r'\b(what do i have|what\'s on|what is on|my schedule|my plans?|calendar)\b.{0,25}\b(today|tomorrow|this week)\b', 'calendar_add_multiple_events.py', 5.0),
            (r'\b(schedule|plans?|calendar)\b.{0,15}\b(for\s+)?(today|tomorrow)\b', 'calendar_add_multiple_events.py', 4.0),
            (r"\bwhat'?s?\s+my\b.{0,15}\b(schedule|plan|calendar)\b", 'calendar_add_multiple_events.py', 6.0),
            (r'\bmy\b.{0,15}\b(schedule|plan|calendar)\b.{0,15}\b(today|tomorrow|this week)\b', 'calendar_add_multiple_events.py', 6.0),
            (r'\b(tomorrow|today)\b.{0,25}\b(at\s+\d|am|pm|\d{1,2}:\d{2})\b', 'calendar_add_multiple_events.py', 3.0),

            # ─── EXERCISE ───────────────────────────────────────────────
            (r'\blog\b.{0,25}\b(workout|exercise|push\s?ups?|pull\s?ups?|squats?|run|cardio|reps?)\b', 'exercise_logger.py', 5.0),
            (r'\b(exercise|workout)\b.{0,20}\b(summary|log|history|today)\b', 'exercise_logger.py', 5.0),
            (r'\bupdate\b.{0,20}\bskill\b', 'exercise_logger.py', 4.0),
            (r'\b(log|record)\b.{0,15}\b(sets?|reps?|intensity)\b', 'exercise_logger.py', 4.0),

            # ─── PHONE ──────────────────────────────────────────────────
            (r'\b(phone|mobile|adb)\b.{0,35}\b(click|tap|press|button)\b', 'click_phone_button.py', 5.0),
            (r'\b(click|tap|press)\b.{0,25}\b(phone|mobile)\b.{0,15}\bbutton\b', 'click_phone_button.py', 5.0),

            # ─── MUSIC ──────────────────────────────────────────────────
            (r'\bplay\b.{0,45}\b(song|music|track|album|playlist)\b', 'play_yt_music.py', 5.0),
            (r'''\b(play|put on)\b\s+["'][^"']+["']''', 'play_yt_music.py', 3.0),
            (r'\b(play|queue)\b\s+\S.{5,60}$', 'play_yt_music.py', 2.0),

            # ─── SEARCH ─────────────────────────────────────────────────
            (r'\b(find|get|search|download|grab|look\s+for)\b.{0,60}\b(from|on)\s+(the\s+)?(net|web|internet|online)\b', 'search_net', 7.0),
            (r'\b(from|on)\s+(the\s+)?(net|web|internet)\b', 'search_net', 6.0),
            (r'\b(download|torrent)\b', 'search_net', 6.5),
            (r'\b(find|get|look\s+for)\b.{0,20}\b(info|information)\b.{0,20}\b(from|on|in)\b.{0,10}\b(this|that|the)\s+(site|page|website)\b', 'scrape_site.py', 6.0),
            (r'\b(search|look\s?up|find\s+(info|information|out)|look\s+for\s+info)\b', 'search_net', 4.0),
            (r'\bgoogle\b(?!\s*(chrome|search)\b)', 'search_net', 4.0),
            (r'\b(what is|who is|who was|when (is|was|did|does)|where (is|was|can)|how (do|does|did|can|to|much|many|old|long))\b', 'search_net', 4.0),
            (r'\bwhy (is|does|did)\b(?!\s+you\b)', 'search_net', 4.0),
            (r'\b(latest|news on|info on|tell me about|explain)\b', 'search_net', 4.0),
            (r'\bfind me\b(?!.{0,20}\b(file|folder)\b)', 'search_net', 4.0),
            (r'\b(weather|forecast|temperature)\b', 'search_net', 4.0),
            (r'\b(is|are|does|did|can|will)\b.{0,50}\b(still|anymore|available|free|down|working|supported)\b', 'search_net', 4.0),
            (r'\b(not|no longer)\b.{0,30}\b(free|available|supported|working)\b', 'search_net', 4.0),
            (r'\b(anymore|still free|still available)\b', 'search_net', 4.0),

            # ─── SAVE & CODE MAPPER ──────────────────────────────────────
            (r'\bsave\b.{0,20}\b(this|that|the)\s+(code|script|as)\b', 'save', 5.0),
            (r'\bsave\s+(it|this|that)\s+as\b', 'save', 4.0),
            (r'\b(code\s*map|map\s+code|code_mapper)\b', 'code_mapper.py', 6.0),
            (r'\b(map|analyze)\b.{0,25}\b(codebase|code\s+structure|file\s+structure)\b', 'code_mapper.py', 4.0),
        ]

        self.compiled: list[Rule] = [
            Rule(re.compile(p, re.IGNORECASE), tool, weight)
            for p, tool, weight in raw_rules
        ]

        self.negation = re.compile(
            r"\b(don'?t|do\s+not|won'?t|wouldn'?t|shouldn'?t|never|stop|without|avoid|skip)\b",
            re.IGNORECASE,
        )

        self.clause_separator = re.compile(r"([.;!\n]|\bbut\b|\bhowever\b)", re.IGNORECASE)

        self.blocklist = re.compile(
            r"^\s*(thank(s|\s+you)?|hello|hi|hey|bye|good\s+(morning|evening|night)|howdy)\b[.!?, ]*$|"
            r"^\s*(how are you|what do you think|who are you|what can you do|tell me about yourself)\b[.?!\s]*$",
            re.IGNORECASE,
        )

        self.past_done = re.compile(
            r"^\s*(i\s+)?(already|just)\s+(checked|sent|found|opened|read|got|did|logged|played|added)\b",
            re.IGNORECASE,
        )

        self.name_prefix = re.compile(r"^\s*(hey\s+)?logic[,!]?\s*", re.IGNORECASE)

        # Splitting supports commas followed by action verbs (with or without 'and')
        self.compound_splitter = re.compile(
            r"(?:"
            r"[;,]?\s*(?:and\s+then|after\s+that|then)\b|"
            r"(?:[;,]\s*(?:and\s+)?|\s+and\s+)"
            r"(?=(?:send|check|find|read|open|get|look|search|tell|show|play|add|create|"
            r"schedule|log|record|monitor|watch|scrape|download|save|update|click|tap|press|"
            r"grab|fetch|pull|extract|forward)\b)|"
            r"\.+\s*(?=(?:send|check|find|read|open|get|look|search|tell|show|play|add|create|schedule|log|record|monitor|watch|scrape|download|save|update|click|tap|press|grab|fetch|pull|extract|forward)\b)|[;\n]+"
            r")",
            re.IGNORECASE,
        )

        self.exclusive: dict[str, list[str]] = {
            'yt_vid_transcript.py': ['scrape_site.py', 'search_net', 'play_yt_music.py', 'find_file.py'],
            'scrape_site.py': ['search_net'],
            'send_message_to_messenger.py': ['chat_monitor', 'search_net'],
            'chat_monitor': ['check_screen', 'send_message_to_messenger.py'],
            'check_screen': ['chat_monitor'],
            'find_file.py': ['search_net'],
            'search_net': ['find_file.py'],
            'play_yt_music.py': ['yt_vid_transcript.py', 'search_net'],
            'calendar_add_multiple_events.py': ['search_net'],
            'exercise_logger.py': ['search_net'],
        }

    def _strip_name(self, prompt: str) -> str:
        return self.name_prefix.sub("", prompt).strip()

    def _prepare_prompt(self, prompt: str) -> str:
        prompt = re.sub(r"relevant_memory:\[[^\]]*\]", " ", prompt, flags=re.IGNORECASE)
        prompt = re.sub(r"SCRIPT_RESULT:\s*", " ", prompt, flags=re.IGNORECASE)
        prompt = re.sub(r"^\s*system:\s*", "", prompt, flags=re.IGNORECASE)
        prompt = re.sub(r"\[+MONITOR\]\s*", " ", prompt, flags=re.IGNORECASE)
        prompt = re.sub(
            r"^(hmm+|um+|uh+|er+|ah+|ok+|okay+|so+|well+|hi|hello|hey|please)[,\.\s]+",
            "",
            prompt,
            flags=re.IGNORECASE,
        )
        return re.sub(r"\s+", " ", prompt).strip()

    def _negated(self, prompt: str, match_start: int) -> bool:
        window_start = max(0, match_start - 50)
        window = prompt[window_start:match_start]
        matches = list(self.clause_separator.finditer(window))
        if matches:
            last_bound = matches[-1].end()
            window = window[last_bound:]
        return bool(self.negation.search(window))

    def _split_compound(self, prompt: str) -> list[str]:
        parts = self.compound_splitter.split(prompt)
        return [p.strip() for p in parts if p and p.strip()]

    def route(self, prompt: str, last_tool: str | None = None) -> tuple[str | None, dict[str, float]]:
        if not prompt or not isinstance(prompt, str):
            return None, {}

        if re.search(r"\bSCRIPT_RESULT\s*:", prompt, re.IGNORECASE):
            return None, {}
        if prompt.strip().lower().startswith("system:"):
            return None, {}

        clean = self._strip_name(self._prepare_prompt(prompt))
        if not clean:
            return None, {}

        if self.blocklist.match(clean) or self.past_done.search(clean):
            return None, {}

        if last_tool and re.match(
            r"^\s*(yes|yeah|ok|okay|do it|that one|go ahead|sure)\b", clean, re.IGNORECASE
        ):
            return last_tool, {"context_inherit": 1.0}

        lowered = clean.lower()
        scores: dict[str, float] = defaultdict(float)

        for rule in self.compiled:
            for m in rule.pattern.finditer(lowered):
                if self._negated(lowered, m.start()):
                    continue
                scores[rule.tool] += rule.weight
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

    def _check_implicit_file_send(self, prompt: str) -> list[tuple[int, str]] | None:
        lowered = prompt.lower()
        if not re.search(r"\b(send|forward|share|deliver)\b", lowered):
            return None

        # Check for filename with extension or file noun
        has_file_ext = re.search(r"\S+\.(pdf|docx?|xlsx?|pptx?|mp[34]|mkv|zip|txt|py|json|exe|csv|png|jpe?g)\b", lowered)
        has_file_noun = re.search(r"\b(the|that|this|my|a)?\s*(file|pdf|doc|document|spreadsheet|folder|txt|script|notes)\b", lowered)
        if not (has_file_ext or has_file_noun):
            return None

        # Check for recipient or inbox target
        has_recipient = re.search(
            r"(\b(to|into)\s+(\w+|my\s+inbox|messenger)\b|\b(send|forward|share)\s+(?!the\b|that\b|this\b|a\b|my\b)\w+\b)",
            lowered
        )
        if not has_recipient:
            return None

        # Web/download check
        is_web = re.search(r"\b(from|on)\s+(the\s+)?(net|web|internet)|online|torrent|download|https?://", lowered)
        first_tool = "search_net" if is_web else "find_file.py"
        return [(1, first_tool), (2, "send_message_to_messenger.py")]

    def route_multi(self, prompt: str, last_tool: str | None = None) -> list[tuple[int, str]]:
        clean = self._strip_name(self._prepare_prompt(prompt))
        parts = self._split_compound(clean)

        if len(parts) <= 1:
            implicit = self._check_implicit_file_send(clean)
            if implicit:
                return implicit
            tool, _ = self.route(prompt, last_tool)
            return [(1, tool)] if tool else []

        steps: list[tuple[int, str]] = []
        step_num = 1
        current_ctx = last_tool

        for part in parts:
            tool, _ = self.route(part, current_ctx)
            if tool:
                # Deduplicate identical consecutive tools
                if not steps or steps[-1][1] != tool:
                    steps.append((step_num, tool))
                    step_num += 1
                current_ctx = tool

        return steps


_router = ToolRouter()


def guess_tool(prompt: str, last_tool: str | None = None) -> str | None:
    steps = _router.route_multi(prompt, last_tool)
    return format_tool_sequence(steps) if steps else None

def guess_tools(prompt: str, last_tool: str | None = None) -> str | None:
    steps = _router.route_multi(prompt, last_tool)
    return format_tool_sequence(steps) if steps else None


if __name__ == "__main__":
    while True:
        try:
            query = input("YOU: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query:
            continue
        if query.lower() in (":q", ":quit", "exit"):
            break
        res = guess_tools(query)
        if res:
            print(f"→ SEQUENCE: {res}")
        else:
            print("→ NONE (model decides)")
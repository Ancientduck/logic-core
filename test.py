"""
patch.py — Plain-text patcher for tool_router.py
Run with:
    python patch.py
"""

from pathlib import Path

TARGET = Path("tool_router.py")

if not TARGET.exists():
    print("[-] Error: tool_router.py not found.")
    exit(1)

content = TARGET.read_text(encoding="utf-8")

old_block = """    def route_multi(self, prompt: str, last_tool: str | None = None) -> list[tuple[int, str]]:
        clean = self._strip_name(self._prepare_prompt(prompt))
        parts = self._split_compound(clean)

        if len(parts) <= 1:
            tool, _ = self.route(prompt, last_tool)
            return [(1, tool)] if tool else []"""

new_block = """    def _check_implicit_file_send(self, prompt: str) -> list[tuple[int, str]] | None:
        lowered = prompt.lower()
        if not re.search(r"\\b(send|forward|share|deliver)\\b", lowered):
            return None

        # Check for filename with extension or file noun
        has_file_ext = re.search(r"\\S+\\.(pdf|docx?|xlsx?|pptx?|mp[34]|mkv|zip|txt|py|json|exe|csv|png|jpe?g)\\b", lowered)
        has_file_noun = re.search(r"\\b(the|that|this|my|a)?\\s*(file|pdf|doc|document|spreadsheet|folder|txt|script|notes)\\b", lowered)
        if not (has_file_ext or has_file_noun):
            return None

        # Check for recipient or inbox target
        has_recipient = re.search(
            r"(\\b(to|into)\\s+(\\w+|my\\s+inbox|messenger)\\b|\\b(send|forward|share)\\s+(?!the\\b|that\\b|this\\b|a\\b|my\\b)\\w+\\b)",
            lowered
        )
        if not has_recipient:
            return None

        # Web/download check
        is_web = re.search(r"\\b(from|on)\\s+(the\\s+)?(net|web|internet)|online|torrent|download|https?://", lowered)
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
            return [(1, tool)] if tool else []"""

if "_check_implicit_file_send" not in content and old_block in content:
    content = content.replace(old_block, new_block, 1)
    TARGET.write_text(content, encoding="utf-8")
    print("[✓] Patched tool_router.py successfully.")
else:
    print("[!] Already patched or target block not found.")

# Quick verification
import tool_router

tests = [
    "logic send hamim the pdf",
    "logic send that file to hamim",
    "send logic_test.txt to hamim",
    "send logic_test.txt from the net to hamim",
    'send hamim "see you soon"',
]

print("\nVerifying outputs:")
for t in tests:
    print(f"YOU: {t}")
    print(f"→ SEQUENCE: {tool_router.guess_tools(t)}")
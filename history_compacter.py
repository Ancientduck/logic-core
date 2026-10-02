import json
import re
from typing import List, Dict, Any, Tuple, Optional


class ConversationHistorySummarizer:
    """
    Manages and compacts LLM conversation history JSON arrays using
    rolling structured state extraction and recent-turn buffering.
    """

    def __init__(
        self,
        token_budget: int = 1200,      # Trigger compression when context exceeds this
        keep_recent_messages: int = 4, # Number of recent messages to keep verbatim
        char_per_token: float = 3.8    # Rule of thumb for fast token estimation
    ):
        self.token_budget = token_budget
        self.keep_recent_messages = keep_recent_messages
        self.char_per_token = char_per_token

    def estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Rough token estimator (~3.8 to 4 chars per token)."""
        total_chars = sum(len(m.get("content", "")) + len(m.get("role", "")) for m in messages)
        return int(total_chars / self.char_per_token)

    def should_compact(self, messages: List[Dict[str, str]]) -> bool:
        """Determines if the history exceeds the designated token budget."""
        return self.estimate_tokens(messages) > self.token_budget

    def _extract_existing_summary(self, messages: List[Dict[str, str]]) -> Tuple[Optional[str], List[Dict[str, str]]]:
        """Checks if a system summary message already exists from a previous run."""
        clean_history = []
        existing_summary = None

        for msg in messages:
            if msg.get("role") == "system" and "[CONVERSATION STATE SUMMARY]" in msg.get("content", ""):
                existing_summary = msg["content"]
            else:
                clean_history.append(msg)

        return existing_summary, clean_history

    def generate_llm_prompt(self, messages_to_compress: List[Dict[str, str]], prior_summary: Optional[str] = None) -> str:
        """
        Production hook: Returns the exact prompt to send to an LLM (e.g. gpt-4o-mini
        or claude-3-haiku) if you want an LLM to generate the compression.
        """
        formatted_dialogue = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in messages_to_compress])
        prior_context = f"\nPRIOR SUMMARY TO UPDATE:\n{prior_summary}\n" if prior_summary else ""

        return f"""You are an expert context compressor for LLM conversation history.
Condense the following conversation into a high-density, fact-preserving structured summary.

CRITICAL REQUIREMENTS:
- Preserve user identity, role, preferences, and explicitly mentioned technical stacks.
- Preserve all decisions made, architectural choices, and bugs solved.
- Preserve concrete values (file paths, endpoints, port numbers, package names, keys).
- Drop all greetings, conversational filler, and rhetorical questions.

{prior_context}
MESSAGES TO COMPRESS:
{formatted_dialogue}

Return the summary strictly in this format:
### CORE USER & PROJECT PROFILE:
- [Items]
### KEY DECISIONS & ESTABLISHED FACTS:
- [Items]
### RESOLVED ISSUES & TECHNICAL ARTIFACTS:
- [Items]
### ACTIVE PENDING TASKS / OPEN QUESTIONS:
- [Items]
"""

    def _fallback_extractive_compressor(self, messages_to_compress: List[Dict[str, str]], prior_summary: Optional[str] = None) -> str:
        """
        Standalone/offline summarizer: Uses semantic pattern extraction to distill 
        facts without requiring an active external OpenAI/Anthropic API key.
        """
        facts = []
        technical_artifacts = []
        user_profile = []
        
        # Patterns for key indicators
        profile_patterns = [r"(i am|my name is|i'm working on|i build|i prefer|we use)", re.IGNORECASE]
        tech_patterns = [r"(/[\w\./\-]+)", r"(\b[A-Z0-9_-]{8,}\b)", r"(POST|GET|PUT|DELETE)", r"(\b(Rust|Python|SQLx|Postgres|Docker|Redis|JWT|Stripe)\b)"]

        for msg in messages_to_compress:
            role = msg['role'].capitalize()
            content = msg['content']
            lines = content.split('\n')

            for line in lines:
                line_str = line.strip().lstrip('-*• ')
                if not line_str:
                    continue

                # Detect user profile declarations
                if msg['role'] == 'user' and re.search(profile_patterns[0], line_str, profile_patterns[1]):
                    user_profile.append(line_str)
                    continue

                # Detect technical entities / endpoints / code references
                has_tech = False
                for p in tech_patterns:
                    matches = re.findall(p, line_str, re.IGNORECASE)
                    if matches:
                        has_tech = True
                
                # Check for decisions, solutions, errors
                if any(w in line_str.lower() for w in ["decided", "picked", "fixed", "bug", "resolved", "endpoint", "set to", "error"]):
                    facts.append(f"{role}: {line_str}")
                elif has_tech and len(line_str) < 140:
                    technical_artifacts.append(f"{role} noted: {line_str}")

        # Deduplicate & trim
        user_profile = list(dict.fromkeys(user_profile))[:4]
        facts = list(dict.fromkeys(facts))[:6]
        technical_artifacts = list(dict.fromkeys(technical_artifacts))[:4]

        summary_parts = ["[CONVERSATION STATE SUMMARY - AUTO-GENERATED]"]
        if prior_summary:
            summary_parts.append(f"PREVIOUS KNOWLEDGE:\n{prior_summary.replace('[CONVERSATION STATE SUMMARY - AUTO-GENERATED]', '').strip()}")

        if user_profile:
            summary_parts.append("USER PROFILE & CONSTRAINTS:\n- " + "\n- ".join(user_profile))
        if facts:
            summary_parts.append("KEY DECISIONS & RESOLUTIONS:\n- " + "\n- ".join(facts))
        if technical_artifacts:
            summary_parts.append("TECHNICAL SPECS & ENDPOINTS:\n- " + "\n- ".join(technical_artifacts))

        return "\n\n".join(summary_parts)

    def compact(
        self, 
        history: List[Dict[str, str]], 
        llm_summarizer_fn=None
    ) -> List[Dict[str, str]]:
        """
        Compresses the history if it exceeds token budget.
        
        Args:
            history: Full list of message dicts: [{'role': 'user', 'content': ...}, ...]
            llm_summarizer_fn: Optional callable taking a prompt string and returning
                               a string summary from a live LLM API.
        """
        if not self.should_compact(history):
            return history

        prior_summary, working_history = self._extract_existing_summary(history)

        # Retain root system message if one was explicitly provided
        root_system_msg = None
        if working_history and working_history[0]["role"] == "system":
            root_system_msg = working_history.pop(0)

        # Split into [Messages to Compress] and [Recent Buffer to Keep Verbatim]
        cutoff = max(1, len(working_history) - self.keep_recent_messages)
        to_compress = working_history[:cutoff]
        recent_buffer = working_history[cutoff:]

        # Run compression (via supplied LLM function or internal fallback)
        if llm_summarizer_fn:
            prompt = self.generate_llm_prompt(to_compress, prior_summary)
            new_summary_text = llm_summarizer_fn(prompt)
        else:
            new_summary_text = self._fallback_extractive_compressor(to_compress, prior_summary)

        # Assemble compacted history
        compacted: List[Dict[str, str]] = []

        if root_system_msg:
            compacted.append(root_system_msg)

        # Summary is placed into a dedicated system context message
        compacted.append({
            "role": "system",
            "content": f"[CONVERSATION STATE SUMMARY]\n{new_summary_text}"
        })

        # Append recent active messages without losing a single word
        compacted.extend(recent_buffer)

        return compacted


# =====================================================================
# LIVE TEST AND VERIFICATION SUITE
# =====================================================================
if __name__ == "__main__":
    print("=" * 80)
    print("AI CONVERSATION HISTORY SUMMARIZER: RUNNING TEST SUITE")
    print("=" * 80)

    # 1. Create a simulated long conversation history (JSON format)
    long_conversation_json = [
        {"role": "system", "content": "You are a senior Rust systems engineering assistant."},
        {"role": "user", "content": "Hello! I am Alex. I am a backend architect building an e-commerce engine in Rust."},
        {"role": "assistant", "content": "Welcome Alex! Glad to help. What database and framework are you thinking of using?"},
        {"role": "user", "content": "We decided to use Postgres and SQLx. I hate ORMs like Diesel because of macro compile times."},
        {"role": "assistant", "content": "Solid choice. SQLx gives compile-time checked queries without the heavy DSL abstractions of Diesel."},
        {"role": "user", "content": "I was hitting a critical bug in our auth handler: JWT tokens were immediately expiring."},
        {"role": "assistant", "content": "Check your claim validation: is exp being generated in milliseconds instead of seconds?"},
        {"role": "user", "content": "That was it! Fixed it by changing exp to epoch seconds: set to 3600 duration."},
        {"role": "assistant", "content": "Nice catch. Glad that's resolved."},
        {"role": "user", "content": "We just mapped out the payment webhook endpoint at /api/v1/stripe/webhook."},
        {"role": "assistant", "content": "Remember to use raw request payload bytes for validating Stripe's HMAC signature header."},
        {"role": "user", "content": "Good call. We will use Actix-web's web::Bytes to prevent payload mutation."},
        {"role": "assistant", "content": "Exactly right. That will preserve the exact byte order for HMAC SHA256 verification."},
        # ---- RECENT MESSAGES THAT MUST REMAIN UNTOUCHED ----
        {"role": "user", "content": "Can you now write the integration test for that /api/v1/stripe/webhook route?"},
        {"role": "assistant", "content": "Here is the integration test using actix_web::test and a mock Stripe header payload..."}
    ]

    # 2. Instantiate Summarizer with a low budget to trigger compression
    summarizer = ConversationHistorySummarizer(
        token_budget=250,        # Deliberately low threshold for demonstration
        keep_recent_messages=2   # Keep the last user question + assistant answer intact
    )

    # 3. Calculate initial metrics
    initial_tokens = summarizer.estimate_tokens(long_conversation_json)
    initial_count = len(long_conversation_json)

    print(f"\n[ORIGINAL HISTORY]")
    print(f"Total Messages : {initial_count}")
    print(f"Estimated Tokens: ~{initial_tokens} tokens")
    print(f"Compression Needed? -> {summarizer.should_compact(long_conversation_json)}")

    # 4. Perform Compact Operation
    compacted_history = summarizer.compact(long_conversation_json)

    # 5. Calculate compacted metrics
    compacted_tokens = summarizer.estimate_tokens(compacted_history)
    compacted_count = len(compacted_history)
    reduction = ((initial_tokens - compacted_tokens) / initial_tokens) * 100

    print(f"\n[COMPACTED HISTORY]")
    print(f"Total Messages : {compacted_count}")
    print(f"Estimated Tokens: ~{compacted_tokens} tokens")
    print(f"Token Reduction : -{reduction:.1f}%\n")

    # 6. Print JSON output to show real data structure
    print("-" * 40 + " GENERATED JSON OUTPUT " + "-" * 40)
    print(json.dumps(compacted_history, indent=2))
    print("-" * 103)

    # 7. Automated Verification Checks
    print("\n[VERIFICATION SANITY CHECKS]:")
    
    # Check 1: Root System Message preserved
    assert compacted_history[0]["role"] == "system"
    assert "senior Rust systems engineering assistant" in compacted_history[0]["content"]
    print(" PASS: Root system prompt retained at index 0.")

    # Check 2: Summary exists
    summary_msg = compacted_history[1]
    assert summary_msg["role"] == "system"
    assert "[CONVERSATION STATE SUMMARY]" in summary_msg["content"]
    print(" PASS: Rolling summary created in secondary system message.")

    # Check 3: Preserved core facts in compressed summary
    summary_text = summary_msg["content"]
    assert "Alex" in summary_text
    assert "Rust" in summary_text or "SQLx" in summary_text
    assert "3600" in summary_text or "JWT" in summary_text
    print(" PASS: Key facts (User: Alex, Tech: Rust/SQLx, JWT fix) preserved in summary.")

    # Check 4: Recency buffer is 100% identical
    assert compacted_history[-2] == long_conversation_json[-2]
    assert compacted_history[-1] == long_conversation_json[-1]
    print(" PASS: Most recent 2 turns preserved word-for-word.")

    print("\nAll tests passed successfully!")
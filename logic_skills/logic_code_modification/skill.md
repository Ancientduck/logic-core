# Skill: LOGIC Code Modification & Architecture

## Architecture Overview
- **Core Backend (`logic.py`)**: Master orchestration and runtime loop. Tool routing, execution, state management, and memory originate here.
- **TUI Frontend (`logic_tui.py`)**: Visual/terminal UI layer on top of `logic.py`.
  - *Rule*: When verifying code modifications or debugging, test via `logic.py` directly to isolate backend behavior from TUI rendering.
- **Prompt Engine (`logic_prompt.py`)**: Assembles dynamic context, system instructions, tool definitions, and relevant memory.
- **Voice & Telemetry**:
  - `logic_voice.py`: Text-to-speech module using Piper TTS. Reads assistant responses aloud.
  - `user_voice.py`: Speech-to-text input module enabling voice interaction from the user.
  - `activity_monitor.py`: Active window / telemetry daemon providing real-time `[MONITOR]` context lines.
- **Specialized Utilities**:
  - `logic_deepwrap.py`: DeepSeek wrapper utilizing browser cookies for vision capabilities.
  - `logic_template.py`: Testing script for provider API keys without spinning up OmniRoute.
- **Routing & Validation**:
  - `tool_router.py`: Suggests matching tools based on user prompt heuristics.
  - `validator.py`: Evaluates script outputs, catches exceptions/errors, provides corrective next steps, and enforces retry caps.
- **Sub-Agent Pool (`logic_hall.py`)**: Spawns and manages VINCI and SAGE worker subprocesses for focused operational tasks.
- **Legacy Backends (`other_logic/`)**: Historical variants and provider experiments. Do not modify unless instructed.
- **Memory Subsystem (`logic_memory_manager.py`, `memory/`)**: Tiered SQLite + FTS + Chroma vector database.

## Reload & Lifecycle Rules
- **Requires Process Restart**: Any modification to `logic.py`, imported core modules (`tool_router.py`, `validator.py`, `logic_voice.py`), or system prompt templates (`logic_prompt.py`).
- **No Restart Needed (Live Execution)**:
  - Standalone tools in `logic_tools/`: Modifying existing tool scripts takes effect immediately on next execution.
  - Skills in `logic_skills/<name>/skill.md`: Managed live via `read_skill` tool without restarts.
  - *Note*: New tools taking arguments can still be executed via script runner immediately, but `logic_prompt.py` must be updated for persistent argument signature awareness.

## Tool & Credential Management
1. **Tool Classification & Prompt Registration**:
   - **Internal Core Tools (`logic.py`)**: Custom tool handlers integrated into `Base_AI.call_logic`. *Mandatory*: Whenever a new internal tool handler is added to `logic.py`, `logic_prompt.py` MUST be updated manually in the system prompt `<tools>` definition block so the model is aware of its signature and usage (similar to `check_screen`, `read_credential`, etc.).
   - **One-Shot / Standalone (`logic_tools/`)**: Discrete execution scripts. Auto-scanned by `logic_prompt.py`. If complex argument structures are required, add concise usage signatures into `logic_prompt.py`.
   - **Persistent / Streaming (`logic.py`)**: Long-running background processes (monitors, listeners). Integrate into `logic.py` or dedicated imported helper.
2. **Credential Storage**:
   - Authentication files (JSON) go inside `logic_tools/oauth_token_files/`.
   - Read via `read_credential` tool.
   - Use clear descriptive names (e.g., `service_name_auth.json`). If the name is non-obvious, update the `read_credential` reference inside `logic_prompt.py`.

## Voice Configuration & Swapping (Piper TTS)
- **Engine**: Piper TTS configured in `logic_voice.py`.
- **Procedure to Change Voice**:
  1. Download the target Piper voice model pair (`.onnx` and `.onnx.json` files).
  2. Quality preference: `medium` preferred for balanced latency/quality; `high` can be used if requested.
  3. Place files in the appropriate voice models folder.
  4. Update the model file path references inside `logic_voice.py`.
  5. Restart backend for changes to take effect.

## Safety, Backups & Recovery
- **Local Backups**: Before making destructive or deep structural edits to core runtime files, create `.bak` copies and place them in a dedicated backup directory (`logic_bk/`) to avoid cluttering root.
- **Remote Repositories (Fallback Reference)**:
  - GitHub Account: `Ancientduck`
  - Logic Repository: `https://github.com/Ancientduck/logic` / `logic-core`
  - Check remote branch via Git or GitHub API if local restoration requires upstream diff.

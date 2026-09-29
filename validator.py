from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
from typing import Any, Callable

ASK_HUMAN = "tell your master"

@dataclasses.dataclass
class ExceptionDetail:
    exc_type: str
    message: str
    filename: str = ""
    lineno: int = 0
    code_context: str = ""
    root_cause: str = ""
    forbidden: str = ""
    next_step: str = ""

@dataclasses.dataclass
class Verdict:
    passed: bool
    tier: int = 1
    category: str = ""
    detail: str = ""
    root_cause: str = ""
    forbidden: str = ""
    next_step: str = ""
    retryable: bool = True
    escalated: bool = False
    exc: ExceptionDetail | None = None

    def report(self, raw: Any, attempt: int, max_attempts: int) -> str:
        if self.passed:
            return "OK"

        if attempt >= max_attempts:
            return (
                f"[MAX ATTEMPTS REACHED: {attempt}/{max_attempts}]\n"
                f"Status: Blocked. Do NOT attempt to run more code.\n"
                f"Error: {self.detail}\n"
                f"Instruction: You must escalate to the user immediately.\n"
                f"Output format:\n"
                f"{ASK_HUMAN}, what you tried, the exact error, and what the user needs to provide"
            )

        escalation_note = ""
        action_step = self.next_step
        forbidden_step = self.forbidden

        if attempt == 2:
            escalation_note = "[Tactical Adjustment] Direct fix failed. Verify inputs, check types, or isolate the target variable."
        elif attempt >= 3:
            escalation_note = "[Strategy Shift Required] Repeated failure with this pattern. Discard the current method and switch to standard library, CLI, or alternative tool."
            action_step = f"Rethink architecture: discard previous approach. {action_step}"

        lines = [
            f"[FAILED: Attempt {attempt}/{max_attempts}] [{self.category}]",
            f"Error: {self.detail}",
        ]

        if escalation_note:
            lines.append(f"Hint: {escalation_note}")

        if self.root_cause:
            lines.append(f"Root cause: {self.root_cause}")

        if forbidden_step:
            lines.append(f"DO NOT: {forbidden_step}")

        if action_step:
            lines.append(f"Action: {action_step}")

        if raw is not None:
            output = _truncate_output(raw)
            if output:
                lines.append(f"Output received:\n{output}")

        return "\n".join(lines)

_KB: dict[str, dict[str, str]] = {
    "FileNotFoundError": {
        "cause": "Path does not exist in the working directory.",
        "forbidden": "Do not reuse the same path without verifying it exists.",
        "fix": "Use find_file, os.getcwd(), or os.listdir() to verify the path before retrying.",
    },
    "ModuleNotFoundError": {
        "cause": "The requested Python module is not installed in the execution environment.",
        "forbidden": "Do not repeatedly import the unavailable module or guess alternative package names.",
        "fix": "Use an available standard-library solution or ask the user to install the required dependency.",
    },
    "AttributeError": {
        "cause": "An object does not contain the requested attribute or method, or the object is None.",
        "forbidden": "Do not repeat the same attribute access without checking the object's type or value.",
        "fix": "Inspect the object's type and available attributes before accessing the member.",
    },
    "KeyError": {
        "cause": "A dictionary key does not exist.",
        "forbidden": "Do not assume the missing key exists.",
        "fix": "Inspect dict.keys() or use dict.get() with an appropriate fallback.",
    },
    "IndexError": {
        "cause": "A sequence index is outside its valid range.",
        "forbidden": "Do not access the same index without checking the sequence length.",
        "fix": "Check len(items) before indexing.",
    },
    "TypeError": {
        "cause": "An operation or function received an incompatible type.",
        "forbidden": "Do not repeat the same incompatible type operation.",
        "fix": "Inspect the involved values with type() and correct or convert the types.",
    },
    "ValueError": {
        "cause": "A value has the correct general type but an invalid value or format.",
        "forbidden": "Do not pass the same invalid value again.",
        "fix": "Inspect the value and validate or normalize it before retrying.",
    },
    "SyntaxError": {
        "cause": "The Python source contains invalid syntax.",
        "forbidden": "Do not rerun the same unedited code.",
        "fix": "Fix the reported syntax, quoting, parentheses, or indentation problem before retrying.",
    },
    "IndentationError": {
        "cause": "The Python source contains invalid indentation.",
        "forbidden": "Do not rerun the same unedited code.",
        "fix": "Fix the indentation at the reported line before retrying.",
    },
    "JSONDecodeError": {
        "cause": "The program attempted to parse invalid JSON.",
        "forbidden": "Do not pass unchecked response text directly into json.loads().",
        "fix": "Inspect the raw response and validate its format before parsing.",
    },
    "PermissionError": {
        "cause": "The process does not have permission to access the requested resource.",
        "forbidden": "Do not repeatedly perform the same operation without changing the access conditions.",
        "fix": "Check the file permissions, process ownership, or whether another process has locked the resource.",
    },
    "IsADirectoryError": {
        "cause": "A directory was used where a file was expected.",
        "forbidden": "Do not open the directory as if it were a file.",
        "fix": "Verify the target path with os.path.isfile() before opening it.",
    },
    "NotADirectoryError": {
        "cause": "A file was used as though it were a directory.",
        "forbidden": "Do not append directory components to a file path.",
        "fix": "Check each path component and verify which paths are files and directories.",
    },
    "FileExistsError": {
        "cause": "The requested operation attempted to create something that already exists.",
        "forbidden": "Do not blindly recreate an existing resource.",
        "fix": "Check whether the target exists and decide whether to reuse, replace, or rename it.",
    },
    "TimeoutError": {
        "cause": "An operation exceeded its allowed execution time.",
        "forbidden": "Do not immediately repeat the same operation with identical timeout conditions.",
        "fix": "Inspect what the operation is waiting for and increase the timeout or change the approach if appropriate.",
    },
    "ConnectionError": {
        "cause": "A network or inter-process connection could not be established or maintained.",
        "forbidden": "Do not blindly retry the identical connection attempt.",
        "fix": "Check whether the target service is running and verify the host, port, and connection state.",
    },
}

_ENTITY_PATTERNS = {
    "ModuleNotFoundError": [
        re.compile(r"No module named ['\"]([^'\"]+)['\"]"),
    ],
    "AttributeError": [
        re.compile(r"'([^']+)' object has no attribute '([^']+)'"),
    ],
    "KeyError": [
        re.compile(r"^'([^']+)'$"),
        re.compile(r'^"([^"]+)"$'),
    ],
    "FileNotFoundError": [
        re.compile(r"No such file or directory: ['\"]([^'\"]+)['\"]"),
    ],
    "NameError": [
        re.compile(r"name '([^']+)' is not defined"),
    ],
    "TypeError": [
        re.compile(r"unexpected keyword argument '([^']+)'"),
        re.compile(r"missing \d+ required positional argument"),
    ],
    "ImportError": [
        re.compile(r"cannot import name '([^']+)' from ['\"]([^'\"]+)['\"]"),
    ],
}

def _extract_entity_hint(exc_type: str, message: str) -> tuple[str, str, str]:
    patterns = _ENTITY_PATTERNS.get(exc_type, [])
    for pat in patterns:
        m = pat.search(message)
        if m:
            groups = m.groups()
            if exc_type == "ModuleNotFoundError":
                mod = groups[0]
                return (
                    f"Dependency '{mod}' is missing from the environment.",
                    f"Do not attempt to import '{mod}' or guess package variations.",
                    f"Use Python standard library substitutes or execute via CLI/subprocess if an alternative utility exists.",
                )
            elif exc_type == "AttributeError":
                obj, attr = groups
                if obj == "NoneType":
                    return (
                        f"Attempted to access '{attr}' on a NoneType object.",
                        f"Do not access attributes on unverified return values.",
                        f"Add a check `if target is not None:` or inspect why the preceding call produced None.",
                    )
                return (
                    f"Object of type '{obj}' lacks attribute or method '{attr}'.",
                    f"Do not repeat access to .{attr}().",
                    f"Use `dir(target)` or type inspection to confirm available members on '{obj}'.",
                )
            elif exc_type == "KeyError":
                k = groups[0]
                return (
                    f"Dictionary key '{k}' does not exist.",
                    f"Do not assume key '{k}' is present.",
                    f"Use `dict.get('{k}')` or inspect `list(data.keys())` before accessing.",
                )
            elif exc_type == "FileNotFoundError":
                path = groups[0]
                return (
                    f"Target file or path does not exist: {path}",
                    f"Do not reuse '{path}' without verifying presence.",
                    f"Run find_file('{os.path.basename(path)}') or check os.path.exists() before opening.",
                )
            elif exc_type == "NameError":
                var = groups[0]
                return (
                    f"Identifier '{var}' is referenced before assignment or import.",
                    f"Do not call undefined variable '{var}'.",
                    f"Define '{var}' or check spelling and imports.",
                )
            elif exc_type == "TypeError":
                arg = groups[0] if groups else "unspecified"
                return (
                    f"Function signature mismatch regarding argument '{arg}'.",
                    f"Do not pass invalid argument '{arg}'.",
                    f"Inspect the callable's signature or help() before invoking.",
                )
            elif exc_type == "ImportError":
                name, mod = groups
                return (
                    f"Cannot import '{name}' from module '{mod}' (potential circular import or version skew).",
                    f"Do not repeat identical import from '{mod}'.",
                    f"Import module directly or inspect `dir({mod})` to verify exported symbols.",
                )
    return ("", "", "")

def _truncate_output(text: Any, max_lines: int = 24, max_chars: int = 2000) -> str:
    s = str(text).strip()
    if not s:
        return ""
    lines = s.splitlines()
    if len(lines) <= max_lines and len(s) <= max_chars:
        return s
    head = lines[:10]
    tail = lines[-10:]
    omitted = len(lines) - 20
    return "\n".join(head) + f"\n\n... [{omitted} lines truncated for context economy] ...\n\n" + "\n".join(tail)

def parse_traceback(tb: str) -> ExceptionDetail | None:
    if not isinstance(tb, str) or not tb.strip():
        return None

    if "Traceback (most recent call last):" not in tb:
        return None

    frame_matches = list(
        re.finditer(
            r'File "([^"]+)", line (\d+)(?:, in (.+))?',
            tb,
        )
    )

    if not frame_matches:
        return None

    lines = [line.rstrip() for line in tb.strip().splitlines() if line.strip()]
    if not lines:
        return None

    match = None
    for line in reversed(lines):
        m = re.match(
            r"^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning))(?::\s*(.*))?$",
            line.strip(),
        )
        if m:
            match = m
            break

    if not match:
        return None

    exc_type = match.group(1).split(".")[-1]
    message = match.group(2) or ""

    user_frame = None
    for f in reversed(frame_matches):
        fn = f.group(1).replace("\\", "/")
        if "site-packages" not in fn and "lib/python" not in fn.lower() and "Lib/test" not in fn:
            user_frame = f
            break

    frame = user_frame if user_frame else frame_matches[-1]
    filename = os.path.basename(frame.group(1))
    lineno = int(frame.group(2))

    code_context = ""
    frame_end = frame.end()
    remaining = tb[frame_end:].splitlines()

    for line in remaining:
        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("^"):
            continue

        if re.match(
            r"^[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning)(?::|$)",
            stripped,
        ):
            break

        code_context = stripped
        break

    ent_cause, ent_forbidden, ent_fix = _extract_entity_hint(exc_type, message)

    kb = _KB.get(
        exc_type,
        {
            "cause": f"Unhandled runtime error: {exc_type}.",
            "forbidden": "Do not retry identical code without adjustments.",
            "fix": "Inspect the failing line and handle the underlying exception.",
        },
    )

    return ExceptionDetail(
        exc_type=exc_type,
        message=message,
        filename=filename,
        lineno=lineno,
        code_context=code_context,
        root_cause=ent_cause or kb["cause"],
        forbidden=ent_forbidden or kb["forbidden"],
        next_step=ent_fix or kb["fix"],
    )

def tier1(raw: Any, expected_type: type | None = None) -> Verdict:
    if raw is None:
        return Verdict(
            passed=True,
            tier=1,
        )

    if isinstance(raw, str):
        exc = parse_traceback(raw)

        if exc:
            location = (
                f" at {exc.filename}:{exc.lineno}"
                if exc.filename
                else ""
            )

            context = (
                f" (line: `{exc.code_context}`)"
                if exc.code_context
                else ""
            )

            return Verdict(
                passed=False,
                tier=1,
                category=f"EXCEPTION:{exc.exc_type}",
                detail=f"{exc.exc_type}{location}: {exc.message}{context}",
                root_cause=exc.root_cause,
                forbidden=exc.forbidden,
                next_step=exc.next_step,
                exc=exc,
            )

    if expected_type and not isinstance(raw, expected_type):
        return Verdict(
            passed=False,
            tier=1,
            category="TYPE_MISMATCH",
            detail=f"Expected {expected_type.__name__}, got {type(raw).__name__}.",
            root_cause="The script returned a value of an unexpected type.",
            forbidden=f"Do not return {type(raw).__name__}.",
            next_step=f"Return or convert the result to {expected_type.__name__}.",
        )

    return Verdict(
        passed=True,
        tier=1,
    )

_CHECKS: dict[str, Callable[..., Verdict]] = {}

def register(name: str):
    def deco(fn: Callable[..., Verdict]):
        _CHECKS[name] = fn
        return fn
    return deco

@register("json_keys")
def _json_keys(
    raw: Any,
    required: list[str] | None = None,
) -> Verdict:
    text = raw if isinstance(raw, str) else json.dumps(raw, default=str)

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        return Verdict(
            passed=False,
            tier=2,
            category="JSON_INVALID",
            detail=f"Malformed JSON at line {e.lineno}, col {e.colno}: {e.msg}",
            root_cause="Invalid JSON syntax.",
            forbidden="Do not assemble JSON through unsafe manual string formatting.",
            next_step="Use json.dumps() or otherwise produce valid JSON.",
        )

    if not isinstance(obj, dict):
        return Verdict(
            passed=False,
            tier=2,
            category="JSON_NOT_DICT",
            detail="JSON is valid but the top-level value is not an object.",
            root_cause="Schema violation.",
            forbidden="Do not return an array or primitive when an object is expected.",
            next_step="Return a JSON object/dictionary.",
        )

    if required:
        missing = [key for key in required if key not in obj]

        if missing:
            return Verdict(
                passed=False,
                tier=2,
                category="JSON_MISSING_KEYS",
                detail=f"Missing required key(s): {missing}",
                root_cause="Required schema fields are missing.",
                forbidden=f"Do not omit required keys: {missing}.",
                next_step=f"Include the required keys: {missing}.",
            )

    return Verdict(
        passed=True,
        tier=2,
    )

@register("file_exists")
def _file_exists(raw: Any) -> Verdict:
    path = os.path.abspath(str(raw).strip())

    if not os.path.exists(path):
        return Verdict(
            passed=False,
            tier=2,
            category="FILE_NOT_FOUND",
            detail=f"File not found: {path}",
            root_cause="The specified path does not exist on disk.",
            forbidden="Do not return or reuse an unverified path.",
            next_step="Verify the path and inspect the directory before retrying.",
        )

    return Verdict(
        passed=True,
        tier=2,
    )

class CodeValidator:
    def __init__(self, max_attempts: int = 4):
        self.max_attempts = max_attempts
        self.attempts = 0
        self._seen_signatures: set[str] = set()

    def reset(self):
        self.attempts = 0
        self._seen_signatures.clear()

    def _normalize(self, text: str) -> str:
        s = re.sub(
            r'[A-Za-z]:\\[^"\n<>|]+',
            "<PATH>",
            str(text),
        )

        s = re.sub(
            r'/(?:[a-zA-Z0-9_.-]+/)+[a-zA-Z0-9_.-]+',
            "<PATH>",
            s,
        )

        s = re.sub(
            r'line \d+',
            "line <N>",
            s,
        )

        s = re.sub(
            r'0x[0-9a-fA-F]+',
            "<HEX>",
            s,
        )

        return s.strip()

    def validate(
        self,
        raw: Any,
        expected_type: type | None = None,
        tier2_checks: list[str] | str | None = None,
        **params,
    ) -> Verdict:
        v = tier1(raw, expected_type)

        if v.passed and tier2_checks:
            checks = (
                [tier2_checks]
                if isinstance(tier2_checks, str)
                else tier2_checks
            )

            for check_name in checks:
                fn = _CHECKS.get(check_name)

                if not fn:
                    v = Verdict(
                        passed=False,
                        tier=2,
                        category="CONFIG_ERROR",
                        detail=(
                            f"Unknown check '{check_name}'. "
                            f"Registered: {list(_CHECKS.keys())}"
                        ),
                        retryable=False,
                        escalated=True,
                    )
                    break

                result = fn(
                    raw,
                    **params.get(check_name, {}),
                )

                if not result.passed:
                    v = result
                    break

        if v.passed:
            self.attempts = 0
            self._seen_signatures.clear()
            return v

        self.attempts += 1

        signature = self._normalize(
            f"{v.category}:{v.detail}:{v.root_cause}"
        )

        signature_hash = hashlib.sha256(
            signature.encode()
        ).hexdigest()

        if (
            signature_hash in self._seen_signatures
            and self.attempts < self.max_attempts
        ):
            v.detail += " (REPEATED ERROR DETECTED)"
            v.forbidden += (
                " Stop resubmitting the identical fix that previously failed."
            )
            v.next_step = (
                f"Change your method completely, or output "
                f"{ASK_HUMAN} <question>."
            )
            v.retryable = False

        self._seen_signatures.add(signature_hash)

        if self.attempts >= self.max_attempts:
            v.escalated = True
            v.retryable = False

        return v

    def report(
        self,
        raw: Any,
        verdict: Verdict,
    ) -> str:
        return verdict.report(
            raw,
            self.attempts,
            self.max_attempts,
        )

validator = CodeValidator(max_attempts=4)

def validate(raw: Any) -> str:
    v = validator.validate(raw)
    return validator.report(raw, v)


if __name__ == "__main__":
    print("=" * 60)
    print("VALIDATOR SELF-TEST SUITE")
    print("=" * 60)

    # Test 1: Clean pass
    print("\n[TEST 1: Clean Output]")
    print(validate("Everything processed successfully. Result: 42"))

    # Test 2: AttributeError on NoneType with entity extraction
    print("\n[TEST 2: NoneType AttributeError]")
    sample_attr_tb = """Traceback (most recent call last):
  File "logic_tools/sample_app.py", line 18, in execute_task
    result = parser.extract_tokens(raw_data)
  File "C:/Users/USER/AppData/Local/Programs/Python/Python313/Lib/site-packages/engine/core.py", line 42, in extract_tokens
    return target.find()
AttributeError: 'NoneType' object has no attribute 'find'"""
    validator.reset()
    print(validate(sample_attr_tb))

    # Test 3: Missing dependency entity extraction
    print("\n[TEST 3: ModuleNotFoundError]")
    sample_mod_tb = """Traceback (most recent call last):
  File "logic_tools/scrape_task.py", line 3, in <module>
    import playwright
ModuleNotFoundError: No module named 'playwright'"""
    validator.reset()
    print(validate(sample_mod_tb))

    # Test 4: Repeated error loop detection
    print("\n[TEST 4: Repeated Failure Loop Detection]")
    validator.reset()
    for i in range(1, 3):
        print(f"--- Run {i} ---")
        print(validate(sample_mod_tb))

    # Test 5: Tier 2 schema validation
    print("\n[TEST 5: Tier 2 Check (json_keys)]")
    bad_payload = '{"status": "ok"}'
    v_t2 = validator.validate(bad_payload, tier2_checks=["json_keys"], json_keys={"required": ["status", "data", "token"]})
    print(validator.report(bad_payload, v_t2))

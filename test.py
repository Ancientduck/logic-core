"""
patch_thread_output.py
Patches run_threaded_code / show_threads in your Base_AI source file.

Usage:
    python patch_thread_output.py path\\to\\your_file.py
    python patch_thread_output.py path\\to\\your_file.py --dry-run

- Backs up the original to <file>.bak_<timestamp>
- Locates `def run_threaded_code(self, code_block: str):` and
  `def show_threads(self):` at the same indent level and replaces each
  method body up to the next same-indent `def`.
- Verifies the replacement compiles before writing.
"""

import argparse
import ast
import os
import re
import shutil
import sys
import time
from pathlib import Path


NEW_RUN_THREADED = '''    def run_threaded_code(self, code_block: str):
        task_id = f"bg_{int(time.time())}_{len(self.active_bg_tasks)+1}"

        def _worker(code, tid):
            temp_file = None

            try:
                with tempfile.NamedTemporaryFile(
                    "w", suffix=".py", delete=False, encoding="utf-8"
                ) as f:
                    f.write(code)
                    temp_file = f.name

                proc = subprocess.Popen(
                    ["python", "-u", temp_file],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
                )

                self.active_bg_tasks[tid] = {
                    "proc": proc,
                    "file": temp_file,
                    "hwnds": [],
                    "output": [],
                }

                time.sleep(0.4)

                hwnds = _get_hwnds_for_pid(proc.pid)
                self.active_bg_tasks[tid]["hwnds"] = hwnds

                for h in hwnds:
                    try:
                        win32gui.ShowWindow(h, win32con.SW_HIDE)
                    except Exception:
                        pass

                info = self.active_bg_tasks[tid]

                for line in iter(proc.stdout.readline, ''):
                    print(line, end='', flush=True)
                    info["output"].append(line)

                proc.wait()
                result = "".join(info["output"]).strip()

                if proc.returncode == 0:
                    user_input_queue.put(
                        f"system:[THREAD {tid} RESULT]\\n{result or '[no output]'}"
                    )
                elif proc.returncode in (1, -1, 15, 3221225786):
                    user_input_queue.put(
                        f"system:[THREAD {tid} TERMINATED]"
                        + (f"\\n{result}" if result else "")
                    )
                else:
                    user_input_queue.put(
                        f"system:[THREAD {tid} CRASHED with code {proc.returncode}]"
                        + (f"\\n{result}" if result else "")
                    )

            except Exception as e:
                user_input_queue.put(
                    f"system:[THREAD_ERROR {tid}]: {e}"
                )

            finally:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except OSError:
                        pass

        t = threading.Thread(
            target=_worker,
            args=(code_block, task_id),
            daemon=True
        )
        t.start()

        yield from self.call_logic(
            f"SYSTEM: Background task {task_id} started."
        )
'''


NEW_SHOW_THREADS = '''    def show_threads(self):
        if not self.active_bg_tasks:
            print("[LOGIC] No background threads active.")
            return

        print()
        print(f"[LOGIC] Active background threads ({len(self.active_bg_tasks)}):")

        for tid, info in list(self.active_bg_tasks.items()):
            proc = info["proc"]
            hwnds = _get_hwnds_for_pid(proc.pid)
            info["hwnds"] = hwnds

            any_visible = any(win32gui.IsWindowVisible(h) for h in hwnds)
            action = "Hidden" if any_visible else "Restored"
            cmd_flag = win32con.SW_HIDE if any_visible else win32con.SW_RESTORE

            for h in hwnds:
                try:
                    win32gui.ShowWindow(h, cmd_flag)
                    if not any_visible:
                        win32gui.SetForegroundWindow(h)
                except Exception:
                    pass

            output = "".join(info.get("output", [])).rstrip()
            if output:
                tail = output[-800:]
                if len(output) > len(tail):
                    tail = "...\\n" + tail
                output_block = "\\n    " + tail.replace("\\n", "\\n    ")
            else:
                output_block = " (no output yet)"

            status = "running" if proc.poll() is None else f"exited({proc.returncode})"
            print(f"  - {tid} (PID: {proc.pid}) [{status}] -> Console {action}")
            print(f"    output:{output_block}")

        print()
'''


def find_method_span(source: str, name: str, want_indent: int = 4):
    """
    Return (start_index, end_index, indent_str) of the full method def block.
    end_index is the index of the first char after the method (start of the
    next same-indent 'def'/'class' or EOF).
    """
    lines = source.splitlines(keepends=True)

    # locate the def line at the target indent
    start_line = None
    for i, line in enumerate(lines):
        stripped = line.lstrip(" \t")
        if stripped.startswith(f"def {name}("):
            indent = len(line) - len(stripped)
            if indent == want_indent:
                start_line = i
                break
    if start_line is None:
        return None

    # walk forward until we hit a line at same-or-lower indent that
    # starts a new def / class / top-level statement.
    end_line = len(lines)
    for j in range(start_line + 1, len(lines)):
        raw = lines[j]
        if not raw.strip():
            continue
        stripped = raw.lstrip(" \t")
        indent = len(raw) - len(stripped)
        if indent <= want_indent:
            # any line at or above method indent terminates the method,
            # but blank/comment lines don't matter since we already skip them
            end_line = j
            break

    # compute char offsets
    start_idx = sum(len(l) for l in lines[:start_line])
    end_idx = sum(len(l) for l in lines[:end_line])
    indent_str = " " * want_indent
    return start_idx, end_idx, indent_str


def replace_method(source: str, name: str, new_body: str, indent: int = 4):
    span = find_method_span(source, name, want_indent=indent)
    if span is None:
        return None, f"method '{name}' not found at indent {indent}"
    start, end, _ = span
    return source[:start] + new_body, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="Path to the .py file containing Base_AI")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    p = Path(args.path)
    if not p.is_file():
        print(f"[patch] not a file: {p}")
        sys.exit(1)

    original = p.read_text(encoding="utf-8")

    working = original
    for name, body in [
        ("run_threaded_code", NEW_RUN_THREADED),
        ("show_threads", NEW_SHOW_THREADS),
    ]:
        working, err = replace_method(working, name, body, indent=4)
        if err:
            print(f"[patch] ERROR: {err}")
            sys.exit(2)
        print(f"[patch] replaced {name}")

    # sanity check: must still parse
    try:
        ast.parse(working)
    except SyntaxError as e:
        print(f"[patch] ABORT: patched source does not parse: {e}")
        sys.exit(3)

    if working == original:
        print("[patch] no changes needed.")
        return

    if args.dry_run:
        print("[patch] dry-run, not writing.")
        # show a short diff summary
        print(f"[patch] original bytes: {len(original)} -> new bytes: {len(working)}")
        return

    backup = p.with_suffix(p.suffix + f".bak_{int(time.time())}")
    shutil.copy2(p, backup)
    p.write_text(working, encoding="utf-8")
    print(f"[patch] wrote {p}")
    print(f"[patch] backup: {backup}")


if __name__ == "__main__":
    main()
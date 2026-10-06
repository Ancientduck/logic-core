
"""
fix_anim_final.py — vlogic-anim-final (v2)

  1. Writes logic_framepump.py (unchanged from v1).
  2. logic_tui.py edits:
     a. removes the dead installer block: cut from its start marker to EOF
        (it was appended at EOF, so no end-marker math — this was v1's bug)
        + scrubs any stray bare '=====' lines for safety
     b. adds throttled stream fallback inside _merge_sink_and_gen  (same as v1)
     c. inserts a 2-line hook before the main guard                (same as v1)

Run:  python fix_anim_final.py
"""

import ast
import os
import re
import shutil
import sys

MARK = "vlogic-anim-final"

FRAMEPUMP_SRC = r'''"""vlogic frame pump.

Called from logic_tui.py before its main guard. Finds the App subclass,
wraps on_mount, and mounts a bottom-docked Static that animates
LOGIC_LIVE_FRAME in place. Falls back to the window subtitle.
"""


def install_frame_pump(ns=None):
    import inspect
    import sys

    if ns is None:
        main = sys.modules.get("__main__")
        ns = vars(main) if main is not None else {}

    try:
        from textual.app import App
        from textual.widgets import Static
        from rich.text import Text
    except Exception as e:
        print(f"[vlogic-pump] WARN: textual import failed: {e}")
        return False

    app_cls = None
    for obj in list(ns.values()):
        if isinstance(obj, type) and issubclass(obj, App) and obj is not App:
            app_cls = obj
            break
    if app_cls is None:
        print("[vlogic-pump] WARN: no App subclass found")
        return False

    if getattr(app_cls, "_vlogic_pumped", False):
        return True
    app_cls._vlogic_pumped = True

    orig_on_mount = getattr(app_cls, "on_mount", None)

    async def _pumped_on_mount(self, *a, **k):
        if orig_on_mount is not None:
            try:
                res = orig_on_mount(self, *a, **k)
                if inspect.isawaitable(res):
                    await res
            except Exception:
                pass

        if getattr(self, "_vlogic_pump_on", False):
            return
        self._vlogic_pump_on = True
        self._vlogic_seq = -1

        w = None
        try:
            w = Static("", id="vlogic-live-frame")
            try:
                await self.mount(w)
            except Exception:
                await self.screen.mount(w)
            w.styles.dock = "bottom"
            w.styles.height = "auto"
            w.styles.padding = (0, 1)
            w.display = False
            self._vlogic_frame_w = w
            lf = ns.get("LOGIC_LIVE_FRAME")
            if lf is not None:
                lf["pump"] = True
            print("[vlogic-pump] frame widget installed (bottom-docked)")
        except Exception as e:
            self._vlogic_frame_w = None
            print(f"[vlogic-pump] WARN: widget mount failed ({e}); subtitle fallback")

        def _pump():
            lf = ns.get("LOGIC_LIVE_FRAME")
            if lf is None:
                return
            if lf.get("seq") == self._vlogic_seq:
                return
            self._vlogic_seq = lf.get("seq", 0)
            txt = lf.get("text", "")
            try:
                w = self._vlogic_frame_w
                if w is not None:
                    if txt:
                        w.update(Text("▸ " + txt[:150], style="bold #e0af68"))
                        w.display = True
                    else:
                        w.update(Text(""))
                        w.display = False
                else:
                    self.sub_title = ("▸ " + txt[:80]) if txt else ""
            except Exception:
                pass

        self.set_interval(0.1, _pump)

    app_cls.on_mount = _pumped_on_mount
    print(f"[vlogic-pump] hooked into {app_cls.__name__}.on_mount")
    return True
'''


def read(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def syntax_fail(path, src, e):
    lines = src.splitlines()
    lo = max(0, (e.lineno or 1) - 5)
    hi = min(len(lines), (e.lineno or 1) + 4)
    print(f"[FAIL] {path} would not parse: {e.msg} at line {e.lineno}")
    print("─" * 60)
    for i in range(lo, hi):
        mk = ">>>" if i + 1 == e.lineno else "   "
        print(f" {mk} {i+1:5d}: {lines[i]}")
    print("─" * 60)
    print("nothing was written")
    sys.exit(1)


def replace_once(src, old, new, label):
    n = src.count(old)
    if n != 1:
        print(f"[FAIL] {label}: found {n} occurrences (need 1)")
        sys.exit(1)
    return src.replace(old, new, 1)


def main():
    write("logic_framepump.py", FRAMEPUMP_SRC)
    ast.parse(FRAMEPUMP_SRC)
    print("[OK] logic_framepump.py written")

    p = "logic_tui.py"
    if not os.path.exists(p):
        raise SystemExit(f"[FAIL] {p} not found")
    src = read(p)
    if MARK in src:
        print("[SKIP] already patched")
        return

    for needle in ('LOGIC_FRAME_PREFIX = "\\x00VFRAME\\x00"',
                   "def _merge_sink_and_gen(gen):"):
        if needle not in src:
            raise SystemExit(f"[FAIL] expected snippet not found: {needle!r}")

    shutil.copy(p, p + ".pre_anim_final")

    # (a) dead installer: appended at EOF by patch_progress.py -> cut to EOF.
    # v1 bug: we cut at the END marker which sits mid-banner-line, leaving a
    # stray ' ====' tail. Cut-to-EOF avoids end-marker math entirely.
    DEAD_START = "# === vlogic-progress-patch: live frame pump"
    if DEAD_START in src:
        src = src[: src.index(DEAD_START)].rstrip() + "\n"
        print("[OK] removed dead installer block (cut to EOF)")
    else:
        print("[INFO] dead installer block not present (fine)")

    # scrub any stray bare '=====' lines (never valid Python, safe to drop)
    src, n_scrub = re.subn(r"(?m)^[ \t]*=+[ \t]*\n?", "", src)
    if n_scrub:
        print(f"[OK] scrubbed {n_scrub} stray separator line(s)")

    # (b) throttled stream fallback in _merge_sink_and_gen
    src = replace_once(
        src,
        "    opened = False\n\n    def drain():\n        nonlocal opened\n",
        "    opened = False\n"
        "    last_frame_emit = 0.0\n\n"
        "    def drain():\n"
        "        nonlocal opened, last_frame_emit\n",
        "merger/init",
    )
    src = replace_once(
        src,
        "            if line.startswith(LOGIC_FRAME_PREFIX):\n"
        '                LOGIC_LIVE_FRAME["text"] = line[len(LOGIC_FRAME_PREFIX):].rstrip("\\r\\n")\n'
        '                LOGIC_LIVE_FRAME["seq"] += 1\n'
        "                continue\n",
        "            if line.startswith(LOGIC_FRAME_PREFIX):\n"
        '                body = line[len(LOGIC_FRAME_PREFIX):].rstrip("\\r\\n")\n'
        '                LOGIC_LIVE_FRAME["text"] = body\n'
        '                LOGIC_LIVE_FRAME["seq"] += 1\n'
        '                if not LOGIC_LIVE_FRAME.get("pump"):\n'
        "                    # vlogic-anim-final: pump missing -> throttled stream frames\n"
        "                    now = time.monotonic()\n"
        "                    if now - last_frame_emit >= 1.5:\n"
        "                        last_frame_emit = now\n"
        "                        if not opened:\n"
        '                            chunks.append("\\n\\n<tool_result>\\n")\n'
        "                            opened = True\n"
        '                        chunks.append("\\u25b8 " + body + "\\n")\n'
        "                continue\n",
        "merger/frame-divert",
    )

    # (c) hook before the LAST main guard
    guards = list(re.finditer(r'^if __name__ == ["\']__main__["\']:', src, re.M))
    if not guards:
        raise SystemExit("[FAIL] no `if __name__` guard found in logic_tui.py")
    g = guards[-1]
    hook = (
        "import logic_framepump as _vlg_fp  # vlogic-anim-final\n"
        "_vlg_fp.install_frame_pump(globals())\n\n"
    )
    src = src[:g.start()] + hook + src[g.start():]
    print("[OK] pump hook inserted before main guard")

    src = f"# {MARK}\n" + src

    try:
        ast.parse(src)
    except SyntaxError as e:
        syntax_fail(p, src, e)

    write(p, src)
    print(f"[OK] {p} patched (backup: logic_tui.py.pre_anim_final)")
    print("\nRestart the app. On startup you should see:")
    print("  [vlogic-pump] hooked into <YourApp>.on_mount")
    print("  [vlogic-pump] frame widget installed (bottom-docked)")
    print("Then run an install: an amber '▸ ...' line animates at the bottom.")


if __name__ == "__main__":
    main()
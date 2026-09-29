"""
DeepWrap vision-only image analyzer.

Usage:
  python image_analyzer.py <image> [image2 ...] ["prompt"]
  python image_analyzer.py                # interactive mode
  python image_analyzer.py --interactive  # force interactive

No history. No session reuse. No tools. Just fast, accurate image analysis
via DeepWrap's vision model.

Requires: deepwrap auth  (once)
"""
from __future__ import annotations

import sys
from pathlib import Path

from deepwrap import Client

DEFAULT_PROMPT = (
    "Describe this image in detail. Be specific: name objects, describe "
    "colors, positions, visible text, UI elements, and spatial relationships. "
    "Answer any question directly. Do not greet or ask follow-ups."
)

MODEL = "vision"


def _resolve_paths(raw_paths):
    """Accepts a list of strings (possibly comma-separated). Returns existing Paths."""
    out = []
    for chunk in raw_paths:
        for p in str(chunk).split(","):
            p = p.strip().strip('"').strip("'")
            if not p:
                continue
            path = Path(p).expanduser()
            if not path.exists():
                print(f"[skip] not found: {path}")
                continue
            out.append(path)
    return out


def analyze(client: Client, paths, prompt: str, stream: bool = True) -> str:
    """One fresh vision session, one answer, no history."""
    files = [str(p) for p in paths]
    chat = client.chats.create_session(model=MODEL)

    if stream:
        buf = []
        for chunk in chat.respond(prompt, files=files, stream=True, thinking=False):
            sys.stdout.write(chunk)
            sys.stdout.flush()
            buf.append(chunk)
        print()
        return "".join(buf)
    else:
        reply = chat.respond(prompt, files=files, stream=False, thinking=False)
        print(reply)
        return str(reply)


def interactive(client: Client):
    print("[vision] interactive image analyzer — no history saved.")
    print("        type image path(s), then optionally a question after '|'")
    print("        examples:")
    print("          ./photo.png")
    print("          ./a.png,./b.png | what differs between these two?")
    print("        /exit to quit\n")

    while True:
        try:
            line = input("image> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[exit]")
            break

        if not line:
            continue
        if line in ("/exit", "/quit", "exit", "quit"):
            print("[exit]")
            break

        if "|" in line:
            path_part, prompt_part = line.split("|", 1)
            prompt = prompt_part.strip() or DEFAULT_PROMPT
        else:
            path_part, prompt = line, DEFAULT_PROMPT

        paths = _resolve_paths([path_part])
        if not paths:
            print("[!] no valid images.")
            continue

        print(f"[vision] analyzing {len(paths)} image(s)...\n")
        try:
            analyze(client, paths, prompt, stream=True)
        except Exception as e:
            print(f"\n[error] {e}")


def main(argv):
    force_interactive = "--interactive" in argv or "-i" in argv
    args = [a for a in argv if a not in ("--interactive", "-i")]

    client = Client()

    if force_interactive or not args:
        interactive(client)
        return

    # Split positional args into paths + optional trailing prompt.
    # Heuristic: existing paths are images; the first non-path arg starts the prompt.
    path_args, prompt_parts = [], []
    in_prompt = False
    for a in args:
        if not in_prompt:
            cand = Path(a.strip().strip('"').strip("'")).expanduser()
            if cand.exists():
                path_args.append(a)
                continue
            in_prompt = True
        prompt_parts.append(a)

    paths = _resolve_paths(path_args)
    if not paths:
        print("usage: python image_analyzer.py <image> [more images] [\"prompt\"]")
        print("       python image_analyzer.py            # interactive")
        sys.exit(1)

    prompt = " ".join(prompt_parts).strip() or DEFAULT_PROMPT
    try:
        analyze(client, paths, prompt, stream=True)
    except Exception as e:
        print(f"[error] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
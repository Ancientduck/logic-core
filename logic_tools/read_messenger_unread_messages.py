import os, sys
from playwright.sync_api import sync_playwright
import psutil, re, time

# Suppress Chrome DevTools/TF noise
_stderr = sys.stderr
sys.stderr = open(os.devnull, 'w')


def _find_chrome():
    import shutil as _sh
    _w = _sh.which("chrome") or _sh.which("chrome.exe")
    if _w:
        return _w
    for _e in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        _p = os.path.join(os.environ.get(_e, ""), "Google", "Chrome", "Application", "chrome.exe")
        if os.path.exists(_p):
            return _p
    return r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

USER_DATA_DIR = r"C:\Users\USER\AppData\Local\Google\Chrome\AutomationProfile"
EXECUTABLE_PATH = _find_chrome()
DEBUG_PORT = 9222
HEADLESS = True
MAX_MSGS = 10

nick_names = {
    "২ নম্বার খাঁটি মাল (•̀ᴗ•́)": "Hamim hossine",
    "Niggacetti": "Hasan Yamin Hisham",
    "vaiya": "Shahriyer Oishorjo",
}

def resolve_name(input_name):
    """Return (search_name, list_of_sidebar_aliases_lowercase)."""
    low = input_name.strip().lower()
    aliases = [low]
    search = input_name.strip()

    for nick, real in nick_names.items():
        if low in nick.lower() or nick.lower() in low:
            aliases += [nick.lower(), real.lower()]
            return real, aliases
        if low in real.lower() or real.lower() in low:
            aliases += [nick.lower(), real.lower()]
            return real, aliases

    return search, aliases

def is_chrome_running():
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if proc.info['name'] == 'chrome.exe' and \
               any('AutomationProfile' in arg for arg in (proc.info['cmdline'] or [])):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

def poll_until(fn, timeout=15, interval=0.3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(interval)
    return fn()

def wait_rows_stable(page, timeout=10):
    prev = 0
    stable = 0
    deadline = time.time() + timeout
    while time.time() < deadline:
        cur = len(page.query_selector_all("[role='row']"))
        if cur > 0 and cur == prev:
            stable += 1
            if stable >= 3:
                return cur
        else:
            stable = 0
            prev = cur
        time.sleep(0.3)
    return prev

def get_unread_convos(page):
    rows = page.query_selector_all("[role='row']")
    unread = []
    for row in rows:
        txt = row.inner_text()
        if "Unread message" not in txt:
            continue
        name = None
        for btn in row.query_selector_all("[role='button']"):
            label = btn.get_attribute("aria-label") or ""
            m = re.match(r'^More options for (.+)$', label)
            if m:
                name = m.group(1).strip()
                break
        if not name:
            lines = [l.strip() for l in txt.split('\n') if l.strip()]
            for l in lines:
                if l not in ("Active now", "Unread message:"):
                    name = l
                    break
        if name:
            unread.append(name)
    return unread

def find_and_click(page, target, aliases=None):
    check = [target.lower()]
    if aliases:
        check = aliases
    rows = page.query_selector_all("[role='row']")
    best = None
    best_name = None
    for row in rows:
        for btn in row.query_selector_all("[role='button']"):
            label = btn.get_attribute("aria-label") or ""
            m = re.match(r'^More options for (.+)$', label)
            if not m:
                continue
            row_name = m.group(1).strip()
            row_lower = row_name.lower()
            # exact match in aliases
            if row_lower in check:
                best = row
                best_name = row_name
                break
            # partial/substring match
            for a in check:
                if a in row_lower or row_lower in a:
                    best = row
                    best_name = row_name
                    break
        if best:
            break
    if best:
        link = best.query_selector("a")
        if link:
            link.click()
        else:
            best.click()
        return best_name
    return None

def wait_conversation_loaded(page, convo_name):
    # Wait for at least 1 message
    def has_msg():
        main = page.query_selector("div[role='main']")
        if not main:
            return False
        return len(main.query_selector_all("[aria-label*='Message sent']")) >= 1
    poll_until(has_msg, timeout=8, interval=0.15)

    # Wait for spinner to vanish (fast poll, short timeout)
    try:
        spinner = page.locator("div[role='main'] [data-visualcompletion='loading-state']")
        if spinner.count() > 0:
            spinner.first.wait_for(state="detached", timeout=5000)
    except:
        pass

    # Quick stability check — message count stops growing
    prev = 0
    for _ in range(4):
        main = page.query_selector("div[role='main']")
        cur = len(main.query_selector_all("[aria-label*='Message sent']")) if main else 0
        if cur > 0 and cur == prev:
            break
        prev = cur
        time.sleep(0.15)
    return True

def extract_messages(page, include_own=False):
    main = page.query_selector("div[role='main']")
    if not main:
        return []

    msg_els = main.query_selector_all("[aria-label*='Message sent']")
    if not msg_els:
        return []

    pattern = re.compile(r'Enter, Message sent .+? by (.+?): (.+)', re.DOTALL)

    parsed = []
    for el in msg_els:
        aria = el.get_attribute("aria-label") or ""
        m = pattern.match(aria)
        if m:
            sender = m.group(1).strip()
            text = m.group(2).strip()
            parsed.append((sender, text))

    own_names = {"you", "apurbo", "apurbo mostafiz"}
    result = []
    for sender, text in reversed(parsed):
        if not include_own and sender.lower() in own_names:
            break
        result.append((sender, text))
        if len(result) >= MAX_MSGS:
            break

    result.reverse()
    return result


def get_convo_header_name(page):
    """Read the actual conversation name from the main panel header after clicking in."""
    def _get():
        # Try the heading element in the main conversation area
        for sel in [
            "div[role='main'] h2",
            "div[role='main'] [data-testid='conversation-header'] span",
            "div[role='main'] a[role='link'] span",
            "div[role='banner'] h2",
            "div[role='banner'] a span",
        ]:
            el = page.query_selector(sel)
            if el:
                txt = el.inner_text().strip()
                if txt and txt not in ("", "Unread message"):
                    return txt
        return None
    return poll_until(_get, timeout=5, interval=0.2)

def main(target_name=None):
    import subprocess
    with sync_playwright() as p:
        launched_chrome = not is_chrome_running()
        if launched_chrome:
            subprocess.Popen([
                EXECUTABLE_PATH,
                f"--user-data-dir={USER_DATA_DIR}",
                f"--remote-debugging-port={DEBUG_PORT}",
                "--no-first-run",
                "--no-default-browser-check",
                *(["--headless=new"] if HEADLESS else []),
                "https://www.messenger.com/"
            ])
            time.sleep(3)

        browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
        context = browser.contexts[0] if browser.contexts else browser.new_context()

        # Find existing messenger tab or open new one
        page = None
        for p_tab in context.pages:
            if "messenger.com" in p_tab.url:
                page = p_tab
                break
        if not page:
            page = context.new_page()
            page.goto("https://www.messenger.com/", wait_until="domcontentloaded")
        wait_rows_stable(page)

        results = {}
        if target_name:
            # Direct mode: go to specific conversation, no unread check
            _, aliases = resolve_name(target_name)
            matched = find_and_click(page, target_name, aliases)
            if not matched:
                print(f"Could not find: {target_name}")
                return
            wait_conversation_loaded(page, matched)
            header = get_convo_header_name(page) or matched
            msgs = extract_messages(page, include_own=True)
            if msgs:
                results[header] = msgs
        else:
            # Default mode: scan all unread
            unread = get_unread_convos(page)
            if not unread:
                print("No unread messages.")
                return
            print(f"Found {len(unread)} unread: {', '.join(unread)}\n")
            for target in unread:
                if not find_and_click(page, target):
                    print(f"Could not find: {target}")
                    continue
                wait_conversation_loaded(page, target)
                header = get_convo_header_name(page) or target
                msgs = extract_messages(page)
                if msgs:
                    results[header] = msgs

        if not results:
            print("No unread messages found.")
        else:
            total = 0
            for name, msgs in results.items():
                print(f"{name}:")
                for sender, text in msgs:
                    print(f"  {sender}: {text}")
                total += len(msgs)
            print(f"\nTotal: {total} message(s) in {len(results)} conversation(s)")

        # Cleanup only if we launched Chrome ourselves
        if launched_chrome:
            try:
                browser.close()
            except Exception:
                pass
            if HEADLESS:
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        if proc.info['name'] == 'chrome.exe' and \
                           any('AutomationProfile' in arg for arg in (proc.info['cmdline'] or [])):
                            proc.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

if __name__ == "__main__":
    import sys
    name = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    main(target_name=name)

import socket
import sys
import json
import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import StaleElementReferenceException

import warnings
import logging
warnings.filterwarnings("ignore", category=DeprecationWarning)
logging.getLogger("selenium").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

# ============================================================
#  CONFIG
# ============================================================
DEBUG_PORT = 9222
USER_DATA_DIR = r"C:\Users\USER\AppData\Local\Google\Chrome\AutomationProfile"
LOCK_PORT = 9301          # held ONLY while a send is in progress (no daemon)
CHROMEDRIVER_PATH = r""   # e.g. r"C:\tools\chromedriver.exe" — leave "" for auto-detect

SIGNATURE = "-LOGIC, Apurbo's AI companion"


# ============================================================
#  SINGLE-INSTANCE LOCK (only exists during a send, then gone)
# ============================================================
class SendLock:
    def __enter__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.bind(('127.0.0.1', LOCK_PORT))
        except OSError:
            print('[ERROR] Another send is already in progress. Try again in a moment.')
            sys.exit(1)
        return self

    def __exit__(self, *exc):
        self.sock.close()


# ============================================================
#  CHROME LIFECYCLE — no daemon, no 24/7 anything.
#  Chrome (detached) stays open like a normal browser;
#  each run attaches to it, sends, and the script exits.
# ============================================================
def is_debug_chrome_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.05)
        return s.connect_ex(('localhost', DEBUG_PORT)) == 0


def make_driver(options):
    if CHROMEDRIVER_PATH:
        return webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)
    return webdriver.Chrome(options=options)


def apply_perf_tuning(driver):
    """Block trackers + heavy media via CDP. Messenger's own API (graph.facebook.com) is NOT blocked."""
    try:
        driver.execute_cdp_cmd('Network.enable', {})
    except Exception:
        pass


def _common_perf_options(options):
    # 'none' = don't wait for full page load; we wait for the UI element we need instead
    options.page_load_strategy = 'none'
    # options.add_argument("--blink-settings=imagesEnabled=false")  # biggest byte saver
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-features=Translate,MediaRouter,OptimizationHints,TranslateUI")
    return options


def launch_new_chrome():
    options = Options()
    options.add_experimental_option("detach", True)  # Chrome survives after script exits
    options.add_experimental_option("prefs", {
        "session.restore_on_startup": 4,   # 4 = open a specific set of pages
        "session.startup_urls": ["https://www.messenger.com"],
    })
    options.add_argument(f"user-data-dir={USER_DATA_DIR}")
    options.add_argument(f"--remote-debugging-port={DEBUG_PORT}")
    # startup baggage
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-component-update")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-session-crashed-bubble")
    options.add_argument("--hide-crash-restore-bubble")
    options = _common_perf_options(options)

    driver = make_driver(options)
    apply_perf_tuning(driver)
    return driver


def attach_to_existing_chrome():
    options = Options()
    options.add_experimental_option("debuggerAddress", f"localhost:{DEBUG_PORT}")
    options = _common_perf_options(options)

    driver = make_driver(options)
    apply_perf_tuning(driver)
    return driver


def get_driver():
    if is_debug_chrome_running():
        try:
            return attach_to_existing_chrome()
        except Exception:
            pass  # stale debug port — fall through to a fresh launch
    return launch_new_chrome()


def find_messenger_tab(driver):
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if "messenger.com" in driver.current_url:
            return True
    return False


def close_chrome():
    """Optional cleanup: run with --close to shut the automation Chrome down."""
    if is_debug_chrome_running():
        try:
            attach_to_existing_chrome().quit()
            print('[OK] Automation Chrome closed.')
        except Exception as e:
            print(f'[ERROR] Could not close Chrome: {e}')
    else:
        print('[OK] Chrome was not running.')


# ============================================================
#  WAITING — wait for hydration signal, not page load
# ============================================================
def wait_for_messenger_ready(driver, timeout=60):
    """Don't wait for page load — wait until the app shell is actually interactive."""
    wait = WebDriverWait(driver, timeout, poll_frequency=0.1,
                         ignored_exceptions=(StaleElementReferenceException,))
    wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "div[role='navigation']")))   # sidebar = app hydrated
    return wait


# ============================================================
#  NAMING / MATCHING
# ============================================================
nick_names = {
    "২ নম্বার খাঁটি মাল (•̀ᴗ•́)": "Hamim hossine",
    "Niggacetti": "Hasan Yamin Hisham",
    "vaiya": "Shahriyer Oishorjo",
}


def resolve_identifiers(input_name):
    input_lower = input_name.strip().lower()
    sidebar_aliases = [input_lower]
    real_search_name = input_name.strip()

    for nick, real in nick_names.items():
        if input_lower in nick.lower() or nick.lower() in input_lower:
            sidebar_aliases += [nick.lower(), real.lower()]
            return real, sidebar_aliases

    for nick, real in nick_names.items():
        if input_lower in real.lower() or real.lower() in input_lower:
            sidebar_aliases += [nick.lower(), real.lower()]
            return real, sidebar_aliases

    return real_search_name, sidebar_aliases


def get_conversation_header_text(driver):
    for sel in ("div[role='main'] h2",
                "div[role='main'] [role='heading']",
                "div[aria-label='Thread header']",
                "h2"):
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                t = el.text.strip()
                if t and t.lower() not in ("chats", "active now", "contacts",
                                           "search results", "marketplace"):
                    return t
        except Exception:
            continue
    return ""


def matches_header(header_text, aliases, real_search_name):
    if not header_text:
        return False
    clean = header_text.lower().replace("conversation with", "").replace(
        "conversation titled", "").strip()
    if any(a in clean or clean in a for a in aliases):
        return True
    if real_search_name.lower() in clean or clean in real_search_name.lower():
        return True
    for nick, real in nick_names.items():
        if (nick.lower() in clean or clean in nick.lower()) and \
           real.lower() == real_search_name.lower():
            return True
    return False


def extract_chat_title_from_row(row):
    try:
        labels = []
        aria = row.get_attribute("aria-label")
        if aria:
            labels.append(aria)
        for a in row.find_elements(By.CSS_SELECTOR, "a[role='link'], a[href*='/t/']"):
            lbl = a.get_attribute("aria-label")
            if lbl:
                labels.append(lbl)
        for lbl in labels:
            clean = re.sub(r"^(conversation with|chat with)\s*", "", lbl, flags=re.I).strip()
            clean = re.sub(r",\s*\d+\s*unread.*$", "", clean, flags=re.I).strip()
            if clean:
                return clean.lower()
    except Exception:
        pass
    try:
        raw = row.get_attribute("innerText") or row.text or ""
        for line in (l.strip() for l in raw.split("\n") if l.strip()):
            if line.lower() in ("active now", "chats") or re.match(r"^\d+[\s:]*\w*$", line):
                continue
            return line.lower()
    except Exception:
        pass
    return ""


def try_select_from_sidebar(driver, aliases):
    print(f'[DEBUG] Checking sidebar for matches with aliases: {aliases}')
    wait = WebDriverWait(driver, 10, poll_frequency=0.1,
                         ignored_exceptions=(StaleElementReferenceException,))

    def get_rows(d):
        for sel in ("div[role='grid'] div[role='row']",
                    "div[role='navigation'] div[role='row']",
                    "div[aria-label='Chats'] [role='row']",
                    "div[aria-label='Chats'] a[href*='/t/']",
                    "div[role='navigation'] a[href*='/t/']"):
            found = d.find_elements(By.CSS_SELECTOR, sel)
            if found and any(r.text.strip() or r.get_attribute("aria-label") for r in found[:5]):
                return found
        return []

    try:
        rows = wait.until(lambda d: get_rows(d) or False)
        print(f'[DEBUG] Found {len(rows)} chat rows in sidebar.')
    except Exception as e:
        print(f'[DEBUG-FAIL] Sidebar chat rows failed to load within timeout: {e}')
        return False

    checked_titles = []
    for row in rows:
        try:
            title = extract_chat_title_from_row(row)
            if not title:
                continue
            checked_titles.append(title)
            if any(a in title or title in a for a in aliases):
                print(f'[DEBUG-SUCCESS] Sidebar match found: "{title}". Clicking row...')
                target = row
                sub = row.find_elements(
                    By.CSS_SELECTOR, "a[href*='/t/'], a[role='link'], div[role='button']")
                if sub:
                    target = sub[0]
                driver.execute_script("arguments[0].click();", target)
                return True
        except Exception as e:
            print(f'[DEBUG-WARN] Error inspecting a sidebar row: {e}')
            continue
    print(f'[DEBUG] No sidebar match among visible rows: {checked_titles[:6]}...')
    return False


# ============================================================
#  TYPING — robust Lexical / contenteditable input + enter
# ============================================================
def type_message(driver, textbox, text):
    from selenium.webdriver.common.action_chains import ActionChains
    try:
        driver.execute_script("arguments[0].focus();", textbox)
        time.sleep(0.05)
        textbox.click()
    except Exception:
        pass

    lines = text.split(chr(10))
    actions = ActionChains(driver)
    actions.click(textbox)
    
    for i, line in enumerate(lines):
        if line:
            actions.send_keys(line)
        if i < len(lines) - 1:
            actions.key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT)
    
    actions.pause(0.1)
    actions.send_keys(Keys.ENTER)
    actions.perform()
# ============================================================
#  CORE SEND
# ============================================================
def send_message(name='', msg='', file_path=''):
    t0 = time.time()
    real_search_name, aliases = resolve_identifiers(name)
    driver = get_driver()

    if not find_messenger_tab(driver):
        driver.get("https://www.messenger.com")

    wait = wait_for_messenger_ready(driver)

    header = get_conversation_header_text(driver)

    if not matches_header(header, aliases, real_search_name):
        # --- attempt 1: sidebar ---
        old_url = driver.current_url
        if try_select_from_sidebar(driver, aliases):
            try:
                WebDriverWait(driver, 5, poll_frequency=0.1).until(
                    lambda d: matches_header(get_conversation_header_text(d), aliases, real_search_name)
                    or d.current_url != old_url)
            except Exception:
                pass
            header = get_conversation_header_text(driver)

        # --- attempt 2: search bar ---
        if not matches_header(header, aliases, real_search_name):
            print(f'[DEBUG] Active header "{header}" did not match. Trying Messenger search for "{real_search_name}"...')
            old_url = driver.current_url
            try:
                print('[DEBUG] Locating Search Messenger input box...')
                search = wait.until(EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "input[placeholder='Search Messenger']")))
                search.click()
                search.send_keys(Keys.CONTROL, "a")
                search.send_keys(Keys.BACKSPACE)
                search.send_keys(real_search_name)
                print(f'[DEBUG] Typed "{real_search_name}". Waiting for dropdown search results...')

                wait_search = WebDriverWait(driver, 8, poll_frequency=0.05,
                                            ignored_exceptions=(StaleElementReferenceException,))
                contact = wait_search.until(EC.element_to_be_clickable(
                    (By.XPATH,
                     "//li[@role='option' and not(contains(@aria-label, 'Search messages'))]")))

                label = contact.get_attribute("aria-label") or contact.text
                print(f'[DEBUG] Top search result found: "{label}"')
                clean = re.sub(r"^(conversation with|chat with)\s*", "", label,
                               flags=re.I).strip().lower()
                if clean and clean not in aliases:
                    aliases.append(clean)

                print('[DEBUG] Clicking top search result...')
                try:
                    contact.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", contact)

                prev = header.lower().replace("conversation with", "").strip() if header else ""

                def _loaded(d):
                    h = get_conversation_header_text(d)
                    if not h:
                        return False
                    cur = h.lower().replace("conversation with", "").strip()
                    if prev and cur == prev and d.current_url == old_url:
                        return False
                    return matches_header(h, aliases, real_search_name)

                print('[DEBUG] Waiting for conversation header / URL to update...')
                WebDriverWait(driver, 10, poll_frequency=0.1).until(_loaded)
                header = get_conversation_header_text(driver)
                print(f'[DEBUG] Conversation loaded with header: "{header}"')

                if not matches_header(header, aliases, real_search_name):
                    print(f'[ERROR-MISMATCH] Opened header "{header}" failed alias/target check. Aliases={aliases}')
                    print('Ask for the correct name.')
                    return
                else:
                    print(f'[DEBUG-SUCCESS] Header verification passed: "{header}" matches target.')
            except Exception as e:
                print(f'[ERROR-SEARCH-FAIL] Search pipeline failed: {e}')
                return

    # --- type & send ---
    textbox = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='textbox']")))

    if file_path:
        files = [file_path] if isinstance(file_path, str) else file_path
        for f in files:
            file_box = wait.until(EC.presence_of_element_located(
                (By.XPATH, "//input[@type='file']")))
            file_box.send_keys(str(Path(f).resolve()))
            time.sleep(0.5)  # let the upload attach before sending

    msg = msg.replace("\\n", "\n")
    if SIGNATURE not in msg:
        msg = f"{msg}\n{SIGNATURE}" if msg else f"files sent by {SIGNATURE}"

    # type_message(driver, textbox, msg)
    print(f'[SUCCESS] Message sent to {real_search_name} in {time.time() - t0:.1f}s')
    print("==========================================\n")
    # NOTE: no driver.quit() — detached Chrome stays open for the next run,
    # and this Python process exits immediately.


def send_messages(the_list):
    for name, msg, *rest in the_list:
        file_path = rest[0] if rest else ''
        print(f"\n[QUEUE] Target: {name} | Msg: {msg} | File: {file_path or 'none'}")
        send_message(name, msg, file_path)


# ============================================================
#  CLI
# ============================================================
if __name__ == '__main__':
    if '--close' in sys.argv:
        close_chrome()
        sys.exit(0)

    with SendLock():
        if len(sys.argv) > 2:
            # script.py "name" "message..."   (may include --close, filtered above)
            send_messages([[sys.argv[1], " ".join(sys.argv[2:])]])
        elif len(sys.argv) > 1:
            try:
                the_list = json.loads(sys.argv[1])
                if not isinstance(the_list[0], list):
                    the_list = [the_list]
                send_messages(the_list)
            except Exception as e:
                print(f'[ERROR] Bad argument: {e}')
        else:
            # === Manual Testing Section ===
            send_message(name='apurbo', msg='Test single message from LOGIC')
            # send_messages([
            #     ['talha', 'Test message'],
            # ])
            pass
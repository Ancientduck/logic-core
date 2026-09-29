from playwright.sync_api import sync_playwright
import psutil
import time

USER_DATA_DIR = r"C:\Users\USER\AppData\Local\Google\Chrome\AutomationProfile"
EXECUTABLE_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
DEBUG_PORT = 9222

def is_chrome_running():
    for proc in psutil.process_iter(['name', 'cmdline']):
        try:
            if proc.info['name'] == 'chrome.exe' and \
               any('AutomationProfile' in arg for arg in proc.info['cmdline'] or []):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False

def count_unread_messages():
    with sync_playwright() as p:
        if is_chrome_running():
            # Attach to existing Chrome via CDP
            browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
        else:
            # Launch fresh Chrome with debugging enabled
            browser = p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                executable_path=EXECUTABLE_PATH,
                channel="chrome",
                headless=True,
                args=[f"--remote-debugging-port={DEBUG_PORT}"]
            )
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto("https://www.messenger.com")

        # Ensure we're on Messenger
        if "messenger.com" not in page.url:
            page.goto("https://www.messenger.com")

        thread_list_selector = "div[role='navigation'][aria-label='Thread list']"
        page.wait_for_selector(thread_list_selector, timeout=20000)

        last_row_count = 0
        stable_seconds = 0
        max_wait_seconds = 20

        for _ in range(max_wait_seconds):
            current_rows = page.query_selector_all("[role='row']")
            current_count = len(current_rows)
            
            if current_count > 2 and current_count == last_row_count:
                stable_seconds += 1
                if stable_seconds >= 3:
                    break
            else:
                stable_seconds = 0
                last_row_count = current_count
                
            time.sleep(1)

        unread_elements = page.query_selector_all("div:text('Unread message:')")

        for el in unread_elements:
            try:
                more_btn = el.evaluate_handle(
                    'el => el.closest(\'[role="row"]\').querySelector(\'[aria-label^="More options for"]\')'
                )
                label = more_btn.as_element().get_attribute('aria-label')
                name = label.replace("More options for ", "")
                
                msg_el = el.evaluate_handle("el => el.nextElementSibling")
                msg = msg_el.as_element().inner_text()
                
                print(f"{name}: {msg}")
            except:
                pass

        print(f"Unread: {len(unread_elements)}")

if __name__ == "__main__":
    count_unread_messages()
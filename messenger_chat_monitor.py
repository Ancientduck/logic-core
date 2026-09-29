# Semi-autonomous messaging system for LOGIC
# Placeholder for development
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
import requests
import sys
import time
import pyperclip
import threading
import socket
from selenium.common.exceptions import StaleElementReferenceException

DEBUG_PORT = 9222
USER_DATA_DIR = r"C:\Users\USER\AppData\Local\Google\Chrome\AutomationProfile"

def is_debug_chrome_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.05)
        return s.connect_ex(('localhost', DEBUG_PORT)) == 0


_driver = None


    
def attach_to_existing_chrome():
    options = Options()
    options.add_experimental_option("debuggerAddress", f"localhost:{DEBUG_PORT}")
    driver = webdriver.Chrome(options=options)
    return driver

def get_driver():
    global _driver

    if _driver is not None:
        try:
            _ = _driver.current_url
            return _driver
        except:
            _driver = None

    if is_debug_chrome_running():
        _driver = attach_to_existing_chrome()
    else:
        _driver = launch_new_chrome()

    return _driver

def launch_new_chrome():
    options = Options()
    options.add_experimental_option("detach", True)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"user-data-dir={USER_DATA_DIR}")
    options.add_argument(f"--remote-debugging-port={DEBUG_PORT}")
    #options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)
    driver.get("https://www.messenger.com")
    return driver

def find_messenger_tab(driver):
    for handle in driver.window_handles:
        driver.switch_to.window(handle)
        if "messenger.com" in driver.current_url:
            return True
    return False

nick_names = {
    "২ নম্বার খাঁটি মাল (•̀ᴗ•́)":"Hamim hossine",
    "Niggacetti":"Hasan Yamin Hisham",
    "vaiya":"Shahriyer Oishorjo",

}

def _get_current_name(driver, wait):
    return wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "h2"))
    ).text.lower().replace("conversation with", "").replace("conversation titled", "").strip()


def _resolve_nick(target_name, current_name):
    
    if any(target_name.lower() in v.lower() for v in nick_names.values()):
        for nickname, main_name in nick_names.items():
            if current_name.lower() in nickname.lower():
                return main_name
    return current_name


def find_inbox(driver, name):
    wait = WebDriverWait(driver, 60)


    name_head = _resolve_nick(name, _get_current_name(driver, wait))
    if name.lower() in name_head.lower():
        return True

    old_url = driver.current_url
    try:
        search = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "input[placeholder='Search Messenger']")
        ))
        search.click()
        search.clear()
        search.send_keys(name)
        wait = WebDriverWait(
            driver,
            5,
            poll_frequency=0.05,
            ignored_exceptions=(StaleElementReferenceException,)
        )


        contact = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH,
                "//li[@role='option' and not(contains(@aria-label, 'Search messages'))]")
            )
        )

        contact.click()

        WebDriverWait(driver, 60).until(lambda d: d.current_url != old_url)


        name_head = _resolve_nick(name, _get_current_name(driver, wait))
        if name.lower() not in name_head.lower():
            print(f'{name.lower()} and {name_head.lower()}')
            print('ABORT ABORT WRONG NAME OPENED, AHHHHHHHHHHHHHHHHHHHHHH')
            return False

        return True

    except Exception as e:
        print(f'ERROR {e}')
        return False


def open_inbox(name):
 
    if is_debug_chrome_running():
        driver = attach_to_existing_chrome()
    else:
        driver = launch_new_chrome()

    if not find_messenger_tab(driver):
        driver.get("https://www.messenger.com")

    if find_inbox(driver, name):
        print(f"Inbox for '{name}' is now open.")
        return driver
    else:
        print(f"Failed to open inbox for '{name}'.")
        return None

import queue

class MessengerBot:
    def __init__(self):
        self.driver = None
        self.current_inbox_msg = []
        self.seen_msg_ids = set()
        self.running = False
        self.thread = None
        self.injection_queue = queue.Queue() 
        self.prev_name = None
        self.current_inbox = None
        self.inbox_changed = False
    def start(self, name, interval=5):
        self.driver = self.setup_driver(name)
        if self.driver is None:
            print("[Monitor] Failed to start — driver is None")
            return  
        self.running = True
        self.thread = threading.Thread(target=self.run_loop, args=(name, interval), daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        if self.driver:
            self.driver.quit()

    def setup_driver(self, name):
        if is_debug_chrome_running():
            driver = attach_to_existing_chrome()
        else:
            driver = launch_new_chrome()

        if not find_messenger_tab(driver):
            driver.get("https://www.messenger.com")

        if find_inbox(driver, name):
            print(f"Inbox for '{name}' is now open.")
            self.prev_name = name
            return driver
        else:
            print(f"Failed to open inbox for '{name}'.")
            return None

    def run_loop(self, name, interval):
        try:

            elements = self.driver.find_elements(By.CSS_SELECTOR, '[aria-roledescription="message"][data-message-id][aria-label]')
            for e in elements:
                self.seen_msg_ids.add(e.get_attribute('data-message-id'))

            while self.running:
                self.check_messages(name)
                time.sleep(interval)
        except Exception as e:
            print(f"Monitor thread crashed: {e}")
            import traceback
            traceback.print_exc()

    def check_messages(self, name):
        elements = self.driver.find_elements(By.CSS_SELECTOR, '[aria-roledescription="message"][data-message-id][aria-label]')
        if not elements:
            return
        
        wait = WebDriverWait(self.driver, 5)
        current_name = _get_current_name(self.driver, wait)
        current_name = _resolve_nick(name,current_name)
        if self.prev_name not in current_name:
            self.current_inbox = current_name
            self.prev_name = current_name
            self.inbox_changed = True

        new_msgs = []
        for e in elements[-5:]:
            msg_id = e.get_attribute('data-message-id')
            if msg_id in self.seen_msg_ids:
                continue
            self.seen_msg_ids.add(msg_id)

            aria = e.get_attribute('aria-label').replace('\u202f', ' ').strip()
            print(aria)
            new_msgs.append(aria)
            self.current_inbox_msg.append(aria)

        if new_msgs:
            latest = new_msgs[-1]
            if 'logic' in latest.lower() and "Apurbo's AI companion" not in latest:
                if not self.inbox_changed:
                    self.injection_queue.put(f"{self.current_inbox_msg.copy()}") 
                else:
                    self.injection_queue.put(f"[INBOX CHANGED TO [{self.current_inbox}] reply to this inbox \n {self.current_inbox_msg.copy()}")
                    self.inbox_changed = False
                 # just the aria-label string
                print(self.current_inbox_msg)
                self.current_inbox_msg.clear()
                
    def get_injection(self):
        try:
            return self.injection_queue.get_nowait()
        except queue.Empty:
            return None
# Usage

if __name__ == "__main__":
    bot = MessengerBot()
    bot.start('Apurbo')
    
    # Keep main thread alive
    try:
        while True:
            msg = bot.get_injection()
            if msg:
                if not bot.inbox_changed:
                    print(f"INJECTED: {msg}")
                else:
                    print(f'[ALTER INBOX CHANGED, NEW INBOX {bot.current_inbox}]')
                    print(f"INJECTED: {msg}")
                    bot.inbox_changed = False
            time.sleep(1)
    except KeyboardInterrupt:
        bot.stop()
        print("Monitor stopped")


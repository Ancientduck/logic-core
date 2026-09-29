import socket
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import StaleElementReferenceException
import sys
import time
import pyperclip
import json

DEBUG_PORT = 9222
USER_DATA_DIR = r"C:\Users\USER\AppData\Local\Google\Chrome\AutomationProfile"

def is_debug_chrome_running():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.05)
        return s.connect_ex(('localhost', DEBUG_PORT)) == 0

def attach_to_existing_chrome():
    options = Options()
    options.add_experimental_option("debuggerAddress", f"localhost:{DEBUG_PORT}")
    driver = webdriver.Chrome(options=options)
    return driver

_driver = None

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


def send_message(name='', msg='', file_path=''):
    for nick, real in nick_names.items():
        if name.lower() == nick.lower():
            print(f'Nickname "{name}" resolved to {real}')
            name = real
            break
    if is_debug_chrome_running():
        driver = get_driver()
    else:
        driver = launch_new_chrome()

    if not find_messenger_tab(driver):
        driver.get("https://www.messenger.com")

    wait = WebDriverWait(driver, 60)
    name_head = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "h2"))
    ).text.lower().replace("conversation with", "").replace("conversation titled", "").strip()

    if any(name.lower() in v.lower() for v in nick_names.values()):
        for nickname, main_name in nick_names.items():
            if name_head.lower() in nickname.lower():
                name_head = main_name
                print(f'{name} has the nickname {nickname}')

    if name.lower() not in name_head.lower():
        old_url = driver.current_url
        try:
            search = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "input[placeholder='Search Messenger']")
            ))
            search.click()
            search.clear()
            search.send_keys(name)

            wait = WebDriverWait(driver, 5, poll_frequency=0.05, ignored_exceptions=(StaleElementReferenceException,))
            contact = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//li[@role='option' and not(contains(@aria-label, 'Search messages'))]")
                )
            )
            contact.click()

            WebDriverWait(driver, 60).until(lambda d: d.current_url != old_url)

            name_head = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h2"))
            ).text.lower().replace("conversation with", "").replace("conversation titled", "").strip()

            if any(name.lower() in v.lower() for v in nick_names.values()):
                for nickname, main_name in nick_names.items():
                    if name_head.lower() in nickname.lower():
                        name_head = main_name
                        print(f'{name} has the nickname {nickname}')

            if name.lower() not in name_head.lower():
                print(f'{name.lower()} and {name_head.lower()}')
                print('Wrong inbox opened,Msg not sent. ask for correct name')
                return
        except Exception as e:
            print(f'ERROR {e}')
            return

    textbox = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='textbox']"))
    )

    if file_path:
        from pathlib import Path
        files = [file_path] if isinstance(file_path, str) else file_path
        for f in files:
            file_box = wait.until(
                EC.presence_of_element_located((By.XPATH, "//input[@type='file']"))
            )
            file_box.send_keys(str(Path(f).resolve()))
            

    msg = msg.replace("\\\n", "\n")
    signature = "-LOGIC, Apurbo's AI companion"

    if signature in msg:
        full_msg = msg
    else:
        full_msg = f"{msg}\n{signature}"

    if file_path and not msg:
        full_msg = "files sent by -LOGIC, Apurbo's AI companion"

    actions = ActionChains(driver)
    actions.click(textbox)

    for char in full_msg:
        if char == '\n':
            actions.key_down(Keys.SHIFT).send_keys(Keys.ENTER).key_up(Keys.SHIFT)
        else:
            actions.send_keys(char)

    actions.send_keys(Keys.ENTER)
    actions.perform()
    print('MSG has been sent')



def send_messages(the_list):
    for name, msg, *rest in the_list:
        file_path = rest[0] if rest else ''
        print(f"{name}:{msg} | file: {file_path or 'none'}")

        send_message(name, msg, file_path)

if __name__ == '__main__':
    if len(sys.argv) > 2:
        name = sys.argv[1]
        msg = " ".join(sys.argv[2:])
        send_message(name, msg)
    elif len(sys.argv) > 1:
        try:
            the_list = json.loads(sys.argv[1])
            if not isinstance(the_list[0], list):
                the_list = [the_list]
            send_messages(the_list)
        except:
            pass

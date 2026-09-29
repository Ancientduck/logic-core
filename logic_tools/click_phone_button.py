import subprocess
import re
import sys
from xml.etree import ElementTree as ET

def adb_shell(command):
    result = subprocess.run(
        ['adb', '-s', '192.168.0.100:5555', 'shell'] + command.split(),
        capture_output=True, text=True, encoding='utf-8', errors='ignore'
    )
    return result.stdout

def find_and_click_all(target):
    adb_shell('uiautomator dump /sdcard/view.xml')
    xml_content = adb_shell('cat /sdcard/view.xml')

    root = ET.fromstring(xml_content)
    target_lower = target.lower()
    matches = []

    # Collect all matching nodes
    for node in root.iter():
        node_text = (node.get('text', '') or '').lower()
        if target_lower in node_text:
            bounds = node.get('bounds')
            if bounds:
                nums = list(map(int, re.findall(r'\d+', bounds)))
                if len(nums) == 4:
                    x1, y1, x2, y2 = nums
                    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                    matches.append((cx, cy))

    if not matches:
        print(f'Could not find "{target}" on screen')
        return False

    # Click all matches with a small delay between each
    for i, (cx, cy) in enumerate(matches):
        adb_shell(f'input tap {cx} {cy}')
        print(f'Clicked match #{i + 1} for "{target}" at {cx}, {cy}')
        # Small delay to let UI settle between taps
        import time
        time.sleep(0.3)

    print(f'Clicked {len(matches)} match(es) total')
    return True

if __name__ == '__main__':
    target = " ".join(sys.argv[1:])
    find_and_click_all(target)
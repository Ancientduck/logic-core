
"""
GUI Controller v9 — The Definitive Version.
- Implements Strict Title Alignment Filter (fixes hidden WPF canvas hijack).
- Restores the global public 'def control(action, *args)' entry point.
- Drop-in replacement with 'Control' class & 'gui_connector(args)' legacy support.
- Blazing-fast cached metadata traversal.
"""

import time
import ctypes
from ctypes import wintypes
import threading
import re
import sys
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, Any
from difflib import SequenceMatcher

from pywinauto import Application

# ─── Constants ────────────────────────────────────────────────────────────────

SW_RESTORE = 9
TOPMOST = -1
NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040

IGNORE_TYPES = {
    "titlebar", "thumb", "gripper", "scrollbar", "separator", 
    "window", "header", "headeritem", "visual"
}

ALL_USEFUL_TYPES = {
    "button", "checkbox", "radiobutton", "tabitem", "listitem",
    "treeitem", "menuitem", "hyperlink", "edit", "combobox",
    "slider", "spinner", "splitbutton", "togglebutton",
    "datagrid", "dataitem", "document", "calendar", "menu", "menubar",
    "text", "statictext", "statusbar", "tooltip", "progressbar",
    "group", "pane"
}


# ─── Data Structures ─────────────────────────────────────────────────────────

class MatchQuality(Enum):
    EXACT = auto()
    EXACT_CASE_INSENSITIVE = auto()
    STARTS_WITH = auto()
    CONTAINS = auto()
    AUTO_ID_MATCH = auto()
    FUZZY = auto()
    NONE = auto()


@dataclass
class ElementInfo:
    wrapper: Any
    name: str
    control_type: str
    automation_id: str
    class_name: str
    rect: Optional[Any]
    runtime_id: Optional[tuple]
    is_enabled: bool
    value: str
    index: int
    key: str
    display: str

    @property
    def midpoint(self) -> Optional[Tuple[int, int]]:
        if self.rect is None:
            return None
        return (
            (self.rect.left + self.rect.right) // 2,
            (self.rect.top + self.rect.bottom) // 2,
        )


# ─── Advanced HWND Resolution Engine ────────────────────────────────────────

def resolve_main_gui_hwnd(title_query: str, log_callback) -> Optional[int]:
    """Uses native Win32 window-process mapping with strict title scoring to find the correct HWND."""
    matched_pid = None
    user32 = ctypes.windll.user32

    # Step 1: Scan for ANY window matching the target title to acquire the Process ID
    def enum_pid_callback(hwnd, lParam):
        nonlocal matched_pid
        if matched_pid is not None:
            return True
        
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value
            if re.search(f".*{re.escape(title_query)}.*", title, re.IGNORECASE) or re.search(f".*{title_query}.*", title, re.IGNORECASE):
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                matched_pid = pid.value
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_pid_callback), 0)

    if matched_pid is None:
        return None

    log_callback(f"Target Process ID discovered: {matched_pid}")

    # Step 2: Query all windows belonging to that PID and score them
    candidates = []

    def enum_windows_callback(hwnd, lParam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == matched_pid:
            class_buff = ctypes.create_unicode_buffer(512)
            user32.GetClassNameW(hwnd, class_buff, 512)
            class_name = class_buff.value
            
            title_len = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if title_len > 0:
                title_buff = ctypes.create_unicode_buffer(title_len + 1)
                user32.GetWindowTextW(hwnd, title_buff, title_len + 1)
                title = title_buff.value
            
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            area = width * height
            
            visible = bool(user32.IsWindowVisible(hwnd))
            
            # --- Scoring Algorithm (Prioritizes exact Title Match and penalizes Hidden canvasses) ---
            score = area
            
            # 1. Enormous bonus if the title strictly contains our search term
            title_match = False
            if title:
                if re.search(f".*{re.escape(title_query)}.*", title, re.IGNORECASE) or re.search(f".*{title_query}.*", title, re.IGNORECASE):
                    title_match = True
            
            if title_match:
                score += 20000000  # Massive priority bonus for direct title match
            
            # 2. Strict Penalty for WPF composite backgrounds & helper elements
            title_lower = title.lower()
            if "hidden window" in title_lower or "notifywindow" in title_lower or "broadcast" in title_lower:
                score -= 10000000
                
            if visible:
                score += 1000000
            if "hwndwrapper" in class_name.lower():
                score += 500000

            candidates.append((hwnd, title, class_name, width, height, visible, score))
        return True

    user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)

    if not candidates:
        return None

    # Sort candidates by score descending
    candidates.sort(key=lambda x: x[6], reverse=True)
    
    for cand in candidates:
        log_callback(f"Evaluated HWND {cand[0]} | Title: '{cand[1]}' | Class: '{cand[2]}' | Size: {cand[3]}x{cand[4]} | Visible: {cand[5]} | Score: {cand[6]}")

    best_hwnd = candidates[0][0]
    log_callback(f"Successfully selected active GUI handle: HWND {best_hwnd} ({candidates[0][3]}x{candidates[0][4]})")
    return best_hwnd


# ─── Robust Control Core ──────────────────────────────────────────────────────

class Control:
    def __init__(self, debug: bool = True):
        self.window = None
        self.elements: Dict[str, ElementInfo] = {}
        self.element_list: List[str] = []
        self._backend = None
        self._lock = threading.Lock()
        self.debug = debug
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

    def log(self, msg: str):
        if self.debug:
            print(f"[GUI] {msg}")

    # ── Connection Engine ─────────────────────────────────────────────────

    def connect(self, title: str, timeout: float = 10.0) -> List[str]:
        with self._lock:
            self.log(f"Connecting to: '{title}'")
            self.window = None
            self._backend = None

            target_hwnd = resolve_main_gui_hwnd(title, self.log)
            if not target_hwnd:
                raise RuntimeError(f"Could not find any active window process matching '{title}'")

            # Bind UIA directly to the selected HWND
            try:
                self.log(f"Binding UIA backend directly to GUI HWND: {target_hwnd}")
                app = Application(backend="uia").connect(handle=target_hwnd, timeout=timeout)
                self.window = app.window(handle=target_hwnd)
                self._backend = "uia"
                self.log("Direct UIA connection successful!")
            except Exception as e:
                self.log(f"UIA direct bind failed: {e}. Trying Win32 fallback...")
                try:
                    app = Application(backend="win32").connect(handle=target_hwnd, timeout=5.0)
                    self.window = app.window(handle=target_hwnd)
                    self._backend = "win32"
                except Exception as fallback_err:
                    raise RuntimeError(f"Failed to connect to window: {fallback_err}")

            self.bring_to_front()
            time.sleep(0.3)
            return self.deep_scan()

    def bring_to_front(self):
        try:
            hwnd = self.window.handle
            if not hwnd:
                return

            self._user32.ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.04)

            fg = self._user32.GetForegroundWindow()
            fg_thread = self._user32.GetWindowThreadProcessId(fg, None)
            target_thread = self._user32.GetWindowThreadProcessId(hwnd, None)
            current_thread = self._kernel32.GetCurrentThreadId()

            attached_fg = False
            attached_cur = False

            try:
                if fg_thread != target_thread and fg_thread != 0:
                    attached_fg = bool(self._user32.AttachThreadInput(fg_thread, target_thread, True))
                if current_thread != target_thread:
                    attached_cur = bool(self._user32.AttachThreadInput(current_thread, target_thread, True))

                self._user32.BringWindowToTop(hwnd)
                self._user32.SetForegroundWindow(hwnd)
                
                self._user32.SetWindowPos(hwnd, TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                time.sleep(0.01)
                self._user32.SetWindowPos(hwnd, NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            finally:
                if attached_fg:
                    self._user32.AttachThreadInput(fg_thread, target_thread, False)
                if attached_cur:
                    self._user32.AttachThreadInput(current_thread, target_thread, False)
            self.log("Brought window to foreground")
        except Exception as e:
            self.log(f"bring_to_front error: {e}")

    # ── High-Speed Traversal Engine ───────────────────────────────────────

    def deep_scan(self, max_depth=10) -> List[str]:
        self.elements.clear()
        self.element_list.clear()

        if self.window is None:
            return []

        seen_rids = set()
        seen_positions = set()
        results: List[ElementInfo] = []

        try:
            descendants = self.window.descendants()
        except Exception as e:
            self.log(f"descendants() failed: {e}")
            return []

        for index, el in enumerate(descendants):
            try:
                info = el.element_info
                
                rect = info.rectangle
                width = rect.width() if rect else 0
                height = rect.height() if rect else 0

                ctrl = (info.control_type or "").lower().strip()
                if ctrl in IGNORE_TYPES:
                    continue

                name = (info.name or "").strip()
                auto_id = (getattr(info, "automation_id", "") or "").strip()

                if ctrl not in ALL_USEFUL_TYPES and not name and not auto_id:
                    continue

                if rect and (width <= 1 and height <= 1) and not name and not auto_id:
                    continue

                rid = None
                try:
                    rid = tuple(info.runtime_id) if info.runtime_id else None
                except Exception:
                    pass
                if rid is None:
                    try:
                        rid = ("handle", el.handle)
                    except Exception:
                        pass

                if rid is not None:
                    if rid in seen_rids:
                        continue
                    seen_rids.add(rid)

                pos_key = (name, ctrl, rect.left if rect else 0, rect.top if rect else 0)
                if pos_key in seen_positions:
                    continue
                seen_positions.add(pos_key)

                # Read value states
                value = ""
                try:
                    if ctrl == "edit":
                        value = el.get_value() if hasattr(el, "get_value") else el.window_text()
                    elif ctrl == "combobox":
                        value = el.selected_text()
                    elif ctrl in ("checkbox", "togglebutton", "radiobutton"):
                        val = el.get_toggle_state() if hasattr(el, "get_toggle_state") else None
                        if val is not None:
                            value = {0: "unchecked", 1: "checked", 2: "indeterminate"}.get(val, str(val))
                except Exception:
                    pass

                key = f"{ctrl}|{auto_id if auto_id else name}|{index}"

                parts = []
                if name:
                    parts.append(name)
                if value and value != name:
                    parts.append(f"= '{value}'")
                parts.append(f"[{ctrl}]")
                if not info.enabled:
                    parts.append("(disabled)")
                display = " ".join(parts)

                results.append(ElementInfo(
                    wrapper=el, name=name, control_type=ctrl, automation_id=auto_id,
                    class_name=getattr(info, "class_name", "") or "", rect=rect,
                    runtime_id=rid, is_enabled=info.enabled, value=value, index=0,
                    key=key, display=display
                ))
            except Exception as item_err:
                pass

        # Sort top-to-bottom, left-to-right
        results.sort(key=lambda e: (e.rect.top if e.rect else 9999, e.rect.left if e.rect else 9999))

        for i, ei in enumerate(results):
            ei.index = i
            self.elements[ei.key] = ei

        self.element_list = [f"[{ei.index}] {ei.display}" for ei in results]
        self.log(f"Scan found {len(self.element_list)} interactive elements")
        return self.element_list

    def scan(self) -> List[str]:
        return self.deep_scan()

    def get_buttons(self) -> List[str]:
        return self.element_list

    # ── Advanced Ranked Pattern Matching ──────────────────────────────────

    def _match_score(self, query: str, ei: ElementInfo) -> Tuple[MatchQuality, float]:
        q = query.lower().strip()
        try:
            if q.isdigit() or (q.startswith("[") and q.endswith("]")):
                idx = int(q.replace("[", "").replace("]", ""))
                if ei.index == idx:
                    return (MatchQuality.EXACT, 1.0)
        except ValueError:
            pass

        name_lower = ei.name.lower()
        auto_id_lower = ei.automation_id.lower()

        if q == name_lower:
            return (MatchQuality.EXACT_CASE_INSENSITIVE, 1.0)
        if q == auto_id_lower:
            return (MatchQuality.AUTO_ID_MATCH, 1.0)
        if name_lower.startswith(q):
            return (MatchQuality.STARTS_WITH, len(q) / max(len(name_lower), 1))
        if q in name_lower:
            return (MatchQuality.CONTAINS, len(q) / max(len(name_lower), 1))
        if q in auto_id_lower:
            return (MatchQuality.CONTAINS, len(q) / max(len(auto_id_lower), 1))

        ratio = SequenceMatcher(None, q, name_lower).ratio()
        if ratio > 0.45:
            return (MatchQuality.FUZZY, ratio)
        return (MatchQuality.NONE, 0.0)

    def _find_element(self, query: str, rescan_on_miss: bool = True) -> Tuple[Optional[ElementInfo], MatchQuality]:
        best_ei = None
        best_quality = MatchQuality.NONE
        best_score = 0.0

        for ei in self.elements.values():
            quality, score = self._match_score(query, ei)
            if quality == MatchQuality.NONE:
                continue
            if (quality.value < best_quality.value or
                (quality == best_quality and score > best_score)):
                best_ei = ei
                best_quality = quality
                best_score = score
            if quality == MatchQuality.EXACT:
                break

        if best_ei is None and rescan_on_miss:
            self.log(f"Element '{query}' not found. Rescanning UI tree...")
            self.deep_scan()
            return self._find_element(query, rescan_on_miss=False)
        return best_ei, best_quality

    # ── High-Reliability UI Actions ───────────────────────────────────────

    def _raw_click(self, x: int, y: int, button: str = "left"):
        self._user32.SetCursorPos(x, y)
        time.sleep(0.02)
        if button == "right":
            down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        elif button == "middle":
            down, up = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
        else:
            down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

        self._user32.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.01)
        self._user32.mouse_event(up, 0, 0, 0, 0)

    def click(self, name: str, button="left") -> Tuple[bool, List[str]]:
        with self._lock:
            if self.window is None:
                return False, self.element_list

            self.bring_to_front()
            ei, quality = self._find_element(name)
            if ei is None:
                return False, self.element_list

            self.log(f"Clicking: {ei.display} ({quality.name})")
            success = False

            # Pattern 1: Pywinauto Native wrapper action
            try:
                if button == "right":
                    ei.wrapper.right_click_input()
                else:
                    ei.wrapper.click_input()
                success = True
            except Exception as e:
                self.log(f"Pywinauto wrapper click failed: {e}. Trying direct Invocation...")

            # Pattern 2: Direct UIA Invoke Call
            if not success:
                try:
                    if hasattr(ei.wrapper, "iface_invoke") and ei.wrapper.iface_invoke:
                        ei.wrapper.iface_invoke.Invoke()
                        success = True
                except Exception:
                    pass

            # Pattern 3: Absolute Win32 Coordinate Click
            if not success:
                mid = ei.midpoint
                if mid:
                    try:
                        self._raw_click(mid[0], mid[1], button)
                        success = True
                    except Exception as coord_err:
                        self.log(f"Absolute coordinate click failed: {coord_err}")

            if success:
                time.sleep(0.25)
                return True, self.deep_scan()
            return False, self.element_list

    def double_click(self, query: str) -> Tuple[bool, List[str]]:
        with self._lock:
            if self.window is None:
                return False, self.element_list
            self.bring_to_front()
            ei, quality = self._find_element(query)
            if ei is None:
                return False, self.element_list
            try:
                ei.wrapper.double_click_input()
                time.sleep(0.2)
                return True, self.deep_scan()
            except Exception:
                mid = ei.midpoint
                if mid:
                    self._raw_click(mid[0], mid[1], "left")
                    time.sleep(0.05)
                    self._raw_click(mid[0], mid[1], "left")
                    time.sleep(0.25)
                    return True, self.deep_scan()
            return False, self.element_list

    def type_text(self, query: str, text: str, clear=True) -> Tuple[bool, List[str]]:
        with self._lock:
            if self.window is None:
                return False, self.element_list
            self.bring_to_front()
            ei, quality = self._find_element(query)
            if ei is None:
                return False, self.element_list
            try:
                if clear:
                    try:
                        ei.wrapper.set_edit_text(text)
                        time.sleep(0.1)
                        return True, self.deep_scan()
                    except Exception:
                        pass
                self.click(query)
                time.sleep(0.05)
                if clear:
                    ei.wrapper.type_keys("^a", with_spaces=True)
                    time.sleep(0.02)
                ei.wrapper.type_keys(text, with_spaces=True, with_newlines=True)
                time.sleep(0.15)
                return True, self.deep_scan()
            except Exception as e:
                self.log(f"Typing text failed: {e}")
                return False, self.element_list

    def get_value(self, query: str) -> Tuple[bool, str]:
        with self._lock:
            if self.window is None:
                return False, "Not connected"
            ei, quality = self._find_element(query)
            if ei is None:
                return False, "Element not found"
            ei_fresh = self.elements.get(ei.key, ei)
            return True, ei_fresh.value

    def toggle(self, query: str) -> Tuple[bool, List[str]]:
        with self._lock:
            if self.window is None:
                return False, self.element_list
            self.bring_to_front()
            ei, quality = self._find_element(query)
            if ei is None:
                return False, self.element_list
            try:
                if hasattr(ei.wrapper, "toggle"):
                    ei.wrapper.toggle()
                else:
                    ei.wrapper.click_input()
                time.sleep(0.2)
                return True, self.deep_scan()
            except Exception:
                return False, self.element_list

    def select(self, query: str, item: str) -> Tuple[bool, List[str]]:
        with self._lock:
            if self.window is None:
                return False, self.element_list
            self.bring_to_front()
            ei, quality = self._find_element(query)
            if ei is None:
                return False, self.element_list
            try:
                ei.wrapper.select(item)
                time.sleep(0.2)
                return True, self.deep_scan()
            except Exception:
                return False, self.element_list

    def expand(self, query: str) -> Tuple[bool, List[str]]:
        with self._lock:
            if self.window is None:
                return False, self.element_list
            self.bring_to_front()
            ei, quality = self._find_element(query)
            if ei is None:
                return False, self.element_list
            try:
                ei.wrapper.expand()
                time.sleep(0.2)
                return True, self.deep_scan()
            except Exception:
                return False, self.element_list

    def collapse(self, query: str) -> Tuple[bool, List[str]]:
        with self._lock:
            if self.window is None:
                return False, self.element_list
            self.bring_to_front()
            ei, quality = self._find_element(query)
            if ei is None:
                return False, self.element_list
            try:
                ei.wrapper.collapse()
                time.sleep(0.2)
                return True, self.deep_scan()
            except Exception:
                return False, self.element_list

    def scroll_to(self, query: str) -> Tuple[bool, List[str]]:
        with self._lock:
            if self.window is None:
                return False, self.element_list
            ei, quality = self._find_element(query)
            if ei is None:
                return False, self.element_list
            try:
                if hasattr(ei.wrapper, "iface_scroll_item") and ei.wrapper.iface_scroll_item:
                    ei.wrapper.iface_scroll_item.ScrollIntoView()
                    time.sleep(0.25)
                    return True, self.deep_scan()
            except Exception:
                pass
            try:
                ei.wrapper.set_focus()
                time.sleep(0.15)
                return True, self.deep_scan()
            except Exception:
                return False, self.element_list

    def send_keys(self, keys: str) -> Tuple[bool, List[str]]:
        with self._lock:
            if self.window is None:
                return False, self.element_list
            self.bring_to_front()
            try:
                self.window.type_keys(keys, with_spaces=True, with_newlines=True)
                time.sleep(0.2)
                return True, self.deep_scan()
            except Exception:
                return False, self.element_list

    def screenshot(self, path: Optional[str] = None) -> Tuple[bool, str]:
        with self._lock:
            if self.window is None:
                return False, "Not connected"
            try:
                img = self.window.capture_as_image()
                save_path = path if path else f"screenshot_{int(time.time())}.png"
                img.save(save_path)
                return True, save_path
            except Exception as e:
                return False, str(e)

    def disconnect(self):
        with self._lock:
            self.window = None
            self._backend = None
            self.elements.clear()
            self.element_list.clear()
            self.log("Disconnected")


# ─── Public Function & Legacies ───────────────────────────────────────────────

_control = Control(debug=True)
_connected = False


def control(action: str, *args) -> str:
    """
    Main Global public execution API.
    
    Usage examples:
      control("connect", "Windows Memory Cleaner")
      control("click", "Clean")
      control("type", "EditBoxTarget", "Clean Text")
      control("screenshot", "image.png")
      control("disconnect")
    """
    global _control, _connected
    action = action.lower().strip()

    if action == "connect":
        try:
            buttons = _control.connect(args[0])
            _connected = True
            return f"Connected. Found {len(buttons)} visible elements.\n" + "\n".join(buttons[:50])
        except Exception as e:
            return f"Connect failed: {e}"

    elif action == "click":
        if not _connected:
            return "Not connected"
        name = args[0]
        btn = args[1] if len(args) > 1 else "left"
        ok, new = _control.click(name, button=btn)
        if ok:
            return f"Clicked '{name}'. Now {len(new)} elements."
        return f"Failed to click '{name}'. Available:\n" + "\n".join(new[:25])

    elif action in ("scan", "deep_scan"):
        if not _connected:
            return "Not connected"
        btns = _control.deep_scan()
        return f"Rescan: {len(btns)} elements\n" + "\n".join(btns[:50])

    elif action in ("type", "text"):
        if not _connected:
            return "Not connected"
        target = args[0]
        text = args[1]
        ok, new = _control.type_text(target, text)
        if ok:
            return f"Typed text into '{target}'. Now {len(new)} elements."
        return f"Failed to type into '{target}'"

    elif action in ("value", "read", "get"):
        if not _connected:
            return "Not connected"
        target = args[0]
        ok, value = _control.get_value(target)
        if ok:
            return f"Value of '{target}': '{value}'"
        return f"Failed to read value from '{target}'"

    elif action == "toggle":
        if not _connected:
            return "Not connected"
        target = args[0]
        ok, new = _control.toggle(target)
        if ok:
            return f"Toggled '{target}'. Now {len(new)} elements."
        return f"Failed to toggle '{target}'"

    elif action == "select":
        if not _connected:
            return "Not connected"
        target = args[0]
        item = args[1]
        ok, new = _control.select(target, item)
        if ok:
            return f"Selected '{item}' in '{target}'."
        return f"Failed to select item in '{target}'"

    elif action == "expand":
        if not _connected:
            return "Not connected"
        target = args[0]
        ok, new = _control.expand(target)
        if ok:
            return f"Expanded '{target}'."
        return f"Failed to expand '{target}'"

    elif action == "collapse":
        if not _connected:
            return "Not connected"
        target = args[0]
        ok, new = _control.collapse(target)
        if ok:
            return f"Collapsed '{target}'."
        return f"Failed to collapse '{target}'"

    elif action == "scroll":
        if not _connected:
            return "Not connected"
        target = args[0]
        ok, new = _control.scroll_to(target)
        if ok:
            return f"Scrolled to '{target}'."
        return f"Failed to scroll to '{target}'"

    elif action == "keys":
        if not _connected:
            return "Not connected"
        keys = args[0]
        ok, new = _control.send_keys(keys)
        if ok:
            return f"Sent key codes."
        return f"Failed to send key commands"

    elif action == "screenshot":
        if not _connected:
            return "Not connected"
        path = args[0] if args else None
        ok, save_path = _control.screenshot(path)
        if ok:
            return f"Screenshot captured: {save_path}"
        return f"Screenshot capture failed: {save_path}"

    elif action == "list":
        return "\n".join(_control.get_buttons())

    elif action == "disconnect":
        _control.disconnect()
        _connected = False
        return "Disconnected successfully."

    return f"Unknown action: {action}"


def gui_connector(args) -> str:
    """Legacy route converter."""
    if not args:
        return "Error: No arguments"
    action = args[0]
    return control(action, *args[1:])


# ─── Console UI Shell ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    WINDOW = sys.argv[1] if len(sys.argv) > 1 else "Windows Memory Cleaner"

    HELP_MENU = """
Usage commands:
  click <target>              - Left-click UI element (matches name, auto_id, index)
  right <target>              - Right-click UI element
  dclick <target>             - Double-click UI element
  type <target> <text>        - Set/type text in input boxes
  value <target>              - Get active value
  toggle <target>             - Check/uncheck boxes
  select <target> <item>      - Pick dropdown item
  expand/collapse <target>    - Open/close tree/combos
  scroll <target>             - Scroll control into view
  keys <text>                 - Send active keystrokes (e.g. ^a^c)
  scan                        - Refresh current UI layout tree
  list                        - Print active cached layout index
  screenshot [name.png]       - Save window screen capture
  help                        - Show commands list
  q                           - Quit shell
"""

    print("=" * 75)
    print("  Perfect GUI Controller v9 (Title-Aligned Multi-Window Engine)")
    print("=" * 75)
    print(control("connect", WINDOW))
    print(HELP_MENU)
    print("=" * 75)

    while True:
        try:
            line = input("\n❯ ").strip()
            if not line:
                continue

            parts = line.split(maxsplit=1)
            cmd = parts[0].lower()
            rest = parts[1] if len(parts) > 1 else ""

            if cmd == "q":
                control("disconnect")
                break
            elif cmd == "help":
                print(HELP_MENU)
            elif cmd == "scan":
                print(control("scan"))
            elif cmd == "list":
                print(control("list"))
            elif cmd in ("right", "rclick"):
                print(control("click", rest, "right"))
            elif cmd == "dclick":
                ok, new = _control.double_click(rest)
                if ok:
                    print(f"Double-clicked '{rest}'")
                else:
                    print(f"Failed to double-click '{rest}'")
            elif cmd == "type":
                sub_parts = rest.split(maxsplit=1)
                if len(sub_parts) < 2:
                    print("Usage: type <element> <text>")
                else:
                    print(control("type", sub_parts[0], sub_parts[1]))
            elif cmd == "value":
                print(control("value", rest))
            elif cmd == "toggle":
                print(control("toggle", rest))
            elif cmd == "select":
                sub_parts = rest.split(maxsplit=1)
                if len(sub_parts) < 2:
                    print("Usage: select <element> <item>")
                else:
                    print(control("select", sub_parts[0], sub_parts[1]))
            elif cmd == "expand":
                print(control("expand", rest))
            elif cmd == "collapse":
                print(control("collapse", rest))
            elif cmd == "scroll":
                print(control("scroll", rest))
            elif cmd == "keys":
                print(control("keys", rest))
            elif cmd == "screenshot":
                print(control("screenshot", rest if rest else None))
            else:
                print(control("click", line))

        except KeyboardInterrupt:
            print("\nExiting Shell.")
            control("disconnect")
            break
        except EOFError:
            break
        except Exception as e:
            print(f"Shell Error: {e}")
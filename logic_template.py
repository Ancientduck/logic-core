from pathlib import Path
from PIL import ImageGrab
from user_voice import get_voice
from datetime import datetime
from logic_memory_manager import memorymanager
from search_net import ask_search_net
from logic_prompt import build_system_prompt
from messenger_chat_monitor import MessengerBot
from rich.console import Console
from rich.text import Text
from rich.style import Style
from openai import OpenAI
from activity_monitor import monitor
from search_net_prototype import get_complete_web_list
from gui_controller import Control
from gemini_image_analysis import ask_image


from tool_router import guess_tool
import asyncio
import logic_voice
import importlib
import json
import groq
import openai
import sounddevice as sd
import keyboard
import logic_voice
import subprocess
import time
import os
from dotenv import load_dotenv
load_dotenv()
import re
import sys
import httpx
import base64
import msvcrt
import tempfile
import os
import queue
import threading
import time
from io import BytesIO
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style as PtStyle


sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
os.environ['PYTHONIOENCODING'] = 'utf-8'



speak_stream = logic_voice.speak_stream
speak_async = logic_voice.speak_async
speak_queue = logic_voice.speak_queue
stop_voice = logic_voice.stop_voice


API_KEY = os.getenv("API_KEY", "")
BASE_URL = "https://api.inceptionlabs.ai/v1"

MODEL = "mercury-2.5"

MODEL_CODE = 'gpt-4o-mini'
#* cline has gemma 4 31B,deepseek v4 flash, and nemo 3 ultra 550B a55b for free
#* Deepseek-v4-flash is actually a good model.
#* IMPORT, THINKING SLOWS DOWN RESPONSE. its on by default
print(f'model in use {MODEL}')

GROQ_API_KEY = os.getenv("API_KEY", "")
MODEL_NAME_GROQ = "qwen/qwen3.8-27b"
#* npx omniroute

the_console = Console()

# ===== Omniroute bootstrap =====
# import socket
# import subprocess
# import sys

# OMNROUTE_URL = "http://localhost:20128/v1"
# OMNROUTE_HOST = "localhost"
# OMNROUTE_PORT = 20128
# OMNROUTE_START_TIMEOUT = 30
# OMNROUTE_POLL_INTERVAL = 1.5

# omniroute_proc = None

# def _is_omniroute_running():
#     """Check if omniroute is already listening on the port."""
#     try:
#         with socket.create_connection((OMNROUTE_HOST, OMNROUTE_PORT), timeout=1):
#             return True
#     except (socket.timeout, ConnectionRefusedError, OSError):
#         return False

# def _wait_for_omniroute():
#     """Poll until the base URL is reachable, or timeout."""
#     import time
#     elapsed = 0
#     while elapsed < OMNROUTE_START_TIMEOUT:
#         if _is_omniroute_running():
#             return True
#         time.sleep(OMNROUTE_POLL_INTERVAL)
#         elapsed += OMNROUTE_POLL_INTERVAL
#     return False

# def ensure_omniroute():
#     """Ensure omniroute is running before proceeding."""
#     global omniroute_proc

#     if _is_omniroute_running():
#         print("[Omniroute] Already active — skipping startup.")
#         return

#     print("[Omniroute] Not detected. Starting omniroute...")
#     try:
#         omniroute_proc = subprocess.Popen(
#             "omniroute",
#             shell=True,
#             stdout=subprocess.DEVNULL,
#             stderr=subprocess.DEVNULL,
#             creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
#     )
    
#     except FileNotFoundError:
#         print("[Omniroute] ERROR: 'omniroute' command not found. Is it installed?")
#         sys.exit(1)

#     if _wait_for_omniroute():
#         print("[Omniroute] Ready.")
#     else:
#         print(f"[Omniroute] ERROR: Timed out after {OMNROUTE_START_TIMEOUT}s. Exiting.")
#         if omniroute_proc:
#             omniroute_proc.terminate()
#         sys.exit(1)

# def cleanup_omniroute():
#     """Kill the omniroute subprocess if we started it."""
#     global omniroute_proc
#     if omniroute_proc is not None and omniroute_proc.poll() is None:
#         print("[Omniroute] Shutting down...")
#         omniroute_proc.terminate()
#         omniroute_proc = None

# # Call the bootstrap right before client init
# ensure_omniroute()
# import atexit
# atexit.register(cleanup_omniroute)
# # ===== End Omniroute bootstrap =====

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
    default_headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    },
)


Code_MODEL = ''
class OpenAIChunkWrapper:
    def __init__(self, text):
        self.text = text
class OpenAIChatSession:
    def __init__(self, client, model, system_instruction, history=None, temperature=1.0, top_p=0.9):
        self.client = client
        self.model = model
        self.system_instruction = system_instruction
        self.history = history or []
        self.temperature = temperature
        self.top_p = top_p
        
    def get_history(self):
        history_text = ""
        for msg in self.history:
            role = msg.get("role")
            content = msg.get("content")
            if isinstance(content, list):
                text_parts = [part.get("text", "") for part in content if part.get("type") == "text"]
                content_str = " ".join(text_parts)
            else:
                content_str = str(content)
            history_text += f"{role}: {content_str}\n"
        return history_text

    def send_message_stream(self, prompt):
        user_content = []
        if isinstance(prompt, list):
            for part in prompt:
                if isinstance(part, str):
                    user_content.append({"type": "text", "text": part})
                elif hasattr(part, "save"):  # Converts screenshot PIL images automatically
                    buffered = BytesIO()
                    part.save(buffered, format="JPEG")
                    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_str}"
                        }
                    })
        else:
            user_content = prompt

        self.history.append({"role": "user", "content": user_content})

        messages = [{"role": "system", "content": self.system_instruction}]
        messages.extend(self.history)

        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            top_p=self.top_p,
            stream=True,
            #reasoning_effort="none", #*here
            # extra_body={
            #     "reasoning_effort": "none"
            # },
            
        )

        full_reply = ""
        for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content is not None:
                    full_reply += content
                    yield OpenAIChunkWrapper(content)

        self.history.append({"role": "assistant", "content": full_reply})


    def clean_history(self):
        cleaned = []
        for msg in self.history:
            role = msg.get('role')
            content = msg.get('content')
            if isinstance(content, list):
                text_parts = [part.get('text', '') for part in content if part.get('type') == 'text']
                content_str = ' '.join(text_parts)
            else:
                content_str = str(content)
            if role == 'assistant' and '```' in content_str:
                continue
            if role == 'user' and 'SCRIPT_RESULT:' in content_str:
                continue
            cleaned.append(msg)

        self.history = cleaned

class Base_AI():
    def __init__(self):

        self.chat = OpenAIChatSession(
            client=client,
            model=MODEL,
            system_instruction=build_system_prompt(),
            temperature=1.0,
            top_p=0.9,
        
        )
        self.logic_tools = 'logic_tools'
        self.debug_prompt = False
        self.code_block = ''
        self.summary_history = []
        self.gen_code_terminator = False
        self.script_results = None
        self.activity_report = "[MONITOR] No activity data yet"
        self.monitor_thread = threading.Thread(
            target=self.activity_monitor_worker,
            daemon=True
        )
        self.monitor_thread.start()
        
    def clean_history(self):
        self.chat.clean_history()
        
    def reset_chat(self):
            self.clean_history()
            history = self.chat.get_history()  # cleaner, no tool call clutter
            print(f'new_history= \n {history}')

            summary = groq_caller.call_groq(f'summarize this conversation briefly. ignore anything in relevant memory:\n{history}')
            #print(f'\n**{summary}**\n')
            memorymanager.reset_sent()
            self.chat = OpenAIChatSession(
                client=client,
                model=MODEL,
                system_instruction=build_system_prompt(),
                history=[
                    {"role": "user", "content": "[session context]"},
                    {"role": "assistant", "content": f"Summary of prior conversation:\n{summary}"}
                ],
                temperature=1.0,
                top_p=0.9
            )
    
    def session_saver(self):
        self.clean_history()
        history = self.chat.get_history()
        groq_ses.call_groq(history)
        self.turn_count = 0
        self.summary_history = []

    def activity_monitor_worker(self):
        for (
                    last_title,
                    last_proc,
                    last_path,
                    last_url,
                    elapsed,
                    total,
                    new_title,
                    new_proc,
                    new_path,
                    new_url
                ) in monitor.monitor():

            time_now = datetime.datetime.now().strftime("%I:%M %p")

            self.activity_report = f"[MONITOR] {time_now} | was: {last_title} ({last_proc}) {last_path} {last_url}  | +{monitor.format_time(elapsed)} (total {monitor.format_time(total)}) | now: {new_title} ({new_proc}) {new_path}  {new_url}"
    
    def call_logic(self, prompt='something'):
        is_code = False
        ai_reply = ''
        summary_prompt = ''
        max_retries = 3
        delay = 2
        current_sentence = '' 
        is_text_prompt = isinstance(prompt, str)
        relevant_memory = ''
        final_prompt = ''

        # Before streaming starts
        activity_report = self.activity_report
        if not str(prompt).strip().lower().startswith("system:"):
            self.summary_history.append(f"User: {prompt}")


        if is_text_prompt and not prompt.startswith('/'):
            if is_text_prompt and not prompt.startswith('SCRIPT_RESULT'):
                #print(f'sending msg:{prompt} /// {ai_reply}')
                relevant_memory = memorymanager.search(prompt) #* mem off

                pass

        if relevant_memory:
            final_prompt = f'relevant_memory:[{relevant_memory}]' 

        if activity_report:
            final_prompt += f'\n{activity_report}'

        possible_tool = guess_tool(f'{final_prompt}\n{prompt}')

        if possible_tool:
            final_prompt += f'\npossible_tool:[{possible_tool}]'

        final_prompt += f'\n{prompt}'

        if self.debug_prompt:
            print(final_prompt)

        for attempt in range(max_retries):
            try:
                if isinstance(prompt, list):
                    response = self.chat.send_message_stream(prompt)
                else:
                    response = self.chat.send_message_stream(final_prompt)
                
                forbidden_words_to_speak = ["run_script:", "check_screen:", "save:", 'keep_in_memory:']
                self.turn_count = getattr(self, 'turn_count', 0) + 1

                if self.turn_count >= 15:  #* handling auto session summary
                    self.session_saver()

                #print(f"**{self.turn_count}**")
                for chunk in response:
                    if chunk.text:
                        code_started = '```' in ai_reply
                        ai_reply += chunk.text
                        
                        if '```' in chunk.text and not code_started:
                            pre_code = chunk.text.split('```')[0]
                            current_sentence += pre_code
                            clean_sentence = re.sub(r'<tool>.*?</tool>', '', current_sentence, flags=re.DOTALL).strip()
                            clean = clean_sentence.replace('*', '').replace('`', '').replace('#', '')
                            if clean and not is_code:
                                
                                speak_async(clean)
                            current_sentence = ''
                        else:
                            current_sentence += chunk.text
                            summary_prompt += chunk.text

                        yield chunk.text
                        if '```' in ai_reply:
                            is_code = True


                        if '<tool>' in current_sentence and '</tool>' in current_sentence:
                            clean_sentence = re.sub(r'<tool>.*?</tool>', '', current_sentence, flags=re.DOTALL).strip()
                            clean = clean_sentence.replace('*', '').replace('`', '').replace('#', '')
                            if clean and not is_code:
                                speak_async(clean)
                            current_sentence = ''
                            
       
                        inside_tool = '<tool>' in current_sentence and '</tool>' not in current_sentence
                        if any(current_sentence.strip().endswith(p) for p in [',','.', '!', '?', '\n']) and not inside_tool:
                            clean_sentence = re.sub(r'<tool>.*?</tool>', '', current_sentence, flags=re.DOTALL).strip()
                            clean = clean_sentence.replace('*', '').replace('`', '').replace('#', '')
                            if clean and not is_code:

                                speak_async(clean)
                            current_sentence = ''
                            
                self.summary_history.append(f"VINCI: {summary_prompt}")
                summary_prompt = ''
                
                if not ai_reply.strip():
                    print("\n[LOGIC] Empty response received, retrying...")
                    ai_reply = ""
                    summary_prompt = ""
                    continue
                break

            
            except openai.OpenAIError as e:
                print(f"\n{e}\n")
                is_code = False
                self.code_block = ''
                ai_reply = ''
                summary_prompt = ''
                
                
                if attempt == max_retries - 1:
                    
                    yield f"\nLOGIC server error after {max_retries} attempts, try again\n"
                    return
                time.sleep(delay)
                delay *= 2

        pattern = r'''
                ```python[ \t]*\n
                (.*?)
                ^[ \t]*```[ \t]*$
            '''
        match = re.search(
            pattern,
            ai_reply,
            re.DOTALL | re.MULTILINE | re.VERBOSE
            
        )
        if match:
            self.code_block = match.group(1)
            is_code = True

        if current_sentence.strip():
            if not is_code:
                clean_sentence = re.sub(r'\b\w+:[^\n]*', '', current_sentence).strip()
                clean = clean_sentence.replace('*', '').replace('`', '').replace('#', '')
                if clean:
                    speak_async(clean)
                    
        if is_text_prompt:

            if not prompt.startswith('SCRIPT_RESULT') and not is_code:
                #memorymanager.save_memory_filter(prompt, ai_reply)
                pass

        if not is_code:

            tool_matches = re.findall(r'<tool>(.*?)</tool>', ai_reply, re.DOTALL)
            
            for tool_str in tool_matches:
                try:
                    tool_data = json.loads(tool_str)
                    command = tool_data.get("command")
                    name = tool_data.get("name", "")
                    args = tool_data.get("args", [])
                    print(f"args going in {args}")

                    if command == "run_script":
                        yield from self.run_scripts(tool_data)
                        
                    elif command == "builtin":

                        if name == "check_screen":
                            yield from self.check_screen(args)
                        elif name == "chat_monitor":
                            yield from self.chat_monitor(args)
                        elif name == "save":
                            yield from self.save_script(args)
                        elif name == "search_net":
                            yield from self.search_net(args)
                        elif name == "memory_manager":
                            yield from self.memory_manager(args)
                        elif name == "gui_connector":
                            yield from self.gui_controller(args)
                        elif name == "set_reminder":
                            yield from self.reminder(args)
                        elif name == "gen_code":
                            yield from self.gen_code(args)

                            
                except json.JSONDecodeError:
                    yield from self.call_logic("\n[Error: LOGIC produced malformed JSON tool call]\n")
                except Exception as e:
                    yield f"\n[Error executing tool: {e}]\n"

        if is_code:
            yield from self.run_gen_code(self.code_block)
            is_code = False
        
    def memory_manager(self,args):
        function_name,text = args[0],args[1]
        if function_name == 'delete':
            memorymanager.delete(text)
            yield from self.call_logic(f"deleted memory: {text}")

        else:
            memorymanager.save(text)
            yield from self.call_logic(f"saved memory: {text}")
    def chat_monitor(self,args):
        target_inbox = args[0]
        start_monitor(target_inbox)
        yield f"[Monitor] Connected to {target_inbox}"

    def gui_controller(self, args):
        parts = args.split(':', 1)
        args_str = parts[1] if len(parts) > 1 else ""
        args = [a.strip() for a in args_str.split('|')]

        func = args[0] if args else ""
        print('\ncontroller invoked')
        if not hasattr(self, 'gui_control'):
            self.gui_control = Control()

        if func == 'connect':
            window_title = args[1] if len(args) > 1 else ""
            buttons = self.gui_control.connect(window_title)
            result = f"[GUI] Connected to {window_title}. {len(buttons)} buttons found:\n" + ", ".join(buttons)
            print(f'\n{result}')
            yield from self.call_logic(result)

        elif func == 'click':
            button_name = args[1] if len(args) > 1 else ""
            click_type = args[2] if len(args) > 2 else "left"
            success, new_buttons = self.gui_control.click(button_name, click_type)
            if success:
                result = f"[GUI] Clicked: {button_name} ({click_type})"
                if new_buttons:
                    result += f"\n[GUI] New buttons: " + ", ".join(new_buttons)
                else:
                    result += f"\n[GUI] No new buttons"
            else:
                result = f"[GUI] Not found: {button_name}"
            print(f'\n{result}')
            yield from self.call_logic(result)

        else:
            yield from self.call_logic(f"[GUI] Unknown function: {func}")
        
    def search_net(self,args):
        print('\nsearching the net...')
        search_quest = args[0]

        search_result = ask_search_net(search_quest)
        print(f"\nsearch_result:{search_result} ")
        yield from self.call_logic(f"SCRIPT_RESULT: {search_result}")

    def gen_code(self,args):
        text = args[0]
        #print(args)
        reply = groq_caller.call_groq(text)
        self.code_block = reply
        print(self.code_block)

        yield from self.run_gen_code(self.code_block)   

    def terminate_gen_code(self):
        if self.script_results:
            self.script_results.kill()
            self.gen_code_terminator = True
    def run_gen_code_streamed(self, cmd):
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding='utf-8',
            errors='replace',
        )
        self.script_results = proc          # /kill still targets this

        lines = []
        for line in iter(proc.stdout.readline, ''):
            print(line, end='', flush=True)  # live output
            lines.append(line)

        proc.wait()
        return ''.join(lines).strip()

    def run_gen_code(self, code):
        self.gen_code_terminator = False

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, encoding='utf-8'
        ) as f:
            f.write(code)
            temp_path = f.name

        try:
            output = self.run_gen_code_streamed(['python', '-u', temp_path])

            if self.gen_code_terminator:
                output = "process terminated by user, standby for further instruction before doing anyting"
            elif not output:
                output = ""

            #print(f"script result from logic: {output}", flush=True)
            yield from self.call_logic(f"SCRIPT_RESULT: {output}")

        except Exception as e:
            print(f"GEN CODE ERROR: {e}", flush=True)

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
    def reminder(self,args):
        reminder_text = args[0] if args else "reminder set"
        minutes = float(args[1] if len(args) > 1 else 1)


        def fire():
            user_input_queue.put(
                f'system:Reminder FIRED: {reminder_text}'
            )
        t = threading.Timer(minutes*60,fire)
        t.daemon = True
        t.start()

        yield from self.call_logic(f'Reminder set: {reminder_text} - {minutes} minutes')

    def call_screen_analyzer(self, image, prompt):
        client = groq.Groq(api_key=GROQ_API_KEY)
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
        image_url = f"data:image/png;base64,{img_base64}"
    
        completion = client.chat.completions.create(
            model=MODEL_NAME_GROQ,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise image analysis engine. "
                        "NOTE: IF requested for phone screen check, say that You only check PC screen and can't help with that"
                        "Rules: "
                        "1. Analyze the image exactly as requested by the user. "
                        "2. Output ONLY the analysis — no greetings, no questions, no offers to help further. "
                        "3. Be specific and detailed: name objects, describe colors, positions, text, UI elements, and spatial relationships. "
                        "4. If the user asks a specific question, answer it directly. If no question is given, describe the image comprehensively. "
                        "5. Never ask the user for clarification. Never suggest next steps. End your response after delivering the analysis."
                        
                    )
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        }
                    ]
                }
            ],
            temperature=1,
            top_p=1,
            stream=False,
            stop=None,
            reasoning_effort='low'
        )
        reply = completion.choices[0].message.content
        print(reply)
        yield from self.call_logic(reply)

    # def check_screen(self,prompt):
    #     global history
    #     ss = pg.mixer.Sound('screenshot.wav')
    #     ss.play()
    #     text = prompt.split(':',1)
        
    #     if len(text) > 1:
    #         question = text[1]
    #     else:
    #         question = 'explain this image in detail KEEP IT SHORT AND ACCURATE'

    #    # print(question)
    #     screenshot = ImageGrab.grab()
    #     print('screen_shot_taken')
    #     yield from self.call_screen_analyzer(screenshot,question)

    def check_screen(self, args):
        global history
        import pygame as pg
        pg.mixer.init()
        ss = pg.mixer.Sound('screenshot.wav')
        ss.play()
        question = None
        try:
            text = args[0]
        except Exception as e:
            question = text if len(text) > 1 else 'explain this image in detail KEEP IT SHORT AND ACCURATE'
        
        screenshot = ImageGrab.grab()
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
            image_path = temp_file.name
            screenshot.save(image_path)
        
        print('screen_shot_taken:', image_path)
        
        try:
            # Run the async coroutine synchronously
            result = asyncio.run(ask_image(image_path, question))
            yield from self.call_logic(result)
        finally:
            if os.path.exists(image_path):
                os.remove(image_path)

    def save_script(self, file_name):
        name = file_name[0]
        code = self.code_block
        with open(f'logic_tools/{name}', 'w', encoding='utf-8') as f:
            f.write(code)
        self.code_block = ''
        yield f"\nSaved as {name}.\n"  
    
    def run_scripts(self, tool_data):
        script_name = tool_data.get("name", "").strip()
        args = tool_data.get("args", [])
        

        if isinstance(args, list) and len(args) > 0 and isinstance(args[0], (list, dict)):
            string_args = [json.dumps(args)]

        elif isinstance(args, str):
            string_args = [args]

        else:
            string_args = [str(arg) for arg in args]
            
        path = f'{self.logic_tools}/{script_name}'

        if os.path.exists(path):
            print(f'args being passed: {string_args}')
            
            result = subprocess.Popen(['python', '-u', path] + string_args,
                                    stdout=subprocess.PIPE, 
                                    stderr=subprocess.PIPE, 
                                    encoding='utf-8',
                                    errors='replace'
                                    )
            
            stdout, stderr = result.communicate()
            #print(stdout)
            #print(f"stderr: {stderr}") 
            
            output = stdout.strip() or stderr.strip()
            print(output,flush=True)
            yield from self.call_logic(f'SCRIPT_RESULT: {output}.\n.')
        else:
            yield from self.call_logic(f"SCRIPT_RESULT: Error. Script '{script_name}' not found.")

MODEL_GEMINI_CODE = MODEL_CODE
class Gemini_code_ai():
    def __init__(self):
        self.system_prompt = """
You are a coding agent. You write code and nothing else.
All code is written inside a markdown code block.
No explanation, no comments outside the block.
"""
        self.code_block = ''

    def call_gemini_code(self, prompt, history: list = None):
        is_code = False
        
        messages = [{"role": "system", "content": self.system_prompt}]
        if history:
            for item in history:
                role = item.get("role", "user")
                if role == "model":
                    role = "assistant"
                content = item.get("parts", [{}])[0].get("text", "") if "parts" in item else item.get("content", "")
                messages.append({"role": role, "content": content})
                
        if isinstance(prompt, str):
            messages.append({"role": "user", "content": prompt})
        else:
            messages.append({"role": "user", "content": str(prompt)})

        response = client.chat.completions.create(
            model=MODEL_GEMINI_CODE,
            messages=messages,
            temperature=1.0,
            top_p=0.9,
        )

        ai_reply = response.choices[0].message.content or ""

        if '```' in ai_reply:
            print('...generating code')
            self.code_block = ''
            parts = ai_reply.split('```')
            for part in parts:
                if part.startswith('python'):
                    code = part
                    if '\n' in code:
                        code = code[code.index('\n')+1:]
                    self.code_block = code
                    is_code = True
                    break

        print(f'assistant-reply:\n{ai_reply}')
        return self.code_block if is_code else ai_reply

gemini_code = Gemini_code_ai

class groq_ai():
    def __init__(self):
        self.client = groq.Groq(api_key=GROQ_API_KEY)
        self.chat_history = [
            {
                "role": "system",
                "content": rf"""
                
                you are a history compactor agent, you 
                summerize history chats given to you and do nothing else. 
                you write in plain text when writting summary.
                no explanation or anything. 
                ignore anything you see inside relevant_memory:[memory]. do not add them in summary
 
                """
            }
        ]
        self.code_block = ''
    def get_time(self):
        now = datetime.datetime.now()
        print(now.strftime("%I:%M %p %B %d, %Y"))
        
    def call_groq(self,prompt):
        try:
            is_code = False
            self.chat_history.append({
                "role": "user",
                "content": str(prompt)
            })

            response = self.client.chat.completions.create(
                        model=MODEL_NAME_GROQ,
                        messages=self.chat_history,
                        temperature=0.7,
                        reasoning_effort='low'
                    )
        
            ai_reply = response.choices[0].message.content

            if '```' in ai_reply:
                print('...generating code ')
                self.code_block = ''
                parts = ai_reply.split('```')
                for part in parts:
                    if part.startswith('python'):
                        code = part
                        if '\n' in code:
                            code = code[code.index('\n')+1:]
                        self.code_block = code
                        is_code = True
                        break
            self.chat_history = [self.chat_history[0]]
            
            print(f'groq-reply:\n {ai_reply}')
            
            if 'run_script|' in ai_reply:
                summary_text = ai_reply.split('run_script|', 1)[1].strip()
                self.save_session(f"summary_text\n{self.get_time()}")
                print('Summary saved to file.')
                return None

            if is_code:
                return self.code_block
            else:
                return ai_reply
            
        except Exception as e:
            print('too big for normal groq\nusing Omniroute default model')
            self.fallback_summarize(prompt)

    def fallback_summarize(self, prompt):
        try:
            fallback_session = OpenAIChatSession(
                client=client,
                model=MODEL,
                system_instruction="""
    You are a conversation history summarizer.

    Your ONLY job is to summarize the provided conversation history.

    Return ONLY the summary in plain text.
    Do not answer the conversation.
    Do not execute tools.
    Do not generate code.
    Do not continue the conversation.
    """,
                temperature=0.7,
                top_p=0.9
            )

            response = fallback_session.send_message_stream(
                f"Summarize this conversation:\n{prompt}"
            )

            summary = ''.join(
                chunk.text
                for chunk in response
                if chunk.text
            ).strip()

            if not summary:
                raise RuntimeError("Fallback returned an empty summary.")


            print("[Fallback] Summary given successfully.")
            print("\n"+summary)
            return summary

        except Exception as e:
            print(f"[Fallback] Summary failed: {e}")
            return None
    

class Groq_session_ai():
    def __init__(self):
        self.client = groq.Groq(api_key=GROQ_API_KEY)
        self.chat_history = [
            {
                "role": "system",
                "content": rf"""

                you are a coding and history compactor agent, you write code and save 
                summerize history chats given to you.
                you write in plain text when writting summary. and only write in code block when asked to code something
                no explanation or anything. 
                ignore anything you see inside relevant_memory:[memory]. do not add them in summary
                all of your code ar written inside a code block. 

                <Scripts>
                to save a summary write, run_script|[summary]
                the script would automatically save the summary in a txt file

                </Scripts>
                """
            }
        ]
        self.code_block = ''
    def save_session(self, text):
        with open("D:/Ai/logic/memory/summaries/summaries.txt", "w", encoding="utf-8") as f:
            f.write(text + "\n\n")


    def fallback_summarize(self, prompt):
        try:
            fallback_session = OpenAIChatSession(
                client=client,
                model=MODEL,
                system_instruction="""
    You are a conversation history summarizer.

    Your ONLY job is to summarize the provided conversation history.

    Return ONLY the summary in plain text.
    Do not answer the conversation.
    Do not execute tools.
    Do not generate code.
    Do not continue the conversation.
    """,
                temperature=0.7,
                top_p=0.9
            )

            response = fallback_session.send_message_stream(
                f"Summarize this conversation:\n{prompt}"
            )

            summary = ''.join(
                chunk.text
                for chunk in response
                if chunk.text
            ).strip()

            if not summary:
                raise RuntimeError("Fallback returned an empty summary.")

            self.save_session(summary)

            print("[Fallback] Summary saved successfully.")

            return summary

        except Exception as e:
            print(f"[Fallback] Summary failed: {e}")
            return None
    

    def get_current_formatted_time(self):
        from datetime import datetime
        return datetime.now().strftime('%I:%M %p, %B %d, %Y')

    def call_groq(self,prompt):
        is_code = False
        #print(f"prompt given to groq\n {prompt}")
        self.chat_history.append({
            "role": "user",
            "content": str(prompt)
        })

        try:
            response = self.client.chat.completions.create(
                model=MODEL_NAME_GROQ,
                messages=self.chat_history,
                temperature=0.7,
                reasoning_effort='low'
            )

            ai_reply = response.choices[0].message.content

        except Exception as e:
            print(f"\n[Groq ERROR] {e}")

            summary = self.fallback_summarize(prompt)

            self.chat_history = [self.chat_history[0]]

            return summary

        if '```' in ai_reply:
            print('...generating code ')
            self.code_block = ''
            parts = ai_reply.split('```')
            for part in parts:
                if part.startswith('python'):
                    code = part
                    if '\n' in code:
                        code = code[code.index('\n')+1:]
                    self.code_block = code
                    is_code = True
                    break
                
        self.chat_history = [self.chat_history[0]]
        print(f'groq-reply:\n {ai_reply}')


        if 'run_script|' in ai_reply:
            summary_text = ai_reply.split('run_script|', 1)[1].strip()
            summary_with_time = f'{summary_text} \n - {self.get_current_formatted_time()} '
            self.save_session(summary_with_time)
            
            print('Summary saved to file.')
            return None

        if is_code:
            return self.code_block
        else:
            return ai_reply
    


groq_ses = Groq_session_ai()

groq_caller = groq_ai()
gemini_code = Gemini_code_ai()
logic_ai = Base_AI()
os.system('cls')




import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def get_local_day_schedule():
    try:
        creds = Credentials.from_authorized_user_file(r'D:\Ai\logic\logic_tools\oauth_token_files\google_oauth.json')
        service = build('calendar', 'v3', credentials=creds)
        
        local_tz = datetime.timezone(datetime.timedelta(hours=6))
        local_now = datetime.datetime.now(local_tz)
        
        DAY_START_HOUR = 4 
        
        if local_now.hour < DAY_START_HOUR:
            start_of_day = (local_now - datetime.timedelta(days=1)).replace(hour=DAY_START_HOUR, minute=0, second=0, microsecond=0)
        else:
            start_of_day = local_now.replace(hour=DAY_START_HOUR, minute=0, second=0, microsecond=0)
            
        end_of_day = start_of_day + datetime.timedelta(days=1, seconds=-1)
        
        events_result = service.events().list(calendarId='primary', 
                                              timeMin=start_of_day.isoformat(), 
                                              timeMax=end_of_day.isoformat(), 
                                              singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])
        
        if not events:
            return "Your schedule is empty for this cycle."
        
        past_events = []
        future_events = []
        
        for event in events:
            if 'date' in event['start'] and 'dateTime' not in event['start']:
                start_date = event['start'].get('date')
                sd = datetime.datetime.fromisoformat(start_date).replace(tzinfo=local_tz)
                
                # All-day event: consider it "done" only when the day is fully over
                # (i.e., local_now is past the end of that day)
                end_of_event_day = sd + datetime.timedelta(days=1)
                
                line = f"- All day ({sd.strftime('%B %d')}): {event['summary']}\n"
                if local_now >= end_of_event_day:
                    past_events.append(line)
                else:
                    future_events.append(line)
                    
            else:
                start_raw = event['start'].get('dateTime', event['start'].get('date'))
                end_raw = event['end'].get('dateTime', event['end'].get('date'))
                try:
                    start_dt = datetime.datetime.fromisoformat(start_raw).astimezone(local_tz)
                    end_dt = datetime.datetime.fromisoformat(end_raw).astimezone(local_tz)
                    
                    start_str = start_dt.strftime('%I:%M %p')
                    end_str = end_dt.strftime('%I:%M %p')
                    
                    line = f"- {start_str} to {end_str} ({start_dt.strftime('%B %d')}): {event['summary']}\n"
                    
                    if start_dt < local_now:
                        past_events.append(line)
                    else:
                        future_events.append(line)
                except Exception:
                    future_events.append(f"- {start_raw} to {end_raw}: {event['summary']}\n")
        
        schedule = f"Schedule for {start_of_day.date()}:\n"
        
        if future_events:
            schedule += "\nUpcoming:\n" + "".join(future_events)
        else:
            schedule += "\nNothing upcoming.\n"
            
        if past_events:
            schedule += "\nAlready done:\n" + "".join(past_events)
            
        local_time_str = local_now.strftime("%I:%M %p")
        local_date_str = local_now.strftime("%B %d, %Y")
        return f"{schedule}\nCurrent Local Time: {local_time_str}\nDate: {local_date_str}"
    except Exception as e:
        return f"Error retrieving local schedule: {e}"

#print(get_local_day_schedule())

voice_mode = False  # start in text mode

def terminal_code(code):
    global voice_mode
    if code == '/compact':
        logic_ai.reset_chat()

    elif code == '/v':
        voice_mode = not voice_mode
        print(f'[Voice mode {voice_mode}]')

    elif code == '/chat off':
        stop_monitor()
    elif code == '/save':
        logic_ai.session_saver()        
    elif code == '/debug':
        logic_ai.debug_prompt = not logic_ai.debug_prompt
        print(f'debugger is {logic_ai.debug_prompt}')
    elif code == '/kill':
        logic_ai.gen_code_terminator = True
        logic_ai.terminate_gen_code()
        print("kill triggered")

    elif code.startswith('/model'):

        try:
            model_name = code.split('/model')[1]
            new_history = logic_ai.chat.history
            logic_ai.chat = OpenAIChatSession(
                        client=client,
                        model=model_name,
                        system_instruction=build_system_prompt(),
                        history=new_history,
                        temperature=1.0,
                        top_p=0.9,
                    
                    )


        except Exception as e:
            pass
    elif code == '/overlay':

        logic_voice.enable_overlay = not logic_voice.enable_overlay
        print(f"overlay {logic_voice.enable_overlay}")
        
    elif code.startswith('/reload'):
        try:
            library = code.split('/reload')[1]
            print(f'reloading...{library}')
            importlib.reload(library)
        except Exception as e:
            pass
    else:
        print('\nCode invalid')

user_input_queue = queue.Queue()
monitor_bot = None

def start_monitor(name):
    global monitor_bot
    if monitor_bot is not None:
        print("[Monitor] Already running")
        return
    monitor_bot = MessengerBot()
    monitor_bot.start(name)
    print(f"[Monitor] Started watching {name}")

def stop_monitor():
    global monitor_bot
    if monitor_bot:
        monitor_bot.stop()
        monitor_bot = None
        print("[Monitor] Stopped")


color_reply = Style(color="#328BFF", bold=True)
color_sep = Style(color="#75716C", dim=True)
color_user = Style(color="#619FAF")
color_label = Style(color="#619FAF")

#prompt_ready = threading.Event()

def input_thread():
    while True:
        text = input()

        # Go back to the line where input() displayed the text
        sys.stdout.write("\033[1A\r\033[2K")
        sys.stdout.flush()

        # Replace that line
        the_console.print(
            f"YOU: {text}",
            style=color_user,
            highlight=False
        )

        if text == "/kill":
            logic_ai.terminate_gen_code()
            print("[Kill triggered]")
            continue

        user_input_queue.put(text)

def load_last_summary(file_path="D:/Ai/logic/memory/summaries/summaries.txt"):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "No prior conversation."



    
if __name__ == "__main__":
    
    the_console.print("LOGIC: ", style=color_reply, end="", highlight=False)
    
    for chunk in logic_ai.call_logic(
    f"system: user is Online. Greet briefly. If schedule matches previous summary, ask about user's current activity or mood instead. Do not reference schedule items already known. Previous: {load_last_summary()}\nSchedule: {get_local_day_schedule()}"
    ):
        the_console.print(chunk, style=color_reply, end="", highlight=False)
    print('')
    

    threading.Thread(target=input_thread, daemon=True).start()
    #prompt_ready.set()
    
    while True:
        prompt = None

        # Check injection first
        if monitor_bot is not None:
            injected = monitor_bot.get_injection()
            if injected:
                prompt = f"system: [Messenger] Msg returned, send reply via  send_message_to_messenger.py directly, don't ask. Chat context:\n{injected}"
                print(f'\n[INJECTED] {prompt}')  

        if voice_mode:
            prompt = get_voice()
            if prompt is not None:
                print(prompt)

        if prompt is None:
            try:
                prompt = user_input_queue.get_nowait()

            except queue.Empty:
                pass

        if prompt is None:
            time.sleep(0.1)
            continue

        if prompt.startswith('/'):
            terminal_code(prompt)
            #prompt_ready.set()
            continue

        if prompt.lower() == 'exit':
            break

        logic_ai.user_prompt = prompt
        
        stop_voice()

        reply = logic_ai.call_logic(prompt)
        
        sys.stdout.write("\r\033[K")  #* clear current line
        sys.stdout.flush()

        

        the_console.print("─" * 40, style=color_sep, highlight=False)
        the_console.print("LOGIC: ", style=color_reply, end="", highlight=False)

        for chunk in reply:
            the_console.print(chunk, style=color_reply, end="", highlight=False)

        print()



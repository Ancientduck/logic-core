"""
LOGIC WebSocket Server
Run: python logic_server.py
Open: http://localhost:8080
"""

import asyncio
import json
import websockets
import http.server
import socketserver
import threading
import os
import sys
from datetime import datetime
from pathlib import Path

# Optional imports
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

try:
    import pynvml
    pynvml.nvmlInit()
    HAS_NVML = True
except (ImportError, Exception):
    HAS_NVML = False

# ===== GUI MODE FLAG =====
os.environ['VINCI_GUI_MODE'] = '1'

# ===== IMPORT YOUR VINCI CORE =====
try:
    import logic as logic
    VINCI_AVAILABLE = True
    print("[LOGIC] Core loaded successfully")
except Exception as e:
    print(f"[LOGIC] Failed to load: {e}")
    VINCI_AVAILABLE = False


class LOGICWebSocketHandler:
    """Handles WebSocket communication between GUI and LOGIC"""

    def __init__(self):
        self.clients = set()
        self.greeting_sent = False

    async def register(self, websocket):
        self.clients.add(websocket)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Client connected")
        await self.send_system_stats(websocket)
        
        if not self.greeting_sent and VINCI_AVAILABLE:
            self.greeting_sent = True
            asyncio.create_task(self.send_greeting(websocket))

    def unregister(self, websocket):
        self.clients.discard(websocket)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Client disconnected")

    async def send_greeting(self, websocket):
        try:
            schedule = logic.get_local_day_schedule()
            prompt = f"System: user is Online via GUI. greet him accordingly to your context, Context for your awareness — today's schedule: {schedule}"
            
            full_response = ""
            for chunk in logic.logic_ai.call_logic(prompt):
                chunk_text = chunk.text if hasattr(chunk, 'text') else chunk
                full_response += chunk_text
                try:
                    await websocket.send(json.dumps({
                        "type": "chunk",
                        "message": chunk_text
                    }))
                except:
                    pass
            
            await websocket.send(json.dumps({
                "type": "response_complete",
                "message": ""
            }))
        except Exception as e:
            print(f"[Greeting Error] {e}")

    async def send_system_stats(self, client=None):
        stats = self.get_system_stats()
        message = json.dumps({"type": "system", "data": stats})
        if client:
            try:
                await client.send(message)
            except:
                pass
        else:
            self.broadcast(message)

    def broadcast(self, message):
        for client in list(self.clients):
            try:
                asyncio.create_task(client.send(message))
            except:
                pass

    def get_system_stats(self):
        if HAS_PSUTIL:
            return {
                "cpu": int(psutil.cpu_percent()),
                "ram": int(psutil.virtual_memory().percent),
                "disk": int(psutil.disk_usage('/').percent),
                "gpu": self._get_gpu_usage()
            }
        else:
            import random
            return {
                "cpu": random.randint(15, 45),
                "ram": random.randint(40, 70),
                "disk": 67,
                "gpu": 0
            }

    def _get_gpu_usage(self):
        if HAS_NVML:
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                return int(util.gpu)
            except Exception:
                return 0
        return 0

    async def process_command(self, raw_message):
        try:
            data = json.loads(raw_message)
            command = data.get('message', '').strip()
            
            if not command:
                return json.dumps({"type": "error", "message": "Empty command"})

            print(f"[Command] {command}")

            if not VINCI_AVAILABLE:
                return json.dumps({
                    "type": "response",
                    "message": "LOGIC core not loaded. Check terminal for errors."
                })

            if command == '/clear':
                return json.dumps({"type": "cleared", "message": ""})
            
            if command == '/schedule':
                schedule = logic.get_local_day_schedule()
                return json.dumps({"type": "response", "message": schedule})

            if command == '/reset':
                logic.logic_ai.reset_chat()
                return json.dumps({"type": "success", "message": "Chat history reset"})

            # ===== SEND TO VINCI CORE =====
            for chunk in logic.logic_ai.call_logic(command):
                chunk_text = chunk.text if hasattr(chunk, 'text') else chunk
                
                for client in list(self.clients):
                    try:
                        await client.send(json.dumps({
                            "type": "chunk",
                            "message": chunk_text
                        }))
                    except:
                        pass

            for client in list(self.clients):
                try:
                    await client.send(json.dumps({
                        "type": "response_complete",
                        "message": ""
                    }))
                except:
                    pass

            return None

        except json.JSONDecodeError:
            return json.dumps({"type": "error", "message": "Invalid message format"})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return json.dumps({"type": "error", "message": str(e)})


# ===== FIXED HTTP SERVER FOR WINDOWS =====
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.directory = os.path.dirname(os.path.abspath(__file__))
        super().__init__(*args, directory=self.directory, **kwargs)

    def do_GET(self):
        if self.path == '/':
            self.path = '/logic_gui.html'
        try:
            return super().do_GET()
        except:
            pass

    def log_message(self, format, *args):
        pass


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True
    allow_reuse_port = True


def run_http_server(port):
    """Run HTTP server in its own thread with its own event loop"""
    try:
        with ReusableTCPServer(("", port), QuietHandler) as httpd:
            httpd.serve_forever()
    except Exception as e:
        print(f"[HTTP] Server error: {e}")


async def websocket_handler(websocket, handler):
    await handler.register(websocket)
    try:
        async for message in websocket:
            response = await handler.process_command(message)
            if response:
                await websocket.send(response)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        handler.unregister(websocket)


async def main():
    handler = LOGICWebSocketHandler()

    # Start HTTP server in a proper daemon thread
    port = 8080
    http_thread = threading.Thread(target=run_http_server, args=(port,), daemon=True)
    http_thread.start()
    # Give it a moment to bind
    await asyncio.sleep(0.5)

    ws_port = 8765
    print()
    print("=" * 55)
    print("       VINCI GUI SERVER")
    print("=" * 55)
    print(f"  GUI:       http://localhost:{port}")
    print(f"  WebSocket: ws://localhost:{ws_port}")
    print(f"  LOGIC:     {'Connected' if VINCI_AVAILABLE else 'NOT LOADED'}")
    print("=" * 55)
    print()

    if not HAS_PSUTIL:
        print("  [!] psutil not installed — fake stats shown")
    if not HAS_NVML:
        print("  [!] pynvml not installed — GPU stats disabled")
    print()

    async with websockets.serve(
        lambda ws: websocket_handler(ws, handler),
        "localhost",
        ws_port
    ):
        while True:
            await handler.send_system_stats()
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[LOGIC] Server stopped")
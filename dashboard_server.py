import http.server
import socketserver
import os
import json
import webbrowser

PORT = 20129
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

DEFAULT_ENV_TEMPLATE = """USER_NAME="Apurbo (your maker)"
API_KEY=
BASE_URL="http://localhost:20128/v1"
GROQ_API_KEY=
TINYFISH_API_KEY=
YOU_API_KEY=
MODEL="logic"
MODEL_NAME_GROQ="openai/gpt-oss-120b"
"""

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def do_GET(self):
        clean_path = self.path.split('?')[0]
        if clean_path == '/api/env':
            env_path = os.path.join(DIRECTORY, '.env')
            created = False
            if not os.path.exists(env_path):
                try:
                    with open(env_path, 'w', encoding='utf-8') as f:
                        f.write(DEFAULT_ENV_TEMPLATE)
                    created = True
                except Exception:
                    pass

            content = DEFAULT_ENV_TEMPLATE
            if os.path.exists(env_path):
                try:
                    with open(env_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except Exception:
                    pass

            response_bytes = json.dumps({
                "created_default": created,
                "path": env_path,
                "content": content
            }).encode('utf-8')

            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(response_bytes)))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response_bytes)
        else:
            super().do_GET()

    def do_POST(self):
        clean_path = self.path.split('?')[0]
        if clean_path == '/api/env':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            env_path = os.path.join(DIRECTORY, '.env')
            try:
                text_to_write = post_data
                try:
                    parsed = json.loads(post_data)
                    if isinstance(parsed, dict) and 'content' in parsed:
                        text_to_write = parsed['content']
                except Exception:
                    pass

                with open(env_path, 'w', encoding='utf-8') as f:
                    f.write(text_to_write)

                res_bytes = json.dumps({"status": "success", "message": ".env updated"}).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(res_bytes)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(res_bytes)
            except Exception as e:
                err_bytes = json.dumps({"status": "error", "message": str(e)}).encode('utf-8')
                self.send_response(500)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(err_bytes)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(err_bytes)
        else:
            self.send_response(404)
            self.end_headers()

if __name__ == '__main__':
    os.chdir(DIRECTORY)
    with ThreadedTCPServer(("127.0.0.1", PORT), DashboardHandler) as httpd:
        print(f"Dashboard server running at http://localhost:{PORT}/setup_dashboard.html")
        httpd.serve_forever()

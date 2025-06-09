import http.server
import asyncio
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from agents.agent import root_agent
from google.genai import types
import os

PORT: int = 8080

# Instantiate session service
session_service = InMemorySessionService()

class RequestHandler(http.server.SimpleHTTPRequestHandler):
    DEFAULT_USER_ID = "default_user"
    DEFAULT_SESSION_ID = "default_session"
    APP_NAME = "computron_9000"

    def __init__(self, *args, **kwargs):
        # Ensure a session exists, or create one if not
        session = session_service.get_session_sync(
            app_name=self.APP_NAME, 
            user_id=self.DEFAULT_USER_ID,
            session_id=self.DEFAULT_SESSION_ID
        )
        if session is None:
            session = session_service.create_session_sync(
                app_name=self.APP_NAME,
                user_id=self.DEFAULT_USER_ID,
                session_id=self.DEFAULT_SESSION_ID
            )
        self.runner = Runner(
            agent=root_agent,  # The agent we want to run
            app_name=self.APP_NAME,  # Associates runs with our app
            session_service=session_service  # Uses our shared session manager
        )
        super().__init__(*args, **kwargs)

    """HTTP proxy handler for serving chat UI and proxying requests to Ollama."""
    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self) -> None:
        """Handle POST requests for chat and pass to agent runner."""
        if self.path == '/api/chat':
            content_length: int = int(self.headers.get('Content-Length', 0))
            post_data: bytes = self.rfile.read(content_length)
            import json
            try:
                data = json.loads(post_data.decode('utf-8'))
                user_query = data.get('message')
            except Exception:
                self.send_response(400)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"error": "Invalid JSON or missing message field."}')
                return
            # Call the agent and get the response
            agent_response = self.handle_agent_chat(user_query)
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = json.dumps({"response": agent_response}).encode('utf-8')
            self.wfile.write(response)
        else:
            self.send_error(404)

    def do_GET(self) -> None:
        """Serve the chat UI or proxy model tags to Ollama."""
        if self.path in ['', '/']:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            # Serve agent_ui.html from the correct static directory
            html_path = os.path.join(os.path.dirname(__file__), 'static', 'agent_ui.html')
            try:
                with open(html_path, 'rb') as f:
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.wfile.write(b'<h1>File not found</h1>')
        elif self.path.startswith('/static/'):
            # Serve static files from the static directory (sibling to this script)
            file_path = os.path.join(os.path.dirname(__file__), self.path.lstrip('/'))
            if os.path.isfile(file_path):
                self.send_response(200)
                # Basic content type detection
                if file_path.endswith('.css'):
                    self.send_header('Content-Type', 'text/css')
                elif file_path.endswith('.js'):
                    self.send_header('Content-Type', 'application/javascript')
                elif file_path.endswith('.html'):
                    self.send_header('Content-Type', 'text/html')
                elif file_path.endswith('.png'):
                    self.send_header('Content-Type', 'image/png')
                elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
                    self.send_header('Content-Type', 'image/jpeg')
                elif file_path.endswith('.svg'):
                    self.send_header('Content-Type', 'image/svg+xml')
                else:
                    self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                with open(file_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404)
        else:
            super().do_GET()

    def end_headers(self) -> None:
        """Ensure CORS headers are set for GET requests."""
        if self.command == 'GET':
            self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def handle_agent_chat(self, user_query: str) -> str:
        """Handles a chat message by passing it to the agent runner and returning the response."""
        async def call_agent_async(query: str, runner):
            content = types.Content(role='user', parts=[types.Part(text=query)])
            final_response_text = "Agent did not produce a final response."
            async for event in runner.run_async(user_id=self.DEFAULT_USER_ID, session_id=self.DEFAULT_SESSION_ID, new_message=content):
                if event.is_final_response():
                    if event.content and event.content.parts:
                        final_response_text = event.content.parts[0].text
                    elif event.actions and getattr(event.actions, 'escalate', False):
                        final_response_text = f"Agent escalated: {getattr(event, 'error_message', 'No specific message.')}"
                    break
            return final_response_text

        # Run the async function in the current (sync) context
        return asyncio.run(call_agent_async(user_query, self.runner))

if __name__ == '__main__':
    from server import start_server
    start_server()

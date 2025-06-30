# Standard library imports
"""aiohttp web server exposing the COMPUTRON_9000 agent API."""

import os
import json

# Third-party imports
from aiohttp import web

# Conditional imports based on environment variable
if os.environ.get("AGENT_SDK", "pydantic").lower() == "adk":
    from agents.adk.message_handler import handle_user_message
elif os.environ.get("AGENT_SDK", "pydantic").lower() == "ollama":
    from agents.ollama.message_handler import handle_user_message
else:
    from agents.pydantic_ai.message_handler import handle_user_message
from agents.types import Data

# Local imports

STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
}

async def handle_options(request):
    """Handle CORS preflight requests."""
    return web.Response(status=200, headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    })

async def handle_post(request):
    """Handle chat POST requests from the UI."""
    if request.path == '/api/chat':
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON.'}, status=400, headers=CORS_HEADERS)
        user_query = data.get('message')
        if user_query is None or str(user_query).strip() == "":
            return web.json_response({'error': 'Message field is required.'}, status=400, headers=CORS_HEADERS)
        user_query = str(user_query)
        stream = data.get('stream', False)
        # Handle optional data field (array with 0 or more entries, always with base64 and content_type)
        data_objs = []
        data_field = data.get('data')
        if data_field and len(data_field) > 0:
            data_objs = [Data(base64_encoded=obj['base64'], content_type=obj['content_type']) for obj in data_field]
        else:
            data_objs = None
        if stream:
            # Streaming response
            resp = web.StreamResponse(
                status=200,
                reason='OK',
                headers={
                    'Content-Type': 'application/json',
                    **CORS_HEADERS,
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Transfer-Encoding': 'chunked',
                }
            )
            await resp.prepare(request)
            try:
                async for event in handle_user_message(user_query, data_objs, stream=True):
                    data = {'response': event.message, 'final': event.final}
                    await resp.write((json.dumps(data) + '\n').encode('utf-8'))
                    if event.final:
                        break
            except Exception as exc:
                error_data = {'error': f'Server error: {str(exc)}', 'final': True}
                await resp.write((json.dumps(error_data) + '\n').encode('utf-8'))
            finally:
                await resp.write_eof()
            return resp
        else:
            # Non-streaming: get the only result from the generator
            gen = handle_user_message(user_query, data_objs, stream=False)
            final_response_text = None
            async for event in gen:
                final_response_text = event.message
            return web.json_response({'response': final_response_text, 'final': 'true'}, headers=CORS_HEADERS)
    else:
        return web.Response(status=404)

async def handle_get(request):
    """Serve the chat UI and static assets."""
    if request.path in ['', '/']:
        html_path = os.path.join(STATIC_DIR, 'agent_ui.html')
        if os.path.isfile(html_path):
            with open(html_path, 'rb') as f:
                html = f.read()
            return web.Response(body=html, content_type='text/html', headers=CORS_HEADERS)
        else:
            return web.Response(text='<h1>File not found</h1>', content_type='text/html', headers=CORS_HEADERS)
    elif request.path.startswith('/static/'):
        rel_path = request.path[len('/static/'):]
        file_path = os.path.join(STATIC_DIR, rel_path)
        if os.path.isfile(file_path):
            # Guess content type
            if file_path.endswith('.css'):
                content_type = 'text/css'
            elif file_path.endswith('.js'):
                content_type = 'application/javascript'
            elif file_path.endswith('.html'):
                content_type = 'text/html'
            elif file_path.endswith('.png'):
                content_type = 'image/png'
            elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif file_path.endswith('.svg'):
                content_type = 'image/svg+xml'
            else:
                content_type = 'application/octet-stream'
            with open(file_path, 'rb') as f:
                data = f.read()
            return web.Response(body=data, content_type=content_type, headers=CORS_HEADERS)
        else:
            return web.Response(status=404)
    else:
        return web.Response(status=404)

app = web.Application()
app.router.add_route('OPTIONS', '/api/chat', handle_options)
app.router.add_route('POST', '/api/chat', handle_post)
app.router.add_route('GET', '/', handle_get)
app.router.add_route('GET', '/static/{tail:.*}', handle_get)

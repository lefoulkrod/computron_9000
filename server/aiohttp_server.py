import asyncio
import os
import json
from aiohttp import web
from google.adk.runners import Runner
from google.adk.events.event import Event
from google.adk.sessions import InMemorySessionService
from agents.agent import root_agent
from google.genai import types
from typing import AsyncGenerator

PORT = 8080
STATIC_DIR = os.path.join(os.path.dirname(__file__), 'static')

# Instantiate session service
session_service = InMemorySessionService()
APP_NAME = "computron_9000"
DEFAULT_USER_ID = "default_user"
DEFAULT_SESSION_ID = "default_session"

# Ensure a session exists, or create one if not (async version)
async def ensure_session():
    session = await session_service.get_session(
        app_name=APP_NAME,
        user_id=DEFAULT_USER_ID,
        session_id=DEFAULT_SESSION_ID
    )
    if session is None:
        session = await session_service.create_session(
            app_name=APP_NAME,
            user_id=DEFAULT_USER_ID,
            session_id=DEFAULT_SESSION_ID
        )
    return session

async def handle_options(request):
    return web.Response(status=200, headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    })

async def handle_post(request):
    if request.path == '/api/chat':
        try:
            data = await request.json()
        except Exception:
            return web.json_response({'error': 'Invalid JSON.'}, status=400, headers={'Access-Control-Allow-Origin': '*'})
        user_query = data.get('message')
        if user_query is None or str(user_query).strip() == "":
            return web.json_response({'error': 'Message field is required.'}, status=400, headers={'Access-Control-Allow-Origin': '*'})
        user_query = str(user_query)
        stream = data.get('stream', False)
        await ensure_session()
        runner = Runner(
            agent=root_agent,
            app_name=APP_NAME,
            session_service=session_service
        )
        if stream:
            # Streaming response
            resp = web.StreamResponse(
                status=200,
                reason='OK',
                headers={
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'Cache-Control': 'no-cache',
                    'Connection': 'keep-alive',
                    'Transfer-Encoding': 'chunked',
                }
            )
            await resp.prepare(request)
            content = types.Content(role='user', parts=[types.Part(text=user_query)])
            events: AsyncGenerator[Event, None] = runner.run_async(
                user_id=DEFAULT_USER_ID,
                session_id=DEFAULT_SESSION_ID,
                new_message=content
            )
            async for event in events:
                if event.content and event.content.parts and event.content.parts[0].text is not None:
                    chunk = event.content.parts[0].text
                    data = {'response': chunk, 'final': event.is_final_response()}
                    await resp.write((json.dumps(data) + '\n').encode('utf-8'))
                if event.is_final_response():
                    break
            await resp.write_eof()
            return resp
        else:
            response_text = await handle_agent_chat(user_query, runner)
            return web.json_response({'response': response_text, 'final': 'true'}, headers={'Access-Control-Allow-Origin': '*'})
    else:
        return web.Response(status=404)

async def handle_get(request):
    if request.path in ['', '/']:
        html_path = os.path.join(STATIC_DIR, 'agent_ui.html')
        if os.path.isfile(html_path):
            with open(html_path, 'rb') as f:
                html = f.read()
            return web.Response(body=html, content_type='text/html', headers={'Access-Control-Allow-Origin': '*'})
        else:
            return web.Response(text='<h1>File not found</h1>', content_type='text/html', headers={'Access-Control-Allow-Origin': '*'})
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
            return web.Response(body=data, content_type=content_type, headers={'Access-Control-Allow-Origin': '*'})
        else:
            return web.Response(status=404)
    else:
        return web.Response(status=404)

async def handle_agent_chat(user_query: str, runner: Runner) -> str:
    content = types.Content(role='user', parts=[types.Part(text=user_query)])
    final_response_text = "Agent did not produce a final response."
    events: AsyncGenerator[Event, None] = runner.run_async(
        user_id=DEFAULT_USER_ID,
        session_id=DEFAULT_SESSION_ID,
        new_message=content
    )
    async for event in events:
        if event.is_final_response():
            if event.content and event.content.parts and event.content.parts[0].text is not None:
                final_response_text = str(event.content.parts[0].text)
            elif event.actions and getattr(event.actions, 'escalate', False):
                final_response_text = f"Agent escalated: {getattr(event, 'error_message', 'No specific message.')}"
            break
    return final_response_text or "Agent did not produce a final response."

app = web.Application()
app.router.add_route('OPTIONS', '/api/chat', handle_options)
app.router.add_route('POST', '/api/chat', handle_post)
app.router.add_route('GET', '/', handle_get)
app.router.add_route('GET', '/static/{tail:.*}', handle_get)


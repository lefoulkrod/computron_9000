import aiohttp.web

from server.aiohttp_server import app, PORT

if __name__ == "__main__":
    aiohttp.web.run_app(app, port=PORT)

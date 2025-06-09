import os
import socketserver
from .request_handler import RequestHandler, PORT

def start_server():
    with socketserver.ThreadingTCPServer(('', PORT), RequestHandler) as httpd:
        print(f"Serving at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            httpd.shutdown()
            httpd.server_close()

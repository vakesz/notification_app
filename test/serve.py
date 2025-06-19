"""Serve files from the current directory using a simple HTTP server."""

# start.py - A simple HTTP server to serve files from the current directory
# This script sets up a basic HTTP server to serve files from the current directory.
# python -m serve.py

import http.server
import socketserver

PORT = 8000
#TODO: Add an option that incrementally adds new and new posts. So we can test the client without having to manually add new posts.
class CustomHandler(http.server.SimpleHTTPRequestHandler):
    """Custom request handler to serve files from the current directory."""
    def do_GET(self):
        path = self.path
        if path == '/':
            path = '/index.html'
        return http.server.SimpleHTTPRequestHandler.do_GET(self)

Handler = CustomHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Serving at http://localhost:{PORT}")
    httpd.serve_forever()

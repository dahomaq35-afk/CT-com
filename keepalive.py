# =========================================================
# CT DASHBOARD - KEEPALIVE
# =========================================================

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "10000"))


class KeepAliveHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "text/plain; charset=utf-8"
        )
        self.end_headers()

        self.wfile.write(
            b"CT Dashboard is Online!"
        )

    def log_message(self, format, *args):
        return


def run_keepalive():

    server = HTTPServer(
        (HOST, PORT),
        KeepAliveHandler
    )

    server.serve_forever()


def start_keepalive():

    thread = threading.Thread(
        target=run_keepalive,
        daemon=True
    )

    thread.start()


if __name__ == "__main__":

    start_keepalive()

    threading.Event().wait()

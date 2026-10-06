import os
import threading

from flask import Flask


# =========================================================
# CT KEEP ALIVE
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "CT Dashboard is Online!"


@app.route("/health")
def health():
    return {
        "ok": True,
        "service": "CT Dashboard",
        "status": "online"
    }


def run():
    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )


def keep_alive():
    thread = threading.Thread(
        target=run,
        daemon=True
    )

    thread.start()

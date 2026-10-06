# =========================================================
# CT DASHBOARD
# Main Server - Full Stable Version
# =========================================================

import os
import re
import json
import sqlite3
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    session,
    redirect,
    url_for,
)


# =========================================================
# SETTINGS
# =========================================================

APP_NAME = "CT"
VERSION = "2.0.0"

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "10000"))

DB_FILE = "ct_dashboard.db"

DISCORD_API = "https://discord.com/api/v10"

# ---------------------------------------------------------
# Discord OAuth
# ---------------------------------------------------------

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "").strip()
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "").strip()
DISCORD_REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "").strip()

# ---------------------------------------------------------
# CT Server
# ---------------------------------------------------------

CT_GUILD_ID = os.getenv("CT_GUILD_ID", "").strip()

# Discord Administrator permission bit
ADMINISTRATOR_PERMISSION = 1 << 3

# ---------------------------------------------------------
# Flask secret
# ---------------------------------------------------------

SECRET_KEY = os.getenv("CT_SECRET_KEY", "").strip()

if not SECRET_KEY:
    # Used only as fallback.
    # On Render you should create CT_SECRET_KEY.
    SECRET_KEY = secrets.token_hex(32)


# =========================================================
# FLASK
# =========================================================

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)

app.secret_key = SECRET_KEY

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv(
        "CT_COOKIE_SECURE",
        "1"
    ) == "1",
)


# =========================================================
# SYSTEMS
# =========================================================

SYSTEMS = {
    "moderation": {
        "name": "الإدارة",
        "icon": "🛡️",
    },
    "welcome": {
        "name": "الترحيب",
        "icon": "👋",
    },
    "levels": {
        "name": "اللفلات",
        "icon": "📊",
    },
    "points": {
        "name": "النقاط",
        "icon": "⭐",
    },
    "tickets": {
        "name": "التذاكر",
        "icon": "🎫",
    },
    "applications": {
        "name": "التقديمات",
        "icon": "📝",
    },
    "suggestions": {
        "name": "الاقتراحات",
        "icon": "💡",
    },
    "notifications": {
        "name": "الإشعارات",
        "icon": "🔔",
    },
    "laws": {
        "name": "القوانين",
        "icon": "📜",
    },
    "logs": {
        "name": "اللوقات",
        "icon": "🧾",
    },
    "replies": {
        "name": "الردود",
        "icon": "💬",
    },
    "shortcuts": {
        "name": "الاختصارات",
        "icon": "⚡",
    },
}


# =========================================================
# PERMISSIONS
# =========================================================

PERMISSIONS = {
    "dashboard.view": "عرض لوحة التحكم",

    "bots.view": "عرض البوتات",
    "bots.manage": "إدارة البوتات",

    "roles.view": "عرض رتب لوحة التحكم",
    "roles.manage": "إدارة رتب لوحة التحكم",

    "owner.manage": "إدارة المالك",

    "moderation.view": "عرض الإدارة",
    "moderation.manage": "إدارة الإدارة",

    "welcome.view": "عرض الترحيب",
    "welcome.manage": "إدارة الترحيب",

    "levels.view": "عرض اللفلات",
    "levels.manage": "إدارة اللفلات",

    "points.view": "عرض النقاط",
    "points.manage": "إدارة النقاط",

    "tickets.view": "عرض التذاكر",
    "tickets.manage": "إدارة التذاكر",

    "applications.view": "عرض التقديمات",
    "applications.manage": "إدارة التقديمات",

    "suggestions.view": "عرض الاقتراحات",
    "suggestions.manage": "إدارة الاقتراحات",

    "notifications.view": "عرض الإشعارات",
    "notifications.manage": "إدارة الإشعارات",

    "laws.view": "عرض القوانين",
    "laws.manage": "إدارة القوانين",

    "logs.view": "عرض اللوقات",
    "logs.manage": "إدارة اللوقات",

    "replies.view": "عرض الردود",
    "replies.manage": "إدارة الردود",

    "shortcuts.view": "عرض الاختصارات",
    "shortcuts.manage": "إدارة الاختصارات",
}


# =========================================================
# DATABASE
# =========================================================

def get_db():
    db = sqlite3.connect(DB_FILE)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            permissions TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id TEXT UNIQUE NOT NULL,
            username TEXT,
            role_id INTEGER,
            created_at TEXT NOT NULL
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_number INTEGER NOT NULL,
            system_id TEXT NOT NULL,
            settings TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL,
            UNIQUE(bot_number, system_id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    db.commit()
    db.close()


# =========================================================
# HELPERS
# =========================================================

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def json_load(value, fallback=None):
    if fallback is None:
        fallback = {}

    try:
        return json.loads(value)
    except Exception:
        return fallback


def get_setting(key, default=None):
    db = get_db()

    row = db.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,)
    ).fetchone()

    db.close()

    if not row:
        return default

    return row["value"]


def set_setting(key, value):
    db = get_db()

    db.execute("""
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
    """, (key, str(value)))

    db.commit()
    db.close()


def clean_bot_number(value):
    try:
        number = int(value)
        if number < 1:
            return None
        return number
    except Exception:
        return None


# =========================================================
# BOT TOKEN DISCOVERY
# =========================================================

def get_bot_tokens():
    """
    Automatically finds:

    BOT_TOKEN_1
    BOT_TOKEN_2
    BOT_TOKEN_3
    ...

    No fixed maximum.
    """

    tokens = []

    for key, value in os.environ.items():
        if not value:
            continue

        match = re.fullmatch(
            r"BOT_TOKEN_(\d+)",
            key.upper()
        )

        if not match:
            continue

        number = int(match.group(1))

        tokens.append({
            "number": number,
            "env": key,
            "token": value.strip(),
        })

    tokens.sort(
        key=lambda item: item["number"]
    )

    return tokens


def get_token_for_bot(bot_number):
    bot_number = clean_bot_number(bot_number)

    if bot_number is None:
        return None

    for bot in get_bot_tokens():
        if bot["number"] == bot_number:
            return bot["token"]

    return None


# =========================================================
# DISCORD REQUEST
# =========================================================

def discord_headers(token):
    return {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "CT-Dashboard/2.0",
    }


def discord_bot_info(token):
    try:
        response = requests.get(
            f"{DISCORD_API}/users/@me",
            headers=discord_headers(token),
            timeout=10,
        )

        if response.status_code != 200:
            return {
                "ok": False,
                "status": response.status_code,
                "error": response.text[:500],
            }

        data = response.json()

        avatar = data.get("avatar")

        avatar_url = None

        if avatar:
            avatar_url = (
                f"https://cdn.discordapp.com/avatars/"
                f"{data['id']}/{avatar}.png"
            )

        return {
            "ok": True,
            "id": data.get("id"),
            "username": data.get("username"),
            "global_name": data.get("global_name"),
            "display_name": (
                data.get("global_name")
                or data.get("username")
                or "Bot"
            ),
            "avatar": avatar_url,
        }

    except requests.RequestException as exc:
        return {
            "ok": False,
            "error": str(exc),
        }


def discord_get_bot_guilds(token):
    try:
        response = requests.get(
            f"{DISCORD_API}/users/@me/guilds",
            headers=discord_headers(token),
            timeout=10,
        )

        if response.status_code != 200:
            return []

        return response.json()

    except requests.RequestException:
        return []


# =========================================================
# GET ALL CT BOTS
# =========================================================

def get_all_bots():
    """
    Returns only configured bots that are inside CT_GUILD_ID.

    Supports unlimited BOT_TOKEN_N variables.
    """

    bots = []

    if not CT_GUILD_ID:
        return bots

    for item in get_bot_tokens():
        number = item["number"]
        token = item["token"]

        info = discord_bot_info(token)

        if not info.get("ok"):
            bots.append({
                "number": number,
                "name": f"Bot {number}",
                "username": None,
                "id": None,
                "avatar": None,
                "online": False,
                "valid_token": False,
                "in_ct": False,
                "error": info.get(
                    "error",
                    "فشل الاتصال مع Discord"
                ),
            })
            continue

        guilds = discord_get_bot_guilds(token)

        in_ct = any(
            str(guild.get("id")) == CT_GUILD_ID
            for guild in guilds
        )

        # Only show bots inside CT.
        if not in_ct:
            continue

        bots.append({
            "number": number,
            "name": info.get("display_name"),
            "username": info.get("username"),
            "id": info.get("id"),
            "avatar": info.get("avatar"),
            "online": True,
            "valid_token": True,
            "in_ct": True,
        })

    return bots


# =========================================================
# OAUTH
# =========================================================

def discord_exchange_code(code):
    try:
        response = requests.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": DISCORD_CLIENT_ID,
                "client_secret": DISCORD_CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": DISCORD_REDIRECT_URI,
            },
            headers={
                "Content-Type": (
                    "application/x-www-form-urlencoded"
                )
            },
            timeout=10,
        )

        if response.status_code != 200:
            return {
                "ok": False,
                "error": response.text[:1000],
            }

        return {
            "ok": True,
            **response.json(),
        }

    except requests.RequestException as exc:
        return {
            "ok": False,
            "error": str(exc),
        }


def discord_get_user(access_token):
    try:
        response = requests.get(
            f"{DISCORD_API}/users/@me",
            headers={
                "Authorization": f"Bearer {access_token}"
            },
            timeout=10,
        )

        if response.status_code != 200:
            return {
                "ok": False,
                "error": response.text[:500],
            }

        return {
            "ok": True,
            **response.json(),
        }

    except requests.RequestException as exc:
        return {
            "ok": False,
            "error": str(exc),
        }


def discord_get_user_guilds(access_token):
    try:
        response = requests.get(
            f"{DISCORD_API}/users/@me/guilds",
            headers={
                "Authorization": f"Bearer {access_token}"
            },
            timeout=10,
        )

        if response.status_code != 200:
            return {
                "ok": False,
                "guilds": [],
                "error": response.text[:500],
            }

        return {
            "ok": True,
            "guilds": response.json(),
        }

    except requests.RequestException as exc:
        return {
            "ok": False,
            "guilds": [],
            "error": str(exc),
        }


# =========================================================
# CT SERVER ADMIN CHECK
# =========================================================

def find_admin_ct_guild(user_guilds):
    """
    Checks ONE fixed server:

    CT_GUILD_ID

    User must have Administrator permission there.
    """

    if not CT_GUILD_ID:
        return {
            "ok": False,
            "error": "CT_GUILD_ID غير مضبوط في Render",
        }

    for guild in user_guilds:

        if str(guild.get("id", "")) != CT_GUILD_ID:
            continue

        permissions = guild.get(
            "permissions",
            "0"
        )

        try:
            permissions = int(permissions)
        except Exception:
            permissions = 0

        if permissions & ADMINISTRATOR_PERMISSION:
            return {
                "ok": True,
                "guild_id": CT_GUILD_ID,
                "guild_name": guild.get(
                    "name",
                    "CT"
                ),
                "permissions": permissions,
            }

        return {
            "ok": False,
            "error": "يجب أن تملك Administrator في سيرفر CT",
        }

    return {
        "ok": False,
        "error": "يجب أن تكون موجودًا في سيرفر CT",
    }


# =========================================================
# SESSION / SECURITY
# =========================================================

def is_logged_in():
    return bool(
        session.get("logged_in", False)
    )


def current_is_owner():
    if not is_logged_in():
        return False

    return bool(
        session.get("discord_admin", False)
    )


def require_login():
    if not is_logged_in():
        return jsonify({
            "ok": False,
            "error": "يجب تسجيل الدخول عبر Discord",
        }), 401

    if not session.get(
        "discord_admin",
        False
    ):
        session.clear()

        return jsonify({
            "ok": False,
            "error": (
                "ليس لديك صلاحية Administrator "
                "في سيرفر CT"
            ),
        }), 403

    return None


def has_permission(permission):
    """
    Discord Administrators are allowed to manage
    the dashboard.

    Custom dashboard roles can be added later
    without changing the authentication system.
    """

    if not is_logged_in():
        return False

    if not session.get(
        "discord_admin",
        False
    ):
        return False

    return True


def permission_error(permission):
    return jsonify({
        "ok": False,
        "error": (
            "ليس لديك صلاحية لهذا الإجراء"
        ),
        "permission": permission,
    }), 403


# =========================================================
# DASHBOARD ROLE HELPERS
# =========================================================

def get_dashboard_role(role_id):
    db = get_db()

    row = db.execute(
        """
        SELECT *
        FROM dashboard_roles
        WHERE id = ?
        """,
        (role_id,)
    ).fetchone()

    db.close()

    return row


def get_dashboard_user(discord_id):
    db = get_db()

    row = db.execute(
        """
        SELECT *
        FROM dashboard_users
        WHERE discord_id = ?
        """,
        (str(discord_id),)
    ).fetchone()

    db.close()

    return row


def get_user_permissions(discord_id):
    """
    Administrator always has full dashboard access.
    """

    if str(session.get("discord_id", "")) == str(discord_id):
        if session.get("discord_admin", False):
            return list(PERMISSIONS.keys())

    user = get_dashboard_user(discord_id)

    if not user:
        return []

    if not user["role_id"]:
        return []

    role = get_dashboard_role(
        user["role_id"]
    )

    if not role:
        return []

    return json_load(
        role["permissions"],
        []
    )


# =========================================================
# ROUTES - MAIN PAGES
# =========================================================

@app.route("/")
def index():
    return render_template(
        "index.html",
        app_name=APP_NAME,
        version=VERSION,
    )


@app.route("/server")
def server():
    if not is_logged_in():
        return redirect(
            url_for("index")
        )

    if not session.get(
        "discord_admin",
        False
    ):
        session.clear()
        return redirect(
            url_for("index")
        )

    return render_template(
        "server.html",
        app_name=APP_NAME,
        version=VERSION,
    )


# =========================================================
# LOGIN
# =========================================================

@app.route("/login")
def login():
    required = {
        "DISCORD_CLIENT_ID": DISCORD_CLIENT_ID,
        "DISCORD_CLIENT_SECRET": DISCORD_CLIENT_SECRET,
        "DISCORD_REDIRECT_URI": DISCORD_REDIRECT_URI,
        "CT_GUILD_ID": CT_GUILD_ID,
    }

    missing = [
        name
        for name, value in required.items()
        if not value
    ]

    if missing:
        return jsonify({
            "ok": False,
            "error": (
                "متغيرات Render ناقصة"
            ),
            "missing": missing,
        }), 500

    state = secrets.token_urlsafe(32)

    session["oauth_state"] = state

    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
        "prompt": "consent",
    }

    discord_url = (
        "https://discord.com/oauth2/authorize?"
        + urlencode(params)
    )

    return redirect(discord_url)


# =========================================================
# LOGIN CALLBACK
# =========================================================

@app.route("/login/callback")
def login_callback():

    error = request.args.get("error")

    if error:
        return jsonify({
            "ok": False,
            "error": (
                "تم إلغاء تسجيل الدخول أو رفض Discord الطلب"
            ),
            "discord_error": error,
        }), 403

    code = request.args.get("code")
    state = request.args.get("state")

    saved_state = session.get(
        "oauth_state"
    )

    if not code:
        return jsonify({
            "ok": False,
            "error": "لم يتم استلام رمز تسجيل الدخول",
        }), 400

    if not state or state != saved_state:
        return jsonify({
            "ok": False,
            "error": "جلسة تسجيل الدخول غير صالحة",
        }), 400

    session.pop(
        "oauth_state",
        None
    )

    token_data = discord_exchange_code(
        code
    )

    if not token_data.get("ok"):
        return jsonify({
            "ok": False,
            "error": "فشل تسجيل الدخول عبر Discord",
            "details": token_data.get(
                "error",
                "Unknown error"
            ),
        }), 502

    access_token = token_data.get(
        "access_token"
    )

    if not access_token:
        return jsonify({
            "ok": False,
            "error": "Discord لم يرجع Access Token",
        }), 502

    user = discord_get_user(
        access_token
    )

    if not user.get("ok"):
        return jsonify({
            "ok": False,
            "error": "تعذر قراءة حساب Discord",
        }), 502

    guild_result = discord_get_user_guilds(
        access_token
    )

    if not guild_result.get("ok"):
        return jsonify({
            "ok": False,
            "error": (
                "تعذر قراءة السيرفرات من Discord"
            ),
        }), 502

    admin_result = find_admin_ct_guild(
        guild_result.get(
            "guilds",
            []
        )
    )

    if not admin_result.get("ok"):
        session.clear()

        return jsonify({
            "ok": False,
            "error": admin_result.get(
                "error",
                "ليس لديك صلاحية الدخول"
            ),
        }), 403

    discord_id = user.get("id")

    username = (
        user.get("global_name")
        or user.get("username")
        or "Discord User"
    )

    avatar_hash = user.get(
        "avatar"
    )

    avatar_url = None

    if avatar_hash and discord_id:
        avatar_url = (
            "https://cdn.discordapp.com/avatars/"
            f"{discord_id}/{avatar_hash}.png"
        )

    # -----------------------------------------------------
    # Save user
    # -----------------------------------------------------

    db = get_db()

    existing = db.execute(
        """
        SELECT id
        FROM dashboard_users
        WHERE discord_id = ?
        """,
        (str(discord_id),)
    ).fetchone()

    if existing:
        db.execute(
            """
            UPDATE dashboard_users
            SET username = ?
            WHERE discord_id = ?
            """,
            (
                username,
                str(discord_id),
            )
        )
    else:
        db.execute(
            """
            INSERT INTO dashboard_users
            (
                discord_id,
                username,
                role_id,
                created_at
            )
            VALUES (?, ?, NULL, ?)
            """,
            (
                str(discord_id),
                username,
                utc_now(),
            )
        )

    db.commit()
    db.close()

    # -----------------------------------------------------
    # Session
    # -----------------------------------------------------

    session.clear()

    session["logged_in"] = True
    session["owner"] = True
    session["discord_admin"] = True

    session["discord_id"] = str(
        discord_id
    )

    session["username"] = username

    session["role_id"] = None

    session["discord_avatar"] = avatar_url

    session["ct_guild_id"] = (
        admin_result["guild_id"]
    )

    session["ct_guild_name"] = (
        admin_result["guild_name"]
    )

    return redirect(
        url_for("server")
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():
    session.clear()

    return redirect(
        url_for("index")
    )


# =========================================================
# API - ME
# =========================================================

@app.route("/api/me")
def api_me():

    protection = require_login()

    if protection:
        return protection

    return jsonify({
        "ok": True,
        "user": {
            "discord_id": session.get(
                "discord_id"
            ),
            "username": session.get(
                "username"
            ),
            "avatar": session.get(
                "discord_avatar"
            ),
            "administrator": bool(
                session.get(
                    "discord_admin",
                    False
                )
            ),
        },
        "server": {
            "id": session.get(
                "ct_guild_id"
            ),
            "name": session.get(
                "ct_guild_name"
            ),
        },
        "app": {
            "name": APP_NAME,
            "version": VERSION,
        },
    })


# =========================================================
# API - BOTS
# =========================================================

@app.route("/api/bots")
def api_bots():

    protection = require_login()

    if protection:
        return protection

    if not has_permission(
        "bots.view"
    ):
        return permission_error(
            "bots.view"
        )

    return jsonify({
        "ok": True,
        "server": {
            "id": CT_GUILD_ID,
            "name": session.get(
                "ct_guild_name",
                "CT"
            ),
        },
        "bots": get_all_bots(),
    })


@app.route(
    "/api/bots/<int:bot_number>"
)
def api_bot(bot_number):

    protection = require_login()

    if protection:
        return protection

    if not has_permission(
        "bots.view"
    ):
        return permission_error(
            "bots.view"
        )

    token = get_token_for_bot(
        bot_number
    )

    if not token:
        return jsonify({
            "ok": False,
            "error": "البوت غير موجود",
        }), 404

    info = discord_bot_info(
        token
    )

    if not info.get("ok"):
        return jsonify({
            "ok": False,
            "error": (
                "تعذر الحصول على معلومات البوت"
            ),
        }), 502

    guilds = discord_get_bot_guilds(
        token
    )

    in_ct = any(
        str(guild.get("id")) == CT_GUILD_ID
        for guild in guilds
    )

    if not in_ct:
        return jsonify({
            "ok": False,
            "error": (
                "هذا البوت غير موجود في سيرفر CT"
            ),
        }), 403

    return jsonify({
        "ok": True,
        "bot": {
            "number": bot_number,
            **info,
            "in_ct": True,
        },
    })


# =========================================================
# API - SYSTEMS
# =========================================================

@app.route("/api/systems")
def api_systems():

    protection = require_login()

    if protection:
        return protection

    systems = []

    for system_id, system in SYSTEMS.items():

        systems.append({
            "id": system_id,
            "name": system["name"],
            "icon": system["icon"],
            "view_permission": (
                f"{system_id}.view"
            ),
            "manage_permission": (
                f"{system_id}.manage"
            ),
        })

    return jsonify({
        "ok": True,
        "systems": systems,
    })


# =========================================================
# API - GET SYSTEM SETTINGS
# =========================================================

@app.route(
    "/api/bots/<int:bot_number>/systems/<system_id>",
    methods=["GET"]
)
def api_get_system(
    bot_number,
    system_id
):

    protection = require_login()

    if protection:
        return protection

    if system_id not in SYSTEMS:
        return jsonify({
            "ok": False,
            "error": "النظام غير موجود",
        }), 404

    permission = (
        f"{system_id}.view"
    )

    if not has_permission(permission):
        return permission_error(
            permission
        )

    token = get_token_for_bot(
        bot_number
    )

    if not token:
        return jsonify({
            "ok": False,
            "error": "البوت غير موجود",
        }), 404

    # Verify bot is in CT.
    guilds = discord_get_bot_guilds(
        token
    )

    in_ct = any(
        str(guild.get("id")) == CT_GUILD_ID
        for guild in guilds
    )

    if not in_ct:
        return jsonify({
            "ok": False,
            "error": (
                "البوت غير موجود في سيرفر CT"
            ),
        }), 403

    db = get_db()

    row = db.execute(
        """
        SELECT settings
        FROM system_settings
        WHERE bot_number = ?
        AND system_id = ?
        """,
        (
            bot_number,
            system_id,
        )
    ).fetchone()

    db.close()

    settings = {}

    if row:
        settings = json_load(
            row["settings"],
            {}
        )

    return jsonify({
        "ok": True,
        "bot_number": bot_number,
        "system": {
            "id": system_id,
            "name": SYSTEMS[
                system_id
            ]["name"],
            "icon": SYSTEMS[
                system_id
            ]["icon"],
        },
        "settings": settings,
    })


# =========================================================
# API - APPLY SETTINGS
# =========================================================

@app.route(
    "/api/apply",
    methods=["POST"]
)
def api_apply():

    protection = require_login()

    if protection:
        return protection

    data = request.get_json(
        silent=True
    ) or {}

    bots = data.get(
        "bots",
        []
    )

    system_id = data.get(
        "system"
    )

    settings = data.get(
        "settings",
        {}
    )

    if not isinstance(
        bots,
        list
    ):
        return jsonify({
            "ok": False,
            "error": (
                "bots يجب أن تكون قائمة"
            ),
        }), 400

    if not system_id:
        return jsonify({
            "ok": False,
            "error": "يجب تحديد النظام",
        }), 400

    if system_id not in SYSTEMS:
        return jsonify({
            "ok": False,
            "error": "النظام غير موجود",
        }), 404

    permission = (
        f"{system_id}.manage"
    )

    if not has_permission(
        permission
    ):
        return permission_error(
            permission
        )

    if not bots:
        return jsonify({
            "ok": False,
            "error": (
                "حدد بوتًا واحدًا على الأقل"
            ),
        }), 400

    db = get_db()

    success = []
    failed = []

    for raw_number in bots:

        bot_number = clean_bot_number(
            raw_number
        )

        if bot_number is None:
            failed.append({
                "bot": raw_number,
                "error": "رقم بوت غير صالح",
            })
            continue

        token = get_token_for_bot(
            bot_number
        )

        if not token:
            failed.append({
                "bot": bot_number,
                "error": "البوت غير موجود",
            })
            continue

        # Make sure the bot belongs to CT.
        guilds = discord_get_bot_guilds(
            token
        )

        in_ct = any(
            str(guild.get("id"))
            == CT_GUILD_ID
            for guild in guilds
        )

        if not in_ct:
            failed.append({
                "bot": bot_number,
                "error": (
                    "البوت غير موجود في سيرفر CT"
                ),
            })
            continue

        try:
            settings_json = json.dumps(
                settings,
                ensure_ascii=False
            )

            db.execute(
                """
                INSERT INTO system_settings
                (
                    bot_number,
                    system_id,
                    settings,
                    updated_at
                )
                VALUES (?, ?, ?, ?)

                ON CONFLICT(
                    bot_number,
                    system_id
                )
                DO UPDATE SET
                    settings = excluded.settings,
                    updated_at = excluded.updated_at
                """,
                (
                    bot_number,
                    system_id,
                    settings_json,
                    utc_now(),
                )
            )

            success.append(
                bot_number
            )

        except Exception as exc:
            failed.append({
                "bot": bot_number,
                "error": str(exc),
            })

    db.commit()
    db.close()

    return jsonify({
        "ok": len(success) > 0,
        "system": system_id,
        "success": success,
        "failed": failed,
        "message": (
            f"تم تطبيق الإعدادات على "
            f"{len(success)} بوت"
        ),
    })


# =========================================================
# OWNER - ROLES
# =========================================================

@app.route(
    "/api/owner/roles",
    methods=["GET"]
)
def api_owner_roles():

    protection = require_login()

    if protection:
        return protection

    if not has_permission(
        "roles.view"
    ):
        return permission_error(
            "roles.view"
        )

    db = get_db()

    rows = db.execute(
        """
        SELECT *
        FROM dashboard_roles
        ORDER BY id ASC
        """
    ).fetchall()

    db.close()

    roles = []

    for row in rows:
        roles.append({
            "id": row["id"],
            "name": row["name"],
            "permissions": json_load(
                row["permissions"],
                []
            ),
            "created_at": row[
                "created_at"
            ],
        })

    return jsonify({
        "ok": True,
        "roles": roles,
    })


# =========================================================
# OWNER - CREATE ROLE
# =========================================================

@app.route(
    "/api/owner/roles",
    methods=["POST"]
)
def api_owner_create_role():

    protection = require_login()

    if protection:
        return protection

    if not has_permission(
        "roles.manage"
    ):
        return permission_error(
            "roles.manage"
        )

    data = request.get_json(
        silent=True
    ) or {}

    name = str(
        data.get(
            "name",
            ""
        )
    ).strip()

    permissions = data.get(
        "permissions",
        []
    )

    if not name:
        return jsonify({
            "ok": False,
            "error": "اكتب اسم الرتبة",
        }), 400

    if not isinstance(
        permissions,
        list
    ):
        return jsonify({
            "ok": False,
            "error": (
                "permissions يجب أن تكون قائمة"
            ),
        }), 400

    valid_permissions = [
        permission
        for permission in permissions
        if permission in PERMISSIONS
    ]

    db = get_db()

    cursor = db.execute(
        """
        INSERT INTO dashboard_roles
        (
            name,
            permissions,
            created_at
        )
        VALUES (?, ?, ?)
        """,
        (
            name,
            json.dumps(
                valid_permissions,
                ensure_ascii=False
            ),
            utc_now(),
        )
    )

    db.commit()

    role_id = cursor.lastrowid

    db.close()

    return jsonify({
        "ok": True,
        "role": {
            "id": role_id,
            "name": name,
            "permissions": valid_permissions,
        },
    }), 201


# =========================================================
# OWNER - UPDATE ROLE
# =========================================================

@app.route(
    "/api/owner/roles/<int:role_id>",
    methods=["PUT"]
)
def api_owner_update_role(
    role_id
):

    protection = require_login()

    if protection:
        return protection

    if not has_permission(
        "roles.manage"
    ):
        return permission_error(
            "roles.manage"
        )

    data = request.get_json(
        silent=True
    ) or {}

    name = data.get(
        "name"
    )

    permissions = data.get(
        "permissions"
    )

    role = get_dashboard_role(
        role_id
    )

    if not role:
        return jsonify({
            "ok": False,
            "error": "الرتبة غير موجودة",
        }), 404

    if name is None:
        name = role["name"]

    name = str(name).strip()

    if not name:
        return jsonify({
            "ok": False,
            "error": "اسم الرتبة لا يمكن أن يكون فارغًا",
        }), 400

    if permissions is None:
        permissions = json_load(
            role["permissions"],
            []
        )

    if not isinstance(
        permissions,
        list
    ):
        return jsonify({
            "ok": False,
            "error": "الصلاحيات غير صحيحة",
        }), 400

    permissions = [
        permission
        for permission in permissions
        if permission in PERMISSIONS
    ]

    db = get_db()

    db.execute(
        """
        UPDATE dashboard_roles
        SET name = ?,
            permissions = ?
        WHERE id = ?
        """,
        (
            name,
            json.dumps(
                permissions,
                ensure_ascii=False
            ),
            role_id,
        )
    )

    db.commit()
    db.close()

    return jsonify({
        "ok": True,
        "role": {
            "id": role_id,
            "name": name,
            "permissions": permissions,
        },
    })


# =========================================================
# OWNER - DELETE ROLE
# =========================================================

@app.route(
    "/api/owner/roles/<int:role_id>",
    methods=["DELETE"]
)
def api_owner_delete_role(
    role_id
):

    protection = require_login()

    if protection:
        return protection

    if not has_permission(
        "roles.manage"
    ):
        return permission_error(
            "roles.manage"
        )

    role = get_dashboard_role(
        role_id
    )

    if not role:
        return jsonify({
            "ok": False,
            "error": "الرتبة غير موجودة",
        }), 404

    db = get_db()

    # Remove role from users first.
    db.execute(
        """
        UPDATE dashboard_users
        SET role_id = NULL
        WHERE role_id = ?
        """,
        (role_id,)
    )

    db.execute(
        """
        DELETE FROM dashboard_roles
        WHERE id = ?
        """,
        (role_id,)
    )

    db.commit()
    db.close()

    return jsonify({
        "ok": True,
        "message": "تم حذف الرتبة",
    })


# =========================================================
# OWNER - PERMISSIONS
# =========================================================

@app.route(
    "/api/owner/permissions"
)
def api_owner_permissions():

    protection = require_login()

    if protection:
        return protection

    if not has_permission(
        "roles.view"
    ):
        return permission_error(
            "roles.view"
        )

    grouped = {}

    for permission, description in PERMISSIONS.items():

        system = permission.split(
            ".",
            1
        )[0]

        if system not in grouped:
            grouped[system] = []

        grouped[system].append({
            "permission": permission,
            "description": description,
        })

    return jsonify({
        "ok": True,
        "permissions": PERMISSIONS,
        "grouped": grouped,
    })


# =========================================================
# OWNER - USERS
# =========================================================

@app.route(
    "/api/owner/users",
    methods=["GET"]
)
def api_owner_users():

    protection = require_login()

    if protection:
        return protection

    if not has_permission(
        "roles.view"
    ):
        return permission_error(
            "roles.view"
        )

    db = get_db()

    rows = db.execute(
        """
        SELECT
            u.id,
            u.discord_id,
            u.username,
            u.role_id,
            u.created_at,
            r.name AS role_name
        FROM dashboard_users u
        LEFT JOIN dashboard_roles r
            ON u.role_id = r.id
        ORDER BY u.id ASC
        """
    ).fetchall()

    db.close()

    users = []

    for row in rows:
        users.append({
            "id": row["id"],
            "discord_id": row[
                "discord_id"
            ],
            "username": row[
                "username"
            ],
            "role_id": row[
                "role_id"
            ],
            "role_name": row[
                "role_name"
            ],
            "created_at": row[
                "created_at"
            ],
        })

    return jsonify({
        "ok": True,
        "users": users,
    })


# =========================================================
# OWNER - ASSIGN ROLE TO USER
# =========================================================

@app.route(
    "/api/owner/users",
    methods=["POST"]
)
def api_owner_assign_user():

    protection = require_login()

    if protection:
        return protection

    if not has_permission(
        "roles.manage"
    ):
        return permission_error(
            "roles.manage"
        )

    data = request.get_json(
        silent=True
    ) or {}

    discord_id = str(
        data.get(
            "discord_id",
            ""
        )
    ).strip()

    username = str(
        data.get(
            "username",
            ""
        )
    ).strip()

    role_id = data.get(
        "role_id"
    )

    if not discord_id:
        return jsonify({
            "ok": False,
            "error": "يجب تحديد Discord ID",
        }), 400

    if role_id is not None:
        try:
            role_id = int(role_id)
        except Exception:
            return jsonify({
                "ok": False,
                "error": "role_id غير صالح",
            }), 400

        role = get_dashboard_role(
            role_id
        )

        if not role:
            return jsonify({
                "ok": False,
                "error": "الرتبة غير موجودة",
            }), 404

    db = get_db()

    existing = db.execute(
        """
        SELECT id
        FROM dashboard_users
        WHERE discord_id = ?
        """,
        (discord_id,)
    ).fetchone()

    if existing:

        db.execute(
            """
            UPDATE dashboard_users
            SET username = ?,
                role_id = ?
            WHERE discord_id = ?
            """,
            (
                username,
                role_id,
                discord_id,
            )
        )

    else:

        db.execute(
            """
            INSERT INTO dashboard_users
            (
                discord_id,
                username,
                role_id,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                discord_id,
                username,
                role_id,
                utc_now(),
            )
        )

    db.commit()
    db.close()

    return jsonify({
        "ok": True,
        "message": "تم تحديث صلاحيات المستخدم",
    })


# =========================================================
# OWNER - DELETE USER
# =========================================================

@app.route(
    "/api/owner/users/<int:user_id>",
    methods=["DELETE"]
)
def api_owner_delete_user(
    user_id
):

    protection = require_login()

    if protection:
        return protection

    if not has_permission(
        "roles.manage"
    ):
        return permission_error(
            "roles.manage"
        )

    db = get_db()

    row = db.execute(
        """
        SELECT discord_id
        FROM dashboard_users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    if not row:
        db.close()

        return jsonify({
            "ok": False,
            "error": "المستخدم غير موجود",
        }), 404

    # Never delete the current authenticated user
    # accidentally.
    if str(row["discord_id"]) == str(
        session.get("discord_id")
    ):
        db.close()

        return jsonify({
            "ok": False,
            "error": (
                "لا يمكنك حذف حسابك الحالي"
            ),
        }), 400

    db.execute(
        """
        DELETE FROM dashboard_users
        WHERE id = ?
        """,
        (user_id,)
    )

    db.commit()
    db.close()

    return jsonify({
        "ok": True,
        "message": "تم حذف المستخدم",
    })


# =========================================================
# SECTIONS
# =========================================================

@app.route(
    "/api/sections",
    methods=["GET"]
)
def api_sections():

    protection = require_login()

    if protection:
        return protection

    db = get_db()

    rows = db.execute(
        """
        SELECT *
        FROM sections
        ORDER BY id ASC
        """
    ).fetchall()

    db.close()

    sections = []

    for row in rows:
        sections.append({
            "id": row["id"],
            "name": row["name"],
            "description": row[
                "description"
            ],
            "enabled": bool(
                row["enabled"]
            ),
            "created_at": row[
                "created_at"
            ],
        })

    return jsonify({
        "ok": True,
        "sections": sections,
    })


@app.route(
    "/api/sections",
    methods=["POST"]
)
def api_create_section():

    protection = require_login()

    if protection:
        return protection

    if not has_permission(
        "owner.manage"
    ):
        return permission_error(
            "owner.manage"
        )

    data = request.get_json(
        silent=True
    ) or {}

    name = str(
        data.get(
            "name",
            ""
        )
    ).strip()

    description = str(
        data.get(
            "description",
            ""
        )
    ).strip()

    if not name:
        return jsonify({
            "ok": False,
            "error": "اكتب اسم القسم",
        }), 400

    db = get_db()

    cursor = db.execute(
        """
        INSERT INTO sections
        (
            name,
            description,
            enabled,
            created_at
        )
        VALUES (?, ?, 1, ?)
        """,
        (
            name,
            description,
            utc_now(),
        )
    )

    db.commit()

    section_id = cursor.lastrowid

    db.close()

    return jsonify({
        "ok": True,
        "section": {
            "id": section_id,
            "name": name,
            "description": description,
            "enabled": True,
        },
    }), 201


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():

    return jsonify({
        "ok": True,
        "service": APP_NAME,
        "version": VERSION,
        "status": "online",
        "guild_configured": bool(
            CT_GUILD_ID
        ),
        "bots_configured": len(
            get_bot_tokens()
        ),
    })


# =========================================================
# API STATUS
# =========================================================

@app.route("/api/status")
def api_status():

    protection = require_login()

    if protection:
        return protection

    bots = get_all_bots()

    return jsonify({
        "ok": True,
        "service": APP_NAME,
        "version": VERSION,
        "server": {
            "id": CT_GUILD_ID,
            "name": session.get(
                "ct_guild_name",
                "CT"
            ),
        },
        "bots": {
            "configured": len(
                get_bot_tokens()
            ),
            "in_ct": len(
                bots
            ),
        },
        "systems": len(
            SYSTEMS
        ),
    })


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def not_found(error):

    if request.path.startswith(
        "/api/"
    ):
        return jsonify({
            "ok": False,
            "error": "المسار غير موجود",
        }), 404

    return (
        "CT Dashboard - الصفحة غير موجودة",
        404
    )


@app.errorhandler(500)
def internal_error(error):

    if request.path.startswith(
        "/api/"
    ):
        return jsonify({
            "ok": False,
            "error": (
                "حدث خطأ داخلي في الخادم"
            ),
        }), 500

    return (
        "CT Dashboard - حدث خطأ داخلي",
        500
    )


# =========================================================
# STARTUP
# =========================================================

init_db()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        host=HOST,
        port=PORT,
        debug=False,
    )

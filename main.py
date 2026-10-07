# =========================================================
# CT DASHBOARD
# Main Server - Full Stable Version
# Welcome Editor + Touch + Image Upload + Save
# =========================================================

import os
import re
import json
import base64
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
    send_file,
)

from werkzeug.middleware.proxy_fix import ProxyFix
from io import BytesIO


# =========================================================
# SETTINGS
# =========================================================

APP_NAME = "CT"
VERSION = "3.0.0"

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "10000"))

DB_FILE = "ct_dashboard.db"

DISCORD_API = "https://discord.com/api/v10"

ADMINISTRATOR_PERMISSION = 1 << 3

MAX_IMAGE_SIZE = 5 * 1024 * 1024

ALLOWED_IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}


# =========================================================
# DISCORD OAUTH
# =========================================================

DISCORD_CLIENT_ID = os.getenv(
    "DISCORD_CLIENT_ID",
    ""
).strip()

DISCORD_CLIENT_SECRET = os.getenv(
    "DISCORD_CLIENT_SECRET",
    ""
).strip()

DISCORD_REDIRECT_URI = os.getenv(
    "DISCORD_REDIRECT_URI",
    ""
).strip()


# =========================================================
# CT SERVER
# =========================================================

CT_GUILD_ID = os.getenv(
    "CT_GUILD_ID",
    ""
).strip()


# =========================================================
# FLASK SECRET
# =========================================================

SECRET_KEY = os.getenv(
    "CT_SECRET_KEY",
    ""
).strip()

if not SECRET_KEY:
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

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1,
    x_port=1,
)

app.config.update(
    SECRET_KEY=SECRET_KEY,
    SESSION_COOKIE_NAME="ct_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_PATH="/",
    SESSION_REFRESH_EACH_REQUEST=True,
    MAX_CONTENT_LENGTH=MAX_IMAGE_SIZE + 1024 * 1024,
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
    db = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False,
    )

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

    # =====================================================
    # WELCOME ASSETS
    # =====================================================

    db.execute("""
        CREATE TABLE IF NOT EXISTS welcome_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_number INTEGER NOT NULL,
            asset_type TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            image_data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(bot_number, asset_type)
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


def clean_bot_number(value):

    try:
        number = int(value)

        if number < 1:
            return None

        return number

    except Exception:
        return None


def get_setting(key, default=None):

    db = get_db()

    row = db.execute(
        """
        SELECT value
        FROM settings
        WHERE key = ?
        """,
        (key,)
    ).fetchone()

    db.close()

    if not row:
        return default

    return row["value"]


def set_setting(key, value):

    db = get_db()

    db.execute(
        """
        INSERT INTO settings
        (key, value)
        VALUES (?, ?)

        ON CONFLICT(key)
        DO UPDATE SET
            value = excluded.value
        """,
        (
            key,
            str(value),
        )
    )

    db.commit()
    db.close()


def get_uploaded_asset(bot_number, asset_type="welcome_background"):

    db = get_db()

    row = db.execute(
        """
        SELECT *
        FROM welcome_assets
        WHERE bot_number = ?
        AND asset_type = ?
        """,
        (
            bot_number,
            asset_type,
        )
    ).fetchone()

    db.close()

    return row


# =========================================================
# BOT TOKEN DISCOVERY
# =========================================================

def get_bot_tokens():

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

        try:
            number = int(match.group(1))
        except Exception:
            continue

        if number < 1:
            continue

        token = value.strip()

        if not token:
            continue

        tokens.append({
            "number": number,
            "env": key,
            "token": token,
        })

    tokens.sort(
        key=lambda item: item["number"]
    )

    return tokens


def get_token_for_bot(bot_number):

    bot_number = clean_bot_number(
        bot_number
    )

    if bot_number is None:
        return None

    for bot in get_bot_tokens():

        if bot["number"] == bot_number:
            return bot["token"]

    return None


# =========================================================
# DISCORD HEADERS
# =========================================================

def discord_headers(token):

    return {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "CT-Dashboard/3.0",
    }


# =========================================================
# DISCORD BOT INFO
# =========================================================

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

        bot_id = data.get("id")
        avatar_hash = data.get("avatar")

        avatar_url = None

        if bot_id and avatar_hash:

            avatar_url = (
                "https://cdn.discordapp.com/avatars/"
                f"{bot_id}/{avatar_hash}.png"
            )

        return {
            "ok": True,
            "id": bot_id,
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


# =========================================================
# CHECK BOT IN CT
# =========================================================

def discord_bot_in_ct(token):

    if not CT_GUILD_ID:

        return {
            "ok": False,
            "in_ct": False,
            "error": "CT_GUILD_ID غير مضبوط",
        }

    try:

        response = requests.get(
            f"{DISCORD_API}/guilds/{CT_GUILD_ID}",
            headers=discord_headers(token),
            timeout=10,
        )

        if response.status_code == 200:

            guild = response.json()

            return {
                "ok": True,
                "in_ct": True,
                "guild": {
                    "id": guild.get("id"),
                    "name": guild.get("name", "CT"),
                    "icon": guild.get("icon"),
                },
            }

        if response.status_code == 404:

            return {
                "ok": True,
                "in_ct": False,
                "error": "البوت غير موجود في سيرفر CT",
            }

        if response.status_code == 403:

            return {
                "ok": True,
                "in_ct": True,
                "error": "البوت موجود في السيرفر لكن Discord رفض الوصول",
            }

        return {
            "ok": False,
            "in_ct": False,
            "status": response.status_code,
            "error": response.text[:500],
        }

    except requests.RequestException as exc:

        return {
            "ok": False,
            "in_ct": False,
            "error": str(exc),
        }


# =========================================================
# GET ALL BOTS
# =========================================================

def get_all_bots():

    bots = []

    configured = get_bot_tokens()

    if not CT_GUILD_ID:
        return bots

    for item in configured:

        number = item["number"]
        token = item["token"]

        info = discord_bot_info(token)

        if not info.get("ok"):
            continue

        ct_result = discord_bot_in_ct(token)

        if not ct_result.get("in_ct", False):
            continue

        bots.append({
            "number": number,
            "name": info.get("display_name"),
            "username": info.get("username"),
            "global_name": info.get("global_name"),
            "id": info.get("id"),
            "avatar": info.get("avatar"),
            "online": True,
            "valid_token": True,
            "in_ct": True,
        })

    return bots


# =========================================================
# DISCORD CHANNELS
# =========================================================

def discord_get_channels(token):

    if not CT_GUILD_ID:
        return {
            "ok": False,
            "channels": [],
            "error": "CT_GUILD_ID غير مضبوط",
        }

    try:

        response = requests.get(
            f"{DISCORD_API}/guilds/{CT_GUILD_ID}/channels",
            headers=discord_headers(token),
            timeout=10,
        )

        if response.status_code != 200:

            return {
                "ok": False,
                "channels": [],
                "error": response.text[:500],
            }

        channels = response.json()

        result = []

        # Discord channel types:
        # 0 = text
        # 5 = announcement
        # 10/11/12 = threads
        allowed_types = {0, 5}

        for channel in channels:

            channel_type = channel.get("type")

            if channel_type not in allowed_types:
                continue

            result.append({
                "id": channel.get("id"),
                "name": channel.get("name"),
                "type": channel_type,
                "parent_id": channel.get("parent_id"),
            })

        result.sort(
            key=lambda item: (
                item.get("name") or ""
            ).lower()
        )

        return {
            "ok": True,
            "channels": result,
        }

    except requests.RequestException as exc:

        return {
            "ok": False,
            "channels": [],
            "error": str(exc),
        }


# =========================================================
# OAUTH - EXCHANGE CODE
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
                "Content-Type":
                    "application/x-www-form-urlencoded"
            },
            timeout=15,
        )

        if response.status_code != 200:

            return {
                "ok": False,
                "error": response.text[:1000],
            }

        data = response.json()

        return {
            "ok": True,
            **data,
        }

    except requests.RequestException as exc:

        return {
            "ok": False,
            "error": str(exc),
        }


# =========================================================
# OAUTH - USER
# =========================================================

def discord_get_user(access_token):

    try:

        response = requests.get(
            f"{DISCORD_API}/users/@me",
            headers={
                "Authorization":
                    f"Bearer {access_token}"
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


# =========================================================
# OAUTH - USER GUILDS
# =========================================================

def discord_get_user_guilds(access_token):

    try:

        response = requests.get(
            f"{DISCORD_API}/users/@me/guilds",
            headers={
                "Authorization":
                    f"Bearer {access_token}"
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
# CHECK ADMINISTRATOR
# =========================================================

def find_admin_ct_guild(user_guilds):

    if not CT_GUILD_ID:

        return {
            "ok": False,
            "error":
                "CT_GUILD_ID غير مضبوط في Render",
        }

    for guild in user_guilds:

        if str(
            guild.get("id", "")
        ) != str(CT_GUILD_ID):

            continue

        permissions = guild.get(
            "permissions",
            "0"
        )

        try:
            permissions = int(
                permissions
            )
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
            "error":
                "يجب أن تملك Administrator في سيرفر CT",
        }

    return {
        "ok": False,
        "error":
            "يجب أن تكون موجودًا في سيرفر CT",
    }


# =========================================================
# SESSION
# =========================================================

def is_logged_in():

    return bool(
        session.get("logged_in", False)
        and session.get("discord_id")
    )


def current_is_owner():

    return bool(
        session.get(
            "discord_admin",
            False
        )
    )


def require_login():

    if not is_logged_in():

        return jsonify({
            "ok": False,
            "error":
                "يجب تسجيل الدخول عبر Discord",
            "login_url":
                url_for(
                    "login",
                    _external=True
                ),
        }), 401

    if not session.get(
        "discord_admin",
        False
    ):

        session.clear()

        return jsonify({
            "ok": False,
            "error":
                "ليس لديك صلاحية Administrator في سيرفر CT",
            "login_url":
                url_for(
                    "login",
                    _external=True
                ),
        }), 403

    return None


def has_permission(permission):

    if not is_logged_in():
        return False

    if session.get(
        "discord_admin",
        False
    ):
        return True

    return permission in get_user_permissions(
        session.get("discord_id")
    )


def permission_error(permission):

    return jsonify({
        "ok": False,
        "error":
            "ليس لديك صلاحية لهذا الإجراء",
        "permission":
            permission,
    }), 403


# =========================================================
# DASHBOARD ROLES
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

    if str(
        session.get(
            "discord_id",
            ""
        )
    ) == str(discord_id):

        if session.get(
            "discord_admin",
            False
        ):

            return list(
                PERMISSIONS.keys()
            )

    user = get_dashboard_user(
        discord_id
    )

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
# HOME
# =========================================================

@app.route("/")
def index():

    if is_logged_in():

        return redirect(
            url_for("server")
        )

    return render_template(
        "index.html",
        app_name=APP_NAME,
        version=VERSION,
    )


# =========================================================
# SERVER
# =========================================================

@app.route("/server")
def server():

    if not is_logged_in():

        return redirect(
            url_for("login")
        )

    if not session.get(
        "discord_admin",
        False
    ):

        session.clear()

        return redirect(
            url_for("login")
        )

    return render_template(
        "server.html",
        app_name=APP_NAME,
        version=VERSION,
        server_name=session.get(
            "ct_guild_name",
            "CT"
        ),
        systems=SYSTEMS,
    )


# =========================================================
# LOGIN
# =========================================================

@app.route("/login")
def login():

    missing = []

    if not DISCORD_CLIENT_ID:
        missing.append(
            "DISCORD_CLIENT_ID"
        )

    if not DISCORD_CLIENT_SECRET:
        missing.append(
            "DISCORD_CLIENT_SECRET"
        )

    if not DISCORD_REDIRECT_URI:
        missing.append(
            "DISCORD_REDIRECT_URI"
        )

    if not CT_GUILD_ID:
        missing.append(
            "CT_GUILD_ID"
        )

    if missing:

        return jsonify({
            "ok": False,
            "error":
                "متغيرات Render ناقصة",
            "missing":
                missing,
        }), 500

    state = secrets.token_urlsafe(32)

    session["oauth_state"] = state

    session.modified = True

    params = {
        "client_id":
            DISCORD_CLIENT_ID,

        "redirect_uri":
            DISCORD_REDIRECT_URI,

        "response_type":
            "code",

        "scope":
            "identify guilds",

        "state":
            state,

        "prompt":
            "consent",
    }

    discord_url = (
        "https://discord.com/oauth2/authorize?"
        + urlencode(params)
    )

    return redirect(
        discord_url
    )


# =========================================================
# LOGIN CALLBACK
# =========================================================

@app.route("/login/callback")
def login_callback():

    error = request.args.get("error")

    if error:

        session.clear()

        return jsonify({
            "ok": False,
            "error":
                "تم إلغاء تسجيل الدخول أو رفض Discord الطلب",
            "discord_error":
                error,
        }), 403

    code = request.args.get("code")

    state = request.args.get("state")

    saved_state = session.get(
        "oauth_state"
    )

    if not code:

        session.clear()

        return jsonify({
            "ok": False,
            "error":
                "لم يتم استلام رمز تسجيل الدخول",
        }), 400

    if not state or state != saved_state:

        session.clear()

        return jsonify({
            "ok": False,
            "error":
                "جلسة تسجيل الدخول غير صالحة، حاول مرة أخرى",
        }), 400

    session.pop(
        "oauth_state",
        None
    )

    token_data = discord_exchange_code(
        code
    )

    if not token_data.get("ok"):

        session.clear()

        return jsonify({
            "ok": False,
            "error":
                "فشل تسجيل الدخول عبر Discord",
            "details":
                token_data.get(
                    "error",
                    "Unknown error"
                ),
        }), 502

    access_token = token_data.get(
        "access_token"
    )

    if not access_token:

        session.clear()

        return jsonify({
            "ok": False,
            "error":
                "Discord لم يرجع Access Token",
        }), 502

    user = discord_get_user(
        access_token
    )

    if not user.get("ok"):

        session.clear()

        return jsonify({
            "ok": False,
            "error":
                "تعذر قراءة حساب Discord",
        }), 502

    guild_result = discord_get_user_guilds(
        access_token
    )

    if not guild_result.get("ok"):

        session.clear()

        return jsonify({
            "ok": False,
            "error":
                "تعذر قراءة السيرفرات من Discord",
            "details":
                guild_result.get("error"),
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
            "error":
                admin_result.get(
                    "error",
                    "ليس لديك صلاحية الدخول"
                ),
        }), 403

    discord_id = user.get("id")

    if not discord_id:

        session.clear()

        return jsonify({
            "ok": False,
            "error":
                "تعذر الحصول على Discord ID",
        }), 502

    username = (
        user.get("global_name")
        or user.get("username")
        or "Discord User"
    )

    avatar_hash = user.get("avatar")

    avatar_url = None

    if avatar_hash:

        avatar_url = (
            "https://cdn.discordapp.com/avatars/"
            f"{discord_id}/{avatar_hash}.png"
        )

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

    session.clear()

    session["logged_in"] = True
    session["owner"] = True
    session["discord_admin"] = True
    session["discord_id"] = str(discord_id)
    session["username"] = username
    session["role_id"] = None
    session["discord_avatar"] = avatar_url
    session["ct_guild_id"] = str(
        admin_result["guild_id"]
    )
    session["ct_guild_name"] = (
        admin_result["guild_name"]
    )

    session.modified = True

    return redirect(
        url_for("server")
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    response = redirect(
        url_for("index")
    )

    response.delete_cookie(
        "ct_session",
        path="/"
    )

    return response


# =========================================================
# API AUTH CHECK
# =========================================================

@app.route("/api/auth/check")
def api_auth_check():

    if not is_logged_in():

        return jsonify({
            "ok": True,
            "logged_in": False,
            "login_url":
                url_for(
                    "login",
                    _external=True
                ),
        })

    return jsonify({
        "ok": True,
        "logged_in": True,
        "administrator":
            bool(
                session.get(
                    "discord_admin",
                    False
                )
            ),
        "username":
            session.get("username"),
        "server":
            session.get(
                "ct_guild_name",
                "CT"
            ),
        "discord_id":
            session.get("discord_id"),
    })


# =========================================================
# API ME
# =========================================================

@app.route("/api/me")
def api_me():

    protection = require_login()

    if protection:
        return protection

    return jsonify({
        "ok": True,
        "user": {
            "discord_id":
                session.get("discord_id"),
            "username":
                session.get("username"),
            "avatar":
                session.get("discord_avatar"),
            "administrator":
                bool(
                    session.get(
                        "discord_admin",
                        False
                    )
                ),
        },
        "server": {
            "id":
                session.get("ct_guild_id"),
            "name":
                session.get("ct_guild_name"),
        },
        "app": {
            "name":
                APP_NAME,
            "version":
                VERSION,
        },
    })


# =========================================================
# API BOTS
# =========================================================

@app.route("/api/bots")
def api_bots():

    protection = require_login()

    if protection:
        return protection

    if not has_permission("bots.view"):
        return permission_error("bots.view")

    bots = get_all_bots()

    return jsonify({
        "ok": True,
        "server": {
            "id":
                CT_GUILD_ID,
            "name":
                session.get(
                    "ct_guild_name",
                    "CT"
                ),
        },
        "bots":
            bots,
        "configured":
            len(get_bot_tokens()),
        "visible":
            len(bots),
    })


# =========================================================
# API SINGLE BOT
# =========================================================

@app.route(
    "/api/bots/<int:bot_number>"
)
def api_bot(bot_number):

    protection = require_login()

    if protection:
        return protection

    if not has_permission("bots.view"):
        return permission_error("bots.view")

    token = get_token_for_bot(
        bot_number
    )

    if not token:

        return jsonify({
            "ok": False,
            "error":
                "البوت غير موجود",
        }), 404

    info = discord_bot_info(token)

    if not info.get("ok"):

        return jsonify({
            "ok": False,
            "error":
                "توكن البوت غير صالح",
            "details":
                info.get("error"),
        }), 502

    ct_result = discord_bot_in_ct(token)

    if not ct_result.get("in_ct", False):

        return jsonify({
            "ok": False,
            "error":
                "هذا البوت غير موجود في سيرفر CT",
        }), 403

    return jsonify({
        "ok": True,
        "bot": {
            "number":
                bot_number,
            **info,
            "in_ct":
                True,
        },
    })


# =========================================================
# API BOT CHANNELS
# =========================================================

@app.route(
    "/api/bots/<int:bot_number>/channels"
)
def api_bot_channels(bot_number):

    protection = require_login()

    if protection:
        return protection

    if not has_permission("bots.view"):
        return permission_error("bots.view")

    token = get_token_for_bot(
        bot_number
    )

    if not token:

        return jsonify({
            "ok": False,
            "error":
                "البوت غير موجود",
        }), 404

    ct_result = discord_bot_in_ct(token)

    if not ct_result.get("in_ct", False):

        return jsonify({
            "ok": False,
            "error":
                "البوت غير موجود في سيرفر CT",
        }), 403

    result = discord_get_channels(token)

    if not result.get("ok"):

        return jsonify({
            "ok": False,
            "error":
                "تعذر قراءة أقسام السيرفر",
            "details":
                result.get("error"),
        }), 502

    return jsonify({
        "ok": True,
        "channels":
            result.get("channels", []),
    })


# =========================================================
# API SYSTEMS
# =========================================================

@app.route("/api/systems")
def api_systems():

    protection = require_login()

    if protection:
        return protection

    systems = []

    for system_id, system in SYSTEMS.items():

        systems.append({
            "id":
                system_id,
            "name":
                system["name"],
            "icon":
                system["icon"],
            "view_permission":
                f"{system_id}.view",
            "manage_permission":
                f"{system_id}.manage",
        })

    return jsonify({
        "ok": True,
        "systems":
            systems,
    })


# =========================================================
# GET SYSTEM SETTINGS
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
            "error":
                "النظام غير موجود",
        }), 404

    permission = f"{system_id}.view"

    if not has_permission(permission):
        return permission_error(permission)

    token = get_token_for_bot(
        bot_number
    )

    if not token:

        return jsonify({
            "ok": False,
            "error":
                "البوت غير موجود",
        }), 404

    ct_result = discord_bot_in_ct(token)

    if not ct_result.get("in_ct", False):

        return jsonify({
            "ok": False,
            "error":
                "البوت غير موجود في سيرفر CT",
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
        "bot_number":
            bot_number,
        "system": {
            "id":
                system_id,
            "name":
                SYSTEMS[system_id]["name"],
            "icon":
                SYSTEMS[system_id]["icon"],
        },
        "settings":
            settings,
    })


# =========================================================
# WELCOME IMAGE UPLOAD
# =========================================================

@app.route(
    "/api/bots/<int:bot_number>/welcome/upload",
    methods=["POST"]
)
def api_welcome_upload(bot_number):

    protection = require_login()

    if protection:
        return protection

    if not has_permission("welcome.manage"):
        return permission_error("welcome.manage")

    token = get_token_for_bot(
        bot_number
    )

    if not token:

        return jsonify({
            "ok": False,
            "error":
                "البوت غير موجود",
        }), 404

    ct_result = discord_bot_in_ct(token)

    if not ct_result.get("in_ct", False):

        return jsonify({
            "ok": False,
            "error":
                "البوت غير موجود في سيرفر CT",
        }), 403

    uploaded = request.files.get(
        "image"
    )

    if not uploaded:

        return jsonify({
            "ok": False,
            "error":
                "لم يتم اختيار صورة",
        }), 400

    mime_type = (
        uploaded.mimetype or ""
    ).lower()

    if mime_type not in ALLOWED_IMAGE_TYPES:

        return jsonify({
            "ok": False,
            "error":
                "نوع الصورة غير مدعوم. استخدم PNG أو JPG أو WebP",
        }), 400

    image_bytes = uploaded.read()

    if not image_bytes:

        return jsonify({
            "ok": False,
            "error":
                "الصورة فارغة",
        }), 400

    if len(image_bytes) > MAX_IMAGE_SIZE:

        return jsonify({
            "ok": False,
            "error":
                "حجم الصورة أكبر من 5MB",
        }), 413

    encoded = base64.b64encode(
        image_bytes
    ).decode("ascii")

    now = utc_now()

    db = get_db()

    existing = db.execute(
        """
        SELECT id
        FROM welcome_assets
        WHERE bot_number = ?
        AND asset_type = ?
        """,
        (
            bot_number,
            "welcome_background",
        )
    ).fetchone()

    if existing:

        db.execute(
            """
            UPDATE welcome_assets

            SET mime_type = ?,
                image_data = ?,
                updated_at = ?

            WHERE bot_number = ?
            AND asset_type = ?
            """,
            (
                mime_type,
                encoded,
                now,
                bot_number,
                "welcome_background",
            )
        )

        asset_id = existing["id"]

    else:

        cursor = db.execute(
            """
            INSERT INTO welcome_assets
            (
                bot_number,
                asset_type,
                mime_type,
                image_data,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                bot_number,
                "welcome_background",
                mime_type,
                encoded,
                now,
                now,
            )
        )

        asset_id = cursor.lastrowid

    db.commit()
    db.close()

    return jsonify({
        "ok": True,
        "asset": {
            "id":
                asset_id,
            "url":
                url_for(
                    "welcome_image",
                    asset_id=asset_id,
                    _external=True
                ),
            "mime_type":
                mime_type,
        },
    })


# =========================================================
# WELCOME IMAGE SERVE
# =========================================================

@app.route(
    "/api/welcome/image/<int:asset_id>"
)
def welcome_image(asset_id):

    db = get_db()

    row = db.execute(
        """
        SELECT mime_type, image_data
        FROM welcome_assets
        WHERE id = ?
        """,
        (asset_id,)
    ).fetchone()

    db.close()

    if not row:

        return jsonify({
            "ok": False,
            "error":
                "الصورة غير موجودة",
        }), 404

    try:

        image_bytes = base64.b64decode(
            row["image_data"]
        )

    except Exception:

        return jsonify({
            "ok": False,
            "error":
                "الصورة تالفة",
        }), 500

    response = send_file(
        BytesIO(image_bytes),
        mimetype=row["mime_type"],
        max_age=3600,
    )

    return response


# =========================================================
# WELCOME DELETE IMAGE
# =========================================================

@app.route(
    "/api/bots/<int:bot_number>/welcome/image",
    methods=["DELETE"]
)
def api_welcome_delete_image(bot_number):

    protection = require_login()

    if protection:
        return protection

    if not has_permission("welcome.manage"):
        return permission_error("welcome.manage")

    db = get_db()

    db.execute(
        """
        DELETE FROM welcome_assets
        WHERE bot_number = ?
        AND asset_type = ?
        """,
        (
            bot_number,
            "welcome_background",
        )
    )

    db.commit()
    db.close()

    return jsonify({
        "ok": True,
        "message":
            "تم حذف صورة الترحيب",
    })


# =========================================================
# APPLY SETTINGS
# =========================================================

@app.route(
    "/api/apply",
    methods=["POST"]
)
def api_apply():

    protection = require_login()

    if protection:
        return protection

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

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
            "error":
                "bots يجب أن تكون قائمة",
        }), 400

    if not system_id:

        return jsonify({
            "ok": False,
            "error":
                "يجب تحديد النظام",
        }), 400

    if system_id not in SYSTEMS:

        return jsonify({
            "ok": False,
            "error":
                "النظام غير موجود",
        }), 404

    permission = f"{system_id}.manage"

    if not has_permission(permission):
        return permission_error(permission)

    if not bots:

        return jsonify({
            "ok": False,
            "error":
                "حدد بوتًا واحدًا على الأقل",
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
                "bot":
                    raw_number,
                "error":
                    "رقم بوت غير صالح",
            })

            continue

        token = get_token_for_bot(
            bot_number
        )

        if not token:

            failed.append({
                "bot":
                    bot_number,
                "error":
                    "البوت غير موجود",
            })

            continue

        ct_result = discord_bot_in_ct(
            token
        )

        if not ct_result.get(
            "in_ct",
            False
        ):

            failed.append({
                "bot":
                    bot_number,
                "error":
                    "البوت غير موجود في سيرفر CT",
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
                    settings =
                        excluded.settings,
                    updated_at =
                        excluded.updated_at
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
                "bot":
                    bot_number,
                "error":
                    str(exc),
            })

    db.commit()
    db.close()

    return jsonify({
        "ok":
            len(success) > 0,
        "system":
            system_id,
        "success":
            success,
        "failed":
            failed,
        "message":
            (
                "تم تطبيق الإعدادات على "
                f"{len(success)} بوت"
            ),
    })


# =========================================================
# OWNER ROLES - GET
# =========================================================

@app.route(
    "/api/owner/roles",
    methods=["GET"]
)
def api_owner_roles():

    protection = require_login()

    if protection:
        return protection

    if not has_permission("roles.view"):
        return permission_error("roles.view")

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
            "id":
                row["id"],
            "name":
                row["name"],
            "permissions":
                json_load(
                    row["permissions"],
                    []
                ),
            "created_at":
                row["created_at"],
        })

    return jsonify({
        "ok": True,
        "roles":
            roles,
    })


# =========================================================
# OWNER ROLES - CREATE
# =========================================================

@app.route(
    "/api/owner/roles",
    methods=["POST"]
)
def api_owner_create_role():

    protection = require_login()

    if protection:
        return protection

    if not has_permission("roles.manage"):
        return permission_error("roles.manage")

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

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
            "error":
                "اكتب اسم الرتبة",
        }), 400

    if not isinstance(
        permissions,
        list
    ):

        return jsonify({
            "ok": False,
            "error":
                "permissions يجب أن تكون قائمة",
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
            "id":
                role_id,
            "name":
                name,
            "permissions":
                valid_permissions,
        },
    }), 201


# =========================================================
# OWNER ROLES - UPDATE
# =========================================================

@app.route(
    "/api/owner/roles/<int:role_id>",
    methods=["PUT"]
)
def api_owner_update_role(role_id):

    protection = require_login()

    if protection:
        return protection

    if not has_permission("roles.manage"):
        return permission_error("roles.manage")

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    role = get_dashboard_role(
        role_id
    )

    if not role:

        return jsonify({
            "ok": False,
            "error":
                "الرتبة غير موجودة",
        }), 404

    name = data.get(
        "name",
        role["name"]
    )

    permissions = data.get(
        "permissions",
        json_load(
            role["permissions"],
            []
        )
    )

    name = str(name).strip()

    if not name:

        return jsonify({
            "ok": False,
            "error":
                "اسم الرتبة لا يمكن أن يكون فارغًا",
        }), 400

    if not isinstance(
        permissions,
        list
    ):

        return jsonify({
            "ok": False,
            "error":
                "الصلاحيات غير صحيحة",
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
            "id":
                role_id,
            "name":
                name,
            "permissions":
                permissions,
        },
    })


# =========================================================
# OWNER ROLES - DELETE
# =========================================================

@app.route(
    "/api/owner/roles/<int:role_id>",
    methods=["DELETE"]
)
def api_owner_delete_role(role_id):

    protection = require_login()

    if protection:
        return protection

    if not has_permission("roles.manage"):
        return permission_error("roles.manage")

    role = get_dashboard_role(
        role_id
    )

    if not role:

        return jsonify({
            "ok": False,
            "error":
                "الرتبة غير موجودة",
        }), 404

    db = get_db()

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
        "message":
            "تم حذف الرتبة",
    })


# =========================================================
# OWNER PERMISSIONS
# =========================================================

@app.route(
    "/api/owner/permissions"
)
def api_owner_permissions():

    protection = require_login()

    if protection:
        return protection

    if not has_permission("roles.view"):
        return permission_error("roles.view")

    grouped = {}

    for permission, description in PERMISSIONS.items():

        system = permission.split(
            ".",
            1
        )[0]

        if system not in grouped:
            grouped[system] = []

        grouped[system].append({
            "permission":
                permission,
            "description":
                description,
        })

    return jsonify({
        "ok": True,
        "permissions":
            PERMISSIONS,
        "grouped":
            grouped,
    })


# =========================================================
# OWNER USERS - GET
# =========================================================

@app.route(
    "/api/owner/users",
    methods=["GET"]
)
def api_owner_users():

    protection = require_login()

    if protection:
        return protection

    if not has_permission("roles.view"):
        return permission_error("roles.view")

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
            "id":
                row["id"],
            "discord_id":
                row["discord_id"],
            "username":
                row["username"],
            "role_id":
                row["role_id"],
            "role_name":
                row["role_name"],
            "created_at":
                row["created_at"],
        })

    return jsonify({
        "ok": True,
        "users":
            users,
    })


# =========================================================
# OWNER USERS - ASSIGN ROLE
# =========================================================

@app.route(
    "/api/owner/users",
    methods=["POST"]
)
def api_owner_assign_user():

    protection = require_login()

    if protection:
        return protection

    if not has_permission("roles.manage"):
        return permission_error("roles.manage")

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

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
            "error":
                "يجب تحديد Discord ID",
        }), 400

    if role_id is not None:

        try:
            role_id = int(role_id)
        except Exception:
            return jsonify({
                "ok": False,
                "error":
                    "role_id غير صالح",
            }), 400

        role = get_dashboard_role(
            role_id
        )

        if not role:

            return jsonify({
                "ok": False,
                "error":
                    "الرتبة غير موجودة",
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
        "message":
            "تم تحديث صلاحيات المستخدم",
    })


# =========================================================
# OWNER USERS - DELETE
# =========================================================

@app.route(
    "/api/owner/users/<int:user_id>",
    methods=["DELETE"]
)
def api_owner_delete_user(user_id):

    protection = require_login()

    if protection:
        return protection

    if not has_permission("roles.manage"):
        return permission_error("roles.manage")

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
            "error":
                "المستخدم غير موجود",
        }), 404

    if str(
        row["discord_id"]
    ) == str(
        session.get(
            "discord_id"
        )
    ):

        db.close()

        return jsonify({
            "ok": False,
            "error":
                "لا يمكنك حذف حسابك الحالي",
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
        "message":
            "تم حذف المستخدم",
    })


# =========================================================
# SECTIONS - GET
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
            "id":
                row["id"],
            "name":
                row["name"],
            "description":
                row["description"],
            "enabled":
                bool(
                    row["enabled"]
                ),
            "created_at":
                row["created_at"],
        })

    return jsonify({
        "ok": True,
        "sections":
            sections,
    })


# =========================================================
# SECTIONS - CREATE
# =========================================================

@app.route(
    "/api/sections",
    methods=["POST"]
)
def api_create_section():

    protection = require_login()

    if protection:
        return protection

    if not has_permission("owner.manage"):
        return permission_error("owner.manage")

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

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
            "error":
                "اكتب اسم القسم",
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
            "id":
                section_id,
            "name":
                name,
            "description":
                description,
            "enabled":
                True,
        },
    }), 201


# =========================================================
# HEALTH
# =========================================================

@app.route("/health")
def health():

    configured = get_bot_tokens()

    return jsonify({
        "ok": True,
        "service":
            APP_NAME,
        "version":
            VERSION,
        "status":
            "online",
        "guild_configured":
            bool(CT_GUILD_ID),
        "bots_configured":
            len(configured),
        "bot_numbers":
            [
                bot["number"]
                for bot in configured
            ],
    })


# =========================================================
# API STATUS
# =========================================================

@app.route("/api/status")
def api_status():

    protection = require_login()

    if protection:
        return protection

    configured = get_bot_tokens()

    bots = get_all_bots()

    return jsonify({
        "ok": True,
        "service":
            APP_NAME,
        "version":
            VERSION,
        "server": {
            "id":
                CT_GUILD_ID,
            "name":
                session.get(
                    "ct_guild_name",
                    "CT"
                ),
        },
        "bots": {
            "configured":
                len(configured),
            "in_ct":
                len(bots),
            "numbers":
                [
                    bot["number"]
                    for bot in bots
                ],
        },
        "systems":
            len(SYSTEMS),
    })


# =========================================================
# DEBUG BOTS
# =========================================================

@app.route("/api/debug/bots")
def api_debug_bots():

    protection = require_login()

    if protection:
        return protection

    results = []

    for item in get_bot_tokens():

        number = item["number"]
        token = item["token"]

        info = discord_bot_info(token)

        if not info.get("ok"):

            results.append({
                "number":
                    number,
                "valid":
                    False,
                "in_ct":
                    False,
                "error":
                    info.get(
                        "error",
                        "Invalid token"
                    ),
            })

            continue

        ct_result = discord_bot_in_ct(token)

        results.append({
            "number":
                number,
            "valid":
                True,
            "bot_id":
                info.get("id"),
            "bot_name":
                info.get("display_name"),
            "in_ct":
                ct_result.get(
                    "in_ct",
                    False
                ),
            "ct_error":
                ct_result.get(
                    "error"
                ),
        })

    return jsonify({
        "ok": True,
        "ct_guild_id":
            CT_GUILD_ID,
        "configured":
            len(get_bot_tokens()),
        "results":
            results,
    })


# =========================================================
# ERROR 413
# =========================================================

@app.errorhandler(413)
def too_large(error):

    if request.path.startswith("/api/"):

        return jsonify({
            "ok": False,
            "error":
                "حجم الملف كبير جدًا. الحد الأقصى 5MB",
        }), 413

    return (
        "CT Dashboard - الملف كبير جدًا",
        413
    )


# =========================================================
# ERROR 404
# =========================================================

@app.errorhandler(404)
def not_found(error):

    if request.path.startswith("/api/"):

        return jsonify({
            "ok": False,
            "error":
                "المسار غير موجود",
        }), 404

    return (
        "CT Dashboard - الصفحة غير موجودة",
        404
    )


# =========================================================
# ERROR 500
# =========================================================

@app.errorhandler(500)
def internal_error(error):

    if request.path.startswith("/api/"):

        return jsonify({
            "ok": False,
            "error":
                "حدث خطأ داخلي في الخادم",
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

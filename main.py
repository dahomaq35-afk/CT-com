import os
import sqlite3
import secrets
import asyncio
from functools import wraps
from threading import Thread

import requests
from flask import (
    Flask,
    render_template,
    redirect,
    request,
    session,
    jsonify,
    url_for
)

import discord
from discord.ext import commands

from keepalive import keep_alive


# =========================================================
# CONFIG
# =========================================================

APP = Flask(__name__)

APP.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    secrets.token_hex(32)
)

DB_FILE = "ct_bot.db"

DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
DISCORD_REDIRECT_URI = os.getenv(
    "DISCORD_REDIRECT_URI",
    "http://127.0.0.1:5000/callback"
)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

PORT = int(os.getenv("PORT", "5000"))


# =========================================================
# DATABASE
# =========================================================

def db():
    connection = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    connection.row_factory = sqlite3.Row

    return connection


def init_db():

    connection = db()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id TEXT PRIMARY KEY,
            data TEXT NOT NULL DEFAULT '{}'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS excluded_roles (
            guild_id TEXT NOT NULL,
            role_id TEXT NOT NULL,
            PRIMARY KEY (guild_id, role_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            channel_id TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS laws (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            law_number INTEGER NOT NULL,
            law_name TEXT NOT NULL,
            law_text TEXT NOT NULL,
            UNIQUE(guild_id, law_number)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS levels (
            guild_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(guild_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS command_settings (
            guild_id TEXT NOT NULL,
            command_name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            role_id TEXT,
            PRIMARY KEY(guild_id, command_name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            application_type TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            data TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.commit()
    connection.close()


# =========================================================
# SETTINGS
# =========================================================

import json


def get_settings(guild_id):

    connection = db()

    row = connection.execute(
        "SELECT data FROM guild_settings WHERE guild_id = ?",
        (str(guild_id),)
    ).fetchone()

    connection.close()

    if not row:
        return {}

    try:
        return json.loads(row["data"])
    except Exception:
        return {}


def save_settings(guild_id, settings):

    connection = db()

    connection.execute("""
        INSERT INTO guild_settings(guild_id, data)
        VALUES (?, ?)
        ON CONFLICT(guild_id)
        DO UPDATE SET data = excluded.data
    """, (
        str(guild_id),
        json.dumps(settings, ensure_ascii=False)
    ))

    connection.commit()
    connection.close()


def update_setting(guild_id, key, value):

    settings = get_settings(guild_id)

    settings[key] = value

    save_settings(guild_id, settings)


# =========================================================
# DISCORD BOT
# =========================================================

intents = discord.Intents.default()

intents.guilds = True
intents.members = True
intents.message_content = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():

    print(
        f"CT BOT connected as "
        f"{bot.user} ({bot.user.id})"
    )

    try:
        await bot.tree.sync()
        print("Slash commands synced.")
    except Exception as error:
        print("Slash sync error:", error)


# =========================================================
# DISCORD HELPERS
# =========================================================

def get_guild(guild_id):

    if not bot.is_ready():
        return None

    try:
        return bot.get_guild(int(guild_id))
    except Exception:
        return None


def guild_channels(guild):

    if not guild:
        return []

    channels = []

    for channel in guild.channels:

        if isinstance(
            channel,
            (
                discord.TextChannel,
                discord.VoiceChannel,
                discord.StageChannel
            )
        ):
            channels.append(channel)

    return channels


def guild_roles(guild):

    if not guild:
        return []

    return guild.roles


# =========================================================
# DISCORD OAUTH
# =========================================================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user" not in session:
            return redirect("/login")

        return function(*args, **kwargs)

    return wrapper


@APP.route("/login")
def login():

    if not DISCORD_CLIENT_ID:

        return """
        <h2>Discord OAuth غير مضبوط</h2>
        <p>
        أضف DISCORD_CLIENT_ID في Environment Variables.
        </p>
        """, 500

    params = {
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify guilds"
    }

    query = "&".join(
        f"{key}={requests.utils.quote(str(value))}"
        for key, value in params.items()
    )

    return redirect(
        "https://discord.com/oauth2/authorize?" + query
    )


@APP.route("/callback")
def callback():

    code = request.args.get("code")

    if not code:
        return redirect("/login")

    token_response = requests.post(
        "https://discord.com/api/oauth2/token",
        data={
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": DISCORD_REDIRECT_URI
        },
        timeout=15
    )

    if token_response.status_code != 200:

        return (
            "فشل تسجيل الدخول مع Discord.",
            401
        )

    token_data = token_response.json()

    access_token = token_data.get("access_token")

    if not access_token:
        return "لم يتم الحصول على Access Token.", 401

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    user_response = requests.get(
        "https://discord.com/api/users/@me",
        headers=headers,
        timeout=15
    )

    if user_response.status_code != 200:
        return "تعذر جلب حساب Discord.", 401

    user = user_response.json()

    session["user"] = user
    session["access_token"] = access_token

    return redirect("/")


@APP.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# =========================================================
# USER GUILDS
# =========================================================

def get_user_guilds():

    access_token = session.get("access_token")

    if not access_token:
        return []

    response = requests.get(
        "https://discord.com/api/users/@me/guilds",
        headers={
            "Authorization": f"Bearer {access_token}"
        },
        timeout=15
    )

    if response.status_code != 200:
        return []

    return response.json()


# =========================================================
# HOME
# =========================================================

@APP.route("/")
@login_required
def index():

    guilds = get_user_guilds()

    for guild in guilds:

        icon = guild.get("icon")

        if icon:

            guild["icon"] = (
                f"https://cdn.discordapp.com/icons/"
                f"{guild['id']}/{icon}.png?size=128"
            )

        else:

            guild["icon"] = None

    return render_template(
        "index.html",
        user=session.get("user"),
        guilds=guilds
    )


# =========================================================
# GUILD ACCESS
# =========================================================

def user_can_manage_guild(guild_id):

    guilds = get_user_guilds()

    for guild in guilds:

        if str(guild["id"]) != str(guild_id):
            continue

        permissions = int(
            guild.get("permissions", 0)
        )

        administrator = bool(
            permissions & 0x8
        )

        manage_guild = bool(
            permissions & 0x20
        )

        return administrator or manage_guild

    return False


# =========================================================
# SERVER PAGE
# =========================================================

@APP.route("/server/<guild_id>")
@login_required
def server(guild_id):

    if not user_can_manage_guild(guild_id):
        return "ليس لديك صلاحية إدارة هذا السيرفر.", 403

    guild = get_guild(guild_id)

    if not guild:

        return (
            "البوت غير موجود في هذا السيرفر "
            "أو لم يتمكن من الوصول إليه.",
            404
        )

    channels = guild_channels(guild)
    roles = guild_roles(guild)

    settings = get_settings(guild_id)

    connection = db()

    excluded_rows = connection.execute(
        """
        SELECT role_id
        FROM excluded_roles
        WHERE guild_id = ?
        """,
        (str(guild_id),)
    ).fetchall()

    ticket_rows = connection.execute(
        """
        SELECT *
        FROM tickets
        WHERE guild_id = ?
        ORDER BY id DESC
        LIMIT 100
        """,
        (str(guild_id),)
    ).fetchall()

    law_count = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM laws
        WHERE guild_id = ?
        """,
        (str(guild_id),)
    ).fetchone()["count"]

    application_count = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM applications
        WHERE guild_id = ?
        """,
        (str(guild_id),)
    ).fetchone()["count"]

    connection.close()

    excluded_ids = {
        str(row["role_id"])
        for row in excluded_rows
    }

    excluded_role_objects = [
        role
        for role in roles
        if str(role.id) in excluded_ids
    ]

    stats = {
        "criminal_records": 0,
        "warnings": 0,
        "security_logs": 0,
        "tickets": len(ticket_rows),
        "deeds": 0,
        "warrants": 0,
        "dispatches": 0,
        "medical_reports": 0,
        "laws": law_count,
        "applications": application_count
    }

    return render_template(
        "server.html",
        user=session.get("user"),
        guild=guild,
        channels=channels,
        roles=roles,
        settings=settings,
        tickets=ticket_rows,
        stats=stats,
        excluded_role_objects=excluded_role_objects
    )


# =========================================================
# SERVER ACTIONS
# =========================================================

@APP.route(
    "/server/<guild_id>/action",
    methods=["POST"]
)
@login_required
def server_action(guild_id):

    if not user_can_manage_guild(guild_id):
        return "غير مصرح.", 403

    guild = get_guild(guild_id)

    if not guild:
        return "السيرفر غير متاح.", 404

    action = request.form.get("action", "")

    # -----------------------------------------
    # PROTECTION
    # -----------------------------------------

    if action == "add_excluded_role":

        role_id = request.form.get("role_id")

        if role_id:

            connection = db()

            connection.execute("""
                INSERT OR IGNORE INTO excluded_roles
                (guild_id, role_id)
                VALUES (?, ?)
            """, (
                str(guild_id),
                str(role_id)
            ))

            connection.commit()
            connection.close()

    elif action == "remove_excluded_role":

        role_id = request.form.get("role_id")

        connection = db()

        connection.execute("""
            DELETE FROM excluded_roles
            WHERE guild_id = ?
            AND role_id = ?
        """, (
            str(guild_id),
            str(role_id)
        ))

        connection.commit()
        connection.close()

    # -----------------------------------------
    # LOGS
    # -----------------------------------------

    elif action in {
        "security_log_channel",
        "delete_log_channel",
        "edit_log_channel",
        "member_log_channel",
        "mod_log_channel",
        "role_log_channel",
        "channel_log_channel"
    }:

        channel_id = request.form.get(
            "channel_id"
        )

        setting_map = {
            "security_log_channel":
                "security_log_channel_id",

            "delete_log_channel":
                "delete_log_channel_id",

            "edit_log_channel":
                "edit_log_channel_id",

            "member_log_channel":
                "member_log_channel_id",

            "mod_log_channel":
                "mod_log_channel_id",

            "role_log_channel":
                "role_log_channel_id",

            "channel_log_channel":
                "channel_log_channel_id"
        }

        update_setting(
            guild_id,
            setting_map[action],
            channel_id or None
        )

    # -----------------------------------------
    # AI
    # -----------------------------------------

    elif action == "ai_enable":

        update_setting(
            guild_id,
            "ai_enabled",
            True
        )

    elif action == "ai_disable":

        update_setting(
            guild_id,
            "ai_enabled",
            False
        )

    elif action == "ai_channel":

        update_setting(
            guild_id,
            "ai_channel_id",
            request.form.get("channel_id") or None
        )

    # -----------------------------------------
    # TICKET SETTINGS
    # -----------------------------------------

    elif action == "ticket_channel":

        update_setting(
            guild_id,
            "ticket_channel_id",
            request.form.get("channel_id") or None
        )

    elif action == "ticket_category":

        update_setting(
            guild_id,
            "ticket_category_id",
            request.form.get("category_id") or None
        )

    # -----------------------------------------
    # LEVELS
    # -----------------------------------------

    elif action == "levels_enable":

        update_setting(
            guild_id,
            "levels_enabled",
            request.form.get("enabled") == "1"
        )

    elif action == "levels_channel":

        update_setting(
            guild_id,
            "levels_channel_id",
            request.form.get("channel_id") or None
        )

    # -----------------------------------------
    # GENERAL
    # -----------------------------------------

    elif action == "setting":

        key = request.form.get("key")
        value = request.form.get("value")

        if key:
            update_setting(
                guild_id,
                key,
                value
            )

    return redirect(
        url_for(
            "server",
            guild_id=guild_id
        )
        + "#"
        + request.form.get(
            "section",
            "overview"
        )
    )


# =========================================================
# LAWS API
# =========================================================

@APP.route(
    "/api/server/<guild_id>/laws",
    methods=["GET"]
)
@login_required
def get_laws(guild_id):

    connection = db()

    rows = connection.execute("""
        SELECT *
        FROM laws
        WHERE guild_id = ?
        ORDER BY law_number ASC
    """, (str(guild_id),)).fetchall()

    connection.close()

    return jsonify([
        dict(row)
        for row in rows
    ])


@APP.route(
    "/api/server/<guild_id>/laws",
    methods=["POST"]
)
@login_required
def create_law(guild_id):

    if not user_can_manage_guild(guild_id):
        return jsonify({
            "error": "unauthorized"
        }), 403

    data = request.get_json(
        silent=True
    ) or {}

    number = data.get("law_number")
    name = data.get("law_name")
    text_value = data.get("law_text")

    try:
        number = int(number)
    except Exception:
        return jsonify({
            "error": "رقم القانون غير صحيح"
        }), 400

    if not 1 <= number <= 30:
        return jsonify({
            "error": "رقم القانون يجب أن يكون من 1 إلى 30"
        }), 400

    if not name or not text_value:
        return jsonify({
            "error": "اسم القانون ونصه مطلوبان"
        }), 400

    connection = db()

    connection.execute("""
        INSERT INTO laws
        (guild_id, law_number, law_name, law_text)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, law_number)
        DO UPDATE SET
            law_name = excluded.law_name,
            law_text = excluded.law_text
    """, (
        str(guild_id),
        number,
        str(name),
        str(text_value)
    ))

    connection.commit()
    connection.close()

    return jsonify({
        "success": True
    })


@APP.route(
    "/api/server/<guild_id>/laws/<int:number>",
    methods=["DELETE"]
)
@login_required
def delete_law(guild_id, number):

    if not user_can_manage_guild(guild_id):
        return jsonify({
            "error": "unauthorized"
        }), 403

    connection = db()

    connection.execute("""
        DELETE FROM laws
        WHERE guild_id = ?
        AND law_number = ?
    """, (
        str(guild_id),
        number
    ))

    connection.commit()
    connection.close()

    return jsonify({
        "success": True
    })


# =========================================================
# LEVELS
# =========================================================

@APP.route(
    "/api/server/<guild_id>/levels/<user_id>",
    methods=["GET"]
)
@login_required
def get_level(guild_id, user_id):

    connection = db()

    row = connection.execute("""
        SELECT *
        FROM levels
        WHERE guild_id = ?
        AND user_id = ?
    """, (
        str(guild_id),
        str(user_id)
    )).fetchone()

    connection.close()

    if not row:

        return jsonify({
            "guild_id": guild_id,
            "user_id": user_id,
            "xp": 0,
            "level": 0
        })

    return jsonify(dict(row))


def add_xp(guild_id, user_id, amount):

    connection = db()

    row = connection.execute("""
        SELECT xp, level
        FROM levels
        WHERE guild_id = ?
        AND user_id = ?
    """, (
        str(guild_id),
        str(user_id)
    )).fetchone()

    if not row:

        xp = amount
        level = 0

    else:

        xp = row["xp"] + amount
        level = row["level"]

    required = 100 + (
        level * 50
    )

    if xp >= required:

        xp -= required
        level += 1

    connection.execute("""
        INSERT INTO levels
        (guild_id, user_id, xp, level)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id)
        DO UPDATE SET
            xp = excluded.xp,
            level = excluded.level
    """, (
        str(guild_id),
        str(user_id),
        xp,
        level
    ))

    connection.commit()
    connection.close()

    return level, xp


# =========================================================
# MESSAGE XP
# =========================================================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    guild = message.guild

    if guild:

        settings = get_settings(
            str(guild.id)
        )

        if settings.get(
            "levels_enabled",
            False
        ):

            try:
                add_xp(
                    guild.id,
                    message.author.id,
                    5
                )
            except Exception as error:
                print(
                    "XP error:",
                    error
                )

    await bot.process_commands(message)


# =========================================================
# TICKETS
# =========================================================

@APP.route(
    "/api/server/<guild_id>/tickets",
    methods=["GET"]
)
@login_required
def get_tickets(guild_id):

    connection = db()

    rows = connection.execute("""
        SELECT *
        FROM tickets
        WHERE guild_id = ?
        ORDER BY id DESC
        LIMIT 100
    """, (str(guild_id),)).fetchall()

    connection.close()

    return jsonify([
        dict(row)
        for row in rows
    ])


@APP.route(
    "/api/server/<guild_id>/tickets",
    methods=["POST"]
)
@login_required
def create_ticket(guild_id):

    if not user_can_manage_guild(guild_id):
        return jsonify({
            "error": "unauthorized"
        }), 403

    data = request.get_json(
        silent=True
    ) or {}

    user_id = data.get("user_id")

    if not user_id:
        return jsonify({
            "error": "user_id مطلوب"
        }), 400

    connection = db()

    cursor = connection.execute("""
        INSERT INTO tickets
        (guild_id, user_id, status)
        VALUES (?, ?, 'open')
    """, (
        str(guild_id),
        str(user_id)
    ))

    connection.commit()

    ticket_id = cursor.lastrowid

    connection.close()

    return jsonify({
        "success": True,
        "ticket_id": ticket_id
    })


# =========================================================
# APPLICATIONS
# =========================================================

@APP.route(
    "/api/server/<guild_id>/applications",
    methods=["GET"]
)
@login_required
def applications(guild_id):

    connection = db()

    rows = connection.execute("""
        SELECT *
        FROM applications
        WHERE guild_id = ?
        ORDER BY id DESC
        LIMIT 100
    """, (str(guild_id),)).fetchall()

    connection.close()

    return jsonify([
        dict(row)
        for row in rows
    ])


@APP.route(
    "/api/server/<guild_id>/applications",
    methods=["POST"]
)
@login_required
def create_application(guild_id):

    data = request.get_json(
        silent=True
    ) or {}

    user_id = data.get("user_id")

    if not user_id:
        return jsonify({
            "error": "user_id مطلوب"
        }), 400

    connection = db()

    cursor = connection.execute("""
        INSERT INTO applications
        (guild_id, user_id, application_type, data)
        VALUES (?, ?, ?, ?)
    """, (
        str(guild_id),
        str(user_id),
        data.get("application_type"),
        json.dumps(
            data,
            ensure_ascii=False
        )
    ))

    connection.commit()

    application_id = cursor.lastrowid

    connection.close()

    return jsonify({
        "success": True,
        "application_id": application_id
    })


# =========================================================
# COMMAND SETTINGS
# =========================================================

@APP.route(
    "/api/server/<guild_id>/commands",
    methods=["GET"]
)
@login_required
def get_commands(guild_id):

    connection = db()

    rows = connection.execute("""
        SELECT *
        FROM command_settings
        WHERE guild_id = ?
        ORDER BY command_name
    """, (str(guild_id),)).fetchall()

    connection.close()

    return jsonify([
        dict(row)
        for row in rows
    ])


@APP.route(
    "/api/server/<guild_id>/commands",
    methods=["POST"]
)
@login_required
def update_command(guild_id):

    if not user_can_manage_guild(guild_id):
        return jsonify({
            "error": "unauthorized"
        }), 403

    data = request.get_json(
        silent=True
    ) or {}

    command_name = data.get(
        "command_name"
    )

    if not command_name:
        return jsonify({
            "error": "command_name مطلوب"
        }), 400

    enabled = (
        1
        if data.get("enabled", True)
        else 0
    )

    connection = db()

    connection.execute("""
        INSERT INTO command_settings
        (guild_id, command_name, enabled, role_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, command_name)
        DO UPDATE SET
            enabled = excluded.enabled,
            role_id = excluded.role_id
    """, (
        str(guild_id),
        str(command_name),
        enabled,
        data.get("role_id")
    ))

    connection.commit()
    connection.close()

    return jsonify({
        "success": True
    })


# =========================================================
# AI
# =========================================================

async def ask_ai(prompt):

    if not prompt:
        return "اكتب سؤالك أولاً."

    if not OPENAI_API_KEY:
        return (
            "نظام الذكاء الاصطناعي غير مربوط حالياً. "
            "أضف OPENAI_API_KEY في Environment Variables."
        )

    try:

        from openai import OpenAI

        client = OpenAI(
            api_key=OPENAI_API_KEY
        )

        response = client.responses.create(
            model="gpt-4.1-mini",
            input=prompt
        )

        return response.output_text

    except Exception as error:

        print("AI error:", error)

        return (
            "حدث خطأ أثناء تشغيل الذكاء الاصطناعي."
        )


@bot.event
async def on_message_ai(message):

    pass


# =========================================================
# HEALTH
# =========================================================

@APP.route("/health")
def health():

    return jsonify({
        "status": "online",
        "name": "CT BOT",
        "discord": bot.is_ready()
    })


# =========================================================
# API STATUS
# =========================================================

@APP.route("/api/status")
@login_required
def api_status():

    return jsonify({
        "website": True,
        "discord": bot.is_ready(),
        "guilds": len(bot.guilds)
        if bot.is_ready()
        else 0
    })


# =========================================================
# ERROR HANDLERS
# =========================================================

@APP.errorhandler(404)
def not_found(error):

    return jsonify({
        "error": "Not Found"
    }), 404


@APP.errorhandler(500)
def server_error(error):

    print("SERVER ERROR:", error)

    return jsonify({
        "error": "Internal Server Error"
    }), 500


# =========================================================
# START DISCORD
# =========================================================

def run_bot():

    if not DISCORD_BOT_TOKEN:

        print(
            "WARNING: "
            "DISCORD_BOT_TOKEN is not configured."
        )

        return

    try:

        asyncio.run(
            bot.start(
                DISCORD_BOT_TOKEN
            )
        )

    except Exception as error:

        print(
            "Discord bot error:",
            error
        )


# =========================================================
# START
# =========================================================

init_db()

keep_alive()


if __name__ == "__main__":

    if DISCORD_BOT_TOKEN:

        bot_thread = Thread(
            target=run_bot,
            daemon=True
        )

        bot_thread.start()

    APP.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )

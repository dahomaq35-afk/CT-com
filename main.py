import os
import sqlite3
import secrets
import asyncio
import json
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

DISCORD_CLIENT_ID = os.getenv(
    "DISCORD_CLIENT_ID",
    ""
)

DISCORD_CLIENT_SECRET = os.getenv(
    "DISCORD_CLIENT_SECRET",
    ""
)

DISCORD_REDIRECT_URI = os.getenv(
    "DISCORD_REDIRECT_URI",
    "http://127.0.0.1:5000/callback"
)

DISCORD_BOT_TOKEN = os.getenv(
    "DISCORD_BOT_TOKEN",
    ""
)

PORT = int(
    os.getenv("PORT", "5000")
)


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

def get_settings(guild_id):

    connection = db()

    row = connection.execute(
        """
        SELECT data
        FROM guild_settings
        WHERE guild_id = ?
        """,
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

    connection.execute(
        """
        INSERT INTO guild_settings
        (guild_id, data)
        VALUES (?, ?)

        ON CONFLICT(guild_id)
        DO UPDATE SET
            data = excluded.data
        """,
        (
            str(guild_id),
            json.dumps(
                settings,
                ensure_ascii=False
            )
        )
    )

    connection.commit()
    connection.close()


def update_setting(
    guild_id,
    key,
    value
):

    settings = get_settings(
        guild_id
    )

    settings[key] = value

    save_settings(
        guild_id,
        settings
    )


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

        print(
            "Slash commands synced."
        )

    except Exception as error:

        print(
            "Slash sync error:",
            error
        )


# =========================================================
# DISCORD HELPERS
# =========================================================

def get_guild(guild_id):

    if not bot.is_ready():
        return None

    try:

        return bot.get_guild(
            int(guild_id)
        )

    except Exception:

        return None


def guild_channels(guild):

    if not guild:
        return []

    result = []

    for channel in guild.channels:

        if isinstance(
            channel,
            (
                discord.TextChannel,
                discord.VoiceChannel,
                discord.StageChannel
            )
        ):

            result.append(channel)

    return result


def guild_categories(guild):

    if not guild:
        return []

    return [
        channel
        for channel in guild.channels
        if isinstance(
            channel,
            discord.CategoryChannel
        )
    ]


def guild_roles(guild):

    if not guild:
        return []

    return guild.roles


# =========================================================
# OAUTH
# =========================================================

def login_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if "user" not in session:

            return redirect(
                "/login"
            )

        return function(
            *args,
            **kwargs
        )

    return wrapper


@APP.route("/login")
def login():

    if not DISCORD_CLIENT_ID:

        return """
        <h2>Discord OAuth غير مضبوط</h2>
        <p>
        أضف DISCORD_CLIENT_ID
        في Environment Variables.
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
        "https://discord.com/oauth2/authorize?"
        + query
    )


@APP.route("/callback")
def callback():

    code = request.args.get(
        "code"
    )

    if not code:
        return redirect(
            "/login"
        )

    response = requests.post(
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

    if response.status_code != 200:

        return (
            "فشل تسجيل الدخول مع Discord.",
            401
        )

    token_data = response.json()

    access_token = token_data.get(
        "access_token"
    )

    if not access_token:

        return (
            "لم يتم الحصول على Access Token.",
            401
        )

    user_response = requests.get(
        "https://discord.com/api/users/@me",
        headers={
            "Authorization":
                f"Bearer {access_token}"
        },
        timeout=15
    )

    if user_response.status_code != 200:

        return (
            "تعذر جلب حساب Discord.",
            401
        )

    session["user"] = (
        user_response.json()
    )

    session["access_token"] = (
        access_token
    )

    return redirect("/")


@APP.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# =========================================================
# USER GUILDS
# =========================================================

def get_user_guilds():

    access_token = session.get(
        "access_token"
    )

    if not access_token:
        return []

    response = requests.get(
        "https://discord.com/api/users/@me/guilds",
        headers={
            "Authorization":
                f"Bearer {access_token}"
        },
        timeout=15
    )

    if response.status_code != 200:
        return []

    return response.json()


def user_can_manage_guild(
    guild_id
):

    guilds = get_user_guilds()

    for guild in guilds:

        if str(
            guild["id"]
        ) != str(guild_id):

            continue

        permissions = int(
            guild.get(
                "permissions",
                0
            )
        )

        return bool(
            permissions & 0x8
            or permissions & 0x20
        )

    return False


# =========================================================
# HOME
# =========================================================

@APP.route("/")
@login_required
def index():

    guilds = get_user_guilds()

    for guild in guilds:

        icon = guild.get(
            "icon"
        )

        if icon:

            guild["icon"] = (
                "https://cdn.discordapp.com/icons/"
                f"{guild['id']}/{icon}.png?size=128"
            )

        else:

            guild["icon"] = None

    return render_template(
        "index.html",
        user=session.get(
            "user"
        ),
        guilds=guilds
    )


# =========================================================
# SERVER PAGE
# =========================================================

@APP.route(
    "/server/<guild_id>"
)
@login_required
def server(guild_id):

    if not user_can_manage_guild(
        guild_id
    ):

        return (
            "ليس لديك صلاحية إدارة هذا السيرفر.",
            403
        )

    guild = get_guild(
        guild_id
    )

    if not guild:

        return (
            "البوت غير موجود في هذا السيرفر.",
            404
        )

    channels = guild_channels(
        guild
    )

    categories = guild_categories(
        guild
    )

    roles = guild_roles(
        guild
    )

    settings = get_settings(
        guild_id
    )

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

    excluded_roles = [
        role
        for role in roles
        if str(role.id)
        in excluded_ids
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
        categories=categories,
        roles=roles,
        settings=settings,
        tickets=ticket_rows,
        stats=stats,
        excluded_roles=excluded_roles
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

    if not user_can_manage_guild(
        guild_id
    ):

        return "غير مصرح.", 403

    guild = get_guild(
        guild_id
    )

    if not guild:

        return "السيرفر غير متاح.", 404

    action = request.form.get(
        "action",
        ""
    )

    # -----------------------------------------------------
    # EXCLUDED ROLE
    # -----------------------------------------------------

    if action == "add_excluded_role":

        role_id = request.form.get(
            "role_id"
        )

        if role_id:

            connection = db()

            connection.execute(
                """
                INSERT OR IGNORE INTO
                excluded_roles
                (guild_id, role_id)
                VALUES (?, ?)
                """,
                (
                    str(guild_id),
                    str(role_id)
                )
            )

            connection.commit()
            connection.close()

    elif action == "remove_excluded_role":

        role_id = request.form.get(
            "role_id"
        )

        connection = db()

        connection.execute(
            """
            DELETE FROM excluded_roles
            WHERE guild_id = ?
            AND role_id = ?
            """,
            (
                str(guild_id),
                str(role_id)
            )
        )

        connection.commit()
        connection.close()

    # -----------------------------------------------------
    # LOGS
    # -----------------------------------------------------

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

        update_setting(
            guild_id,
            action,
            channel_id or None
        )

    # -----------------------------------------------------
    # TICKETS
    # -----------------------------------------------------

    elif action == "ticket_channel":

        update_setting(
            guild_id,
            "ticket_channel",
            request.form.get(
                "channel_id"
            ) or None
        )

    elif action == "ticket_category":

        update_setting(
            guild_id,
            "ticket_category",
            request.form.get(
                "category_id"
            ) or None
        )

    # -----------------------------------------------------
    # LEVELS
    # -----------------------------------------------------

    elif action == "levels_enable":

        update_setting(
            guild_id,
            "levels_enabled",
            request.form.get(
                "enabled"
            ) == "1"
        )

    elif action == "levels_channel":

        update_setting(
            guild_id,
            "levels_channel",
            request.form.get(
                "channel_id"
            ) or None
        )

    # -----------------------------------------------------
    # GENERAL
    # -----------------------------------------------------

    elif action == "setting":

        key = request.form.get(
            "key"
        )

        value = request.form.get(
            "value"
        )

        if key:

            update_setting(
                guild_id,
                key,
                value
            )

    section = request.form.get(
        "section",
        "overview"
    )

    return redirect(
        url_for(
            "server",
            guild_id=guild_id
        )
        + "#"
        + section
    )


# =========================================================
# LAWS
# =========================================================

@APP.route(
    "/api/server/<guild_id>/laws",
    methods=["GET"]
)
@login_required
def get_laws(guild_id):

    connection = db()

    rows = connection.execute(
        """
        SELECT *
        FROM laws
        WHERE guild_id = ?
        ORDER BY law_number ASC
        """,
        (str(guild_id),)
    ).fetchall()

    connection.close()

    return jsonify({
        "laws": [
            dict(row)
            for row in rows
        ]
    })


@APP.route(
    "/api/server/<guild_id>/laws",
    methods=["POST"]
)
@login_required
def create_law(guild_id):

    if not user_can_manage_guild(
        guild_id
    ):

        return jsonify({
            "error": "unauthorized"
        }), 403

    data = request.get_json(
        silent=True
    ) or {}

    try:

        number = int(
            data.get("law_number")
        )

    except Exception:

        return jsonify({
            "error":
                "رقم القانون غير صحيح"
        }), 400

    name = str(
        data.get(
            "law_name",
            ""
        )
    ).strip()

    text_value = str(
        data.get(
            "law_text",
            ""
        )
    ).strip()

    if not 1 <= number <= 30:

        return jsonify({
            "error":
                "رقم القانون من 1 إلى 30"
        }), 400

    if not name or not text_value:

        return jsonify({
            "error":
                "اسم القانون ونصه مطلوبان"
        }), 400

    connection = db()

    connection.execute(
        """
        INSERT INTO laws
        (
            guild_id,
            law_number,
            law_name,
            law_text
        )
        VALUES (?, ?, ?, ?)

        ON CONFLICT(
            guild_id,
            law_number
        )
        DO UPDATE SET
            law_name = excluded.law_name,
            law_text = excluded.law_text
        """,
        (
            str(guild_id),
            number,
            name,
            text_value
        )
    )

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
def delete_law(
    guild_id,
    number
):

    if not user_can_manage_guild(
        guild_id
    ):

        return jsonify({
            "error": "unauthorized"
        }), 403

    connection = db()

    connection.execute(
        """
        DELETE FROM laws
        WHERE guild_id = ?
        AND law_number = ?
        """,
        (
            str(guild_id),
            number
        )
    )

    connection.commit()
    connection.close()

    return jsonify({
        "success": True
    })


# =========================================================
# LEVELS
# =========================================================

def add_xp(
    guild_id,
    user_id,
    amount
):

    connection = db()

    row = connection.execute(
        """
        SELECT xp, level
        FROM levels
        WHERE guild_id = ?
        AND user_id = ?
        """,
        (
            str(guild_id),
            str(user_id)
        )
    ).fetchone()

    if row:

        xp = row["xp"] + amount
        level = row["level"]

    else:

        xp = amount
        level = 0

    while xp >= (
        100 + level * 50
    ):

        xp -= (
            100 + level * 50
        )

        level += 1

    connection.execute(
        """
        INSERT INTO levels
        (
            guild_id,
            user_id,
            xp,
            level
        )
        VALUES (?, ?, ?, ?)

        ON CONFLICT(
            guild_id,
            user_id
        )
        DO UPDATE SET
            xp = excluded.xp,
            level = excluded.level
        """,
        (
            str(guild_id),
            str(user_id),
            xp,
            level
        )
    )

    connection.commit()
    connection.close()

    return level, xp


@APP.route(
    "/api/server/<guild_id>/levels/<user_id>",
    methods=["GET"]
)
@login_required
def get_level(
    guild_id,
    user_id
):

    connection = db()

    row = connection.execute(
        """
        SELECT *
        FROM levels
        WHERE guild_id = ?
        AND user_id = ?
        """,
        (
            str(guild_id),
            str(user_id)
        )
    ).fetchone()

    connection.close()

    if not row:

        return jsonify({
            "guild_id": guild_id,
            "user_id": user_id,
            "xp": 0,
            "level": 0
        })

    return jsonify(
        dict(row)
    )


# =========================================================
# MESSAGE XP
# =========================================================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if message.guild:

        settings = get_settings(
            message.guild.id
        )

        if settings.get(
            "levels_enabled",
            False
        ):

            try:

                old_level = 0

                connection = db()

                row = connection.execute(
                    """
                    SELECT level
                    FROM levels
                    WHERE guild_id = ?
                    AND user_id = ?
                    """,
                    (
                        str(
                            message.guild.id
                        ),
                        str(
                            message.author.id
                        )
                    )
                ).fetchone()

                connection.close()

                if row:
                    old_level = row["level"]

                new_level, xp = add_xp(
                    message.guild.id,
                    message.author.id,
                    5
                )

                if new_level > old_level:

                    channel_id = settings.get(
                        "levels_channel"
                    )

                    if channel_id:

                        channel = (
                            message.guild.get_channel(
                                int(channel_id)
                            )
                        )

                        if channel:

                            await channel.send(
                                f"🎉 {message.author.mention} "
                                f"وصل إلى المستوى **{new_level}**!"
                            )

            except Exception as error:

                print(
                    "XP error:",
                    error
                )

    await bot.process_commands(
        message
    )


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

    rows = connection.execute(
        """
        SELECT *
        FROM tickets
        WHERE guild_id = ?
        ORDER BY id DESC
        LIMIT 100
        """,
        (str(guild_id),)
    ).fetchall()

    connection.close()

    return jsonify({
        "tickets": [
            dict(row)
            for row in rows
        ]
    })


@APP.route(
    "/api/server/<guild_id>/tickets",
    methods=["POST"]
)
@login_required
def create_ticket(
    guild_id
):

    if not user_can_manage_guild(
        guild_id
    ):

        return jsonify({
            "error": "unauthorized"
        }), 403

    guild = get_guild(
        guild_id
    )

    if not guild:

        return jsonify({
            "error":
                "البوت غير موجود في السيرفر"
        }), 404

    data = request.get_json(
        silent=True
    ) or {}

    user_id = data.get(
        "user_id"
    )

    if not user_id:

        return jsonify({
            "error":
                "user_id مطلوب"
        }), 400

    settings = get_settings(
        guild_id
    )

    category = None

    category_id = settings.get(
        "ticket_category"
    )

    if category_id:

        try:

            category = guild.get_channel(
                int(category_id)
            )

        except Exception:

            category = None

    try:

        user = guild.get_member(
            int(user_id)
        )

    except Exception:

        user = None

    overwrites = {
        guild.default_role:
            discord.PermissionOverwrite(
                view_channel=False
            )
    }

    if user:

        overwrites[user] = (
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
        )

    overwrites[guild.me] = (
        discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_channels=True
        )
    )

    channel = await_create_ticket_channel(
        guild,
        user,
        category,
        overwrites
    )

    return jsonify(channel)


def await_create_ticket_channel(
    guild,
    user,
    category,
    overwrites
):

    loop = bot.loop

    future = asyncio.run_coroutine_threadsafe(
        guild.create_text_channel(
            name=(
                f"ticket-{user.id}"
                if user
                else "ticket"
            ),
            category=category,
            overwrites=overwrites
        ),
        loop
    )

    channel = future.result(
        timeout=20
    )

    connection = db()

    cursor = connection.execute(
        """
        INSERT INTO tickets
        (
            guild_id,
            user_id,
            channel_id,
            status
        )
        VALUES (?, ?, ?, 'open')
        """,
        (
            str(guild.id),
            str(
                user.id
                if user
                else "0"
            ),
            str(channel.id)
        )
    )

    connection.commit()

    ticket_id = cursor.lastrowid

    connection.close()

    return {
        "success": True,
        "ticket_id": ticket_id,
        "channel_id": str(
            channel.id
        )
    }


# =========================================================
# APPLICATIONS
# =========================================================

@APP.route(
    "/api/server/<guild_id>/applications",
    methods=["GET"]
)
@login_required
def get_applications(
    guild_id
):

    connection = db()

    rows = connection.execute(
        """
        SELECT *
        FROM applications
        WHERE guild_id = ?
        ORDER BY id DESC
        LIMIT 100
        """,
        (str(guild_id),)
    ).fetchall()

    connection.close()

    return jsonify({
        "applications": [
            dict(row)
            for row in rows
        ]
    })


@APP.route(
    "/api/server/<guild_id>/applications",
    methods=["POST"]
)
@login_required
def create_application(
    guild_id
):

    data = request.get_json(
        silent=True
    ) or {}

    user_id = data.get(
        "user_id"
    )

    if not user_id:

        return jsonify({
            "error":
                "user_id مطلوب"
        }), 400

    connection = db()

    cursor = connection.execute(
        """
        INSERT INTO applications
        (
            guild_id,
            user_id,
            application_type,
            status,
            data
        )
        VALUES (?, ?, ?, 'pending', ?)
        """,
        (
            str(guild_id),
            str(user_id),
            data.get(
                "application_type"
            ),
            json.dumps(
                data,
                ensure_ascii=False
            )
        )
    )

    connection.commit()

    application_id = (
        cursor.lastrowid
    )

    connection.close()

    return jsonify({
        "success": True,
        "application_id":
            application_id
    })


# =========================================================
# COMMAND SETTINGS
# =========================================================

def get_bot_commands():

    result = []

    for command in bot.tree.get_commands():

        result.append({
            "name": command.name,
            "description":
                command.description
                or ""
        })

    return result


@APP.route(
    "/api/server/<guild_id>/commands",
    methods=["GET"]
)
@login_required
def get_commands(
    guild_id
):

    connection = db()

    rows = connection.execute(
        """
        SELECT *
        FROM command_settings
        WHERE guild_id = ?
        """,
        (str(guild_id),)
    ).fetchall()

    connection.close()

    saved = {
        row["command_name"]:
            row
        for row in rows
    }

    commands_list = []

    for command in get_bot_commands():

        saved_command = saved.get(
            command["name"]
        )

        if saved_command:

            enabled = bool(
                saved_command["enabled"]
            )

            role_id = (
                saved_command["role_id"]
            )

        else:

            enabled = True
            role_id = None

        commands_list.append({
            "name":
                command["name"],

            "description":
                command["description"],

            "enabled":
                enabled,

            "role_id":
                role_id
        })

    return jsonify({
        "commands":
            commands_list
    })


@APP.route(
    "/api/server/<guild_id>/commands",
    methods=["POST"]
)
@login_required
def update_command(
    guild_id
):

    if not user_can_manage_guild(
        guild_id
    ):

        return jsonify({
            "error":
                "unauthorized"
        }), 403

    data = request.get_json(
        silent=True
    ) or {}

    command_name = data.get(
        "command_name"
    )

    if not command_name:

        return jsonify({
            "error":
                "command_name مطلوب"
        }), 400

    enabled = (
        1
        if data.get(
            "enabled",
            True
        )
        else 0
    )

    role_id = data.get(
        "role_id"
    )

    connection = db()

    connection.execute(
        """
        INSERT INTO command_settings
        (
            guild_id,
            command_name,
            enabled,
            role_id
        )
        VALUES (?, ?, ?, ?)

        ON CONFLICT(
            guild_id,
            command_name
        )
        DO UPDATE SET
            enabled = excluded.enabled,
            role_id = excluded.role_id
        """,
        (
            str(guild_id),
            str(command_name),
            enabled,
            role_id
        )
    )

    connection.commit()
    connection.close()

    return jsonify({
        "success": True
    })


# =========================================================
# SYSTEM STATUS
# =========================================================

@APP.route(
    "/health"
)
def health():

    return jsonify({
        "status": "online",
        "name": "CT BOT",
        "discord":
            bot.is_ready()
    })


@APP.route(
    "/api/status"
)
@login_required
def api_status():

    return jsonify({
        "website": True,
        "discord":
            bot.is_ready(),
        "guilds":
            len(bot.guilds)
            if bot.is_ready()
            else 0
    })


# =========================================================
# ERRORS
# =========================================================

@APP.errorhandler(404)
def not_found(error):

    return jsonify({
        "error":
            "Not Found"
    }), 404


@APP.errorhandler(500)
def server_error(error):

    print(
        "SERVER ERROR:",
        error
    )

    return jsonify({
        "error":
            "Internal Server Error"
    }), 500


# =========================================================
# RUN BOT
# =========================================================

def run_bot():

    if not DISCORD_BOT_TOKEN:

        print(
            "WARNING: "
            "DISCORD_BOT_TOKEN "
            "is not configured."
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

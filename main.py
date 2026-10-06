# =========================================================
# CT DASHBOARD
# Main Server
# Discord Server + Administrator Protection
# Unlimited Bots
# =========================================================
import os
import re
import json
import sqlite3
import secrets
from datetime import datetime, timezone
from threading import Lock
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
# =========================================================
# DISCORD
# =========================================================
DISCORD_API = "https://discord.com/api/v10"
# Discord OAuth
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
# ID سيرفر CT فقط
#
# مثال:
# CT_GUILD_ID=123456789012345678
#
CT_GUILD_ID = os.getenv(
    "CT_GUILD_ID",
    ""
).strip()
# Discord Administrator permission
ADMINISTRATOR_PERMISSION = 1 << 3
# =========================================================
# FLASK
# =========================================================
app = Flask(__name__)
app.secret_key = os.getenv(
    "CT_SECRET_KEY",
    secrets.token_hex(32)
)
app.config["JSON_SORT_KEYS"] = False
# حماية كوكي الجلسة
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Render يستخدم HTTPS
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv(
        "CT_COOKIE_SECURE",
        "1"
    ) == "1"
)
db_lock = Lock()
# =========================================================
# DATABASE
# =========================================================
def get_db():
    conn = sqlite3.connect(
        DB_FILE,
        timeout=30,
        check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn
def init_db():
    with db_lock:
        conn = get_db()
        cur = conn.cursor()
        # -------------------------------------------------
        # Dashboard settings
        # -------------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # -------------------------------------------------
        # Dashboard roles
        # -------------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                permissions TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            )
        """)
        # -------------------------------------------------
        # Dashboard users
        # -------------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                role_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(role_id)
                    REFERENCES dashboard_roles(id)
            )
        """)
        # -------------------------------------------------
        # System settings
        # -------------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bot_id TEXT NOT NULL,
                system TEXT NOT NULL,
                settings TEXT DEFAULT '{}',
                updated_at TEXT NOT NULL,
                UNIQUE(bot_id, system)
            )
        """)
        # -------------------------------------------------
        # Sections
        # -------------------------------------------------
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                icon TEXT DEFAULT '📁',
                description TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                created_at TEXT NOT NULL
            )
        """)
        # -------------------------------------------------
        # Default settings
        # -------------------------------------------------
        cur.execute("""
            INSERT OR IGNORE INTO settings(
                key,
                value
            )
            VALUES(
                'server_name',
                'CT'
            )
        """)
        cur.execute("""
            INSERT OR IGNORE INTO settings(
                key,
                value
            )
            VALUES(
                'version',
                ?
            )
        """, (
            VERSION,
        ))
        conn.commit()
        conn.close()
# =========================================================
# HELPERS
# =========================================================
def utc_now():
    return datetime.now(
        timezone.utc
    ).isoformat()
def json_load(
    value,
    default=None
):
    if default is None:
        default = {}
    try:
        return json.loads(
            value
        )
    except Exception:
        return default
def get_setting(
    key,
    default=None
):
    conn = get_db()
    row = conn.execute(
        """
        SELECT value
        FROM settings
        WHERE key = ?
        """,
        (
            key,
        )
    ).fetchone()
    conn.close()
    if not row:
        return default
    return row["value"]
def set_setting(
    key,
    value
):
    conn = get_db()
    conn.execute(
        """
        INSERT INTO settings(
            key,
            value
        )
        VALUES(
            ?,
            ?
        )
        ON CONFLICT(key)
        DO UPDATE SET
            value = excluded.value
        """,
        (
            key,
            str(value)
        )
    )
    conn.commit()
    conn.close()
# =========================================================
# BOT ENVIRONMENT VARIABLES
# =========================================================
#
# Unlimited:
#
# BOT_TOKEN_1
# BOT_TOKEN_2
# BOT_TOKEN_3
# ...
#
# No fixed maximum.
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
            number = int(
                match.group(1)
            )
        except Exception:
            continue
        token = value.strip()
        if not token:
            continue
        tokens.append({
            "number": number,
            "env": key,
            "token": token
        })
    tokens.sort(
        key=lambda item: item["number"]
    )
    return tokens
def get_token_for_bot(
    bot_number
):
    try:
        bot_number = int(
            bot_number
        )
    except Exception:
        return None
    for item in get_bot_tokens():
        if (
            item["number"]
            == bot_number
        ):
            return item["token"]
    return None
# =========================================================
# DISCORD REQUEST HELPERS
# =========================================================
def discord_request(
    method,
    endpoint,
    token=None,
    token_type="Bot",
    **kwargs
):
    headers = kwargs.pop(
        "headers",
        {}
    )
    if token:
        headers["Authorization"] = (
            f"{token_type} {token}"
        )
    headers.setdefault(
        "User-Agent",
        "CT-Dashboard/2.0"
    )
    kwargs["headers"] = headers
    kwargs.setdefault(
        "timeout",
        15
    )
    try:
        response = requests.request(
            method,
            f"{DISCORD_API}{endpoint}",
            **kwargs
        )
        return response
    except requests.RequestException:
        return None
# =========================================================
# DISCORD BOT INFO
# =========================================================
def discord_bot_info(
    token
):
    response = discord_request(
        "GET",
        "/users/@me",
        token=token,
        token_type="Bot"
    )
    if response is None:
        return {
            "ok": False,
            "error":
                "تعذر الاتصال بـ Discord"
        }
    if response.status_code != 200:
        return {
            "ok": False,
            "status":
                response.status_code,
            "error":
                "توكن البوت غير صالح"
        }
    try:
        data = response.json()
    except Exception:
        return {
            "ok": False,
            "error":
                "استجابة Discord غير صالحة"
        }
    user_id = str(
        data.get(
            "id",
            ""
        )
    )
    avatar = data.get(
        "avatar"
    )
    if avatar:
        avatar_url = (
            "https://cdn.discordapp.com/"
            f"avatars/{user_id}/"
            f"{avatar}.png?size=256"
        )
    else:
        avatar_url = (
            "https://cdn.discordapp.com/"
            "embed/avatars/0.png"
        )
    return {
        "ok": True,
        "id":
            user_id,
        "username":
            data.get(
                "username",
                "Unknown Bot"
            ),
        "global_name":
            data.get(
                "global_name"
            ),
        "avatar":
            avatar_url,
        "verified":
            data.get(
                "verified",
                False
            )
    }
# =========================================================
# CHECK BOT IN CT SERVER
# =========================================================
def discord_bot_in_ct(
    token
):
    if not CT_GUILD_ID:
        return False
    response = discord_request(
        "GET",
        "/users/@me/guilds",
        token=token,
        token_type="Bot"
    )
    if response is None:
        return False
    if response.status_code != 200:
        return False
    try:
        guilds = response.json()
    except Exception:
        return False
    if not isinstance(
        guilds,
        list
    ):
        return False
    for guild in guilds:
        if str(
            guild.get(
                "id",
                ""
            )
        ) == CT_GUILD_ID:
            return True
    return False
# =========================================================
# GET ALL CT BOTS
# =========================================================
def get_all_bots():
    result = []
    for item in get_bot_tokens():
        token = item["token"]
        info = discord_bot_info(
            token
        )
        if not info.get(
            "ok"
        ):
            result.append({
                "number":
                    item["number"],
                "environment":
                    item["env"],
                "id":
                    None,
                "name":
                    "Unknown Bot",
                "username":
                    "Unknown",
                "avatar":
                    None,
                "status":
                    "offline",
                "in_ct":
                    False,
                "error":
                    info.get(
                        "error",
                        "Invalid token"
                    )
            })
            continue
        in_ct = discord_bot_in_ct(
            token
        )
        # لا نعرض البوت في لوحة CT
        # إذا لم يكن داخل سيرفر CT
        if not in_ct:
            continue
        result.append({
            "number":
                item["number"],
            "environment":
                item["env"],
            "id":
                info["id"],
            "name":
                (
                    info.get(
                        "global_name"
                    )
                    or
                    info.get(
                        "username"
                    )
                    or
                    "Discord Bot"
                ),
            "username":
                info.get(
                    "username",
                    "Unknown"
                ),
            "avatar":
                info.get(
                    "avatar"
                ),
            "status":
                "online",
            "in_ct":
                True,
            "verified":
                info.get(
                    "verified",
                    False
                )
        })
    return result
# =========================================================
# DISCORD USER OAUTH
# =========================================================
def discord_exchange_code(
    code
):
    if not DISCORD_CLIENT_ID:
        return {
            "ok": False,
            "error":
                "DISCORD_CLIENT_ID غير مضبوط في Render"
        }
    if not DISCORD_CLIENT_SECRET:
        return {
            "ok": False,
            "error":
                "DISCORD_CLIENT_SECRET غير مضبوط في Render"
        }
    if not DISCORD_REDIRECT_URI:
        return {
            "ok": False,
            "error":
                "DISCORD_REDIRECT_URI غير مضبوط في Render"
        }
    try:
        response = requests.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id":
                    DISCORD_CLIENT_ID,
                "client_secret":
                    DISCORD_CLIENT_SECRET,
                "grant_type":
                    "authorization_code",
                "code":
                    code,
                "redirect_uri":
                    DISCORD_REDIRECT_URI,
            },
            headers={
                "Content-Type":
                    "application/x-www-form-urlencoded"
            },
            timeout=15
        )
        if response.status_code != 200:
            return {
                "ok": False,
                "error":
                    "فشل تسجيل الدخول عبر Discord"
            }
        data = response.json()
        return {
            "ok": True,
            **data
        }
    except Exception as exc:
        return {
            "ok": False,
            "error":
                str(exc)
        }
def discord_get_user(
    access_token
):
    response = discord_request(
        "GET",
        "/users/@me",
        token=access_token,
        token_type="Bearer"
    )
    if response is None:
        return {
            "ok": False
        }
    if response.status_code != 200:
        return {
            "ok": False
        }
    try:
        data = response.json()
    except Exception:
        return {
            "ok": False
        }
    return {
        "ok": True,
        **data
    }
# =========================================================
# GET USER DISCORD SERVERS
# =========================================================
def discord_get_user_guilds(
    access_token
):
    response = discord_request(
        "GET",
        "/users/@me/guilds",
        token=access_token,
        token_type="Bearer"
    )
    if response is None:
        return []
    if response.status_code != 200:
        return []
    try:
        data = response.json()
    except Exception:
        return []
    if not isinstance(
        data,
        list
    ):
        return []
    return data
# =========================================================
# FIND CT SERVER + ADMIN
# =========================================================
def find_ct_admin_guild(
    user_guilds
):
    """
    يفحص سيرفر CT المحدد فقط.
    لا يهتم بأي سيرفر آخر للمستخدم.
    """
    if not CT_GUILD_ID:
        return {
            "ok": False,
            "error":
                "CT_GUILD_ID غير مضبوط في Render"
        }
    for guild in user_guilds:
        guild_id = str(
            guild.get(
                "id",
                ""
            )
        )
        if guild_id != CT_GUILD_ID:
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
        is_admin = bool(
            permissions
            & ADMINISTRATOR_PERMISSION
        )
        if not is_admin:
            return {
                "ok": False,
                "error":
                    "يجب أن تملك Administrator في سيرفر CT"
            }
        return {
            "ok": True,
            "guild_id":
                CT_GUILD_ID,
            "guild_name":
                guild.get(
                    "name",
                    "CT"
                ),
            "permissions":
                permissions
        }
    return {
        "ok": False,
        "error":
            "يجب أن تكون موجودًا في سيرفر CT"
    }
# =========================================================
# SESSION SECURITY
# =========================================================
def is_logged_in():
    return bool(
        session.get(
            "logged_in",
            False
        )
    )
def current_is_owner():
    if not is_logged_in():
        return False
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
                "يجب تسجيل الدخول عبر Discord"
        }), 401
    if not session.get(
        "discord_admin",
        False
    ):
        session.clear()
        return jsonify({
            "ok": False,
            "error":
                "يجب أن تملك Administrator في سيرفر CT"
        }), 403
    # تأكيد أن الجلسة مرتبطة بسيرفر CT
    if (
        CT_GUILD_ID
        and str(
            session.get(
                "ct_guild_id",
                ""
            )
        ) != CT_GUILD_ID
    ):
        session.clear()
        return jsonify({
            "ok": False,
            "error":
                "الحساب غير مرتبط بسيرفر CT"
        }), 403
    return None
def has_permission(
    permission
):
    """
    أي مستخدم Administrator في سيرفر CT
    لديه صلاحية لوحة CT.
    permission محفوظة لدعم نظام
    الصلاحيات المستقبلي.
    """
    if not is_logged_in():
        return False
    if not session.get(
        "discord_admin",
        False
    ):
        return False
    if (
        CT_GUILD_ID
        and str(
            session.get(
                "ct_guild_id",
                ""
            )
        ) != CT_GUILD_ID
    ):
        return False
    return True
# =========================================================
# SYSTEMS
# =========================================================
SYSTEMS = [
    {
        "id": "moderation",
        "name": "الإدارة",
        "icon": "🛡️",
        "description":
            "إعدادات الإدارة والعقوبات"
    },
    {
        "id": "welcome",
        "name": "الترحيب",
        "icon": "👋",
        "description":
            "إعدادات نظام الترحيب"
    },
    {
        "id": "levels",
        "name": "اللفلات",
        "icon": "📊",
        "description":
            "إعدادات نظام اللفلات"
    },
    {
        "id": "points",
        "name": "النقاط",
        "icon": "⭐",
        "description":
            "إعدادات النقاط"
    },
    {
        "id": "tickets",
        "name": "التذاكر",
        "icon": "🎫",
        "description":
            "إعدادات نظام التذاكر"
    },
    {
        "id": "applications",
        "name": "التقديمات",
        "icon": "📝",
        "description":
            "إعدادات التقديمات"
    },
    {
        "id": "suggestions",
        "name": "الاقتراحات",
        "icon": "💡",
        "description":
            "إعدادات الاقتراحات"
    },
    {
        "id": "notifications",
        "name": "الإشعارات",
        "icon": "🔔",
        "description":
            "إعدادات الإشعارات"
    },
    {
        "id": "laws",
        "name": "القوانين",
        "icon": "📜",
        "description":
            "إعدادات القوانين"
    },
    {
        "id": "logs",
        "name": "اللوقات",
        "icon": "🧾",
        "description":
            "إعدادات اللوقات"
    },
    {
        "id": "replies",
        "name": "الردود",
        "icon": "💬",
        "description":
            "إعدادات الردود التلقائية"
    },
    {
        "id": "shortcuts",
        "name": "الاختصارات",
        "icon": "⚡",
        "description":
            "اختصارات الأوامر"
    },
]
def get_system(
    system_id
):
    for system in SYSTEMS:
        if system["id"] == system_id:
            return system
    return None
# =========================================================
# PERMISSIONS
# =========================================================
PERMISSIONS = [
    "dashboard.view",
    "bots.view",
    "bots.manage",
    "moderation.view",
    "moderation.manage",
    "welcome.view",
    "welcome.manage",
    "levels.view",
    "levels.manage",
    "points.view",
    "points.manage",
    "tickets.view",
    "tickets.manage",
    "applications.view",
    "applications.manage",
    "suggestions.view",
    "suggestions.manage",
    "notifications.view",
    "notifications.manage",
    "laws.view",
    "laws.manage",
    "logs.view",
    "logs.manage",
    "replies.view",
    "replies.manage",
    "shortcuts.view",
    "shortcuts.manage",
    "roles.view",
    "roles.manage",
    "owner.manage",
]
# =========================================================
# LOGIN / INDEX
# =========================================================
@app.route("/")
def index():
    if is_logged_in():
        if session.get(
            "discord_admin",
            False
        ):
            return redirect(
                url_for("server")
            )
        session.clear()
    return render_template(
        "index.html",
        server_name:
            get_setting(
                "server_name",
                "CT"
            ),
        systems:
            SYSTEMS
    )
# =========================================================
# SERVER PAGE
# =========================================================
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
    if (
        CT_GUILD_ID
        and str(
            session.get(
                "ct_guild_id",
                ""
            )
        ) != CT_GUILD_ID
    ):
        session.clear()
        return redirect(
            url_for("index")
        )
    return render_template(
        "server.html",
        server_name:
            get_setting(
                "server_name",
                "CT"
            ),
        systems:
            SYSTEMS
    )
# =========================================================
# DISCORD LOGIN
# =========================================================
@app.route("/login")
def login():
    if is_logged_in():
        if session.get(
            "discord_admin",
            False
        ):
            return redirect(
                url_for("server")
            )
        session.clear()
    # -----------------------------------------------------
    # Required configuration
    # -----------------------------------------------------
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
                "متغيرات Render الناقصة: "
                + ", ".join(
                    missing
                )
        }), 500
    # -----------------------------------------------------
    # OAuth state
    # -----------------------------------------------------
    state = secrets.token_urlsafe(
        32
    )
    session["oauth_state"] = state
    # -----------------------------------------------------
    # Discord OAuth
    # -----------------------------------------------------
    params = {
        "client_id":
            DISCORD_CLIENT_ID,
        "redirect_uri":
            DISCORD_REDIRECT_URI,
        "response_type":
            "code",
        # identify = معلومات الحساب
        # guilds = معرفة السيرفرات للتحقق
        "scope":
            "identify guilds",
        "state":
            state
    }
    query = urlencode(
        params
    )
    return redirect(
        "https://discord.com/oauth2/authorize?"
        + query
    )
# =========================================================
# DISCORD LOGIN CALLBACK
# =========================================================
@app.route(
    "/login/callback"
)
def login_callback():
    # -----------------------------------------------------
    # Discord error
    # -----------------------------------------------------
    error = request.args.get(
        "error"
    )
    if error:
        session.clear()
        return render_template(
            "index.html",
            server_name:
                get_setting(
                    "server_name",
                    "CT"
                ),
            systems:
                SYSTEMS,
            login_error:
                "تم رفض تسجيل الدخول عبر Discord"
        )
    # -----------------------------------------------------
    # OAuth state
    # -----------------------------------------------------
    state = request.args.get(
        "state"
    )
    saved_state = session.get(
        "oauth_state"
    )
    if not state:
        return jsonify({
            "ok": False,
            "error":
                "لم يتم استلام State"
        }), 400
    if not saved_state:
        return jsonify({
            "ok": False,
            "error":
                "انتهت جلسة تسجيل الدخول"
        }), 400
    if state != saved_state:
        session.clear()
        return jsonify({
            "ok": False,
            "error":
                "جلسة تسجيل الدخول غير صالحة"
        }), 400
    session.pop(
        "oauth_state",
        None
    )
    # -----------------------------------------------------
    # Authorization code
    # -----------------------------------------------------
    code = request.args.get(
        "code"
    )
    if not code:
        return jsonify({
            "ok": False,
            "error":
                "لم يتم استلام كود Discord"
        }), 400
    # -----------------------------------------------------
    # Exchange code
    # -----------------------------------------------------
    token_data = discord_exchange_code(
        code
    )
    if not token_data.get(
        "ok"
    ):
        return jsonify(
            token_data
        ), 401
    access_token = token_data.get(
        "access_token"
    )
    if not access_token:
        return jsonify({
            "ok": False,
            "error":
                "فشل الحصول على جلسة Discord"
        }), 401
    # -----------------------------------------------------
    # Get Discord user
    # -----------------------------------------------------
    discord_user = discord_get_user(
        access_token
    )
    if not discord_user.get(
        "ok"
    ):
        return jsonify({
            "ok": False,
            "error":
                "تعذر التحقق من حساب Discord"
        }), 401
    user_id = str(
        discord_user.get(
            "id",
            ""
        )
    )
    username = (
        discord_user.get(
            "global_name"
        )
        or
        discord_user.get(
            "username",
            "Discord User"
        )
    )
    # -----------------------------------------------------
    # Get user's servers
    # -----------------------------------------------------
    user_guilds = discord_get_user_guilds(
        access_token
    )
    # -----------------------------------------------------
    # Check CT server + Administrator
    # -----------------------------------------------------
    admin_check = find_ct_admin_guild(
        user_guilds
    )
    if not admin_check.get(
        "ok"
    ):
        session.clear()
        return render_template(
            "index.html",
            server_name:
                get_setting(
                    "server_name",
                    "CT"
                ),
            systems:
                SYSTEMS,
            login_error:
                admin_check.get(
                    "error",
                    "ليس لديك صلاحية للدخول"
                )
        )
    # -----------------------------------------------------
    # SUCCESS
    # -----------------------------------------------------
    session.clear()
    session["logged_in"] = True
    # كل Administrator في CT
    # يعتبر لديه صلاحية لوحة CT
    session["discord_admin"] = True
    session["owner"] = True
    session["discord_id"] = (
        user_id
    )
    session["username"] = (
        username
    )
    session["role_id"] = None
    session["discord_avatar"] = (
        discord_user.get(
            "avatar"
        )
    )
    session["ct_guild_id"] = (
        CT_GUILD_ID
    )
    session["ct_guild_name"] = (
        admin_check.get(
            "guild_name",
            "CT"
        )
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
    if not is_logged_in():
        return jsonify({
            "ok": False,
            "logged_in": False
        }), 401
    if not session.get(
        "discord_admin",
        False
    ):
        return jsonify({
            "ok": False,
            "logged_in": False,
            "error":
                "يجب أن تملك Administrator في سيرفر CT"
        }), 403
    return jsonify({
        "ok": True,
        "logged_in": True,
        "username":
            session.get(
                "username"
            ),
        "discord_id":
            session.get(
                "discord_id"
            ),
        "discord_admin":
            True,
        "owner":
            current_is_owner(),
        "role_id":
            session.get(
                "role_id"
            ),
        "avatar":
            session.get(
                "discord_avatar"
            ),
        "ct_guild_id":
            session.get(
                "ct_guild_id"
            ),
        "ct_guild_name":
            session.get(
                "ct_guild_name"
            )
    })
# =========================================================
# API - BOTS
# =========================================================
@app.route("/api/bots")
def api_bots():
    denied = require_login()
    if denied:
        return denied
    return jsonify({
        "ok": True,
        "bots":
            get_all_bots()
    })
@app.route(
    "/api/bots/<int:bot_number>"
)
def api_bot(
    bot_number
):
    denied = require_login()
    if denied:
        return denied
    bots = get_all_bots()
    for bot in bots:
        if (
            bot["number"]
            == bot_number
        ):
            return jsonify({
                "ok": True,
                "bot":
                    bot
            })
    return jsonify({
        "ok": False,
        "error":
            "البوت غير موجود في سيرفر CT"
    }), 404
# =========================================================
# API - SYSTEMS
# =========================================================
@app.route("/api/systems")
def api_systems():
    denied = require_login()
    if denied:
        return denied
    return jsonify({
        "ok": True,
        "systems":
            SYSTEMS
    })
# =========================================================
# API - GET SYSTEM SETTINGS
# =========================================================
@app.route(
    "/api/bots/<int:bot_number>/systems/<system_id>",
    methods=["GET"]
)
def get_system_settings(
    bot_number,
    system_id
):
    denied = require_login()
    if denied:
        return denied
    system = get_system(
        system_id
    )
    if not system:
        return jsonify({
            "ok": False,
            "error":
                "النظام غير موجود"
        }), 404
    bots = get_all_bots()
    bot = next(
        (
            b
            for b in bots
            if b["number"]
            == bot_number
        ),
        None
    )
    if not bot:
        return jsonify({
            "ok": False,
            "error":
                "البوت غير موجود في سيرفر CT"
        }), 404
    conn = get_db()
    row = conn.execute(
        """
        SELECT settings
        FROM system_settings
        WHERE bot_id = ?
        AND system = ?
        """,
        (
            bot["id"],
            system_id
        )
    ).fetchone()
    conn.close()
    settings = {}
    if row:
        settings = json_load(
            row["settings"],
            {}
        )
    return jsonify({
        "ok": True,
        "bot":
            bot,
        "system":
            system,
        "settings":
            settings
    })
# =========================================================
# API - APPLY SYSTEM TO MULTIPLE BOTS
# =========================================================
@app.route(
    "/api/apply",
    methods=["POST"]
)
def apply_changes():
    denied = require_login()
    if denied:
        return denied
    data = request.get_json(
        silent=True
    ) or {}
    bot_numbers = data.get(
        "bots",
        []
    )
    system_id = str(
        data.get(
            "system",
            ""
        )
    ).strip()
    settings = data.get(
        "settings",
        {}
    )
    # -----------------------------------------------------
    # Validate bot list
    # -----------------------------------------------------
    if not isinstance(
        bot_numbers,
        list
    ):
        return jsonify({
            "ok": False,
            "error":
                "قائمة البوتات غير صحيحة"
        }), 400
    if not bot_numbers:
        return jsonify({
            "ok": False,
            "error":
                "حدد بوتًا واحدًا على الأقل"
        }), 400
    # -----------------------------------------------------
    # Validate system
    # -----------------------------------------------------
    system = get_system(
        system_id
    )
    if not system:
        return jsonify({
            "ok": False,
            "error":
                "النظام غير موجود"
        }), 404
    # -----------------------------------------------------
    # Administrator
    # -----------------------------------------------------
    if not has_permission(
        f"{system_id}.manage"
    ):
        return jsonify({
            "ok": False,
            "error":
                "يجب أن تملك Administrator في سيرفر CT"
        }), 403
    # -----------------------------------------------------
    # Get CT bots
    # -----------------------------------------------------
    bots = get_all_bots()
    bot_map = {
        bot["number"]:
            bot
        for bot in bots
    }
    conn = get_db()
    applied = []
    failed = []
    # -----------------------------------------------------
    # Apply
    # -----------------------------------------------------
    for raw_number in bot_numbers:
        try:
            number = int(
                raw_number
            )
        except Exception:
            failed.append({
                "number":
                    raw_number,
                "reason":
                    "رقم البوت غير صحيح"
            })
            continue
        bot = bot_map.get(
            number
        )
        if not bot:
            failed.append({
                "number":
                    number,
                "reason":
                    "البوت غير موجود في سيرفر CT"
            })
            continue
        if not bot.get(
            "id"
        ):
            failed.append({
                "number":
                    number,
                "reason":
                    "البوت غير متصل"
            })
            continue
        try:
            conn.execute(
                """
                INSERT INTO system_settings(
                    bot_id,
                    system,
                    settings,
                    updated_at
                )
                VALUES(
                    ?,
                    ?,
                    ?,
                    ?
                )
                ON CONFLICT(
                    bot_id,
                    system
                )
                DO UPDATE SET
                    settings =
                        excluded.settings,
                    updated_at =
                        excluded.updated_at
                """,
                (
                    bot["id"],
                    system_id,
                    json.dumps(
                        settings,
                        ensure_ascii=False
                    ),
                    utc_now()
                )
            )
            applied.append({
                "number":
                    number,
                "bot_id":
                    bot["id"],
                "name":
                    bot["name"]
            })
        except Exception as exc:
            failed.append({
                "number":
                    number,
                "reason":
                    str(exc)
            })
    conn.commit()
    conn.close()
    return jsonify({
        "ok": True,
        "system":
            system_id,
        "applied":
            applied,
        "failed":
            failed
    })
# =========================================================
# OWNER - ROLES
# =========================================================
@app.route(
    "/api/owner/roles",
    methods=["GET"]
)
def owner_roles():
    denied = require_login()
    if denied:
        return denied
    conn = get_db()
    rows = conn.execute(
        """
        SELECT *
        FROM dashboard_roles
        ORDER BY id DESC
        """
    ).fetchall()
    conn.close()
    roles = []
    for row in rows:
        roles.append({
            "id":
                row["id"],
            "name":
                row["name"],
            "description":
                row["description"],
            "permissions":
                json_load(
                    row["permissions"],
                    []
                ),
            "created_at":
                row["created_at"]
        })
    return jsonify({
        "ok": True,
        "roles":
            roles
    })
# =========================================================
# CREATE ROLE
# =========================================================
@app.route(
    "/api/owner/roles",
    methods=["POST"]
)
def create_role():
    denied = require_login()
    if denied:
        return denied
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
    permissions = data.get(
        "permissions",
        []
    )
    if not name:
        return jsonify({
            "ok": False,
            "error":
                "اسم الرتبة مطلوب"
        }), 400
    if not isinstance(
        permissions,
        list
    ):
        permissions = []
    permissions = [
        p
        for p in permissions
        if p in PERMISSIONS
    ]
    conn = get_db()
    cur = conn.execute(
        """
        INSERT INTO dashboard_roles(
            name,
            description,
            permissions,
            created_at
        )
        VALUES(
            ?,
            ?,
            ?,
            ?
        )
        """,
        (
            name,
            description,
            json.dumps(
                permissions,
                ensure_ascii=False
            ),
            utc_now()
        )
    )
    conn.commit()
    role_id = cur.lastrowid
    conn.close()
    return jsonify({
        "ok": True,
        "role_id":
            role_id
    })
# =========================================================
# UPDATE ROLE
# =========================================================
@app.route(
    "/api/owner/roles/<int:role_id>",
    methods=["PUT"]
)
def update_role(
    role_id
):
    denied = require_login()
    if denied:
        return denied
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
    permissions = data.get(
        "permissions",
        []
    )
    if not name:
        return jsonify({
            "ok": False,
            "error":
                "اسم الرتبة مطلوب"
        }), 400
    if not isinstance(
        permissions,
        list
    ):
        permissions = []
    permissions = [
        p
        for p in permissions
        if p in PERMISSIONS
    ]
    conn = get_db()
    existing = conn.execute(
        """
        SELECT id
        FROM dashboard_roles
        WHERE id = ?
        """,
        (
            role_id,
        )
    ).fetchone()
    if not existing:
        conn.close()
        return jsonify({
            "ok": False,
            "error":
                "الرتبة غير موجودة"
        }), 404
    conn.execute(
        """
        UPDATE dashboard_roles
        SET
            name = ?,
            description = ?,
            permissions = ?
        WHERE id = ?
        """,
        (
            name,
            description,
            json.dumps(
                permissions,
                ensure_ascii=False
            ),
            role_id
        )
    )
    conn.commit()
    conn.close()
    return jsonify({
        "ok": True
    })
# =========================================================
# DELETE ROLE
# =========================================================
@app.route(
    "/api/owner/roles/<int:role_id>",
    methods=["DELETE"]
)
def delete_role(
    role_id
):
    denied = require_login()
    if denied:
        return denied
    conn = get_db()
    conn.execute(
        """
        UPDATE dashboard_users
        SET role_id = NULL
        WHERE role_id = ?
        """,
        (
            role_id,
        )
    )
    conn.execute(
        """
        DELETE FROM dashboard_roles
        WHERE id = ?
        """,
        (
            role_id,
        )
    )
    conn.commit()
    conn.close()
    return jsonify({
        "ok": True
    })
# =========================================================
# OWNER - PERMISSIONS
# =========================================================
@app.route(
    "/api/owner/permissions"
)
def owner_permissions():
    denied = require_login()
    if denied:
        return denied
    return jsonify({
        "ok": True,
        "permissions":
            PERMISSIONS
    })
# =========================================================
# OWNER - USERS
# =========================================================
@app.route(
    "/api/owner/users",
    methods=["GET"]
)
def owner_users():
    denied = require_login()
    if denied:
        return denied
    conn = get_db()
    rows = conn.execute(
        """
        SELECT
            dashboard_users.id,
            dashboard_users.username,
            dashboard_users.role_id,
            dashboard_roles.name AS role_name
        FROM dashboard_users
        LEFT JOIN dashboard_roles
            ON dashboard_roles.id =
               dashboard_users.role_id
        ORDER BY dashboard_users.id DESC
        """
    ).fetchall()
    conn.close()
    users = []
    for row in rows:
        users.append({
            "id":
                row["id"],
            "username":
                row["username"],
            "role_id":
                row["role_id"],
            "role_name":
                row["role_name"]
        })
    return jsonify({
        "ok": True,
        "users":
            users
    })
# =========================================================
# CREATE DASHBOARD USER
# =========================================================
@app.route(
    "/api/owner/users",
    methods=["POST"]
)
def create_user():
    denied = require_login()
    if denied:
        return denied
    data = request.get_json(
        silent=True
    ) or {}
    username = str(
        data.get(
            "username",
            ""
        )
    ).strip()
    role_id = data.get(
        "role_id"
    )
    if not username:
        return jsonify({
            "ok": False,
            "error":
                "اسم المستخدم مطلوب"
        }), 400
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO dashboard_users(
                username,
                role_id,
                created_at
            )
            VALUES(
                ?,
                ?,
                ?
            )
            """,
            (
                username,
                role_id,
                utc_now()
            )
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({
            "ok": False,
            "error":
                "المستخدم موجود مسبقًا"
        }), 409
    conn.close()
    return jsonify({
        "ok": True
    })
# =========================================================
# DELETE DASHBOARD USER
# =========================================================
@app.route(
    "/api/owner/users/<int:user_id>",
    methods=["DELETE"]
)
def delete_user(
    user_id
):
    denied = require_login()
    if denied:
        return denied
    conn = get_db()
    conn.execute(
        """
        DELETE FROM dashboard_users
        WHERE id = ?
        """,
        (
            user_id,
        )
    )
    conn.commit()
    conn.close()
    return jsonify({
        "ok": True
    })
# =========================================================
# SECTIONS
# =========================================================
@app.route(
    "/api/sections",
    methods=["GET"]
)
def get_sections():
    denied = require_login()
    if denied:
        return denied
    conn = get_db()
    rows = conn.execute(
        """
        SELECT *
        FROM sections
        ORDER BY id ASC
        """
    ).fetchall()
    conn.close()
    return jsonify({
        "ok": True,
        "sections": [
            dict(row)
            for row in rows
        ]
    })
# =========================================================
# CREATE SECTION
# =========================================================
@app.route(
    "/api/sections",
    methods=["POST"]
)
def create_section():
    denied = require_login()
    if denied:
        return denied
    if not has_permission(
        "owner.manage"
    ):
        return jsonify({
            "ok": False,
            "error":
                "يجب أن تملك Administrator في سيرفر CT"
        }), 403
    data = request.get_json(
        silent=True
    ) or {}
    name = str(
        data.get(
            "name",
            ""
        )
    ).strip()
    icon = str(
        data.get(
            "icon",
            "📁"
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
                "اسم القسم مطلوب"
        }), 400
    conn = get_db()
    conn.execute(
        """
        INSERT INTO sections(
            name,
            icon,
            description,
            created_at
        )
        VALUES(
            ?,
            ?,
            ?,
            ?
        )
        """,
        (
            name,
            icon,
            description,
            utc_now()
        )
    )
    conn.commit()
    conn.close()
    return jsonify({
        "ok": True
    })
# =========================================================
# HEALTH
# =========================================================
@app.route(
    "/health"
)
def health():
    return jsonify({
        "status":
            "online",
        "name":
            APP_NAME,
        "version":
            VERSION,
        "ct_guild_configured":
            bool(
                CT_GUILD_ID
            ),
        "bot_environment_count":
            len(
                get_bot_tokens()
            )
    })
# =========================================================
# ERROR HANDLERS
# =========================================================
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "ok": False,
        "error":
            "Not Found"
    }), 404
@app.errorhandler(500)
def server_error(error):
    return jsonify({
        "ok": False,
        "error":
            "Internal Server Error"
    }), 500
# =========================================================
# STARTUP
# =========================================================
def startup():
    init_db()
    print(
        "=" * 60
    )
    print(
        "CT DASHBOARD"
    )
    print(
        "=" * 60
    )
    print(
        f"Version: {VERSION}"
    )
    print(
        f"Port: {PORT}"
    )
    print(
        "CT Guild ID: "
        + (
            "Configured"
            if CT_GUILD_ID
            else "NOT CONFIGURED"
        )
    )
    tokens = get_bot_tokens()
    print(
        "Bot Environment Variables: "
        f"{len(tokens)}"
    )
    for item in tokens:
        print(
            "  • "
            f"BOT_TOKEN_{item['number']} "
            "detected"
        )
    print(
        "=" * 60
    )
# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    startup()
    app.run(
        host=HOST,
        port=PORT,
        debug=False,
        threaded=True
    )

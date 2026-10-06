# =========================================================
# CT DASHBOARD
# Main Server
# =========================================================

import os
import re
import json
import sqlite3
import secrets
from datetime import datetime, timezone
from threading import Lock

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
VERSION = "1.0.0"

HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "10000"))

DB_FILE = "ct_dashboard.db"

# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "CT_SECRET_KEY",
    secrets.token_hex(32)
)

app.config["JSON_SORT_KEYS"] = False

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
        # Custom dashboard roles
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
        # Default dashboard settings
        # -------------------------------------------------

        cur.execute("""
            INSERT OR IGNORE INTO settings(key, value)
            VALUES('server_name', 'CT')
        """)

        cur.execute("""
            INSERT OR IGNORE INTO settings(key, value)
            VALUES('version', ?)
        """, (VERSION,))

        conn.commit()
        conn.close()


# =========================================================
# HELPERS
# =========================================================


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def json_load(value, default=None):

    if default is None:
        default = {}

    try:
        return json.loads(value)
    except Exception:
        return default


def get_setting(key, default=None):

    conn = get_db()

    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,)
    ).fetchone()

    conn.close()

    if not row:
        return default

    return row["value"]


def set_setting(key, value):

    conn = get_db()

    conn.execute("""
        INSERT INTO settings(key, value)
        VALUES(?, ?)
        ON CONFLICT(key)
        DO UPDATE SET value = excluded.value
    """, (key, str(value)))

    conn.commit()
    conn.close()


# =========================================================
# BOT ENVIRONMENT VARIABLES
# =========================================================

# يدعم:
#
# BOT_TOKEN_1
# BOT_TOKEN_2
# BOT_TOKEN_3
# ...
#
# وأيضًا:
#
# BOT_TOKEN_10
# BOT_TOKEN_50
# BOT_TOKEN_100
#
# بدون حد برمجي ثابت.


def get_bot_tokens():

    tokens = []

    for key, value in os.environ.items():

        if not value:
            continue

        match = re.fullmatch(
            r"BOT_TOKEN_(\d+)",
            key.upper()
        )

        if match:
            number = int(match.group(1))

            tokens.append({
                "number": number,
                "env": key,
                "token": value.strip()
            })

    tokens.sort(
        key=lambda x: x["number"]
    )

    return tokens


# =========================================================
# DISCORD API
# =========================================================

DISCORD_API = "https://discord.com/api/v10"


def discord_bot_info(token):

    try:

        response = requests.get(
            f"{DISCORD_API}/users/@me",
            headers={
                "Authorization": f"Bot {token}"
            },
            timeout=15
        )

        if response.status_code != 200:
            return {
                "ok": False,
                "status": response.status_code
            }

        data = response.json()

        user_id = str(data.get("id", ""))

        avatar = data.get("avatar")

        if avatar:
            avatar_url = (
                f"https://cdn.discordapp.com/avatars/"
                f"{user_id}/{avatar}.png?size=256"
            )
        else:
            discriminator = data.get(
                "discriminator",
                "0"
            )

            try:
                index = int(discriminator) % 5
            except Exception:
                index = 0

            avatar_url = (
                "https://cdn.discordapp.com/embed/avatars/"
                f"{index}.png"
            )

        return {
            "ok": True,
            "id": user_id,
            "username": data.get(
                "username",
                "Unknown Bot"
            ),
            "global_name": data.get(
                "global_name"
            ),
            "avatar": avatar_url,
            "verified": data.get(
                "verified",
                False
            ),
        }

    except Exception as exc:

        return {
            "ok": False,
            "error": str(exc)
        }


def get_all_bots():

    result = []

    for item in get_bot_tokens():

        info = discord_bot_info(
            item["token"]
        )

        if info.get("ok"):

            result.append({
                "number": item["number"],
                "environment": item["env"],
                "id": info["id"],
                "name": (
                    info.get("global_name")
                    or info.get("username")
                    or "Discord Bot"
                ),
                "username": info.get(
                    "username",
                    "Unknown"
                ),
                "avatar": info.get(
                    "avatar"
                ),
                "status": "online",
                "verified": info.get(
                    "verified",
                    False
                ),
            })

        else:

            result.append({
                "number": item["number"],
                "environment": item["env"],
                "id": None,
                "name": "Unknown Bot",
                "username": "Unknown",
                "avatar": None,
                "status": "offline",
                "error": info.get(
                    "error",
                    "Invalid token"
                ),
            })

    return result


def get_token_for_bot(bot_number):

    for item in get_bot_tokens():

        if item["number"] == int(bot_number):
            return item["token"]

    return None


# =========================================================
# SYSTEMS
# =========================================================

SYSTEMS = [
    {
        "id": "moderation",
        "name": "الإدارة",
        "icon": "🛡️",
        "description": "إعدادات الإدارة والعقوبات"
    },
    {
        "id": "welcome",
        "name": "الترحيب",
        "icon": "👋",
        "description": "إعدادات نظام الترحيب"
    },
    {
        "id": "levels",
        "name": "اللفلات",
        "icon": "📊",
        "description": "إعدادات نظام اللفلات"
    },
    {
        "id": "points",
        "name": "النقاط",
        "icon": "⭐",
        "description": "إعدادات النقاط"
    },
    {
        "id": "tickets",
        "name": "التذاكر",
        "icon": "🎫",
        "description": "إعدادات نظام التذاكر"
    },
    {
        "id": "applications",
        "name": "التقديمات",
        "icon": "📝",
        "description": "إعدادات التقديمات"
    },
    {
        "id": "suggestions",
        "name": "الاقتراحات",
        "icon": "💡",
        "description": "إعدادات الاقتراحات"
    },
    {
        "id": "notifications",
        "name": "الإشعارات",
        "icon": "🔔",
        "description": "إعدادات الإشعارات"
    },
    {
        "id": "laws",
        "name": "القوانين",
        "icon": "📜",
        "description": "إعدادات القوانين"
    },
    {
        "id": "logs",
        "name": "اللوقات",
        "icon": "🧾",
        "description": "إعدادات اللوقات"
    },
    {
        "id": "replies",
        "name": "الردود",
        "icon": "💬",
        "description": "إعدادات الردود التلقائية"
    },
    {
        "id": "shortcuts",
        "name": "الاختصارات",
        "icon": "⚡",
        "description": "اختصارات الأوامر"
    },
]


def get_system(system_id):

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


def current_is_owner():

    return session.get(
        "owner",
        False
    )


def has_permission(permission):

    if current_is_owner():
        return True

    role_id = session.get("role_id")

    if not role_id:
        return False

    conn = get_db()

    row = conn.execute("""
        SELECT permissions
        FROM dashboard_roles
        WHERE id = ?
    """, (role_id,)).fetchone()

    conn.close()

    if not row:
        return False

    permissions = json_load(
        row["permissions"],
        []
    )

    return permission in permissions


# =========================================================
# LOGIN
# =========================================================

@app.route("/")
def index():

    return render_template(
        "index.html",
        server_name=get_setting(
            "server_name",
            "CT"
        ),
        systems=SYSTEMS
    )


@app.route("/server")
def server():

    return render_template(
        "server.html",
        server_name=get_setting(
            "server_name",
            "CT"
        ),
        systems=SYSTEMS
    )


# =========================================================
# SIMPLE OWNER LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET":

        return jsonify({
            "ok": True,
            "message": "CT Login API"
        })

    data = request.get_json(
        silent=True
    ) or {}

    username = str(
        data.get("username", "")
    ).strip()

    owner_username = os.getenv(
        "CT_OWNER_USERNAME",
        ""
    ).strip()

    owner_password = os.getenv(
        "CT_OWNER_PASSWORD",
        ""
    )

    password = str(
        data.get("password", "")
    )

    if (
        owner_username
        and owner_password
        and username == owner_username
        and password == owner_password
    ):

        session["logged_in"] = True
        session["owner"] = True
        session["username"] = username
        session["role_id"] = None

        return jsonify({
            "ok": True,
            "owner": True
        })

    conn = get_db()

    row = conn.execute("""
        SELECT
            dashboard_users.username,
            dashboard_users.role_id,
            dashboard_roles.permissions
        FROM dashboard_users
        LEFT JOIN dashboard_roles
            ON dashboard_roles.id =
               dashboard_users.role_id
        WHERE dashboard_users.username = ?
    """, (username,)).fetchone()

    conn.close()

    if not row:

        return jsonify({
            "ok": False,
            "error": "بيانات الدخول غير صحيحة"
        }), 401

    session["logged_in"] = True
    session["owner"] = False
    session["username"] = username
    session["role_id"] = row["role_id"]

    return jsonify({
        "ok": True,
        "owner": False
    })


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

    return jsonify({
        "logged_in": session.get(
            "logged_in",
            False
        ),
        "username": session.get(
            "username"
        ),
        "owner": current_is_owner(),
        "role_id": session.get(
            "role_id"
        )
    })


# =========================================================
# API - BOTS
# =========================================================

@app.route("/api/bots")
def api_bots():

    return jsonify({
        "ok": True,
        "bots": get_all_bots()
    })


@app.route("/api/bots/<int:bot_number>")
def api_bot(bot_number):

    bots = get_all_bots()

    for bot in bots:

        if bot["number"] == bot_number:

            return jsonify({
                "ok": True,
                "bot": bot
            })

    return jsonify({
        "ok": False,
        "error": "البوت غير موجود"
    }), 404


# =========================================================
# API - SYSTEMS
# =========================================================

@app.route("/api/systems")
def api_systems():

    return jsonify({
        "ok": True,
        "systems": SYSTEMS
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

    system = get_system(system_id)

    if not system:

        return jsonify({
            "ok": False,
            "error": "النظام غير موجود"
        }), 404

    bots = get_all_bots()

    bot = next(
        (
            b for b in bots
            if b["number"] == bot_number
        ),
        None
    )

    if not bot:

        return jsonify({
            "ok": False,
            "error": "البوت غير موجود"
        }), 404

    conn = get_db()

    row = conn.execute("""
        SELECT settings
        FROM system_settings
        WHERE bot_id = ?
        AND system = ?
    """, (
        bot["id"],
        system_id
    )).fetchone()

    conn.close()

    settings = {}

    if row:
        settings = json_load(
            row["settings"],
            {}
        )

    return jsonify({
        "ok": True,
        "bot": bot,
        "system": system,
        "settings": settings
    })


# =========================================================
# API - APPLY SYSTEM TO MULTIPLE BOTS
# =========================================================

@app.route(
    "/api/apply",
    methods=["POST"]
)
def apply_changes():

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

    if not isinstance(
        bot_numbers,
        list
    ):

        return jsonify({
            "ok": False,
            "error": "قائمة البوتات غير صحيحة"
        }), 400

    if not bot_numbers:

        return jsonify({
            "ok": False,
            "error": "حدد بوتًا واحدًا على الأقل"
        }), 400

    system = get_system(
        system_id
    )

    if not system:

        return jsonify({
            "ok": False,
            "error": "النظام غير موجود"
        }), 404

    permission = (
        f"{system_id}.manage"
    )

    if not has_permission(
        permission
    ):

        return jsonify({
            "ok": False,
            "error": "ليس لديك صلاحية لتعديل هذا النظام"
        }), 403

    bots = get_all_bots()

    bot_map = {
        bot["number"]: bot
        for bot in bots
    }

    conn = get_db()

    applied = []
    failed = []

    for number in bot_numbers:

        try:

            number = int(number)

            bot = bot_map.get(
                number
            )

            if not bot:

                failed.append({
                    "number": number,
                    "reason": "البوت غير موجود"
                })

                continue

            if not bot.get("id"):

                failed.append({
                    "number": number,
                    "reason": "البوت غير متصل"
                })

                continue

            conn.execute("""
                INSERT INTO system_settings(
                    bot_id,
                    system,
                    settings,
                    updated_at
                )
                VALUES(?, ?, ?, ?)
                ON CONFLICT(bot_id, system)
                DO UPDATE SET
                    settings = excluded.settings,
                    updated_at = excluded.updated_at
            """, (
                bot["id"],
                system_id,
                json.dumps(
                    settings,
                    ensure_ascii=False
                ),
                utc_now()
            ))

            applied.append({
                "number": number,
                "bot_id": bot["id"],
                "name": bot["name"]
            })

        except Exception as exc:

            failed.append({
                "number": number,
                "reason": str(exc)
            })

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "system": system_id,
        "applied": applied,
        "failed": failed
    })


# =========================================================
# OWNER - ROLES
# =========================================================

@app.route(
    "/api/owner/roles",
    methods=["GET"]
)
def owner_roles():

    if not current_is_owner():

        return jsonify({
            "ok": False,
            "error": "Owner فقط"
        }), 403

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM dashboard_roles
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    roles = []

    for row in rows:

        roles.append({
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "permissions": json_load(
                row["permissions"],
                []
            ),
            "created_at": row["created_at"]
        })

    return jsonify({
        "ok": True,
        "roles": roles
    })


@app.route(
    "/api/owner/roles",
    methods=["POST"]
)
def create_role():

    if not current_is_owner():

        return jsonify({
            "ok": False,
            "error": "Owner فقط"
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
            "error": "اسم الرتبة مطلوب"
        }), 400

    if not isinstance(
        permissions,
        list
    ):

        permissions = []

    permissions = [
        p for p in permissions
        if p in PERMISSIONS
    ]

    conn = get_db()

    cur = conn.execute("""
        INSERT INTO dashboard_roles(
            name,
            description,
            permissions,
            created_at
        )
        VALUES(?, ?, ?, ?)
    """, (
        name,
        description,
        json.dumps(
            permissions,
            ensure_ascii=False
        ),
        utc_now()
    ))

    conn.commit()

    role_id = cur.lastrowid

    conn.close()

    return jsonify({
        "ok": True,
        "role_id": role_id
    })


@app.route(
    "/api/owner/roles/<int:role_id>",
    methods=["PUT"]
)
def update_role(role_id):

    if not current_is_owner():

        return jsonify({
            "ok": False,
            "error": "Owner فقط"
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

    if not isinstance(
        permissions,
        list
    ):

        permissions = []

    permissions = [
        p for p in permissions
        if p in PERMISSIONS
    ]

    conn = get_db()

    conn.execute("""
        UPDATE dashboard_roles
        SET
            name = ?,
            description = ?,
            permissions = ?
        WHERE id = ?
    """, (
        name,
        description,
        json.dumps(
            permissions,
            ensure_ascii=False
        ),
        role_id
    ))

    conn.commit()
    conn.close()

    return jsonify({
        "ok": True
    })


@app.route(
    "/api/owner/roles/<int:role_id>",
    methods=["DELETE"]
)
def delete_role(role_id):

    if not current_is_owner():

        return jsonify({
            "ok": False,
            "error": "Owner فقط"
        }), 403

    conn = get_db()

    conn.execute("""
        UPDATE dashboard_users
        SET role_id = NULL
        WHERE role_id = ?
    """, (role_id,))

    conn.execute("""
        DELETE FROM dashboard_roles
        WHERE id = ?
    """, (role_id,))

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

    if not current_is_owner():

        return jsonify({
            "ok": False,
            "error": "Owner فقط"
        }), 403

    return jsonify({
        "ok": True,
        "permissions": PERMISSIONS
    })


# =========================================================
# OWNER - USERS
# =========================================================

@app.route(
    "/api/owner/users",
    methods=["GET"]
)
def owner_users():

    if not current_is_owner():

        return jsonify({
            "ok": False,
            "error": "Owner فقط"
        }), 403

    conn = get_db()

    rows = conn.execute("""
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
    """).fetchall()

    conn.close()

    users = []

    for row in rows:

        users.append({
            "id": row["id"],
            "username": row["username"],
            "role_id": row["role_id"],
            "role_name": row["role_name"]
        })

    return jsonify({
        "ok": True,
        "users": users
    })


@app.route(
    "/api/owner/users",
    methods=["POST"]
)
def create_user():

    if not current_is_owner():

        return jsonify({
            "ok": False,
            "error": "Owner فقط"
        }), 403

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
            "error": "اسم المستخدم مطلوب"
        }), 400

    conn = get_db()

    try:

        conn.execute("""
            INSERT INTO dashboard_users(
                username,
                role_id,
                created_at
            )
            VALUES(?, ?, ?)
        """, (
            username,
            role_id,
            utc_now()
        ))

        conn.commit()

    except sqlite3.IntegrityError:

        conn.close()

        return jsonify({
            "ok": False,
            "error": "المستخدم موجود مسبقًا"
        }), 409

    conn.close()

    return jsonify({
        "ok": True
    })


@app.route(
    "/api/owner/users/<int:user_id>",
    methods=["DELETE"]
)
def delete_user(user_id):

    if not current_is_owner():

        return jsonify({
            "ok": False,
            "error": "Owner فقط"
        }), 403

    conn = get_db()

    conn.execute("""
        DELETE FROM dashboard_users
        WHERE id = ?
    """, (user_id,))

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

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM sections
        ORDER BY id ASC
    """).fetchall()

    conn.close()

    return jsonify({
        "ok": True,
        "sections": [
            dict(row)
            for row in rows
        ]
    })


@app.route(
    "/api/sections",
    methods=["POST"]
)
def create_section():

    if not has_permission(
        "owner.manage"
    ):

        return jsonify({
            "ok": False,
            "error": "ليس لديك صلاحية"
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
            "error": "اسم القسم مطلوب"
        }), 400

    conn = get_db()

    conn.execute("""
        INSERT INTO sections(
            name,
            icon,
            description,
            created_at
        )
        VALUES(?, ?, ?, ?)
    """, (
        name,
        icon,
        description,
        utc_now()
    ))

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
        "status": "online",
        "name": APP_NAME,
        "version": VERSION,
        "bots": len(
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
        "error": "Not Found"
    }), 404


@app.errorhandler(500)
def server_error(error):

    return jsonify({
        "ok": False,
        "error": "Internal Server Error"
    }), 500


# =========================================================
# STARTUP
# =========================================================

def startup():

    init_db()

    print("=" * 60)
    print("CT DASHBOARD")
    print("=" * 60)
    print(f"Version: {VERSION}")
    print(f"Port: {PORT}")

    tokens = get_bot_tokens()

    print(
        f"Bot Environment Variables: {len(tokens)}"
    )

    for item in tokens:

        print(
            f"  • BOT_TOKEN_{item['number']} detected"
        )

    print("=" * 60)


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

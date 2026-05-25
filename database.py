import json
import sqlite3
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

from config import ALL_PERMISSION_KEYS, DEFAULT_SETTINGS

DB_PATH = Path(__file__).parent / "amal_costs.db"

STAGE_TYPES = {
    "raw": "خام المحصول",
    "manufacturing": "تصنيع",
    "packing": "تعبئة وتغليف",
    "other": "أخرى",
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_setting(key: str, default: str = "") -> str:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def get_all_settings() -> dict:
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    out = dict(DEFAULT_SETTINGS)
    for r in rows:
        out[r["key"]] = r["value"]
    return out


def set_setting(key: str, value: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )


def next_serial(prefix_key: str, next_key: str) -> str:
    prefix = get_setting(prefix_key, "DOC")
    num = int(get_setting(next_key, "1") or "1")
    serial = f"{prefix}-{num:05d}"
    set_setting(next_key, str(num + 1))
    return serial


def init_db():
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                permissions TEXT NOT NULL DEFAULT '[]',
                is_system INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL DEFAULT '',
                role_id INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (role_id) REFERENCES roles(id)
            );

            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                unit TEXT NOT NULL DEFAULT 'كجم',
                quantity REAL NOT NULL DEFAULT 1,
                raw_price_per_unit REAL NOT NULL DEFAULT 0,
                export_price_per_unit REAL NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS cost_stages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                stage_type TEXT NOT NULL DEFAULT 'manufacturing',
                name TEXT NOT NULL,
                cost_per_unit REAL NOT NULL DEFAULT 0,
                lump_sum REAL NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS treasury_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                move_date TEXT NOT NULL,
                move_type TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                reference_no TEXT,
                created_by INTEGER,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS admin_fund_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                move_date TEXT NOT NULL,
                move_type TEXT NOT NULL,
                amount REAL NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                reference_no TEXT,
                created_by INTEGER,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                account_type TEXT NOT NULL DEFAULT 'expense',
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS journal_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL,
                serial_number TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_by INTEGER,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS journal_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                debit REAL NOT NULL DEFAULT 0,
                credit REAL NOT NULL DEFAULT 0,
                line_note TEXT,
                FOREIGN KEY (entry_id) REFERENCES journal_entries(id) ON DELETE CASCADE,
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            );

            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                serial_number TEXT NOT NULL UNIQUE,
                invoice_date TEXT NOT NULL,
                invoice_type TEXT NOT NULL DEFAULT 'sales',
                party_name TEXT NOT NULL,
                party_phone TEXT,
                notes TEXT,
                subtotal REAL NOT NULL DEFAULT 0,
                discount REAL NOT NULL DEFAULT 0,
                tax REAL NOT NULL DEFAULT 0,
                grand_total REAL NOT NULL DEFAULT 0,
                created_by INTEGER,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                quantity REAL NOT NULL DEFAULT 1,
                unit_price REAL NOT NULL DEFAULT 0,
                line_total REAL NOT NULL DEFAULT 0,
                FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS description_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                context TEXT NOT NULL DEFAULT 'admin_fund',
                label TEXT NOT NULL,
                use_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(context, label)
            );

            CREATE TABLE IF NOT EXISTS sack_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                size_kg REAL NOT NULL DEFAULT 0,
                notes TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS sack_movements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sack_type_id INTEGER NOT NULL,
                move_date TEXT NOT NULL,
                move_type TEXT NOT NULL,
                quantity REAL NOT NULL DEFAULT 0,
                weight_kg REAL NOT NULL DEFAULT 0,
                description TEXT,
                created_by INTEGER,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (sack_type_id) REFERENCES sack_types(id),
                FOREIGN KEY (created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS truck_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date TEXT NOT NULL,
                direction TEXT NOT NULL,
                plate_number TEXT NOT NULL,
                description TEXT,
                scale_weight REAL NOT NULL DEFAULT 0,
                attachment_path TEXT,
                created_by INTEGER,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (created_by) REFERENCES users(id)
            );
            """
        )
        conn.execute(
            "UPDATE admin_fund_movements SET move_type='out' WHERE move_type='out_to_manager'"
        )
        conn.execute(
            "UPDATE admin_fund_movements SET move_type='in' WHERE move_type='in_from_manager'"
        )
        _seed_defaults(conn)


def _seed_defaults(conn):
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?,?)", (k, v)
        )

    admin_role = conn.execute(
        "SELECT id FROM roles WHERE name='مدير النظام'"
    ).fetchone()
    if not admin_role:
        perms = json.dumps(ALL_PERMISSION_KEYS, ensure_ascii=False)
        cur = conn.execute(
            "INSERT INTO roles (name, permissions, is_system) VALUES (?,?,1)",
            ("مدير النظام", perms),
        )
        role_id = cur.lastrowid
    else:
        role_id = admin_role["id"]
        existing = json.loads(
            conn.execute("SELECT permissions FROM roles WHERE id=?", (role_id,)).fetchone()[
                "permissions"
            ]
            or "[]"
        )
        merged = list(set(existing) | set(ALL_PERMISSION_KEYS))
        conn.execute(
            "UPDATE roles SET permissions=? WHERE id=?",
            (json.dumps(merged, ensure_ascii=False), role_id),
        )

    if not conn.execute("SELECT id FROM users WHERE username='admin'").fetchone():
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role_id) VALUES (?,?,?,?)",
            (
                "admin",
                generate_password_hash("admin123"),
                "مدير النظام",
                role_id,
            ),
        )

    if conn.execute("SELECT COUNT(*) c FROM accounts").fetchone()["c"] == 0:
        defaults = [
            ("1000", "الخزينة النقدية", "asset"),
            ("1100", "صندوق مدير الإدارة", "asset"),
            ("4000", "إيرادات المبيعات", "income"),
            ("5000", "مصروفات تشغيلية", "expense"),
            ("5100", "مصروفات مدير الإدارة", "expense"),
        ]
        for code, name, t in defaults:
            conn.execute(
                "INSERT INTO accounts (code, name, account_type) VALUES (?,?,?)",
                (code, name, t),
            )

    default_labels = [
        ("admin_fund", "سلفة تشغيل"),
        ("admin_fund", "مصروفات مكتب"),
        ("admin_fund", "نثرية يومية"),
        ("admin_fund", "تسوية حساب"),
        ("admin_fund", "مرتجع"),
        ("treasury", "تحصيل مبيعات"),
        ("treasury", "سداد مورد"),
    ]
    for ctx, lbl in default_labels:
        conn.execute(
            "INSERT OR IGNORE INTO description_presets (context, label) VALUES (?,?)",
            (ctx, lbl),
        )


def get_description_presets(context: str, query: str = "") -> list:
    with get_db() as conn:
        q = "SELECT label FROM description_presets WHERE context=? OR context='all'"
        params = [context]
        if query:
            q += " AND label LIKE ?"
            params.append(f"%{query}%")
        q += " ORDER BY use_count DESC, label ASC LIMIT 30"
        return [r["label"] for r in conn.execute(q, params).fetchall()]


def add_description_preset(context: str, label: str) -> bool:
    label = label.strip()
    if not label:
        return False
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO description_presets (context, label) VALUES (?,?)",
            (context, label),
        )
    return True


def bump_preset_usage(context: str, label: str):
    label = label.strip()
    if not label:
        return
    with get_db() as conn:
        conn.execute(
            "UPDATE description_presets SET use_count = use_count + 1 WHERE context=? AND label=?",
            (context, label),
        )
        if conn.total_changes == 0:
            conn.execute(
                "INSERT INTO description_presets (context, label, use_count) VALUES (?,?,1)",
                (context, label),
            )


def stage_label(stage_type: str) -> str:
    return STAGE_TYPES.get(stage_type, stage_type)


def compute_totals(product: dict, stages: list) -> dict:
    qty = float(product["quantity"] or 0)
    raw_unit = float(product["raw_price_per_unit"] or 0)
    export_unit = float(product["export_price_per_unit"] or 0)

    raw_total = raw_unit * qty
    stages_detail = []
    stages_total = 0.0

    for s in stages:
        per_unit = float(s["cost_per_unit"] or 0)
        lump = float(s["lump_sum"] or 0)
        line = per_unit * qty + lump
        stages_detail.append(
            {
                **dict(s),
                "line_total": line,
                "type_label": stage_label(s["stage_type"]),
            }
        )
        stages_total += line

    total_cost = raw_total + stages_total
    export_total = export_unit * qty
    margin = export_total - total_cost
    margin_pct = (margin / export_total * 100) if export_total else 0
    cost_pct_of_export = (total_cost / export_total * 100) if export_total else 0

    return {
        "quantity": qty,
        "raw_total": raw_total,
        "stages_detail": stages_detail,
        "stages_total": stages_total,
        "total_cost": total_cost,
        "export_total": export_total,
        "margin": margin,
        "margin_pct": margin_pct,
        "cost_pct_of_export": cost_pct_of_export,
        "profitable": margin >= 0,
    }


def verify_user(username: str, password: str):
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT u.*, r.name as role_name, r.permissions
            FROM users u JOIN roles r ON u.role_id = r.id
            WHERE u.username=? AND u.active=1
            """,
            (username,),
        ).fetchone()
    if not row or not check_password_hash(row["password_hash"], password):
        return None
    u = dict(row)
    u["permissions"] = json.loads(row["permissions"] or "[]")
    return u


def get_role_permissions(role_id: int) -> list:
    with get_db() as conn:
        row = conn.execute(
            "SELECT permissions FROM roles WHERE id=?", (role_id,)
        ).fetchone()
    return json.loads(row["permissions"]) if row else []

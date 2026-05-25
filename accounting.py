from database import get_db


def treasury_balance(before_date: str | None = None) -> float:
    with get_db() as conn:
        q = "SELECT move_type, SUM(amount) as s FROM treasury_movements"
        params = []
        if before_date:
            q += " WHERE move_date < ?"
            params.append(before_date)
        q += " GROUP BY move_type"
        rows = conn.execute(q, params).fetchall()
    bal = 0.0
    for r in rows:
        if r["move_type"] == "in":
            bal += float(r["s"])
        else:
            bal -= float(r["s"])
    return bal


def treasury_movements(date_from: str | None = None, date_to: str | None = None):
    with get_db() as conn:
        q = """
            SELECT t.*, u.full_name as creator_name
            FROM treasury_movements t
            LEFT JOIN users u ON t.created_by = u.id
            WHERE 1=1
        """
        params = []
        if date_from:
            q += " AND t.move_date >= ?"
            params.append(date_from)
        if date_to:
            q += " AND t.move_date <= ?"
            params.append(date_to)
        q += " ORDER BY t.move_date DESC, t.id DESC"
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def treasury_summary(date_from: str | None, date_to: str | None) -> dict:
    moves = treasury_movements(date_from, date_to)
    total_in = sum(m["amount"] for m in moves if m["move_type"] == "in")
    total_out = sum(m["amount"] for m in moves if m["move_type"] == "out")
    opening = treasury_balance(date_from) if date_from else 0.0
    return {
        "movements": moves,
        "total_in": total_in,
        "total_out": total_out,
        "net": total_in - total_out,
        "opening": opening,
        "closing": opening + total_in - total_out,
        "count": len(moves),
    }


def admin_fund_movements(date_from: str | None = None, date_to: str | None = None):
    with get_db() as conn:
        q = """
            SELECT a.*, u.full_name as creator_name
            FROM admin_fund_movements a
            LEFT JOIN users u ON a.created_by = u.id
            WHERE 1=1
        """
        params = []
        if date_from:
            q += " AND a.move_date >= ?"
            params.append(date_from)
        if date_to:
            q += " AND a.move_date <= ?"
            params.append(date_to)
        q += " ORDER BY a.move_date DESC, a.id DESC"
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def _admin_is_out(move_type: str) -> bool:
    return move_type in ("out", "out_to_manager")


def _admin_is_in(move_type: str) -> bool:
    return move_type in ("in", "in_from_manager")


def admin_fund_summary(date_from: str | None, date_to: str | None) -> dict:
    moves = admin_fund_movements(date_from, date_to)
    total_out = sum(m["amount"] for m in moves if _admin_is_out(m["move_type"]))
    total_in = sum(m["amount"] for m in moves if _admin_is_in(m["move_type"]))
    return {
        "movements": moves,
        "total_out": total_out,
        "total_in": total_in,
        "out_to_manager": total_out,
        "in_from_manager": total_in,
        "balance_effect": total_in - total_out,
        "count": len(moves),
    }


def dashboard_stats() -> dict:
    with get_db() as conn:
        products = conn.execute("SELECT COUNT(*) c FROM products").fetchone()["c"]
        invoices = conn.execute("SELECT COUNT(*) c FROM invoices").fetchone()["c"]
        journals = conn.execute("SELECT COUNT(*) c FROM journal_entries").fetchone()["c"]
    return {
        "treasury_balance": treasury_balance(),
        "admin_net": admin_fund_summary(None, None)["balance_effect"],
        "products_count": products,
        "invoices_count": invoices,
        "journals_count": journals,
    }


def get_accounts(active_only=True):
    with get_db() as conn:
        q = "SELECT * FROM accounts"
        if active_only:
            q += " WHERE active=1"
        q += " ORDER BY code"
        return [dict(r) for r in conn.execute(q).fetchall()]


def get_journal_entries(limit=50):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT e.*, u.full_name as creator_name
            FROM journal_entries e
            LEFT JOIN users u ON e.created_by = u.id
            ORDER BY e.entry_date DESC, e.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_journal_lines(entry_id: int):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT l.*, a.code, a.name as account_name
            FROM journal_lines l
            JOIN accounts a ON l.account_id = a.id
            WHERE l.entry_id=?
            """,
            (entry_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_invoice(invoice_id: int):
    with get_db() as conn:
        inv = conn.execute(
            "SELECT * FROM invoices WHERE id=?", (invoice_id,)
        ).fetchone()
        if not inv:
            return None, []
        items = conn.execute(
            "SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY id",
            (invoice_id,),
        ).fetchall()
    return dict(inv), [dict(i) for i in items]

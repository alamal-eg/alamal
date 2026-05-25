from database import get_db

SACK_MOVE_TYPES = {"in": "وارد", "out": "صادر"}
TRUCK_DIRECTIONS = {"in": "دخول", "out": "خروج"}


def get_sack_types():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM sack_types WHERE active=1 ORDER BY size_kg, name"
        ).fetchall()
    return [dict(r) for r in rows]


def sack_balances():
    types = get_sack_types()
    with get_db() as conn:
        for t in types:
            rows = conn.execute(
                """
                SELECT move_type, SUM(quantity) q, SUM(weight_kg) w
                FROM sack_movements WHERE sack_type_id=? GROUP BY move_type
                """,
                (t["id"],),
            ).fetchall()
            qty_in = qty_out = kg_in = kg_out = 0.0
            for r in rows:
                if r["move_type"] == "in":
                    qty_in = float(r["q"] or 0)
                    kg_in = float(r["w"] or 0)
                else:
                    qty_out = float(r["q"] or 0)
                    kg_out = float(r["w"] or 0)
            t["qty_in"] = qty_in
            t["qty_out"] = qty_out
            t["qty_balance"] = qty_in - qty_out
            t["kg_in"] = kg_in
            t["kg_out"] = kg_out
            t["kg_balance"] = kg_in - kg_out
    return types


def sack_movements(type_id: int | None = None, date_from=None, date_to=None):
    with get_db() as conn:
        q = """
            SELECT m.*, t.name as type_name, t.size_kg
            FROM sack_movements m
            JOIN sack_types t ON m.sack_type_id = t.id
            WHERE 1=1
        """
        params = []
        if type_id:
            q += " AND m.sack_type_id=?"
            params.append(type_id)
        if date_from:
            q += " AND m.move_date >= ?"
            params.append(date_from)
        if date_to:
            q += " AND m.move_date <= ?"
            params.append(date_to)
        q += " ORDER BY m.move_date DESC, m.id DESC"
        return [dict(r) for r in conn.execute(q, params).fetchall()]


def get_truck_logs(date_from=None, date_to=None):
    with get_db() as conn:
        q = "SELECT * FROM truck_logs WHERE 1=1"
        params = []
        if date_from:
            q += " AND log_date >= ?"
            params.append(date_from)
        if date_to:
            q += " AND log_date <= ?"
            params.append(date_to)
        q += " ORDER BY log_date DESC, id DESC"
        return [dict(r) for r in conn.execute(q, params).fetchall()]

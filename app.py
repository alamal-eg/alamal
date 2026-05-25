import json
from datetime import date

import uuid
from pathlib import Path

from flask import (
    Flask,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import generate_password_hash

from accounting import (
    admin_fund_movements,
    admin_fund_summary,
    dashboard_stats,
    get_accounts,
    get_invoice,
    get_journal_entries,
    get_journal_lines,
    treasury_movements,
    treasury_summary,
)
from auth import (
    current_user,
    has_permission,
    load_user_context,
    login_required,
    login_user,
    logout_user,
    permission_required,
)
from branding import company_header, logo_url
from backup_util import create_backup
from config import (
    ACCOUNT_TYPES,
    ADMIN_FUND_MANAGER,
    ADMIN_FUND_TYPES,
    ALL_PERMISSION_KEYS,
    COMPANY_AR,
    PERMISSIONS,
    SACK_MOVE_TYPES,
    SECRET_KEY,
    TRUCK_DIRECTIONS,
    TREASURY_TYPES,
    UPLOAD_DIR,
)
from inventory import (
    get_sack_types,
    get_truck_logs,
    sack_balances,
    sack_movements,
)
from database import (
    add_description_preset,
    bump_preset_usage,
    compute_totals,
    get_all_settings,
    get_db,
    get_description_presets,
    get_role_permissions,
    init_db,
    next_serial,
    set_setting,
    stage_label,
    verify_user,
)
from exports import (
    export_excel,
    export_invoice_excel,
    export_invoice_pdf,
    export_movements_excel,
    export_movements_pdf,
    export_pdf,
)

app = Flask(__name__)
app.secret_key = SECRET_KEY


@app.before_request
def _before():
    init_db()
    load_user_context()


def _admin_move_label(move_type: str) -> str:
    if move_type in ("out", "out_to_manager"):
        return "صادر"
    if move_type in ("in", "in_from_manager"):
        return "وارد"
    return ADMIN_FUND_TYPES.get(move_type, move_type)


def _float(val, default=0.0):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _ctx(**extra):
    settings = get_all_settings()
    ctx = {
        "company": settings.get("company_name_ar", COMPANY_AR),
        "settings": settings,
        "header": company_header(settings),
        "logo_url": logo_url(),
        "user": current_user(),
        "permissions_list": PERMISSIONS,
    }
    ctx.update(extra)
    return ctx


@app.before_request
def require_login():
    ep = request.endpoint or ""
    if ep in ("login", "static") or ep.startswith("static"):
        return
    if not current_user():
        return redirect(url_for("login", next=request.url))


def _get_product(pid):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
        if not row:
            return None, []
        stages = conn.execute(
            "SELECT * FROM cost_stages WHERE product_id = ? ORDER BY sort_order, id",
            (pid,),
        ).fetchall()
        return dict(row), [dict(s) for s in stages]


# ─── Auth ───────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        user = verify_user(
            request.form.get("username", "").strip(),
            request.form.get("password", ""),
        )
        if user:
            login_user(user)
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("اسم المستخدم أو كلمة المرور غير صحيحة", "error")
    return render_template("login.html", **_ctx())


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))


# ─── Dashboard ──────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    if not has_permission("dashboard"):
        if has_permission("costs"):
            return redirect(url_for("costs_index"))
        if has_permission("treasury"):
            return redirect(url_for("treasury"))
        return redirect(url_for("login"))
    stats = dashboard_stats()
    return render_template("dashboard.html", stats=stats, **_ctx())


# ─── Costs (products) ───────────────────────────────────────────────

@app.route("/costs")
@permission_required("costs")
def costs_index():
    with get_db() as conn:
        products = conn.execute(
            "SELECT * FROM products ORDER BY created_at DESC"
        ).fetchall()
    items = []
    for p in products:
        p = dict(p)
        _, stages = _get_product(p["id"])
        items.append({"product": p, "totals": compute_totals(p, stages)})
    return render_template("index.html", items=items, **_ctx())


@app.route("/product/new", methods=["GET", "POST"])
@app.route("/product/<int:pid>/edit", methods=["GET", "POST"])
@permission_required("costs")
def product_form(pid=None):
    from database import STAGE_TYPES as ST

    product, stages = (None, [])
    if pid:
        product, stages = _get_product(pid)
        if not product:
            flash("المحصول غير موجود", "error")
            return redirect(url_for("costs_index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("اسم المحصول مطلوب", "error")
            return redirect(request.url)
        data = (
            name,
            request.form.get("unit", "كجم").strip() or "كجم",
            _float(request.form.get("quantity"), 1),
            _float(request.form.get("raw_price_per_unit")),
            _float(request.form.get("export_price_per_unit")),
            request.form.get("notes", "").strip(),
        )
        with get_db() as conn:
            if pid:
                conn.execute(
                    "UPDATE products SET name=?, unit=?, quantity=?, raw_price_per_unit=?, export_price_per_unit=?, notes=? WHERE id=?",
                    (*data, pid),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO products (name, unit, quantity, raw_price_per_unit, export_price_per_unit, notes) VALUES (?,?,?,?,?,?)",
                    data,
                )
                pid = cur.lastrowid
        flash("تم الحفظ", "success")
        return redirect(url_for("product_detail", pid=pid))

    totals = compute_totals(product or {}, stages) if product else None
    return render_template(
        "product_form.html",
        product=product,
        stages=stages,
        totals=totals,
        stage_types=ST,
        stage_label=stage_label,
        **_ctx(),
    )


@app.route("/product/<int:pid>")
@permission_required("costs")
def product_detail(pid):
    from database import STAGE_TYPES as ST

    product, stages = _get_product(pid)
    if not product:
        flash("غير موجود", "error")
        return redirect(url_for("costs_index"))
    return render_template(
        "product_detail.html",
        product=product,
        stages=stages,
        totals=compute_totals(product, stages),
        stage_types=ST,
        stage_label=stage_label,
        **_ctx(),
    )


@app.route("/product/<int:pid>/stage", methods=["POST"])
@permission_required("costs")
def add_stage(pid):
    name = request.form.get("name", "").strip()
    if not name:
        flash("اسم المرحلة مطلوب", "error")
        return redirect(url_for("product_detail", pid=pid))
    with get_db() as conn:
        mx = conn.execute(
            "SELECT COALESCE(MAX(sort_order),0) FROM cost_stages WHERE product_id=?",
            (pid,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO cost_stages (product_id, stage_type, name, cost_per_unit, lump_sum, sort_order) VALUES (?,?,?,?,?,?)",
            (
                pid,
                request.form.get("stage_type", "manufacturing"),
                name,
                _float(request.form.get("cost_per_unit")),
                _float(request.form.get("lump_sum")),
                mx + 1,
            ),
        )
    flash("تمت الإضافة", "success")
    return redirect(url_for("product_detail", pid=pid))


@app.route("/stage/<int:sid>/edit", methods=["POST"])
@permission_required("costs")
def edit_stage(sid):
    with get_db() as conn:
        row = conn.execute("SELECT product_id FROM cost_stages WHERE id=?", (sid,)).fetchone()
        if not row:
            return redirect(url_for("costs_index"))
        pid = row["product_id"]
        conn.execute(
            "UPDATE cost_stages SET stage_type=?, name=?, cost_per_unit=?, lump_sum=?, sort_order=? WHERE id=?",
            (
                request.form.get("stage_type"),
                request.form.get("name", "").strip(),
                _float(request.form.get("cost_per_unit")),
                _float(request.form.get("lump_sum")),
                int(request.form.get("sort_order", 0)),
                sid,
            ),
        )
    return redirect(url_for("product_detail", pid=pid))


@app.route("/stage/<int:sid>/delete", methods=["POST"])
@permission_required("costs")
def delete_stage(sid):
    with get_db() as conn:
        row = conn.execute("SELECT product_id FROM cost_stages WHERE id=?", (sid,)).fetchone()
        if row:
            conn.execute("DELETE FROM cost_stages WHERE id=?", (sid,))
            return redirect(url_for("product_detail", pid=row["product_id"]))
    return redirect(url_for("costs_index"))


@app.route("/product/<int:pid>/delete", methods=["POST"])
@permission_required("costs")
def delete_product(pid):
    with get_db() as conn:
        conn.execute("DELETE FROM products WHERE id=?", (pid,))
    flash("تم الحذف", "success")
    return redirect(url_for("costs_index"))


@app.route("/product/<int:pid>/export/<fmt>")
@permission_required("reports_export")
def export_report(pid, fmt):
    product, stages = _get_product(pid)
    if not product:
        return redirect(url_for("costs_index"))
    safe = "".join(c if c.isalnum() else "_" for c in product["name"])
    if fmt == "xlsx":
        return send_file(export_excel(product, stages), as_attachment=True, download_name=f"cost_{safe}.xlsx")
    if fmt == "pdf":
        return send_file(export_pdf(product, stages), as_attachment=True, download_name=f"cost_{safe}.pdf")
    return redirect(url_for("product_detail", pid=pid))


# ─── Treasury ───────────────────────────────────────────────────────

@app.route("/treasury", methods=["GET", "POST"])
@permission_required("treasury")
def treasury():
    if request.method == "POST":
        if request.form.get("action") == "add_preset":
            if add_description_preset("treasury", request.form.get("preset_label", "")):
                flash("تمت إضافة مسمى البيان", "success")
            return redirect(url_for("treasury", **request.args))
        desc = request.form.get("description", "").strip()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO treasury_movements (move_date, move_type, amount, description, reference_no, created_by) VALUES (?,?,?,?,?,?)",
                (
                    request.form.get("move_date", str(date.today())),
                    request.form.get("move_type", "in"),
                    _float(request.form.get("amount")),
                    desc,
                    request.form.get("reference_no", "").strip(),
                    g.user["id"],
                ),
            )
        if desc:
            bump_preset_usage("treasury", desc)
        flash("تم تسجيل الحركة", "success")
        return redirect(url_for("treasury", **request.args))

    df = request.args.get("date_from", "")
    dt = request.args.get("date_to", "")
    summary = treasury_summary(df or None, dt or None)
    return render_template(
        "treasury.html",
        summary=summary,
        types=TREASURY_TYPES,
        presets=get_description_presets("treasury"),
        date_from=df,
        date_to=dt,
        **_ctx(),
    )


@app.route("/treasury/export/<fmt>")
@permission_required("reports_export")
def treasury_export(fmt):
    df, dt = request.args.get("date_from"), request.args.get("date_to")
    s = treasury_summary(df or None, dt or None)
    serial = next_serial("report_prefix", "report_next")
    headers = ["التاريخ", "النوع", "المبلغ", "البيان", "مرجع"]
    rows = [
        [
            m["move_date"],
            TREASURY_TYPES.get(m["move_type"], m["move_type"]),
            m["amount"],
            m["description"],
            m.get("reference_no") or "",
        ]
        for m in s["movements"]
    ]
    summary = [
        ("رصيد افتتاحي", s["opening"]),
        ("إجمالي قبض", s["total_in"]),
        ("إجمالي صرف", s["total_out"]),
        ("صافي الفترة", s["net"]),
        ("رصيد ختامي", s["closing"]),
    ]
    title = "تقرير الخزينة اليومية"
    if fmt == "xlsx":
        return send_file(
            export_movements_excel(title, headers, rows, summary, serial),
            as_attachment=True,
            download_name=f"treasury_{serial}.xlsx",
        )
    return send_file(
        export_movements_pdf(title, headers, rows, summary, serial),
        as_attachment=True,
        download_name=f"treasury_{serial}.pdf",
    )


# ─── Admin fund ─────────────────────────────────────────────────────

@app.route("/admin-fund", methods=["GET", "POST"])
@permission_required("admin_fund")
def admin_fund():
    if request.method == "POST":
        action = request.form.get("action", "add_move")
        if action == "add_preset":
            label = request.form.get("preset_label", "").strip()
            if add_description_preset("admin_fund", label):
                flash(f"تمت إضافة مسمى البيان: {label}", "success")
            else:
                flash("أدخل مسمى البيان", "error")
            return redirect(url_for("admin_fund", **request.args))

        desc = request.form.get("description", "").strip()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO admin_fund_movements (move_date, move_type, amount, description, reference_no, created_by) VALUES (?,?,?,?,?,?)",
                (
                    request.form.get("move_date", str(date.today())),
                    request.form.get("move_type", "out"),
                    _float(request.form.get("amount")),
                    desc,
                    request.form.get("reference_no", "").strip(),
                    g.user["id"],
                ),
            )
        if desc:
            bump_preset_usage("admin_fund", desc)
        flash("تم التسجيل", "success")
        return redirect(url_for("admin_fund", **request.args))

    df, dt = request.args.get("date_from", ""), request.args.get("date_to", "")
    summary = admin_fund_summary(df or None, dt or None)
    presets = get_description_presets("admin_fund")
    return render_template(
        "admin_fund.html",
        summary=summary,
        types=ADMIN_FUND_TYPES,
        manager_name=ADMIN_FUND_MANAGER,
        presets=presets,
        date_from=df,
        date_to=dt,
        **_ctx(),
    )


@app.route("/api/presets/<context>")
@login_required
def api_presets(context):
    q = request.args.get("q", "").strip()
    return {"items": get_description_presets(context, q)}


@app.route("/admin-fund/export/<fmt>")
@permission_required("reports_export")
def admin_fund_export(fmt):
    df, dt = request.args.get("date_from"), request.args.get("date_to")
    s = admin_fund_summary(df or None, dt or None)
    serial = next_serial("report_prefix", "report_next")
    headers = ["التاريخ", "نوع الحركة", "المبلغ", "البيان", "مرجع"]
    rows = [
        [
            m["move_date"],
            _admin_move_label(m["move_type"]),
            m["amount"],
            m["description"],
            m.get("reference_no") or "",
        ]
        for m in s["movements"]
    ]
    summary = [
        ("إجمالي صادر", s["total_out"]),
        ("إجمالي وارد", s["total_in"]),
        ("صافي الحركة", s["balance_effect"]),
    ]
    title = f"كشف حركة صندوق {ADMIN_FUND_MANAGER}"
    if fmt == "xlsx":
        return send_file(
            export_movements_excel(title, headers, rows, summary, serial),
            as_attachment=True,
            download_name=f"admin_fund_{serial}.xlsx",
        )
    return send_file(
        export_movements_pdf(title, headers, rows, summary, serial),
        as_attachment=True,
        download_name=f"admin_fund_{serial}.pdf",
    )


# ─── Accounting ─────────────────────────────────────────────────────

@app.route("/accounting", methods=["GET", "POST"])
@permission_required("accounting")
def accounting():
    if request.method == "POST":
        desc = request.form.get("description", "").strip()
        entry_date = request.form.get("entry_date", str(date.today()))
        accounts = request.form.getlist("account_id")
        debits = request.form.getlist("debit")
        credits = request.form.getlist("credit")
        lines = []
        for aid, d, c in zip(accounts, debits, credits):
            d, c = _float(d), _float(c)
            if aid and (d > 0 or c > 0):
                lines.append((int(aid), d, c))
        if len(lines) < 2:
            flash("أدخل سطرين على الأقل (مدين ودائن)", "error")
        else:
            td = sum(l[1] for l in lines)
            tc = sum(l[2] for l in lines)
            if abs(td - tc) > 0.01:
                flash("مجموع المدين يجب أن يساوي مجموع الدائن", "error")
            else:
                serial = next_serial("report_prefix", "report_next")
                with get_db() as conn:
                    cur = conn.execute(
                        "INSERT INTO journal_entries (entry_date, serial_number, description, created_by) VALUES (?,?,?,?)",
                        (entry_date, serial, desc, g.user["id"]),
                    )
                    eid = cur.lastrowid
                    for aid, d, c in lines:
                        conn.execute(
                            "INSERT INTO journal_lines (entry_id, account_id, debit, credit) VALUES (?,?,?,?)",
                            (eid, aid, d, c),
                        )
                flash(f"تم قيد اليومية {serial}", "success")
                return redirect(url_for("accounting"))

    entries = get_journal_entries()
    enriched = []
    for e in entries:
        lines = get_journal_lines(e["id"])
        enriched.append({**e, "lines": lines})
    return render_template(
        "accounting.html",
        entries=enriched,
        accounts=get_accounts(),
        account_types=ACCOUNT_TYPES,
        **_ctx(),
    )


@app.route("/accounts", methods=["GET", "POST"])
@permission_required("accounting")
def accounts_manage():
    if request.method == "POST":
        with get_db() as conn:
            conn.execute(
                "INSERT INTO accounts (code, name, account_type) VALUES (?,?,?)",
                (
                    request.form.get("code", "").strip(),
                    request.form.get("name", "").strip(),
                    request.form.get("account_type", "expense"),
                ),
            )
        flash("تمت إضافة الحساب", "success")
    return render_template("accounts.html", accounts=get_accounts(False), account_types=ACCOUNT_TYPES, **_ctx())


# ─── Invoices ───────────────────────────────────────────────────────

@app.route("/invoices")
@permission_required("invoices")
def invoices_list():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM invoices ORDER BY invoice_date DESC, id DESC"
        ).fetchall()
    return render_template("invoices.html", invoices=[dict(r) for r in rows], **_ctx())


@app.route("/invoices/new", methods=["GET", "POST"])
@permission_required("invoices")
def invoice_new():
    if request.method == "POST":
        descs = request.form.getlist("item_desc")
        qtys = request.form.getlist("item_qty")
        prices = request.form.getlist("item_price")
        items = []
        subtotal = 0.0
        for d, q, p in zip(descs, qtys, prices):
            d = d.strip()
            if not d:
                continue
            q, p = _float(q, 1), _float(p)
            lt = q * p
            items.append((d, q, p, lt))
            subtotal += lt
        if not items:
            flash("أضف بنداً واحداً على الأقل", "error")
            return redirect(request.url)
        discount = _float(request.form.get("discount"))
        tax = _float(request.form.get("tax"))
        grand = subtotal - discount + tax
        serial = next_serial("invoice_prefix", "invoice_next")
        with get_db() as conn:
            cur = conn.execute(
                """
                INSERT INTO invoices (serial_number, invoice_date, invoice_type, party_name,
                party_phone, notes, subtotal, discount, tax, grand_total, created_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    serial,
                    request.form.get("invoice_date", str(date.today())),
                    request.form.get("invoice_type", "sales"),
                    request.form.get("party_name", "").strip(),
                    request.form.get("party_phone", "").strip(),
                    request.form.get("notes", "").strip(),
                    subtotal,
                    discount,
                    tax,
                    grand,
                    g.user["id"],
                ),
            )
            iid = cur.lastrowid
            for d, q, p, lt in items:
                conn.execute(
                    "INSERT INTO invoice_items (invoice_id, description, quantity, unit_price, line_total) VALUES (?,?,?,?,?)",
                    (iid, d, q, p, lt),
                )
        flash(f"تم إنشاء الفاتورة {serial}", "success")
        return redirect(url_for("invoice_view", iid=iid))

    return render_template("invoice_form.html", invoice=None, items=[], **_ctx())


@app.route("/invoices/<int:iid>")
@permission_required("invoices")
def invoice_view(iid):
    inv, items = get_invoice(iid)
    if not inv:
        flash("الفاتورة غير موجودة", "error")
        return redirect(url_for("invoices_list"))
    return render_template("invoice_view.html", invoice=inv, items=items, **_ctx())


@app.route("/invoices/<int:iid>/export/<fmt>")
@permission_required("reports_export")
def invoice_export(iid, fmt):
    inv, items = get_invoice(iid)
    if not inv:
        return redirect(url_for("invoices_list"))
    if fmt == "xlsx":
        return send_file(
            export_invoice_excel(inv, items),
            as_attachment=True,
            download_name=f"{inv['serial_number']}.xlsx",
        )
    return send_file(
        export_invoice_pdf(inv, items),
        as_attachment=True,
        download_name=f"{inv['serial_number']}.pdf",
    )


# ─── Users & settings ─────────────────────────────────────────────────

@app.route("/users", methods=["GET", "POST"])
@permission_required("users")
def users_manage():
    with get_db() as conn:
        if request.method == "POST":
            action = request.form.get("action")
            if action == "add_user":
                conn.execute(
                    "INSERT INTO users (username, password_hash, full_name, role_id) VALUES (?,?,?,?)",
                    (
                        request.form.get("username", "").strip(),
                        generate_password_hash(request.form.get("password", "123456")),
                        request.form.get("full_name", "").strip(),
                        int(request.form.get("role_id")),
                    ),
                )
                flash("تم إنشاء المستخدم", "success")
            elif action == "add_role":
                perms = request.form.getlist("permissions")
                conn.execute(
                    "INSERT INTO roles (name, permissions) VALUES (?,?)",
                    (
                        request.form.get("role_name", "").strip(),
                        json.dumps(perms, ensure_ascii=False),
                    ),
                )
                flash("تم إنشاء الدور", "success")
            elif action == "update_role":
                rid = int(request.form.get("role_id"))
                perms = request.form.getlist("permissions")
                conn.execute(
                    "UPDATE roles SET name=?, permissions=? WHERE id=? AND is_system=0",
                    (
                        request.form.get("role_name", "").strip(),
                        json.dumps(perms, ensure_ascii=False),
                        rid,
                    ),
                )
                flash("تم تحديث الصلاحيات", "success")
        users = conn.execute(
            """
            SELECT u.id, u.username, u.full_name, u.active, r.name as role_name, r.id as role_id
            FROM users u JOIN roles r ON u.role_id = r.id ORDER BY u.id
            """
        ).fetchall()
        roles = conn.execute("SELECT * FROM roles ORDER BY id").fetchall()

    roles_data = []
    for r in roles:
        rd = dict(r)
        rd["permissions"] = json.loads(r["permissions"] or "[]")
        roles_data.append(rd)

    return render_template(
        "users.html",
        users=[dict(u) for u in users],
        roles=roles_data,
        all_permissions=ALL_PERMISSION_KEYS,
        perm_labels=PERMISSIONS,
        **_ctx(),
    )


@app.route("/settings", methods=["GET", "POST"])
@permission_required("settings")
def settings_page():
    if request.method == "POST":
        for key in [
            "company_name_ar",
            "company_branch",
            "company_name_en",
            "invoice_prefix",
            "invoice_next",
            "report_prefix",
            "report_next",
            "receipt_prefix",
            "receipt_next",
        ]:
            if key in request.form:
                set_setting(key, request.form[key])
        flash("تم حفظ الإعدادات", "success")
        return redirect(url_for("settings_page"))

    return render_template("settings.html", **_ctx())


def _save_photo(file) -> str | None:
    if not file or not file.filename:
        return None
    ext = Path(file.filename).suffix.lower() or ".jpg"
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    file.save(UPLOAD_DIR / name)
    return name


@app.route("/uploads/<name>")
@login_required
def serve_upload(name):
    return send_from_directory(UPLOAD_DIR, name)


# ─── Sacks inventory ──────────────────────────────────────────────────

@app.route("/sacks", methods=["GET", "POST"])
@permission_required("sacks")
def sacks_index():
    if request.method == "POST":
        action = request.form.get("action")
        with get_db() as conn:
            if action == "add_type":
                conn.execute(
                    "INSERT INTO sack_types (name, size_kg, notes) VALUES (?,?,?)",
                    (
                        request.form.get("name", "").strip(),
                        _float(request.form.get("size_kg")),
                        request.form.get("notes", "").strip(),
                    ),
                )
                flash("تم إضافة صنف الخيش", "success")
            elif action == "add_move":
                conn.execute(
                    """
                    INSERT INTO sack_movements (sack_type_id, move_date, move_type, quantity, weight_kg, description, created_by)
                    VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        int(request.form.get("sack_type_id")),
                        request.form.get("move_date", str(date.today())),
                        request.form.get("move_type", "in"),
                        _float(request.form.get("quantity")),
                        _float(request.form.get("weight_kg")),
                        request.form.get("description", "").strip(),
                        g.user["id"],
                    ),
                )
                flash("تم تسجيل الحركة", "success")
        return redirect(url_for("sacks_index", **request.args))

    tid = request.args.get("type_id", "")
    filter_type = int(tid) if tid.isdigit() else None
    df, dt = request.args.get("date_from", ""), request.args.get("date_to", "")
    types = get_sack_types()
    return render_template(
        "sacks.html",
        types=types,
        balances=sack_balances(),
        movements=sack_movements(filter_type, df or None, dt or None),
        move_types=SACK_MOVE_TYPES,
        filter_type=filter_type,
        date_from=df,
        date_to=dt,
        **_ctx(),
    )


@app.route("/sacks/export/<fmt>")
@permission_required("reports_export")
def sacks_export(fmt):
    df, dt = request.args.get("date_from"), request.args.get("date_to")
    tid = request.args.get("type_id")
    type_id = int(tid) if tid and tid.isdigit() else None
    balances = sack_balances()
    moves = sack_movements(type_id, df or None, dt or None)
    serial = next_serial("report_prefix", "report_next")
    headers = ["صنف", "كجم/خيشة", "وارد", "صادر", "متبقي", "كجم متبقي"]
    rows = [
        [
            b["name"],
            b["size_kg"],
            b["qty_in"],
            b["qty_out"],
            b["qty_balance"],
            b["kg_balance"],
        ]
        for b in balances
    ]
    summary = [("عدد الحركات", len(moves))]
    title = "جرد مخزون الخيش"
    if fmt == "xlsx":
        return send_file(
            export_movements_excel(title, headers, rows, summary, serial),
            as_attachment=True,
            download_name=f"sacks_{serial}.xlsx",
        )
    return send_file(
        export_movements_pdf(title, headers, rows, summary, serial),
        as_attachment=True,
        download_name=f"sacks_{serial}.pdf",
    )


# ─── Trucks ─────────────────────────────────────────────────────────

@app.route("/trucks", methods=["GET", "POST"])
@permission_required("trucks")
def trucks_index():
    if request.method == "POST":
        photo = _save_photo(request.files.get("photo"))
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO truck_logs (log_date, direction, plate_number, description, scale_weight, attachment_path, created_by)
                VALUES (?,?,?,?,?,?,?)
                """,
                (
                    request.form.get("log_date", str(date.today())),
                    request.form.get("direction", "in"),
                    request.form.get("plate_number", "").strip(),
                    request.form.get("description", "").strip(),
                    _float(request.form.get("scale_weight")),
                    photo,
                    g.user["id"],
                ),
            )
        flash("تم تسجيل الشاحنة", "success")
        return redirect(url_for("trucks_index", **request.args))

    df, dt = request.args.get("date_from", ""), request.args.get("date_to", "")
    return render_template(
        "trucks.html",
        logs=get_truck_logs(df or None, dt or None),
        directions=TRUCK_DIRECTIONS,
        date_from=df,
        date_to=dt,
        **_ctx(),
    )


@app.route("/trucks/export/<fmt>")
@permission_required("reports_export")
def trucks_export(fmt):
    df, dt = request.args.get("date_from"), request.args.get("date_to")
    logs = get_truck_logs(df or None, dt or None)
    serial = next_serial("report_prefix", "report_next")
    headers = ["تاريخ", "اتجاه", "لوحة", "ميزان", "بيان"]
    rows = [
        [
            L["log_date"],
            TRUCK_DIRECTIONS.get(L["direction"], L["direction"]),
            L["plate_number"],
            L["scale_weight"],
            L["description"],
        ]
        for L in logs
    ]
    title = "سجل الشاحنات"
    if fmt == "xlsx":
        return send_file(
            export_movements_excel(title, headers, rows, [], serial),
            as_attachment=True,
            download_name=f"trucks_{serial}.xlsx",
        )
    return send_file(
        export_movements_pdf(title, headers, rows, [], serial),
        as_attachment=True,
        download_name=f"trucks_{serial}.pdf",
    )


@app.route("/backup", methods=["POST"])
@login_required
def backup_now():
    dest = create_backup()
    flash(f"تم حفظ نسخة احتياطية في: {dest.name}", "success")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/settings/logo", methods=["POST"])
@permission_required("settings")
def upload_logo():
    f = request.files.get("logo")
    if f and f.filename:
        from config import LOGO_PNG

        LOGO_PNG.parent.mkdir(parents=True, exist_ok=True)
        f.save(LOGO_PNG)
        flash("تم رفع الشعار (logo.png)", "success")
    else:
        flash("اختر ملف صورة", "error")
    return redirect(url_for("settings_page"))


if __name__ == "__main__":
    init_db()
    print("\n  شركة الأمل — النظام المتكامل")
    print("  http://127.0.0.1:5000")
    print("  المستخدم: admin / كلمة المرور: admin123\n")
    app.run(debug=True, port=5000)

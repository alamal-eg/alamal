import json
from functools import wraps

from flask import flash, g, redirect, request, session, url_for

from config import PERMISSIONS
from database import get_db, verify_user


def login_user(user: dict):
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["full_name"] = user["full_name"]
    session["role_name"] = user["role_name"]
    session["permissions"] = user["permissions"]


def logout_user():
    session.clear()


def current_user():
    if not session.get("user_id"):
        return None
    return {
        "id": session["user_id"],
        "username": session.get("username"),
        "full_name": session.get("full_name"),
        "role_name": session.get("role_name"),
        "permissions": session.get("permissions", []),
    }


def has_permission(perm: str) -> bool:
    user = current_user()
    if not user:
        return False
    return perm in user.get("permissions", [])


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)

    return wrapped


def permission_required(perm: str):
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapped(*args, **kwargs):
            if not has_permission(perm):
                flash("ليس لديك صلاحية للوصول إلى هذه الصفحة", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)

        return wrapped

    return decorator


def load_user_context():
    g.user = current_user()
    g.permissions = PERMISSIONS
    g.can = has_permission

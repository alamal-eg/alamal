from pathlib import Path

from config import COMPANY_AR, COMPANY_EN, LOGO_PNG, LOGO_SVG, STATIC_DIR


def logo_url():
    if LOGO_PNG.exists():
        return "/static/img/logo.png"
    return "/static/img/logo.svg"


def logo_path_for_pdf() -> Path | None:
    if LOGO_PNG.exists():
        return LOGO_PNG
    if LOGO_SVG.exists():
        return LOGO_SVG
    return None


def company_header(settings: dict | None = None) -> dict:
    from config import COMPANY_BRANCH, COMPANY_FULL

    settings = settings or {}
    return {
        "name_ar": settings.get("company_name_ar", COMPANY_FULL),
        "branch": settings.get("company_branch", COMPANY_BRANCH),
        "name_en": settings.get("company_name_en", COMPANY_EN),
        "logo": logo_url(),
    }

from pathlib import Path

BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
LOGO_PNG = STATIC_DIR / "img" / "logo.png"
LOGO_SVG = STATIC_DIR / "img" / "logo.svg"

COMPANY_AR = "الأمل للاستيراد والتصدير"
COMPANY_BRANCH = "فرع الغربية"
COMPANY_FULL = f"{COMPANY_AR} — {COMPANY_BRANCH}"
COMPANY_EN = "AL AMAL EXPORT OF AGRICULTURAL PRODUCTS"
COMPANY_SHORT = "الأمل"

SECRET_KEY = "amal-erp-2026-change-in-production"

PERMISSIONS = {
    "dashboard": "لوحة التحكم",
    "costs": "تكاليف المحاصيل",
    "treasury": "الخزينة اليومية",
    "admin_fund": "صندوق السيد محمد جمال",
    "accounting": "المحاسبة العامة",
    "invoices": "الفواتير",
    "reports_export": "تصدير التقارير",
    "users": "إدارة المستخدمين والصلاحيات",
    "settings": "الإعدادات والتسلسل",
    "sacks": "مخزون الخيش",
    "trucks": "دخول وخروج الشاحنات",
}

ALL_PERMISSION_KEYS = list(PERMISSIONS.keys())

DEFAULT_SETTINGS = {
    "company_name_ar": COMPANY_FULL,
    "company_branch": COMPANY_BRANCH,
    "company_name_en": COMPANY_EN,
    "invoice_prefix": "INV",
    "invoice_next": "1001",
    "report_prefix": "RPT",
    "report_next": "1",
    "receipt_prefix": "REC",
    "receipt_next": "1",
}

TREASURY_TYPES = {"in": "قبض (وارد للخزينة)", "out": "صرف (صادر من الخزينة)"}
ADMIN_FUND_MANAGER = "السيد محمد جمال"
ADMIN_FUND_TYPES = {
    "out": "صادر",
    "in": "وارد",
    "out_to_manager": "صادر",
    "in_from_manager": "وارد",
}
ACCOUNT_TYPES = {
    "asset": "أصول",
    "liability": "خصوم",
    "equity": "حقوق ملكية",
    "income": "إيرادات",
    "expense": "مصروفات",
}

UPLOAD_DIR = STATIC_DIR / "uploads"
SACK_MOVE_TYPES = {"in": "وارد", "out": "صادر"}
TRUCK_DIRECTIONS = {"in": "دخول", "out": "خروج"}

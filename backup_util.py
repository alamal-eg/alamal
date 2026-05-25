import shutil
from datetime import datetime
from pathlib import Path

from config import BASE_DIR, LOGO_PNG
from database import DB_PATH

BACKUP_DIR = BASE_DIR / "backups"


def create_backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"amal_backup_{stamp}"
    dest.mkdir(parents=True)
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, dest / DB_PATH.name)
    if LOGO_PNG.exists():
        shutil.copy2(LOGO_PNG, dest / "logo.png")
    uploads = BASE_DIR / "static" / "uploads"
    if uploads.exists():
        shutil.copytree(uploads, dest / "uploads", dirs_exist_ok=True)
    return dest

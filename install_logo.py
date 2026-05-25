"""نسخ الشعار الرسمي إلى static/img/logo.png — شغّل مرة واحدة إن لزم."""
import shutil
from pathlib import Path

SRC_CANDIDATES = [
    Path(__file__).parent / "logo_original.png",
    Path(
        r"C:\Users\mm\.cursor\projects\C-Users-mm-AppData-Local-Temp-daf187b4-bdbb-44f2-9edd-98d44bcc218d\assets\logo.png"
    ),
]
SRC = next((p for p in SRC_CANDIDATES if p.exists()), SRC_CANDIDATES[0])
DEST = Path(__file__).parent / "static" / "img" / "logo.png"

if SRC.exists():
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC, DEST)
    print(f"تم: {DEST}")
else:
    print("لم يُعثر على ملف الشعار. ارفعه من الإعدادات أو ضعه في static/img/logo.png")

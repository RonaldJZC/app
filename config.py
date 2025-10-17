from pathlib import Path
import os

APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent

def find_first(*candidates):
    for p in candidates:
        if p.exists():
            return str(p)
    return str(candidates[0])

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "cambia-esto-en-produccion")

    # Usuarios por UE (ya lo tenías)
    USERS_SHEET = os.environ.get("USERS_SHEET", "usuarios")
    USERS_FILE = find_first(
        APP_DIR / "data" / "UE PLIEGOS Y UE LIMA Y REGIONES.xlsx",
        PROJECT_DIR / "data" / "UE PLIEGOS Y UE LIMA Y REGIONES.xlsx",
    )

    # Maestro de IPRESS (nuevo)
    IPRESS_FILE = find_first(
        APP_DIR / "data" / "IPRESS.xlsx",
        APP_DIR / "data" / "IPRESS.xls",
        PROJECT_DIR / "data" / "IPRESS.xlsx",
        PROJECT_DIR / "data" / "IPRESS.xls",
    )

    # ⬇⬇ NUEVO: archivo SIGA
    SIGA_FILE = find_first(APP_DIR / "data" / "siga DLS 4.25.xlsx",
                           PROJECT_DIR / "data" / "siga DLS 4.25.xlsx")
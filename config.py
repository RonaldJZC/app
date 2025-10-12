from pathlib import Path
import os

APP_DIR = Path(__file__).resolve().parent        # ...\plataforma\app
PROJECT_DIR = APP_DIR.parent                     # ...\plataforma
FILENAME = "UE PLIEGOS Y UE LIMA Y REGIONES.xlsx"

CANDIDATES = [
    APP_DIR / "data" / FILENAME,                 # ...\plataforma\app\data\...
    PROJECT_DIR / "data" / FILENAME,             # ...\plataforma\data\...
]

def first_existing(paths):
    for p in paths:
        if p.exists():
            return str(p)
    # Si ninguno existe, devolvemos el primero para que el error sea claro
    return str(paths[0])

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "cambia-esto-en-produccion")
    DATA_FILE = first_existing(CANDIDATES)
    USERS_SHEET = os.environ.get("USERS_SHEET", "usuarios")

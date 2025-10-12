from pathlib import Path
import pandas as pd

REQUIRED_COLS = ["ue_codigo", "ue_nombre", "pliego_codigo", "pliego_nombre", "password_temp"]

def load_users(xlsx_path: str, sheet_name: str = "usuarios") -> dict:
    path = Path(xlsx_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el Excel de usuarios: {path}")

    df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
    faltantes = [c for c in REQUIRED_COLS if c not in df.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas en la hoja '{sheet_name}': {faltantes}")

    df = df.fillna("")
    for c in REQUIRED_COLS:
        df[c] = df[c].astype(str).str.strip()

    users = {}
    for _, row in df.iterrows():
        ue = row["ue_codigo"]
        if not ue:
            continue
        users[ue] = {
            "ue_codigo": ue,
            "ue_nombre": row["ue_nombre"],
            "pliego_codigo": row["pliego_codigo"],
            "pliego_nombre": row["pliego_nombre"],
            "password_temp": row["password_temp"],
        }
    return users

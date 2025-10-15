# app/excel_loader.py

from pathlib import Path
import re
import unicodedata
import pandas as pd

# =========================
# USUARIOS (login por UE)
# =========================

REQUIRED_COLS = ["ue_codigo", "ue_nombre", "pliego_codigo", "pliego_nombre", "password_temp"]

def load_users(xlsx_path: str, sheet_name: str = "usuarios") -> dict:
    """
    Lee el maestro de usuarios (UE -> datos de pliego y password temporal)
    Espera columnas: ue_codigo, ue_nombre, pliego_codigo, pliego_nombre, password_temp
    """
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

# =========================
# UTILIDADES DE NORMALIZACIÓN
# =========================

def _norm_header(s: str) -> str:
    """
    Normaliza encabezados: minúsculas, sin tildes, solo a-z0-9 (sin espacios).
    Sirve para identificar columnas aunque cambie el formato.
    """
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', s.lower())

def _ue_key(val) -> str:
    """
    Normaliza valores de 'Código UE' para usarlos como clave:
      - extrae todos los dígitos
      - si hay 4 o más, devuelve los ÚLTIMOS 4 (p.ej. '145-1685' -> '1685', '001685' -> '1685')
      - si hay menos, devuelve lo que haya
    """
    s = str(val).strip()
    if not s:
        return ""
    digits = re.sub(r'\D', '', s)
    if not digits:
        return ""
    return digits[-4:] if len(digits) >= 4 else digits


# =========================
# IPRESS (UE -> lista de EESS)
# =========================

def load_ipress(xlsx_path: str, sheet_name: str | None = None) -> dict:
    """
    Devuelve un dict agrupado por UE normalizada (últimos 4 dígitos):
      {
        '1685': [
           {'ipress_codigo': '0001234567', 'eess_nombre': 'C.M.I. SAN JOSÉ', 'eess_categoria': 'I-3'},
           ...
        ],
        ...
      }

    Soporta:
      - .xlsx (engine=openpyxl)
      - .xls  (engine=xlrd)

    Detecta encabezados de forma flexible. Se da PRIORIDAD a 'Código UE'.
    """
    path = Path(xlsx_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo IPRESS: {path}")

    engine = "openpyxl" if path.suffix.lower() == ".xlsx" else "xlrd"

    # Si no se especifica hoja, pandas puede devolver un dict de DataFrames
    raw = pd.read_excel(path, sheet_name=sheet_name if sheet_name else None, engine=engine)

    # ---------- elegir DataFrame (hoja) ----------
    if isinstance(raw, dict):
        if sheet_name and sheet_name in raw:
            df = raw[sheet_name]
        else:
            df = None
            for _, tmp in raw.items():
                if not isinstance(tmp, pd.DataFrame):
                    continue
                cols_norm = {_norm_header(c) for c in tmp.columns}

                has_ue = any(k in cols_norm for k in [
                    "codigoue", "uecodigo", "ue", "unidadejecutora", "uecod"
                ])
                has_ipress = any(k in cols_norm for k in [
                    "codigounico", "codigoipress", "ipress", "codipress", "ipresscodigo"
                ])
                has_name = any(k in cols_norm for k in [
                    "nombredelestablecimiento", "nombreestablecimiento",
                    "establecimientodesalud", "establecimiento", "eessnombre"
                ])

                if has_ue and has_ipress and has_name:
                    df = tmp
                    break
            if df is None:
                df = next(iter(raw.values()))
    else:
        df = raw

    # ---------- mapear encabezados reales ----------
    norm_cols = {_norm_header(c): c for c in df.columns}

    def pick(*candidates: str) -> str | None:
        for cand in candidates:
            k = _norm_header(cand)
            if k in norm_cols:
                return norm_cols[k]
        return None

    # *** PRIORIDAD a "Código UE" ***
    ue_col = pick(
        "codigo ue", "codigoue",              # prioridad
        "ue_codigo", "ue", "ue cod", "uecodigo", "unidad ejecutora", "unidadejecutora", "uecod"
    )
    ipr_col = pick(
        "codigo unico", "codigounico",        # 'Código Único' (IPRESS)
        "codigo ipress", "codigo_ipress", "ipress", "ipresscodigo", "codipress"
    )
    name_col = pick(
        "nombre del establecimiento", "nombre establecimiento", "nombredelestablecimiento",
        "establecimiento de salud", "establecimientodesalud", "establecimiento",
        "eess_nombre"
    )
    categ_col = pick(
        "categoria", "eess_categoria", "categoria eess", "categoría", "nivel"
    )

    if not (ue_col and ipr_col and name_col):
        raise ValueError("No se detectaron columnas obligatorias: (Código UE, Código Único/IPRESS, Nombre).")

    use_cols = [ue_col, ipr_col, name_col] + ([categ_col] if categ_col else [])
    df = df[use_cols].fillna("")

    new_names = ["ue_bruto", "ipress_codigo", "eess_nombre"] + (["eess_categoria"] if categ_col else [])
    df.columns = new_names

    # normaliza strings
    for c in new_names:
        df[c] = df[c].astype(str).str.strip()

    # agrega la clave de agrupación por UE (últimos 4 dígitos)
    df["ue_key"] = df["ue_bruto"].apply(_ue_key)

    # --- agrupar por UE normalizada ---
    by_ue: dict[str, list[dict[str, str]]] = {}
    for row in df.to_dict("records"):
        k = row.get("ue_key", "")
        rec = {
            "ue_key": k,  # guardado por si lo quieres usar/depurar
            "ipress_codigo": row.get("ipress_codigo", ""),
            "eess_nombre": row.get("eess_nombre", ""),
            "eess_categoria": row.get("eess_categoria", ""),
        }
        if k:
            by_ue.setdefault(k, []).append(rec)
        else:
            by_ue.setdefault("_sin_ue", []).append(rec)

    print("[IPRESS] columnas detectadas:",
          ue_col, "|", ipr_col, "|", name_col, "|", categ_col)
    total = sum(len(v) for v in by_ue.values() if v)
    print("[IPRESS] registros totales leídos:", total)

    return by_ue

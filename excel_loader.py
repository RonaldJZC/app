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
# UTIL: normalizar textos
# =========================

def _norm(s: str) -> str:
    """
    Normaliza a minúsculas, elimina acentos y deja solo a-z0-9.
    Sirve para detectar encabezados flexiblemente.
    """
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', s.lower())

def _ue_key(val) -> str:
    """Normaliza valores de 'Código UE' para usarlos como clave."""
    try:
        # 1685, 1685.0 -> "1685"
        if isinstance(val, (int, float)):
            return str(int(round(float(val))))
        s = str(val).strip()
        if not s:
            return ""
        # "1685.0" -> "1685"
        m = re.fullmatch(r'(\d+)(?:\.0+)?', s)
        if m:
            return m.group(1)
        # "145-1685" -> "1451685"   " 1685 " -> "1685"
        return re.sub(r'\D', '', s)
    except Exception:
        return ""

# =========================
# IPRESS (UE -> lista de EESS)
# =========================

def load_ipress(xlsx_path: str, sheet_name: str | None = None) -> dict:
    """
    Devuelve un dict:
      {
        '145-1685': [
           {'ipress_codigo': '0001234567', 'eess_nombre': 'C.S. SAN ROQUE', 'eess_categoria': 'I-3'},
           ...
        ],
        ...
      }

    Soporta:
      - .xlsx (engine=openpyxl)
      - .xls  (engine=xlrd)
    Si no se pasa sheet_name, autodetecta la hoja buscando columnas típicas.
    Reconoce encabezados como:
      - UE:           'ue_codigo', 'ue', 'unidad ejecutora', 'código ue', 'codigo ue', 'codigoue', 'uecod'
      - IPRESS:       'ipress_codigo', 'codigo ipress', 'ipress', 'codipress', 'codigo_ipress', 'código único', 'codigo unico', 'codigounico'
      - Establecimiento: 'eess_nombre', 'establecimiento de salud', 'establecimiento', 'nombre establecimiento', 'nombre del establecimiento'
      - Categoría (opcional): 'eess_categoria', 'categoria eess', 'categoria', 'categoría', 'nivel'
    """
    path = Path(xlsx_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo IPRESS: {path}")

    engine = "openpyxl" if path.suffix.lower() == ".xlsx" else "xlrd"

    # Si no se especifica hoja, pandas puede devolver un dict de DataFrames
    raw = pd.read_excel(path, sheet_name=sheet_name if sheet_name else None, engine=engine)

    # ---------- elegir DataFrame (hoja) ----------
    if isinstance(raw, dict):
        # 1) Si sheet_name viene y existe, úsala
        if sheet_name and sheet_name in raw:
            df = raw[sheet_name]
        else:
            # 2) Buscar hoja con columnas típicas (normalizadas)
            df = None
            for name, tmp in raw.items():
                if not isinstance(tmp, pd.DataFrame):
                    continue
                cols_norm = {_norm(c) for c in tmp.columns}

                has_ue = any(k in cols_norm for k in [
                    "uecodigo", "ue", "unidadejecutora", "uecod", "codigoue"
                ])
                has_ipress = any(k in cols_norm for k in [
                    "ipresscodigo", "codigoipress", "ipress", "codipress", "codigounico"
                ])
                has_name = any(k in cols_norm for k in [
                    "eessnombre", "establecimientodesalud", "establecimiento", "nombreestablecimiento", "nombredelestablecimiento"
                ])

                if has_ue and has_ipress and has_name:
                    df = tmp
                    break

            # 3) Si no se encontró por heurística, toma la primera hoja
            if df is None:
                df = next(iter(raw.values()))
    else:
        df = raw

    # ---------- mapear encabezados reales ----------
    norm_cols = {_norm(c): c for c in df.columns}

    def pick(*candidates: str) -> str | None:
        for cand in candidates:
            if not cand:
                continue
            k = _norm(cand)
            if k in norm_cols:
                return norm_cols[k]
        return None

    # Acepta tus encabezados reales con acentos/espacios
    ue_col = pick(
        "ue_codigo", "ue", "unidad ejecutora", "ue cod", "uecodigo",
        "código ue", "codigo ue", "codigoue"
    )
    ipr_col = pick(
        "ipress_codigo", "codigo ipress", "ipress", "codipress", "codigo_ipress",
        "código único", "codigo unico", "codigounico"
    )
    name_col = pick(
        "eess_nombre", "establecimiento de salud", "establecimiento",
        "nombre establecimiento", "nombre del establecimiento", "nombredelestablecimiento"
    )
    categ_col = pick(
        "eess_categoria", "categoria eess", "categoria", "categoría", "nivel"
    )

    if not (ue_col and ipr_col and name_col):
        raise ValueError("No se pudieron detectar columnas obligatorias (UE, IPRESS, Establecimiento). Revisa encabezados del archivo IPRESS.")

    use_cols = [ue_col, ipr_col, name_col] + ([categ_col] if categ_col else [])
    df = df[use_cols].fillna("")

    new_names = ["ue_codigo", "ipress_codigo", "eess_nombre"] + (["eess_categoria"] if categ_col else [])
    df.columns = new_names

    for c in new_names:
        df[c] = df[c].astype(str).str.strip()

    # --- agrupar por UE normalizada ---
    by_ue: dict[str, list[dict[str, str]]] = {}
    for row in df.to_dict("records"):
        ue_raw = row["ue_codigo"]
        ue_key = _ue_key(ue_raw)
        if not ue_key:
            continue
        by_ue.setdefault(ue_key, []).append({
            "ipress_codigo": row["ipress_codigo"],
            "eess_nombre": row["eess_nombre"],
            "eess_categoria": row.get("eess_categoria", ""),
        })
    return by_ue



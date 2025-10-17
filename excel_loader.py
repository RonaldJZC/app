# app/excel_loader.py

from pathlib import Path
import re
import unicodedata
import pandas as pd
from datetime import datetime  # <-- esto es para e tiempo del excel del siga 

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

    total = sum(len(v) for v in by_ue.values() if v)

    return by_ue

# --- PEGAR AQUÍ EL HELPER DE FECHAS ---
def _parse_excel_date(val):
    """
    Acepta:
    - '2020-08-03 00:00:00' (ISO, Y-m-d)  -> dayfirst=False
    - '03/08/2020' o '03-08-2020'         -> dayfirst=True
    - valores datetime de Excel/pandas
    Devuelve pandas.Timestamp o NaT.
    """
    if val is None or str(val).strip() == "":
        return pd.NaT

    # Si ya es datetime/Timestamp, devuélvelo directo
    if isinstance(val, (pd.Timestamp, datetime)):
        return pd.to_datetime(val, errors="coerce")

    s = str(val).strip()

    # ISO: 2020-08-03 ...
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return pd.to_datetime(s, dayfirst=False, errors="coerce")

    # D/M/Y o D-M-Y: 03/08/2020 o 3-8-2020
    if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{4}", s):
        return pd.to_datetime(s, dayfirst=True, errors="coerce")

    # Último recurso: que pandas infiera
    return pd.to_datetime(s, errors="coerce")

# Lector SIGA para llenar los 5 campos, lee la información de Denominacion del equipo,
# marca, modelo, serie/placa de rodaje y antiguedad.

def _norm_text_basic(s: str) -> str:
    t = unicodedata.normalize('NFKD', str(s))
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = t.lower().strip()
    t = re.sub(r'\s+', ' ', t)
    return t

#mejorando la busqueda y filtro por establecimiento 

_ABBR = [
    (r'\bcmi\b', 'centro materno infantil'),
    (r'\bcs\b', 'centro de salud'),
    (r'\bps\b', 'puesto de salud'),
    (r'\bcmi\.', 'centro materno infantil'),
    (r'\bcl\b', 'centro de salud'),  # por si acaso
]

def _norm_text(s: str) -> str:
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r'\s+', ' ', s)
    return s

def _expand_abbr(s: str) -> str:
    t = _norm_text(s)
    for pat, rep in _ABBR:
        t = re.sub(pat, rep, t)
    return t

def _site_key(name: str) -> str:
    # clave canónica para comparar sedes
    t = _expand_abbr(name)
    t = re.sub(r'[^a-z0-9 ]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def _n(s: str) -> str:
    """Normaliza encabezados: minúsculas, sin tildes, solo a-z0-9."""
    t = unicodedata.normalize('NFKD', str(s))
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', t.lower())

# instruccion para fechas de la antiguedad con fecha actual
def _years_from(date_val) -> str:
    """Devuelve años completos (floor) desde date_val hasta hoy. '' si no hay fecha."""
    try:
        ts = _parse_excel_date(date_val)  # ← USAR EL HELPER AQUÍ
        if pd.isna(ts):
            return ""
        delta_days = (pd.Timestamp.today().normalize() - ts.normalize()).days
        years = int(delta_days // 365.25)  # aprox
        return str(max(years, 0))
    except Exception:
        return ""

# ===== Índice SIGA mínimo con FECHA_ADQUISICION -> ANTIGÜEDAD =====
def load_siga_min(xlsx_path: str) -> dict:
    """
    Índice SIGA por:
      key = (sede_normalizada, codigo_patrimonial_sin_espacios)
      value = {denominacion, marca, modelo, serie, antiguedad}

    - Detecta múltiples nombres de columnas (flexible).
    - Si existe FECHA_ADQUISICION (o variantes), calcula antigüedad en años.
    """
    path = Path(xlsx_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el Excel SIGA: {path}")

    # Lee todas las hojas (dtype=str evita NaN y mantiene codigos como texto)
    book = pd.read_excel(path, sheet_name=None, dtype=str, engine="openpyxl")

    # Candidatos por columna (normalizados)
    C_SEDE   = {"nombresede","sede","establecimiento","eess","ipress","nombreipress","nombr e sede"}
    C_CODPAT = {"codigopatrimonial","codpatrimonial","codpat","codigopatrim","patrimonial","cp","codpatrimo"}
    C_DEN    = {
        "denominaciondelequipamientoexistente","denominaciondelbien","descripciondelbien",
        "descripcionbien","descripcion","denominacion","bienes","bien"
    }
    C_MARCA  = {"marca"}
    C_MODELO = {"modelo"}
    C_SERIE  = {"serie","nserie","numeroserie","ser ie","serieplacaderodaje","placa","serieplaca"}
    C_ANTI   = {"antiguedad","antiguedad(anios)","antiguedadanos","antiguedadyears"}
    C_FECHA  = {"fechaadquisicion","fecha adquisicion","fechadeadquisicion","fecadq","fechaadq","fec_adq"}

    def pick(map_cols: dict[str,str], *cand_sets: set[str]) -> str|None:
        """Devuelve el nombre REAL de la primera coincidencia."""
        keys = set(map_cols.keys())
        for cset in cand_sets:
            for c in cset:
                if c in keys:
                    return map_cols[c]
        # extra: si no hubo match exacto, intenta por 'contiene'
        for key_norm, real in map_cols.items():
            if any(any(c in key_norm for c in cset) for cset in cand_sets):
                return real
        return None

    chosen_df = None
    chosen_cols = None

    # Elige la primera hoja que tenga, al menos, sede y código patrimonial
    for sheet_name, df in book.items():
        if not isinstance(df, pd.DataFrame) or df.empty:
            continue
        # mapa: encabezado_normalizado -> encabezado_real
        colmap = {_n(c): c for c in df.columns}
        sede_col   = pick(colmap, C_SEDE)
        codpat_col = pick(colmap, C_CODPAT)
        if sede_col and codpat_col:
            chosen_df = df.fillna("")
            chosen_cols = colmap
            break

    if chosen_df is None:
        # diagnóstico: imprime encabezados por hoja
        print("[SIGA][debug] No se halló hoja con Sede y Código Patrimonial.")
        for sheet_name, df in book.items():
            if isinstance(df, pd.DataFrame):
                print(f"  - Hoja '{sheet_name}':", list(df.columns))
        raise ValueError("No se encontraron columnas básicas del SIGA. Revisa encabezados.")

    # Resolver todas las columnas
    sede_col   = pick(chosen_cols, C_SEDE)
    codpat_col = pick(chosen_cols, C_CODPAT)
    den_col    = pick(chosen_cols, C_DEN)    or ""
    marca_col  = pick(chosen_cols, C_MARCA)  or ""
    modelo_col = pick(chosen_cols, C_MODELO) or ""
    serie_col  = pick(chosen_cols, C_SERIE)  or ""
    anti_col   = pick(chosen_cols, C_ANTI)   or ""     # opcional
    fecha_col  = pick(chosen_cols, C_FECHA)  or ""     # opcional (para calcular antigüedad)

    # Indexado
    idx: dict[tuple[str,str], dict] = {}
    for _, r in chosen_df.iterrows():
        sede_key = _norm_text_basic(r.get(sede_col, ""))
        if not sede_key:
            continue
        cod = re.sub(r"\s+", "", str(r.get(codpat_col, "")))
        if not cod:
            continue

        # Datos base
        den   = str(r.get(den_col, ""))[:255] if den_col else ""
        marca = str(r.get(marca_col, ""))[:255] if marca_col else ""
        modelo= str(r.get(modelo_col, ""))[:255] if modelo_col else ""
        serie = str(r.get(serie_col, ""))[:255] if serie_col else ""

        # Antigüedad: preferimos FECHA_ADQUISICION si está; si no, tomamos la columna ANTIGÜEDAD tal cual.
        antig = ""
        if fecha_col:
            antig = _years_from(r.get(fecha_col, ""))
        if not antig and anti_col:
            antig = str(r.get(anti_col, ""))[:255]

        idx[(sede_key, cod)] = {
            "denominacion": den,
            "marca":        marca,
            "modelo":       modelo,
            "serie":        serie,
            "antiguedad":   antig,
        }

    print("[SIGA] registros indexados:", len(idx))
    return idx

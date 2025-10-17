# app/views.py
from flask import Blueprint, render_template, session, redirect, url_for, current_app, request, jsonify
import re
import unicodedata
from .excel_loader import _site_key

views_bp = Blueprint("views", __name__)

def is_logged_in():
    return "ue_codigo" in session

@views_bp.route("/")
def root():
    return redirect(url_for("views.formato8") if is_logged_in() else url_for("auth.login"))

@views_bp.route("/formato8")
def formato8():
    if not is_logged_in():
        return redirect(url_for("auth.login"))

    pliego_texto = f"{session.get('pliego_codigo','')} - {session.get('pliego_nombre','')}".strip()
    ue_texto     = f"{session.get('ue_codigo','')} - {session.get('ue_nombre','')}".strip()

    # Ya NO pasamos ipress_items (el cliente buscará al servidor con Enter)
    return render_template(
        "formato8.html",
        pliego_texto=pliego_texto,
        ue_texto=ue_texto,
    )

# ---------------------------
# API para buscar IPRESS
# ---------------------------

def _ue_candidates(ue_raw: str) -> list[str]:
    """Claves posibles de UE: '145-1685' -> ['1451685', '1685']."""
    if not ue_raw:
        return []
    full_digits = re.sub(r"\D", "", ue_raw)
    m = re.search(r"-(\d+)$", ue_raw)
    after_hyphen = m.group(1) if m else None
    return [c for c in [full_digits, after_hyphen] if c]

def _norm_txt(s: str) -> str:
    s = ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', s.lower())

@views_bp.post("/api/ipress/search")
def api_ipress_search():
    data = request.get_json(silent=True) or {}
    q = (data.get("q") or "").strip()
    if not q:
        return jsonify([])

    ipress_by_ue = current_app.config.get("IPRESS_BY_UE", {})
    ue_raw = session.get("ue_codigo", "")

    # UE normalizada: últimos 4 dígitos
    ue_digits = re.sub(r"\D", "", ue_raw or "")
    ue_key = ue_digits[-4:] if len(ue_digits) >= 4 else ue_digits

    # 1) pool por UE (lo correcto)
    pool = ipress_by_ue.get(ue_key, [])

    # 2) fallback por sufijo de clave si no trajo
    if not pool and ue_key:
        for k, items in ipress_by_ue.items():
            if k.endswith(ue_key):
                pool = items
                break

    # 3) último recurso: global
    if not pool:
        for items in ipress_by_ue.values():
            pool.extend(items)

    print("[SEARCH] UE:", ue_raw, "ue_key:", ue_key, "| pool size:", len(pool), "| q:", q)

    def remove_accents_lower(s: str) -> str:
        s = ''.join(c for c in unicodedata.normalize('NFKD', str(s)) if not unicodedata.combining(c))
        return s.lower()

    def normalize_for_tokens(s: str) -> str:
        s = remove_accents_lower(s)
        s = re.sub(r'[^a-z0-9 ]+', ' ', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    q_tokens_str = normalize_for_tokens(q)
    tokens = q_tokens_str.split()
    q_compact = q_tokens_str.replace(" ", "")

    def name_views(r):
        name_raw = r.get("eess_nombre", "")
        name_tok = normalize_for_tokens(name_raw)
        name_cmp = name_tok.replace(" ", "")
        return name_tok, name_cmp

    def matches(r):
        raw_name = str(r.get("eess_nombre", ""))
        raw_name_lower = " ".join(raw_name.lower().split())
        raw_q_lower = " ".join(q.lower().split())

        name_tok, name_cmp = name_views(r)
        code = str(r.get("ipress_codigo", ""))

        if tokens and all(t in name_tok for t in tokens):
            return True
        if q_compact and name_cmp.startswith(q_compact):
            return True
        if raw_q_lower and raw_q_lower in raw_name_lower:
            return True
        if q and q in code:
            return True
        return False

    hits = [r for r in pool if matches(r)]

    def score(r):
        name_tok, name_cmp = name_views(r)
        code = str(r.get("ipress_codigo", ""))
        if name_cmp.startswith(q_compact): return (0, len(name_cmp))
        if tokens and all(t in name_tok for t in tokens): return (1, len(name_tok))
        if q in code: return (2, len(code))
        return (9, 9999)

    hits.sort(key=score)
    return jsonify(hits[:10])

# ---------------------------
# API para buscar en SIGA por (Establecimiento + Código Patrimonial)
# SOLO devuelve: denominación, marca, modelo, serie, antigüedad
# ---------------------------

def _only_name_from_establecimiento(s: str) -> str:
    # Si llega "CMI MANUEL BARRETO — 6104" → "CMI MANUEL BARRETO"
    return str(s).split(" — ", 1)[0].strip()

def _norm_sede(s: str) -> str:
    txt = unicodedata.normalize('NFKD', str(s))
    txt = ''.join(c for c in txt if not unicodedata.combining(c))
    txt = txt.lower().strip()
    txt = re.sub(r'\s+', ' ', txt)
    return txt

@views_bp.post("/api/siga/find")
def api_siga_find():
    data = request.get_json(silent=True) or {}
    establecimiento = _only_name_from_establecimiento(data.get("establecimiento", ""))
    codigo = (data.get("codigo_patrimonial") or "").strip()

    if not codigo:
        return jsonify({"ok": False, "error": "codigo_patrimonial requerido"}), 400

    sede_key = _norm_sede(establecimiento)
    cod_key  = re.sub(r"\s+", "", codigo)

    index = current_app.config.get("SIGA_MIN_INDEX", {}) or {}
    hit = index.get((sede_key, cod_key))

    print("[SIGA][QUERY]", (sede_key, cod_key), "→", "HIT" if hit else "MISS")

    if not hit:
        return jsonify({"ok": True, "found": False})

    return jsonify({
        "ok": True,
        "found": True,
        "data": {
            "denominacion": hit.get("denominacion", ""),
            "marca":        hit.get("marca", ""),
            "modelo":       hit.get("modelo", ""),
            "serie":        hit.get("serie", ""),
            "antiguedad":   hit.get("FECHA_ADQUISICION", ""),
        }
    })

#esto es opcional temporal pora ver el UE 
@views_bp.get("/debug/ipress")
def debug_ipress():
    ipress_by_ue = current_app.config.get("IPRESS_BY_UE", {})
    ue_raw = session.get("ue_codigo","")
    print("UE en sesión:", ue_raw, "claves disponibles:", len(ipress_by_ue))
    # muestra 5 claves ejemplo
    sample_keys = list(ipress_by_ue.keys())[:5]
    return {"ue": ue_raw, "keys": sample_keys, "count": len(ipress_by_ue)}

# --- SIGA: lookup por código patrimonial (12 dígitos) -------------------------
def _norm_text_basic(s: str) -> str:
    import unicodedata, re
    t = unicodedata.normalize('NFKD', str(s or ""))
    t = ''.join(c for c in t if not unicodedata.combining(c))
    t = t.lower().strip()
    t = re.sub(r'\s+', ' ', t)
    return t

# devuelve los datos
@views_bp.post("/api/siga/lookup")
def siga_lookup():
    data = request.get_json(silent=True) or {}
    codigo = (data.get("codigo") or "").strip().replace(" ", "")
    establecimiento = data.get("establecimiento", "")

    idx = current_app.config.get("SIGA_MIN_INDEX", {})
    sede_key = _site_key(establecimiento)  # ← misma clave que al indexar

    rec = idx.get((sede_key, codigo))
    print("[SIGA] lookup:", {"sede_key": sede_key, "codigo": codigo, "hit": bool(rec)})

    if not rec:
      return jsonify({"ok": False, "msg": "No se encontró en SIGA ese código patrimonial."})

    return jsonify({
      "ok": True,
      "denominacion": rec.get("denominacion", ""),
      "marca": rec.get("marca", ""),
      "modelo": rec.get("modelo", ""),
      "serie": rec.get("serie", ""),
      "antiguedad": rec.get("antiguedad", ""),
    })


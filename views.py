from flask import Blueprint, render_template, session, redirect, url_for, current_app
import re

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

    pliego_texto = f"{session.get('pliego_codigo','')} – {session.get('pliego_nombre','')}".strip()
    ue_raw = session.get("ue_codigo","")
    ue_texto = f"{ue_raw} – {session.get('ue_nombre','')}".strip()

    # ---- NUEVO: generar candidatos de clave UE ----
    ue_full_digits = re.sub(r"\D", "", ue_raw)          # "145-1685" -> "1451685"
    ue_after_hyphen = None
    m = re.search(r"-(\d+)$", ue_raw)                   # si viene "145-1685" toma "1685"
    if m:
        ue_after_hyphen = m.group(1)

    candidates = [c for c in [ue_full_digits, ue_after_hyphen] if c]
    # -----------------------------------------------

    ipress_by_ue = current_app.config.get("IPRESS_BY_UE", {})
    ipress_items = []
    tried = []
    for key in candidates:
        tried.append(key)
        ipress_items = ipress_by_ue.get(key, [])
        if ipress_items:
            break

    # Debug útil en consola
    print("UE lookup candidates:", tried, "found:", len(ipress_items))

    return render_template(
        "formato8.html",
        pliego_texto=pliego_texto,
        ue_texto=ue_texto,
        ipress_items=ipress_items
    )

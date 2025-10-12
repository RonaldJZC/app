from flask import Blueprint, render_template, session, redirect, url_for

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
    ue_texto = f"{session.get('ue_codigo','')} – {session.get('ue_nombre','')}".strip()
    return render_template("formato8.html", pliego_texto=pliego_texto, ue_texto=ue_texto)

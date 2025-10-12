from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        users = current_app.config.get("USERS", {})
        user = users.get(username)

        if not user or password != user["password_temp"]:
            flash("UE o contraseña inválida", "error")
            return render_template("login.html")

        # Sesión
        session.clear()
        session["ue_codigo"] = user["ue_codigo"]
        session["ue_nombre"] = user["ue_nombre"]
        session["pliego_codigo"] = user["pliego_codigo"]
        session["pliego_nombre"] = user["pliego_nombre"]
        return redirect(url_for("views.formato8"))
    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))

from flask import Flask
from .config import Config
from .excel_loader import load_users, load_ipress

def create_app():
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(Config)
    
    # Carga usuarios en memoria al iniciar
    app.config["USERS"] = load_users(app.config["USERS_FILE"], sheet_name=app.config["USERS_SHEET"])

    # IPRESS por UE (nuevo)
    app.config["IPRESS_BY_UE"] = load_ipress(app.config["IPRESS_FILE"])
    
    # Blueprints
    from .auth import auth_bp
    from .views import views_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(views_bp)
    return app

# Para `flask run`
app = create_app()

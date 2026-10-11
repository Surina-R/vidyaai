from flask import Flask, jsonify, request

from config import Config, FRONTEND_DIR
from database import close_db, init_db
from auth import auth_bp, role_required
from catalog import catalog_bp
from quiz import quiz_bp
from analytics import analytics_bp
from ai import ai_bp


def create_app():
    # The Flask server also serves the frontend files, so there is only ONE server to run
    app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
    app.config.from_object(Config)

    init_db(app.config["DATABASE_PATH"])      # make sure tables exist
    app.teardown_appcontext(close_db)

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(catalog_bp, url_prefix="/api")
    app.register_blueprint(quiz_bp, url_prefix="/api/quiz")
    app.register_blueprint(analytics_bp, url_prefix="/api/student")
    app.register_blueprint(ai_bp, url_prefix="/api/ai")

    @app.get("/")
    def home():
        return app.send_static_file("index.html")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    # Demo of role separation: students get 403 here, teachers get 200
    @app.get("/api/teacher/ping")
    @role_required("teacher")
    def teacher_ping():
        return jsonify(message="Hello teacher")

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify(code="NOT_FOUND", error="Not found"), 404
        return e

    return app


app = create_app()

if __name__ == "__main__":
    # debug=True is for development only
    app.run(debug=True, port=5000)
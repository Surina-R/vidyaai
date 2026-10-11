import os
import secrets
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend"))

# Reads the .env file (if present) into environment variables
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    # If SECRET_KEY is missing, use a random one (you will be logged out on every restart)
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    DATABASE_PATH = os.environ.get("DATABASE_PATH") or os.path.join(BASE_DIR, "vidyaai.db")
    SESSION_COOKIE_HTTPONLY = True     # JavaScript cannot read the session cookie
    SESSION_COOKIE_SAMESITE = "Lax"    # basic protection against cross-site requests
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE") == "1"   # only send the cookie over HTTPS (set on the live site)
    MAX_CONTENT_LENGTH = 64 * 1024     # reject request bodies larger than 64 KB

    # AI settings. The key is read from the environment and is NEVER written in code.
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or "gemini-3.5-flash-lite"


GRADES = [6, 7, 8, 9, 10]
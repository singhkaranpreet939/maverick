from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import requests
import json
import pymysql
import pymysql.cursors
import logging

app = Flask(__name__)
app.secret_key = "change_this_to_a_secret_in_production"

# MySQL configuration (as requested)
DB_HOST = "localhost"
DB_USER = "karanpreet"
DB_PASSWORD = "karan#123"
DB_NAME = "maverick"
DB_TABLE = "user"

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "gemma3:1b"

logging.basicConfig(level=logging.INFO)

def get_ollama_response(prompt):
    try:
        payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False
        }
        headers = {"Content-Type": "application/json"}
        res = requests.post(OLLAMA_URL, headers=headers, data=json.dumps(payload))  # Fixed here
        res.raise_for_status()
        data = res.json()
        return data.get("message", {}).get("content", "No response")
    except Exception as e:
        return f"Error: {str(e)}"


def get_db_connection():
    # Returns a new connection. Caller is responsible for closing it.
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def init_db():
    """Create database table if it doesn't exist and ensure the seeded user exists."""
    conn = None
    try:
        # Try connecting to the specified database first
        conn = get_db_connection()
    except pymysql.err.OperationalError as e:
        # Unknown database -> create database and retry
        logging.info(f"Initial DB connection failed: {e}. Attempting to create database '{DB_NAME}'.")
        try:
            tmp_conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, autocommit=True)
            with tmp_conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
            tmp_conn.close()
            conn = get_db_connection()
        except Exception as e2:
            logging.warning(f"Could not create database '{DB_NAME}': {e2}")
            return
    try:
        with conn.cursor() as cur:
            # Create table if not exists
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS `{DB_TABLE}` (
                    `username` VARCHAR(255) NOT NULL PRIMARY KEY,
                    `password` VARCHAR(255) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)

            # Ensure the seeded user exists
            cur.execute(f"SELECT 1 FROM `{DB_TABLE}` WHERE `username`=%s", (DB_USER,))
            exists = cur.fetchone()
            if not exists:
                cur.execute(f"INSERT INTO `{DB_TABLE}` (`username`,`password`) VALUES (%s,%s)", (DB_USER, DB_PASSWORD))
                logging.info(f"Seeded user '{DB_USER}' into `{DB_TABLE}` table.")
    except Exception as e:
        logging.warning(f"Could not initialize DB/table: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


# Initialize DB / table / seed user at startup (best-effort)
init_db()

@app.route("/", methods=["GET", "POST"])
def login():
    # Handle login form GET and POST
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            error = "Please enter username and password."
        else:
            try:
                conn = get_db_connection()
                with conn.cursor() as cur:
                    cur.execute(f"SELECT * FROM `{DB_TABLE}` WHERE `username`=%s AND `password`=%s", (username, password))
                    user = cur.fetchone()
                if user:
                    session["username"] = username
                    return redirect(url_for("index"))
                else:
                    error = "Invalid username or password."
            except Exception as e:
                error = f"Database error: {e}"
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

    return render_template("login.html", error=error)
@app.route("/index")
def index():
    
    if not session.get("username"):
        return redirect(url_for("login"))
    return render_template("index.html")

@app.route("/chat", methods=["POST"])  
def chat():
    user_msg = request.json.get("message", "")
    if not user_msg.strip():
        return jsonify({"reply": "Please type something"}) 
    bot_reply = get_ollama_response(user_msg)
    return jsonify({"reply": bot_reply})

if __name__ == "__main__":
    app.run(debug=True)

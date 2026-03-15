"""Sample Flask application for the governance demo workspace."""

from flask import Flask, jsonify

app = Flask(__name__)

API_VERSION = "1.2.0"
DATABASE_URL = "postgresql://app:secret@db:5432/myapp"


@app.route("/health")
def health():
    return jsonify({"status": "healthy", "version": API_VERSION})


@app.route("/api/users")
def list_users():
    return jsonify({"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

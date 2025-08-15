from flask import Flask, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/camera")
def camera():
    return render_template("camera.html")

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
    # socketio.run(app, host="127.0.0.1", port=5000, debug=True)
from flask import Flask, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/camera")
def camera():
    return render_template("camera.html")

@app.route("/monitor")
def monitor():
    return render_template("monitor.html")

from sockets_handler import * # SocketIO Routes are here

if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=5000, debug=True)
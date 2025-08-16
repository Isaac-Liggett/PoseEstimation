from flask import Flask, render_template
from flask_socketio import SocketIO

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

import requests

# def get_ngrok_url(name):
#     """Return the public URL of the ngrok tunnel with the given name."""
#     try:
#         tunnels = requests.get("http://127.0.0.1:4040/api/tunnels").json()["tunnels"]
#         for tunnel in tunnels:
#             if tunnel["name"] == name:
#                 return tunnel["public_url"]
#     except Exception as e:
#         print("Error fetching ngrok URL:", e)
#     return None

static_url = "http://127.0.0.1:5000" #get_ngrok_url("static")
webrtc_url = "http://127.0.0.1:8080" #get_ngrok_url("webrtc")

print("STATIC URL:", static_url)
print("WEBRTC URL:", webrtc_url)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/camera")
def camera():
    return render_template("camera.html", webrtcurl=webrtc_url)

@app.route("/monitor")
def monitor():
    return render_template("monitor.html", webrtcurl=webrtc_url)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
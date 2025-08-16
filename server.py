from flask import Flask, render_template
from flask_socketio import SocketIO
import os
import json

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

import json

def get_url(name, config_file="tunnels.config.json"):
    """
    Reads the localtunnel domains from a config file and returns them as a dictionary.
    
    Args:
        config_file (str): Path to the JSON config file
    
    Returns:
        dict: {"app_name": "https://public-url", ...}
    """
    try:
        with open(config_file, "r") as f:
            url = json.load(f)[name]
            if not url or url == "":
                if name == "static":
                    return "http://127.0.0.1:5000"
                elif name == "webrtc":
                    return "http://127.0.0.1:8080"
            return url
    except FileNotFoundError:
        print(f"Config file {config_file} not found.")
        return "http://127.0.0.1:5000"
    except json.JSONDecodeError:
        print(f"Config file {config_file} contains invalid JSON.")
        return "http://127.0.0.1:5000"

print("STATIC URL:", get_url("static"))
print("WEBRTC URL:", get_url("webrtc"))

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/camera")
def camera():
    return render_template("camera.html", webrtcurl=get_url("webrtc"))

@app.route("/monitor")
def monitor():
    return render_template("monitor.html", webrtcurl=get_url("webrtc"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
from flask import request
from flask_socketio import SocketIO, emit, join_room, leave_room
from server import socketio

clients = {}

roles = set(["Camera", "Monitor"])

@socketio.on("connect")
def handle_connect(data):
    role = data.get("role")
    sid = request.sid
    clients[sid] = role

    if role in roles:
        join_room(role)

    print(f"Client {sid} registered as {role}")
    emit("server_message", {"data": f"Registered as {role}"})

@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    role = clients.pop(sid, None)
    if role:
        leave_room(role)
        print(f"Client {sid} ({role}) disconnected")

@socketio.on("video_pkt")
def handle_custom_event(data):
    pass
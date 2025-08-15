from flask import request
from flask_socketio import SocketIO, emit, join_room, leave_room
from server import socketio
import logging
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, RTCIceCandidate
from aiortc.contrib.signaling import BYE
import cv2
import asyncio

logging.basicConfig(level=logging.INFO)

clients = {}

# Store peer connections by socket id
pcs = {}

roles = set(["Camera", "Monitor"])

class VideoProcessorTrack(VideoStreamTrack):
    """
    Receives frames from the camera and processes them.
    """
    def __init__(self, track):
        super().__init__()
        self.track = track

    async def recv(self):
        frame = await self.track.recv()
        img = frame.to_ndarray(format="bgr24")

        print("Video Received!!!")

        # Return the original frame (or processed frame if you want to forward)
        return frame

# @socketio.on("connect")
# def connect():
#     sid = request.sid
    
#     logging.info(f"Client {sid} connected")
    
# @socketio.on("register_role")
# def register_role(data):
#     role = data.get("role")
#     sid = request.sid
#     clients[sid] = role

#     if role not in roles:
#         emit("server_message", {"data": "Invalid role"})
#         return

#     join_room(role)

#     print(f"Client {sid} registered as {role}")
#     emit("server_message", {"data": f"Registered as {role}"})

# @socketio.on("disconnect")
# def handle_disconnect():
#     sid = request.sid
#     role = clients.pop(sid, None)
#     if role:
#         leave_room(role if role == "Monitor" else sid)
#         print(f"Client {sid} ({role}) disconnected")

# # WebRTC Handling
# @socketio.on("ice-candidate")
# def on_ice(data):
#     sid = request.sid
#     pc = pcs.get(sid)
#     if not pc:
#         return

#     candidate_dict = data["candidate"]

#     # Schedule the coroutine safely on the event loop
#     loop = asyncio.get_event_loop()
#     asyncio.run_coroutine_threadsafe(pc.addIceCandidate(candidate_dict), loop)

# @socketio.on("offer")
# def on_offer(data):
#     sid = request.sid
#     offer_sdp = data["sdp"]

#     pc = RTCPeerConnection()
#     pcs[sid] = pc

#     @pc.on("track")
#     def on_track(track):
#         print(f"Received track from {sid}: {track.kind}")
#         video_track = VideoProcessorTrack(track)
#         # You can store video_track to forward to monitors or process frames

#     # Set remote description
#     offer = RTCSessionDescription(sdp=offer_sdp, type="offer")
#     asyncio.run(pc.setRemoteDescription(offer))

#     # Create answer
#     answer = asyncio.run(pc.createAnswer())
#     asyncio.run(pc.setLocalDescription(answer))

#     emit("answer", {"sdp": pc.localDescription.sdp})
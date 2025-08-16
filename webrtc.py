import asyncio
import logging
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, MediaStreamError
from aiortc.contrib.media import MediaRelay
import cv2
import numpy as np
from collections import deque
import aiohttp_cors
import mediapipe as mp

logging.basicConfig(level=logging.INFO)

# --------- Globals ----------
pcs = set()
relay = MediaRelay()

# Track slots
camera_tracks = {"cam1": None, "cam2": None}

# Deque buffers for each camera (store last 30 frames ~1 sec @30fps)
frame_buffers = {
    "cam1": deque(maxlen=30),
    "cam2": deque(maxlen=30)
}

skeleton_channels = set() # monitors

import time
import json

# --------- Camera offer handler ----------
async def camera_offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    
    pc = RTCPeerConnection()
    pcs.add(pc)
    logging.info("New camera connected")

    @pc.on("track")
    async def on_track(track):
        if track.kind != "video":
            return

        # Assign slot
        slot_name = None
        if camera_tracks["cam1"] is None:
            slot_name = "cam1"
        elif camera_tracks["cam2"] is None:
            slot_name = "cam2"
        else:
            logging.warning("No free camera slots. Track rejected.")
            return

        camera_tracks[slot_name] = relay.subscribe(track)
        logging.info(f"{slot_name} track stored")

        # Start processing frames into deque buffer
        asyncio.create_task(process_video(camera_tracks[slot_name], slot_name))

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    
    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

# --------- Monitor offer handler (for data channel) ----------
async def monitor_offer(request):
    params = await request.json()
    pc = RTCPeerConnection()

    # Listen for any data channels created by the client
    @pc.on("datachannel")
    def on_datachannel(channel):
        if channel.label == "skeleton":
            logging.info("Server received skeleton channel")
            _wire_datachannel(channel)

    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

def _wire_datachannel(channel):
    logging.info("Server received skeleton channel")
    skeleton_channels.add(channel)  # add immediately

    @channel.on("open")
    def _open():
        logging.info("Skeleton channel opened")

    @channel.on("close")
    def _close():
        logging.info("Skeleton channel closed")
        skeleton_channels.discard(channel)

async def _send_hello(channel):
    hello = {
        "type": "hello",
        "calibration": {"image_width": 640, "image_height": 480, "fov_deg": 80, "baseline_m": 0.5},
        "ts": time.time()
    }
    try:
        await channel.send(json.dumps(hello))
    except Exception as e:
        logging.warning(f"Failed to send hello: {e}")

# --------- Video processing ----------
async def process_video(track: VideoStreamTrack, slot_name: str):
    while True:
        try:
            frame = await track.recv()
        except MediaStreamError:
            logging.warning(f"{slot_name} track closed")
            camera_tracks[slot_name] = None
            break
        
        img = frame.to_ndarray(format="bgr24")
        
        # Add to frame buffer
        frame_buffers[slot_name].append(img)
        await asyncio.sleep(0)  # yield control

def get_synchronized_frames():
    if frame_buffers["cam1"] and frame_buffers["cam2"]:
        # Grab the latest frame from each camera
        frame1 = frame_buffers["cam1"][-1]
        frame2 = frame_buffers["cam2"][-1]
        return frame1, frame2
    return None, None

mp_pose = mp.solutions.pose
pose = mp_pose.Pose(static_image_mode=False, model_complexity=1)

async def broadcast_skeleton(points_3d):
    if not skeleton_channels:
        return

    points_list = [point.tolist() if isinstance(point, np.ndarray) else point for point in points_3d]
    msg = {"type": "pose3d", "points": points_list}
    data = json.dumps(msg)

    dead = []
    for ch in list(skeleton_channels):
        try:
            if getattr(ch, "readyState", "") == "open":
                ch.send(data)  # synchronous
            else:
                dead.append(ch)
        except Exception as e:
            logging.warning(f"DataChannel send failed: {e}")
            dead.append(ch)
    for ch in dead:
        skeleton_channels.discard(ch)

async def process_3d_pose():
    # Camera intrinsics
    image_width = 640
    image_height = 480
    FOV_deg = 80
    FOV_rad = np.deg2rad(FOV_deg)

    fx = (image_width / 2) / np.tan(FOV_rad / 2)
    fy = fx  # square pixels
    cx = image_width / 2
    cy = image_height / 2

    K = np.array([
        [fx, 0, cx],
        [0, fy, cy],
        [0,  0,  1]
    ])

    # Camera extrinsics
    R1, t1 = np.eye(3), np.zeros((3, 1))
    R2, t2 = np.eye(3), np.array([[0.5], [0], [0]])  # 0.5m to the right

    P1 = K @ np.hstack((R1, t1))
    P2 = K @ np.hstack((R2, t2))

    while True:
        frame1, frame2 = get_synchronized_frames()
        if frame1 is not None and frame2 is not None:
            # Convert to RGB for BlazePose
            rgb1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2RGB)
            rgb2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2RGB)

            res1 = pose.process(rgb1)
            res2 = pose.process(rgb2)

            if res1.pose_landmarks and res2.pose_landmarks:
                points_3d = []

                for lm1, lm2 in zip(res1.pose_landmarks.landmark,
                                    res2.pose_landmarks.landmark):
                    # Normalized → pixel coordinates
                    x1 = lm1.x * image_width
                    y1 = lm1.y * image_height
                    x2 = lm2.x * image_width
                    y2 = lm2.y * image_height

                    # OpenCV expects shape (2, N)
                    pts1 = np.array([[x1], [y1]], dtype=np.float32)
                    pts2 = np.array([[x2], [y2]], dtype=np.float32)

                    # Triangulate
                    point_4d = cv2.triangulatePoints(P1, P2, pts1, pts2)
                    point_4d /= point_4d[3]  # divide by w

                    point_3d = point_4d[:3].reshape(-1)

                    points_3d.append(point_3d)

                # Broadcast to monitors
                # logging.info("Broadcasting to monitors")
                asyncio.create_task(broadcast_skeleton(points_3d))

                # logging.info(f"3D skeleton points: {points_3d}")

        await asyncio.sleep(1/30)  # ~30fps

def _broadcast_json(obj: dict):
    # Send to all open channels; drop any that error out
    dead = []
    data = json.dumps(obj)
    for ch in list(skeleton_channels):
        try:
            if getattr(ch, "readyState", "") == "open":
                ch.send(data)
            else:
                dead.append(ch)
        except Exception as e:
            logging.warning(f"DataChannel send failed: {e}")
            dead.append(ch)
    for ch in dead:
        skeleton_channels.discard(ch)

# --------- MJPEG stream route ----------
async def mjpeg_stream(request):
    cam = request.query.get("cam", "cam1")
    if cam not in frame_buffers:
        return web.Response(status=404, text="Camera not found")
    
    resp = web.StreamResponse(
        status=200,
        reason='OK',
        headers={'Content-Type': 'multipart/x-mixed-replace; boundary=frame'}
    )
    await resp.prepare(request)

    while True:
        if frame_buffers[cam]:
            # Use the latest frame
            img = frame_buffers[cam][-1]
        else:
            # Camera not available → black frame
            img = np.zeros((480, 640, 3), dtype=np.uint8)

        ret, jpeg = cv2.imencode(".jpg", img)
        if ret:
            await resp.write(b"--frame\r\n"
                             b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
        await asyncio.sleep(1/30)  # ~30 FPS

# --------- Cleanup ----------
async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()
    camera_tracks["cam1"] = None
    camera_tracks["cam2"] = None
    frame_buffers["cam1"].clear()
    frame_buffers["cam2"].clear()

# --------- Startup --------------
async def start_background_tasks(app):
    # Schedule the 3D processing task
    app["3d_pose_task"] = asyncio.create_task(process_3d_pose())

async def cleanup_background_tasks(app):
    # Cancel the task on shutdown
    app["3d_pose_task"].cancel()
    try:
        await app["3d_pose_task"]
    except asyncio.CancelledError:
        pass

# --------- aiohttp app ----------
app = web.Application()
app.on_shutdown.append(on_shutdown)
app.on_startup.append(start_background_tasks)
app.on_cleanup.append(cleanup_background_tasks)

camera_route = app.router.add_post("/camera_offer", camera_offer)
monitor_route = app.router.add_post("/monitor_offer", monitor_offer)
view_route = app.router.add_get("/view", mjpeg_stream)

# CORS
cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
    )
})
cors.add(camera_route)
cors.add(monitor_route)
cors.add(view_route)

if __name__ == "__main__":
    logging.info("Starting server on port 8080")
    web.run_app(app, host="0.0.0.0", port=8080)

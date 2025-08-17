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

video_tasks = {"cam1": None, "cam2": None}

skeleton_channels = set() # monitors

MAX_TIMESTAMP_DIFF = 0.05  # maximum allowed difference in seconds (50 ms)

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
        task = asyncio.create_task(process_video(camera_tracks[slot_name], slot_name, pc))
        video_tasks[slot_name] = task

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
async def process_video(track: VideoStreamTrack, slot_name: str, pc: RTCPeerConnection):
    while True:
        try:
            frame = await track.recv()
        except MediaStreamError:
            logging.warning(f"{slot_name} track closed")

            task = video_tasks.get(slot_name)
            if task:
                task.cancel()
                video_tasks[slot_name] = None

            camera_tracks[slot_name] = None
            frame_buffers[slot_name].clear()
            frame_buffers[slot_name].append(np.zeros((480, 640, 3), dtype=np.uint8))

            await pc.close()
            pcs.discard(pc)

            break
        
        img = frame.to_ndarray(format="bgr24")
        
        # Add to frame buffer
        timestamp = time.time()
        frame_buffers[slot_name].append((timestamp, img))
        await asyncio.sleep(0)  # yield control

def get_synchronized_frames():
    """
    Return the latest pair of frames whose timestamps are within MAX_TIMESTAMP_DIFF.
    Drop frames that are too old or too far apart.
    """
    if len(frame_buffers["cam1"]) == 0 or len(frame_buffers["cam2"]) == 0:
        return None, None

    # Get latest frame from cam1
    ts1, frame1 = frame_buffers["cam1"][-1]

    # Find closest frame in cam2
    ts2, frame2 = min(frame_buffers["cam2"], key=lambda x: abs(x[0] - ts1))

    # If too far apart, drop the older frame(s)
    if abs(ts1 - ts2) > MAX_TIMESTAMP_DIFF:
        # Remove older frames from cam1
        frame_buffers["cam1"] = deque([(t, f) for t, f in frame_buffers["cam1"] if t > ts2], maxlen=30)
        # Remove older frames from cam2
        frame_buffers["cam2"] = deque([(t, f) for t, f in frame_buffers["cam2"] if t > ts1], maxlen=30)
        return None, None

    return frame1, frame2

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

async def process_3d_pose():  # keeping the name so other code works
    image_width = 640
    image_height = 480

    while True:
        frame1, _ = get_synchronized_frames()  # only use cam1
        if frame1 is not None:
            # Convert to RGB for BlazePose
            rgb1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2RGB)
            res1 = pose.process(rgb1)

            if res1.pose_landmarks:
                points_3d = []
                for lm in res1.pose_landmarks.landmark:
                    # x = 0, y and z unchanged
                    points_3d.append([lm.x, lm.y, 0])

                # Broadcast to monitors (same as original)
                asyncio.create_task(broadcast_skeleton(points_3d))

        await asyncio.sleep(1/30)  # ~30fps

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
        try:
            # Use latest frame or black frame if empty
            if frame_buffers[cam]:
                ts, img = frame_buffers[cam][-1]
            else:
                img = np.zeros((480, 640, 3), dtype=np.uint8)

            # Resize and encode
            img_small = cv2.resize(img, (320, 240))
            ret, jpeg = cv2.imencode(".jpg", img_small, [int(cv2.IMWRITE_JPEG_QUALITY), 70])

            if ret:
                await resp.write(b"--frame\r\n"
                                 b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
                await resp.drain()  # flush

            await asyncio.sleep(1/30)  # ~30 FPS

        except ConnectionResetError:
            logging.info(f"Client disconnected from {cam} MJPEG stream")
            break
        except Exception as e:
            logging.warning(f"MJPEG streaming error: {e}")
            # send a placeholder black frame
            img = np.zeros((240, 320, 3), dtype=np.uint8)
            ret, jpeg = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ret:
                try:
                    await resp.write(b"--frame\r\n"
                                     b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
                    await resp.drain()
                except:
                    break


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

import asyncio
import json
import logging
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaRelay
import cv2
from av import VideoFrame

logging.basicConfig(level=logging.INFO)

# --------- Globals ----------
pcs = set()
relay = MediaRelay()
camera_tracks = {"cam1": None, "cam2": None}
last_frame = None  # for MJPEG streaming

# --------- Camera offer handler ----------
async def camera_offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    
    pc = RTCPeerConnection()
    pcs.add(pc)
    logging.info("New camera connected")

    @pc.on("track")
    async def on_track(track):
        global last_frame
        if track.kind != "video":
            return

        slot_name = "cam1" if camera_tracks["cam1"] is None else "cam2"
        camera_tracks[slot_name] = relay.subscribe(track)
        logging.info(f"{slot_name} track stored")

        # Start processing frames
        asyncio.create_task(process_video(camera_tracks[slot_name]))

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    
    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

# --------- Video processing ----------
async def process_video(track: VideoStreamTrack):
    global last_frame
    while True:
        frame = await track.recv()
        img = frame.to_ndarray(format="bgr24")
        
        # Example processing: convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        last_frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        
        await asyncio.sleep(0)  # yield control

# --------- MJPEG stream route ----------
async def mjpeg_stream(request):
    cam = request.query.get("cam", "cam1")
    
    async def stream_generator():
        while True:
            track = camera_tracks.get(cam)
            
            if track is not None:
                # Receive frame from track
                frame = await track.recv()
                img = frame.to_ndarray(format="bgr24")
            else:
                # Camera not available → black frame
                img = np.zeros((480, 640, 3), dtype=np.uint8)
            
            # Optional: convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            
            ret, jpeg = cv2.imencode(".jpg", img)
            if ret:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
            
            await asyncio.sleep(1/30)
    
    return web.Response(body=stream_generator(), content_type='multipart/x-mixed-replace; boundary=frame')

# --------- Cleanup ----------
async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()
    camera_tracks["cam1"] = None
    camera_tracks["cam2"] = None

# --------- aiohttp app ----------
app = web.Application()
app.on_shutdown.append(on_shutdown)

camera_route = app.router.add_post("/camera_offer", camera_offer)
view_route = app.router.add_get("/view", mjpeg_stream)

import aiohttp_cors
cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
    )
})
cors.add(camera_route)
cors.add(view_route)

if __name__ == "__main__":
    logging.info("Starting server on port 8080")
    web.run_app(app, host="0.0.0.0", port=8080)
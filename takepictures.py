import asyncio
import logging
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, MediaStreamError
from aiortc.contrib.media import MediaRelay
import cv2
import numpy as np
import os
import time
import aiohttp_cors

logging.basicConfig(level=logging.INFO)

pcs = set()
relay = MediaRelay()
camera_track = None
video_task = None
OUT_DIR = "captures"

if not os.path.exists(OUT_DIR):
    os.makedirs(OUT_DIR)

# ---------------- Camera offer handler ----------------
async def camera_offer(request):
    global camera_track, video_task

    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)
    logging.info("New camera connected")

    @pc.on("track")
    async def on_track(track):
        global camera_track, video_task
        if track.kind != "video":
            return

        camera_track = relay.subscribe(track)
        logging.info("Camera track stored")

        # Start video processing task
        video_task = asyncio.create_task(process_video(camera_track))

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

# ---------------- Video processing ----------------
async def process_video(track: VideoStreamTrack):
    logging.info("Opening OpenCV video window. Press 's' to save a frame, 'q' to quit.")
    while True:
        try:
            frame = await track.recv()
        except MediaStreamError:
            logging.warning("Camera track closed")
            break

        img = frame.to_ndarray(format="bgr24")
        cv2.imshow("Camera Stream", img)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('s'):
            filename = os.path.join(OUT_DIR, f"capture_{int(time.time())}.png")
            cv2.imwrite(filename, img)
            logging.info(f"Saved frame to {filename}")

        elif key == ord('q'):
            logging.info("Exiting video stream")
            break

    cv2.destroyAllWindows()

# ---------------- Cleanup ----------------
async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

# ---------------- App ----------------
app = web.Application()
app.on_shutdown.append(on_shutdown)
camera_route = app.router.add_post("/camera_offer", camera_offer)

# ---------------- CORS ----------------
cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
    )
})
cors.add(camera_route)

if __name__ == "__main__":
    logging.info("Starting server on port 8080")
    web.run_app(app, host="0.0.0.0", port=8080)

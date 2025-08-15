import asyncio
import json
import logging
from aiohttp import web
import aiohttp_cors
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, RTCDataChannel
from aiortc.contrib.media import MediaRelay

logging.basicConfig(level=logging.INFO)

# Globals
pcs = set()         # All PeerConnections
monitors = set()    # Monitor PeerConnections
relay = MediaRelay()
camera_tracks = set()

# --------- Camera offer handler ----------
async def camera_offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)
    logging.info("New camera connected")

    @pc.on("track")
    async def on_track(track):
        if track.kind == "video":
            local_track = relay.subscribe(track)
            camera_tracks.add(local_track)

            # Add this new track to all existing monitors
            for monitor_pc in monitors:
                monitor_pc.addTrack(local_track)
                # optionally trigger renegotiation if needed

            # Start AI processing
            asyncio.create_task(process_video(local_track))

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

# --------- Monitor offer handler ----------
async def monitor_offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    monitors.add(pc)
    logging.info("New monitor connected")

    @pc.on("datachannel")
    def on_datachannel(channel: RTCDataChannel):
        logging.info(f"Monitor data channel {channel.label} opened")

    @pc.on("track")
    def on_track(track):
        logging.info(f"Monitor will receive track: {track.kind}")

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

# --------- Video processing & forwarding ----------
async def process_video(track: VideoStreamTrack):
    """
    Simulated AI processing: receives frames from camera, 
    sends pose data to all monitors via data channels.
    """
    frame_count = 0
    while True:
        frame = await track.recv()

        frame_count += 1
        if frame_count % 30 == 0:  # Log every 30 frames
            logging.info(f"Received {frame_count} frames from camera")

        # Replace this with your AI pose estimation
        pose_data = {"x": 100, "y": 200}  # dummy pose

        # Send to all monitors
        for monitor_pc in monitors:
            for sender in monitor_pc.getSenders():
                if isinstance(sender, RTCDataChannel):
                    try:
                        await sender.send(json.dumps(pose_data))
                    except Exception as e:
                        logging.warning(f"Failed to send pose: {e}")

# --------- Cleanup on shutdown ----------
async def on_shutdown(app):
    coros = [pc.close() for pc in pcs.union(monitors)]
    await asyncio.gather(*coros)
    pcs.clear()
    monitors.clear()

# --------- aiohttp app & CORS ----------
app = web.Application()
app.on_shutdown.append(on_shutdown)

# Add routes
camera_route = app.router.add_post("/camera_offer", camera_offer)
monitor_route = app.router.add_post("/monitor_offer", monitor_offer)

# Enable CORS on all routes
cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
    )
})
cors.add(camera_route)
cors.add(monitor_route)

# --------- Run the server ----------
if __name__ == "__main__":
    logging.info("Starting WebRTC server on port 8080")
    web.run_app(app, host="0.0.0.0", port=8080)

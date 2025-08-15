import asyncio
import json
import logging
from aiohttp import web
import aiohttp_cors
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaRelay
import cv2

logging.basicConfig(level=logging.INFO)

# --------- Globals ----------
pcs = set()               # all PeerConnections
monitors = set()          # monitor PeerConnections
relay = MediaRelay()
camera_tracks = {"cam1": None, "cam2": None}  # fixed slots
monitor_channels = {}     # monitor PC -> data channel

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

        slot_name = "cam1" if camera_tracks["cam1"] is None else "cam2"
        camera_tracks[slot_name] = relay.subscribe(track)
        logging.info(f"{slot_name} track stored")

        # Start AI processing
        asyncio.create_task(process_video(camera_tracks[slot_name]))

        # Safely attach track to monitors
        async def _replace():
            await asyncio.sleep(0.1)  # allow monitors to finish SDP
            for monitor_pc in monitors:
                # Add transceiver if missing
                if len(monitor_pc.getTransceivers()) < 2:
                    monitor_pc.addTransceiver("video", direction="recvonly")
                for transceiver, cam_key in zip(monitor_pc.getTransceivers(), ["cam1", "cam2"]):
                    if cam_key == slot_name:
                        await transceiver.sender.replace_track(camera_tracks[slot_name])

        asyncio.create_task(_replace())

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
    pcs.add(pc)
    monitors.add(pc)
    logging.info("New monitor connected")

    # Data channel for pose
    pose_channel = pc.createDataChannel("pose")
    monitor_channels[pc] = pose_channel

    # Set remote description first
    await pc.setRemoteDescription(offer)

    # Create recvonly transceivers to match existing camera tracks
    for cam_key in ["cam1", "cam2"]:
        if camera_tracks[cam_key] is not None:
            pc.addTransceiver("video", direction="recvonly")

    # Create answer after transceivers
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # Attach existing camera tracks
    for transceiver, cam_key in zip(pc.getTransceivers(), ["cam1", "cam2"]):
        track = camera_tracks[cam_key]
        if track is not None:
            await transceiver.sender.replace_track(track)

    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })

# --------- Video processing & pose forwarding ----------
async def process_video(track: VideoStreamTrack):
    while True:
        frame = await track.recv()  # av.VideoFrame
        img = frame.to_ndarray(format="bgr24")  # Convert to NumPy array in BGR

        # Display the frame using OpenCV
        cv2.imshow("Camera Feed", img)

        # Wait 1 ms and allow exit on 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

        # Simulate pose detection
        pose_data = {"x": 100, "y": 200}

        # Send pose data to monitors (existing code)
        for monitor_pc, channel in monitor_channels.items():
            if channel.readyState == "open":
                try:
                    await channel.send(json.dumps(pose_data))
                except Exception:
                    pass

    cv2.destroyAllWindows()

# --------- Cleanup ----------
async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()
    monitors.clear()
    camera_tracks["cam1"] = None
    camera_tracks["cam2"] = None
    monitor_channels.clear()

# --------- aiohttp app & CORS ----------
app = web.Application()
app.on_shutdown.append(on_shutdown)

camera_route = app.router.add_post("/camera_offer", camera_offer)
monitor_route = app.router.add_post("/monitor_offer", monitor_offer)

cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
        allow_credentials=True,
        expose_headers="*",
        allow_headers="*",
    )
})
cors.add(camera_route)
cors.add(monitor_route)

# --------- Run ----------
if __name__ == "__main__":
    logging.info("Starting WebRTC server on port 8080")
    web.run_app(app, host="0.0.0.0", port=8080)

import asyncio
import json
import os
import socket
import uuid
import webbrowser
from typing import Dict, Set

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Body
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from aiortc import RTCPeerConnection
from aiortc.contrib.signaling import BYE
from aiortc.rtcdatachannel import RTCDataChannel

import qrcode
from qrcode.image.pil import PilImage


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Runtime in-memory state -----------------------------------------------

class Peer:
    def __init__(self, peer_id: str, pc: RTCPeerConnection):
        self.id = peer_id
        self.pc = pc
        self.channel: RTCDataChannel | None = None
        self.device_label = None
        self.samples_received = 0

peers: Dict[str, Peer] = {}
dashboards: Set[WebSocket] = set()
lock = asyncio.Lock()


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


# --- Pages ------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    host = request.headers.get("host") or f"{lan_ip()}:8000"
    # Include ?stun=auto (client will fallback to STUN only if needed)
    sender_url = f"http://{host}/sender?stun=auto"
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "sender_url": sender_url,
        },
    )


@app.get("/sender", response_class=HTMLResponse)
async def sender_page(request: Request):
    # Pass server URL down to the client
    host = request.headers.get("host") or f"{lan_ip()}:8000"
    return templates.TemplateResponse(
        "sender.html",
        {"request": request, "server_base": f"http://{host}"},
    )


# --- QR code for dashboard ---------------------------------------------------

@app.get("/qr")
async def qr(text: str):
    img: PilImage = qrcode.make(text)  # defaults are fine
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png")


# --- Signaling (offer/answer) -----------------------------------------------

@app.post("/webrtc/offer")
async def webrtc_offer(payload: dict = Body(...)):
    """
    Expected payload: { "sdp": "...","type": "offer","label": "iPhone 13", "ice": "none|stun" }
    The phone is the offerer and creates a DataChannel named "imu".
    """
    sdp = payload["sdp"]
    sdp_type = payload["type"]
    label = payload.get("label", "unknown")
    ice_pref = payload.get("ice", "none")

    pc = RTCPeerConnection(
        # We generally don't need to configure ICE servers for aiortc itself; the
        # browser will use STUN to reveal srflx candidates if necessary.
        # (aiortc will accept incoming STUN checks from the browser)
    )
    peer_id = str(uuid.uuid4())
    peer = Peer(peer_id, pc)
    peer.device_label = label
    peers[peer_id] = peer

    @pc.on("datachannel")
    def on_datachannel(channel: RTCDataChannel):
        peer.channel = channel

        @channel.on("message")
        def on_message(message):
            # message is bytes (binary IMU packet) or str (control)
            if isinstance(message, bytes):
                peer.samples_received += 1
                # Forward a tiny summary to dashboards (don’t binary-parse here to keep it simple)
                # First 1 byte = version, next 1 byte flags, next 2 bytes seq,
                # next 8 bytes ts (Float64), next six Float32 (ax,ay,az,gx,gy,gz)
                # We’ll send bufferedAmount too for observability.
                data = {
                    "kind": "sample",
                    "peerId": peer.id,
                    "label": peer.device_label,
                    "bytes": len(message),
                    "count": peer.samples_received,
                    "buffer": channel.bufferedAmount,
                }
                asyncio.create_task(broadcast(data))
            else:
                # Control/hello/ping
                try:
                    obj = json.loads(message)
                except Exception:
                    obj = {"text": message}
                obj["kind"] = obj.get("kind", "msg")
                obj["peerId"] = peer.id
                asyncio.create_task(broadcast(obj))

        @channel.on("close")
        def on_close():
            asyncio.create_task(remove_peer(peer.id))

    @pc.on("iceconnectionstatechange")
    async def on_ice_state():
        await broadcast({
            "kind": "ice",
            "peerId": peer.id,
            "state": pc.iceConnectionState
        })
        if pc.iceConnectionState in ("failed", "closed", "disconnected"):
            await remove_peer(peer.id)

    # Complete SDP handshake
    from aiortc import RTCSessionDescription
    offer = RTCSessionDescription(sdp=sdp, type=sdp_type)
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {
        "peerId": peer_id,
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
    }


async def remove_peer(peer_id: str):
    peer = peers.pop(peer_id, None)
    if not peer:
        return
    try:
        await peer.pc.close()
    finally:
        await broadcast({"kind": "left", "peerId": peer_id})


# --- Dashboard realtime (WebSocket) -----------------------------------------

async def broadcast(msg: dict):
    stale = []
    for ws in list(dashboards):
        try:
            await ws.send_text(json.dumps(msg))
        except Exception:
            stale.append(ws)
    for ws in stale:
        dashboards.discard(ws)


@app.websocket("/ws")
async def ws_dashboard(ws: WebSocket):
    await ws.accept()
    dashboards.add(ws)
    # On connect, send a snapshot
    await ws.send_text(json.dumps({
        "kind": "snapshot",
        "peers": [
            {"peerId": p.id, "label": p.device_label, "count": p.samples_received}
            for p in peers.values()
        ]
    }))
    try:
        while True:
            await ws.receive_text()  # no-op; client may ping
    except WebSocketDisconnect:
        dashboards.discard(ws)


if __name__ == "__main__":
    import uvicorn
    url = f"http://{lan_ip()}:8000"
    print(f"Open dashboard at {url}")
    try:
        webbrowser.open_new(url)
    except Exception:
        pass
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)

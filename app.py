import asyncio
import base64
import json
import os
import socket
import struct
import uuid
import webbrowser
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional, Set, Coroutine, Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, Body, HTTPException
from fastapi.responses import HTMLResponse, Response, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.rtcdatachannel import RTCDataChannel

import qrcode
from qrcode.image.pil import PilImage


# ---------- Config ----------
TLS_CERT = os.environ.get("TLS_CERT", "certs/lan.pem")
TLS_KEY  = os.environ.get("TLS_KEY",  "certs/lan-key.pem")
PORT     = int(os.environ.get("PORT", "8443"))  # HTTPS default here

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ---------- Runtime state ----------
class Peer:
    def __init__(self, peer_id: str, pc: RTCPeerConnection):
        self.id = peer_id
        self.pc = pc
        self.channel: Optional[RTCDataChannel] = None
        self.device_label: Optional[str] = None
        self.samples_received = 0


peers: Dict[str, Peer] = {}
dashboards: Set[WebSocket] = set()

# Track background tasks so we can cancel/await them on shutdown
background_tasks: Set[asyncio.Task] = set()


def spawn(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """Create a tracked background task."""
    t = asyncio.create_task(coro)
    background_tasks.add(t)
    t.add_done_callback(background_tasks.discard)
    return t


def lan_ip() -> str:
    """Detect a LAN-reachable IPv4 address for this host."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


# ---------- Root CA discovery / serving ----------
def _read_text(p: Path) -> Optional[str]:
    try:
        return p.read_text()
    except Exception:
        return None


def find_root_ca_pem() -> Optional[str]:
    """
    Try common locations for mkcert root CA.
    Preference order:
      1) ./certs/rootCA.pem      (if you copied it there)
      2) $CAROOT/rootCA.pem
      3) mkcert -CAROOT/rootCA.pem
    Returns the PEM string or None if not found.
    """
    # 1) local copy
    local = Path("certs") / "rootCA.pem"
    txt = _read_text(local)
    if txt:
        return txt

    # 2) env CAROOT
    caroot_env = os.environ.get("CAROOT")
    if caroot_env:
        p = Path(caroot_env) / "rootCA.pem"
        txt = _read_text(p)
        if txt:
            return txt

    # 3) query mkcert -CAROOT
    try:
        out = subprocess.run(
            ["mkcert", "-CAROOT"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        ).stdout.strip()
        p = Path(out) / "rootCA.pem"
        txt = _read_text(p)
        if txt:
            return txt
    except Exception:
        pass

    return None


def pem_to_der(pem: str) -> bytes:
    """Convert PEM to DER by base64-decoding the certificate body."""
    lines = [ln.strip() for ln in pem.splitlines() if ln and "-----" not in ln]
    b64 = "".join(lines)
    return base64.b64decode(b64)


@app.get("/ca/root.pem")
def download_root_pem():
    pem = find_root_ca_pem()
    if not pem:
        raise HTTPException(404, detail="mkcert root CA not found. Run 'mkcert -install' first.")
    headers = {"Content-Disposition": 'attachment; filename="TriDance-Local-CA.pem"'}
    return PlainTextResponse(pem, headers=headers, media_type="application/x-pem-file")


@app.get("/ca/root.cer")
def download_root_cer():
    pem = find_root_ca_pem()
    if not pem:
        raise HTTPException(404, detail="mkcert root CA not found. Run 'mkcert -install' first.")
    der = pem_to_der(pem)
    headers = {"Content-Disposition": 'attachment; filename="TriDance-Local-CA.cer"'}
    return Response(content=der, headers=headers, media_type="application/x-x509-ca-cert")


# ---------- Pages ----------
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """
    Dashboard page.

    Always generate a QR/link that points to a LAN-reachable host with the *HTTPS* port.
    We do NOT reuse the incoming Host header's port, because you might be viewing
    the dashboard on http://<ip>:8000/ while the phones must open https://<ip>:8443/.
    """
    host_for_phones = f"{lan_ip()}:{PORT}"
    sender_url = f"https://{host_for_phones}/sender?stun=auto"
    return templates.TemplateResponse("dashboard.html", {"request": request, "sender_url": sender_url})


@app.get("/sender", response_class=HTMLResponse)
async def sender_page(request: Request):
    # Use relative base on the client to avoid mixed-content issues.
    return templates.TemplateResponse("sender.html", {"request": request, "server_base": ""})


# ---------- QR code ----------
@app.get("/qr")
async def qr(text: str):
    img: PilImage = qrcode.make(text)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), media_type="image/png")


# ---------- WebRTC signaling ----------
@app.post("/webrtc/offer")
async def webrtc_offer(payload: dict = Body(...)):
    """
    Expected payload: { "sdp": "...", "type": "offer", "label": "...", "ice": "none|stun" }
    The phone is the offerer and creates a DataChannel named "imu".

    Binary packet layout from sender.js (little-endian, 36 bytes):
      [u8 version=1][u8 flags=0][u16 seq][f64 ts_ms]
      [f32 ax][f32 ay][f32 az][f32 gx][f32 gy][f32 gz]
    """
    sdp = payload["sdp"]
    sdp_type = payload["type"]
    label = payload.get("label", "unknown")

    pc = RTCPeerConnection()
    peer_id = str(uuid.uuid4())
    peer = Peer(peer_id, pc)
    peer.device_label = label
    peers[peer_id] = peer

    @pc.on("datachannel")
    def on_datachannel(channel: RTCDataChannel):
        peer.channel = channel

        @channel.on("message")
        def on_message(message):
            if isinstance(message, bytes):
                peer.samples_received += 1

                # Parse 36-byte little-endian packet if possible
                ax = ay = az = gx = gy = gz = None
                ts_ms = None
                seq = None
                try:
                    if len(message) >= 36:
                        version, flags, seq, ts_ms, ax, ay, az, gx, gy, gz = struct.unpack(
                            "<BBH d f f f f f f".replace(" ", ""), message[:36]
                        )
                except Exception:
                    # leave fields as None on parse failure
                    pass

                data = {
                    "kind": "sample",
                    "peerId": peer.id,
                    "label": peer.device_label,
                    "count": peer.samples_received,
                    "seq": seq,
                    "ts": ts_ms,       # milliseconds since epoch (float)
                    "ax": ax, "ay": ay, "az": az,   # m/s^2
                    "gx": gx, "gy": gy, "gz": gz,   # rad/s
                }
                spawn(broadcast(data))
            else:
                # JSON/text control messages (e.g., hello/ping)
                try:
                    obj = json.loads(message)
                except Exception:
                    obj = {"text": message}
                obj["kind"] = obj.get("kind", "msg")
                obj["peerId"] = peer.id
                obj.setdefault("label", peer.device_label)
                spawn(broadcast(obj))

        @channel.on("close")
        def on_close():
            spawn(remove_peer(peer.id))

    @pc.on("iceconnectionstatechange")
    async def on_ice_state():
        await broadcast({"kind": "ice", "peerId": peer.id, "state": pc.iceConnectionState})
        if pc.iceConnectionState in ("failed", "closed", "disconnected"):
            await remove_peer(peer.id)

    offer = RTCSessionDescription(sdp=sdp, type=sdp_type)
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return {"peerId": peer_id, "sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


async def remove_peer(peer_id: str):
    peer = peers.pop(peer_id, None)
    if not peer:
        return
    try:
        await peer.pc.close()
    except asyncio.CancelledError:
        return
    except Exception:
        pass
    finally:
        try:
            await broadcast({"kind": "left", "peerId": peer_id})
        except asyncio.CancelledError:
            return
        except Exception:
            pass


# ---------- Dashboard realtime (WebSocket) ----------
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
    await ws.send_text(
        json.dumps(
            {
                "kind": "snapshot",
                "peers": [
                    {"peerId": p.id, "label": p.device_label, "count": p.samples_received}
                    for p in peers.values()
                ],
            }
        )
    )
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        dashboards.discard(ws)
    except Exception:
        dashboards.discard(ws)


# ---------- Graceful shutdown ----------
@app.on_event("shutdown")
async def shutdown():
    # 1) Close all peer connections
    for p in list(peers.values()):
        try:
            await p.pc.close()
        except Exception:
            pass
    peers.clear()

    # 2) Close any open dashboard websockets
    for ws in list(dashboards):
        try:
            await ws.close()
        except Exception:
            pass
        finally:
            dashboards.discard(ws)

    # 3) Cancel and await any background tasks we spawned
    for t in list(background_tasks):
        t.cancel()
    if background_tasks:
        await asyncio.gather(*background_tasks, return_exceptions=True)


if __name__ == "__main__":
    import uvicorn

    ip = lan_ip()
    url = f"https://{ip}:{PORT}"
    print(f"Open dashboard at {url}")
    try:
        webbrowser.open_new(url)
    except Exception:
        pass

    # If you run this file directly, we expect certs to exist already.
    if not (Path(TLS_CERT).exists() and Path(TLS_KEY).exists()):
        raise SystemExit(
            f"TLS cert/key not found.\n"
            f"Expected:\n  {TLS_CERT}\n  {TLS_KEY}\n"
            f"Run your HTTPS init script first (e.g., init_https.py)."
        )

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=PORT,
        ssl_certfile=TLS_CERT,
        ssl_keyfile=TLS_KEY,
        reload=False,
        timeout_graceful_shutdown=5,
    )

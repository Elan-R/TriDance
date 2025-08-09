# TriDance

Stream motion data from multiple phones to a Python (FastAPI + aiortc) server over WebRTC.  
HTTPS is recommended so iOS will allow motion sensors & Wake Lock.

---

## Quick Start (HTTPS — recommended)

> One-time on your computer: install **mkcert**. After that, you can just run `init_https.py`.

| Action | Command |
| - | - |
| 1. Go to the parent directory | `cd /PATH/TO/PARENT` |
| 2. Clone and enter the project | `git clone https://github.com/Elan-R/TriDance.git && cd TriDance` |
| 3a. (macOS/Linux) Create & activate venv | `python3 -m venv .venv && source .venv/bin/activate` |
| 3b. (Windows, PowerShell) Create & activate venv | `py -m venv .venv; .\.venv\Scripts\Activate.ps1` |
| 3c. (Windows, cmd.exe) Create & activate venv | `py -m venv .venv && .venv\Scripts\activate.bat` |
| 4. Upgrade pip & install deps | `python -m pip install --upgrade pip && pip install -r requirements.txt` |
| 5. Install mkcert (once per machine) | **macOS:** `brew install mkcert nss` · **Windows:** `choco install mkcert` · **Linux:** install `mkcert` (see mkcert docs for your distro), then run `mkcert -install` |
| 6. Run HTTPS init + server | `python init_https.py --open` |

What step 6 does:
- Detects your LAN IP and hostnames
- Ensures local CA exists (`mkcert -install`) and issues/refreshes `certs/lan.pem` + `certs/lan-key.pem`
- Starts the app over **HTTPS** (default port `8443`) and opens the dashboard

**On each phone (one-time):**  
Open the **Sender** page, tap **Download CA certificate**, and follow the on-page OS instructions to trust the local CA. (After this one-time trust, you won’t need to do it again for that device.)

---

## Quick Start (HTTP — for basic testing only)

Some features (iOS motion sensors & Wake Lock) require HTTPS and will not work here.

| Action | Command |
| - | - |
| 1. Go to the parent directory | `cd /PATH/TO/PARENT` |
| 2. Clone and enter the project | `git clone https://github.com/Elan-R/TriDance.git && cd TriDance` |
| 3a. (macOS/Linux) Create & activate venv | `python3 -m venv .venv && source .venv/bin/activate` |
| 3b. (Windows, PowerShell) Create & activate venv | `py -m venv .venv; .\.venv\Scripts\Activate.ps1` |
| 3c. (Windows, cmd.exe) Create & activate venv | `py -m venv .venv && .venv\Scripts\activate.bat` |
| 4. Upgrade pip & install deps | `python -m pip install --upgrade pip && pip install -r requirements.txt` |
| 5. Run the server | `python app.py` |
| 6. Open the dashboard | Visit the printed URL like `http://<LAN-IP>:8000/` on this computer, then scan the QR with each phone. |

> Tip (PowerShell): If activation is blocked, run once:  
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

---

## Notes

- When using **HTTPS**, you do **not** need to run `uvicorn` or `python app.py` yourself; just run `python init_https.py` (use `--open` if you want it to auto-open).
- The **sender page** provides OS-specific instructions and a **Download CA** button so phones can trust your local CA once.
- The dashboard’s QR always points to the LAN HTTPS URL (not `localhost`).

## Troubleshooting

- **iPhone shows “about:blank” after scanning QR**  
  Make sure the dashboard URL is `https://<LAN-IP>:8443/`. The QR is generated with the LAN IP; rescan from there.

- **Motion permission never appears / is denied**  
  Ensure the sender page shows a **lock icon** (HTTPS). Open in **Safari** (not an in-app webview). If you previously tapped “Don’t Allow,” clear it via *Settings → Safari → Advanced → Website Data* (delete this host), then reload.

- **mkcert not found**  
  Install mkcert (see step 5 above) and run `mkcert -install` once. Then re-run `python init_https.py`.

- **Firewall**  
  Allow inbound LAN access to port **8443** (HTTPS) or **8000** (HTTP mode).

## Requirements

- Python 3.10+
- Computer and phones on the same Wi-Fi/LAN
- For iOS sensor access: HTTPS + trusted local CA (one-time per device)


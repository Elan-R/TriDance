# TriDance

## Quick Start

| Action | Command |
| - | - |
| 1. Go to the parent directory | `cd /PATH/TO/PARENT` |
| 2. Clone and enter the project | `git clone https://github.com/Elan-R/TriDance.git && cd TriDance` |
| 3a. (macOS/Linux) Create & activate venv | `python3 -m venv .venv && source .venv/bin/activate` |
| 3b. (Windows, PowerShell) Create & activate venv | `py -m venv .venv; .\.venv\Scripts\Activate.ps1` |
| 3c. (Windows, cmd.exe) Create & activate venv | `py -m venv .venv && .venv\Scripts\activate.bat` |
| 4. Upgrade pip & install deps | `python -m pip install --upgrade pip && pip install -r requirements.txt` |
| 5. Run the server | `python app.py` |
| 6. Open the dashboard | Visit the printed URL on this device and scan the QR code on that page with each phone |

> Tip: If PowerShell blocks activation, run once:  
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`


# TriDance

## Quick Start

| Action | Command |
| - | - |
| 1. Go to the parent directory | `cd /PATH/TO/PARENT` |
| 2. Clone and enter the project | `git clone https://github.com/Elan-R/TriDance.git && cd TriDance` |
| 3a. (macOS/Linux) Create & activate venv | `python3 -m venv .venv && source .venv/bin/activate` |
| 3b. (Windows, PowerShell) Create & activate venv | `py -m venv .venv; .\.venv\Scripts\Activate.ps1` |
| 3c. (Windows, cmd.exe) Create & activate venv | `py -m venv .venv && .venv\Scripts\activate.bat` |
| 4. Upgrade pip & install deps | `python -m pip install --upgrade pip && pip install -r requirements.txt` |
| 5. Run the server | `python app.py` |
| 6. Open the dashboard | The app prints (and usually opens) a URL like `http://<LAN-IP>:8000/`. Open it on this computer, then scan the QR on that page with each phone. |

> Tip (PowerShell): If activation is blocked, run once:  
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`

### Prereqs
- Python 3.10+  
- Computer and phones on the same Wi-Fi/LAN  
- On iOS: allow **Local Network** on first run and approve **Motion & Orientation** permission

### Troubleshooting
- If the page doesn’t load, check firewall rules for port **8000**.
- If phones connect unreliably on some networks, use HTTPS/STUN later (see docs).

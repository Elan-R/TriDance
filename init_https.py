#!/usr/bin/env python3
"""
init_https.py

One-shot HTTPS bootstrap + launcher for TriDance.

- Detects your LAN IP and common hostnames.
- Ensures mkcert is installed (or prints exact install steps).
- Creates ./certs/lan.pem and ./certs/lan-key.pem with all needed SANs.
- Re-issues the cert automatically if SANs change (e.g., new LAN IP).
- Launches the FastAPI app over HTTPS with Uvicorn.

Usage:
    python init_https.py
    python init_https.py --port 8443
    python init_https.py --extra-san imu.local my-host.lan

Notes:
- Phones still need to trust your mkcert root CA once.
  On your dev machine: `mkcert -CAROOT` shows where rootCA.pem lives.
  AirDrop/email rootCA.pem to iPhone → install → Settings → General → About → Certificate Trust Settings → enable full trust.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import List


CERT_DIR = Path("certs")
CERT_FILE = CERT_DIR / "lan.pem"
KEY_FILE = CERT_DIR / "lan-key.pem"
SANS_FILE = CERT_DIR / "lan.sans.json"
DEFAULT_PORT = 8443


def run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )


def have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def os_hint_install_mkcert() -> List[str]:
    sysname = platform.system().lower()
    if "darwin" in sysname or "mac" in sysname:
        return [
            "brew install mkcert nss",
            "mkcert -install",
        ]
    if "windows" in sysname:
        return [
            "choco install mkcert",
            "mkcert -install",
        ]
    # generic Linux
    return [
        "# Install mkcert from https://github.com/FiloSottile/mkcert",
        "# Then run:",
        "mkcert -install",
    ]


def lan_ip() -> str:
    # Robust trick: open a UDP socket to a public IP (no data sent) and read local sockname
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def candidate_sans(extra: List[str]) -> List[str]:
    names = set(extra or [])
    # Always include localhost loopbacks
    names.update(["localhost", "127.0.0.1", "::1"])
    # Current LAN IP
    names.add(lan_ip())
    # Hostname variants
    host = socket.gethostname()
    if host:
        names.add(host)
        # Add .local variant; harmless if it doesn't resolve
        names.add(f"{host}.local")
    # Clean empties/whitespace and keep order stable
    cleaned = []
    for n in names:
        n = (n or "").strip()
        if n and n not in cleaned:
            cleaned.append(n)
    # Prefer deterministic order: IPs first, then names
    ips = [x for x in cleaned if looks_like_ip(x)]
    dns = [x for x in cleaned if x not in ips]
    # Ensure consistent ordering for cache comparison
    return sorted(ips, key=ip_sort_key) + sorted(dns, key=str.casefold)


def looks_like_ip(s: str) -> bool:
    try:
        socket.inet_pton(socket.AF_INET, s)
        return True
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, s)
        return True
    except OSError:
        return False


def ip_sort_key(ip: str) -> tuple:
    # Sort IPv4 before IPv6, then numeric
    try:
        socket.inet_pton(socket.AF_INET, ip)
        octets = tuple(int(x) for x in ip.split("."))
        return (0, octets)
    except OSError:
        pass
    # IPv6: rough sort by string (good enough for a stable order)
    return (1, ip)


def load_saved_sans() -> List[str]:
    if SANS_FILE.exists():
        try:
            return json.loads(SANS_FILE.read_text())
        except Exception:
            return []
    return []


def save_sans(sans: List[str]) -> None:
    SANS_FILE.write_text(json.dumps(sans, indent=2))


def ensure_mkcert() -> None:
    if have("mkcert"):
        return
    print("\n[!] mkcert is not installed.\n")
    print("Install it with:")
    for line in os_hint_install_mkcert():
        print("   ", line)
    print("\nAfter installing, re-run: python init_https.py\n")
    sys.exit(2)


def issue_cert_if_needed(sans: List[str], force: bool = False) -> None:
    CERT_DIR.mkdir(parents=True, exist_ok=True)

    existing_sans = load_saved_sans()
    must_issue = force or not CERT_FILE.exists() or not KEY_FILE.exists() or (existing_sans != sans)

    if not must_issue:
        print(f"[✓] Using existing certificate: {CERT_FILE}")
        return

    ensure_mkcert()

    # Ensure local root installed on THIS machine (not phones)
    print("[*] Ensuring local mkcert root is installed (this may prompt once)...")
    try:
        out = run(["mkcert", "-install"]).stdout
        print(out.strip())
    except subprocess.CalledProcessError as e:
        print(e.stdout)
        print("\n[!] mkcert -install failed. You may need to run it manually with admin rights.")
        sys.exit(3)

    # Build mkcert command
    cmd = [
        "mkcert",
        "-cert-file", str(CERT_FILE),
        "-key-file", str(KEY_FILE),
    ] + sans

    print("[*] Issuing leaf certificate with SANs:")
    for name in sans:
        print("    -", name)

    try:
        out = run(cmd).stdout
        print(out.strip())
    except subprocess.CalledProcessError as e:
        print(e.stdout)
        print("\n[!] mkcert issuance failed.")
        sys.exit(4)

    save_sans(sans)
    print(f"[✓] Wrote cert: {CERT_FILE}")
    print(f"[✓] Wrote key : {KEY_FILE}")
    print("\nReminder: Install & trust the mkcert root CA on each PHONE once (not done by this script).")
    print("  $ mkcert -CAROOT   # shows where rootCA.pem is; AirDrop/email to iPhone and trust.\n")


def main():
    ap = argparse.ArgumentParser(description="HTTPS bootstrap + launcher for TriDance")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"HTTPS port (default: {DEFAULT_PORT})")
    ap.add_argument("--extra-san", nargs="*", default=[], help="Additional DNS names or IPs to include in the cert")
    ap.add_argument("--force", action="store_true", help="Force re-issue the certificate even if one exists")
    ap.add_argument("--open", action="store_true", help="Open the dashboard URL in your default browser")
    args = ap.parse_args()

    sans = candidate_sans(args.extra_san)
    issue_cert_if_needed(sans, force=args.force)

    # Launch Uvicorn with SSL
    lan = lan_ip()
    url = f"https://{lan}:{args.port}/"
    print(f"\n[→] Starting TriDance over HTTPS at: {url}\n")

    try:
        if args.open:
            webbrowser.open_new(url)
    except Exception:
        pass

    # Import your FastAPI app
    try:
        import uvicorn  # noqa: F401
        # Import to validate presence of 'app'
        import app as tridance_app  # noqa: F401
    except Exception as e:
        print("\n[!] Failed to import app.py. Make sure 'app.py' is in this directory and defines 'app'.")
        print("    Error:", e)
        sys.exit(5)

    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=args.port,
        ssl_certfile=str(CERT_FILE),
        ssl_keyfile=str(KEY_FILE),
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()

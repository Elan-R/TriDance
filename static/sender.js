// static/sender.js
(function () {
  const $ = (id) => document.getElementById(id);
  const statusEl = $("status");
  const startBtn = $("start");
  const outEl = $("log");

  const log = (s) => {
    if (outEl) outEl.textContent += s + "\n";
    console.log(s);
  };

  // Query params and device label
  const params = new URLSearchParams(location.search);
  const stunMode = params.get("stun") || "auto";
  const label = navigator.userAgent;

  // Wake Lock
  let wakeLock = null;
  async function keepAwake() {
    try {
      if ("wakeLock" in navigator) {
        wakeLock = await navigator.wakeLock.request("screen");
        wakeLock.addEventListener("release", () => log("Wake lock released"));
        log("Screen Wake Lock granted");
        document.addEventListener("visibilitychange", async () => {
          if (document.visibilityState === "visible" && (!wakeLock || wakeLock.released)) {
            try { wakeLock = await navigator.wakeLock.request("screen"); } catch (e) { log("Wake Lock re-acquire error: " + e); }
          }
        });
      } else {
        log("Wake Lock API not supported; screen may dim.");
      }
    } catch (e) {
      log("Wake Lock error: " + e);
    }
  }

  function needsStunFallback() {
    if (stunMode === "none") return false;
    if (stunMode === "force") return true;
    const host = location.hostname;
    return !(host === "localhost" || host === "127.0.0.1");
  }

  function iceServers() {
    return needsStunFallback()
      ? [{ urls: ["stun:stun.l.google.com:19302"] }]
      : [];
  }

  // Binary pack: [u8 ver=1][u8 flags=0][u16 seq][f64 ts_ms][6×f32 ax..gz]
  function toLEBuffer(seq, tsMs, ax, ay, az, gx, gy, gz) {
    const buf = new ArrayBuffer(1 + 1 + 2 + 8 + 4 * 6);
    const dv = new DataView(buf);
    let o = 0;
    dv.setUint8(o, 1); o += 1;
    dv.setUint8(o, 0); o += 1;
    dv.setUint16(o, seq, true); o += 2;
    dv.setFloat64(o, tsMs, true); o += 8;
    dv.setFloat32(o, ax, true); o += 4;
    dv.setFloat32(o, ay, true); o += 4;
    dv.setFloat32(o, az, true); o += 4;
    dv.setFloat32(o, gx, true); o += 4;
    dv.setFloat32(o, gy, true); o += 4;
    dv.setFloat32(o, gz, true); o += 4;
    return buf;
  }

  // Ask for permissions *synchronously* inside the user gesture
  function requestMotionPermissionsFromGesture() {
    if (!isSecureContext) {
      return Promise.reject(new Error("This page is not HTTPS (secure context)."));
    }

    let pm;
    if (typeof DeviceMotionEvent !== "undefined" &&
        typeof DeviceMotionEvent.requestPermission === "function") {
      pm = DeviceMotionEvent.requestPermission();
    } else {
      pm = Promise.resolve("granted");
    }

    let po;
    if (typeof DeviceOrientationEvent !== "undefined" &&
        typeof DeviceOrientationEvent.requestPermission === "function") {
      po = DeviceOrientationEvent.requestPermission();
    } else {
      po = Promise.resolve("granted");
    }

    // Chain without awaiting before the prompt is triggered
    return Promise.all([pm, po]).then(([rm, ro]) => {
      const granted = (rm === "granted") && (ro === "granted" || ro === undefined || ro === "granted");
      if (!granted) {
        throw new Error("DeviceMotion/Orientation permission denied.");
      }
      return true;
    });
  }

  async function continueStartup() {
    if (statusEl) { statusEl.textContent = "Starting..."; statusEl.className = "warn"; }
    await keepAwake();

    const pc = new RTCPeerConnection({ iceServers: iceServers() });
    const dc = pc.createDataChannel("imu", { ordered: false, maxRetransmits: 0 });
    dc.binaryType = "arraybuffer";

    dc.onopen = () => {
      if (statusEl) { statusEl.textContent = "Connected ✅"; statusEl.className = "ok"; }
      dc.send(JSON.stringify({ kind: "hello", label }));
      log("DataChannel open");
    };

    dc.onclose = () => {
      if (statusEl) { statusEl.textContent = "Closed"; statusEl.className = "warn"; }
      log("DataChannel closed");
    };

    dc.onerror = (e) => log("DataChannel error: " + (e?.message || e));

    pc.oniceconnectionstatechange = () => {
      log("ICE state: " + pc.iceConnectionState);
      if (pc.iceConnectionState === "failed" && statusEl) {
        statusEl.textContent = "ICE failed";
        statusEl.className = "err";
      }
    };

    // SDP offer/answer
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise((resolve) => {
      if (pc.iceGatheringState === "complete") return resolve();
      pc.onicegatheringstatechange = () => {
        if (pc.iceGatheringState === "complete") resolve();
      };
      setTimeout(resolve, 2000);
    });

    const base = (typeof SERVER_BASE === "string" && SERVER_BASE) ? SERVER_BASE : "";
    const answerRes = await fetch(`${base}/webrtc/offer`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        sdp: pc.localDescription.sdp,
        type: pc.localDescription.type,
        label,
        ice: needsStunFallback() ? "stun" : "none",
      }),
    });

    if (!answerRes.ok) {
      throw new Error(`Offer failed: ${answerRes.status} ${answerRes.statusText}`);
    }

    const answer = await answerRes.json();
    await pc.setRemoteDescription({ sdp: answer.sdp, type: answer.type });
    log("SDP handshake complete");

    // IMU streaming
    let seq = 0;
    const toRad = Math.PI / 180;

    window.addEventListener(
      "devicemotion",
      (e) => {
        if (dc.readyState !== "open") return;

        const a = e.acceleration ?? e.accelerationIncludingGravity ?? {};
        const ax = a.x ?? 0;
        const ay = a.y ?? 0;
        const az = a.z ?? 0;

        const rr = e.rotationRate ?? {};
        const gx = (rr.alpha ?? 0) * toRad;
        const gy = (rr.beta  ?? 0) * toRad;
        const gz = (rr.gamma ?? 0) * toRad;

        const ts = performance.timeOrigin + performance.now();

        const buf = toLEBuffer(seq++ & 0xffff, ts, ax, ay, az, gx, gy, gz);
        if (dc.bufferedAmount > 1_000_000) return; // drop if backed up
        dc.send(buf);
      },
      { passive: true }
    );

    setInterval(() => {
      if (dc.readyState === "open") {
        dc.send(JSON.stringify({ kind: "ping", t: Date.now() }));
      }
    }, 5000);
  }

  function onUserGesture(e) {
    e.preventDefault(); // keep it a clean, single gesture
    if (startBtn) startBtn.disabled = true;

    log("isSecureContext=" + isSecureContext);

    // Call permission requests *immediately*, then continue
    requestMotionPermissionsFromGesture()
      .then(() => continueStartup())
      .catch((err) => {
        log("Permission error: " + (err?.message || err));
        if (statusEl) { statusEl.textContent = "Permission denied"; statusEl.className = "err"; }
        alert(
          "Motion permission failed.\n\nTips:\n" +
          "• Ensure this page is HTTPS (lock icon in Safari).\n" +
          "• In Settings > Safari, enable “Motion & Orientation Access”.\n" +
          "• If you previously tapped “Don’t Allow”, go to Settings > Safari > Advanced > Website Data,\n" +
          "  search this host, delete it, then reload and tap Start again."
        );
        if (startBtn) startBtn.disabled = false;
      });
  }

  // Wire up both click and touchend (some iOS versions are picky)
  if (startBtn) {
    startBtn.addEventListener("click", onUserGesture, { once: true });
    startBtn.addEventListener("touchend", onUserGesture, { once: true, passive: false });
  }

  // Surface uncaught errors to the page
  window.addEventListener("error", (e) => log("Uncaught error: " + e.message));
})();

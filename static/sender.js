(async function(){
  const $ = (id)=>document.getElementById(id);
  const log = (s)=> { $.log.textContent += s + "\n"; }

  const params = new URLSearchParams(location.search);
  const stunMode = params.get("stun") || "auto";
  const label = navigator.userAgent;

  let wakeLock = null;
  async function keepAwake(){
    try {
      if ('wakeLock' in navigator) {
        wakeLock = await navigator.wakeLock.request('screen');
        wakeLock.addEventListener('release', ()=>log("Wake lock released"));
        log("Screen Wake Lock granted");
      } else {
        log("Wake Lock API not supported; screen may dim.");
      }
    } catch (e) {
      log("Wake Lock error: " + e);
    }
  }

  function needsStunFallback(){
    // Browsers often obfuscate host candidates via mDNS; without STUN,
    // a Python peer may fail to resolve them. Prefer STUN except on localhost.
    if (stunMode === "none") return false;
    if (stunMode === "force") return true;
    // auto: use STUN unless server is localhost
    const host = location.hostname;
    return !(host === "localhost" || host === "127.0.0.1");
  }

  function iceServers(){
    return needsStunFallback()
      ? [{ urls: ["stun:stun.l.google.com:19302"] }]
      : [];
  }

  function toLEBuffer(seq, tsMs, ax, ay, az, gx, gy, gz){
    // Binary packet layout (little-endian):
    // [u8 version=1][u8 flags=0][u16 seq][f64 ts_ms]
    // [f32 ax][f32 ay][f32 az][f32 gx][f32 gy][f32 gz]
    const buf = new ArrayBuffer(1+1+2 + 8 + 4*6);
    const dv = new DataView(buf);
    let o = 0;
    dv.setUint8(o, 1); o+=1;
    dv.setUint8(o, 0); o+=1;
    dv.setUint16(o, seq, true); o+=2;
    dv.setFloat64(o, tsMs, true); o+=8;
    dv.setFloat32(o, ax, true); o+=4;
    dv.setFloat32(o, ay, true); o+=4;
    dv.setFloat32(o, az, true); o+=4;
    dv.setFloat32(o, gx, true); o+=4;
    dv.setFloat32(o, gy, true); o+=4;
    dv.setFloat32(o, gz, true); o+=4;
    return buf;
  }

  async function requestMotionPermission(){
    // iOS needs a user gesture + permission call
    try {
      if (typeof DeviceMotionEvent !== "undefined" && typeof DeviceMotionEvent.requestPermission === "function") {
        const r = await DeviceMotionEvent.requestPermission();
        if (r !== "granted") throw new Error("DeviceMotion permission denied");
      }
    } catch (e) {
      log("Motion permission flow: " + e);
    }
  }

  async function start(){
    $.status.textContent = "Starting...";
    await keepAwake();
    await requestMotionPermission();

    const pc = new RTCPeerConnection({ iceServers: iceServers() });
    const dc = pc.createDataChannel("imu", { ordered: false, maxRetransmits: 0 });
    dc.binaryType = "arraybuffer";

    dc.onopen = () => {
      $.status.textContent = "Connected ✅";
      $.status.className = "ok";
      dc.send(JSON.stringify({ kind: "hello", label }));
      log("DataChannel open");
    };
    dc.onclose = () => { $.status.textContent = "Closed"; $.status.className = "warn"; };

    pc.oniceconnectionstatechange = () => log("ICE: " + pc.iceConnectionState);

    // SDP offer/answer
    await pc.setLocalDescription(await pc.createOffer());
    await new Promise(resolve => {
      if (pc.iceGatheringState === "complete") resolve();
      else pc.onicegatheringstatechange = () => pc.iceGatheringState === "complete" && resolve();
    });

    const res = await fetch(`${SERVER_BASE}/webrtc/offer`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type, label, ice: needsStunFallback() ? "stun" : "none" })
    });
    const answer = await res.json();
    await pc.setRemoteDescription({ sdp: answer.sdp, type: answer.type });

    // IMU streaming
    let seq = 0;
    const toRad = Math.PI / 180;

    window.addEventListener("devicemotion", (e) => {
      if (dc.readyState !== "open") return;

      // Accelerometer (m/s^2). On some browsers it's in 'accelerationIncludingGravity'.
      const a = e.acceleration ?? e.accelerationIncludingGravity ?? {};
      const ax = a.x ?? 0;
      const ay = a.y ?? 0;
      const az = a.z ?? 0;

      // Gyro (deg/s) -> rad/s
      const rr = e.rotationRate ?? {};
      const gx = (rr.alpha ?? 0) * toRad; // Note: axes differ by browser; you may remap later
      const gy = (rr.beta  ?? 0) * toRad;
      const gz = (rr.gamma ?? 0) * toRad;

      const ts = performance.timeOrigin + performance.now(); // ms epoch
      const buf = toLEBuffer(seq++ & 0xffff, ts, ax, ay, az, gx, gy, gz);

      // backpressure: drop if too backed up
      if (dc.bufferedAmount > 1_000_000) return;
      dc.send(buf);
    }, { frequency: 60 }); // hint

    // Keepalive (optional)
    setInterval(()=> {
      if (dc.readyState === "open") dc.send(JSON.stringify({ kind: "ping", t: Date.now() }));
    }, 5000);
  }

  $.start.addEventListener("click", start);
})();

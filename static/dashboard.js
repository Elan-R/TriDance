// static/dashboard.js
(function () {
  const tbody = document.getElementById("peers");
  const byId = new Map();

  // Number formatter: fixed 2 decimals, always show sign, stable width with monospace
  let fmtSigned2;
  try {
    fmtSigned2 = new Intl.NumberFormat(undefined, {
      signDisplay: "always",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
      useGrouping: false,
    });
  } catch {
    fmtSigned2 = {
      format(n) {
        if (n === null || n === undefined || Number.isNaN(n)) return "—";
        const s = Number(n).toFixed(2);
        return (n >= 0 ? "+" + s : s);
      },
    };
  }
  const FMT = (n) =>
    n === null || n === undefined || Number.isNaN(n) ? "—" : fmtSigned2.format(n);

  function spanFor(n) {
    const s = document.createElement("span");
    s.textContent = FMT(n);
    const num = Number(n);
    if (!Number.isNaN(num) && Math.abs(num) > 2) {
      s.classList.add("thr"); // green if |value| > 2
    }
    return s;
  }

  function triplet(ax, ay, az) {
    const wrap = document.createElement("div");
    wrap.className = "mono triplet";
    wrap.append(spanFor(ax), spanFor(ay), spanFor(az));
    return wrap;
  }

  function renderRow(id, p) {
    const tr = document.createElement("tr");

    const tdId = document.createElement("td");
    const tdLabel = document.createElement("td");
    const tdCount = document.createElement("td");
    const tdAccel = document.createElement("td");
    const tdGyro = document.createElement("td");

    tdId.textContent = id.slice(0, 8);
    tdLabel.textContent = p.label || "";
    tdCount.textContent = p.count ?? 0;

    tdAccel.appendChild(triplet(p.ax, p.ay, p.az));
    tdGyro.appendChild(triplet(p.gx, p.gy, p.gz));

    tr.append(tdId, tdLabel, tdCount, tdAccel, tdGyro);
    return tr;
  }

  function fullRender() {
    if (!tbody) return;
    tbody.innerHTML = "";
    for (const [id, p] of byId.entries()) {
      tbody.appendChild(renderRow(id, p));
    }
  }

  function updateAllRows() {
    if (!tbody) return;
    const rows = Array.from(byId.entries());
    tbody.innerHTML = "";
    for (const [peerId, peer] of rows) {
      tbody.appendChild(renderRow(peerId, peer));
    }
  }

  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);

    if (m.kind === "snapshot") {
      for (const p of m.peers || []) {
        byId.set(p.peerId, {
          peerId: p.peerId,
          label: p.label,
          count: p.count || 0,
          ax: null, ay: null, az: null,
          gx: null, gy: null, gz: null,
        });
      }
      fullRender();
      return;
    }

    if (m.kind === "left") {
      byId.delete(m.peerId);
      fullRender();
      return;
    }

    if (m.kind === "sample") {
      const p = byId.get(m.peerId) || {
        peerId: m.peerId, label: m.label || "", count: 0,
        ax: null, ay: null, az: null, gx: null, gy: null, gz: null,
      };
      p.count = m.count ?? p.count ?? 0;

      if ("ax" in m) p.ax = m.ax;
      if ("ay" in m) p.ay = m.ay;
      if ("az" in m) p.az = m.az;
      if ("gx" in m) p.gx = m.gx;
      if ("gy" in m) p.gy = m.gy;
      if ("gz" in m) p.gz = m.gz;

      p.label = m.label || p.label;
      byId.set(m.peerId, p);

      updateAllRows();
      return;
    }

    if (m.kind === "hello" || m.kind === "msg") {
      const p = byId.get(m.peerId) || {
        peerId: m.peerId, label: "", count: 0,
        ax: null, ay: null, az: null, gx: null, gy: null, gz: null,
      };
      if (m.label) p.label = m.label;
      byId.set(m.peerId, p);
      fullRender();
      return;
    }
  };

  ws.onerror = () => {
    setTimeout(() => location.reload(), 1500);
  };
})();

// static/dashboard.js
(function () {
  const tbody = document.getElementById("peers");
  const byId = new Map();

  function render() {
    if (!tbody) return;
    tbody.innerHTML = "";
    for (const [id, p] of byId.entries()) {
      const tr = document.createElement("tr");
      const tdId = document.createElement("td");
      const tdLabel = document.createElement("td");
      const tdCount = document.createElement("td");
      tdId.textContent = id.slice(0, 8);
      tdLabel.textContent = p.label || "";
      tdCount.textContent = p.count ?? 0;
      tr.append(tdId, tdLabel, tdCount);
      tbody.appendChild(tr);
    }
  }

  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);

    if (m.kind === "snapshot") {
      // Initial state
      for (const p of m.peers || []) {
        byId.set(p.peerId, { peerId: p.peerId, label: p.label, count: p.count || 0 });
      }
      render();
      return;
    }

    if (m.kind === "left") {
      byId.delete(m.peerId);
      render();
      return;
    }

    if (m.kind === "sample") {
      const p = byId.get(m.peerId) || { peerId: m.peerId, label: m.label, count: 0 };
      p.count = m.count ?? (p.count || 0);
      p.label = m.label || p.label;
      byId.set(m.peerId, p);
      // Re-render periodically to avoid excessive DOM work
      if ((p.count % 10) === 0) render();
      return;
    }

    // Handle the phone's initial hello message to show it immediately
    if (m.kind === "hello" || m.kind === "msg") {
      const p = byId.get(m.peerId) || { peerId: m.peerId, label: "", count: 0 };
      if (m.label) p.label = m.label;
      byId.set(m.peerId, p);
      render();
      return;
    }

    // Optional: show ICE state changes later if you add a status column
    // if (m.kind === "ice") { ... }
  };

  ws.onerror = () => {
    // Best-effort retry after a short delay
    setTimeout(() => location.reload(), 1500);
  };
})();

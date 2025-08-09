(function(){
  const tbody = document.getElementById("peers");
  const ws = new WebSocket(`ws://${location.host}/ws`);

  const byId = new Map();

  function render(){
    tbody.innerHTML = "";
    for (const [id, p] of byId.entries()){
      const tr = document.createElement("tr");
      const tdId = document.createElement("td"); tdId.textContent = id.slice(0,8);
      const tdLabel = document.createElement("td"); tdLabel.textContent = p.label || "";
      const tdCount = document.createElement("td"); tdCount.textContent = p.count ?? 0;
      tr.append(tdId, tdLabel, tdCount);
      tbody.appendChild(tr);
    }
  }

  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.kind === "snapshot"){
      for (const p of m.peers) byId.set(p.peerId, p);
      render();
    } else if (m.kind === "left"){
      byId.delete(m.peerId); render();
    } else if (m.kind === "sample"){
      const p = byId.get(m.peerId) || {peerId: m.peerId, label: m.label, count: 0};
      p.count = m.count;
      p.label = m.label || p.label;
      byId.set(m.peerId, p);
      if ((p.count % 30) === 0) render();
    } else if (m.kind === "msg" || m.kind === "ice"){
      // optional: console.log(m)
    }
  };
})();

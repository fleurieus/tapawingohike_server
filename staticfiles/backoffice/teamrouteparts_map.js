(function(){
  let map, bounds, infoWindow;
  const markers = new Map();   // destId -> marker
  const circles = new Map();   // destId -> circle
  const itemsById = new Map(); // destId -> item payload
  const selectedTeams = new Set(); // team ids
  const palette = [
    "#1E88E5","#E53935","#43A047","#FB8C00","#8E24AA",
    "#00ACC1","#FDD835","#6D4C41","#3949AB","#00897B",
    "#C0CA33","#5E35B1","#D81B60","#7CB342","#F4511E"
  ];

  // ---------- helpers ----------
  function num(x){ if(x==null)return NaN; const v=parseFloat(String(x).trim().replace(",", ".")); return Number.isFinite(v)?v:NaN; }
  function getMapId(){ return document.getElementById("map")?.dataset?.mapId || ""; }
  function getItems(){ const el=document.getElementById("teamrouteparts-dests"); try{ return JSON.parse(el.textContent); }catch{ return []; } }
  function getCsrfToken(){ const m=document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/); return m?decodeURIComponent(m[1]):""; }

  async function ensureLibs(){
    while(!(window.google && google.maps && typeof google.maps.importLibrary==="function")){
      await new Promise(r=>setTimeout(r,50));
    }
    await google.maps.importLibrary("maps");
    try{ await google.maps.importLibrary("marker"); }catch{}
  }

  function colorForRoutePart(order, baseRpId){
    const idx = (order && order>0) ? (order-1) : (baseRpId % palette.length);
    return palette[idx % palette.length];
  }
  function labelText(it){ return `${it.rp_order}.${it.idx}`; }

  // overlap helpers
  function posKey(lat, lng, precision=6){ const f=v=>Number(v).toFixed(precision); return `${f(lat)},${f(lng)}`; }
  function overlapCountFor(it){
    const k = posKey(it.lat, it.lng);
    let n = 0;
    itemsById.forEach(v => {
        if (selectedTeams.has(v.team_id) && posKey(v.lat, v.lng) === k) n++;
    });
    return n;
  }


  // peers in dezelfde plek (base_rp_id + idx) binnen _geselecteerde_ teams
  function peersFor(it){
    const key = it.group_key; // `${base_rp_id}:${idx}`
    const peers = [];
    itemsById.forEach(v=>{
      if (v.group_key===key && selectedTeams.has(v.team_id)) peers.push(v);
    });
    return peers;
  }

  function pinUrl(text, colorHex){
    const bg = colorHex.replace("#","");
    return `/pin?letter=${encodeURIComponent(text)}&bgcolor=${bg}&color=FFFFFF&chs=48x64&format=svg`;
  }

  function isAdvancedMarker(m){
    // AdvancedMarkerElement heeft geen setPosition-functie
    return !!m && typeof m.setPosition !== "function";
  }
  
  function setMarkerPosition(marker, pos){
    if (!marker) return;
    if (isAdvancedMarker(marker)) {
      // AdvancedMarkerElement
      marker.position = pos; // {lat, lng}
    } else if (typeof marker.setPosition === "function") {
      // classic Marker
      marker.setPosition(new google.maps.LatLng(pos.lat, pos.lng));
    }
  }

  function applyMovedPositions(ids, pos){
    ids.forEach(id=>{
      const m = markers.get(id);
      setMarkerPosition(m, pos);
  
      const c = circles.get(id);
      if (c) c.setCenter(pos);
    });
  }
  
  function forceRerender(ids){
    // In edge cases kan een Advanced marker een stale DOM houden;
    // kort togglen van map forceert een schone render.
    ids.forEach(id=>{
      const m = markers.get(id);
      if (!m) return;
      hideMarkerInstance(m);
      showMarkerInstance(m);
    });
  }  

  function ensureCircle(it, center){
    let c = circles.get(it.id);
    const r = num(it.radius)||0;
    if (r <= 0) { if (c) { c.setMap(null); circles.delete(it.id); } return null; }
    if (!c) {
      c = new google.maps.Circle({
        map, center, radius: r,
        strokeColor: "#1976D2", strokeOpacity: 0.35, strokeWeight: 1,
        fillColor: "#1976D2", fillOpacity: 0.08
      });
      circles.set(it.id, c);
    } else { c.setCenter(center); c.setRadius(r); }
    return c;
  }



    function hideMarkerInstance(m){
      if (!m) return;
      if (typeof m.setMap === "function") m.setMap(null);
      else m.map = null; // AdvancedMarkerElement
    }
    function showMarkerInstance(m){
      if (!m) return;
      if (typeof m.setMap === "function") m.setMap(map);
      else m.map = map; // AdvancedMarkerElement
    }
    function setDestVisibility(it, visible){
      const m = markers.get(it.id);
      const c = circles.get(it.id);
      if (visible){ showMarkerInstance(m); if (c) c.setMap(map); }
      else { hideMarkerInstance(m); if (c) c.setMap(null); }
    }
    function refreshTeamVisibility(){
      itemsById.forEach(it => setDestVisibility(it, selectedTeams.has(it.team_id)));
    }
    function setTeamVisibility(teamId, visible){
      itemsById.forEach(it => {
        if (it.team_id === teamId) setDestVisibility(it, visible);
      });
    }


  function refreshOverlapBadges(){
    const adv = google.maps.marker && google.maps.marker.AdvancedMarkerElement;
    if (!adv) return;
    itemsById.forEach((it)=>{
      const m = markers.get(it.id);
      if (!m || !m.content) return;
      const count = overlapCountFor(it);
      let badge = m.content.querySelector(".gmp-badge");
      if (count > 1){
        if (!badge){
          badge = document.createElement("span");
          badge.className = "gmp-badge";
          Object.assign(badge.style, {
            position:"absolute", top:"-4px", right:"-4px",
            minWidth:"18px", height:"18px", padding:"0 4px",
            borderRadius:"9999px", background:"#111827", color:"#fff",
            fontSize:"11px", lineHeight:"18px", textAlign:"center",
            boxShadow:"0 0 0 1px rgba(255,255,255,.75)"
          });
          m.content.appendChild(badge);
        }
        badge.textContent = String(count);
      } else if (badge){ badge.remove(); }
    });
  }

  function removeLocal(id){
    const m = markers.get(id);
    const c = circles.get(id);
    if (m) { hideMarkerInstance(m); markers.delete(id); }
    if (c) { c.setMap(null); circles.delete(id); }
    itemsById.delete(id);
  }

  function syncSelectAll(){
    const all = Array.from(document.querySelectorAll("#teams-list .t-chk"));
    const any = all.some(ch => ch.checked);
    const allChecked = all.length > 0 && all.every(ch => ch.checked);
    const master = document.getElementById("t-all");
    if (!master) return;
    //master.indeterminate = any && !allChecked;
    master.checked = allChecked;
  }  

  // ---------- server calls (bulk) ----------
  async function bulkDelete(ids){
    const res = await fetch(`/backoffice/teamrouteparts/destinations/bulk_delete`, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify({ ids })
    });
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }  

  async function bulkMove(ids, pos){
    const res = await fetch(`/backoffice/teamrouteparts/destinations/bulk_move`, {
      method:"POST", credentials:"same-origin",
      headers:{
        "Content-Type":"application/json",
        "X-CSRFToken": getCsrfToken(),
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify({ ids, lat: pos.lat, lng: pos.lng })
    });
    if(!res.ok) throw new Error(await res.text());
    const out = await res.json();
    // items bijwerken
    ids.forEach(id=>{
      const it = itemsById.get(id);
      if (it){ it.lat = out.lat; it.lng = out.lng; }
    });

    applyMovedPositions(ids, { lat: out.lat, lng: out.lng });
    forceRerender(ids);
    return out;
  }

  async function bulkUpdate(ids, payload){
    const res = await fetch(`/backoffice/teamrouteparts/destinations/bulk_update`, {
      method:"POST", credentials:"same-origin",
      headers:{
        "Content-Type":"application/json",
        "X-CSRFToken": getCsrfToken(),
        "X-Requested-With": "XMLHttpRequest"
      },
      body: JSON.stringify({ ids, ...payload })
    });
    if(!res.ok) throw new Error(await res.text());
    const out = await res.json();
    ids.forEach(id=>{
      const it = itemsById.get(id);
      if (it){
        if ("radius" in payload) it.radius = out.radius;
        if ("confirm_by_user" in payload) it.confirm_by_user = out.confirm_by_user;
        if ("hide_for_user" in payload) it.hide_for_user = out.hide_for_user;
        ensureCircle(it, {lat:num(it.lat), lng:num(it.lng)});
      }
    });
  }

  // ---------- popup ----------
  function buildPopupContent(it){
    const wrap = document.createElement("div");
    wrap.className = "min-w-[240px] text-sm";
    const latStr = Number(it.lat).toFixed(6);
    const lngStr = Number(it.lng).toFixed(6);

    const peers = peersFor(it);            // alleen geselecteerde teams
    const peerIds = peers.map(p=>p.id);    // voor bulk bewerkingen
    const selectedCount = peers.length;

    wrap.innerHTML = `
      <div class="font-semibold mb-1">${it.rp_name} · ${labelText(it)}</div>
      <div class="text-xs text-slate-600 mb-2">Team: <span class="font-medium">${it.team_name}</span></div>

      <div class="grid grid-cols-2 gap-2 mb-2">
        <label class="block">
          <span class="block text-slate-600 text-xs mb-1">Lat</span>
          <input id="f-lat" type="text" value="${latStr}"
                class="w-full border rounded px-2 py-1 font-mono text-xs bg-slate-50" readonly>
        </label>
        <label class="block">
          <span class="block text-slate-600 text-xs mb-1">Lng</span>
          <input id="f-lng" type="text" value="${lngStr}"
                class="w-full border rounded px-2 py-1 font-mono text-xs bg-slate-50" readonly>
        </label>
      </div>

      <div class="flex items-center justify-between mb-2">
        <div class="text-xs text-slate-600">Wijzigingen toepassen op</div>
        <div class="text-xs"><span class="px-1 rounded bg-slate-100">${selectedCount}</span> geselecteerde team(s)</div>
      </div>

      <div class="flex flex-col gap-2 mb-3">
        <label class="block">
          <span class="block text-slate-600 text-xs mb-1">Radius (m)</span>
          <input id="f-radius" type="number" min="0" value="${it.radius ?? 0}"
                class="w-full border rounded px-2 py-1">
        </label>

        <label class="inline-flex items-center gap-2">
          <input id="f-confirm" type="checkbox" ${it.confirm_by_user ? "checked":""}
                 class="h-4 w-4 rounded border-slate-300">
          <span>Confirm by user</span>
        </label>

        <label class="inline-flex items-center gap-2">
          <input id="f-hide" type="checkbox" ${it.hide_for_user ? "checked":""}
                 class="h-4 w-4 rounded border-slate-300">
          <span>Hide for user</span>
        </label>
      </div>

        <div class="flex justify-between items-center gap-2">
            <button id="deleteBtn" class="px-2 py-1 rounded bg-red-600 text-white">
            Verwijderen
            </button>
            <button id="saveBtn" class="px-2 py-1 rounded bg-emerald-600 text-white">
            Opslaan
            </button>
        </div>
    `;

    // save → bulkUpdate naar peers (geselecteerde teams)
    wrap.querySelector("#saveBtn").addEventListener("click", async ()=>{
      const radius = parseInt(wrap.querySelector("#f-radius").value || "0", 10);
      const confirm_by_user = wrap.querySelector("#f-confirm").checked;
      const hide_for_user   = wrap.querySelector("#f-hide").checked;
      try{
        await bulkUpdate(peerIds, { radius, confirm_by_user, hide_for_user });
        infoWindow && infoWindow.close();
        window.clearActivePart && window.clearActivePart();
      }catch(err){ console.error(err); alert("Opslaan mislukt: "+err); }
    });

      wrap.querySelector("#deleteBtn").addEventListener("click", async ()=>{
        const peerIds = peersFor(it).map(p=>p.id);        // alléén geselecteerde teams
        if (!peerIds.length) return;
        if (!confirm(`Destination(s) verwijderen voor ${peerIds.length} geselecteerde team(s)?`)) return;
      
        try {
          const out = await bulkDelete(peerIds);
          (out.deleted || peerIds).forEach(removeLocal);
          infoWindow && infoWindow.close();
          refreshOverlapBadges();
        } catch (err) {
          console.error(err);
          alert("Verwijderen mislukt: " + err);
        }
      });  

    return wrap;
  }

  // ---------- markers ----------
  function addMarker(it, useAdvanced){
    const lat = num(it.lat), lng = num(it.lng);
    if(!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    const pos = { lat, lng };
    const text = labelText(it);
    const col  = colorForRoutePart(it.rp_order, it.base_rp_id);

    let markerInstance;

    if(useAdvanced && google.maps.marker && google.maps.marker.AdvancedMarkerElement){
      const wrap = document.createElement("div");
      wrap.style.position = "relative"; wrap.style.width = "48px"; wrap.style.height = "64px";
      const img = document.createElement("img");
      img.src = pinUrl(text, col); img.width = 48; img.height = 64; img.alt = text; img.style.display="block";
      wrap.appendChild(img);

      // overlap badge
      const count = overlapCountFor(it);
      if (count > 1){
        const badge = document.createElement("span");
        badge.className = "gmp-badge";
        Object.assign(badge.style,{
          position:"absolute", top:"-4px", right:"-4px", minWidth:"18px", height:"18px",
          padding:"0 4px", borderRadius:"9999px", background:"#111827", color:"#fff",
          fontSize:"11px", lineHeight:"18px", textAlign:"center", boxShadow:"0 0 0 1px rgba(255,255,255,.75)"
        });
        badge.textContent = String(count);
        wrap.appendChild(badge);
      }

      markerInstance = new google.maps.marker.AdvancedMarkerElement({
        map, position: pos, content: wrap, title: `${text} · ${it.team_name}`, gmpDraggable: true
      });

      markerInstance.addListener("drag", (ev)=>{
        const p = { lat: ev.latLng.lat(), lng: ev.latLng.lng() };
        // move all peers (visual) while dragging
        peersFor(it).forEach(peer=>{
          const pm = markers.get(peer.id);
          if (pm && pm !== markerInstance) setMarkerPosition(pm, p, useAdvanced);
          const c = circles.get(peer.id);
          if (c) c.setCenter(p);
        });
        const cSelf = circles.get(it.id);
        if (cSelf) cSelf.setCenter(p);
        const latEl = document.getElementById("f-lat");
        const lngEl = document.getElementById("f-lng");
        if (latEl && lngEl) { latEl.value = p.lat.toFixed(6); lngEl.value = p.lng.toFixed(6); }
      });

        markerInstance.addListener("dragend", async (ev)=>{
          const p = { lat: ev.latLng.lat(), lng: ev.latLng.lng() };
          const ids = peersFor(it).map(p=>p.id);
          try {
            await bulkMove(ids, p);           // server opslaan
          } catch(err){
            console.error(err); alert("Opslaan mislukt: "+err);
          }
          // Altijd lokaal hard syncen + evt. re-renderen
          applyMovedPositions(ids, p);
          forceRerender(ids);
          refreshOverlapBadges();
        })

    } else {
      const count = overlapCountFor(it);
      markerInstance = new google.maps.Marker({
        map, position: pos, title: `${text} · ${it.team_name}${count>1?` (×${count})`:""}`, draggable: true,
        icon: { url: pinUrl(text, col), size: new google.maps.Size(48,64), anchor: new google.maps.Point(24,64) }
      });

      markerInstance.addListener("drag", ()=>{
        const p = markerInstance.getPosition();
        const newPos = { lat: p.lat(), lng: p.lng() };
        peersFor(it).forEach(peer=>{
          const pm = markers.get(peer.id);
          if (pm && pm !== markerInstance) setMarkerPosition(pm, newPos, false);
          const c = circles.get(peer.id);
          if (c) c.setCenter(newPos);
        });
        const cSelf = circles.get(it.id);
        if (cSelf) cSelf.setCenter(newPos);
        const latEl = document.getElementById("f-lat");
        const lngEl = document.getElementById("f-lng");
        if (latEl && lngEl) { latEl.value = newPos.lat.toFixed(6); lngEl.value = newPos.lng.toFixed(6); }
      });

      markerInstance.addListener("dragend", async ()=>{
        const p = markerInstance.getPosition();
        const pos = { lat: p.lat(), lng: p.lng() };
        const ids = peersFor(it).map(p=>p.id);
        try {
          await bulkMove(ids, pos);
        } catch(err){
          console.error(err); alert("Opslaan mislukt: "+err);
        }
        applyMovedPositions(ids, pos);
        // (Classic heeft meestal geen ghost, maar schaadt niets:)
        forceRerender(ids);
        refreshOverlapBadges();
      });
    }

    markerInstance.addListener("click", ()=>{
      if (window.setActivePart) window.setActivePart(it.base_rp_id); // highlight per base RoutePart als je wilt
      if(!infoWindow){
        infoWindow = new google.maps.InfoWindow();
        infoWindow.addListener("closeclick", ()=>{ window.clearActivePart && window.clearActivePart(); });
      }
      infoWindow.setContent(buildPopupContent(it));
      infoWindow.open({ map, anchor: markerInstance });
    });

    markers.set(it.id, markerInstance);
    bounds.extend(pos);
    ensureCircle(it, pos);
  }

  function clearAll(){
    markers.forEach(m => { if (m && typeof m.setMap==="function") m.setMap(null); else if(m) m.map=null; });
    markers.clear();
    circles.forEach(c => c.setMap(null)); circles.clear();
  }

  // ---------- init ----------
  async function init(){
    await ensureLibs();

    // init selected teams from checkboxes
    document.querySelectorAll("#teams-list .t-chk").forEach(ch=>{
      if (ch.checked) selectedTeams.add(parseInt(ch.value,10));
    });

    const items = getItems();
    items.forEach(it => itemsById.set(it.id, it));

    const mapId = getMapId();
    const useAdvanced = !!mapId;

    map = new google.maps.Map(document.getElementById("map"), {
      center: { lat: 52.1, lng: 5.1 }, zoom: 7, mapTypeControl: false,
      ...(useAdvanced ? { mapId } : {})
    });

    clearAll();
    bounds = new google.maps.LatLngBounds();
    items.forEach(it => addMarker(it, useAdvanced));
    if(!bounds.isEmpty()) map.fitBounds(bounds, 48);
    if(!useAdvanced) console.warn("Advanced markers niet actief (geen mapId). Fallback naar classic Marker.");

    refreshTeamVisibility();
    refreshOverlapBadges();

    // Team-selectie toggles → (de)selecteer markers visueel (optioneel) of herteken
    document.getElementById("t-all")?.addEventListener("change", (e)=>{
      const check = e.target.checked;
      document.querySelectorAll("#teams-list .t-chk").forEach(ch=>{
        ch.checked = check;
        const id = parseInt(ch.value,10);
        if (check) selectedTeams.add(id); else selectedTeams.delete(id);
      });
      // Toon/verberg alles in één keer
      refreshTeamVisibility();
      refreshOverlapBadges();
      infoWindow && infoWindow.close();
      syncSelectAll();
    });
    
    document.querySelectorAll("#teams-list .t-chk").forEach(ch=>{
      ch.addEventListener("change", (e)=>{
        const id = parseInt(ch.value,10);
        const visible = e.target.checked;
        if (visible) selectedTeams.add(id); else selectedTeams.delete(id);
        // Alleen deze teammarkers togglen
        setTeamVisibility(id, visible);
        refreshOverlapBadges();
        // Sluit popup als die op een verborgen marker zat
        infoWindow && infoWindow.close();
        syncSelectAll();
      });
    });
    
    // Klik op map: alleen nieuwe dest toevoegen als géén infowindow open is (zoals in je andere pagina)
    map.addListener("click", (ev)=>{
      if (infoWindow && infoWindow.getMap()) return;
      // hier zou je een ‘add team destinations’ flow kunnen starten, maar voor nu: niets doen
    });

    syncSelectAll();
  }

  document.addEventListener("DOMContentLoaded", ()=>{ init().catch(console.error); });
})();

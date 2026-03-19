(function () {
  let map, bounds, infoWindow;

  // Pools
  const destGroups = new Map();   // posKey -> { marker, count, lat, lng, imgUrl }
  const compGroups = new Map();   // posKey -> { marker, lat, lng, imgUrl }
  const compIndex  = new Map();   // posKey -> Set(teamId)
  const teamMarkers = new Map();  // teamId -> marker

  // State
  const selectedTeams = new Set();   // Numbers
  let showDestinations = true;

  // Team registries (uit teams_meta)
  const teamMeta = [];               // [{id,name,color?,icon?,label?}] (orde zoals aangeleverd)
  const teamIndexById = new Map();   // id -> 1-based index
  const teamColorById = new Map();   // id -> hex
  const teamLabelById = new Map();   // id -> string
  const teamIconById  = new Map();   // id -> url

  // Route-destination palette (zoals routeparts_map)
  const palette = [
    "#1E88E5", "#E53935", "#43A047", "#FB8C00", "#8E24AA",
    "#00ACC1", "#FDD835", "#6D4C41", "#3949AB", "#00897B",
    "#C0CA33", "#5E35B1", "#D81B60", "#7CB342", "#F4511E"
  ];
  function colorForOrder(order){ const o=Math.max(1, Number(order)||1); return palette[(o-1)%palette.length]; }
  function colorFromIndex(i1){ const i=Math.max(1, Number(i1)||1); return palette[(i-1)%palette.length]; }

  // Eén uniforme kleur voor álle destinations (anders dan teams)
  let destinationColor = "#111827"; // fallback (slate-900)

  // ---------- helpers ----------
  function num(x){ if(x==null) return NaN; const v=parseFloat(String(x).trim().replace(",", ".")); return Number.isFinite(v)?v:NaN; }
  function nTeamId(v){ const n=Number(v); return Number.isFinite(n)?n:v; }
  function getMapId(){ return document.getElementById("map")?.dataset?.mapId || ""; }
  function readJSON(id){ const el=document.getElementById(id); try{ return JSON.parse(el?.textContent||"[]"); }catch{ return []; } }
  function posKey(lat,lng,precision=6){ const f=v=>Number(v).toFixed(precision); return `${f(lat)},${f(lng)}`; }

  async function ensureLibs(){
    while (!(window.google && google.maps && typeof google.maps.importLibrary==="function")){
      await new Promise(r=>setTimeout(r,50));
    }
    await google.maps.importLibrary("maps");
    try { await google.maps.importLibrary("marker"); } catch {}
  }

  // pin endpoint (48x64, witte tekst)
  function pinUrl(text, colorHex){
    const bg = String(colorHex||"#1E88E5").replace("#","");
    return `/pin?letter=${encodeURIComponent(text)}&bgcolor=${bg}&color=FFFFFF&chs=48x64&format=svg`;
  }

  // Advanced vs Classic
  function isAdvancedMarker(m){
    const Adv = google.maps.marker && google.maps.marker.AdvancedMarkerElement;
    return !!(Adv && m instanceof Adv);
  }
  function createBadgeEl(count){
    const badge = document.createElement("span");
    badge.className = "gmp-badge";
    Object.assign(badge.style,{
      position:"absolute", top:"-4px", right:"-4px",
      minWidth:"18px", height:"18px", padding:"0 4px",
      borderRadius:"9999px", background:"#111827", color:"#fff",
      fontSize:"11px", lineHeight:"18px", textAlign:"center",
      boxShadow:"0 0 0 1px rgba(255,255,255,.75)"
    });
    badge.textContent = String(count);
    return badge;
  }
  function makeAdvContent(imgUrl, count){
    const wrap = document.createElement("div");
    wrap.style.position="relative"; wrap.style.width="48px"; wrap.style.height="64px";
    const img = document.createElement("img");
    img.src=imgUrl; img.width=48; img.height=64; img.alt=""; img.style.display="block";
    wrap.appendChild(img);
    if (count && count>1) wrap.appendChild(createBadgeEl(count));
    return wrap;
  }
  function setMarkerMap(m, target){ if(!m)return; if (typeof m.setMap==="function") m.setMap(target); else m.map=target; }
  function setMarkerPosition(m, lat, lng){ if(!m)return; if(typeof m.setPosition==="function") m.setPosition(new google.maps.LatLng(lat,lng)); else m.position={lat,lng}; }
  function makeClassicMarker(pos, title, iconUrl){
    return new google.maps.Marker({
      map, position: pos, title,
      icon: { url: iconUrl, size: new google.maps.Size(48,64), anchor: new google.maps.Point(24,64) }
    });
  }
  function makeAdvMarker(pos, imgUrl, count, title){
    const content = makeAdvContent(imgUrl, count||0);
    const M = google.maps.marker && google.maps.marker.AdvancedMarkerElement;
    return new M({ map, position: pos, content, title });
  }

  // ---------- Team registry uit teams_meta ----------
  function buildTeamRegistryFromMeta(){
    teamMeta.length = 0;
    const raw = readJSON("live-map-teams"); // [{id,name,color?,icon?,label?}]
    (raw || []).forEach(t => teamMeta.push({
      id: nTeamId(t.id),
      name: t.name,
      color: t.color || null,
      icon: t.icon || null,
      label: (t.label!=null ? String(t.label) : null)
    }));
    // volgorde laten zoals aangeleverd; index 1..N
    teamIndexById.clear();
    teamColorById.clear();
    teamLabelById.clear();
    teamIconById.clear();

    teamMeta.forEach((t, idx) => {
      const i = idx + 1; // 1-based
      teamIndexById.set(t.id, i);

      const col = t.color || colorFromIndex(i);
      const label = (t.label && t.label.length ? t.label : String(i));
      const icon = t.icon || pinUrl(label, col);

      teamColorById.set(t.id, col);
      teamLabelById.set(t.id, label);
      teamIconById.set(t.id, icon);
    });

    // Kies een destinations-kleur die niet in gebruik is door teams
    const used = new Set([...teamColorById.values()].map(s => s.toUpperCase()));
    const candidates = [
      "#111827", // slate-900
      "#10B981", // emerald-500
      "#06B6D4", // cyan-500
      "#F97316", // orange-500
      "#22C55E", // green-500
      "#A855F7", // purple-500
      "#F43F5E"  // rose-500
    ];
    destinationColor = candidates.find(c => !used.has(c.toUpperCase())) || "#111827";
  }

  function paintLegend(){
    // team bolletjes
    document.querySelectorAll('[data-legend-color][data-team-id]').forEach(span=>{
      const id = nTeamId(span.dataset.teamId);
      const col = teamColorById.get(id) || "#6b7280";
      span.style.backgroundColor = col;
    });
    // destinations bolletje
    const destSpan = document.getElementById("destinations-color");
    if (destSpan) destSpan.style.backgroundColor = destinationColor;
  }

  // ---------- Destinations (groeperen per positie; uniforme kleur) ----------
  function clearPool(pool){ for(const e of pool.values()) setMarkerMap(e.marker, null); pool.clear(); }

  function ensureDestGroup(lat,lng,order){
    const key = posKey(lat,lng);
    let e = destGroups.get(key);
    const col = destinationColor; // uniforme kleur
    const label = (order!=null && order!=="") ? String(order) : ""; // label blijft order
    const imgUrl = pinUrl(label, col);
    if (!e){
      const pos={lat,lng};
      const marker = (google.maps.marker && google.maps.marker.AdvancedMarkerElement)
        ? makeAdvMarker(pos, imgUrl, 1, label)
        : makeClassicMarker(pos, label, imgUrl);
      e = { marker, count:1, lat, lng, imgUrl };
      destGroups.set(key, e);
      bounds.extend(pos);
    } else {
      e.count += 1;
      if (isAdvancedMarker(e.marker)){
        e.marker.content = makeAdvContent(e.imgUrl, e.count);
      } else if (typeof e.marker.setTitle==="function"){
        e.marker.setTitle(`×${e.count}`);
      }
    }
  }
  function updateDestinationVisibility(){ for(const e of destGroups.values()) setMarkerMap(e.marker, showDestinations?map:null); }

  // ---------- Completed (index per positie; badge op basis van selectie) ----------
  function clearCompleted(){ clearPool(compGroups); compIndex.clear(); }
  function addCompletedEntry(lat,lng,teamIdRaw){
    const teamId = nTeamId(teamIdRaw);
    const key = posKey(lat,lng);
    let s = compIndex.get(key); if(!s){ s=new Set(); compIndex.set(key,s); }
    s.add(teamId);
  }
  function visibleCompletedCountAt(key){
    const s = compIndex.get(key);
    if (!s || s.size===0) return 0;
    if (selectedTeams.size===0) return 0;
    let n=0; s.forEach(tid=>{ if (selectedTeams.has(nTeamId(tid))) n++; });
    return n;
  }

  // Recompute icon for completed group based on current selection
  function chooseCompletedIconUrl(key){
    const s = compIndex.get(key) || new Set();
    let chosenTeam = null;
    for (const tid of s.values()){
      const id = nTeamId(tid);
      if (selectedTeams.has(id)){ chosenTeam = id; break; }
      if (chosenTeam == null) chosenTeam = id;
    }
    return (chosenTeam!=null && teamIconById.get(chosenTeam)) || pinUrl("T", "#444444");
  }

  function ensureCompletedMarker(key, lat, lng){
    const iconUrl = chooseCompletedIconUrl(key);
    const count = visibleCompletedCountAt(key);
    const pos = {lat,lng};

    let e = compGroups.get(key);
    if (!e){
      const marker = (google.maps.marker && google.maps.marker.AdvancedMarkerElement)
        ? makeAdvMarker(pos, iconUrl, count, "")
        : makeClassicMarker(pos, "", iconUrl);
      e = { marker, lat, lng, imgUrl: iconUrl };
      compGroups.set(key, e);
      bounds.extend(pos);
    } else {
      // update content/icon
      if (isAdvancedMarker(e.marker)){
        e.marker.content = makeAdvContent(iconUrl, count);
      } else {
        if (typeof e.marker.setIcon==="function"){
          e.marker.setIcon({ url: iconUrl, size: new google.maps.Size(48,64), anchor: new google.maps.Point(24,64) });
        }
        if (typeof e.marker.setTitle==="function"){
          e.marker.setTitle(count>1?`×${count}`:"");
        }
      }
      e.imgUrl = iconUrl;
    }
    setMarkerMap(e.marker, count>0 ? map : null);
  }
  function rebuildCompletedMarkersFromIndex(){
    for (const [key] of compIndex.entries()){
      const [latStr,lngStr] = key.split(",");
      ensureCompletedMarker(key, parseFloat(latStr), parseFloat(lngStr));
    }
  }
  function refreshCompletedVisibility(){
    // Recompute count AND icon per positie o.b.v. huidige selectie
    for (const [key, e] of compGroups.entries()){
      const count = visibleCompletedCountAt(key);
      const iconUrl = chooseCompletedIconUrl(key);

      if (isAdvancedMarker(e.marker)){
        e.marker.content = makeAdvContent(iconUrl, count);
      } else {
        if (typeof e.marker.setIcon==="function"){
          e.marker.setIcon({ url: iconUrl, size: new google.maps.Size(48,64), anchor: new google.maps.Point(24,64) });
        }
        if (typeof e.marker.setTitle==="function"){
          e.marker.setTitle(count>1?`×${count}`:"");
        }
      }
      e.imgUrl = iconUrl;
      setMarkerMap(e.marker, count>0?map:null);
    }
  }

  // ---------- Team markers (laatste positie), icon uit teams_meta mappings ----------
  function ensureTeamMarker(teamIdRaw, lat, lng){
    const teamId = nTeamId(teamIdRaw);
    const iconUrl = teamIconById.get(teamId) || pinUrl("T", "#444444");
    const pos = {lat,lng};
    let m = teamMarkers.get(teamId);
    if (!m){
      m = (google.maps.marker && google.maps.marker.AdvancedMarkerElement)
        ? makeAdvMarker(pos, iconUrl, null, "")
        : makeClassicMarker(pos, "", iconUrl);
      teamMarkers.set(teamId, m);
      bounds.extend(pos);
    } else {
      setMarkerPosition(m, lat, lng);
      if (isAdvancedMarker(m)){
        m.content = makeAdvContent(iconUrl, null);
      } else if (typeof m.setIcon==="function"){
        m.setIcon({ url: iconUrl, size: new google.maps.Size(48,64), anchor: new google.maps.Point(24,64) });
      }
    }
    const visible = selectedTeams.size>0 && selectedTeams.has(teamId);
    setMarkerMap(m, visible ? map : null);
  }
  function refreshTeamsVisibility(){
    for (const [teamId, m] of teamMarkers.entries()){
      const visible = selectedTeams.size>0 && selectedTeams.has(nTeamId(teamId));
      setMarkerMap(m, visible ? map : null);
    }
  }

  // ---------- Initial build ----------
  function buildInitial(){
    const dests     = readJSON("live-map-destinations");
    const completed = readJSON("live-map-completed");
    const teamlocs  = readJSON("live-map-teamlocs");

    clearPool(destGroups);
    clearCompleted();
    teamMarkers.forEach(m=>setMarkerMap(m,null)); teamMarkers.clear();

    bounds = new google.maps.LatLngBounds();

    // Destinations (uniforme kleur)
    for (const d of dests){
      const lat=num(d.lat), lng=num(d.lng); if(!Number.isFinite(lat)||!Number.isFinite(lng)) continue;
      ensureDestGroup(lat, lng, d["routepart__order"]);
    }

    // Completed -> index + markers
    for (const c of completed){
      const lat=num(c.lat), lng=num(c.lng); if(!Number.isFinite(lat)||!Number.isFinite(lng)) continue;
      addCompletedEntry(lat, lng, c["teamroutepart__team_id"]);
    }
    rebuildCompletedMarkersFromIndex();

    // Team latest
    const seen = new Set();
    for (const t of teamlocs){
      const id = nTeamId(t["team__id"]); if (seen.has(id)) continue; seen.add(id);
      const lat=num(t.lat), lng=num(t.lng); if(!Number.isFinite(lat)||!Number.isFinite(lng)) continue;
      ensureTeamMarker(id, lat, lng);
    }

    if (!bounds.isEmpty()) map.fitBounds(bounds, 48);
    updateDestinationVisibility();
    refreshTeamsVisibility();
  }

  // ---------- Live updates ----------
  function applyLiveState(payload){
    
    // Teams (laatste per team)
    const latest = new Map();
    for (const t of (payload.teams||[])){
      const id = nTeamId(t["team__id"]);
      if (!latest.has(id)) latest.set(id,t);
    }
    for (const [teamId, t] of latest.entries()){
      const lat=num(t.lat), lng=num(t.lng); if(!Number.isFinite(lat)||!Number.isFinite(lng)) continue;
      ensureTeamMarker(teamId, lat, lng);
    }

    // Completed
    clearCompleted();
    for (const c of (payload.completed_destinations||[])){
      const lat=num(c.lat), lng=num(c.lng); if(!Number.isFinite(lat)||!Number.isFinite(lng)) continue;
      addCompletedEntry(lat, lng, c["teamroutepart__team_id"]);
    }
    rebuildCompletedMarkersFromIndex();

    updateDestinationVisibility();
    refreshTeamsVisibility();
    refreshCompletedVisibility();
  }

  // ---------- Filters ----------
  function initFilters(){
    // bouw registry uit teams_meta    
    buildTeamRegistryFromMeta();

    // legend: teams + destinations-kleur tonen
    paintLegend();

    const allCb   = document.getElementById("all-teams");
    const teamCbs = Array.from(document.querySelectorAll(".team-filter"));
    const destCb  = document.getElementById("destinations-filter");

    // init selectie: alles aan
    selectedTeams.clear();
    teamCbs.forEach(cb => selectedTeams.add(nTeamId(cb.dataset.team)));
    refreshTeamsVisibility();
    refreshCompletedVisibility();

    function syncAll(){
      const total = teamCbs.length;
      const checked = teamCbs.filter(cb=>cb.checked).length;
      allCb.checked = (checked===total);
    }

    allCb.addEventListener("change", ()=>{
      const on = allCb.checked;
      selectedTeams.clear();
      teamCbs.forEach(cb=>{
        cb.checked = on;
        if (on) selectedTeams.add(nTeamId(cb.dataset.team));
      });
      refreshTeamsVisibility();
      refreshCompletedVisibility();   // << recompute icons + counts
      syncAll();
    });

    teamCbs.forEach(cb=>{
      cb.addEventListener("change", ()=>{
        const id = nTeamId(cb.dataset.team);
        if (cb.checked) selectedTeams.add(id); else selectedTeams.delete(id);
        refreshTeamsVisibility();
        refreshCompletedVisibility(); // << recompute icons + counts
        syncAll();
      });
    });

    destCb.addEventListener("change", ()=>{
      showDestinations = destCb.checked;
      updateDestinationVisibility();
    });

    syncAll();
  }

  // ---------- init ----------
  async function init(){
    await ensureLibs();

    const mapId = getMapId();
    const useAdvanced = !!mapId;

    map = new google.maps.Map(document.getElementById("map"), {
      center: { lat: 52.1, lng: 5.1 },
      zoom: 7,
      mapTypeControl: false,
      ...(useAdvanced ? { mapId } : {})
    });

    initFilters();
    buildInitial();

    // HTMX live (nu uitgeschakeld in applyLiveState)
    document.body.addEventListener("htmx:afterOnLoad", (e)=>{
      const txt = e.detail?.xhr?.responseText || "";
      if (!txt) return;
      try { applyLiveState(JSON.parse(txt)); } catch {}
    });
  }

  document.addEventListener("DOMContentLoaded", ()=>{ init().catch(console.error); });
})();

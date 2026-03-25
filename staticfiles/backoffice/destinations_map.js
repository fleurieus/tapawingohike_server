/**
 * Destinations map — works for both RoutePart and TeamRoutePart destinations.
 * Reads base URL from #map[data-base-url] so all fetch calls use the correct
 * prefix (/backoffice/routeparts/<id> or /backoffice/teamrouteparts/<id>).
 */
(function () {
  let map, bounds, infoWindow;
  const markers = new Map();
  const circles = new Map();
  const itemsById = new Map();

  // ---------- helpers ----------
  function num(x) {
    if (x == null) return NaN;
    const v = parseFloat(String(x).trim().replace(",", "."));
    return Number.isFinite(v) ? v : NaN;
  }

  function getMapEl() {
    return document.getElementById("map");
  }
  function getMapId() {
    return getMapEl()?.dataset?.mapId || "";
  }
  function getBaseUrl() {
    return getMapEl()?.dataset?.baseUrl || "";
  }

  function getItems() {
    const el = document.getElementById("destinations-boot");
    try { return JSON.parse(el.textContent); } catch { return []; }
  }

  function getCsrfToken() {
    const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  async function ensureLibs() {
    while (!(window.google && google.maps && typeof google.maps.importLibrary === "function")) {
      await new Promise(r => setTimeout(r, 50));
    }
    await google.maps.importLibrary("maps");
    try { await google.maps.importLibrary("marker"); } catch {}
  }

  function pinUrl(text, colorHex) {
    const bg = colorHex.replace("#", "");
    return `/pin?letter=${encodeURIComponent(text)}&bgcolor=${bg}&color=FFFFFF&chs=48x64&format=svg`;
  }

  // single color for destinations page (all same routepart)
  const PIN_COLOR = "#1E88E5";

  function labelText(it, idx) {
    return String(idx != null ? idx : it.idx || "");
  }

  // ---------- circles ----------
  function ensureCircle(it, center) {
    let c = circles.get(it.id);
    const r = num(it.radius) || 0;
    if (r <= 0) {
      if (c) { c.setMap(null); circles.delete(it.id); }
      return null;
    }
    if (!c) {
      c = new google.maps.Circle({
        map, center, radius: r,
        strokeColor: "#1976D2", strokeOpacity: 0.35, strokeWeight: 1,
        fillColor: "#1976D2", fillOpacity: 0.08,
      });
      circles.set(it.id, c);
    } else {
      c.setCenter(center);
      c.setRadius(r);
    }
    return c;
  }

  // ---------- API calls ----------
  function updateTableRow(it) {
    const row = document.getElementById(`row-${it.id}`);
    if (!row) return;
    // cell 1 = "lat, lng"
    row.cells[1].textContent = `${Number(it.lat).toFixed(6)}, ${Number(it.lng).toFixed(6)}`;
  }

  async function postMove(it, pos) {
    const base = getBaseUrl();
    const res = await fetch(`${base}/destinations/${it.id}/move`, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify({ lat: pos.lat, lng: pos.lng }),
    });
    if (!res.ok) throw new Error(await res.text());
    const out = await res.json();
    it.lat = out.lat; it.lng = out.lng;
    itemsById.set(it.id, it);
    const c = circles.get(it.id);
    if (c) c.setCenter({ lat: out.lat, lng: out.lng });
    updateTableRow(it);
  }

  async function postUpdate(it, payload) {
    const base = getBaseUrl();
    const res = await fetch(`${base}/destinations/${it.id}/update`, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrfToken() },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    const out = await res.json();
    it.radius = out.radius;
    it.confirm_by_user = out.confirm_by_user;
    it.hide_for_user = out.hide_for_user;
    ensureCircle(it, { lat: num(it.lat), lng: num(it.lng) });
  }

  async function postDelete(it) {
    const base = getBaseUrl();
    const res = await fetch(`${base}/destinations/${it.id}/delete`, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": getCsrfToken() },
    });
    if (!res.ok) throw new Error(await res.text());
  }

  // ---------- popup ----------
  function buildPopupContent(it) {
    const wrap = document.createElement("div");
    wrap.className = "min-w-[220px] text-sm";
    const latStr = Number(it.lat).toFixed(6);
    const lngStr = Number(it.lng).toFixed(6);

    wrap.innerHTML = `
      <div class="font-semibold mb-2">Destination #${it.id}</div>
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
      <div class="flex flex-col gap-2 mb-3">
        <label class="block">
          <span class="block text-slate-600 text-xs mb-1">Radius (m)</span>
          <input id="f-radius" type="number" min="0" value="${it.radius ?? 0}"
            class="w-full border rounded px-2 py-1">
        </label>
        <label class="inline-flex items-center gap-2">
          <input id="f-confirm" type="checkbox" ${it.confirm_by_user ? "checked" : ""}
            class="h-4 w-4 rounded border-slate-300">
          <span>Confirm by user</span>
        </label>
        <label class="inline-flex items-center gap-2">
          <input id="f-hide" type="checkbox" ${it.hide_for_user ? "checked" : ""}
            class="h-4 w-4 rounded border-slate-300">
          <span>Hide for user</span>
        </label>
      </div>
      <div class="flex justify-end gap-2">
        <button id="deleteBtn" class="px-2 py-1 rounded bg-red-600 text-white">Verwijderen</button>
        <button id="saveBtn" class="px-2 py-1 rounded bg-emerald-600 text-white">Opslaan</button>
      </div>`;

    wrap.querySelector("#saveBtn").addEventListener("click", async () => {
      const radius = parseInt(wrap.querySelector("#f-radius").value || "0", 10);
      const confirm_by_user = wrap.querySelector("#f-confirm").checked;
      const hide_for_user = wrap.querySelector("#f-hide").checked;
      try {
        await postUpdate(it, { radius, confirm_by_user, hide_for_user });
        if (infoWindow) infoWindow.close();
        // update table row
        const row = document.getElementById(`row-${it.id}`);
        if (row) {
          row.cells[3].textContent = String(radius);
          row.cells[4].textContent = confirm_by_user ? "Ja" : "Nee";
          row.cells[5].textContent = hide_for_user ? "Ja" : "Nee";
        }
      } catch (err) { console.error(err); alert("Opslaan mislukt: " + err); }
    });

    wrap.querySelector("#deleteBtn").addEventListener("click", async () => {
      if (!confirm(`Destination #${it.id} verwijderen?`)) return;
      try {
        await postDelete(it);
        removeLocal(it);
        if (infoWindow) infoWindow.close();
      } catch (err) { console.error(err); alert("Verwijderen mislukt: " + err); }
    });

    return wrap;
  }

  // ---------- remove ----------
  function removeLocal(it) {
    const m = markers.get(it.id);
    if (m) { if (typeof m.setMap === "function") m.setMap(null); else m.map = null; markers.delete(it.id); }
    const c = circles.get(it.id);
    if (c) { c.setMap(null); circles.delete(it.id); }
    itemsById.delete(it.id);
    const row = document.getElementById(`row-${it.id}`);
    if (row) row.remove();
  }

  // ---------- markers ----------
  function addMarker(it, idx, useAdvanced) {
    const lat = num(it.lat), lng = num(it.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    const pos = { lat, lng };
    const text = labelText(it, idx);

    let marker;
    if (useAdvanced && google.maps.marker && google.maps.marker.AdvancedMarkerElement) {
      const img = document.createElement("img");
      img.src = pinUrl(text, PIN_COLOR);
      img.width = 48; img.height = 64; img.alt = text;

      marker = new google.maps.marker.AdvancedMarkerElement({
        map, position: pos, content: img, title: text, gmpDraggable: true,
      });
      marker.addListener("drag", (ev) => {
        const p = { lat: ev.latLng.lat(), lng: ev.latLng.lng() };
        const c = circles.get(it.id);
        if (c) c.setCenter(p);
        // live update popup + table
        const latEl = document.getElementById("f-lat");
        const lngEl = document.getElementById("f-lng");
        if (latEl && lngEl) { latEl.value = p.lat.toFixed(6); lngEl.value = p.lng.toFixed(6); }
        const row = document.getElementById(`row-${it.id}`);
        if (row) row.cells[1].textContent = `${p.lat.toFixed(6)}, ${p.lng.toFixed(6)}`;
      });
      marker.addListener("dragend", async (ev) => {
        const p = { lat: ev.latLng.lat(), lng: ev.latLng.lng() };
        try { await postMove(it, p); } catch (err) { console.error(err); alert("Opslaan mislukt: " + err); }
      });
    } else {
      marker = new google.maps.Marker({
        map, position: pos, title: text, draggable: true,
        icon: { url: pinUrl(text, PIN_COLOR), size: new google.maps.Size(48, 64), anchor: new google.maps.Point(24, 64) },
      });
      marker.addListener("drag", () => {
        const p = marker.getPosition();
        const c = circles.get(it.id);
        if (c) c.setCenter({ lat: p.lat(), lng: p.lng() });
        const latEl = document.getElementById("f-lat");
        const lngEl = document.getElementById("f-lng");
        if (latEl && lngEl) { latEl.value = p.lat().toFixed(6); lngEl.value = p.lng().toFixed(6); }
        const row = document.getElementById(`row-${it.id}`);
        if (row) row.cells[1].textContent = `${p.lat().toFixed(6)}, ${p.lng().toFixed(6)}`;
      });
      marker.addListener("dragend", async () => {
        const p = marker.getPosition();
        try { await postMove(it, { lat: p.lat(), lng: p.lng() }); } catch (err) { console.error(err); alert("Opslaan mislukt: " + err); }
      });
    }

    marker.addListener("gmp-click", () => {
      if (!infoWindow) infoWindow = new google.maps.InfoWindow();
      infoWindow.setContent(buildPopupContent(it));
      infoWindow.open({ map, anchor: marker });
    });

    markers.set(it.id, marker);
    bounds.extend(pos);
    ensureCircle(it, pos);
  }

  // ---------- listen for new destinations (via HTMX form save) ----------
  document.body.addEventListener("destination:saved", (e) => {
    const it = e.detail?.item;
    if (!it) return;
    itemsById.set(it.id, it);
    const useAdvanced = !!getMapId();
    addMarker(it, itemsById.size, useAdvanced);
    // close sidepanel
    const sp = document.getElementById("sidepanel");
    if (sp) sp.innerHTML = "";
  });

  // ---------- init ----------
  async function init() {
    await ensureLibs();
    const items = getItems();
    items.forEach(it => itemsById.set(it.id, it));

    const mapId = getMapId();
    const useAdvanced = !!mapId;

    map = new google.maps.Map(getMapEl(), {
      center: { lat: 52.1, lng: 5.1 }, zoom: 7,
      mapTypeControl: false,
      ...(useAdvanced ? { mapId } : {}),
    });

    bounds = new google.maps.LatLngBounds();
    items.forEach((it, i) => addMarker(it, i + 1, useAdvanced));
    if (!bounds.isEmpty()) map.fitBounds(bounds, 48);

    // Click on map → open new destination form in sidepanel
    map.addListener("click", (ev) => {
      if (infoWindow && infoWindow.getMap()) return;
      const base = getBaseUrl();
      const lat = ev.latLng.lat().toFixed(6);
      const lng = ev.latLng.lng().toFixed(6);
      htmx.ajax("GET", `${base}/destinations/new?lat=${lat}&lng=${lng}`, {
        target: "#sidepanel", swap: "innerHTML",
      });
    });
  }

  // ---------- table row edit buttons → open map popup ----------
  function bindTableButtons() {
    document.querySelectorAll("#dest-rows .dest-edit-btn").forEach(btn => {
      const id = Number(btn.dataset.destId);
      if (!id || btn.dataset.bound) return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", () => {
        const it = itemsById.get(id);
        const m = markers.get(id);
        if (!it || !m) return;
        if (!infoWindow) infoWindow = new google.maps.InfoWindow();
        infoWindow.setContent(buildPopupContent(it));
        infoWindow.open({ map, anchor: m });
        const pos = { lat: num(it.lat), lng: num(it.lng) };
        if (Number.isFinite(pos.lat)) map.panTo(pos);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    init().then(() => bindTableButtons()).catch(console.error);
  });
})();

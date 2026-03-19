(function() {
    let map, bounds, infoWindow;
    const markers = new Map(); // id -> marker (Advanced of classic)
    const circles = new Map(); // id -> google.maps.Circle
    const itemsById = new Map(); // id -> item payload
    const palette = [
        "#1E88E5", "#E53935", "#43A047", "#FB8C00", "#8E24AA",
        "#00ACC1", "#FDD835", "#6D4C41", "#3949AB", "#00897B",
        "#C0CA33", "#5E35B1", "#D81B60", "#7CB342", "#F4511E"
    ];
    let activeRpId = null;

    // ---------- helpers ----------
    function num(x) {
        if (x == null) return NaN;
        const v = parseFloat(String(x).trim().replace(",", "."));
        return Number.isFinite(v) ? v : NaN;
    }

    function getMapId() {
        return document.getElementById("map")?.dataset?.mapId || "";
    }

    function getItems() {
        const el = document.getElementById("routeparts-dests");
        try {
            return JSON.parse(el.textContent);
        } catch {
            return [];
        }
    }

    function getCsrfToken() {
        const m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : (window.CSRF_TOKEN || "");
    }

    async function ensureLibs() {
        while (!(window.google && google.maps && typeof google.maps.importLibrary === "function")) {
            await new Promise(r => setTimeout(r, 50));
        }
        await google.maps.importLibrary("maps");
        try {
            await google.maps.importLibrary("marker");
        } catch {}
    }

    function colorForRoutePart(order, rp_id) {
        const idx = (order && order > 0) ? (order - 1) : (rp_id % palette.length);
        return palette[idx % palette.length];
    }

    function labelText(it) {
        return `${it.rp_order}.${it.idx}`;
    }

    // ---- jouw /pin endpoint, 48x64 ----
    function pinUrl(text, colorHex) {
        // Pas evt. query-keys aan als jouw /pin iets anders verwacht.
        const bg = colorHex.replace("#", "");
        return `/pin?letter=${encodeURIComponent(text)}&bgcolor=${bg}&color=FFFFFF&chs=48x64&format=svg`;
    }

    function updatePartDestCount(partId, delta) {
        const li = document.querySelector(`li[data-rp-id="${partId}"]`);
        if (!li) return;
        const span = li.querySelector(".dest-count");
        if (!span) return;
        const val = parseInt(span.textContent || "0", 10);
        span.textContent = Math.max(0, val + delta);
    }

    function removeDestinationLocal(it) {
        // marker
        const m = markers.get(it.id);
        if (m) {
            if (typeof m.setMap === "function") m.setMap(null);
            else m.map = null;
            markers.delete(it.id);
        }
        // cirkel
        const c = circles.get(it.id);
        if (c) {
            c.setMap(null);
            circles.delete(it.id);
        }
        // state
        if (itemsById.has(it.id)) itemsById.delete(it.id);
        // teller in legenda
        updatePartDestCount(it.rp_id, -1);
        // hernummer alle overblijvende
        reindexPart(it.rp_id);
        refreshOverlapBadges();
    }

    window.removePartMarkers = function(partId) {
        // Verwijder alle markers/cirkels van dit RoutePart (na routepart delete)
        const toDelete = [];
        itemsById.forEach((it, id) => {
            if (it.rp_id === partId) toDelete.push(it);
        });
        toDelete.forEach(it => removeDestinationLocal(it));
    };

    document.body.addEventListener("routepart:deleted", (e) => {
        const pid = e.detail && e.detail.rp_id;
        if (pid) {
            window.removePartMarkers(pid);
        }
    });


    function clearAll() {
        markers.forEach(m => {
            if (m && typeof m.setMap === "function") m.setMap(null);
            else if (m) m.map = null;
        });
        markers.clear();
        circles.forEach(c => c.setMap(null));
        circles.clear();
    }

    function setMarkerPosition(marker, pos, useAdvanced) {
        if (useAdvanced && marker && !marker.setMap) {
            marker.position = pos;
        } else if (marker && typeof marker.setPosition === "function") {
            marker.setPosition(pos);
        }
    }

    function ensureCircle(it, center) {
        let c = circles.get(it.id);
        const r = num(it.radius) || 0;
        if (r <= 0) {
            if (c) {
                c.setMap(null);
                circles.delete(it.id);
            }
            return null;
        }
        if (!c) {
            c = new google.maps.Circle({
                map,
                center,
                radius: r,
                strokeColor: "#1976D2",
                strokeOpacity: 0.35,
                strokeWeight: 1,
                fillColor: "#1976D2",
                fillOpacity: 0.08
            });
            circles.set(it.id, c);
        } else {
            c.setCenter(center);
            c.setRadius(r);
        }
        return c;
    }

    function buildPopupContent(it) {
        const wrap = document.createElement("div");
        wrap.className = "min-w-[220px] text-sm";
        const latStr = Number(it.lat).toFixed(6);
        const lngStr = Number(it.lng).toFixed(6);
        const siblings = findOverlapping(it);

        let siblingHtml = "";
        if (siblings.length){
            const items = siblings
            .map(s => `<button data-open="${s.id}" class="underline text-slate-700 hover:text-slate-900">
                        #${s.id} · ${labelText(s)}
                        </button>`)
            .join("<span class='text-slate-400 mx-1'>·</span>");
            siblingHtml = `
            <div class="mt-1 text-xs text-slate-600">
                Ook op dit punt: ${items}
            </div>`;
        }

        wrap.innerHTML = `
            <div class="font-semibold mb-2">Dest #${it.id} · ${labelText(it)}</div>
            ${siblingHtml}

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
            </div>
        `;

        // event: switchen naar een andere overlappende dest
        wrap.querySelectorAll("[data-open]").forEach(btn => {
            btn.addEventListener("click", (ev) => {
            const id = Number(btn.getAttribute("data-open"));
            const other = itemsById.get(id);
            if (other) openPopupFor(other);
            });
        });        

        wrap.querySelector("#saveBtn").addEventListener("click", async () => {
            const radius = parseInt(wrap.querySelector("#f-radius").value || "0", 10);
            const confirm_by_user = wrap.querySelector("#f-confirm").checked;
            const hide_for_user = wrap.querySelector("#f-hide").checked;
            try {
                await postUpdate(it, {
                    radius,
                    confirm_by_user,
                    hide_for_user
                });
                infoWindow && infoWindow.close();
                clearActivePart();
            } catch (err) {
                console.error(err);
                alert("Opslaan mislukt: " + err);
            }
        });

        wrap.querySelector("#deleteBtn").addEventListener("click", async () => {
            if (!confirm(`Destination #${it.id} verwijderen?`)) return;
            try {
                const res = await fetch(`/backoffice/routeparts/${it.rp_id}/destinations/${it.id}/delete`, {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "X-CSRFToken": getCsrfToken(),
                        "X-Requested-With": "XMLHttpRequest"
                    }
                });
                if (!res.ok) throw new Error(await res.text());
                removeDestinationLocal(it);
                infoWindow && infoWindow.close();
                clearActivePart();
            } catch (err) {
                console.error(err);
                alert("Verwijderen mislukt: " + err);
            }
        });



        return wrap;
    }

    function posKey(lat, lng, precision = 6){
        const f = (v) => Number(v).toFixed(precision);
        return `${f(lat)},${f(lng)}`;
    }

    function findOverlapping(it, precision = 6){
        const key = posKey(it.lat, it.lng, precision);
        const out = [];
        itemsById.forEach((v) => {
            if (v.id !== it.id && posKey(v.lat, v.lng, precision) === key) out.push(v);
        });
        return out;
    }
    function overlapCountFor(it){
      const key = posKey(it.lat, it.lng);
      let n = 0;
      itemsById.forEach(v => { if (posKey(v.lat, v.lng) === key) n++; });
      return n; // inclusief it zelf
    }    

    // open popup voor een andere destination (ook bij Advanced markers)
    function openPopupFor(other){
        const m = markers.get(other.id);
        if (!m) return;
        if (!infoWindow) infoWindow = new google.maps.InfoWindow();
        infoWindow.setContent(buildPopupContent(other));
        infoWindow.open({ map, anchor: m });
        // highlight + scroll in sync houden:
        if (window.setActivePart) window.setActivePart(other.rp_id);
        scrollPartIntoView && scrollPartIntoView(other.rp_id);
    }    

    function scrollPartIntoView(partId) {
        const li = document.getElementById(`rp-${partId}`) ||
            document.querySelector(`li[data-rp-id="${partId}"]`);
        if (!li) return;

        // scrollcontainer = dichtstbijzijnde overflow-auto (in jouw layout is dat de bovenste witte card)
        const container = li.closest('.overflow-auto') || li.parentElement;
        if (!container) {
            li.scrollIntoView({
                block: 'center',
                behavior: 'smooth'
            });
            return;
        }

        // Bereken zichtbaarheid en scroll minimaal
        const liTop = li.offsetTop - container.offsetTop;
        const liBottom = liTop + li.offsetHeight;
        const viewTop = container.scrollTop;
        const viewBottom = viewTop + container.clientHeight;

        if (liTop < viewTop) {
            container.scrollTo({
                top: Math.max(liTop - 8, 0),
                behavior: 'smooth'
            });
        } else if (liBottom > viewBottom) {
            container.scrollTo({
                top: liBottom - container.clientHeight + 8,
                behavior: 'smooth'
            });
        }
    }

    // helper om vanuit event een dest toe te voegen
    function addDestinationFromPayload(it) {
        // idx fallback als die ontbreekt
        if (!Number.isFinite(it.idx)) {
            const count = Array.from(itemsById.values()).filter(x => x.rp_id === it.rp_id).length;
            it.idx = count + 1;
        }
        itemsById.set(it.id, it);

        const useAdvanced = !!getMapId();
        addMarker(it, useAdvanced); // tekent marker + (init) cirkel
        updatePartDestCount(it.rp_id, +1); // legenda teller +1

        // hernummeren om eventuele gaten te dichten
        reindexPart(it.rp_id);
        refreshOverlapBadges();
    }

    // luister op het server-event en sluit sidepanel
    document.body.addEventListener("destination:saved", (e) => {
        const it = e.detail?.item;
        if (!it) return;
        addDestinationFromPayload(it);

        const sp = document.getElementById("sidepanel");
        if (sp) sp.innerHTML = ""; // paneel leeg
    });

    function clearActivePart(){
    // maak je eigen state leeg (als je activeRpId gebruikt)
    if (typeof activeRpId !== "undefined") activeRpId = null;

    // verwijder de ring-styling van alle items
    document.querySelectorAll('#parts-list li[data-rp-id]').forEach(li=>{
        li.classList.remove('ring-2', 'ring-emerald-500');
    });
    }
    // eventueel ook exporteren:
    window.clearActivePart = clearActivePart;
    window.setActivePart = function(rpId){
        const same = activeRpId === rpId;

        // Zet alles uit als je op dezelfde + klikt (toggle off)
        if (same) {
            const sp = document.getElementById('sidepanel');
            if (sp) sp.innerHTML = '';
            clearActivePart && clearActivePart();
            return;
        }

        // Activeer nieuwe part
        activeRpId = rpId;
        document.querySelectorAll('#parts-list li[data-rp-id]').forEach(li=>{
            li.classList.toggle('ring-2', +li.dataset.rpId === rpId);
            li.classList.toggle('ring-emerald-500', +li.dataset.rpId === rpId);
        });
    };


    window.routepartsMapRefreshLegend = function() {
        // 1) Bouw een mapping rp_id -> rp_order vanaf de server-JSON
        const items = getItems(); // [{ id, rp_id, rp_order, ... }]
        const rpOrderMap = new Map();
        for (const it of items) {
            if (!rpOrderMap.has(it.rp_id)) {
                rpOrderMap.set(it.rp_id, it.rp_order);
            }
        }

        // 2) Kleur alle legendablokjes
        document.querySelectorAll('[data-legend-color][data-rp-id]').forEach((span) => {
            const pid = parseInt(span.dataset.rpId, 10);

            // Probeer eerst uit JSON…
            let order = rpOrderMap.get(pid);

            // …val terug op DOM (#<order>) als er (nog) geen destinations zijn
            if (!order) {
                const li = span.closest('li');
                const label = li?.querySelector('span.text-slate-500')?.textContent || '';
                const m = label.match(/#(\d+)/);
                order = m ? parseInt(m[1], 10) : 1;
            }

            // Gebruik bestaande kleurfunctie
            const color = colorForRoutePart(order, pid);
            span.style.backgroundColor = color;
        });
    };


    async function postMove(it, pos) {
        const res = await fetch(`/backoffice/routeparts/${it.rp_id}/destinations/${it.id}/move`, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCsrfToken(),
                "X-Requested-With": "XMLHttpRequest"
            },
            body: JSON.stringify({
                lat: pos.lat,
                lng: pos.lng
            })
        });
        if (!res.ok) throw new Error(await res.text());
        const out = await res.json();
        it.lat = out.lat;
        it.lng = out.lng;
        itemsById.set(it.id, it);
        const c = circles.get(it.id);
        if (c) c.setCenter({
            lat: out.lat,
            lng: out.lng
        });
    }

    async function postUpdate(it, payload) {
        const res = await fetch(`/backoffice/routeparts/${it.rp_id}/destinations/${it.id}/update`, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCsrfToken(),
                "X-Requested-With": "XMLHttpRequest"
            },
            body: JSON.stringify(payload)
        });
        if (!res.ok) throw new Error(await res.text());
        const out = await res.json();
        it.radius = out.radius;
        it.confirm_by_user = out.confirm_by_user;
        it.hide_for_user = out.hide_for_user;
        ensureCircle(it, {
            lat: num(it.lat),
            lng: num(it.lng)
        });
    }

    function updateMarkerAppearance(it) {
        const m = markers.get(it.id);
        if (!m) return;
        const color = colorForRoutePart(it.rp_order, it.rp_id);
        const text = labelText(it); // gebruikt it.idx

        // Advanced vs Classic
        if (google.maps.marker && google.maps.marker.AdvancedMarkerElement && !m.setMap) {
            // Advanced: m.content is je <img>
            const img = m.content;
            if (img && img.tagName === 'IMG') {
                img.src = pinUrl(text, color);
                img.alt = text;
                // breedte/hoogte blijven 48x64
            }
        } else {
            // Classic: setIcon
            m.setIcon({
                url: pinUrl(text, color),
                size: new google.maps.Size(48, 64),
                anchor: new google.maps.Point(24, 64)
            });
            m.setTitle(text);
        }
    }

    function reindexPart(partId) {
        // Pak alle items van dit part, sorteer op id (stabiel, eenvoudig)
        const arr = Array.from(itemsById.values()).filter(x => x.rp_id === partId)
            .sort((a, b) => a.id - b.id);
        arr.forEach((it, i) => {
            const newIdx = i + 1;
            if (it.idx !== newIdx) {
                it.idx = newIdx;
                itemsById.set(it.id, it);
                updateMarkerAppearance(it);
            }
        });
    }


    function refreshOverlapBadges(){
    // Alleen zinvol voor Advanced markers
    const adv = google.maps.marker && google.maps.marker.AdvancedMarkerElement;
    if (!adv) return;

    itemsById.forEach((it) => {
        const m = markers.get(it.id);
        if (!m || !m.content) return;
        const count = overlapCountFor(it);

        // zoek bestaande badge in de wrapper
        let badge = m.content.querySelector(".gmp-badge");

        if (count > 1){
        if (!badge){
            badge = document.createElement("span");
            badge.className = "gmp-badge";
            Object.assign(badge.style, {
            position: "absolute",
            top: "-4px",
            right: "-4px",
            minWidth: "18px",
            height: "18px",
            padding: "0 4px",
            borderRadius: "9999px",
            background: "#111827",
            color: "#fff",
            fontSize: "11px",
            lineHeight: "18px",
            textAlign: "center",
            boxShadow: "0 0 0 1px rgba(255,255,255,.75)"
            });
            m.content.appendChild(badge);
        }
        badge.textContent = String(count);
        } else {
        if (badge) badge.remove();
        }
    });
    }


    function addMarker(it, useAdvanced) {
        const lat = num(it.lat),
            lng = num(it.lng);
        if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
        const pos = {
            lat,
            lng
        };
        const text = labelText(it);
        const col = colorForRoutePart(it.rp_order, it.rp_id);

        let markerInstance;
        if (useAdvanced && google.maps.marker && google.maps.marker.AdvancedMarkerElement){
            // wrapper met img + (optioneel) badge
            const count = overlapCountFor(it);
            const wrap = document.createElement("div");
            wrap.style.position = "relative";
            wrap.style.width = "48px";
            wrap.style.height = "64px";

            const img = document.createElement("img");
            img.src = pinUrl(labelText(it), colorForRoutePart(it.rp_order, it.rp_id));
            img.width = 48; img.height = 64; img.alt = labelText(it);
            img.style.display = "block";
            wrap.appendChild(img);

            if (count > 1){
                const badge = document.createElement("span");
                badge.className = "gmp-badge";
                badge.textContent = String(count);
                Object.assign(badge.style, {
                position: "absolute",
                top: "-4px",
                right: "-4px",
                minWidth: "18px",
                height: "18px",
                padding: "0 4px",
                borderRadius: "9999px",
                background: "#111827",   // slate-900
                color: "#fff",
                fontSize: "11px",
                lineHeight: "18px",
                textAlign: "center",
                boxShadow: "0 0 0 1px rgba(255,255,255,.75)"
                });
                wrap.appendChild(badge);
            }

            markerInstance = new google.maps.marker.AdvancedMarkerElement({
                map, position: pos, content: wrap, title: labelText(it), gmpDraggable: true
            });

            // live cirkel-center tijdens slepen
            markerInstance.addListener("drag", (ev)=>{
                const p = { lat: ev.latLng.lat(), lng: ev.latLng.lng() };
                const c = circles.get(it.id);
                if (c) c.setCenter(p);
                // lat/lng in popup bijwerken als die open is
                const latEl = document.getElementById("f-lat");
                const lngEl = document.getElementById("f-lng");
                if (latEl && lngEl) { latEl.value = p.lat.toFixed(6); lngEl.value = p.lng.toFixed(6); }
            });

            markerInstance.addListener("dragend", async (ev)=>{
                const p = { lat: ev.latLng.lat(), lng: ev.latLng.lng() };
                try { await postMove(it, p); } catch(err){ console.error(err); alert("Opslaan mislukt: "+err); }
                // na move kan overlapcount wijzigen → badges verversen
                refreshOverlapBadges();
            });

        } else {
            markerInstance = new google.maps.Marker({
                map,
                position: pos,
                title: text,
                draggable: true,
                icon: {
                    url: pinUrl(text, col),
                    size: new google.maps.Size(48, 64),
                    anchor: new google.maps.Point(24, 64) // onder-midden
                }
            });
            // live cirkel-center tijdens slepen
            markerInstance.addListener("drag", () => {
                const p = markerInstance.getPosition();
                const center = {
                    lat: p.lat(),
                    lng: p.lng()
                };
                const c = circles.get(it.id);
                if (c) c.setCenter(center);
            });
            // opslaan op dragend
            markerInstance.addListener("dragend", async () => {
                const p = markerInstance.getPosition();
                const pos = {
                    lat: p.lat(),
                    lng: p.lng()
                };
                try {
                    await postMove(it, pos);
                } catch (err) {
                    console.error(err);
                    alert("Opslaan mislukt: " + err);
                }
            });
        }

        // klik → mooi popup-formulier
        markerInstance.addListener("click", () => {
            // highlight + scroll naar het juiste RoutePart-item
            if (window.setActivePart) window.setActivePart(it.rp_id);
            scrollPartIntoView(it.rp_id);

            if(!infoWindow) {
                infoWindow = new google.maps.InfoWindow();
                infoWindow.addListener('closeclick', clearActivePart);
            }
            
            infoWindow.setContent(buildPopupContent(it));
            infoWindow.open({
                map,
                anchor: markerInstance
            });
        });


        markers.set(it.id, markerInstance);
        bounds.extend(pos);

        // init radius-cirkel indien > 0
        ensureCircle(it, pos);
    }

    async function init() {
        await ensureLibs();
        const items = getItems();
        items.forEach(it => itemsById.set(it.id, it));

        const mapId = getMapId();
        const useAdvanced = !!mapId;

        map = new google.maps.Map(document.getElementById("map"), {
            center: {
                lat: 52.1,
                lng: 5.1
            },
            zoom: 7,
            mapTypeControl: false,
            ...(useAdvanced ? {
                mapId
            } : {})
        });

        // legenda inkleuren
        items.forEach(it => {
            const el = document.querySelector(`[data-legend-color][data-rp-id="${it.rp_id}"]`);
            if (el) el.style.backgroundColor = colorForRoutePart(it.rp_order, it.rp_id);
        });

        clearAll();
        bounds = new google.maps.LatLngBounds();
        items.forEach(it => addMarker(it, useAdvanced));
        if (!bounds.isEmpty()) map.fitBounds(bounds, 48);

        if (!useAdvanced) console.warn("Advanced markers niet actief (geen mapId). Fallback naar classic Marker.");
        refreshOverlapBadges();

        map.addListener("click", (ev) => {
            if (!activeRpId) return; // alleen als er een actief part is
            if (infoWindow && infoWindow.getMap()) return;

            const lat = ev.latLng.lat().toFixed(6);
            const lng = ev.latLng.lng().toFixed(6);
            htmx.ajax(
                "GET",
                `/backoffice/routeparts/${activeRpId}/destinations/new?lat=${lat}&lng=${lng}`, {
                    target: "#sidepanel",
                    swap: "innerHTML"
                }
            );
        });


    }

    document.addEventListener("DOMContentLoaded", () => {
        init().catch(console.error);
    });
})();
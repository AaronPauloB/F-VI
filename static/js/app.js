let map = null;
let routeLayers = [];
let currentRoutes = [];

const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

async function checkHealth() {
    try {
        const response = await fetch("/api/health");
        const data = await response.json();
        const badge = $("#statusBadge");
        if (data.configured) {
            badge.textContent = "API configured";
            badge.classList.add("ok");
        } else {
            badge.textContent = "API key required";
            badge.classList.add("bad");
        }
    } catch {
        $("#statusBadge").textContent = "Backend offline";
        $("#statusBadge").classList.add("bad");
    }
}

function selectedAvoids() {
    return [...document.querySelectorAll('.checkbox-grid input:checked')].map((input) => input.value);
}

function setLoading(loading) {
    const button = $("#routeBtn");
    button.classList.toggle("loading", loading);
    button.textContent = loading ? "Calculating…" : "Find Route";
}

function showError(message) {
    const box = $("#errorBox");
    box.textContent = message;
    box.classList.remove("hidden");
}

function clearError() {
    $("#errorBox").classList.add("hidden");
}

function formatDuration(seconds) {
    const minutes = Math.round(Number(seconds || 0) / 60);
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return hours ? `${hours} hr ${mins} min` : `${mins} min`;
}

function renderRouteCards(routes) {
    $("#routeCards").innerHTML = routes.map((route, index) => `
        <article class="route-card ${index === 0 ? "active" : ""}" data-index="${index}">
            <span class="route-tag">${index === 0 ? "Primary" : "Alternative"}</span>
            <h3>${escapeHtml(route.route_name || `Route ${index + 1}`)}</h3>
            <div class="route-line">${escapeHtml(route.origin)} → ${escapeHtml(route.destination)}</div>
            <div class="metrics">
                <div class="metric"><span>Distance</span><strong>${route.distance.toFixed(2)} ${escapeHtml(route.distance_unit)}</strong></div>
                <div class="metric"><span>Time</span><strong>${escapeHtml(route.duration)}</strong></div>
                <div class="metric"><span>Route</span><strong>${escapeHtml(route.route_type_label)}</strong></div>
                <div class="metric"><span>Tolls</span><strong>${route.toll_cost_usd == null ? "Not reported" : `$${route.toll_cost_usd.toFixed(2)}`}</strong></div>
            </div>
            <div class="route-flags">
                ${route.has_toll_road ? '<span class="flag">Toll road</span>' : ''}
                ${route.has_ferry ? '<span class="flag">Ferry</span>' : ''}
                <span class="flag">${route.maneuvers.length} steps</span>
            </div>
        </article>
    `).join("");

    document.querySelectorAll(".route-card").forEach((card) => {
        card.addEventListener("click", () => {
            document.querySelectorAll(".route-card").forEach((item) => item.classList.remove("active"));
            card.classList.add("active");
            renderRouteDetails(Number(card.dataset.index));
        });
    });
}

function renderRouteDetails(index) {
    const route = currentRoutes[index];
    if (!route) return;

    $("#stepCount").textContent = `${route.maneuvers.length} steps`;
    $("#directionsList").innerHTML = route.maneuvers.map((step) => `
        <div class="direction-item">
            <div class="step-number">${step.number}</div>
            <div class="direction-text">${escapeHtml(step.narrative)}</div>
            <div class="direction-meta">${step.distance.toFixed(2)} ${escapeHtml(route.distance_unit)}<br>${formatDuration(step.time)}</div>
        </div>
    `).join("");

    drawMap(index);
}

function ensureMap() {
    if (map) return;
    map = L.map("map").setView([14.5995, 120.9842], 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);
}

function drawMap(index) {
    const route = currentRoutes[index];
    if (!route) return;
    ensureMap();
    routeLayers.forEach((layer) => map.removeLayer(layer));
    routeLayers = [];

    const points = route.shape || [];
    if (points.length >= 2) {
        const line = L.polyline(points, { weight: 5, opacity: 0.9 }).addTo(map);
        routeLayers.push(line);
        const start = L.marker(points[0]).bindPopup(`<strong>Start</strong><br>${escapeHtml(route.origin)}`).addTo(map);
        const end = L.marker(points[points.length - 1]).bindPopup(`<strong>Destination</strong><br>${escapeHtml(route.destination)}`).addTo(map);
        routeLayers.push(start, end);
        map.fitBounds(line.getBounds(), { padding: [24, 24] });
    }
}

function renderResults(data) {
    currentRoutes = data.routes || [];
    if (!currentRoutes.length) {
        showError("No routes were returned.");
        return;
    }
    $("#emptyState").classList.add("hidden");
    $("#historyPanel").classList.add("hidden");
    $("#results").classList.remove("hidden");
    renderRouteCards(currentRoutes);
    renderRouteDetails(0);
    setTimeout(() => map?.invalidateSize(), 50);
}

async function submitRoute(event) {
    event.preventDefault();
    clearError();
    setLoading(true);

    const payload = {
        origin: $("#origin").value.trim(),
        destination: $("#destination").value.trim(),
        unit: $("#unit").value,
        route_type: $("#routeType").value,
        avoids: selectedAvoids(),
        alternates: $("#alternates").checked,
    };

    try {
        const response = await fetch("/api/route", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || "Unable to calculate the route.");
        renderResults(data);
    } catch (error) {
        showError(error.message || "Something went wrong while calculating the route.");
    } finally {
        setLoading(false);
    }
}

async function loadHistory() {
    clearError();
    try {
        const response = await fetch("/api/history?limit=20");
        const data = await response.json();
        const list = $("#historyList");
        if (!data.history.length) {
            list.innerHTML = '<div class="history-item">No route searches have been saved yet.</div>';
        } else {
            list.innerHTML = data.history.map((item) => `
                <div class="history-item">
                    <div class="history-route">${escapeHtml(item.origin)} → ${escapeHtml(item.destination)}</div>
                    <div class="history-meta">${escapeHtml(item.route_type)} • ${item.distance ?? "—"} ${escapeHtml(item.distance_unit ?? "")} • ${escapeHtml(item.duration ?? "—")}</div>
                </div>
            `).join("");
        }
        $("#results").classList.add("hidden");
        $("#emptyState").classList.add("hidden");
        $("#historyPanel").classList.remove("hidden");
    } catch (error) {
        showError("Could not load search history.");
    }
}

async function clearHistory() {
    await fetch("/api/history", { method: "DELETE" });
    await loadHistory();
}

function downloadReport() {
    if (!currentRoutes.length) return;
    const route = currentRoutes.find((_, index) => document.querySelector(`.route-card[data-index="${index}"].active`)) || currentRoutes[0];
    const lines = [
        "MAPQUEST ROUTE PLANNER REPORT",
        "=========================================",
        `From: ${route.origin}`,
        `To: ${route.destination}`,
        `Route: ${route.route_name || "Primary Route"}`,
        `Type: ${route.route_type_label}`,
        `Distance: ${route.distance.toFixed(2)} ${route.distance_unit}`,
        `Travel time: ${route.duration}`,
        `Toll cost (USD): ${route.toll_cost_usd == null ? "Not reported" : route.toll_cost_usd.toFixed(2)}`,
        "",
        "DIRECTIONS",
        "-----------------------------------------",
        ...route.maneuvers.map((step) => `${step.number}. ${step.narrative} (${step.distance.toFixed(2)} ${route.distance_unit})`),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "mapquest-route-report.txt";
    link.click();
    URL.revokeObjectURL(url);
}

$("#routeForm").addEventListener("submit", submitRoute);
$("#historyBtn").addEventListener("click", loadHistory);
$("#clearHistoryBtn").addEventListener("click", clearHistory);
$("#downloadBtn").addEventListener("click", downloadReport);
$("#swapBtn").addEventListener("click", () => {
    const origin = $("#origin").value;
    $("#origin").value = $("#destination").value;
    $("#destination").value = origin;
});

checkHealth();

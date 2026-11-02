const state = {
  data: { reports: [], transport_records: [], zones: [] },
  database: null,
  map: null,
  markers: null,
  toastTimer: null,
  objectUrls: [],
  photoPreviewUrl: "",
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));
const formatDate = (value) => value ? new Date(value).toLocaleString("es-PE") : "—";
const statusClass = (status) => ({
  "Pendiente": "pending",
  "En investigación": "investigation",
  "Resuelto": "done",
  "Revisado": "done",
  "Observada": "observed",
}[status] || "");
const makeId = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;

function openDatabase() {
  if (state.database) return Promise.resolve(state.database);
  return new Promise((resolve, reject) => {
    if (!window.indexedDB) {
      reject(new Error("Este navegador no permite guardar registros localmente."));
      return;
    }
    const request = indexedDB.open("ForestGuardLocal", 1);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains("reports")) database.createObjectStore("reports", { keyPath: "id" });
      if (!database.objectStoreNames.contains("transport_records")) database.createObjectStore("transport_records", { keyPath: "id" });
      if (!database.objectStoreNames.contains("zones")) database.createObjectStore("zones", { keyPath: "name" });
    };
    request.onsuccess = () => {
      state.database = request.result;
      state.database.onversionchange = () => state.database.close();
      resolve(state.database);
    };
    request.onerror = () => reject(request.error || new Error("No se pudo abrir el almacenamiento del navegador."));
    request.onblocked = () => reject(new Error("Cierra otras pestañas de ForestGuard e inténtalo de nuevo."));
  });
}

async function storeRequest(storeName, mode, action, value) {
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(storeName, mode);
    let result;
    let request;
    try {
      const store = transaction.objectStore(storeName);
      if (action === "getAll") request = store.getAll();
      else if (action === "put") request = store.put(value);
      else if (action === "delete") request = store.delete(value);
      else throw new Error("Operación de almacenamiento no válida.");
    } catch (error) {
      reject(error);
      return;
    }
    request.onsuccess = () => { result = request.result; };
    request.onerror = () => reject(request.error || new Error("No se pudo acceder a los registros locales."));
    transaction.oncomplete = () => resolve(result);
    transaction.onerror = () => reject(transaction.error || new Error("No se pudieron guardar los cambios."));
    transaction.onabort = () => reject(transaction.error || new Error("Se canceló el guardado de los cambios."));
  });
}

async function refreshData() {
  const [reports, transportRecords, zones] = await Promise.all([
    storeRequest("reports", "readonly", "getAll"),
    storeRequest("transport_records", "readonly", "getAll"),
    storeRequest("zones", "readonly", "getAll"),
  ]);
  state.data = {
    reports: reports.sort((a, b) => b.created_at.localeCompare(a.created_at)),
    transport_records: transportRecords.sort((a, b) => b.created_at.localeCompare(a.created_at)),
    zones,
  };
  renderAll();
}

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.remove("show"), 3200);
}

function setView(viewName) {
  const view = $(`#view-${viewName}`);
  if (!view) return;
  $$(".view").forEach((item) => item.classList.toggle("active", item === view));
  $$("[data-view]").forEach((link) => link.classList.toggle("active", link.dataset.view === viewName));
  if (viewName === "mapa") {
    initializeMap();
    setTimeout(() => state.map?.invalidateSize(), 80);
  }
  if (viewName === "estadisticas") drawStatistics();
}

function openDialog({ title, eyebrow = "FORESTGUARD", content }) {
  $("#dialog-title").textContent = title;
  $("#dialog-eyebrow").textContent = eyebrow;
  $("#dialog-content").innerHTML = content;
  $("#app-dialog").showModal();
}

function closeDialog() {
  $("#app-dialog").close();
  $("#dialog-content").replaceChildren();
  state.objectUrls.forEach((url) => URL.revokeObjectURL(url));
  state.objectUrls = [];
  if (state.photoPreviewUrl) URL.revokeObjectURL(state.photoPreviewUrl);
  state.photoPreviewUrl = "";
}

function renderRecentReports() {
  const root = $("#recent-reports");
  const reports = state.data.reports.slice(0, 4);
  if (!reports.length) {
    root.className = "empty-state";
    root.textContent = "Aún no hay denuncias. Registra la primera incidencia.";
    return;
  }
  root.className = "table-wrap";
  root.innerHTML = `<table><thead><tr><th>Incidencia</th><th>Lugar</th><th>Estado</th><th>Fecha</th><th></th></tr></thead><tbody>${reports.map((report) => `
    <tr><td><strong>${escapeHtml(report.type)}</strong><small>${escapeHtml(report.description)}</small></td>
    <td>${escapeHtml(report.location)}</td><td><span class="pill ${statusClass(report.status)}">${escapeHtml(report.status)}</span></td>
    <td>${escapeHtml(formatDate(report.created_at))}</td>
    <td><div class="row-actions"><button class="button button-quiet button-small" data-edit-report="${escapeHtml(report.id)}">Monitorear</button></div></td></tr>`).join("")}</tbody></table>`;
}

function renderReports() {
  const query = ($("#report-search").value || "").trim().toLocaleLowerCase();
  const status = $("#report-status-filter").value;
  const filtered = state.data.reports.filter((report) => {
    const text = [report.type, report.location, report.description, report.status].join(" ").toLocaleLowerCase();
    return (!query || text.includes(query)) && (!status || report.status === status);
  });
  $("#report-count").textContent = `${filtered.length} de ${state.data.reports.length} registros`;
  $("#reports-table").innerHTML = filtered.length ? filtered.map((report) => `
    <tr><td><strong>${escapeHtml(report.type)}</strong><small>${escapeHtml(report.description)}</small></td>
    <td>${escapeHtml(report.location)}</td><td><span class="pill ${statusClass(report.status)}">${escapeHtml(report.status)}</span></td>
    <td>${escapeHtml(formatDate(report.created_at))}</td>
    <td><div class="row-actions"><button class="button button-quiet button-small" data-edit-report="${escapeHtml(report.id)}">Monitorear</button></div></td></tr>`).join("") :
    `<tr><td colspan="5"><div class="empty-state">No hay denuncias que coincidan con la búsqueda.</div></td></tr>`;
}

function renderTransports() {
  const rows = state.data.transport_records;
  $("#transports-table").innerHTML = rows.length ? rows.map((record) => `
    <tr><td><strong>${escapeHtml(record.guide)}</strong></td><td>${escapeHtml(record.plate)}</td>
    <td>${escapeHtml(record.origin)} → ${escapeHtml(record.destination)}</td><td>${escapeHtml(record.wood_type || "—")}</td>
    <td>${record.volume == null ? "—" : `${escapeHtml(record.volume)} m³`}</td>
    <td><span class="pill ${statusClass(record.verification_status)}">${escapeHtml(record.verification_status)}</span></td>
    <td>${escapeHtml(formatDate(record.created_at))}</td></tr>`).join("") :
    `<tr><td colspan="7"><div class="empty-state">Todavía no hay transportes registrados.</div></td></tr>`;
}

function renderZones() {
  const rows = state.data.zones;
  $("#zones-table").innerHTML = rows.length ? rows.map((zone) => `
    <tr><td><strong>${escapeHtml(zone.name)}</strong></td><td>${Number(zone.latitude).toFixed(6)}</td>
    <td>${Number(zone.longitude).toFixed(6)}</td><td><span class="pill ${zone.status === "Atención prioritaria" ? "observed" : ""}">${escapeHtml(zone.status)}</span></td>
    <td><div class="row-actions"><button class="button button-quiet button-small" data-edit-zone="${escapeHtml(zone.name)}">Editar</button><button class="button button-danger button-small" data-delete-zone="${escapeHtml(zone.name)}">Eliminar</button></div></td></tr>`).join("") :
    `<tr><td colspan="5"><div class="empty-state">Todavía no hay zonas monitoreadas.</div></td></tr>`;
}

function refreshMetrics() {
  const reports = state.data.reports;
  $("#metric-areas").textContent = state.data.zones.length;
  $("#metric-alerts").textContent = reports.filter((report) => report.status === "Pendiente" || report.status === "En investigación").length;
  $("#metric-transports").textContent = state.data.transport_records.length;
  $("#metric-reviewed").textContent = reports.filter((report) => report.status === "Resuelto" || report.status === "Revisado").length;
}

function renderAll() {
  refreshMetrics();
  renderRecentReports();
  renderReports();
  renderTransports();
  renderZones();
  if (state.map) renderMapMarkers();
  if ($("#view-estadisticas").classList.contains("active")) drawStatistics();
}

function field(label, name, { type = "text", required = false, value = "", hint = "", min, max, step } = {}) {
  const attrs = [
    `name="${escapeHtml(name)}"`,
    `type="${escapeHtml(type)}"`,
    required ? "required" : "",
    value !== "" ? `value="${escapeHtml(value)}"` : "",
    min !== undefined ? `min="${min}"` : "",
    max !== undefined ? `max="${max}"` : "",
    step !== undefined ? `step="${step}"` : "",
  ].filter(Boolean).join(" ");
  return `<div class="form-field"><label for="field-${escapeHtml(name)}">${escapeHtml(label)}</label><input id="field-${escapeHtml(name)}" ${attrs}>${hint ? `<small class="form-hint">${escapeHtml(hint)}</small>` : ""}</div>`;
}

function formError(text) {
  const element = $("#form-error");
  if (!element) {
    showToast(text);
    return;
  }
  element.textContent = text;
  element.classList.add("visible");
}

function formButtons(label) {
  return `<div id="form-error" class="form-error" role="alert"></div><div class="form-actions"><button class="button button-quiet" type="button" data-action="close-dialog">Cancelar</button><button class="button button-primary" type="submit">${escapeHtml(label)}</button></div>`;
}

function showReportForm() {
  openDialog({
    title: "Registrar denuncia",
    eyebrow: "NUEVA INCIDENCIA",
    content: `<form id="report-form" class="form">
      ${field("Lugar o zona", "location", { required: true })}
      ${field("Tipo de incidente", "type", { required: true })}
      <div class="form-field"><label for="field-description">Descripción</label><textarea id="field-description" name="description" required></textarea></div>
      <div class="form-grid">${field("Latitud (opcional)", "latitude", { type: "number", min: -90, max: 90, step: "any" })}${field("Longitud (opcional)", "longitude", { type: "number", min: -180, max: 180, step: "any" })}</div>
      <div class="form-field"><label for="field-evidence">Fotos o documentos PDF</label><input id="field-evidence" type="file" name="evidence" accept="image/*,.pdf" multiple><small class="form-hint">Hasta cinco imágenes o PDF. Máximo total: 16 MB.</small></div>
      ${formButtons("Guardar denuncia")}
    </form>`,
  });
}

function showTransportForm() {
  openDialog({
    title: "Registrar transporte de madera",
    eyebrow: "TRAZABILIDAD",
    content: `<form id="transport-form" class="form">
      <div class="form-grid">${field("Número de guía", "guide", { required: true })}${field("Placa", "plate", { required: true, hint: "De 5 a 7 letras o números." })}</div>
      <div class="form-grid">${field("Origen", "origin", { required: true })}${field("Destino", "destination", { required: true })}</div>
      <div class="form-grid">${field("Especie o tipo de madera", "wood_type", { required: true })}${field("Volumen (m³, opcional)", "volume", { type: "number", min: "0.01", step: "any" })}</div>
      <div class="form-field"><label for="field-verification_status">Verificación de guía</label><select id="field-verification_status" name="verification_status"><option>Pendiente de verificación</option><option>Verificada</option><option>Observada</option></select><small class="form-hint">La verificación se registra manualmente; no consulta un padrón oficial.</small></div>
      ${formButtons("Guardar transporte")}
    </form>`,
  });
}

function showZoneForm(existing = null) {
  const zone = existing || {};
  const name = zone.name || "";
  openDialog({
    title: existing ? "Editar zona" : "Agregar zona",
    eyebrow: "ZONAS MONITOREADAS",
    content: `<form id="zone-form" class="form" data-existing-name="${escapeHtml(name)}">
      ${field("Nombre de la zona", "name", { required: true, value: name })}
      <div class="form-grid">${field("Latitud", "latitude", { required: true, type: "number", min: -90, max: 90, step: "any", value: zone.latitude ?? "" })}${field("Longitud", "longitude", { required: true, type: "number", min: -180, max: 180, step: "any", value: zone.longitude ?? "" })}</div>
      <div class="form-field"><label for="field-status">Estado del monitoreo</label><select id="field-status" name="status"><option ${zone.status === "Monitoreo activo" ? "selected" : ""}>Monitoreo activo</option><option ${zone.status === "Alerta pendiente" ? "selected" : ""}>Alerta pendiente</option><option ${zone.status === "Atención prioritaria" ? "selected" : ""}>Atención prioritaria</option></select></div>
      ${formButtons("Guardar zona")}
    </form>`,
  });
}

function showReportDetails(report) {
  const evidence = report.evidence?.length ? `<div class="form-field"><label>Evidencias</label><div class="evidence-list">${report.evidence.map((item) => {
    const url = URL.createObjectURL(item.file);
    state.objectUrls.push(url);
    return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(item.name)}</a>`;
  }).join("")}</div></div>` : "";
  openDialog({
    title: "Seguimiento de denuncia",
    eyebrow: report.type,
    content: `<form id="followup-form" class="form" data-report-id="${escapeHtml(report.id)}">
      <p class="form-hint">${escapeHtml(report.location)} · Registrada ${escapeHtml(formatDate(report.created_at))}</p>
      <div class="form-field"><label for="field-followup-status">Estado</label><select id="field-followup-status" name="status">${["Pendiente", "En investigación", "Resuelto", "Revisado"].map((item) => `<option ${report.status === item ? "selected" : ""}>${item}</option>`).join("")}</select></div>
      <div class="form-field"><label for="field-assigned_to">Responsable asignado</label><input id="field-assigned_to" name="assigned_to" value="${escapeHtml(report.assigned_to || "")}"></div>
      <div class="form-field"><label for="field-notes">Notas de seguimiento</label><textarea id="field-notes" name="notes">${escapeHtml(report.notes || "")}</textarea></div>
      <div class="form-field"><label>Descripción original</label><div class="analysis-result">${escapeHtml(report.description)}</div></div>${evidence}
      ${formButtons("Guardar seguimiento")}
    </form>`,
  });
}

function showPhotoReview() {
  openDialog({
    title: "Análisis visual de fotografía",
    eyebrow: "DETECCIÓN · ANÁLISIS LOCAL",
    content: `<form id="photo-form" class="form">
      <div class="form-field"><label for="photo-input">Selecciona una fotografía</label><input id="photo-input" name="photo" type="file" accept="image/*" required><small class="form-hint">La imagen se procesa en este navegador; no se envía por internet para analizarla.</small></div>
      <img id="photo-preview" class="photo-preview" alt="Vista previa" hidden>
      <div id="photo-result" class="analysis-result">Elige una imagen para calcular sus indicadores visuales.</div>
      <div class="form-grid">${field("Lugar (opcional)", "location")}${field("Latitud (opcional)", "latitude", { type: "number", min: -90, max: 90, step: "any" })}</div>
      ${field("Longitud (opcional)", "longitude", { type: "number", min: -180, max: 180, step: "any" })}
      <p class="form-hint">El resultado es orientativo y se basa solo en colores; no confirma tala ilegal ni reemplaza una inspección humana.</p>
      <div id="form-error" class="form-error" role="alert"></div>
      <div class="form-actions"><button class="button button-quiet" type="button" data-action="close-dialog">Cerrar</button><button id="save-photo-report" class="button button-primary" type="submit" disabled>Guardar como denuncia</button></div>
    </form>`,
  });
}

function analyzePhoto(file) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const objectUrl = URL.createObjectURL(file);
    image.onload = () => {
      try {
        const canvas = document.createElement("canvas");
        const scale = Math.min(1, 512 / Math.max(image.naturalWidth, image.naturalHeight));
        canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
        canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
        const context = canvas.getContext("2d", { willReadFrequently: true });
        if (!context) throw new Error("No se pudo preparar el análisis de la imagen.");
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
        let greenPixels = 0;
        let soilPixels = 0;
        let brightnessTotal = 0;
        const count = pixels.length / 4;
        for (let index = 0; index < pixels.length; index += 4) {
          const red = pixels[index];
          const green = pixels[index + 1];
          const blue = pixels[index + 2];
          const lowest = Math.min(red, green, blue);
          brightnessTotal += (red + green + blue) / 3;
          if (green > red * 1.08 && green > blue * 1.05 && green - lowest >= 15) greenPixels++;
          if (red > green * 1.06 && green >= blue * 0.85 && red - blue >= 20) soilPixels++;
        }
        const greenPercent = greenPixels * 100 / count;
        const soilPercent = soilPixels * 100 / count;
        let finding;
        let observation;
        if (greenPercent < 30 && soilPercent >= 20) {
          finding = "Posibles indicios de tala o pérdida de cobertura forestal";
          observation = "La combinación de vegetación visible reducida y tonos de suelo elevados amerita una revisión del área.";
        } else if (greenPercent >= 35 && soilPercent < 20) {
          finding = "Sin indicios claros de tala en el análisis por color";
          observation = "Los colores analizados no muestran señales claras; esto no descarta tala ni reemplaza una inspección.";
        } else {
          finding = "Resultado no concluyente; se recomienda revisión";
          observation = "Los indicadores de color son mixtos y no permiten una clasificación clara.";
        }
        resolve({
          dimensions: `${image.naturalWidth} × ${image.naturalHeight}`,
          greenPercent,
          soilPercent,
          brightness: brightnessTotal / count,
          finding,
          observation,
        });
      } catch {
        reject(new Error("No se pudo leer la imagen. Prueba con otro archivo."));
      } finally {
        URL.revokeObjectURL(objectUrl);
      }
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error("Selecciona una imagen válida."));
    };
    image.src = objectUrl;
  });
}

function initializeMap() {
  const mapElement = $("#map");
  if (state.map || !mapElement) return;
  if (!window.L) {
    mapElement.textContent = "El mapa necesita conexión a Internet para cargar sus componentes.";
    return;
  }
  state.map = L.map(mapElement).setView([-12.5, -70], 7);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 19,
  }).addTo(state.map);
  state.markers = L.layerGroup().addTo(state.map);
  renderMapMarkers();
}

function renderMapMarkers() {
  if (!state.markers) return;
  state.markers.clearLayers();
  const coordinates = [];
  for (const zone of state.data.zones) {
    const position = [Number(zone.latitude), Number(zone.longitude)];
    L.marker(position).bindPopup(`<strong>${escapeHtml(zone.name)}</strong><br>${escapeHtml(zone.status)}`).addTo(state.markers);
    coordinates.push(position);
  }
  for (const report of state.data.reports) {
    if (report.latitude == null || report.longitude == null) continue;
    const position = [Number(report.latitude), Number(report.longitude)];
    L.circleMarker(position, {
      radius: 7,
      color: "#f0bd55",
      fillColor: "#f0bd55",
      fillOpacity: 0.85,
    }).bindPopup(`<strong>${escapeHtml(report.type)}</strong><br>${escapeHtml(report.location)}<br>${escapeHtml(report.status)}`).addTo(state.markers);
    coordinates.push(position);
  }
  if (coordinates.length) state.map.fitBounds(coordinates, { padding: [28, 28], maxZoom: 11 });
}

function drawStatistics() {
  const canvas = $("#stats-chart");
  if (!canvas) return;
  const context = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  if (!context || !rect.width) return;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = rect.width * ratio;
  canvas.height = 300 * ratio;
  context.scale(ratio, ratio);
  const reports = state.data.reports;
  const transports = state.data.transport_records;
  const items = [
    ["Pendientes", reports.filter((item) => item.status === "Pendiente").length, "#f0bd55"],
    ["En investigación", reports.filter((item) => item.status === "En investigación").length, "#6ab7e8"],
    ["Resueltas / revisadas", reports.filter((item) => ["Resuelto", "Revisado"].includes(item.status)).length, "#50c987"],
    ["Transportes", transports.length, "#a78bfa"],
    ["Zonas", state.data.zones.length, "#70c993"],
  ];
  context.clearRect(0, 0, rect.width, 300);
  const max = Math.max(1, ...items.map((item) => item[1]));
  const left = Math.min(150, rect.width * 0.38);
  const right = rect.width - 35;
  items.forEach(([label, count, color], index) => {
    const y = 28 + index * 52;
    context.fillStyle = "#c8d8cd";
    context.font = "11px system-ui";
    context.textAlign = "right";
    context.fillText(label, left - 12, y + 15);
    context.fillStyle = color;
    context.fillRect(left, y, (right - left) * count / max, 23);
    context.fillStyle = "#edf5ef";
    context.textAlign = "left";
    context.fillText(String(count), Math.min(left + (right - left) * count / max + 8, right), y + 16);
  });
  if (!reports.length && !transports.length && !state.data.zones.length) {
    context.fillStyle = "#9aada1";
    context.textAlign = "center";
    context.fillText("Aún no hay datos. Registra zonas, denuncias o transportes.", rect.width / 2, 270);
  }
  renderStatSummaries();
}

function renderStatSummaries() {
  const reports = state.data.reports;
  const summarize = (selector, values, empty) => {
    const entries = Object.entries(values);
    $(selector).innerHTML = entries.length
      ? entries.map(([name, count]) => `<div>${escapeHtml(name)} <span class="muted">· ${count}</span></div>`).join("")
      : `<span>${empty}</span>`;
  };
  const countBy = (key) => reports.reduce((counts, report) => {
    const value = report[key] || "Sin especificar";
    counts[value] = (counts[value] || 0) + 1;
    return counts;
  }, {});
  summarize("#stats-types", countBy("type"), "Sin denuncias por tipo todavía.");
  const locations = Object.entries(countBy("location")).sort((a, b) => b[1] - a[1]).slice(0, 8);
  $("#stats-locations").innerHTML = locations.length
    ? locations.map(([name, count]) => `<div>${escapeHtml(name)} <span class="muted">· ${count}</span></div>`).join("")
    : "<span>Sin incidencias por lugar todavía.</span>";
  summarize("#stats-months", countByMonth(reports), "Sin incidencias registradas por mes todavía.");
}

function countByMonth(reports) {
  return reports.reduce((counts, report) => {
    const month = String(report.created_at || "").slice(0, 7) || "Sin fecha";
    counts[month] = (counts[month] || 0) + 1;
    return counts;
  }, {});
}

function formValues(form) {
  return Object.fromEntries(new FormData(form));
}

function numericValue(value) {
  return value === "" || value == null ? null : Number(value);
}

async function saveReport(values, files = []) {
  const evidence = files.map((file) => ({ name: file.name, file }));
  await storeRequest("reports", "readwrite", "put", {
    ...values,
    id: makeId(),
    latitude: numericValue(values.latitude),
    longitude: numericValue(values.longitude),
    status: "Pendiente",
    assigned_to: "",
    notes: "",
    evidence,
    created_at: new Date().toISOString(),
  });
}

function csvCell(value) {
  let text = String(value ?? "");
  if (typeof value !== "number" && /^[\s]*[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

function exportCsv() {
  const rows = [["Registro", "Tipo", "Lugar u origen", "Destino", "Estado", "Fecha", "Detalle"]];
  state.data.reports.forEach((report) => rows.push([
    "Denuncia", report.type, report.location, "", report.status, report.created_at, report.description,
  ]));
  state.data.transport_records.forEach((record) => rows.push([
    "Transporte", record.guide, record.origin, record.destination, record.verification_status, record.created_at,
    `Placa: ${record.plate}; Madera: ${record.wood_type}; Volumen: ${record.volume ?? ""}`,
  ]));
  state.data.zones.forEach((zone) => rows.push([
    "Zona", zone.name, zone.latitude, zone.longitude, zone.status, "", "",
  ]));
  const csv = `\uFEFF${rows.map((row) => row.map(csvCell).join(",")).join("\r\n")}`;
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "forestguard-registros.csv";
  link.click();
  URL.revokeObjectURL(url);
  showToast("Se descargó el archivo CSV.");
}

document.addEventListener("click", async (event) => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
  const action = target.closest("[data-action]")?.dataset.action;
  if (action === "close-dialog") closeDialog();
  if (action === "new-report") showReportForm();
  if (action === "new-transport") showTransportForm();
  if (action === "new-zone") showZoneForm();
  if (action === "photo-review") showPhotoReview();
  if (action === "export-csv") exportCsv();
  const editReportId = target.closest("[data-edit-report]")?.dataset.editReport;
  if (editReportId) {
    const report = state.data.reports.find((item) => String(item.id) === editReportId);
    if (report) showReportDetails(report);
  }
  const editZoneName = target.closest("[data-edit-zone]")?.dataset.editZone;
  if (editZoneName) {
    const zone = state.data.zones.find((item) => item.name === editZoneName);
    if (zone) showZoneForm(zone);
  }
  const deleteZoneName = target.closest("[data-delete-zone]")?.dataset.deleteZone;
  if (deleteZoneName && confirm(`¿Eliminar la zona «${deleteZoneName}»?`)) {
    try {
      await storeRequest("zones", "readwrite", "delete", deleteZoneName);
      await refreshData();
      showToast("Zona eliminada.");
    } catch (error) {
      showToast(error.message);
    }
  }
});

document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  event.preventDefault();
  try {
    if (form.id === "report-form") {
      const selectedFiles = [...form.elements.evidence.files];
      if (selectedFiles.length > 5) throw new Error("Puedes adjuntar hasta cinco archivos por denuncia.");
      if (selectedFiles.some((file) => !file.type.startsWith("image/") && file.type !== "application/pdf")) {
        throw new Error("Adjunta únicamente imágenes o documentos PDF.");
      }
      if (selectedFiles.reduce((sum, file) => sum + file.size, 0) > 16 * 1024 * 1024) {
        throw new Error("El tamaño total de los archivos supera los 16 MB.");
      }
      const values = formValues(form);
      await saveReport(values, selectedFiles);
      closeDialog();
      await refreshData();
      showToast("Denuncia registrada como pendiente en este navegador.");
    } else if (form.id === "transport-form") {
      const values = formValues(form);
      await storeRequest("transport_records", "readwrite", "put", {
        ...values,
        id: makeId(),
        volume: numericValue(values.volume),
        created_at: new Date().toISOString(),
      });
      closeDialog();
      await refreshData();
      showToast("Transporte registrado en este navegador.");
    } else if (form.id === "zone-form") {
      const values = formValues(form);
      const existingName = form.dataset.existingName;
      const zone = { ...values, latitude: Number(values.latitude), longitude: Number(values.longitude) };
      if (existingName && existingName !== zone.name) {
        await storeRequest("zones", "readwrite", "delete", existingName);
      }
      await storeRequest("zones", "readwrite", "put", zone);
      closeDialog();
      await refreshData();
      showToast("Zona guardada en este navegador.");
    } else if (form.id === "followup-form") {
      const report = state.data.reports.find((item) => item.id === form.dataset.reportId);
      if (!report) throw new Error("No se encontró la denuncia seleccionada.");
      await storeRequest("reports", "readwrite", "put", { ...report, ...formValues(form) });
      closeDialog();
      await refreshData();
      showToast("Seguimiento actualizado.");
    } else if (form.id === "photo-form") {
      const file = form.elements.photo.files[0];
      if (!file) throw new Error("Selecciona una fotografía para analizar.");
      const analysis = await analyzePhoto(file);
      const description = `Resultado preliminar: ${analysis.finding}. ${analysis.observation} Imagen: ${file.name}; resolución: ${analysis.dimensions} px; tonos verdes: ${analysis.greenPercent.toFixed(1)}%; tonos tierra: ${analysis.soilPercent.toFixed(1)}%; brillo medio: ${analysis.brightness.toFixed(0)}/255. Resultado orientativo por color; no determina legalidad y requiere verificación humana.`;
      await saveReport({
        location: form.elements.location.value.trim() || "Por verificar",
        type: "Posible tala (revisión manual)",
        description,
        latitude: form.elements.latitude.value,
        longitude: form.elements.longitude.value,
      }, [file]);
      closeDialog();
      await refreshData();
      showToast("Análisis guardado como denuncia pendiente.");
    }
  } catch (error) {
    formError(error.message || "No se pudieron guardar los cambios.");
  }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "report-search" || event.target.id === "report-status-filter") renderReports();
});

document.addEventListener("change", (event) => {
  if (event.target.id !== "photo-input" || !event.target.files?.[0]) return;
  const file = event.target.files[0];
  if (!file.type.startsWith("image/")) {
    formError("Selecciona un archivo de imagen válido.");
    return;
  }
  if (state.photoPreviewUrl) URL.revokeObjectURL(state.photoPreviewUrl);
  state.photoPreviewUrl = URL.createObjectURL(file);
  const preview = $("#photo-preview");
  preview.src = state.photoPreviewUrl;
  preview.hidden = false;
  analyzePhoto(file).then((analysis) => {
    $("#photo-result").textContent = `RESULTADO PRELIMINAR\n${analysis.finding}\n\n${analysis.observation}\n\nResolución: ${analysis.dimensions} px\nTonos verdes: ${analysis.greenPercent.toFixed(1)}%\nTonos tierra: ${analysis.soilPercent.toFixed(1)}%\nBrillo medio: ${analysis.brightness.toFixed(0)} / 255`;
    $("#save-photo-report").disabled = false;
  }).catch((error) => formError(error.message));
});

window.addEventListener("hashchange", () => setView(location.hash.slice(1) || "inicio"));
window.addEventListener("resize", () => {
  if ($("#view-estadisticas").classList.contains("active")) drawStatistics();
});
window.addEventListener("DOMContentLoaded", async () => {
  setView(location.hash.slice(1) || "inicio");
  try {
    await refreshData();
  } catch (error) {
    showToast(`No se pudieron cargar los registros locales: ${error.message}`);
  }
});

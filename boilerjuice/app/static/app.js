/* ── BoilerJuice Tank Monitor - Frontend ──────────────────── */

// Determine base URL (handles HA ingress path rewriting)
const BASE = "";  // Relative — works with ingress proxy

// ── State ───────────────────────────────────────────────────
let currentSection = "dashboard";
let tankData = null;
let config = {};
let authActive = false;

// ── Initialization ──────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initNavigation();
  initTheme();
  initMqttToggle();
  loadConfig();
  loadStatus();
});

// ── Navigation ──────────────────────────────────────────────
function initNavigation() {
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.addEventListener("click", () => {
      switchSection(btn.dataset.section);
    });
  });
}

function switchSection(name) {
  currentSection = name;
  document.querySelectorAll(".nav-item").forEach(n =>
    n.classList.toggle("active", n.dataset.section === name)
  );
  document.querySelectorAll(".section").forEach(s =>
    s.classList.toggle("active", s.id === `section-${name}`)
  );
}

// ── Theme ───────────────────────────────────────────────────
function initTheme() {
  const saved = localStorage.getItem("bj_theme") || "dark";
  setTheme(saved);
  document.getElementById("themeToggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    setTheme(current === "dark" ? "light" : "dark");
  });
}

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("bj_theme", theme);
  document.getElementById("themeToggle").textContent = theme === "dark" ? "🌙" : "☀️";
}

// ── MQTT Toggle ─────────────────────────────────────────────
function initMqttToggle() {
  const cb = document.getElementById("mqttEnabled");
  const fields = document.getElementById("mqttFields");
  cb.addEventListener("change", () => {
    fields.style.display = cb.checked ? "block" : "none";
  });
}

// ── API Helpers ─────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE}${path}`, opts);
  return res.json();
}

// ── Toast Notifications ─────────────────────────────────────
function toast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.style.transition = "opacity 0.3s";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 300);
  }, 4000);
}

// ── Loading state for buttons ───────────────────────────────
function setLoading(btn, loading) {
  if (loading) {
    btn.classList.add("loading");
    btn.disabled = true;
  } else {
    btn.classList.remove("loading");
    btn.disabled = false;
  }
}

// ── Password toggle ─────────────────────────────────────────
function togglePassword(inputId, btn) {
  const input = document.getElementById(inputId);
  if (input.type === "password") {
    input.type = "text";
    btn.textContent = "🔒";
  } else {
    input.type = "password";
    btn.textContent = "👁️";
  }
}

// ═══════════════════════════════════════════════════════════
// CONFIG
// ═══════════════════════════════════════════════════════════

async function loadConfig() {
  try {
    const data = await api("GET", "/api/config");
    if (data && data.success !== false) {
      config = data;
      // Populate fields
      if (config.email) document.getElementById("bjEmail").value = config.email;
      if (config.tank_id) document.getElementById("bjTankId").value = config.tank_id;
      if (config.tank_capacity) document.getElementById("bjTankCapacity").value = config.tank_capacity;
      if (config.refresh_interval != null) {
        document.getElementById("refreshInterval").value = config.refresh_interval;
      }
      // Password is masked from server, don't overwrite
      if (config.has_password) {
        document.getElementById("bjPassword").placeholder = "••••••• (saved)";
      }
      // MQTT
      if (config.mqtt_enabled) {
        document.getElementById("mqttEnabled").checked = true;
        document.getElementById("mqttFields").style.display = "block";
      }
      if (config.mqtt_host) document.getElementById("mqttHost").value = config.mqtt_host;
      if (config.mqtt_port) document.getElementById("mqttPort").value = config.mqtt_port;
      if (config.mqtt_user) document.getElementById("mqttUser").value = config.mqtt_user;
    }
  } catch (e) {
    console.error("Failed to load config:", e);
  }
}

async function saveSettings() {
  const btn = document.getElementById("saveSettingsBtn");
  setLoading(btn, true);

  const payload = {
    email: document.getElementById("bjEmail").value.trim(),
    tank_id: document.getElementById("bjTankId").value.trim(),
    tank_capacity: parseInt(document.getElementById("bjTankCapacity").value) || 0,
    refresh_interval: parseInt(document.getElementById("refreshInterval").value),
    mqtt_enabled: document.getElementById("mqttEnabled").checked,
    mqtt_host: document.getElementById("mqttHost").value.trim(),
    mqtt_port: parseInt(document.getElementById("mqttPort").value) || 1883,
    mqtt_user: document.getElementById("mqttUser").value.trim(),
  };

  // Only include password if the user typed a new one
  const pw = document.getElementById("bjPassword").value;
  if (pw) payload.password = pw;

  const mqttPw = document.getElementById("mqttPassword").value;
  if (mqttPw) payload.mqtt_password = mqttPw;

  try {
    const data = await api("POST", "/api/config", payload);
    if (data.success) {
      toast("Settings saved successfully", "success");
      config = { ...config, ...payload };
      // Clear password fields after save
      document.getElementById("bjPassword").value = "";
      document.getElementById("bjPassword").placeholder = "••••••• (saved)";
      document.getElementById("mqttPassword").value = "";
    } else {
      toast(data.error || "Failed to save settings", "error");
    }
  } catch (e) {
    toast("Network error saving settings", "error");
  } finally {
    setLoading(btn, false);
  }
}

// ═══════════════════════════════════════════════════════════
// DASHBOARD / STATUS
// ═══════════════════════════════════════════════════════════

async function loadStatus() {
  try {
    const data = await api("GET", "/api/status");
    if (data && data.success && data.data) {
      updateDashboard(data.data);
    }
  } catch (e) {
    console.error("Failed to load status:", e);
  }
}

function updateDashboard(data) {
  tankData = data;
  const emptyState = document.getElementById("emptyState");
  const dataView = document.getElementById("tankDataView");

  if (!data || (data.litres === 0 && data.percent === 0)) {
    emptyState.style.display = "flex";
    dataView.style.display = "none";
    return;
  }

  emptyState.style.display = "none";
  dataView.style.display = "block";

  // Percentage
  const pct = Math.round(data.percent || 0);
  document.getElementById("tankPercentText").textContent = pct;

  // Tank fill
  const fill = document.getElementById("tankFill");
  fill.style.height = Math.min(pct, 100) + "%";
  fill.className = "tank-fill " + getLevelClass(pct);

  // Level badge
  const badge = document.getElementById("levelBadge");
  const levelName = data.level_name || getLevelName(pct);
  badge.textContent = levelName;
  badge.className = "level-name " + getLevelClass(pct);

  // Stats
  document.getElementById("statLitres").textContent = formatNum(data.litres);
  document.getElementById("statPercent").textContent = pct + "%";
  document.getElementById("statCapacity").textContent =
    data.capacity ? formatNum(data.capacity) : "--";

  // Timestamp
  if (data.timestamp) {
    const d = new Date(data.timestamp);
    document.getElementById("lastUpdated").textContent =
      "Last updated: " + d.toLocaleString();
  }

  // Connection badge
  updateConnectionBadge(true);
}

function getLevelClass(pct) {
  if (pct >= 60) return "high";
  if (pct >= 30) return "medium";
  return "low";
}

function getLevelName(pct) {
  if (pct >= 60) return "High";
  if (pct >= 30) return "Medium";
  return "Low";
}

function formatNum(n) {
  if (n == null || isNaN(n)) return "--";
  return Math.round(n).toLocaleString();
}

function updateConnectionBadge(connected) {
  const badge = document.getElementById("connectionBadge");
  const text = document.getElementById("connectionText");
  if (connected) {
    badge.className = "connection-badge connected";
    text.textContent = "Connected";
  } else {
    badge.className = "connection-badge disconnected";
    text.textContent = "Not Connected";
  }
}

async function refreshData() {
  const btn = document.getElementById("refreshBtn");
  setLoading(btn, true);
  try {
    const data = await api("POST", "/api/refresh");
    if (data.success && data.data) {
      updateDashboard(data.data);
      toast("Tank data refreshed", "success");
    } else if (data.needs_auth) {
      toast("Session expired — please re-login", "error");
      updateConnectionBadge(false);
      switchSection("login");
    } else {
      toast(data.error || "Refresh failed", "error");
    }
  } catch (e) {
    toast("Network error refreshing data", "error");
  } finally {
    setLoading(btn, false);
  }
}

// ═══════════════════════════════════════════════════════════
// AUTH / REMOTE BROWSER
// ═══════════════════════════════════════════════════════════

async function startAuth() {
  const btn = document.getElementById("startAuthBtn");
  setLoading(btn, true);
  authActive = true;

  const remoteBrowser = document.getElementById("remoteBrowser");
  const overlay = document.getElementById("browserOverlay");
  const hint = document.getElementById("browserHint");
  const autoFillBtn = document.getElementById("autoFillBtn");
  const fetchBtn = document.getElementById("fetchAfterAuthBtn");

  remoteBrowser.style.display = "block";
  overlay.classList.remove("hidden");
  hint.style.display = "block";

  setAuthStatus("info", "Opening BoilerJuice login page...");

  try {
    const data = await api("POST", "/api/auth/start");
    if (data.success && data.screenshot) {
      updateBrowserScreenshot(data.screenshot);
      overlay.classList.add("hidden");
      autoFillBtn.style.display = "inline-flex";

      const pageType = data.page_info?.page_type || "unknown";
      if (pageType === "captcha") {
        setAuthStatus("info", "CAPTCHA detected — click on the image to solve it");
      } else if (pageType === "login") {
        setAuthStatus("info", "Login form ready — click Auto-fill or type manually");
        autoFillBtn.style.display = "inline-flex";
      } else {
        setAuthStatus("info", "Page loaded — interact with the screenshot below");
      }
    } else {
      setAuthStatus("error", data.error || "Failed to start login");
    }
  } catch (e) {
    setAuthStatus("error", "Network error: " + e.message);
  } finally {
    setLoading(btn, false);
  }
}

function updateBrowserScreenshot(base64) {
  const img = document.getElementById("browserScreenshot");
  img.src = "data:image/png;base64," + base64;
}

async function handleBrowserClick(event) {
  if (!authActive) return;

  const img = event.target;
  const rect = img.getBoundingClientRect();

  // Calculate actual coordinates on the browser page
  const scaleX = img.naturalWidth / rect.width;
  const scaleY = img.naturalHeight / rect.height;
  const x = Math.round((event.clientX - rect.left) * scaleX);
  const y = Math.round((event.clientY - rect.top) * scaleY);

  setAuthStatus("info", `Clicking at (${x}, ${y})...`);

  try {
    const data = await api("POST", "/api/auth/click", { x, y });
    if (data.success && data.screenshot) {
      updateBrowserScreenshot(data.screenshot);
      handlePageTypeChange(data.page_info);
    } else {
      toast(data.error || "Click failed", "error");
    }
  } catch (e) {
    toast("Network error", "error");
  }
}

function handlePageTypeChange(pageInfo) {
  if (!pageInfo) return;
  const type = pageInfo.page_type;
  const autoFillBtn = document.getElementById("autoFillBtn");
  const fetchBtn = document.getElementById("fetchAfterAuthBtn");

  if (type === "captcha") {
    setAuthStatus("info", "CAPTCHA detected — click to interact with the puzzle");
    autoFillBtn.style.display = "none";
    fetchBtn.style.display = "none";
  } else if (type === "login") {
    setAuthStatus("success", "Login form visible — click Auto-fill Credentials");
    autoFillBtn.style.display = "inline-flex";
    fetchBtn.style.display = "none";
  } else if (type === "tank" || type === "unknown") {
    // Might be logged in
    if (pageInfo.url && !pageInfo.url.includes("login")) {
      setAuthStatus("success", "Logged in! Click Fetch Tank Data to get your readings.");
      autoFillBtn.style.display = "none";
      fetchBtn.style.display = "inline-flex";
      updateConnectionBadge(true);
    } else {
      setAuthStatus("info", "Page loaded — continue interacting");
    }
  }
}

async function autoFillLogin() {
  const email = document.getElementById("bjEmail").value.trim();
  const password = document.getElementById("bjPassword").value ||
                   (config.has_password ? "__saved__" : "");

  if (!email) {
    toast("Please enter your email in Settings first", "error");
    switchSection("settings");
    return;
  }

  setAuthStatus("info", "Filling login form...");

  try {
    const data = await api("POST", "/api/auth/fill-login", { email, password });
    if (data.success && data.screenshot) {
      updateBrowserScreenshot(data.screenshot);
      if (data.logged_in) {
        setAuthStatus("success", "Login successful! You can now fetch tank data.");
        document.getElementById("autoFillBtn").style.display = "none";
        document.getElementById("fetchAfterAuthBtn").style.display = "inline-flex";
        updateConnectionBadge(true);
      } else {
        handlePageTypeChange(data.page_info);
      }
    } else {
      setAuthStatus("error", data.error || "Auto-fill failed");
      if (data.screenshot) updateBrowserScreenshot(data.screenshot);
    }
  } catch (e) {
    toast("Network error", "error");
  }
}

async function fetchAfterAuth() {
  const btn = document.getElementById("fetchAfterAuthBtn");
  setLoading(btn, true);
  setAuthStatus("info", "Fetching tank data...");

  try {
    const data = await api("POST", "/api/refresh");
    if (data.success && data.data) {
      updateDashboard(data.data);
      setAuthStatus("success", "Tank data fetched successfully!");
      toast("Tank data loaded!", "success");
      // Switch to dashboard after a short delay
      setTimeout(() => switchSection("dashboard"), 1500);
    } else if (data.needs_auth) {
      setAuthStatus("error", "Session invalid — please try logging in again");
    } else {
      setAuthStatus("error", data.error || "Could not fetch tank data");
    }
  } catch (e) {
    toast("Network error", "error");
  } finally {
    setLoading(btn, false);
  }
}

function setAuthStatus(type, message) {
  const el = document.getElementById("authStatus");
  const text = document.getElementById("authStatusText");
  el.className = `auth-status ${type}`;
  text.textContent = message;

  // Set pulse animation on the dot if in progress
  const dot = el.querySelector(".status-dot");
  if (dot) {
    dot.classList.toggle("pulse", type === "info");
  }
}

// ── Auto-refresh ────────────────────────────────────────────
let refreshTimer = null;

function startAutoRefresh() {
  stopAutoRefresh();
  const interval = config.refresh_interval || 60;
  if (interval > 0) {
    refreshTimer = setInterval(() => {
      loadStatus();
    }, interval * 60 * 1000);
  }
}

function stopAutoRefresh() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

// Start auto-refresh after initial load
setTimeout(startAutoRefresh, 5000);

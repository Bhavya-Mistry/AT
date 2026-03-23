"use strict";

const App = (() => {
  // ═══════════════════════════════════════
  // CONFIG
  // ═══════════════════════════════════════
  const CONFIG = Object.freeze({
    API_BASE: (() => {
      const meta = document.querySelector('meta[name="api-base"]');
      if (meta) return meta.content;
      const h = location.hostname;
      return h === "localhost" || h === "127.0.0.1"
        ? "http://127.0.0.1:8000"
        : `${location.origin}/api`;
    })(),
    TOKEN_KEY: "mc_token",
    USER_KEY: "mc_user",
    MAX_FILE_SIZE: 25 * 1024 * 1024,
    TOAST_DURATION: 4000,
    POLL_INTERVAL: 6000,
    DEBOUNCE_MS: 300,
  });

  // ═══════════════════════════════════════
  // STATE
  // ═══════════════════════════════════════
  const state = {
    token: null,
    user: null, // { email, role }
    currentScreen: "dashboard",
    currentSessionId: null,
    sessions: [],
    files: [],
    patients: [],
    selectedPatientId: null,
    isOnline: navigator.onLine,
    isSending: false,
    modalFile: null,
    confirmResolver: null,
    pollTimer: null,
    abortControllers: new Map(),
    patientSummariesCache: {},
  };

  // ═══════════════════════════════════════
  // HELPERS
  // ═══════════════════════════════════════
  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

  const _escDiv = document.createElement("div");
  function esc(str) {
    if (!str) return "";
    _escDiv.textContent = str;
    return _escDiv.innerHTML;
  }

  function genId(prefix = "sess") {
    const seg = () => Math.random().toString(36).substring(2, 7);
    return `${prefix}_${seg()}${seg()}`;
  }

  function formatDate(d) {
    if (!d) return "";
    try {
      return new Date(d).toLocaleDateString("en-IN", {
        day: "numeric", month: "short", year: "numeric",
      });
    } catch { return ""; }
  }

  function formatTime(d) {
    try {
      return (d ? new Date(d) : new Date()).toLocaleTimeString("en-IN", {
        hour: "2-digit", minute: "2-digit",
      });
    } catch { return ""; }
  }

  function priorityClass(score) {
    if (!score && score !== 0) return "";
    const n = Number(score);
    if (n >= 7) return "high";
    if (n >= 4) return "medium";
    return "low";
  }

  function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  function validateEmail(e) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e);
  }

  function validateFileSize(file) {
    return file && file.size <= CONFIG.MAX_FILE_SIZE;
  }

  function autoResize(el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  }

  function isDoctor() {
    return state.user?.role === "doctor";
  }

  function parseApiError(data) {
    if (!data) return "Unknown error";
    if (typeof data === "string") return data;
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((err) => {
          if (typeof err === "string") return err;
          const field = err.loc ? err.loc.slice(-1)[0] : "";
          return field ? `${field}: ${err.msg}` : err.msg || JSON.stringify(err);
        })
        .join("; ");
    }
    if (typeof data.detail === "object") return JSON.stringify(data.detail);
    if (typeof data.message === "string") return data.message;
    if (typeof data.error === "string") return data.error;
    return JSON.stringify(data);
  }

  function decodeJWT(token) {
    try {
      const base64Url = token.split(".")[1];
      const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
      const json = decodeURIComponent(
        atob(base64).split("").map((c) =>
          "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2)
        ).join("")
      );
      return JSON.parse(json);
    } catch {
      return null;
    }
  }

  // ═══════════════════════════════════════
  // API
  // ═══════════════════════════════════════
  function abortPrevious(key) {
    if (state.abortControllers.has(key)) state.abortControllers.get(key).abort();
    const c = new AbortController();
    state.abortControllers.set(key, c);
    return c.signal;
  }

  async function api(path, opts = {}) {
    const headers = { ...(opts.headers || {}) };
    if (!(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
    if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
    const signal = opts.signal || (opts._abortKey ? abortPrevious(opts._abortKey) : undefined);
    try {
      const res = await fetch(CONFIG.API_BASE + path, { ...opts, headers, signal });
      if (res.status === 401) { handleLogout(true); throw new Error("Session expired"); }
      return res;
    } catch (err) {
      if (err.name === "AbortError") throw err;
      console.error(`[API] ${opts.method || "GET"} ${path}:`, err.message);
      throw err;
    }
  }

  async function apiJSON(path, opts = {}) {
    const res = await api(path, opts);
    const data = await res.json();
    if (!res.ok) throw new Error(parseApiError(data));
    return data;
  }

  async function apiForm(path, formData, opts = {}) {
    return api(path, { method: "POST", body: formData, ...opts });
  }

  // ═══════════════════════════════════════
  // TOAST
  // ═══════════════════════════════════════
  function toast(msg, type = "info") {
    const c = $("#toast-container");
    const el = document.createElement("div");
    el.className = `toast ${esc(type)}`;
    el.setAttribute("role", "status");
    el.innerHTML = `<div class="toast-dot"></div><span>${esc(msg)}</span><button class="toast-close" aria-label="Dismiss">&times;</button>`;
    c.appendChild(el);
    const dismiss = () => { el.classList.add("removing"); setTimeout(() => el.remove(), 260); };
    el.querySelector(".toast-close").addEventListener("click", dismiss);
    setTimeout(dismiss, CONFIG.TOAST_DURATION);
  }

  // ═══════════════════════════════════════
  // CONFIRM
  // ═══════════════════════════════════════
  function confirm(title, body) {
    return new Promise((resolve) => {
      state.confirmResolver = resolve;
      $("#confirmTitle").textContent = title;
      $("#confirmBody").textContent = body;
      $("#confirmModal").classList.add("open");
      $("#confirmOkBtn").focus();
    });
  }

  function closeConfirm(result) {
    $("#confirmModal").classList.remove("open");
    if (state.confirmResolver) { state.confirmResolver(result); state.confirmResolver = null; }
  }

  // ═══════════════════════════════════════
  // CONNECTION
  // ═══════════════════════════════════════
  function updateConnectionStatus() {
    const banner = $("#connBanner");
    state.isOnline = navigator.onLine;
    banner.className = "conn-banner";
    if (!state.isOnline) {
      banner.classList.add("offline");
      banner.textContent = "⚠ You are offline. Some features may not work.";
    }
  }

  // ═══════════════════════════════════════
  // AUTH
  // ═══════════════════════════════════════
  function toggleAuthMode(mode) {
    $("#loginForm").style.display = mode === "login" ? "block" : "none";
    $("#registerForm").style.display = mode === "register" ? "block" : "none";
    $("#loginError").textContent = "";
    $("#registerError").textContent = "";
    setTimeout(() => $(mode === "login" ? "#loginEmail" : "#regEmail")?.focus(), 100);
  }

  function showAuthError(id, msg) {
    const el = $(`#${id}`);
    el.textContent = msg;
    el.setAttribute("aria-live", "assertive");
    setTimeout(() => { el.textContent = ""; el.removeAttribute("aria-live"); }, 5000);
  }

  function setButtonLoading(btn, loading) {
    if (loading) {
      btn._origHTML = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> Please wait…';
    } else {
      btn.disabled = false;
      btn.innerHTML = btn._origHTML || "Submit";
    }
  }

  async function handleLogin(e) {
    e.preventDefault();
    const email = $("#loginEmail").value.trim();
    const pass = $("#loginPassword").value;
    let valid = true;

    if (!validateEmail(email)) {
      $("#loginEmail").setAttribute("aria-invalid", "true");
      $("#loginEmailHint").classList.add("visible");
      valid = false;
    } else {
      $("#loginEmail").removeAttribute("aria-invalid");
      $("#loginEmailHint").classList.remove("visible");
    }
    if (!pass || pass.length < 6) {
      $("#loginPassword").setAttribute("aria-invalid", "true");
      $("#loginPasswordHint").classList.add("visible");
      valid = false;
    } else {
      $("#loginPassword").removeAttribute("aria-invalid");
      $("#loginPasswordHint").classList.remove("visible");
    }
    if (!valid) return;

    const btn = $("#loginBtn");
    setButtonLoading(btn, true);

    try {
      const form = new URLSearchParams();
      form.append("username", email);
      form.append("password", pass);

      const res = await fetch(CONFIG.API_BASE + "/login", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form,
      });
      const data = await res.json();
      if (!res.ok) { showAuthError("loginError", data.detail || "Invalid credentials"); return; }

      state.token = data.access_token;

      // Detect role from JWT payload
      const payload = decodeJWT(state.token);
      const role = payload?.role || "patient";

      state.user = { email, role };
      localStorage.setItem(CONFIG.TOKEN_KEY, state.token);
      localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(state.user));

      // If JWT didn't have role, try detecting via doctor endpoint
      if (!payload?.role) {
        await detectRole();
      }

      enterApp();
    } catch {
      showAuthError("loginError", `Cannot connect to ${CONFIG.API_BASE}. Is the backend running?`);
    } finally {
      setButtonLoading(btn, false);
    }
  }

  async function detectRole() {
    try {
      const res = await api("/doctor/patients/");
      if (res.ok) {
        state.user.role = "doctor";
        localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(state.user));
      }
    } catch {
      state.user.role = "patient";
    }
  }

  async function handleRegister(e) {
    e.preventDefault();
    const email = $("#regEmail").value.trim();
    const pass = $("#regPassword").value;
    const policy = $("#regPolicy").checked;
    const baa = $("#regBaa").checked;
    let valid = true;

    if (!validateEmail(email)) {
      $("#regEmail").setAttribute("aria-invalid", "true");
      $("#regEmailHint").classList.add("visible");
      valid = false;
    } else {
      $("#regEmail").removeAttribute("aria-invalid");
      $("#regEmailHint").classList.remove("visible");
    }
    if (!pass || pass.length < 6) {
      $("#regPassword").setAttribute("aria-invalid", "true");
      $("#regPasswordHint").classList.add("visible");
      valid = false;
    } else {
      $("#regPassword").removeAttribute("aria-invalid");
      $("#regPasswordHint").classList.remove("visible");
    }
    if (!policy) { showAuthError("registerError", "Please accept the Terms of Service"); valid = false; }
    if (!valid) return;

    const btn = $("#registerBtn");
    setButtonLoading(btn, true);

    try {
      await apiJSON("/users/", {
        method: "POST",
        body: JSON.stringify({ email, password: pass, is_policy_accepted: policy, has_signed_baa: baa }),
      });
      toast("Account created! Please sign in.", "success");
      toggleAuthMode("login");
      $("#loginEmail").value = email;
    } catch (err) {
      showAuthError("registerError", err.message || "Registration failed");
    } finally {
      setButtonLoading(btn, false);
    }
  }

  function enterApp() {
    $("#authWrap").style.display = "none";
    $("#mainApp").style.display = "flex";
    applyRole();
    showScreen("dashboard");
    loadDashboard();
    loadProfile();
  }

  function handleLogout(expired = false) {
    state.token = null;
    state.user = null;
    state.currentSessionId = null;
    state.sessions = [];
    state.files = [];
    state.patients = [];
    state.selectedPatientId = null;
    state.patientSummariesCache = {};

    // Clear storage
    localStorage.removeItem(CONFIG.TOKEN_KEY);
    localStorage.removeItem(CONFIG.USER_KEY);

    // Stop background tasks
    stopPolling();
    state.abortControllers.forEach((c) => c.abort());
    state.abortControllers.clear();

    // Clear all form fields to prevent data leaking to next user
    clearProfileForm();
    $$(".auth-card input").forEach((i) => { if (i.type !== "checkbox") i.value = ""; });
    $$(".auth-card input[type=checkbox]").forEach((i) => (i.checked = false));

    // Reset UI
    $("#authWrap").style.display = "flex";
    $("#mainApp").style.display = "none";
    closeSidebar();

    toast(expired ? "Session expired. Please sign in again." : "Signed out", expired ? "error" : "info");
    toggleAuthMode("login");
  }

  // ═══════════════════════════════════════
  // ROLE-BASED UI
  // ═══════════════════════════════════════
  function applyRole() {
    const email = state.user?.email || "";
    const role = state.user?.role || "patient";
    const initial = email[0]?.toUpperCase() || "U";
    const doc = role === "doctor";
    const roleLabel = doc ? "Doctor" : "Patient";

    // Sidebar - reset to email initial (loadProfile will update if profile exists)
    $("#sidebarEmail").textContent = email;
    $("#sidebarAvatar").textContent = initial;
    $("#sidebarAvatar").classList.toggle("doctor-avatar", doc);
    $("#sidebarRole").textContent = `${roleLabel} · Sign out`;

    // Profile - reset to email initial
    // ✅ Fix: HTML uses #profileAvatarText and #profileAvatarContainer, not #profileAvatar
    $("#profileEmail").textContent = email;
    const profAvatarText = $("#profileAvatarText");
    if (profAvatarText) {
      profAvatarText.textContent = initial;
      profAvatarText.classList.toggle("doctor-avatar", doc);
    }
    $("#profileBadge").textContent = roleLabel;
    $("#profileBadge").classList.toggle("doctor-badge", doc);
    $("#profileName").textContent = "\u2014"; // Will be updated by loadProfile

    // Show/hide role-specific elements
    $$(".role-patient").forEach((el) => {
      el.style.display = doc ? "none" : "";
    });
    $$(".role-doctor").forEach((el) => {
      el.style.display = doc ? "" : "none";
    });

    // Dashboard cards
    if (doc) {
      $("#recentChatsTitle").textContent = "High Priority Patients";
      $("#recentFilesTitle").textContent = "Recent Activity";
      $("#viewAllChatsBtn").setAttribute("data-action", "go-patients");
      $("#viewAllChatsBtn").textContent = "View all patients";
      $("#viewAllFilesBtn").style.display = "none";
    } else {
      $("#recentChatsTitle").textContent = "Recent Consultations";
      $("#recentFilesTitle").textContent = "Recent Files";
      $("#viewAllChatsBtn").setAttribute("data-action", "go-chat");
      $("#viewAllChatsBtn").textContent = "View all";
      $("#viewAllFilesBtn").style.display = "";
    }

    console.log(`[App] Role applied: ${roleLabel}`);
  }

  // ═══════════════════════════════════════
  // NAVIGATION
  // ═══════════════════════════════════════
  const SCREEN_META = {
    dashboard: ["Overview", "Your portal at a glance"],
    chat: ["AI Consultation", "Talk to your medical assistant"],
    files: ["Medical Files", "Your uploaded records and documents"],
    appointments: ["Appointments", "Your upcoming check-ups and visits"], // ✅ Fix: was missing — nav click did nothing
    profile: ["Profile", "Manage your account and health info"],
    patients: ["All Patients", "Monitor and manage patient cases"],
    "patient-detail": ["Patient Detail", "Review patient history and prescribe"],
  };

  function showScreen(name) {
    if (!SCREEN_META[name]) return;
    state.currentScreen = name;

    $$(".screen").forEach((s) => { s.classList.remove("active"); s.style.display = "none"; });
    const screen = $(`#screen-${name}`);
    screen.style.display = name === "chat" ? "flex" : "block";
    requestAnimationFrame(() => screen.classList.add("active"));

    $$(".nav-item[data-screen]").forEach((n) => {
      n.setAttribute("aria-current", n.dataset.screen === name ? "page" : "false");
    });

    const [title, sub] = SCREEN_META[name];
    $("#topbarTitle").innerHTML = `${esc(title)}<span>${esc(sub)}</span>`;

    if (name === "files") loadFiles();
    if (name === "chat") { loadSessions(); startPolling(); } else { stopPolling(); }
    if (name === "dashboard") loadDashboard();
    if (name === "patients") loadPatients();
    if (name === "profile") loadProfile();
    if (name === "appointments") loadAppointments(); // ✅ Fix: appointments screen never loaded data

    closeSidebar();
  }

  function openSidebar() {
    $("#sidebar").classList.add("open");
    $("#sidebarOverlay").classList.add("open");
    document.body.style.overflow = "hidden";
  }

  function closeSidebar() {
    $("#sidebar").classList.remove("open");
    $("#sidebarOverlay").classList.remove("open");
    document.body.style.overflow = "";
  }

  // ═══════════════════════════════════════
  // DASHBOARD
  // ═══════════════════════════════════════
  async function loadDashboard() {
    if (isDoctor()) {
      await loadDoctorDashboard();
    } else {
      await loadPatientDashboard();
    }
  }

  async function loadPatientDashboard() {
    try {
      const [sessRes, filesRes] = await Promise.allSettled([
        api("/users/me/chats/", { _abortKey: "dash-chats" }),
        api("/users/me/media/", { _abortKey: "dash-media" }),
      ]);
      if (sessRes.status === "fulfilled" && sessRes.value.ok) state.sessions = await sessRes.value.json();
      if (filesRes.status === "fulfilled" && filesRes.value.ok) state.files = await filesRes.value.json();

      // Session count
      $("#statPatientSessions").textContent = state.sessions.length;

      // File count
      $("#statPatientFiles").textContent = state.files.length;

      // Count prescriptions (files that start with "Rx:")
      const rxCount = state.files.filter((f) =>
        f.file_name?.startsWith("Rx:") || f.file_type === "pdf"
      ).length;
      $("#statPatientRx").textContent = rxCount || "\u2014";

      // Latest priority score (from most recent session with a score)
      const withScore = state.sessions.filter((s) => s.summary?.priority_score);
      if (withScore.length) {
        // Sort by date, get most recent
        const sorted = withScore.sort((a, b) =>
          new Date(b.created_at || 0) - new Date(a.created_at || 0)
        );
        const latest = sorted[0].summary.priority_score;
        $("#statPatientPriority").textContent = latest;
      } else {
        $("#statPatientPriority").textContent = "\u2014";
      }

      renderRecentChats(state.sessions.slice(0, 4));
      renderRecentFiles(state.files.slice(0, 4));
    } catch (err) {
      if (err.name !== "AbortError") console.error(err);
    }
  }

  async function loadDoctorDashboard() {
    try {
      const res = await api("/doctor/patients/", { _abortKey: "doc-dash" });
      if (!res.ok) return;
      state.patients = await res.json();

      // Patient count
      $("#statDocPatients").textContent = state.patients.length;

      // Show patients badge in sidebar
      const badge = $("#patientsBadge");
      if (state.patients.length) {
        badge.textContent = state.patients.length;
        badge.style.display = "";
      }

      // Fetch summaries for all patients in parallel
      const summaryPromises = state.patients.map((p) =>
        apiJSON(`/doctor/patients/${p.id}/summaries`).catch(() => [])
      );
      const allSummaries = await Promise.all(summaryPromises);

      // Cache for later use
      state.patients.forEach((p, i) => {
        state.patientSummariesCache[p.id] = allSummaries[i];
      });

      // Aggregate stats
      let totalSessions = 0;
      let totalPriority = 0;
      let priorityCount = 0;
      let pendingCount = 0;
      let highPriorityPatients = [];

      allSummaries.forEach((sessions, idx) => {
        const patient = state.patients[idx];
        totalSessions += sessions.length;

        let patientMaxPriority = 0;

        sessions.forEach((s) => {
          if (s.summary) {
            const score = s.summary.priority_score;
            if (score) {
              totalPriority += score;
              priorityCount++;
              if (score > patientMaxPriority) patientMaxPriority = score;
            }
            if (!s.summary.reviewed) {
              pendingCount++;
            }
          }
        });

        if (patientMaxPriority > 0) {
          highPriorityPatients.push({
            ...patient,
            maxPriority: patientMaxPriority,
            sessionCount: sessions.length,
          });
        }
      });

      // Update doctor stat cards
      $("#statDocSessions").textContent = totalSessions || "\u2014";
      $("#statDocPending").textContent = pendingCount || "\u2014";
      $("#statDocPriority").textContent = priorityCount
        ? (totalPriority / priorityCount).toFixed(1)
        : "\u2014";

      // Render patients sorted by priority
      highPriorityPatients.sort((a, b) => b.maxPriority - a.maxPriority);
      renderDoctorRecentPatients(
        highPriorityPatients.length
          ? highPriorityPatients.slice(0, 5)
          : state.patients.slice(0, 5)
      );
      renderDoctorRecentActivity(allSummaries);

    } catch (err) {
      if (err.name !== "AbortError") console.error("Doctor dashboard error:", err);
    }
  }

  function renderDoctorRecentPatients(patients) {
    const el = $("#recentChats");
    if (!patients.length) {
      el.innerHTML = '<div class="empty-state" style="padding:30px 20px"><div class="empty-state-icon" aria-hidden="true">👥</div><div class="empty-state-title">No patients yet</div><div class="empty-state-sub">Patients will appear once they register</div></div>';
      return;
    }
    el.innerHTML = patients.map((p) => {
      const name = p.profile?.full_name || p.email || "Unknown";
      const initial = name[0]?.toUpperCase() || "?";
      const score = p.maxPriority;
      const pc = priorityClass(score);
      const sessions = p.sessionCount || 0;
      return `<div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);cursor:pointer" data-action="view-patient" data-patient-id="${p.id}" tabindex="0" role="button">
        <div class="patient-card-avatar" style="width:32px;height:32px;font-size:13px">${esc(initial)}</div>
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;color:var(--text)">${esc(name)}</div>
          <div style="font-size:11px;color:var(--text-dim);font-family:var(--mono)">${esc(p.email)}${sessions ? ` · ${sessions} sessions` : ""}</div>
        </div>
        ${score ? `<span class="priority ${pc}">${esc(String(score))}/10</span>` : ""}
      </div>`;
    }).join("");
  }

  function renderDoctorRecentActivity(allSummaries) {
    const el = $("#recentFiles");

    // Flatten all sessions with patient info, sort by date
    const allSessions = [];
    allSummaries.forEach((sessions, idx) => {
      const patient = state.patients[idx];
      sessions.forEach((s) => {
        allSessions.push({
          ...s,
          patientName: patient?.profile?.full_name || patient?.email || "Unknown",
          patientId: patient?.id,
        });
      });
    });

    // Sort by created_at descending
    allSessions.sort((a, b) => {
      const da = new Date(a.created_at || 0);
      const db = new Date(b.created_at || 0);
      return db - da;
    });

    const recent = allSessions.slice(0, 5);

    if (!recent.length) {
      el.innerHTML = '<div class="empty-state" style="padding:30px 20px"><div class="empty-state-icon" aria-hidden="true">📊</div><div class="empty-state-title">No activity yet</div><div class="empty-state-sub">Patient consultations will appear here</div></div>';
      return;
    }

    el.innerHTML = recent.map((s) => {
      const score = s.summary?.priority_score;
      const pc = priorityClass(score);
      const msgCount = s.messages?.length || 0;
      const lastMsg = s.messages?.slice().reverse().find((m) => m.sender !== "system");
      const preview = esc((lastMsg?.text || "No messages").substring(0, 40));

      return `<div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);cursor:pointer" data-action="view-patient" data-patient-id="${s.patientId}" tabindex="0" role="button">
        <div style="flex:1;min-width:0">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">
            <span style="font-size:12px;color:var(--text);font-weight:500">${esc(s.patientName)}</span>
            <span style="font-size:10px;color:var(--text-faint);font-family:var(--mono)">${esc(s.session_id)}</span>
          </div>
          <div style="font-size:11px;color:var(--text-dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${preview}… · ${msgCount} msgs · ${formatDate(s.created_at)}</div>
        </div>
        ${score ? `<span class="priority ${pc}">${esc(String(score))}/10</span>` : ""}
      </div>`;
    }).join("");
  }

  function renderRecentChats(chats) {
    const el = $("#recentChats");
    if (!chats.length) {
      el.innerHTML = '<div class="empty-state" style="padding:30px 20px"><div class="empty-state-icon" aria-hidden="true">💬</div><div class="empty-state-title">No consultations yet</div><div class="empty-state-sub">Start a conversation with the AI assistant</div></div>';
      return;
    }
    el.innerHTML = chats.map((s) => {
      const firstPatientMsg = s.messages?.find((m) => m.sender === "patient");
      const displayName = getSessionDisplayName(firstPatientMsg?.text);
      const last = s.messages?.slice().reverse().find((m) => m.sender !== "system");
      const score = s.summary?.priority_score;
      const pc = priorityClass(score);
      const preview = esc((last?.text || "No messages yet").substring(0, 50));
      return `<div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);cursor:pointer" data-action="open-session" data-session-id="${esc(s.session_id)}" tabindex="0" role="button">
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;color:var(--text);font-weight:500;margin-bottom:2px">${esc(displayName)}</div>
          <div style="font-size:11px;color:var(--text-dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${preview}…</div>
        </div>
        ${score ? `<span class="priority ${pc}">${esc(String(score))}/10</span>` : ""}
      </div>`;
    }).join("");
  }

  function renderRecentFiles(files) {
    const el = $("#recentFiles");
    if (!files.length) {
      el.innerHTML = '<div class="empty-state" style="padding:30px 20px"><div class="empty-state-icon" aria-hidden="true">📄</div><div class="empty-state-title">No files uploaded</div><div class="empty-state-sub">Upload medical records, prescriptions</div></div>';
      return;
    }
    el.innerHTML = files.map((f) => {
      const icon = f.file_type === "audio" ? "🎵" : f.file_type?.includes("pdf") ? "📄" : "🖼";
      return `<div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border)">
        <span style="font-size:20px" aria-hidden="true">${icon}</span>
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(f.file_name)}</div>
          <div style="font-size:11px;color:var(--text-dim);font-family:var(--mono)">${formatDate(f.created_at)}</div>
        </div>
      </div>`;
    }).join("");
  }

  // ═══════════════════════════════════════
  // DOCTOR: PATIENTS LIST
  // ═══════════════════════════════════════
  async function loadPatients() {
    try {
      const res = await api("/doctor/patients/", { _abortKey: "load-patients" });
      if (res.ok) state.patients = await res.json();
      renderPatientsList();
    } catch (err) {
      if (err.name !== "AbortError") {
        console.error(err);
        toast("Failed to load patients", "error");
      }
    }
  }

  function renderPatientsList() {
    const el = $("#patientsList");
    if (!state.patients.length) {
      el.innerHTML = '<div class="empty-state" style="padding:60px 20px"><div class="empty-state-icon" aria-hidden="true">👥</div><div class="empty-state-title">No patients found</div><div class="empty-state-sub">Patients will appear here once they register</div></div>';
      return;
    }
    el.innerHTML = state.patients.map((p) => {
      const name = p.profile?.full_name || p.email?.split("@")[0] || "Unknown";
      const initial = name[0]?.toUpperCase() || "?";
      const status = p.profile?.current_status || "unknown";
      const blood = p.profile?.blood_group || "—";

      return `<div class="patient-card" data-action="view-patient" data-patient-id="${p.id}" tabindex="0" role="listitem">
        <div class="patient-card-avatar">${esc(initial)}</div>
        <div class="patient-card-info">
          <div class="patient-card-name">${esc(name)}</div>
          <div class="patient-card-email">${esc(p.email)}</div>
        </div>
        <div class="patient-card-meta">
          <div class="patient-card-stat">
            <div class="patient-card-stat-value">${esc(blood)}</div>
            <div class="patient-card-stat-label">Blood</div>
          </div>
          <div class="patient-card-stat">
            <div class="patient-card-stat-value" style="font-size:13px">
              <span class="priority ${status === 'critical' ? 'high' : status === 'monitoring' ? 'medium' : 'low'}">${esc(status)}</span>
            </div>
            <div class="patient-card-stat-label">Status</div>
          </div>
        </div>
      </div>`;
    }).join("");
  }

  // ═══════════════════════════════════════
  // DOCTOR: PATIENT DETAIL
  // ═══════════════════════════════════════

  async function viewPatient(patientId) {
    state.selectedPatientId = patientId;
    showScreen("patient-detail");

    const patient = state.patients.find((p) => p.id === patientId);
    const name = patient?.profile?.full_name || patient?.email || "Unknown";
    const initial = name[0]?.toUpperCase() || "?";

    // Render header
    $("#patientDetailHeader").innerHTML = `
      <div class="patient-detail-header">
        <div class="profile-avatar" style="width:56px;height:56px;font-size:22px">${esc(initial)}</div>
        <div class="profile-info">
          <div class="profile-name">${esc(name)}</div>
          <div class="profile-email">${esc(patient?.email || "")}</div>
          <div style="display:flex;gap:8px;margin-top:6px">
            ${patient?.profile?.blood_group ? `<span class="priority low">${esc(patient.profile.blood_group)}</span>` : ""}
            ${patient?.profile?.current_status ? `<span class="priority ${patient.profile.current_status === 'critical' ? 'high' : patient.profile.current_status === 'monitoring' ? 'medium' : 'low'}">${esc(patient.profile.current_status)}</span>` : ""}
          </div>
        </div>
      </div>`;

    // Load summaries
    await loadPatientSummaries(patientId);
    await loadPatientFiles(patientId);

    // Show summaries tab by default
    activateDetailTab("summaries");
  }

  async function loadPatientSummaries(patientId) {
    const el = $("#patientDetailSummaries");
    el.innerHTML = '<div style="text-align:center;padding:20px"><span class="spinner"></span></div>';

    try {
      const data = await apiJSON(`/doctor/patients/${patientId}/summaries`);

      // Cache for chat viewer
      state.patientSummariesCache[patientId] = data;

      if (!data.length) {
        el.innerHTML = '<div class="empty-state" style="padding:40px 20px"><div class="empty-state-icon" aria-hidden="true">📋</div><div class="empty-state-title">No chat sessions</div><div class="empty-state-sub">This patient hasn\'t started any AI consultations yet</div></div>';
        return;
      }

      el.innerHTML = data.map((s) => {
        const score = s.summary?.priority_score;
        const pc = priorityClass(score);
        const summaryFields = s.summary ? Object.entries(s.summary) : [];
        const msgCount = s.messages?.length || 0;

        return `<div class="summary-list-card">
        <div class="summary-list-header">
          <span class="summary-list-session">${esc(s.session_id)}</span>
          <div style="display:flex;align-items:center;gap:8px">
            <span class="cv-msg-count">${msgCount} msgs</span>
            ${score ? `<span class="priority ${pc}">${esc(String(score))}/10</span>` : '<span class="priority low">No score</span>'}
          </div>
        </div>
        <div class="summary-list-body">
          ${summaryFields.slice(0, 6).map(([k, v]) => `
            <div class="summary-list-field">
              <span class="summary-list-key">${esc(k.replace(/_/g, " "))}</span>
              <span class="summary-list-val">${esc(String(v).substring(0, 80))}</span>
            </div>`).join("")}
        </div>
        <div style="font-size:11px;color:var(--text-faint);margin-top:8px;font-family:var(--mono)">
          ${msgCount} messages · ${formatDate(s.created_at)}
        </div>
        <div class="summary-list-actions">
          <button class="btn btn-purple" data-action="prescribe" data-session-id="${esc(s.session_id)}" data-patient-id="${patientId}" type="button">
            <svg viewBox="0 0 24 24" style="width:14px;height:14px;stroke:currentColor;fill:none"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>
            Prescribe
          </button>
          <button class="btn btn-ghost" data-action="view-chat-readonly" data-session-id="${esc(s.session_id)}" data-patient-id="${patientId}" type="button">
            <svg viewBox="0 0 24 24" style="width:14px;height:14px;stroke:currentColor;fill:none"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
            View Chat
          </button>
        </div>
      </div>`;
      }).join("");
    } catch (err) {
      el.innerHTML = `<div class="empty-state" style="padding:40px 20px"><div class="empty-state-title">Error loading summaries</div><div class="empty-state-sub">${esc(err.message)}</div></div>`;
    }
  }
  async function loadPatientFiles(patientId) {
    const el = $("#patientDetailFiles");
    el.innerHTML = '<div style="text-align:center;padding:20px"><span class="spinner"></span></div>';

    try {
      const data = await apiJSON(`/doctor/patients/${patientId}/files`);

      if (!data.length) {
        el.innerHTML = '<div class="empty-state" style="padding:40px 20px"><div class="empty-state-icon" aria-hidden="true">📂</div><div class="empty-state-title">No files</div><div class="empty-state-sub">This patient hasn\'t uploaded any files yet</div></div>';
        return;
      }

      el.innerHTML = `<div class="files-grid">${data.map((f) => {
        const info = getFileTypeInfo(f);
        const hasTranscript = f.transcript && f.transcript !== "User Uploaded Record";
        return `<div class="file-card" data-action="view-file-direct" data-view-link="${esc(f.drive_view_link || "")}" tabindex="0">
          <div class="file-icon ${info.cls}" aria-hidden="true">${info.svg}</div>
          <div class="file-name">${esc(f.file_name)}</div>
          <div class="file-meta">${formatDate(f.created_at)} · ${esc(f.file_type || "file")}</div>
          ${hasTranscript ? `<div class="file-transcript">${esc(f.transcript)}</div>` : ""}
        </div>`;
      }).join("")}</div>`;
    } catch (err) {
      el.innerHTML = `<div class="empty-state"><div class="empty-state-title">Error</div><div class="empty-state-sub">${esc(err.message)}</div></div>`;
    }
  }

  function activateDetailTab(tabName) {
    $$(".detail-tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === tabName));
    $("#patientDetailSummaries").style.display = tabName === "summaries" ? "" : "none";
    $("#patientDetailFiles").style.display = tabName === "patient-files" ? "" : "none";
  }

  // ═══════════════════════════════════════
  // DOCTOR: PRESCRIPTION
  // ═══════════════════════════════════════
  function openPrescribeModal(sessionId, patientId) {
    const patient = state.patients.find((p) => p.id === Number(patientId));
    const name = patient?.profile?.full_name || patient?.email || "Patient";
    $("#prescribeModalSub").textContent = `Prescribing for ${name} — Session: ${sessionId}`;
    $("#rxSessionId").value = sessionId;
    $("#rxDoctorNotes").value = "";
    $("#rxFollowUp").value = "7";
    $("#prescribeModal").classList.add("open");
    setTimeout(() => $("#rxDoctorNotes").focus(), 150);
  }

  function closePrescribeModal() {
    $("#prescribeModal").classList.remove("open");
  }

  async function submitPrescription(e) {
    e.preventDefault();
    const sessionId = $("#rxSessionId").value;
    const notes = $("#rxDoctorNotes").value.trim();
    const followUp = parseInt($("#rxFollowUp").value, 10);

    if (!notes) { toast("Doctor notes are required", "error"); return; }
    if (!followUp || followUp < 1) { toast("Follow-up days must be at least 1", "error"); return; }

    const btn = $("#rxSubmitBtn");
    setButtonLoading(btn, true);

    try {
      const data = await apiJSON("/doctor/prescribe/", {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          doctor_notes: notes,
          follow_up_days: followUp,
        }),
      });
      toast("Prescription generated and sent to patient!", "success");
      closePrescribeModal();

      // Refresh patient detail
      if (state.selectedPatientId) {
        await loadPatientSummaries(state.selectedPatientId);
        await loadPatientFiles(state.selectedPatientId);
      }
    } catch (err) {
      toast(err.message || "Failed to create prescription", "error");
    } finally {
      setButtonLoading(btn, false);
    }
  }
  // ═══════════════════════════════════════
  // DOCTOR: CHAT VIEWER
  // ═══════════════════════════════════════
  function openChatViewer(sessionId, patientId) {
    const pid = Number(patientId);
    const sessions = state.patientSummariesCache[pid] || [];
    const session = sessions.find((s) => s.session_id === sessionId);

    if (!session) {
      toast("Session data not found. Try refreshing.", "error");
      return;
    }

    const patient = state.patients.find((p) => p.id === pid);
    const patientName = patient?.profile?.full_name || patient?.email || "Patient";
    const patientInitial = patientName[0]?.toUpperCase() || "P";
    const messages = session.messages || [];

    // Set header
    $("#chatViewerTitle").textContent = `Chat: ${sessionId}`;
    $("#chatViewerSub").textContent = `${patientName} · ${messages.length} messages · ${formatDate(session.created_at)}`;

    // Render messages
    const el = $("#chatViewerMessages");

    if (!messages.length) {
      el.innerHTML = '<div class="empty-state" style="padding:40px 20px"><div class="empty-state-icon" aria-hidden="true">💬</div><div class="empty-state-title">Empty session</div><div class="empty-state-sub">No messages in this conversation</div></div>';
    } else {
      let html = "";

      // Count by sender
      const counts = { patient: 0, ai: 0, system: 0 };
      messages.forEach((m) => {
        const sender = m.sender === "patient" ? "patient" : m.sender === "system" ? "system" : "ai";
        counts[sender]++;
      });

      messages.forEach((m, i) => {
        const sender = m.sender === "patient" ? "patient" : m.sender === "system" ? "system" : "ai";
        const avatarMap = { patient: patientInitial, system: "⚙", ai: "🤖" };
        const senderLabel = { patient: patientName, system: "System", ai: "AI Assistant" };
        const text = esc(m.text || "").replace(/\n/g, "<br>");

        html += `<div class="cv-msg ${sender}">
        <div class="cv-msg-avatar" aria-hidden="true">${avatarMap[sender]}</div>
        <div>
          <div class="cv-msg-bubble">${text}</div>
          <div class="cv-msg-meta">${esc(senderLabel[sender])}${m.timestamp ? " · " + formatTime(m.timestamp) : ""}</div>
        </div>
      </div>`;
      });

      // Append summary if exists
      if (session.summary) {
        html += '<div class="cv-divider">Clinical Summary</div>';
        html += '<div class="cv-summary-inline">';
        html += '<div class="summary-card-title">— AI Summary —</div>';
        html += Object.entries(session.summary).map(([k, v]) => {
          const key = esc(k.replace(/_/g, " "));
          const val = k === "priority_score"
            ? `<span class="priority ${priorityClass(v)}">${esc(String(v))}/10</span>`
            : esc(String(v));
          return `<div class="summary-row"><span class="summary-key">${key}</span><span class="summary-val">${val}</span></div>`;
        }).join("");
        html += "</div>";
      }

      el.innerHTML = html;
    }

    // Stats footer
    const counts = { patient: 0, ai: 0, system: 0 };
    messages.forEach((m) => {
      const s = m.sender === "patient" ? "patient" : m.sender === "system" ? "system" : "ai";
      counts[s]++;
    });
    $("#chatViewerStats").innerHTML = `
    <span class="cv-msg-count"><span class="dot patient-dot"></span>${counts.patient} patient</span>
    <span class="cv-msg-count"><span class="dot ai-dot"></span>${counts.ai} AI</span>
    ${counts.system ? `<span class="cv-msg-count"><span class="dot system-dot"></span>${counts.system} system</span>` : ""}
  `;

    // Prescribe button
    const rxBtn = $("#chatViewerPrescribeBtn");
    rxBtn.style.display = "";
    rxBtn.dataset.sessionId = sessionId;
    rxBtn.dataset.patientId = patientId;

    // Open modal
    $("#chatViewerModal").classList.add("open");

    // Scroll to bottom
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }

  function closeChatViewer() {
    $("#chatViewerModal").classList.remove("open");
  }
  // ═══════════════════════════════════════
  // CHAT (Patient)
  // ═══════════════════════════════════════
  async function loadSessions() {
    try {
      const res = await api("/users/me/chats/", { _abortKey: "load-sessions" });
      if (res.ok) state.sessions = await res.json();
      renderSessionList();
    } catch (err) {
      if (err.name !== "AbortError") console.error(err);
    }
  }

  function renderSessionList() {
    const el = $("#sessionList");
    if (!state.sessions.length) {
      el.innerHTML = '<div class="empty-state" style="padding:30px 16px"><div class="empty-state-sub">No sessions yet. Start typing to begin.</div></div>';
      return;
    }
    el.innerHTML = state.sessions.map((s) => {
      const firstPatientMsg = s.messages?.find((m) => m.sender === "patient");
      const last = s.messages?.slice().reverse().find((m) => m.sender !== "system");
      const displayName = getSessionDisplayName(firstPatientMsg?.text);
      const preview = esc((last?.text || "No messages").substring(0, 45));
      const active = s.session_id === state.currentSessionId;
      const score = s.summary?.priority_score;
      const pc = priorityClass(score);

      return `<div class="session-item" role="option" aria-selected="${active}" data-action="open-session" data-session-id="${esc(s.session_id)}" tabindex="0">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
          <div style="font-size:13px;font-weight:500;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(displayName)}</div>
          ${score ? `<span class="priority ${pc}" style="flex-shrink:0;margin-left:6px">${esc(String(score))}</span>` : ""}
        </div>
        <div class="session-preview">${preview}…</div>
        <div class="session-date">${formatDate(s.created_at)}</div>
      </div>`;
    }).join("");
  }


  function createNewSession() {
    state.currentSessionId = genId("sess");
    const dateName = `New · ${new Date().toLocaleDateString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`;
    $("#currentSessionName").textContent = dateName;
    $("#currentSessionMeta").textContent = "Type your first message to begin";
    $("#summaryBtn").disabled = false;
    renderMessages([]);
    renderSessionList();
    toast("New session started", "success");
    $("#chatInput").focus();
  }


  function getSessionDisplayName(firstMessage) {
    if (!firstMessage || firstMessage.length < 3) {
      return `Consultation · ${new Date().toLocaleDateString("en-IN", { day: "numeric", month: "short" })}`;
    }

    // Clean up the message
    let name = firstMessage
      .replace(/^(hi|hello|hey|doc|doctor|please|i have|i am|i'm|i've been|i feel|i need)\s*/gi, "")
      .replace(/[.!?,;:]+$/, "")
      .trim();

    // Capitalize first letter
    if (name.length > 0) {
      name = name[0].toUpperCase() + name.slice(1);
    }

    // Truncate to reasonable length
    if (name.length > 40) {
      name = name.substring(0, 37) + "…";
    }

    // If cleaning removed everything, fall back to date
    if (name.length < 3) {
      return `Consultation · ${new Date().toLocaleDateString("en-IN", { day: "numeric", month: "short" })}`;
    }

    return name;
  }

  function openSession(id) {
    state.currentSessionId = id;
    const s = state.sessions.find((x) => x.session_id === id);
    const firstPatientMsg = s?.messages?.find((m) => m.sender === "patient");
    const displayName = getSessionDisplayName(firstPatientMsg?.text);

    $("#currentSessionName").textContent = displayName;
    $("#currentSessionMeta").textContent = `${s?.messages?.length || 0} messages · ${formatDate(s?.created_at)}`;
    $("#summaryBtn").disabled = false;
    renderMessages(s?.messages || []);
    renderSessionList();
    if (s?.summary) appendSummaryCard(s.summary);
    if (state.currentScreen !== "chat") showScreen("chat");
  }

  function renderMessages(msgs) {
    const el = $("#chatMessages");
    if (!msgs.length) {
      el.innerHTML = '<div class="empty-state"><div class="empty-state-icon" aria-hidden="true">🩺</div><div class="empty-state-title">Start the conversation</div><div class="empty-state-sub">Describe your symptoms to the AI assistant</div></div>';
      return;
    }
    el.innerHTML = "";
    msgs.forEach((m) => appendMessage(m, false));
    el.scrollTop = el.scrollHeight;
  }

  function appendMessage(msg, scroll = true) {
    const el = $("#chatMessages");
    const empty = el.querySelector(".empty-state");
    if (empty) el.innerHTML = "";

    const sc = msg.sender === "patient" ? "patient" : msg.sender === "system" ? "system" : "ai";
    const initial = state.user?.email?.[0]?.toUpperCase() || "P";
    const avatarMap = { patient: initial, system: "⚙", ai: "🤖" };

    const div = document.createElement("div");
    div.className = `msg ${sc}`;
    div.setAttribute("role", "article");
    const text = esc(msg.text || "").replace(/\n/g, "<br>");
    div.innerHTML = `<div class="msg-avatar" aria-hidden="true">${avatarMap[sc]}</div>
      <div>
        <div class="msg-bubble">${text}</div>
        ${msg.is_file ? '<div class="msg-file-tag">📎 Attached file</div>' : ""}
        <div class="msg-time">${formatTime(msg.timestamp)}</div>
      </div>`;
    el.appendChild(div);
    if (scroll) el.scrollTop = el.scrollHeight;
  }

  function showTypingIndicator() {
    const el = $("#chatMessages");
    $("#typing-indicator")?.remove();
    const div = document.createElement("div");
    div.className = "msg ai"; div.id = "typing-indicator";
    div.innerHTML = '<div class="msg-avatar" aria-hidden="true">🤖</div><div class="msg-bubble"><div class="typing-dots"><span></span><span></span><span></span></div></div>';
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
  }

  function removeTypingIndicator() { $("#typing-indicator")?.remove(); }

  function appendSummaryCard(summary) {
    const el = $("#chatMessages");
    if (el.querySelector(".summary-card")) return;
    const div = document.createElement("div");
    div.className = "summary-card";
    const rows = Object.entries(summary).map(([k, v]) => {
      const key = esc(k.replace(/_/g, " "));
      const val = k === "priority_score" ? `<span class="priority ${priorityClass(v)}">${esc(String(v))}/10</span>` : esc(String(v));
      return `<div class="summary-row"><span class="summary-key">${key}</span><span class="summary-val">${val}</span></div>`;
    }).join("");
    div.innerHTML = `<div class="summary-card-title">— Clinical Summary —</div>${rows}`;
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
  }

  async function sendChatMessage() {
    const input = $("#chatInput");
    const msg = input.value.trim();
    if (!msg) return;

    // Auto-create session if none exists
    if (!state.currentSessionId) {
      state.currentSessionId = genId("sess");
      $("#currentSessionName").textContent = getSessionDisplayName(msg);
      $("#currentSessionMeta").textContent = "New session";
      $("#summaryBtn").disabled = false;
    }

    if (state.isSending) return;

    state.isSending = true;
    input.value = "";
    input.style.height = "auto";
    $("#sendBtn").disabled = true;



    appendMessage({ sender: "patient", text: msg });
    showTypingIndicator();

    try {
      const res = await api("/chat/", {
        method: "POST",
        body: JSON.stringify({ user_id: 1, session_id: state.currentSessionId, message: msg }),
      });
      const data = await res.json();
      removeTypingIndicator();
      console.log("[Chat] Response:", data);

      if (res.ok) {
        const reply = data.response || data.reply || data.message || data.answer || data.text || (typeof data === "string" ? data : null);
        if (reply) {
          appendMessage({ sender: "ai", text: reply });
        } else {
          appendMessage({ sender: "ai", text: JSON.stringify(data, null, 2) });
        }
        loadSessions().catch(() => { });
      } else {
        appendMessage({ sender: "system", text: `Error: ${parseApiError(data)}` });
      }
    } catch (err) {
      removeTypingIndicator();
      if (err.name !== "AbortError") {
        appendMessage({ sender: "system", text: "Could not reach the server." });
      }
    } finally {
      state.isSending = false;
      $("#sendBtn").disabled = false;
      input.focus();
    }
  }

  async function handleChatFileUpload(input) {
    if (!input.files[0]) return;
    if (!state.currentSessionId) { toast("Start a session first", "error"); input.value = ""; return; }
    const file = input.files[0];
    if (!validateFileSize(file)) { toast(`File too large. Max ${CONFIG.MAX_FILE_SIZE / 1024 / 1024} MB`, "error"); input.value = ""; return; }

    const form = new FormData();
    form.append("file", file);
    form.append("session_id", state.currentSessionId);
    toast("Uploading file…", "info");
    appendMessage({ sender: "system", text: `Uploading ${file.name}…` });

    try {
      const res = await apiForm("/chat/upload", form);
      const data = await res.json();
      if (res.ok) toast("File uploaded!", "success");
      else toast(parseApiError(data), "error");
    } catch { toast("Upload failed", "error"); }
    input.value = "";
  }

  // ═══════════════════════════════════════
  // POLLING
  // ═══════════════════════════════════════
  function startPolling() {
    stopPolling();
    state.pollTimer = setInterval(() => {
      if (state.currentScreen === "chat") loadSessions().catch(() => { });
    }, CONFIG.POLL_INTERVAL);
  }

  function stopPolling() {
    if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
  }


  // ═══════════════════════════════════════
  // APPOINTMENTS DATA
  // ═══════════════════════════════════════
  // ═══════════════════════════════════════
  // APPOINTMENTS DATA
  // ═══════════════════════════════════════
  async function loadAppointments() {
    try {
      const endpoint = state.user.role === 'doctor' ? '/appointments/doctor' : '/appointments/me';
      const appts = await apiJSON(endpoint); // <-- Fixed apiJSON
      const container = $("#appointmentsList");

      if (!appts || appts.length === 0) {
        container.innerHTML = `
          <div class="empty-state" style="padding:60px 20px">
            <div class="empty-state-icon" aria-hidden="true">📅</div>
            <div class="empty-state-title">No appointments</div>
            <div class="empty-state-sub">You have no upcoming appointments scheduled.</div>
          </div>`;
        return;
      }

      container.innerHTML = appts.map(apt => {
        // ✅ Fix: backend field is scheduled_time, not appointment_date
        const dt = apt.scheduled_time || apt.appointment_date;
        const dateStr = dt ? new Date(dt).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—';
        const statusVal = apt.status?.value || apt.status || 'scheduled';
        const statusClass = statusVal === 'scheduled' ? 'upcoming' : statusVal;
        return `
        <div class="appointment-card">
          <div class="appointment-details">
            <div class="apt-date">${dateStr}</div>
            <div class="apt-title">${state.user.role === 'doctor' ? 'Patient ID: ' + apt.patient_id : 'Appointment #' + apt.id}</div>
            <div class="apt-sub">${apt.meeting_link ? `<a href="${esc(apt.meeting_link)}" target="_blank" style="color:var(--accent)">Join Google Meet</a>` : 'No meeting link yet'}</div>
          </div>
          <div class="apt-actions">
            <span class="apt-status ${esc(statusClass)}">${esc(statusVal)}</span>
            ${statusVal === 'scheduled' ? `<button class="btn btn-ghost" data-action="cancel-apt" data-apt-id="${apt.id}" style="color:var(--red); font-size:12px;">Cancel</button>` : ''}
          </div>
        </div>`;
      }).join('');
    } catch (e) {
      console.error(e);
      toast("Failed to load appointments", "error"); // <-- Fixed toast
    }
  }

  // ═══════════════════════════════════════
  // FILES (Patient)
  // ═══════════════════════════════════════
  async function loadFiles() {
    try {
      const res = await api("/users/me/media/", { _abortKey: "load-files" });
      if (res.ok) state.files = await res.json();
      renderFiles();
    } catch (err) {
      if (err.name !== "AbortError") console.error(err);
    }
  }

  function getFileTypeInfo(f) {
    if (f.file_type === "audio") return {
      cls: "audio",
      svg: '<svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
    };
    if (f.file_type === "pdf" || f.file_name?.endsWith(".pdf")) return {
      cls: "pdf",
      svg: '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>',
    };
    return {
      cls: "image",
      svg: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21,15 16,10 5,21"/></svg>',
    };
  }

  function renderFiles() {
    const el = $("#filesGrid");
    if (!state.files.length) {
      el.innerHTML = '<div class="empty-state" style="grid-column:1/-1;padding:60px 20px"><div class="empty-state-icon" aria-hidden="true">📂</div><div class="empty-state-title">No files yet</div><div class="empty-state-sub">Upload your medical records</div></div>';
      return;
    }
    el.innerHTML = state.files.map((f) => {
      const info = getFileTypeInfo(f);
      const isProc = f.transcript?.includes("being analyzed") || f.drive_file_id === "processing...";
      const hasTr = f.transcript && f.transcript !== "User Uploaded Record" && !isProc;
      return `<div class="file-card" role="listitem" data-action="view-file" data-file-id="${f.id}" tabindex="0">
        <div class="file-card-actions">
          <button class="file-delete-btn" data-action="delete-file" data-file-id="${f.id}" aria-label="Delete ${esc(f.file_name)}" type="button">
            <svg viewBox="0 0 24 24"><polyline points="3,6 5,6 21,6"/><path d="M19,6v14a2,2,0,01-2,2H7a2,2,0,01-2-2V6m3,0V4a2,2,0,012-2h4a2,2,0,012,2v2"/></svg>
          </button>
        </div>
        <div class="file-icon ${info.cls}" aria-hidden="true">${info.svg}</div>
        <div class="file-name">${esc(f.file_name)}</div>
        <div class="file-meta">${formatDate(f.created_at)} · ${esc(f.file_type || "file")}</div>
        ${isProc ? '<div class="file-transcript" style="color:var(--amber);font-style:italic">⟳ Processing…</div>' : ""}
        ${hasTr ? `<div class="file-transcript">${esc(f.transcript)}</div>` : ""}
      </div>`;
    }).join("");

    const processing = state.files.some((f) => f.drive_file_id === "processing...");
    $("#processingBanner").classList.toggle("visible", processing);
    if (processing) setTimeout(loadFiles, CONFIG.POLL_INTERVAL);
  }

  async function deleteFile(id) {
    const ok = await confirm("Delete File", "This will permanently delete this file.");
    if (!ok) return;
    try {
      const res = await api(`/media/${id}`, { method: "DELETE" });
      if (res.ok) { toast("File deleted", "success"); loadFiles(); loadDashboard(); }
      else toast("Could not delete file", "error");
    } catch { toast("Error deleting file", "error"); }
  }
  // ═══════════════════════════════════════
  // FILE VIEWING (Authenticated)
  // ═══════════════════════════════════════

  /**
   * Fetches a file through the API with proper auth headers,
   * creates a temporary blob URL, and opens it in a new tab.
   */
  async function viewFileAuthenticated(url) {
    if (!url) {
      toast("File not yet available", "info");
      return;
    }

    toast("Loading file…", "info");

    try {
      // Fetch with auth header
      const res = await fetch(url, {
        headers: {
          "Authorization": `Bearer ${state.token}`,
        },
      });

      if (!res.ok) {
        const errorText = await res.text();
        console.error("[ViewFile] Error:", res.status, errorText);
        if (res.status === 401) {
          toast("Session expired. Please sign in again.", "error");
          handleLogout(true);
          return;
        }
        toast(`Could not load file (${res.status})`, "error");
        return;
      }

      // Get the content type from response
      const contentType = res.headers.get("content-type") || "application/octet-stream";
      const blob = await res.blob();

      // Create a temporary URL for the blob
      const blobUrl = URL.createObjectURL(blob);

      // Open in new tab
      const newTab = window.open(blobUrl, "_blank");

      // If popup was blocked, offer download instead
      if (!newTab) {
        const a = document.createElement("a");
        a.href = blobUrl;
        a.download = "medical-file";
        a.click();
        toast("File downloaded (popup was blocked)", "info");
      }

      // Clean up blob URL after a delay (tab has already loaded it)
      setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);

    } catch (err) {
      console.error("[ViewFile] Fetch error:", err);
      toast("Could not load file. Check your connection.", "error");
    }
  }
  function viewFile(id) {
    const f = state.files.find((x) => x.id === id);
    if (f?.drive_view_link) {
      viewFileAuthenticated(f.drive_view_link);
    } else {
      toast("File not yet available", "info");
    }
  }

  async function handleGenericUpload(input) {
    if (!input.files[0]) return;
    const file = input.files[0];
    if (!validateFileSize(file)) { toast(`File too large. Max ${CONFIG.MAX_FILE_SIZE / 1024 / 1024} MB`, "error"); input.value = ""; return; }
    const form = new FormData();
    form.append("file", file);
    toast("Uploading…", "info");
    try {
      const res = await apiForm("/media/upload/", form);
      if (res.ok) { toast("File uploaded!", "success"); loadFiles(); loadDashboard(); }
      else { const d = await res.json(); toast(parseApiError(d), "error"); }
    } catch { toast("Upload error", "error"); }
    input.value = "";
  }

  async function handleOcrUpload(input) {
    if (!input.files[0]) return;
    const file = input.files[0];
    if (!validateFileSize(file)) { toast(`File too large`, "error"); input.value = ""; return; }
    const form = new FormData();
    form.append("file", file);
    toast("Starting OCR…", "info");
    try {
      const res = await apiForm("/ocr/analyze", form);
      if (res.ok) { toast("OCR started!", "success"); setTimeout(loadFiles, 3000); }
      else { const d = await res.json(); toast(parseApiError(d), "error"); }
    } catch { toast("OCR error", "error"); }
    input.value = "";
  }

  // ═══════════════════════════════════════
  // UPLOAD MODAL
  // ═══════════════════════════════════════
  function openUploadModal() {
    state.modalFile = null;
    $("#modalFileInput").value = "";
    $("#uploadFileName").style.display = "none";
    $("#modalUploadBtn").disabled = true;
    $("#uploadModal").classList.add("open");
  }

  function closeUploadModal() {
    $("#uploadModal").classList.remove("open");
    state.modalFile = null;
  }

  function handleModalFileSelect(file) {
    if (!file) return;
    if (!validateFileSize(file)) { toast(`File too large`, "error"); return; }
    state.modalFile = file;
    const fn = $("#uploadFileName");
    fn.textContent = `📎 ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    fn.style.display = "block";
    $("#modalUploadBtn").disabled = false;
  }

  async function submitModalUpload() {
    if (!state.modalFile) { toast("Select a file first", "error"); return; }
    const btn = $("#modalUploadBtn");
    setButtonLoading(btn, true);
    const form = new FormData();
    form.append("file", state.modalFile);
    try {
      const res = await apiForm("/media/upload/", form);
      if (res.ok) { toast("File uploaded!", "success"); closeUploadModal(); loadFiles(); loadDashboard(); }
      else { const d = await res.json(); toast(parseApiError(d), "error"); }
    } catch { toast("Upload error", "error"); }
    finally { setButtonLoading(btn, false); }
  }

  // ═══════════════════════════════════════
  // PROFILE
  // ═══════════════════════════════════════
  function clearProfileForm() {
    $("#profFullName").value = "";
    $("#profContact").value = "";
    $("#profAddress").value = "";
    $("#profBlood").value = "";
    $("#profStatus").value = "stable";
    $("#profileName").textContent = "\u2014";
  }

  async function loadProfile() {
    // Always clear first to prevent stale data from showing
    clearProfileForm();

    try {
      const res = await api("/users/me/profile/", { _abortKey: "load-profile" });

      if (res.ok) {
        const profile = await res.json();
        const displayName = profile.full_name || state.user?.email || "User";
        const initial = displayName.charAt(0).toUpperCase();

        // Populate form fields
        $("#profFullName").value = profile.full_name || "";
        $("#profContact").value = profile.contact_no || "";
        $("#profAddress").value = profile.address || "";
        $("#profBlood").value = profile.blood_group || "";
        $("#profStatus").value = profile.current_status || "stable";

        // Update sidebar and profile names
        if ($("#sidebarEmail")) $("#sidebarEmail").textContent = displayName;
        if ($("#profileName")) $("#profileName").textContent = displayName;

        // Handle Profile Picture vs Initial Letter
        const avatarImg = $("#profileAvatarImg");
        const avatarText = $("#profileAvatarText");

        if (profile.profile_pic_drive_id) {
          // User HAS a picture: Show Image, Hide Text
          const imgUrl = `${CONFIG.API_BASE}/media/view/${profile.profile_pic_drive_id}`;

          if (avatarImg) {
            avatarImg.src = imgUrl;
            avatarImg.style.display = "block";
          }
          if (avatarText) avatarText.style.display = "none";

          // Update the tiny sidebar avatar!
          if ($("#sidebarAvatar")) {
            $("#sidebarAvatar").innerHTML = `<img src="${imgUrl}" style="width:100%; height:100%; object-fit:cover; border-radius:50%;">`;
          }
        } else {
          // NO picture: Show Text, Hide Image
          if (avatarImg) avatarImg.style.display = "none";
          if (avatarText) {
            avatarText.style.display = "block";
            avatarText.textContent = initial;
          }
          if ($("#sidebarAvatar")) $("#sidebarAvatar").innerHTML = initial;
        }

      } else if (res.status === 404) {
        // No profile yet — form already cleared above
        console.log("[Profile] No existing profile found");
        const initial = state.user?.email?.[0]?.toUpperCase() || "U";
        if ($("#profileAvatarText")) $("#profileAvatarText").textContent = initial;
        if ($("#sidebarAvatar")) $("#sidebarAvatar").innerHTML = initial;
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        console.error("[Profile] Failed to load:", err);
      }
    }
  }

  async function saveProfile(e) {
    e.preventDefault();
    const body = {
      full_name: $("#profFullName").value.trim(),
      contact_no: $("#profContact").value.trim(),
      address: $("#profAddress").value.trim(),
      blood_group: $("#profBlood").value,
      current_status: $("#profStatus").value,
    };

    if (!body.full_name || !body.contact_no) {
      toast("Name and contact required", "error");
      return;
    }

    const btn = $("#profileSaveBtn");
    setButtonLoading(btn, true);

    try {
      const res = await api("/users/me/profile/", { method: "POST", body: JSON.stringify(body) });
      if (res.ok) {
        toast("Profile saved!", "success");
        // Reload the profile to cleanly update names/avatars without breaking images
        loadProfile();
      } else {
        const d = await res.json();
        toast(parseApiError(d), "error");
      }
    } catch {
      toast("Server error", "error");
    } finally {
      setButtonLoading(btn, false);
    }
  }

  // ═══════════════════════════════════════
  // ACTION HANDLER
  // ═══════════════════════════════════════
  function handleAction(e) {
    const target = e.target.closest("[data-action]");
    if (!target) return;
    const action = target.dataset.action;

    switch (action) {
      case "new-consult": showScreen("chat"); createNewSession(); break;
      case "upload-modal": openUploadModal(); break;
      case "new-session": createNewSession(); break;
      case "open-session": e.preventDefault(); openSession(target.dataset.sessionId); break;
      case "get-summary": $("#chatInput").value = "Please SUMMARIZE our conversation"; sendChatMessage(); break;
      case "send-chat": sendChatMessage(); break;
      case "toggle-sessions": $("#chatSessionsPanel").classList.toggle("mobile-open"); break;
      case "go-chat": showScreen("chat"); break;
      case "go-files": showScreen("files"); break;
      case "go-patients": showScreen("patients"); break;
      case "close-upload": closeUploadModal(); break;
      case "submit-upload": submitModalUpload(); break;
      case "confirm-cancel": closeConfirm(false); break;
      case "appointments":
        showScreen("appointments");
        break;
      case "confirm-ok": closeConfirm(true); break;
      case "delete-file": e.stopPropagation(); deleteFile(Number(target.dataset.fileId)); break;
      case "view-file": viewFile(Number(target.dataset.fileId)); break;
      case "view-file-direct": {
        const link = target.dataset.viewLink;
        if (link) {
          viewFileAuthenticated(link);
        } else {
          toast("File not available", "info");
        }
        break;
      }
      case "refresh-patients": loadPatients(); break;
      case "view-patient": viewPatient(Number(target.dataset.patientId)); break;
      case "back-to-patients": showScreen("patients"); break;
      case "prescribe": openPrescribeModal(target.dataset.sessionId, target.dataset.patientId); break;
      case "close-prescribe": closePrescribeModal(); break;
      case "view-chat-readonly":
        openChatViewer(target.dataset.sessionId, target.dataset.patientId);
        break;
      case "close-chat-viewer":
        closeChatViewer();
        break;
      case "prescribe-from-viewer":
        closeChatViewer();
        openPrescribeModal(target.dataset.sessionId, target.dataset.patientId);
        break;
      // ✅ Fix: cancel-apt was added to the render HTML but never handled here
      case "cancel-apt": {
        const aptId = Number(target.dataset.aptId);
        confirm("Cancel Appointment", "Are you sure you want to cancel this appointment?").then(async (ok) => {
          if (!ok) return;
          try {
            await api(`/appointments/${aptId}/cancel`, { method: "PATCH" });
            toast("Appointment cancelled", "success");
            loadAppointments();
          } catch (err) {
            toast("Could not cancel appointment", "error");
          }
        });
        break;
      }
    }
  }


  // ═══════════════════════════════════════
  // EVENTS
  // ═══════════════════════════════════════
  function initEvents() {
    $("#loginFormEl").addEventListener("submit", handleLogin);
    $("#registerFormEl").addEventListener("submit", handleRegister);
    $("#showRegister").addEventListener("click", (e) => { e.preventDefault(); toggleAuthMode("register"); });
    $("#showLogin").addEventListener("click", (e) => { e.preventDefault(); toggleAuthMode("login"); });
    $("#profileFormEl").addEventListener("submit", saveProfile);
    $("#prescribeFormEl").addEventListener("submit", submitPrescription);

    $$(".nav-item[data-screen]").forEach((item) => {
      item.addEventListener("click", () => showScreen(item.dataset.screen));
      item.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); showScreen(item.dataset.screen); } });
    });

    // Detail tabs
    $$(".detail-tab").forEach((tab) => {
      tab.addEventListener("click", () => activateDetailTab(tab.dataset.tab));
    });

    $("#hamburgerBtn").addEventListener("click", openSidebar);
    $("#sidebarOverlay").addEventListener("click", closeSidebar);

    const logoutPill = $("#logoutPill");
    logoutPill.addEventListener("click", () => handleLogout());
    logoutPill.addEventListener("keydown", (e) => { if (e.key === "Enter") handleLogout(); });

    const chatInput = $("#chatInput");
    chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChatMessage(); } });
    chatInput.addEventListener("input", () => autoResize(chatInput));

    $("#chatFileInput").addEventListener("change", function () { handleChatFileUpload(this); });
    $("#genericUploadInput").addEventListener("change", function () { handleGenericUpload(this); });
    $("#ocrInput").addEventListener("change", function () { handleOcrUpload(this); });
    $("#modalFileInput").addEventListener("change", function () { if (this.files[0]) handleModalFileSelect(this.files[0]); });

    const zone = $("#uploadZone");
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("drag-over"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
    zone.addEventListener("drop", (e) => { e.preventDefault(); zone.classList.remove("drag-over"); if (e.dataTransfer.files[0]) handleModalFileSelect(e.dataTransfer.files[0]); });

    $$(".hint-chip[data-hint]").forEach((chip) => {
      chip.addEventListener("click", () => { chatInput.value = chip.dataset.hint; chatInput.focus(); });
    });

    document.addEventListener("click", handleAction);

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if ($("#confirmModal").classList.contains("open")) closeConfirm(false);
        else if ($("#chatViewerModal").classList.contains("open")) closeChatViewer();
        else if ($("#prescribeModal").classList.contains("open")) closePrescribeModal();
        else if ($("#uploadModal").classList.contains("open")) closeUploadModal();
        else if ($("#sidebar").classList.contains("open")) closeSidebar();
      }
    });

    $("#uploadModal").addEventListener("click", (e) => { if (e.target === $("#uploadModal")) closeUploadModal(); });
    $("#confirmModal").addEventListener("click", (e) => { if (e.target === $("#confirmModal")) closeConfirm(false); });
    $("#prescribeModal").addEventListener("click", (e) => { if (e.target === $("#prescribeModal")) closePrescribeModal(); });
    $("#chatViewerModal").addEventListener("click", (e) => {
      if (e.target === $("#chatViewerModal")) closeChatViewer();
    });

    window.addEventListener("online", updateConnectionStatus);
    window.addEventListener("offline", updateConnectionStatus);

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && state.token) {
        if (state.currentScreen === "dashboard") loadDashboard();
        if (state.currentScreen === "chat") loadSessions();
        if (state.currentScreen === "files") loadFiles();
        if (state.currentScreen === "patients") loadPatients();
      }
    });

    if (window.innerWidth <= 768) $("#mobileSessionsBtn").style.display = "inline-flex";
    window.addEventListener("resize", debounce(() => {
      $("#mobileSessionsBtn").style.display = window.innerWidth <= 768 ? "inline-flex" : "none";
    }, CONFIG.DEBOUNCE_MS));

    $$(".form-input[required]").forEach((input) => {
      input.addEventListener("blur", () => {
        if (input.type === "email" && input.value && !validateEmail(input.value)) input.setAttribute("aria-invalid", "true");
        else if (input.value) input.removeAttribute("aria-invalid");
      });
      input.addEventListener("input", () => {
        input.removeAttribute("aria-invalid");
        const hint = input.parentElement?.querySelector(".form-hint");
        if (hint) hint.classList.remove("visible");
      });
    });
    // --- 🎙️ VOICE TO TEXT (CHAT) ---
    let mediaRecorder;
    let audioChunks = [];
    const recordBtn = $("#recordVoiceBtn");

    if (recordBtn) {
      // Start Recording on Mouse Down
      recordBtn.addEventListener("mousedown", async () => {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          mediaRecorder = new MediaRecorder(stream);
          audioChunks = [];

          mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
          mediaRecorder.start();

          recordBtn.classList.add("is-recording");
          recordBtn.innerHTML = "🛑 Recording...";
        } catch (e) {
          toast("Microphone access denied. Please allow permissions.", "error");
        }
      });

      // Stop Recording on Mouse Up and Send to API
      recordBtn.addEventListener("mouseup", () => {
        if (mediaRecorder && mediaRecorder.state === "recording") {
          mediaRecorder.stop();
          recordBtn.classList.remove("is-recording");
          recordBtn.innerHTML = "🎙️ Dictate";

          mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            const formData = new FormData();
            formData.append("file", audioBlob, "voice_memo.webm");

            try {
              toast("Transcribing voice...", "info");
              const res = await fetch(`${CONFIG.API_BASE}/chat/voice-to-text`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${state.token}` },
                body: formData
              });
              if (!res.ok) throw new Error("Transcription failed");
              const data = await res.json();

              if (data.text) {
                const input = $("#chatInput");
                input.value = input.value ? input.value + " " + data.text : data.text;
                toast("Voice transcribed!", "success");
              }
            } catch (e) {
              toast(e.message, "error");
            }
          };
        }
      });
    }

    // --- 🖼️ PROFILE PICTURE UPLOAD ---
    const profilePicUpload = $("#profilePicUpload");
    if (profilePicUpload) {
      profilePicUpload.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append("file", file);

        try {
          toast("Uploading profile picture...", "info");
          const res = await fetch(`${CONFIG.API_BASE}/users/me/profile-pic/`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${state.token}` },
            body: formData
          });
          if (!res.ok) throw new Error("Failed to upload image");

          toast("Profile picture updated successfully!", "success");
          loadProfile(); // Reload the profile to fetch the new image
        } catch (err) {
          toast(err.message, "error");
        } finally {
          e.target.value = ""; // Reset input
        }
      });
    }

    // --- 🎙️ FILE TRANSCRIPTION ---
    const transcribeInput = $("#transcribeInput");
    if (transcribeInput) {
      transcribeInput.addEventListener("change", async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append("file", file);

        $("#processingBanner").classList.add("visible");
        try {
          const res = await fetch(`${CONFIG.API_BASE}/transcribe/`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${state.token}` },
            body: formData
          });
          if (!res.ok) throw new Error("Transcription failed");

          toast("Audio transcribed successfully!", "success");
          loadFiles(); // Reload files to show the new transcript file
        } catch (err) {
          toast(err.message, "error");
        } finally {
          $("#processingBanner").classList.remove("visible");
          e.target.value = "";
        }
      });
    }

    // --- 📅 BOOK APPOINTMENT MOCK ---
    const bookBtn = $("#bookAppointmentBtn");
    if (bookBtn) {
      bookBtn.addEventListener("click", async () => {
        // ✅ Fix: backend AppointmentCreate schema needs doctor_id, session_id, scheduled_time
        // Old code sent appointment_date + reason which the backend doesn't accept

        // Get available sessions so user can pick one
        let sessionOptions = '<option value="">Select a chat session</option>';
        try {
          const sessions = await apiJSON("/users/me/chats/");
          if (sessions.length) {
            sessionOptions = '<option value="">Select a session</option>' +
              sessions.map(s => `<option value="${esc(s.session_id)}">Session ${s.session_id.slice(0, 16)}… (${formatDate(s.created_at)})</option>`).join('');
          }
        } catch (e) { /* leave default */ }

        // Build a simple inline modal using the confirm modal as a base
        $("#confirmTitle").textContent = "Book Appointment";
        $("#confirmBody").innerHTML = `
          <div style="display:flex;flex-direction:column;gap:14px;margin-top:12px">
            <div>
              <label class="form-label" for="bookDoctorId">Doctor ID</label>
              <input type="number" class="form-input" id="bookDoctorId" placeholder="Enter doctor's user ID" min="1" />
            </div>
            <div>
              <label class="form-label" for="bookSessionSel">Chat Session</label>
              <select class="form-select" id="bookSessionSel">${sessionOptions}</select>
            </div>
            <div>
              <label class="form-label" for="bookDateTime">Date &amp; Time</label>
              <input type="datetime-local" class="form-input" id="bookDateTime"
                min="${new Date().toISOString().slice(0, 16)}" />
            </div>
          </div>`;
        $("#confirmOkBtn").textContent = "Book";
        $("#confirmOkBtn").className = "btn btn-primary";
        $("#confirmModal").classList.add("open");
        $("#confirmOkBtn").focus();

        // Override confirm resolver to do the booking
        state.confirmResolver = async (ok) => {
          state.confirmResolver = null;
          $("#confirmModal").classList.remove("open");
          $("#confirmOkBtn").textContent = "Confirm";
          $("#confirmOkBtn").className = "btn btn-danger";
          if (!ok) return;

          const doctorId = parseInt($("#bookDoctorId")?.value);
          const sessionId = $("#bookSessionSel")?.value;
          const dt = $("#bookDateTime")?.value;

          if (!doctorId || !sessionId || !dt) {
            toast("Please fill all fields", "error");
            return;
          }

          try {
            await apiJSON("/appointments/", {
              method: "POST",
              body: JSON.stringify({
                doctor_id: doctorId,
                session_id: sessionId,
                scheduled_time: new Date(dt).toISOString(),
              })
            });
            toast("Appointment booked!", "success");
            loadAppointments();
          } catch (err) {
            toast("Failed to book: " + err.message, "error");
          }
        };
      });
    }
  }

  // ═══════════════════════════════════════
  // GOOGLE AUTHENTICATION
  // ═══════════════════════════════════════
  async function handleGoogleCredential(response) {
    try {
      // ✅ Fix: backend auth router has no prefix, so endpoint is /google not /auth/google
      const res = await apiJSON("/google", {
        method: "POST",
        body: JSON.stringify({ token: response.credential })
      });

      // Save token and extract user info
      localStorage.setItem(CONFIG.TOKEN_KEY, res.access_token);
      state.token = res.access_token;

      // Decode JWT to get user role
      const base64Url = res.access_token.split('.')[1];
      const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
      const decodedData = JSON.parse(window.atob(base64));

      state.user = { email: decodedData.sub || decodedData.email, role: decodedData.role };
      localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(state.user));

      toast("Successfully logged in with Google", "success"); // <-- Fixed toast
      enterApp();
    } catch (err) {
      toast("Google Login failed: " + err.message, "error"); // <-- Fixed toast
    }
  }

  function initGoogleAuth() {
    if (window.google && window.google.accounts) {
      window.google.accounts.id.initialize({
        // THIS IS YOUR CLIENT ID FROM YOUR backend/token.json FILE
        client_id: "666424566836-g3mqci3qmqh07er02rrdu94pj844ck35.apps.googleusercontent.com",
        callback: handleGoogleCredential
      });
      window.google.accounts.id.renderButton(
        document.getElementById("googleSignInContainer"),
        { theme: "outline", size: "large", type: "standard", shape: "pill", width: "100%" }
      );
    }
  }
  // ═══════════════════════════════════════
  // INIT
  // ═══════════════════════════════════════
  function init() {
    initEvents();
    updateConnectionStatus();
    initGoogleAuth();

    state.token = localStorage.getItem(CONFIG.TOKEN_KEY) || null;
    try { state.user = JSON.parse(localStorage.getItem(CONFIG.USER_KEY) || "null"); } catch { state.user = null; }

    if (state.token && state.user) {
      enterApp();
    } else {
      localStorage.removeItem(CONFIG.TOKEN_KEY);
      localStorage.removeItem(CONFIG.USER_KEY);
      $("#authWrap").style.display = "flex";
      $("#mainApp").style.display = "none";
      setTimeout(() => $("#loginEmail").focus(), 200);
    }
  }

  return { init };
})();

document.addEventListener("DOMContentLoaded", App.init);
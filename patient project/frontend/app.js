const API_BASE = "http://127.0.0.1:8000";
let token = localStorage.getItem("token") || null;
let userRole = null;
let currentSessionId = "session_" + Date.now();

// --- INIT & UTILS ---
window.onload = () => {
    if (token) {
        decodeTokenAndSetup(token);
    }
};

function parseJwt(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(window.atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        return JSON.parse(jsonPayload);
    } catch (e) {
        return null;
    }
}

function decodeTokenAndSetup(jwt) {
    const payload = parseJwt(jwt);
    if (!payload) return logout();
    
    token = jwt;
    userRole = payload.role;
    localStorage.setItem("token", token);
    
    document.getElementById("auth-status").innerText = `Logged in as: ${payload.email} (${userRole})`;
    document.getElementById("auth-section").classList.add("hidden");
    document.getElementById("logout-btn").classList.remove("hidden");

    if (userRole === "doctor" || userRole === "admin") {
        document.getElementById("doctor-section").classList.remove("hidden");
    } else {
        document.getElementById("patient-section").classList.remove("hidden");
    }
}

function logout() {
    token = null;
    userRole = null;
    localStorage.removeItem("token");
    location.reload();
}

async function apiFetch(endpoint, options = {}) {
    const headers = { ...options.headers };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
        headers["Content-Type"] = "application/json";
    }

    const response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
    if (!response.ok) {
        const err = await response.json();
        alert(`Error: ${err.detail || response.statusText}`);
        throw new Error(err.detail);
    }
    return response.json();
}

// --- AUTHENTICATION ---
document.getElementById("register-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const email = document.getElementById("reg-email").value;
    const password = document.getElementById("reg-password").value;
    try {
        await apiFetch("/users/", {
            method: "POST",
            body: JSON.stringify({ email, password, is_policy_accepted: true, has_signed_baa: true })
        });
        alert("Registration successful! Please login.");
    } catch (e) {}
});

document.getElementById("login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("login-email").value;
    const password = document.getElementById("login-password").value;
    
    const formData = new URLSearchParams();
    formData.append("username", username);
    formData.append("password", password);

    try {
        const res = await apiFetch("/login", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: formData.toString()
        });
        decodeTokenAndSetup(res.access_token);
    } catch (e) {}
});

// --- PATIENT FEATURES ---
document.getElementById("profile-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
        full_name: document.getElementById("prof-name").value,
        contact_no: document.getElementById("prof-contact").value,
        address: document.getElementById("prof-address").value,
        blood_group: document.getElementById("prof-blood").value,
        current_status: document.getElementById("prof-status").value
    };
    try {
        await apiFetch("/users/me/profile/", { method: "POST", body: JSON.stringify(payload) });
        alert("Profile Updated!");
    } catch (e) {}
});

// AI Chat
document.getElementById("chat-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("chat-input");
    const msg = input.value;
    input.value = "";
    
    appendMessage("patient", msg);

    try {
        const res = await apiFetch("/chat/", {
            method: "POST",
            body: JSON.stringify({ user_id: 0, session_id: currentSessionId, message: msg })
        });
        appendMessage("ai", res.response);
    } catch (e) {}
});

document.getElementById("chat-upload-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fileInput = document.getElementById("chat-file");
    if (!fileInput.files[0]) return;

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);
    formData.append("session_id", currentSessionId);

    appendMessage("system", `Uploading ${fileInput.files[0].name}...`);

    try {
        await apiFetch("/chat/upload", { method: "POST", body: formData });
        appendMessage("system", "Upload sent to background processing. AI will respond shortly.");
    } catch (e) {}
    fileInput.value = "";
});

function appendMessage(role, text) {
    const box = document.getElementById("chat-box");
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.innerText = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

// Media Uploads
async function uploadMedia(inputId, endpoint) {
    const fileInput = document.getElementById(inputId);
    if (!fileInput.files[0]) return alert("Please select a file.");

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    try {
        const res = await apiFetch(endpoint, { method: "POST", body: formData });
        alert(res.message || "Upload initiated!");
        fileInput.value = "";
    } catch (e) {}
}

async function fetchMyMedia() {
    try {
        const media = await apiFetch("/users/me/media/");
        const list = document.getElementById("media-list");
        list.innerHTML = "";
        media.forEach(m => {
            const li = document.createElement("li");
            li.innerHTML = `<strong>${m.file_type}:</strong> ${m.file_name} <br>
                            <small>${m.transcript || 'No transcript'}</small><br>
                            <a href="${m.drive_view_link}" target="_blank">View File</a> | 
                            <button onclick="deleteMedia(${m.id})">Delete</button>`;
            list.appendChild(li);
        });
    } catch (e) {}
}

async function deleteMedia(id) {
    try {
        await apiFetch(`/media/${id}`, { method: "DELETE" });
        alert("Deleted");
        fetchMyMedia();
    } catch (e) {}
}


// --- DOCTOR FEATURES ---
async function fetchPatients() {
    try {
        const patients = await apiFetch("/doctor/patients/");
        const list = document.getElementById("patient-list");
        list.innerHTML = "";
        patients.forEach(p => {
            const li = document.createElement("li");
            li.innerHTML = `<strong>${p.profile ? p.profile.full_name : p.email}</strong> (ID: ${p.id}) 
                            <button onclick="fetchSummaries(${p.id})">View Summaries</button>`;
            list.appendChild(li);
        });
    } catch (e) {}
}

async function fetchSummaries(patientId) {
    try {
        const sessions = await apiFetch(`/doctor/patients/${patientId}/summaries`);
        const list = document.getElementById("patient-list");
        list.innerHTML = `<h3>Summaries for Patient ${patientId}</h3><button onclick="fetchPatients()">Back to Patients</button>`;
        
        sessions.forEach(s => {
            const li = document.createElement("li");
            li.innerHTML = `<strong>Session:</strong> ${s.session_id} <br>
                            <strong>Summary:</strong> <pre>${JSON.stringify(s.summary, null, 2)}</pre>
                            <button onclick="openPrescriptionForm('${s.session_id}')">Write Prescription</button>`;
            list.appendChild(li);
        });
    } catch (e) {}
}

function openPrescriptionForm(sessionId) {
    document.getElementById("rx-session-id").innerText = sessionId;
    document.getElementById("prescription-card").style.display = "block";
}

document.getElementById("prescription-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const sessionId = document.getElementById("rx-session-id").innerText;
    const payload = {
        session_id: sessionId,
        doctor_notes: document.getElementById("rx-notes").value,
        follow_up_days: parseInt(document.getElementById("rx-followup").value)
    };

    try {
        const res = await apiFetch("/doctor/prescribe/", { method: "POST", body: JSON.stringify(payload) });
        alert("Prescription Generated! View link: " + res.file_url);
        document.getElementById("prescription-card").style.display = "none";
    } catch (e) {}
});
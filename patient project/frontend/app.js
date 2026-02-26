const API_URL = "http://127.0.0.1:8000";
let currentSessionId = "sess_" + Date.now();

// 1. SECURE FETCH WRAPPER
async function fetchSecure(endpoint, options = {}) {
    const token = localStorage.getItem("token");
    const headers = options.headers || {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const response = await fetch(`${API_URL}${endpoint}`, { ...options, headers });
    if (response.status === 401) app.logout();
    return response;
}

const app = {
    // 2. AUTHENTICATION
    handleLogin: async (e) => {
        e.preventDefault();
        const params = new URLSearchParams();
        params.append("username", document.getElementById('login-email').value);
        params.append("password", document.getElementById('login-pass').value);

        const res = await fetch(`${API_URL}/login`, {
            method: "POST",
            body: params
        });

        if (res.ok) {
            const data = await res.json();
            localStorage.setItem("token", data.access_token);
            ui.showApp();
        } else {
            alert("Login Failed");
        }
    },

    // 3. UNIFIED CHAT & CONTEXT
    sendMessage: async () => {
        const input = document.getElementById('chat-msg-input');
        const text = input.value;
        if (!text) return;

        ui.appendMsg('user', text);
        input.value = "";

        const res = await fetchSecure('/chat/', {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: currentSessionId, message: text })
        });

        const data = await res.json();
        ui.appendMsg('ai', data.response);
    },

    // 4. EPHEMERAL VOICE-TO-TEXT
    processVoice: async (blob) => {
        const formData = new FormData();
        formData.append("file", blob, "voice.webm");

        const res = await fetchSecure('/chat/voice-to-text', {
            method: "POST",
            body: formData
        });

        const data = await res.json();
        document.getElementById('chat-msg-input').value += data.text;
    },

    // 5. SUMMARIZE (DOCTOR NOTIFICATION)
    summarizeSession: async () => {
        ui.appendMsg('system', "Generating clinical summary for your doctor...");
        const res = await fetchSecure('/chat/', {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: currentSessionId, message: "SUMMARIZE" })
        });
        const data = await res.json();
        ui.appendMsg('ai', data.response);
    }
};

// 6. RECORDING LOGIC
const recorder = {
    mediaRecorder: null,
    chunks: [],
    start: async () => {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        recorder.mediaRecorder = new MediaRecorder(stream);
        recorder.mediaRecorder.ondataavailable = e => recorder.chunks.push(e.data);
        recorder.mediaRecorder.onstop = () => {
            const blob = new Blob(recorder.chunks, { type: 'audio/webm' });
            app.processVoice(blob);
            recorder.chunks = [];
        };
        recorder.mediaRecorder.start();
        document.getElementById('mic-btn').classList.add('recording');
    },
    stop: () => {
        recorder.mediaRecorder.stop();
        document.getElementById('mic-btn').classList.remove('recording');
    }
};

// UI Handlers (Simplified for example)
const ui = {
    switchTab: (tab) => {
        document.querySelectorAll('.tab-content').forEach(t => t.classList.add('hidden'));
        document.getElementById(`tab-${tab}`).classList.remove('hidden');
    },
    appendMsg: (role, text) => {
        const win = document.getElementById('chat-window');
        win.innerHTML += `<div class="msg ${role}"><div class="bubble">${text}</div></div>`;
        win.scrollTop = win.scrollHeight;
    }
};

document.getElementById('login-form').onsubmit = app.handleLogin;
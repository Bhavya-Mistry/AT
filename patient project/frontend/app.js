const API_URL = "http://127.0.0.1:8000";

// === STATE MANAGEMENT ===
const state = {
    user: JSON.parse(localStorage.getItem("user")) || null,
    sessionId: localStorage.getItem("sessionId") || `sess_${Date.now()}`,
    isRecording: false,
    mediaRecorder: null,
    audioChunks: []
};

// === UI CONTROLLER ===
const ui = {
    showToast: (msg) => {
        const t = document.getElementById('toast');
        t.textContent = msg;
        t.classList.remove('hidden');
        setTimeout(() => t.classList.add('hidden'), 3000);
    },

    toggleAuthTab: (tab) => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        event.target.classList.add('active');
        
        if(tab === 'login') {
            document.getElementById('form-login').classList.remove('hidden');
            document.getElementById('form-signup').classList.add('hidden');
        } else {
            document.getElementById('form-login').classList.add('hidden');
            document.getElementById('form-signup').classList.remove('hidden');
        }
    },

    nav: (view) => {
        // Hide all sections
        document.querySelectorAll('.tab-section').forEach(el => el.classList.add('hidden'));
        document.querySelectorAll('.nav-links li').forEach(el => el.classList.remove('active'));

        // Show selected
        document.getElementById(`tab-${view}`).classList.remove('hidden');
        
        // Highlight Sidebar
        const navItem = [...document.querySelectorAll('.nav-links li')].find(li => li.onclick.toString().includes(view));
        if(navItem) navItem.classList.add('active');

        // Load specific data
        if(view === 'files') app.loadFiles(state.user.id, 'gallery-grid');
        if(view === 'profile') app.loadProfile();
        if(view === 'dashboard') app.loadPatients();
    },

    // Info Modals
    showDoc: (type) => {
        const title = document.getElementById('modal-title');
        const content = document.getElementById('modal-content');
        document.getElementById('modal-overlay').classList.remove('hidden');

        if(type === 'privacy') {
            title.innerText = "Privacy Policy";
            content.innerHTML = "<p>We respect your privacy. All your data is encrypted and stored securely...</p>";
        } else {
            title.innerText = "BAA Agreement";
            content.innerHTML = "<p><strong>Business Associate Agreement</strong><br>By checking this box, you agree that we handle PHI in compliance with HIPAA...</p>";
        }
    },
    closeModal: () => document.getElementById('modal-overlay').classList.add('hidden'),

    // Rx Modal
    openRxModal: (sessionId) => {
        document.getElementById('rx-session-id').value = sessionId;
        document.getElementById('modal-rx-overlay').classList.remove('hidden');
    },
    closeRxModal: () => document.getElementById('modal-rx-overlay').classList.add('hidden')
};

// === MAIN LOGIC ===
const app = {
    init: () => {
        if (state.user) {
            app.setupAppLayout();
        } else {
            document.getElementById('view-auth').classList.remove('hidden');
        }
    },

    // --- AUTH ---
    handleLogin: async (e) => {
        e.preventDefault();
        const email = document.getElementById('login-email').value;
        const password = document.getElementById('login-pass').value;

        try {
            const res = await fetch(`${API_URL}/login`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password })
            });

            if (!res.ok) throw new Error("Invalid Credentials");
            
            const user = await res.json();
            app.loginSuccess(user);
        } catch (err) { alert(err.message); }
    },

    handleSignup: async (e) => {
        e.preventDefault();
        const email = document.getElementById('signup-email').value;
        const password = document.getElementById('signup-pass').value;
        
        const privacyAccepted = document.getElementById('check-privacy').checked;
        const baaAccepted = document.getElementById('check-baa').checked; 

        try {
            const res = await fetch(`${API_URL}/users/`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    email, 
                    password,
                    is_policy_accepted: privacyAccepted,
                    has_signed_baa: baaAccepted 
                })
            });

            if (!res.ok) throw new Error("Email likely taken.");
            
            alert("Account created! Please log in.");
            ui.toggleAuthTab('login');
        } catch (err) { alert(err.message); }
    },

    loginSuccess: (user) => {
        state.user = user;
        localStorage.setItem("user", JSON.stringify(user));
        localStorage.setItem("sessionId", state.sessionId); 
        
        document.getElementById('view-auth').classList.add('hidden');
        app.setupAppLayout();
    },

    logout: () => {
        localStorage.clear();
        location.reload();
    },

    setupAppLayout: () => {
    document.getElementById('view-app').classList.remove('hidden');
    document.getElementById('current-user-name').innerText = state.user.email.split('@')[0];
    document.getElementById('current-user-avatar').innerText = state.user.email[0].toUpperCase();

    if (state.user.role === 'patient') {
        document.getElementById('nav-patient').classList.remove('hidden');
        ui.nav('chat');
        app.loadChatHistoryList(); // <--- NEW: Load sidebar
    } else {
        document.getElementById('nav-doctor').classList.remove('hidden');
        ui.nav('dashboard');
    }
    },

    // --- CHAT & VOICE ---
    sendMessage: async (manualText = null) => {
    const input = document.getElementById('chat-input');
    const text = manualText || input.value.trim();
    
    if (!text) return;

    const history = document.getElementById('chat-history');
    history.innerHTML += `<div class="msg user"><div class="bubble">${text}</div></div>`;
    if(!manualText) input.value = ''; 
    history.scrollTop = history.scrollHeight;

    try {
        const res = await fetch(`${API_URL}/chat/`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                user_id: state.user.id,
                session_id: state.sessionId,
                message: text
            })
        });
        const data = await res.json();

        history.innerHTML += `<div class="msg ai"><div class="bubble">${data.response}</div></div>`;
        history.scrollTop = history.scrollHeight;
        
        // REFRESH SIDEBAR (To show the new chat appearing in the list)
        app.loadChatHistoryList(); 

    } catch (err) { console.error(err); }
    },

    // --- PROFILE ---
    loadProfile: async () => {
        const p = state.user.profile || {};
        document.getElementById('p-name').value = p.full_name || "";
        document.getElementById('p-contact').value = p.contact_no || "";
        document.getElementById('p-blood').value = p.blood_group || "";
        document.getElementById('p-address').value = p.address || "";
        if(p.current_status) document.getElementById('p-status').value = p.current_status;
    },

    updateProfile: async (e) => {
        e.preventDefault();
        const profileData = {
            full_name: document.getElementById('p-name').value,
            contact_no: document.getElementById('p-contact').value,
            blood_group: document.getElementById('p-blood').value,
            address: document.getElementById('p-address').value,
            current_status: document.getElementById('p-status').value
        };

        try {
            const res = await fetch(`${API_URL}/users/${state.user.id}/profile/`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(profileData)
            });
            
            if (res.ok) {
                const updatedProfile = await res.json();
                state.user.profile = updatedProfile;
                localStorage.setItem("user", JSON.stringify(state.user));
                
                ui.showToast("Profile Saved");
                const alertBox = document.getElementById('profile-success-alert');
                alertBox.classList.remove('hidden');
                setTimeout(() => alertBox.classList.add('hidden'), 4000);
            }
        } catch (err) { alert("Failed to save profile"); }
    },

loadChatHistoryList: async () => {
    const listContainer = document.getElementById('session-list');
    try {
        const res = await fetch(`${API_URL}/users/${state.user.id}/chats/`);
        const sessions = await res.json();

        listContainer.innerHTML = '';
        
        sessions.forEach(sess => {
            const div = document.createElement('div');
            // If this is the current session, highlight it
            const isActive = sess.session_id === state.sessionId ? 'active' : '';
            div.className = `session-item ${isActive}`;
            
            // Get date or preview text
            const dateStr = new Date(sess.created_at).toLocaleDateString();
            const preview = sess.messages.length > 0 
                ? sess.messages[0].text.substring(0, 20) + "..." 
                : "Empty Chat";

            div.innerHTML = `
                <div class="session-preview">${preview}</div>
                <div class="session-date">${dateStr}</div>
            `;
            
            // When clicked, load that specific chat
            div.onclick = () => app.loadSession(sess);
            
            listContainer.appendChild(div);
        });

    } catch (err) { console.error("History load error", err); }
},

// 3. NEW: Switch to an Old Session
loadSession: (sessionData) => {
    // 1. Update State
    state.sessionId = sessionData.session_id;
    localStorage.setItem("sessionId", state.sessionId);

    // 2. Clear Chat Window
    const historyDiv = document.getElementById('chat-history');
    historyDiv.innerHTML = '';

    // 3. Render Old Messages
    sessionData.messages.forEach(msg => {
        const type = msg.sender === 'patient' ? 'user' : 'ai';
        const bubbleHtml = `<div class="msg ${type}"><div class="bubble">${msg.text}</div></div>`;
        historyDiv.innerHTML += bubbleHtml;
    });

    // 4. Update UI Header
    document.getElementById('chat-title').innerText = "Past Consultation";
    document.getElementById('chat-status').innerText = new Date(sessionData.created_at).toLocaleDateString();
    
    // 5. Refresh sidebar to highlight active
    app.loadChatHistoryList();
    
    // Scroll to bottom
    historyDiv.scrollTop = historyDiv.scrollHeight;
},

// 4. NEW: Start Fresh Chat
startNewChat: () => {
    // Generate new ID
    state.sessionId = `sess_${Date.now()}`;
    localStorage.setItem("sessionId", state.sessionId);

    // Reset UI
    document.getElementById('chat-history').innerHTML = `
        <div class="msg ai">
            <div class="bubble">Hello. I am your Medical AI Assistant. How can I help you today?</div>
        </div>
    `;
    document.getElementById('chat-title').innerText = "New Consultation";
    document.getElementById('chat-status').innerText = "Active";

    // Refresh list (removes active highlight from old chats)
    app.loadChatHistoryList();
},


    // --- FILES ---
    loadFiles: async (userId, elementId) => {
        const grid = document.getElementById(elementId);
        grid.innerHTML = '<p>Loading...</p>';
        
        try {
            const res = await fetch(`${API_URL}/users/${userId}/media/`);
            const files = await res.json();
            grid.innerHTML = '';

            if (files.length === 0) {
                grid.innerHTML = '<p class="text-gray">No files found.</p>';
                return;
            }

            files.forEach(f => {
                let icon = 'fa-file';
                if (f.file_type === 'audio') icon = 'fa-file-audio';
                if (f.file_type === 'image') icon = 'fa-file-image';
                if (f.file_name.endsWith('.pdf')) icon = 'fa-file-pdf';

                const card = document.createElement('div');
                card.className = 'file-card';
                
                card.innerHTML = `
                    <div class="delete-btn-wrapper" title="Delete File">
                        <i class="fa-solid fa-trash text-red-500 delete-icon"></i>
                    </div>
                    <i class="fa-solid ${icon} file-icon"></i>
                    <div class="file-name">${f.file_name}</div>
                    <div class="file-date">${new Date(f.created_at).toLocaleDateString()}</div>
                `;

                card.onclick = (e) => {
                   window.open(f.drive_view_link, '_blank');
                };

                const delBtn = card.querySelector('.delete-btn-wrapper');
                delBtn.onclick = (e) => {
                    e.stopPropagation(); 
                    app.deleteFile(f.id, userId);
                };

                grid.appendChild(card);
            });
        } catch (err) { grid.innerHTML = 'Error loading files.'; }
    },

    deleteFile: async (fileId, userId) => {
        if(!confirm("Are you sure you want to delete this file?")) return;
        
        try {
            const res = await fetch(`${API_URL}/media/${fileId}`, { method: 'DELETE' });
            if(res.ok || res.status === 404) { 
                ui.showToast("File Deleted");
                app.loadFiles(userId, userId === state.user.id ? 'gallery-grid' : 'detail-gallery-grid');
            } else {
                alert("Could not delete file (Backend not ready?)");
            }
        } catch(e) {
            console.log("Delete API missing, hiding from UI for now");
            ui.showToast("File deleted (UI Only)"); 
            app.loadFiles(userId, userId === state.user.id ? 'gallery-grid' : 'detail-gallery-grid');
        }
    },

    uploadFile: async (input) => {
        const file = input.files[0];
        if (!file) return;

        const formData = new FormData();
        formData.append("file", file);
        formData.append("user_id", state.user.id);

        ui.showToast("Uploading...");

        try {
            const res = await fetch(`${API_URL}/media/upload/`, { method: 'POST', body: formData });
            if (res.ok) {
                ui.showToast("Upload Complete");
                app.loadFiles(state.user.id, 'gallery-grid');
            } else { alert("Upload failed"); }
        } catch (err) { alert("Error uploading file"); }
    },

    // --- DOCTOR DASHBOARD ---
    loadPatients: async () => {
        try {
            const res = await fetch(`${API_URL}/patients/`);
            const patients = await res.json();
            
            const tbody = document.getElementById('patient-table-body');
            tbody.innerHTML = '';

            patients.forEach(p => {
                const profile = p.profile || {};
                const name = profile.full_name || p.full_name || p.name || "Unnamed Patient";
                const contact = profile.contact_no || p.contact_no || p.email;
                const status = profile.current_status || p.status || "mild";
                
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${name}</strong></td>
                    <td>${contact}</td>
                    <td><span class="status-badge status-${status}">${status}</span></td>
                    <td><button class="btn btn-outline btn-sm" onclick='app.viewPatientDetail(${JSON.stringify(p)})'>View Records</button></td>
                `;
                tbody.appendChild(tr);
            });
        } catch (err) { console.error(err); }
    },

    viewPatientDetail: (patient) => {
        document.getElementById('tab-dashboard').classList.add('hidden');
        document.getElementById('tab-patient-detail').classList.remove('hidden');

        const p = patient.profile || {};
        
        document.getElementById('detail-name').innerText = p.full_name || patient.full_name || patient.name || "Unnamed Patient";
        document.getElementById('detail-email').innerText = patient.email;
        document.getElementById('detail-contact').innerText = p.contact_no || patient.contact_no || "N/A";
        document.getElementById('detail-address').innerText = p.address || patient.address || "N/A";
        document.getElementById('detail-blood').innerText = p.blood_group || "N/A";
        
        const status = p.current_status || patient.status || "mild";
        const badge = document.getElementById('detail-status');
        badge.innerText = status;
        badge.className = `status-badge status-${status}`;

        app.loadFiles(patient.id, 'detail-gallery-grid');
        app.loadSummaries(patient.id);
    },

    // --- NEW: FETCH AND RENDER SUMMARIES + PRESCRIPTION BUTTON ---
    loadSummaries: async (patientId) => {
        const grid = document.getElementById('summary-grid');
        grid.innerHTML = '<p>Loading reports...</p>';

        try {
            const res = await fetch(`${API_URL}/doctor/patients/${patientId}/summaries`);
            const sessions = await res.json();
            grid.innerHTML = '';

            const reports = sessions.filter(s => s.summary);

            if (reports.length === 0) {
                grid.innerHTML = '<p class="text-gray" style="grid-column: 1/-1;">No AI consultation summaries generated yet.</p>';
                return;
            }

            reports.forEach(session => {
                const data = session.summary;
                const date = new Date(session.created_at || Date.now()).toLocaleDateString();
                
                // EXTRACT PRIORITY SCORE
                const priority = data.priority_score || 0;
                let priorityClass = 'badge-low';
                let priorityLabel = 'Low Priority';
                if(priority > 7) { priorityClass = 'badge-high'; priorityLabel = 'HIGH PRIORITY'; }
                else if(priority > 4) { priorityClass = 'badge-med'; priorityLabel = 'Medium Priority'; }

                const card = document.createElement('div');
                card.className = 'summary-card';
                
                // Header with Date and Priority Badge
                let contentHtml = `
                    <div class="card-header" style="display:flex; justify-content:space-between; align-items:center;">
                        <span>Consultation: ${date}</span>
                        <span class="priority-badge ${priorityClass}">${priorityLabel} (${priority}/10)</span>
                    </div>
                `;
                
                for (const [key, value] of Object.entries(data)) {
                    if(key === 'priority_score') continue; // Don't show score in list again

                    const label = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                    let valueHtml = `<span class="s-value">${value}</span>`;
                    
                    if(key.toLowerCase().includes('status') || key.toLowerCase().includes('severity')) {
                        valueHtml = `<span class="s-value badge-style">${value}</span>`;
                    }

                    contentHtml += `
                        <div class="summary-row">
                            <span class="s-label">${label}:</span>
                            ${valueHtml}
                        </div>
                    `;
                }

                // ADD PRESCRIPTION BUTTON
                contentHtml += `
                    <div style="margin-top: 15px; text-align: right;">
                        <button class="btn btn-primary btn-sm" onclick="ui.openRxModal('${session.session_id}')">
                            <i class="fa-solid fa-file-prescription"></i> Write Prescription
                        </button>
                    </div>
                `;

                card.innerHTML = contentHtml;
                grid.appendChild(card);
            });

        } catch (err) { 
            console.error(err); 
            grid.innerHTML = '<p class="text-gray">Unable to fetch summaries.</p>'; 
        }
    },

    // --- NEW: SUBMIT PRESCRIPTION ---
    submitPrescription: async (e) => {
        e.preventDefault();
        const sessionId = document.getElementById('rx-session-id').value;
        const notes = document.getElementById('rx-notes').value;
        const days = document.getElementById('rx-days').value;

        ui.showToast("Generating PDF & Sending...");

        try {
            const res = await fetch(`${API_URL}/doctor/prescribe/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    doctor_notes: notes,
                    follow_up_days: parseInt(days)
                })
            });

            if (res.ok) {
                ui.closeRxModal();
                ui.showToast("Prescription Sent Successfully!");
                document.getElementById('form-prescription').reset();
                
                // Ideally refresh files to show the new Rx PDF if we are viewing that patient
                // app.loadFiles(patientId... but we don't have patientId handy here easily without state)
                // Just reloading the detail view is safest if we tracked currentPatientId
            } else {
                alert("Failed to send prescription.");
            }
        } catch (err) { alert("Error sending prescription"); console.error(err); }
    }
};

// === AUDIO RECORDER LOGIC ===
const recorder = {
    toggle: async () => {
        if (!state.isRecording) {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                state.mediaRecorder = new MediaRecorder(stream);
                state.audioChunks = [];
                
                state.mediaRecorder.ondataavailable = e => state.audioChunks.push(e.data);
                state.mediaRecorder.onstop = recorder.process;
                
                state.mediaRecorder.start();
                state.isRecording = true;
                document.getElementById('mic-btn').classList.add('recording');
            } catch (e) { alert("Microphone access needed."); }
        } else {
            state.mediaRecorder.stop();
            state.isRecording = false;
            document.getElementById('mic-btn').classList.remove('recording');
        }
    },

    process: async () => {
        const blob = new Blob(state.audioChunks, { type: 'audio/webm' });
        const formData = new FormData();
        formData.append("file", blob, "voice_note.webm");
        formData.append("user_id", state.user.id);

        const input = document.getElementById('chat-input');
        input.placeholder = "Transcribing...";
        input.disabled = true;

        try {
            const res = await fetch(`${API_URL}/transcribe/`, { method: 'POST', body: formData });
            const data = await res.json();
            
            if (data.transcript) {
                input.value = data.transcript;
                input.focus();
            }
        } catch (e) { alert("Transcription failed"); }
        
        input.disabled = false;
        input.placeholder = "Type or dictate...";
    }
};

document.addEventListener('DOMContentLoaded', app.init);
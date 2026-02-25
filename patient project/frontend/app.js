const API_BASE = "http://127.0.0.1:8000";

// --- UTILITIES ---
const ui = {
    show(id) { document.getElementById(id).classList.remove('hidden'); },
    hide(id) { document.getElementById(id).classList.add('hidden'); },
    
    toast(message, type = 'success') {
        const container = document.getElementById('toast-container');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const icon = type === 'success' ? 'ph-check-circle' : 'ph-warning-circle';
        toast.innerHTML = `<i class="ph ${icon}"></i> ${message}`;
        
        container.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    },

    switchAuthTab(tab) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        event.target.classList.add('active');
        if (tab === 'login') {
            this.show('login-form'); this.hide('register-form');
        } else {
            this.hide('login-form'); this.show('register-form');
        }
    },

    setLoading(btnId, isLoading, originalText = '') {
        const btn = document.getElementById(btnId);
        if(!btn) return;
        if (isLoading) {
            btn.disabled = true;
            btn.innerHTML = `<i class="ph ph-spinner ph-spin"></i> Processing...`;
        } else {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
};

// --- APP CORE ---
const app = {
    token: localStorage.getItem("token"),
    role: null,
    sessionId: "sess_" + Date.now() + "_" + Math.random().toString(36).substr(2, 6),

    init() {
        if (this.token) {
            this.decodeTokenAndSetup();
        } else {
            ui.show('auth-view');
        }
    },

    parseJwt(token) {
        try {
            return JSON.parse(atob(token.split('.')[1]));
        } catch (e) { return null; }
    },

    decodeTokenAndSetup() {
        const payload = this.parseJwt(this.token);
        if (!payload) return this.logout();
        
        this.role = payload.role;
        document.getElementById("user-greeting").innerHTML = `<b>${payload.email}</b> <span class="badge">${this.role}</span>`;
        
        ui.hide('auth-view');
        ui.show('navbar');

        if (this.role === "doctor" || this.role === "admin") {
            ui.show('doctor-view');
            this.fetchPatients();
        } else {
            ui.show('patient-view');
            this.fetchMedia();
            this.fetchProfile();
        }
    },

    logout() {
        this.token = null;
        this.role = null;
        localStorage.removeItem("token");
        location.reload();
    },

    async api(endpoint, options = {}) {
        const headers = { ...options.headers };
        if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
        if (!(options.body instanceof FormData) && !headers["Content-Type"]) {
            headers["Content-Type"] = "application/json";
        }

        try {
            const res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Something went wrong");
            return data;
        } catch (err) {
            ui.toast(err.message, 'error');
            throw err;
        }
    },

    // --- AUTH FLOW ---
    async handleLogin(e) {
        e.preventDefault();
        ui.setLoading('login-btn', true);
        const formData = new URLSearchParams();
        formData.append("username", document.getElementById("login-email").value);
        formData.append("password", document.getElementById("login-password").value);

        try {
            const res = await this.api("/login", {
                method: "POST",
                headers: { "Content-Type": "application/x-www-form-urlencoded" },
                body: formData.toString()
            });
            this.token = res.access_token;
            localStorage.setItem("token", this.token);
            ui.toast("Welcome back!");
            this.decodeTokenAndSetup();
        } catch (e) {} finally {
            ui.setLoading('login-btn', false, 'Sign In');
        }
    },

    async handleRegister(e) {
        e.preventDefault();
        ui.setLoading('reg-btn', true);
        const email = document.getElementById("reg-email").value;
        const password = document.getElementById("reg-password").value;

        try {
            await this.api("/users/", {
                method: "POST",
                body: JSON.stringify({ email, password, is_policy_accepted: true, has_signed_baa: true })
            });
            ui.toast("Account created! Please log in.");
            ui.switchAuthTab('login');
        } catch (e) {} finally {
            ui.setLoading('reg-btn', false, 'Create Account');
        }
    },

    // --- PATIENT FLOW ---
    async fetchProfile() {
        try {
            // Fails silently if profile doesn't exist yet
            const profile = await this.api("/users/me/profile/").catch(()=>null); 
            if(profile) {
                document.getElementById('prof-name').value = profile.full_name || '';
                document.getElementById('prof-contact').value = profile.contact_no || '';
                document.getElementById('prof-blood').value = profile.blood_group || '';
                document.getElementById('prof-status').value = profile.current_status || 'mild';
                document.getElementById('prof-address').value = profile.address || '';
            }
        } catch(e) {}
    },

    async updateProfile(e) {
        e.preventDefault();
        const payload = {
            full_name: document.getElementById("prof-name").value,
            contact_no: document.getElementById("prof-contact").value,
            address: document.getElementById("prof-address").value,
            blood_group: document.getElementById("prof-blood").value,
            current_status: document.getElementById("prof-status").value
        };
        try {
            await this.api("/users/me/profile/", { method: "POST", body: JSON.stringify(payload) });
            ui.toast("Profile updated successfully");
        } catch (e) {}
    },

    // Chat
    appendChat(role, text) {
        const box = document.getElementById("chat-box");
        const div = document.createElement("div");
        div.className = `msg ${role}`;
        
        // Convert URLs to clickable links if present
        const urlRegex = /(https?:\/\/[^\s]+)/g;
        const formattedText = text.replace(urlRegex, function(url) {
            return `<a href="${url}" target="_blank" class="msg-link">View File</a>`;
        });
        
        div.innerHTML = formattedText;
        box.appendChild(div);
        box.scrollTop = box.scrollHeight;
    },

    async sendChatMessage(e) {
        e.preventDefault();
        const input = document.getElementById("chat-input");
        const msg = input.value.trim();
        if(!msg) return;
        
        input.value = "";
        this.appendChat("patient", msg);

        // Add a temporary loading indicator
        const loadingId = 'loading-' + Date.now();
        const box = document.getElementById("chat-box");
        box.insertAdjacentHTML('beforeend', `<div id="${loadingId}" class="msg ai"><i class="ph ph-dots-three ph-bounce"></i> Thinking...</div>`);
        box.scrollTop = box.scrollHeight;

        try {
            const res = await this.api("/chat/", {
                method: "POST",
                body: JSON.stringify({ user_id: 0, session_id: this.sessionId, message: msg })
            });
            document.getElementById(loadingId).remove();
            this.appendChat("ai", res.response);
        } catch (e) {
            document.getElementById(loadingId).remove();
            this.appendChat("system", "Failed to connect to AI. Please try again.");
        }
    },

    async uploadChatFile() {
        const fileInput = document.getElementById("chat-file");
        if (!fileInput.files[0]) return;

        const formData = new FormData();
        formData.append("file", fileInput.files[0]);
        formData.append("session_id", this.sessionId);

        this.appendChat("system", `Uploading ${fileInput.files[0].name}...`);

        try {
            await this.api("/chat/upload", { method: "POST", body: formData });
            this.appendChat("system", "File upload processing in background. AI will review it shortly.");
            setTimeout(() => this.fetchMedia(), 2000); // refresh media list
        } catch (e) {}
        fileInput.value = "";
    },

    // Media
    async uploadMedia(inputId, endpoint) {
        const fileInput = document.getElementById(inputId);
        if (!fileInput.files[0]) return;

        const formData = new FormData();
        formData.append("file", fileInput.files[0]);

        ui.toast("Upload started...", "success");
        try {
            const res = await this.api(endpoint, { method: "POST", body: formData });
            ui.toast(res.message || "Upload initiated!");
            setTimeout(() => this.fetchMedia(), 2000);
        } catch (e) {}
        fileInput.value = "";
    },

    async fetchMedia() {
        try {
            const media = await this.api("/users/me/media/");
            const list = document.getElementById("media-list");
            
            if(media.length === 0) {
                list.innerHTML = `<div class="empty-state"><p>No records uploaded yet.</p></div>`;
                return;
            }

            list.innerHTML = media.map(m => `
                <div class="list-item">
                    <div class="list-item-content">
                        <h4><i class="ph ph-file-text"></i> ${m.file_name}</h4>
                        <p>${m.transcript || 'Processing...'}</p>
                    </div>
                    <div class="list-item-actions flex">
                        ${m.drive_view_link ? `<a href="${m.drive_view_link}" target="_blank" class="icon-btn" title="View"><i class="ph ph-eye"></i></a>` : ''}
                        <button class="icon-btn" onclick="app.deleteMedia(${m.id})" title="Delete"><i class="ph ph-trash text-danger"></i></button>
                    </div>
                </div>
            `).join("");
        } catch (e) {}
    },

    async deleteMedia(id) {
        if(!confirm("Delete this record?")) return;
        try {
            await this.api(`/media/${id}`, { method: "DELETE" });
            ui.toast("File deleted.");
            this.fetchMedia();
        } catch (e) {}
    },

    // --- DOCTOR FLOW ---
    async fetchPatients() {
        try {
            const patients = await this.api("/doctor/patients/");
            const list = document.getElementById("patient-list");
            
            if(patients.length === 0) {
                list.innerHTML = `<div class="empty-state"><p>No patients registered.</p></div>`;
                return;
            }

            list.innerHTML = patients.map(p => `
                <div class="list-item" style="cursor:pointer;" onclick="app.fetchSummaries(${p.id}, '${p.profile?.full_name || p.email}')">
                    <div class="list-item-content">
                        <h4>${p.profile?.full_name || 'Un-profiled Patient'}</h4>
                        <p>${p.email}</p>
                    </div>
                    <div class="list-item-actions">
                        <i class="ph ph-caret-right text-muted"></i>
                    </div>
                </div>
            `).join("");
        } catch (e) {}
    },

    async fetchSummaries(patientId, patientName) {
        try {
            const sessions = await this.api(`/doctor/patients/${patientId}/summaries`);
            const area = document.getElementById("doc-action-area");
            
            if (sessions.length === 0) {
                area.innerHTML = `
                    <div class="card-header"><h3><i class="ph ph-activity"></i> ${patientName}</h3></div>
                    <div class="empty-state"><p>No triage sessions found for this patient.</p></div>`;
                return;
            }

            let html = `<div class="card-header"><h3><i class="ph ph-activity"></i> Triage Summaries: ${patientName}</h3></div>`;
            
            sessions.forEach(s => {
                const priority = s.summary?.priority_score || 'N/A';
                const color = priority > 7 ? 'danger' : (priority > 4 ? 'warning' : 'success');
                
                html += `
                <div class="card" style="box-shadow:none; background:var(--bg-color);">
                    <div class="flex justify-between items-center" style="margin-bottom:10px;">
                        <strong>Session: ${s.session_id.substring(0,14)}...</strong>
                        <span class="badge" style="background:var(--${color}); color:white;">Priority: ${priority}</span>
                    </div>
                    <div style="font-size:0.875rem; margin-bottom:1rem;">
                        ${s.summary ? 
                            `<p><strong>Complaint:</strong> ${s.summary.chief_complaint}</p>
                             <p><strong>Note:</strong> ${s.summary.summary_note}</p>` 
                            : '<p class="text-muted">No summary generated by AI yet.</p>'}
                    </div>
                    <button class="btn btn-primary btn-sm" onclick="app.renderPrescriptionForm('${s.session_id}')">
                        <i class="ph ph-prescription"></i> Write Prescription
                    </button>
                    
                    <div id="rx-form-${s.session_id}" class="hidden" style="margin-top:15px; padding-top:15px; border-top:1px solid var(--border);">
                        <form onsubmit="app.submitPrescription(event, '${s.session_id}')">
                            <textarea id="notes-${s.session_id}" class="input" placeholder="Doctor's orders, medications, etc..." rows="3" required></textarea>
                            <div class="flex gap-2">
                                <input type="number" id="follow-${s.session_id}" class="input" placeholder="Follow-up days" value="3" required style="width:150px;">
                                <button type="submit" class="btn btn-secondary w-full" id="btn-${s.session_id}">Send to Patient</button>
                            </div>
                        </form>
                    </div>
                </div>`;
            });
            area.innerHTML = html;
        } catch (e) {}
    },

    renderPrescriptionForm(sessionId) {
        ui.show(`rx-form-${sessionId}`);
    },

    async submitPrescription(e, sessionId) {
        e.preventDefault();
        ui.setLoading(`btn-${sessionId}`, true);
        
        const payload = {
            session_id: sessionId,
            doctor_notes: document.getElementById(`notes-${sessionId}`).value,
            follow_up_days: parseInt(document.getElementById(`follow-${sessionId}`).value)
        };

        try {
            const res = await this.api("/doctor/prescribe/", { method: "POST", body: JSON.stringify(payload) });
            ui.toast("Prescription Issued Successfully!");
            ui.hide(`rx-form-${sessionId}`);
        } catch (e) {} finally {
            ui.setLoading(`btn-${sessionId}`, false, 'Send to Patient');
        }
    }
};

// Initialize app
app.init();
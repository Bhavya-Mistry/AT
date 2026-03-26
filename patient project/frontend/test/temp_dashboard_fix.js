// // ═══════════════════════════════════════
// // DASHBOARD
// // ═══════════════════════════════════════
// async function loadDashboard() {
//   if (isDoctor()) {
//     await loadDoctorDashboard();
//   } else {
//     await loadPatientDashboard();
//   }
// }

// async function loadPatientDashboard() {
//   try {
//     const [sessRes, filesRes] = await Promise.allSettled([
//       api("/users/me/chats/", { _abortKey: "dash-chats" }),
//       api("/users/me/media/", { _abortKey: "dash-media" }),
//     ]);
//     if (sessRes.status === "fulfilled" && sessRes.value.ok) state.sessions = await sessRes.value.json();
//     if (filesRes.status === "fulfilled" && filesRes.value.ok) state.files = await filesRes.value.json();

//     // Session count
//     $("#statPatientSessions").text(state.sessions.length);

//     // File count
//     $("#statPatientFiles").text(state.files.length);

//     // Count prescriptions (files that start with "Rx:")
//     const rxCount = state.files.filter((f) =>
//       f.file_name?.startsWith("Rx:") || f.file_type === "pdf"
//     ).length;
//     $("#statPatientRx").text(rxCount || "\u2014");

//     // Latest priority score (from most recent session with a score)
//     const withScore = state.sessions.filter((s) => s.summary?.priority_score);
//     if (withScore.length) {
//       // Sort by date, get most recent
//       const sorted = withScore.sort((a, b) =>
//         new Date(b.created_at || 0) - new Date(a.created_at || 0)
//       );
//       const latest = sorted[0].summary.priority_score;
//       $("#statPatientPriority").text(latest);
//     } else {
//       $("#statPatientPriority").text("\u2014");
//     }

//     renderRecentChats(state.sessions.slice(0, 4));
//     renderRecentFiles(state.files.slice(0, 4));
//   } catch (err) {
//     if (err.name !== "AbortError") console.error(err);
//   }
// }

// async function loadDoctorDashboard() {
//   try {
//     const res = await api("/doctor/patients/", { _abortKey: "doc-dash" });
//     if (!res.ok) return;
//     state.patients = await res.json();

//     // Patient count
//     $("#statDocPatients").text(state.patients.length);

//     // Show patients badge in sidebar
//     const badge = $("#patientsBadge");
//     if (state.patients.length) {
//       badge.text(state.patients.length);
//       badge.style.display = "";
//     }

//     // 1. FETCH SUMMARIES AND APPOINTMENTS IN PARALLEL
//     const summaryPromises = state.patients.map((p) =>
//       apiJSON(`/doctor/patients/${p.id}/summaries`).catch(() => [])
//     );
//     const apptPromise = apiJSON("/appointments/doctor").catch(() => []);

//     const [allSummaries, appts] = await Promise.all([
//       Promise.all(summaryPromises),
//       apptPromise
//     ]);

//     // 2. SORT APPOINTMENTS BY DATE/TIME
//     const now = Date.now();
//     appts.sort((a, b) => {
//       const timeA = new Date(a.scheduled_time || a.appointment_date).getTime();
//       const timeB = new Date(b.scheduled_time || b.appointment_date).getTime();

//       const statusA = String(a.status?.value || a.status || 'scheduled').toLowerCase();
//       const statusB = String(b.status?.value || b.status || 'scheduled').toLowerCase();

//       // Helper to assign a sorting rank
//       const getRank = (time, status) => {
//         if (status === 'cancelled') return 3; // Cancelled goes to the very bottom
//         if (time < now) return 2;             // Past/Completed goes to the middle
//         return 1;                             // Active/Upcoming stays at the top
//       };

//       const rankA = getRank(timeA, statusA);
//       const rankB = getRank(timeB, statusB);

//       // 1. Sort by Rank first
//       if (rankA !== rankB) {
//         return rankA - rankB;
//       }

//       // 2. If they have the exact same rank, sort by time
//       if (rankA === 1) {
//         return timeA - timeB; // Upcoming: Closest date first (Ascending)
//       } else {
//         return timeB - timeA; // Past/Cancelled: Most recent first (Descending)
//       }
//     });

//     // Cache for later use
//     state.patients.forEach((p, i) => {
//       state.patientSummariesCache[p.id] = allSummaries[i];
//     });

//     // Aggregate stats
//     let totalSessions = 0;
//     let totalPriority = 0;
//     let priorityCount = 0;
//     let pendingCount = 0;
//     let highPriorityPatients = [];

//     allSummaries.forEach((sessions, idx) => {
//       const patient = state.patients[idx];
//       // Only count triage_summary type items (not file records)
//       const triageSessions = sessions.filter((s) => s.type === "triage_summary");
//       totalSessions += triageSessions.length;

//       let patientMaxPriority = 0;

//       triageSessions.forEach((s) => {
//         const score = s.priority_score || s.content?.priority_score;
//         if (score) {
//           totalPriority += score;
//           priorityCount++;
//           if (score > patientMaxPriority) patientMaxPriority = score;
//         }
//         // Count as pending if no reviewed flag in content
//         if (!s.content?.reviewed) {
//           pendingCount++;
//         }
//       });

//       if (patientMaxPriority > 0) {
//         highPriorityPatients.push({
//           ...patient,
//           maxPriority: patientMaxPriority,
//           sessionCount: triageSessions.length,
//         });
//       }
//     });

//     // 3. CALCULATE TODAY'S APPOINTMENTS
//     const currentDate = new Date();
//     const todayYear = currentDate.getFullYear();
//     const todayMonth = currentDate.getMonth();
//     const todayDate = currentDate.getDate();

//     const todayCount = appts.filter(a => {
//       const dt = a.scheduled_time || a.appointment_date;
//       if (!dt) return false;

//       const d = new Date(dt);
//       // Skip if the database sent an invalid date string
//       if (isNaN(d.getTime())) return false;

//       // Explicitly compare Year, Month, and Day integers 
//       const isSameDay = d.getFullYear() === todayYear &&
//         d.getMonth() === todayMonth &&
//         d.getDate() === todayDate;

//       // Force lowercase to catch 'Scheduled', 'SCHEDULED', etc.
//       const statusVal = String(a.status?.value || a.status || 'scheduled').toLowerCase();

//       // Count it if it's today AND it hasn't been cancelled
//       return isSameDay && statusVal !== "cancelled";
//     }).length;

//     console.log("🔍 DEBUG: Today's appointments count:", todayCount);
//     console.log("🔍 DEBUG: Total appointments:", appts.length);
//     console.log("🔍 DEBUG: Appointments:", appts.map(a => ({
//       time: a.scheduled_time,
//       status: a.status,
//       isToday: new Date(a.scheduled_time).toDateString() === currentDate.toDateString()
//     })));

//     // Update doctor stat cards
//     $("#statDocSessions").text(totalSessions || "\u2014");
//     $("#statDocPending").text(pendingCount || "0");
//     $("#statDocAppointments").text(todayCount || "0");
//     $("#statDocPriority").text(priorityCount
//       ? (totalPriority / priorityCount).toFixed(1)
//       : "\u2014");
    
//     console.log("🔍 DEBUG: UI Updated - statDocAppointments now shows:", $("#statDocAppointments").text());

//     // Render patients sorted by priority
//     highPriorityPatients.sort((a, b) => b.maxPriority - a.maxPriority);
//     renderDoctorRecentPatients(
//       highPriorityPatients.length
//         ? highPriorityPatients.slice(0, 5)
//         : state.patients.slice(0, 5)
//     );
//     renderDoctorRecentActivity(allSummaries);

//   } catch (err) {
//     if (err.name !== "AbortError") console.error("Doctor dashboard error:", err);
//   }
// }

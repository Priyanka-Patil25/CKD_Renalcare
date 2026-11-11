document.addEventListener("DOMContentLoaded", async () => {
  const me = Api.requireRole("doctor");
  if (!me) return;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cls = (r) => (r || "").replace(" ", "-");
  const withBusy = async (button, label, action) => {
    const original = button.innerHTML;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = label;
    try { return await action(); }
    finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
      button.innerHTML = original;
    }
  };
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const fd = (iso) => { if (!iso) return "—"; const [y, m, d] = iso.split("-"); return `${+d} ${MON[+m - 1]} ${y}`; };
  const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);

  $("#who").innerHTML = esc(me.name) + " · Nephrology";
  const h = new Date().getHours();
  $("#greeting").textContent = `${h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"}, ${me.name}`;
  $("#logout").addEventListener("click", (e) => { e.preventDefault(); Api.logout(); });

  const queueView = $("#queue-view"), reviewView = $("#review-view");
  let cur = null;           // {p, visitId}
  let grid = null, modelInfo = null;

  // ---------------- queue ----------------
  let queueRows = [];
  async function renderQueue() {
    const queue = $("#doctor-queue");
    const status = $("#queue-status");
    queue.setAttribute("aria-busy", "true");
    status.textContent = "";
    status.classList.remove("error");
    try {
      const response = await Api.getQueue();
      queueRows = Array.isArray(response) ? response : [];
      queue.innerHTML = queueRows.map((p) => {
        const noLabs = p.stage === "Not enough results";
        const visit = p.visit_id == null ? "" : esc(p.visit_id);
        return `<div class="patient-row doctor-patient-row">
          <div><strong>${esc(p.token)} · ${esc(p.name)}</strong><br><small class="muted">${esc(p.id)} · ${esc(p.age ?? "—")} years · ${esc(p.reason || "")} · ${esc(String(p.status || "unknown").replace("_", " "))}</small>
          <div class="q-chips">
            ${noLabs ? '<span class="chip info">No kidney labs yet</span>' : `<span class="chip">${esc(p.stage || "Stage unavailable")}</span><span class="chip ${esc(cls(p.risk))}">${esc(p.risk || "risk n/a")} risk</span>`}
            ${p.flags_open ? `<span class="chip ${p.flags_high ? "very-high" : "medium"}">${esc(p.flags_open)} alert${p.flags_open > 1 ? "s" : ""}</span>` : ""}
            ${p.is_follow_up ? '<span class="chip info">follow-up</span>' : '<span class="chip info">new</span>'}
          </div></div>
          <button class="button secondary" type="button" data-open="${esc(p.id)}" data-visit="${visit}">Open patient <span aria-hidden="true">→</span></button></div>`;
      }).join("") || '<p class="empty">No patients in the queue today.</p>';
      queue.querySelectorAll("[data-open]").forEach((button) => button.addEventListener("click", async () => {
        button.disabled = true;
        button.setAttribute("aria-busy", "true");
        try { await openPatient(button.dataset.open, Number(button.dataset.visit) || null); }
        catch (error) {
          status.textContent = error?.message || "Could not open this patient. Please try again.";
          status.classList.add("error");
        } finally {
          button.disabled = false;
          button.removeAttribute("aria-busy");
        }
      }));
    } catch (error) {
      queueRows = [];
      queue.innerHTML = '<p class="empty">The queue could not be loaded.</p>';
      status.textContent = error?.message || "Could not load the queue. Please try again.";
      status.classList.add("error");
    } finally {
      queue.setAttribute("aria-busy", "false");
    }
  }

  // ---------------- charts (plain SVG) ----------------
  function lineChart(el, pts, o = {}) {
    pts = (pts || []).filter((p) => p.value != null);
    if (!pts.length) { el.innerHTML = '<p class="muted" style="margin:6px 0">No results yet.</p>'; return; }
    const W = o.w || 560, H = o.h || 170, L = 34, R = 12, T = 10, B = 22;
    const t = pts.map((p) => new Date(p.date).getTime());
    const t0 = Math.min(...t), t1 = Math.max(...t, t0 + 86400000 * 30);
    const vals = pts.map((p) => p.value).concat((o.refs || []).map((r) => r.y));
    let lo = o.min ?? Math.min(...vals), hi = o.max ?? Math.max(...vals);
    const pad = (hi - lo) * 0.1 || 5; lo = o.min ?? lo - pad; hi = o.max ?? hi + pad;
    const X = (v) => L + ((v - t0) / (t1 - t0)) * (W - L - R), Y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    const refs = (o.refs || []).map((r) => `<line x1="${L}" x2="${W - R}" y1="${Y(r.y)}" y2="${Y(r.y)}" stroke="#d4dfde" stroke-dasharray="4 4"/><text x="${L - 4}" y="${Y(r.y) + 3}" font-size="9" fill="#71838a" text-anchor="end">${r.label ?? r.y}</text>`).join("");
    const line = pts.map((p, i) => `${i ? "L" : "M"}${X(new Date(p.date).getTime()).toFixed(1)},${Y(p.value).toFixed(1)}`).join(" ");
    const dots = pts.map((p) => `<circle cx="${X(new Date(p.date).getTime()).toFixed(1)}" cy="${Y(p.value).toFixed(1)}" r="4" fill="${o.color || "#16877c"}"><title>${fd(p.date)}: ${p.value}</title></circle>`).join("");
    const last = pts[pts.length - 1];
    el.classList.add("chart");
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="trend chart">${refs}
      <path d="${line}" fill="none" stroke="${o.color || "#16877c"}" stroke-width="2.5"/>${dots}
      <text x="${X(new Date(last.date).getTime()) - 4}" y="${Y(last.value) - 9}" font-size="11" font-weight="700" text-anchor="end" fill="#173642">${last.value}</text>
      <text x="${L}" y="${H - 5}" font-size="9" fill="#71838a">${fd(pts[0].date)}</text>
      <text x="${W - R}" y="${H - 5}" font-size="9" fill="#71838a" text-anchor="end">${fd(last.date)}</text></svg>`;
  }

  // ---------------- KDIGO grid ----------------
  function renderGrid(k) {
    if (!grid || !Array.isArray(grid.rows) || !Array.isArray(grid.cols) || !grid.risk) {
      $("#kdigo-grid").innerHTML = '<p class="muted">The KDIGO grid is unavailable right now. Existing measured results remain available below.</p>';
      $("#kdigo-note").textContent = "No classification grid was returned by the existing service. Do not interpret this as a risk category.";
      return;
    }
    const here = (g, a) => k.g === g && k.a === a;
    const rows = grid.rows.map((g) => `<tr><th class="rowh">${g} <small>${esc(grid.g_labels[g].match(/\(.*\)/)?.[0] || "")}</small></th>${grid.cols.map((a) =>
      `<td class="${cls(grid.risk[g][a])} ${here(g, a) ? "here" : ""}" title="${g} ${a}: ${grid.risk[g][a]} risk">${esc(grid.risk[g][a])}</td>`).join("")}</tr>`).join("");
    $("#kdigo-grid").innerHTML = `<table class="kgrid"><thead><tr><th class="rowh">eGFR ↓ · uACR →</th>${grid.cols.map((a) => `<th>${a}<br><small>${esc(grid.a_labels[a].match(/\(.*\)/)?.[0] || "")}</small></th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>
      <div class="legend"><span><i style="background:#cfe9d6"></i>low</span><span><i style="background:#fbeea8"></i>moderate</span><span><i style="background:#fcd3a6"></i>high</span><span><i style="background:#f3b1ab"></i>very high</span></div>`;
    let note;
    if (k.g && !k.a) note = `eGFR ${k.egfr} puts this patient in ${k.g}. uACR is missing, so the column cannot be placed${k.g === "G4" || k.g === "G5" ? " (G4 and G5 are always very high risk)" : ""}. Order a urine ACR.`;
    else if (!k.g) note = "No eGFR or uACR on record, so the grid cannot be placed. Use the screening model below or order the tests.";
    else note = `${k.g} ${k.a}: ${k.g_label.toLowerCase()}, ${k.a_label.toLowerCase()}. Risk: ${k.risk}. KDIGO suggests checking about every ${k.monitor_months} months. ${k.ckd_range ? "" : "Neither value is in the CKD range."} Confirm abnormal results persist for more than 3 months.`;
    $("#kdigo-note").textContent = note;
  }

  // ---------------- flags ----------------
  function renderFlags(flags) {
    const open = flags.filter((f) => f.status === "pending").length;
    $("#flag-count").textContent = open ? `${open} to review` : "all reviewed";
    $("#flags").innerHTML = flags.map((f, i) => {
      const done = f.status !== "pending";
      return `<div class="flag ${esc(f.level)} ${done ? "done" : ""}" data-i="${i}">
        <h4><span>${esc(f.title)}</span><span class="chip ${esc(f.level)}">${esc(f.level)}</span></h4>
        <p>${esc(f.edited_text || f.detail)}</p><small>Source: ${esc(f.source)}</small>
        ${done ? `<div class="acts"><span class="chip">${esc(f.status)}</span><button class="button secondary" data-act="undo">Undo</button></div>`
               : `<div class="acts"><button class="button primary" data-act="accepted">Accept</button><button class="button secondary" data-act="edit">Edit</button><button class="button secondary" data-act="dismissed">Dismiss</button></div>`}
        <div class="edit-box"></div></div>`;
    }).join("") || '<p class="muted" style="margin:0">No care gaps found for this patient.</p>';
    $("#flags").querySelectorAll(".flag").forEach((el) => {
      const f = flags[+el.dataset.i];
      el.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", async () => {
        const act = b.dataset.act;
        if (act === "edit") {
          el.querySelector(".edit-box").innerHTML = `<label class="sr-only">Edited care-gap text<textarea aria-label="Edited care-gap text">${esc(f.edited_text || f.detail)}</textarea></label><div class="acts"><button class="button primary" type="button" data-save>Save edit</button></div>`;
          el.querySelector("[data-save]").addEventListener("click", async (saveEvent) => {
            const saveButton = saveEvent.currentTarget;
            const editedText = el.querySelector("textarea").value;
            try {
              await withBusy(saveButton, "Saving…", () => Api.decideFlag(f.id, "edited", editedText));
              f.status = "edited"; f.edited_text = editedText; renderFlags(flags);
              $("#save-status").textContent = "Care-gap edit saved for clinician review.";
            } catch (error) { $("#save-status").textContent = error?.message || "Care-gap edit could not be saved."; }
          });
          return;
        }
        const status = act === "undo" ? "pending" : act;
        try {
          await withBusy(b, status === "pending" ? "Restoring…" : "Saving…", () => Api.decideFlag(f.id, status, null));
          f.status = status; if (status === "pending") f.edited_text = null; renderFlags(flags);
          $("#save-status").textContent = "Care-gap decision saved.";
        } catch (error) { $("#save-status").textContent = error?.message || "Care-gap decision could not be saved."; }
      }));
    });
  }

  // ---------------- screening ----------------
  function renderScreening(s) {
    const form = $("#screen-form");
    if (!s || !s.inputs) {
      $("#screen-banner").hidden = true;
      $("#screen-result").innerHTML = '<p class="muted">No screening result is available for this patient.</p>';
      return;
    }
    for (const [k, v] of Object.entries(s.inputs)) if (form.elements[k] && v != null) form.elements[k].value = v;
    const b = $("#screen-banner"); b.hidden = false;
    b.textContent = s.applicable
      ? "This patient has no eGFR or uACR on record, so the screening model applies. It only suggests whether to test."
      : "This patient already has kidney results, so the KDIGO stage above is the answer. The screening model is shown for testing only.";
    showScreen(s.result);
  }
  function showScreen(r) {
    const el = $("#screen-result");
    if (!r) { el.innerHTML = ""; return; }
    const label = { low: "Low", watch: "Watch", high: "High" }[r.level];
    el.innerHTML = `<div class="risk-big ${r.level}"><div><span class="muted" style="margin:0">Screening level</span><br><strong>${label}</strong></div><div style="max-width:60%;font-size:12.5px">${esc(r.message)}</div></div>
      ${r.missing_inputs.length ? `<div class="notice">Not filled in (the model used typical values): ${esc(r.missing_inputs.join(", "))}.</div>` : ""}
      ${r.warnings.map((w) => `<div class="notice">${esc(w)}</div>`).join("")}
      <h3 style="margin-top:14px">What pushed the score</h3>
      ${r.explanation.slice(0, 6).map((e) => `<div class="feature"><strong>${esc(e.feature)}</strong><div class="bar"><i class="${e.value > 0 ? "up" : "down"}" style="width:${Math.max(4, e.share)}%"></i></div><b>${e.value > 0 ? "+" : ""}${e.value.toFixed(2)}</b></div>`).join("")}
      <div class="notice">${esc(r.disclaimer)} Red bars raise the score, green lower it (SHAP). Model ${esc(r.model_version)}${modelInfo ? `: AUC ${modelInfo.test_auc} on a held-out NHANES test set; at the watch line it catches ${Math.round(modelInfo.at_watch_line.recall * 100)}% of CKD cases but about ${Math.round((1 - modelInfo.at_watch_line.precision) * 100)}% of flagged people do not have CKD` : ""}.</div>`;
  }

  // ---------------- one patient ----------------
  function render(p) {
    cur.p = p;
    const k = p.kdigo || {};
    const conditions = p.conditions || {};
    const series = p.series || {};
    const labs = Array.isArray(p.labs) ? p.labs : [];
    const medicines = Array.isArray(p.medicines) ? p.medicines : [];
    const visits = Array.isArray(p.visits) ? p.visits : [];
    const notes = Array.isArray(p.notes) ? p.notes : [];
    $("#patient-name").textContent = p.name;
    $("#patient-meta").textContent = `${p.id} · ${p.age ?? "?"} years · ${{ M: "Male", F: "Female" }[p.sex] || "Not specified"} · ` +
      Object.entries(conditions).filter(([, v]) => v).map(([n]) => n.replace(/_/g, " ")).join(", ");
    $("#syn-badge").textContent = p.is_synthetic ? "Synthetic demo patient" : "Clinical review";
    const slope = k.egfr_slope;
    $("#summary").innerHTML = `
      <div class="sum risk-${cls(k.risk)}"><span>KDIGO stage</span><strong>${esc(k.stage_text)}</strong><small>${k.risk ? esc(k.risk) + " risk" : "cannot grade yet"}</small></div>
      <div class="sum"><span>eGFR</span><strong>${esc(k.egfr ?? "—")}</strong><small>${fd(k.egfr_date)}</small></div>
      <div class="sum"><span>uACR (mg/g)</span><strong>${esc(k.uacr ?? "—")}</strong><small>${fd(k.uacr_date)}</small></div>
      <div class="sum"><span>eGFR trend / year</span><strong style="color:${slope != null && slope < -5 ? "#a3302a" : "inherit"}">${slope != null ? (slope > 0 ? "+" : "") + slope : "—"}</strong><small>${slope == null ? "needs 3 results over 6 months" : slope < -5 ? "rapid decline" : "within normal range of change"}</small></div>
      <div class="sum"><span>Next tests due</span><strong>${k.monitor_months ? "every " + k.monitor_months + " mo" : "—"}</strong><small>${k.monitor_months ? (12 / k.monitor_months).toFixed(k.monitor_months === 12 ? 0 : 1).replace(".0", "") + " per year · KDIGO Figure 13" : "by KDIGO risk"}</small></div>`;
    renderGrid(k);
    $("#labs").innerHTML = labs.map((lab) => `<div class="lab-row"><span>${esc(String(lab.code || "").toUpperCase())}</span><strong>${esc(lab.value)} ${esc(lab.unit)}</strong><small class="muted">${fd(lab.date)}</small></div>`).join("") || '<p class="muted">No laboratory results on record.</p>';
    lineChart($("#chart-egfr"), series.egfr, { refs: [{ y: 60 }, { y: 45 }, { y: 30 }, { y: 15 }] });
    lineChart($("#chart-uacr"), series.uacr, { refs: [{ y: 30 }, { y: 300 }], h: 150, color: "#b77b25", min: 0 });
    lineChart($("#chart-sbp"), series.sbp, { refs: [{ y: 140 }, { y: 120 }], h: 150, color: "#3d7198" });
    $("#meds").innerHTML = medicines.length ? medicines.map((medicine) => `<span class="chip ${medicine.drug_class === "NSAID" ? "high" : ""}">${esc(medicine.drug)}</span> `).join("") : '<p class="muted" style="margin:0">No medicines recorded.</p>';
    $("#visits").innerHTML = visits.map((visit) => `<p class="muted" style="margin:8px 0">${fd(visit.visit_date)} · visit ${esc(visit.visit_no)} · ${esc(visit.reason || "")}${visit.doctor_stage ? " · doctor stage: " + esc(visit.doctor_stage) : ""}</p>`).join("") +
      (notes.length ? '<h3 style="margin-top:14px">Earlier notes</h3>' + notes.map((note) => `<p style="margin:8px 0"><small class="muted">${fd(note.visit_date)}</small><br>${esc(note.body)}</p>`).join("") : "");
    renderFlags(Array.isArray(p.flags) ? p.flags : []);
    renderScreening(p.screening);
    const rf = $("#results-form"); rf.reset(); rf.elements.date.value = today();
    rf.elements.medicines.value = medicines.map((medicine) => medicine.drug).join(", ");
  }

  async function openPatient(id, visitId) {
    const p = await Api.getPatient(id);
    cur = { p, visitId };
    queueView.hidden = true; reviewView.hidden = false;
    $("#notes").value = ""; $("#save-status").textContent = ""; $("#results-status").textContent = "";
    $("#rag-answer").innerHTML = '<p class="muted" style="margin:14px 0 0">Nothing asked yet.</p>'; $("#rag-question").value = ""; $("#rag-mode").textContent = "";
    $("#agent-out").innerHTML = '<p class="muted" style="margin:10px 0 0">No briefing yet. The agent only reads; it never changes the record.</p>'; $("#agent-brain").textContent = "not run yet";
    $("#lab-out").innerHTML = ""; $("#lab-text").value = ""; $("#lab-count").textContent = "";
    render(p);
    renderPipeline(null);
    Api.lastPipeline(id).then((r) => { if (cur && cur.p === p) renderPipeline(r); }).catch(() => {});
    if (visitId) {
      Api.startVisit(visitId).catch((error) => {
        $("#save-status").textContent = `Visit could not be marked as started: ${error?.message || "please try again."}`;
      });
    }
    window.scrollTo({ top: 0 });
  }

  // ---------------- wiring ----------------
  $("#next-patient").addEventListener("click", async () => {
    const p = queueRows.find((r) => r.status !== "completed");
    const button = $("#next-patient");
    if (!p) {
      $("#queue-status").textContent = "There is no waiting patient to open.";
      return;
    }
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try { await openPatient(p.id, p.visit_id); }
    catch (error) {
      $("#queue-status").textContent = error?.message || "Could not open the next patient.";
      $("#queue-status").classList.add("error");
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  });
  $("#back-queue").addEventListener("click", async () => { reviewView.hidden = true; queueView.hidden = false; await renderQueue(); });
  $("#nav-queue").addEventListener("click", async () => { reviewView.hidden = true; queueView.hidden = false; await renderQueue(); });
  $("#nav-guide").addEventListener("click", () => {
    if (reviewView.hidden) $("#queue-view .page-title p").textContent = "Open a patient first, then use the Guideline assistant panel.";
    else $("#rag-form").scrollIntoView({ behavior: "smooth" });
  });

  $("#save-notes").addEventListener("click", async (event) => {
    if (!cur) return;
    const button = event.currentTarget;
    const text = $("#notes").value;
    $("#save-status").textContent = "";
    try {
      await withBusy(button, "Saving…", async () => {
        await Api.saveConsultationNotes(cur.visitId, text);
        $("#notes").value = "";
        $("#save-status").textContent = "Notes saved.";
        try { render(await Api.getPatient(cur.p.id)); }
        catch (refreshError) { $("#save-status").textContent = `Notes saved. History refresh failed: ${refreshError?.message || "please refresh the patient."}`; }
      });
    } catch (error) { $("#save-status").textContent = error?.message || "Notes could not be saved. Your draft remains in the editor."; }
  });
  $("#complete").addEventListener("click", async (event) => {
    if (!cur || !window.confirm("Complete this consultation? This updates the visit status.")) return;
    const button = event.currentTarget;
    $("#save-status").textContent = "";
    try {
      await withBusy(button, "Completing…", async () => {
        await Api.completeConsultation(cur.visitId);
        reviewView.hidden = true;
        queueView.hidden = false;
        await renderQueue();
      });
    } catch (error) { $("#save-status").textContent = error?.message || "The consultation could not be completed."; }
  });
  $("#draft-btn").addEventListener("click", async (event) => {
    if (!cur) return;
    $("#save-status").textContent = "";
    try {
      await withBusy(event.currentTarget, "Drafting…", async () => {
        const result = await Api.brief(cur.p.id);
        const box = $("#notes");
        box.value = (box.value ? box.value + "\n\n" : "") + (result.draft || "");
        const citations = Array.isArray(result.citations) ? result.citations.filter(Boolean).map(String) : [];
        $("#save-status").textContent = citations.length
          ? `Draft added for clinician review. Edit it before saving; this summary is rule-based. Sources: ${citations.join("; ")}.`
          : "Draft added for clinician review. Edit it before saving; this summary is rule-based. No citations were returned.";
        box.focus();
      });
    } catch (error) { $("#save-status").textContent = error?.message || "A draft could not be created."; }
  });

  $("#results-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    if (!form.reportValidity()) return;
    const f = new FormData(form), values = {};
    for (const [k, v] of f.entries()) if (!["date", "medicines"].includes(k) && v !== "") values[k] = Number(v);
    const meds = (f.get("medicines") || "").split(",").map((s) => s.trim()).filter(Boolean);
    if (!Object.keys(values).length && !meds.length) {
      $("#results-status").textContent = "Enter at least one measured result or a recorded medicine before saving.";
      $("#results-status").classList.add("error");
      return;
    }
    $("#results-status").textContent = "";
    const submit = form.querySelector('[type="submit"]');
    try {
      await withBusy(submit, "Saving results…", async () => {
        const r = await Api.addResults(cur.p.id, { date: f.get("date"), visit_id: cur.visitId, values, medicines: meds });
        const m = r.merge;
        $("#results-status").textContent = `Saved: ${m.added} new, ${m.updated} updated, ${m.duplicates_ignored} duplicate(s) ignored${m.egfr_calculated ? ". eGFR calculated from creatinine (CKD-EPI 2021)" : ""}.`;
        $("#results-status").classList.remove("error");
        render(r.patient);
      });
    } catch (error) {
      $("#results-status").textContent = error?.message || "Results could not be saved. Your entries are still here.";
      $("#results-status").classList.add("error");
    }
  });

  $("#screen-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = {}; for (const [k, v] of new FormData(e.target).entries()) if (v !== "") d[k] = ["sex", "diabetes"].includes(k) ? v : Number(v);
    const submit = e.currentTarget.querySelector('[type="submit"]');
    try {
      await withBusy(submit, "Running screening…", async () => showScreen(await Api.runScreening(d)));
    } catch (error) { $("#screen-result").textContent = error?.message || "Screening could not be completed."; }
  });

  // ---------------- guideline assistant (RAG) ----------------
  // The service returns one text block "[1] passage ... [2] passage ..." plus a citations list.
  // We split it back into one card per passage so each can show its own document and page.
  function parsePassages(answer) {
    const out = [];
    const re = /(?:^|\n\n)\[(\d+)\]\s([\s\S]*?)(?=\n\n\[\d+\]\s|$)/g;
    let m;
    while ((m = re.exec(String(answer || "")))) out.push({ n: Number(m[1]), text: m[2].trim() });
    return out;
  }
  function renderRag(result) {
    const el = $("#rag-answer");
    const passages = parsePassages(result.answer);
    const cites = Array.isArray(result.citations) ? result.citations : [];
    $("#rag-mode").textContent = result.mode === "retrieval-only" ? "passages only" : (result.mode || "");
    if (!passages.length) {
      el.innerHTML = `<div class="notice">${esc(result.answer || "No answer was returned.")}</div>`;
      return;
    }
    el.innerHTML = `<p class="muted" style="margin:14px 0 8px">${passages.length} closest passage${passages.length > 1 ? "s" : ""}. No AI summary is added: you read the guideline's own words.</p>` +
      passages.map((ps) => {
        const c = cites.find((x) => x.n === ps.n) || {};
        const long = ps.text.length > 380;
        return `<article class="passage"><header><span class="passage-n">${ps.n}</span><span class="chip info">${esc(c.doc || "Guideline")}</span>${c.page ? `<span class="chip">page ${esc(c.page)}</span>` : ""}${c.section ? `<span class="chip">${esc(c.section)}</span>` : ""}</header>
          <p class="${long ? "clamped" : ""}">${esc(ps.text)}</p>${long ? '<button class="link-btn" type="button" data-more>Show more</button>' : ""}</article>`;
      }).join("");
    el.querySelectorAll("[data-more]").forEach((b) => b.addEventListener("click", () => {
      const p = b.previousElementSibling; const open = p.classList.toggle("clamped");
      b.textContent = open ? "Show more" : "Show less";
    }));
  }
  async function askGuidelines(question) {
    const submit = $("#rag-form").querySelector('[type="submit"]');
    try {
      await withBusy(submit, "Searching…", async () => renderRag(await Api.queryRag(question, cur?.p.id)));
    } catch (error) { $("#rag-answer").innerHTML = `<div class="notice">${esc(error?.message || "Guideline search is unavailable.")}</div>`; }
  }
  $("#rag-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const question = $("#rag-question").value.trim();
    if (!question) { $("#rag-answer").innerHTML = '<div class="notice">Enter a question to search the available guideline text.</div>'; $("#rag-question").focus(); return; }
    await askGuidelines(question);
  });
  document.querySelectorAll("#rag-examples .example-chip").forEach((b) => b.addEventListener("click", () => {
    $("#rag-question").value = b.textContent.trim(); askGuidelines(b.textContent.trim());
  }));

  // ---------------- agent briefing ----------------
  const TOOL_INFO = {
    get_patient_summary: ["Read patient summary", "Age, conditions, latest eGFR and uACR, KDIGO stage, trend, medicines"],
    get_care_gaps: ["Check care-gap rules", "Overdue tests, missing or unsafe medicines, fast decline, referral, BP"],
    run_screening_model: ["Run screening model", "Used only when the patient has no kidney labs"],
    search_guidelines: ["Search guidelines", "Finds the guideline passage that supports the main finding"],
  };
  const brainLabel = (b) => !b ? "unknown brain" : /scripted/.test(b) ? "Demo brain (no AI model)" : /claude/.test(b) ? "Claude" : /open/.test(b) ? "Open-source model" : b;
  const withCites = (t) => esc(t).replace(/\[([^\]]{3,200})\]/g, (m, c) => `<span class="cite">${c}</span>`).replace(/\n/g, "<br>");
  function toolSummary(name, r) {
    if (!r || r.error) return `Error: ${r?.error || "no result"}`;
    if (name === "get_patient_summary") return `${r.kdigo_stage || "no stage"} · ${r.kdigo_risk ? r.kdigo_risk + " risk" : "risk not gradable"} · eGFR ${r.egfr ?? "—"} · uACR ${r.uacr ?? "—"}`;
    if (name === "get_care_gaps") return (r.flags || []).length ? `${r.flags.length} flag(s): ` + r.flags.map((f) => f.title).join("; ") : "No care gaps found";
    if (name === "run_screening_model") return r.level ? `${String(r.level).toUpperCase()} · ${r.message}` : (r.error || "");
    if (name === "search_guidelines") return (r.passages || []).length ? r.passages.map((x) => `${x.doc} ${x.page}`).join(" · ") : "No passages found (is the guideline library loaded?)";
    return "";
  }
  function renderAgent(res) {
    $("#agent-brain").textContent = brainLabel(res.brain);
    const v = res.verification || {};
    const steps = (res.trace || []).filter((t) => t.kind !== "final");
    const verdict = v.ok
      ? `<div class="verify ok"><strong>Checked</strong><span>Every number and citation in this briefing was found in a tool result, and it claims no action.</span></div>`
      : `<div class="verify bad"><strong>Check failed</strong><span>${(v.problems || ["Not verified"]).map(esc).join(" · ")}. Do not rely on this briefing.</span></div>`;
    const answer = res.answer
      ? `<div class="agent-answer"><h3>Briefing</h3><p>${withCites(res.answer)}</p></div>`
      : '<div class="notice">The agent stopped before finishing (step limit). Nothing was changed.</div>';
    const trace = steps.map((t, i) => {
      if (t.kind === "tool") {
        const info = TOOL_INFO[t.tool] || [t.tool, ""];
        return `<li class="trace-step ${t.status === "error" ? "err" : ""}"><span class="trace-dot">${i + 1}</span><div>
          <strong>${esc(info[0])}</strong> <span class="chip ${t.status === "error" ? "high" : "info"}">${esc(t.status)}</span> <small class="muted">${esc(t.ms ?? "")} ms</small>
          <small class="trace-why">${esc(info[1])}${t.args && Object.keys(t.args).length ? " · asked: “" + esc(Object.values(t.args).join(", ")) + "”" : ""}</small>
          <p class="trace-result">${esc(toolSummary(t.tool, t.result))}</p>
          <details><summary>Raw tool result</summary><pre>${esc(JSON.stringify(t.result, null, 2))}</pre></details></div></li>`;
      }
      return `<li class="trace-step err"><span class="trace-dot">!</span><div><strong>${esc(t.kind)}</strong><p class="trace-result">${esc(t.reason || "")}</p></div></li>`;
    }).join("");
    $("#agent-out").innerHTML = `${verdict}${answer}
      <div class="actions agent-actions"><button class="button secondary" id="agent-to-notes" type="button" ${res.answer ? "" : "disabled"}>Add to consultation notes</button></div>
      <h3>What the agent did <small class="muted">(${res.steps} step${res.steps === 1 ? "" : "s"}, all saved in the audit log)</small></h3>
      <ol class="trace">${trace}</ol>
      <p class="field-hint">The agent can only read: the patient is fixed by the system, names are never sent to it, and it cannot change any record. Review before using.</p>`;
    const toNotes = $("#agent-to-notes");
    if (toNotes) toNotes.addEventListener("click", () => {
      const box = $("#notes");
      box.value = (box.value ? box.value + "\n\n" : "") + "Agent briefing (draft, reviewed by clinician):\n" + res.answer;
      $("#save-status").textContent = "Briefing added to the notes box. Edit it before saving.";
      box.focus();
    });
  }
  $("#agent-run").addEventListener("click", async (event) => {
    if (!cur) return;
    $("#agent-out").innerHTML = '<p class="muted" style="margin:10px 0 0">The agent is working…</p>';
    try { await withBusy(event.currentTarget, "Agent working…", async () => renderAgent(await Api.runAgent(cur.p.id))); }
    catch (error) { $("#agent-out").innerHTML = `<div class="notice">${esc(error?.message || "The agent could not run.")}</div>`; }
  });

  // ---------------- lab report reader ----------------
  const LAB_NAMES = { creatinine: "Creatinine", egfr: "eGFR", uacr: "uACR", hba1c: "HbA1c", potassium: "Potassium", bun: "BUN", sodium: "Sodium" };
  const SAMPLE_REPORT = "Date: 12/03/2026\nSerum creatinine: 1.9 mg/dL\neGFR 38\nUACR >300 mg/g\nHbA1c 7.2 %\nPotassium 5.1 mEq/L";
  $("#lab-sample").addEventListener("click", () => { $("#lab-text").value = SAMPLE_REPORT; $("#lab-text").focus(); });
  function renderLabProposal(r) {
    const rows = r.proposed || [];
    $("#lab-count").textContent = rows.length ? `${rows.length} proposed` : "";
    if (!rows.length) { $("#lab-out").innerHTML = '<div class="notice">No known test names were found in that text. Check the text or use Add results below.</div>'; return; }
    $("#lab-out").innerHTML = `<div class="notice">Proposal only. Nothing has been saved. Check each value against the report, fix anything wrong, then confirm.</div>
      <div class="table-wrap"><table class="lab-table"><thead><tr><th>Use</th><th>Test</th><th>Value</th><th>Unit</th><th>From the report</th></tr></thead><tbody>
      ${rows.map((x) => `<tr data-code="${esc(x.code)}"><td><input type="checkbox" aria-label="Use ${esc(LAB_NAMES[x.code] || x.code)}" ${x.value != null && !x.warning ? "checked" : ""}></td>
        <td><strong>${esc(LAB_NAMES[x.code] || x.code)}</strong></td>
        <td><input type="number" step="any" aria-label="${esc(LAB_NAMES[x.code] || x.code)} value" value="${x.value ?? ""}"></td><td>${esc(x.unit)}</td>
        <td><small class="muted">${esc(x.from_line)}</small>${x.warning ? `<br><span class="chip high">${esc(x.warning)}</span>` : ""}</td></tr>`).join("")}
      </tbody></table></div>
      <form id="lab-confirm" class="lab-confirm"><label>Result date<input type="date" name="date" value="${esc(r.report_date || today())}" required></label>
        <button class="button primary" type="submit">Confirm and save selected</button></form>
      <p class="form-message" id="lab-status" role="status" aria-live="polite"></p>`;
    $("#lab-out").querySelectorAll('tbody input[type="number"]').forEach((inp) => inp.addEventListener("input", () => {
      inp.closest("tr").querySelector('input[type="checkbox"]').checked = inp.value !== "";
    }));
    $("#lab-confirm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const values = {};
      $("#lab-out").querySelectorAll("tbody tr").forEach((tr) => {
        const on = tr.querySelector('input[type="checkbox"]').checked, v = tr.querySelector('input[type="number"]').value;
        if (on && v !== "") values[tr.dataset.code] = Number(v);
      });
      const status = $("#lab-status");
      if (!Object.keys(values).length) { status.textContent = "Select at least one value with a number before saving."; status.classList.add("error"); return; }
      try {
        await withBusy(e.currentTarget.querySelector('[type="submit"]'), "Saving…", async () => {
          const res = await Api.addResults(cur.p.id, { date: new FormData(e.currentTarget).get("date"), visit_id: cur.visitId, values });
          const m = res.merge;
          render(res.patient);
          $("#lab-out").innerHTML = `<div class="notice ok-note">Saved after your confirmation: ${m.added} new, ${m.updated} updated, ${m.duplicates_ignored} duplicate(s) ignored${m.egfr_calculated ? ". eGFR calculated from creatinine (CKD-EPI 2021)" : ""}.</div>`;
          $("#lab-text").value = ""; $("#lab-count").textContent = "";
        });
      } catch (error) { status.textContent = error?.message || "Results could not be saved."; status.classList.add("error"); }
    });
  }
  $("#lab-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = $("#lab-text").value.trim();
    if (!text) { $("#lab-out").innerHTML = '<div class="notice">Paste the text of a lab report first.</div>'; return; }
    try { await withBusy(e.currentTarget.querySelector('[type="submit"]'), "Reading…", async () => renderLabProposal(await Api.proposeLabs(cur.p.id, text))); }
    catch (error) { $("#lab-out").innerHTML = `<div class="notice">${esc(error?.message || "The report could not be read.")}</div>`; }
  });

  // ---------------- four-agent workspace (project flow) ----------------
  const PL_NAMES = ["Clinical Data Agent", "Risk Assessment Agent", "Clinical Management Agent", "Diet Recommendation Agent"];
  const PL_ST = { completed: ["Completed", "ok"], needs_review: ["Needs review", "warn"], insufficient_evidence: ["Insufficient evidence", "warn"], failed: ["Failed", "bad"] };
  const plChip = (st) => { const [t, c] = PL_ST[st] || ["Not started", "idle"]; return `<span class="pl-st ${c}">${t}</span>`; };
  const plEv = (groups) => (groups || []).map((g) => `<div class="pl-topic"><h4>${esc(g.topic)}</h4>${g.evidence.length ? g.evidence.map((e) => `<details><summary>${esc(e.doc)}, PDF p.${esc(e.page)}</summary><p>${esc(e.text)}</p></details>`).join("") : '<p class="muted">No guideline passage found for this topic.</p>'}</div>`).join("");
  function plBody(a) {
    if (a.name === PL_NAMES[0]) return `<table class="pl-table"><thead><tr><th>Value</th><th>Result</th><th>Date</th><th>Status</th></tr></thead><tbody>${(a.fields || []).map((f) => `<tr><td>${esc(f.name)}</td><td>${f.value == null ? "not on record" : esc(f.value) + " " + esc(f.unit)}</td><td>${f.date ? fd(f.date) : "—"}</td><td>${esc(f.status)}</td></tr>`).join("")}</tbody></table>`;
    if (a.name === PL_NAMES[1]) return `<p><strong>${esc(a.stage || "No KDIGO stage")}</strong>${a.risk ? " · " + esc(a.risk) + " risk" : ""}${a.trend_per_year != null ? " · eGFR trend " + (a.trend_per_year > 0 ? "+" : "") + esc(a.trend_per_year) + " per year" : ""}${a.monitor_months ? " · test about every " + esc(a.monitor_months) + " months" : ""}</p>` +
      (a.screening ? `<p>Screening: <strong>${esc(a.screening.level)}</strong> (model ${esc(a.screening.model_version)}). Main factors: ${a.screening.factors.map((f) => esc(f.feature) + " (" + esc(f.direction) + ")").join(", ")}.</p>` : "") + `<p class="muted">${esc(a.limitations || "")}</p>`;
    if (a.name === PL_NAMES[2]) return ((a.care_gaps || []).length ? `<h4>Care gaps (rules)</h4><ul>${a.care_gaps.map((g) => `<li><strong>${esc(g.title)}</strong> <span class="chip ${esc(g.level)}">${esc(g.level)}</span><br><small class="muted">${esc(g.detail)} Source: ${esc(g.source)}</small></li>`).join("")}</ul>` : "") + plEv(a.topics);
    return ((a.constraints || []).length ? `<p>Constraints: ${a.constraints.map((c) => `<span class="chip">${esc(c)}</span>`).join(" ")}</p>` : "") + plEv(a.topics);
  }
  function renderPipeline(r) {
    const ag = (r && r.agents) || [], by = Object.fromEntries(ag.map((a) => [a.name, a]));
    $("#pipe-flow").innerHTML = PL_NAMES.map((n, i) => `<li><span class="pl-num">${i + 1}</span><strong>${n}</strong>${plChip(by[n] && by[n].status)}</li>`).join("");
    $("#pipe-time").textContent = r && r.generated_at ? "run " + new Date(r.generated_at).toLocaleString() : "not run yet";
    $("#pipe-notes").disabled = !ag.length;
    $("#pipe-out").innerHTML = !ag.length ? '<p class="muted" style="margin:12px 0 0">Not run yet. The agents only read the record; they never change a value.</p>' :
      ag.map((a) => `<article class="pl-card"><h3>${esc(a.name)} ${plChip(a.status)}</h3><p>${esc(a.summary || "")}</p>
        <p class="pl-meta">Started ${new Date(a.started_at).toLocaleTimeString()} · finished ${new Date(a.finished_at).toLocaleTimeString()} · inputs: ${(a.inputs_used || []).map(esc).join(", ") || "—"} · doctor review required</p>
        ${(a.warnings || []).map((w) => `<div class="notice">${esc(w)}</div>`).join("")}${a.status === "failed" ? "" : plBody(a)}</article>`).join("") +
      `<div class="pl-cites"><h3>Sources used</h3>${r.citations.length ? "<ul>" + r.citations.map((c) => `<li>${esc(c)}</li>`).join("") + "</ul>" : '<p class="muted">No guideline passages were found.</p>'}<p class="field-hint">${esc(r.disclaimer)}</p></div>`;
    cur && (cur.pipe = r);
  }
  $("#pipe-run").addEventListener("click", async (event) => {
    const mine = cur; $("#pipe-out").innerHTML = '<p class="muted" style="margin:12px 0 0">The four agents are running…</p>';
    try { const r = await withBusy(event.currentTarget, "Running…", () => Api.runPipeline(mine.p.id)); if (cur === mine) renderPipeline(r); }
    catch (error) { $("#pipe-out").innerHTML = `<div class="notice">The agents did not run. ${esc(error?.message || "Try again.")} Nothing was changed.</div>`; }
  });
  $("#pipe-notes").addEventListener("click", () => {
    const r = cur && cur.pipe; if (!r) return;
    const t = ["DRAFT AGENT SUMMARY (doctor to review and edit)", ...r.agents.map((a) => `- ${a.name} [${(PL_ST[a.status] || ["?"])[0]}]: ${a.summary}`), r.citations.length ? "Sources: " + r.citations.join("; ") : "", r.disclaimer].filter(Boolean).join("\n");
    const box = $("#notes"); box.value = (box.value ? box.value + "\n\n" : "") + t; box.scrollIntoView({ behavior: "smooth", block: "center" });
  });

  // ---------------- side navigation shortcuts ----------------
  const goPanel = (sel, name) => {
    if (reviewView.hidden) { $("#queue-view .page-title p").textContent = `Open a patient first, then use the ${name} panel.`; return; }
    document.querySelector(sel).scrollIntoView({ behavior: "smooth" });
  };
  $("#nav-pipeline").addEventListener("click", () => goPanel("#pipeline-panel", "Agent workspace"));
  $("#nav-agent").addEventListener("click", () => goPanel("#agent-panel", "Agent briefing"));
  $("#nav-labs").addEventListener("click", () => goPanel("#lab-panel", "Lab report reader"));

  // ---------------- model card (queue page) ----------------
  function renderModelCard() {
    const el = $("#model-card"), m = modelInfo;
    if (!m) { el.innerHTML = ""; return; }
    const pct = (x) => (x == null ? "—" : Math.round(x * 100) + "%");
    const w = m.at_watch_line || {}, hi = m.at_high_line || {};
    el.innerHTML = `<h3>Screening model at a glance</h3><div class="model-stats">
      <div><span>Test AUC</span><strong>${esc(m.test_auc)}</strong><small>PR-AUC ${esc(m.test_pr_auc)}</small></div>
      <div><span>Watch line</span><strong>${pct(w.recall)}</strong><small>of CKD cases caught; ${pct(w.precision)} of those flagged have CKD</small></div>
      <div><span>High line</span><strong>${pct(hi.recall)}</strong><small>caught; ${pct(hi.precision)} of those flagged have CKD</small></div>
      <div><span>Held-out test</span><strong>${esc(m.n_test)}</strong><small>${esc(m.n_test_ckd)} with CKD (NHANES)</small></div></div>
      <p class="field-hint">${esc(m.note || "")} Inputs: ${(m.features || []).map((f) => esc(f.replace(/_/g, " "))).join(", ")}. Version ${esc(m.version)}.</p>`;
  }

  const [gridResult, modelResult] = await Promise.allSettled([Api.grid(), Api.model()]);
  grid = gridResult.status === "fulfilled" ? gridResult.value : null;
  modelInfo = modelResult.status === "fulfilled" ? modelResult.value : null;
  renderModelCard();
  await renderQueue();
});

document.addEventListener("DOMContentLoaded", async () => {
  const me = Api.requireRole("reception");
  if (!me) return;
  const $ = (selector) => document.querySelector(selector);
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[character]));
  const body = $("#queue-body");
  const search = $("#patient-search");
  const directorySearch = $("#existing-patient-search");
  const directoryStatus = $("#existing-patient-status");
  const directoryResults = $("#existing-patient-results");
  const form = $("#register-form");
  const registerButton = form.querySelector('[type="submit"]');
  const statusMessage = $("#queue-status");
  const formMessage = $("#register-status");
  let all = [];
  let directoryTimer = null;
  let directoryRequest = 0;

  $("#who").textContent = me.name || "Reception";
  $("#logout").addEventListener("click", (event) => {
    event.preventDefault();
    Api.logout();
  });

  const setMessage = (element, message, type = "") => {
    element.textContent = message;
    element.classList.toggle("error", type === "error");
    element.classList.toggle("success", type === "success");
  };

  const draw = () => {
    const query = (search.value || "").trim().toLocaleLowerCase();
    const rows = all.filter((patient) =>
      `${patient.name || ""} ${patient.id || ""}`.toLocaleLowerCase().includes(query));
    body.innerHTML = rows.map((patient) => {
      const status = String(patient.status || "unknown").replaceAll("_", " ");
      const statusClass = patient.status === "completed" ? "done" : patient.status === "waiting" ? "waiting" : "";
      return `<tr><td><strong>${esc(patient.token || "—")}</strong></td><td>${esc(patient.name || "—")}<br><small class="muted">${esc(patient.age ?? "—")} years${patient.is_follow_up ? " · follow-up" : " · new"}</small></td><td>${esc(patient.id || "—")}</td><td><span class="status ${statusClass}">${esc(status)}</span></td></tr>`;
    }).join("") || `<tr><td colspan="4" class="empty">${query ? "No matching patients in the loaded queue." : "No patients in the queue yet."}</td></tr>`;
  };

  const load = async () => {
    body.setAttribute("aria-busy", "true");
    setMessage(statusMessage, "");
    try {
      const queue = await Api.getQueue();
      all = Array.isArray(queue) ? queue : [];
      $("#waiting-count").textContent = all.filter((patient) => patient.status === "waiting").length;
      $("#checked-count").textContent = all.length;
      $("#done-count").textContent = all.filter((patient) => patient.status === "completed").length;
      draw();
    } catch (error) {
      all = [];
      $("#waiting-count").textContent = "—";
      $("#checked-count").textContent = "—";
      $("#done-count").textContent = "—";
      body.innerHTML = '<tr><td colspan="4" class="empty">Queue could not be loaded.</td></tr>';
      setMessage(statusMessage, error?.message || "Could not load the queue. Please try again.", "error");
    } finally {
      body.setAttribute("aria-busy", "false");
    }
  };

  search.addEventListener("input", draw);
  directorySearch.addEventListener("input", () => {
    clearTimeout(directoryTimer);
    const query = directorySearch.value.trim();
    const requestId = ++directoryRequest;
    if (query.length < 2) {
      directoryResults.setAttribute("aria-busy", "false");
      directoryResults.innerHTML = '<p class="empty">Enter at least 2 characters to search authorized records.</p>';
      setMessage(directoryStatus, "");
      return;
    }
    directoryResults.setAttribute("aria-busy", "true");
    setMessage(directoryStatus, "Searching existing records…");
    directoryTimer = setTimeout(async () => {
      try {
        const records = await Api.searchPatients(query);
        if (requestId !== directoryRequest) return;
        const patients = Array.isArray(records) ? records : [];
        if (!patients.length) {
          directoryResults.innerHTML = '<p class="empty">No matching existing records. Check the ID, or register as a new patient.</p>';
          setMessage(directoryStatus, "");
          return;
        }
        directoryResults.innerHTML = patients.map((patient) => {
          const label = `Use ${patient.name || patient.id} for a follow-up`;
          const details = [patient.sex || null, patient.birth_year ? `Birth year ${patient.birth_year}` : null].filter(Boolean).join(" · ");
          return `<div class="directory-result"><div><strong>${esc(patient.name || "Name unavailable")}</strong><small>${esc(patient.id || "ID unavailable")}${details ? ` · ${esc(details)}` : ""}</small></div><button class="button secondary" type="button" data-select-patient data-id="${esc(patient.id)}" data-name="${esc(patient.name)}" data-sex="${esc(patient.sex)}" aria-label="${esc(label)}">Use for follow-up</button></div>`;
        }).join("");
        setMessage(directoryStatus, `${patients.length} matching record${patients.length === 1 ? "" : "s"} found.`);
      } catch (error) {
        if (requestId !== directoryRequest) return;
        directoryResults.innerHTML = '<p class="empty">Existing records could not be searched.</p>';
        setMessage(directoryStatus, error?.message || "Search is unavailable. Please try again.", "error");
      } finally {
        if (requestId === directoryRequest) directoryResults.setAttribute("aria-busy", "false");
      }
    }, 250);
  });
  directoryResults.addEventListener("click", (event) => {
    const button = event.target.closest("[data-select-patient]");
    if (!button) return;
    form.elements.study_id.value = button.dataset.id || "";
    form.elements.name.value = button.dataset.name || "";
    form.elements.sex.value = ["F", "M"].includes(button.dataset.sex) ? button.dataset.sex : "";
    setMessage(formMessage, `${button.dataset.name || button.dataset.id} selected. Add a reason, then submit to register a follow-up visit.`);
    $("#register-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    form.elements.reason.focus({ preventScroll: true });
  });
  $("[data-scroll-register]").addEventListener("click", () => {
    $("#register-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    form.elements.name.focus({ preventScroll: true });
  });
  form.addEventListener("reset", () => setMessage(formMessage, ""));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    setMessage(formMessage, "");
    if (!form.reportValidity()) return;
    const data = Object.fromEntries(new FormData(form));
    data.name = String(data.name || "").trim();
    data.reason = String(data.reason || "").trim();
    data.age = data.age ? Number(data.age) : null;
    data.study_id = String(data.study_id || "").trim() || null;
    if (!data.name || !data.reason) {
      setMessage(formMessage, "Enter the patient name and reason for visit.", "error");
      return;
    }
    registerButton.disabled = true;
    registerButton.setAttribute("aria-busy", "true");
    registerButton.textContent = "Adding to queue…";
    try {
      const result = await Api.registerPatient(data);
      form.reset();
      setMessage(formMessage, `Added ${result.name || "patient"} (${result.id || "ID unavailable"}), token ${result.token || "not returned"}.`, "success");
      await load();
    } catch (error) {
      setMessage(formMessage, error?.message || "Could not add the patient. Your entries are still here; try again.", "error");
    } finally {
      registerButton.disabled = false;
      registerButton.removeAttribute("aria-busy");
      registerButton.innerHTML = 'Add to queue <span aria-hidden="true">→</span>';
    }
  });

  await load();
});

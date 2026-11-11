"use strict";

document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id);

  const params = new URLSearchParams(window.location.search);
  const initialPatientId = params.get("patient_id");
  const initialVisitId = params.get("visit_id");

  const state = {
    patients: [],
    patient: null,
    visit: null,
    measurements: [],
    medicines: [],
    issues: [],
    loading: false,
    submitting: false,
    toastTimer: null
  };

  const listView = $("patientListView");
  const detailView = $("patientDetailView");
  const alertBox = $("pageAlert");

  // Keep navigation responsive on small screens.
  const sidebar = $("rd-sidebar");
  const overlay = $("rd-overlay");
  const menuButton = $("rd-menu-toggle");

  function openSidebar() {
    sidebar.classList.add("is-open");
    overlay.hidden = false;
    menuButton.setAttribute("aria-expanded", "true");
    menuButton.setAttribute("aria-label", "Close navigation");
  }

  function closeSidebar() {
    sidebar.classList.remove("is-open");
    overlay.hidden = true;
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.setAttribute("aria-label", "Open navigation");
  }

  menuButton.addEventListener("click", () => {
    sidebar.classList.contains("is-open") ? closeSidebar() : openSidebar();
  });

  overlay.addEventListener("click", closeSidebar);

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeSidebar();
      closeModal();
    }
  });

  // Safe text rendering: patient data is never inserted as HTML.
  function text(value, fallback = "Not recorded") {
    if (
      value === undefined ||
      value === null ||
      String(value).trim() === ""
    ) {
      return fallback;
    }

    return String(value);
  }

  function first(...values) {
    return values.find(
      (value) =>
        value !== undefined &&
        value !== null &&
        value !== ""
    );
  }

  function object(value) {
    return (
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value)
    );
  }

  function read(obj, keys) {
    if (!object(obj)) return undefined;

    for (const key of keys) {
      if (
        obj[key] !== undefined &&
        obj[key] !== null &&
        obj[key] !== ""
      ) {
        return obj[key];
      }
    }

    return undefined;
  }

  function date(value) {
    if (!value) return "Not recorded";

    const match = String(value).match(
      /^(\d{4})-(\d{2})-(\d{2})/
    );

    if (match) {
      return `${match[3]}/${match[2]}/${match[1]}`;
    }

    const parsed = new Date(value);

    if (Number.isNaN(parsed.getTime())) {
      return String(value);
    }

    return new Intl.DateTimeFormat("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric"
    }).format(parsed);
  }

  function showAlert(message) {
    alertBox.textContent = message;
    alertBox.hidden = false;
  }

  function clearAlert() {
    alertBox.textContent = "";
    alertBox.hidden = true;
  }

  function toast(message, error = false) {
    const node = $("toastMessage");

    clearTimeout(state.toastTimer);

    node.textContent = message;
    node.classList.toggle("is-error", error);
    node.hidden = false;

    state.toastTimer = setTimeout(() => {
      node.hidden = true;
    }, 4200);
  }

  function unwrap(response) {
    if (object(response?.data)) return response.data;
    if (object(response?.result)) return response.result;

    return response;
  }

  function patientFrom(record) {
    return record?.patient || record?.patient_data || record;
  }

  function getPatientId(patient) {
    return first(
      patient?.patient_id,
      patient?.id,
      patient?.patientId
    );
  }

  function getVisitId(visit) {
    return first(
      visit?.visit_id,
      visit?.id,
      visit?.visitId
    );
  }

  function visitsOf(patient) {
    if (Array.isArray(patient?.visits)) {
      return patient.visits;
    }

    if (Array.isArray(patient?.encounters)) {
      return patient.encounters;
    }

    if (Array.isArray(patient?.visit_history)) {
      return patient.visit_history;
    }

    return [];
  }

  function matchVisit(patient, requestedVisitId) {
    const visits = visitsOf(patient);

    if (requestedVisitId) {
      return (
        visits.find(
          (visit) =>
            String(getVisitId(visit)) ===
            String(requestedVisitId)
        ) || null
      );
    }

    return visits.length === 1 ? visits[0] : null;
  }

  function getPatientName(patient) {
    return first(
      patient?.full_name,
      patient?.name,
      [
        patient?.first_name,
        patient?.middle_name,
        patient?.last_name
      ]
        .filter(Boolean)
        .join(" "),
      patient?.patient_name
    );
  }

  function initials(name) {
    return (
      String(name || "P")
        .trim()
        .split(/\s+/)
        .slice(0, 2)
        .map((part) => part[0]?.toUpperCase() || "")
        .join("") || "P"
    );
  }

  function setText(id, value, fallback = "Not recorded") {
    $(id).textContent = text(value, fallback);
  }

  function statusClass(status) {
    const value = String(status || "").toLowerCase();

    if (/submitted|review|complete|approved/.test(value)) {
      return "is-submitted";
    }

    if (/error|failed|rejected/.test(value)) {
      return "is-error";
    }

    if (/pending|draft|in.progress|incomplete|awaiting/.test(value)) {
      return "is-pending";
    }

    return "";
  }

  function showListView() {
    listView.hidden = false;
    detailView.hidden = true;

    $("pageTitle").textContent = "Review & Submit";

    $("pageSubtitle").textContent =
      "Find the correct patient and review the saved visit before submitting it for doctor review.";

    $("breadcrumbCurrent").textContent = "Review & Submit";

    history.replaceState({}, "", "/review-submit.html");

    closeSidebar();
  }

  function showDetailView(patientId, visitId) {
    listView.hidden = true;
    detailView.hidden = false;

    $("pageTitle").textContent = "Patient Review";

    $("pageSubtitle").textContent =
      "Verify this patient's saved visit information and original report.";

    $("breadcrumbCurrent").textContent = "Patient Review";

    const query = new URLSearchParams();

    query.set("patient_id", patientId);

    if (visitId) {
      query.set("visit_id", visitId);
    }

    history.replaceState(
      {},
      "",
      `/review-submit.html?${query.toString()}`
    );

    closeSidebar();

    window.scrollTo({
      top: 0,
      behavior: "smooth"
    });
  }

  function editUrl() {
    const query = new URLSearchParams();

    const patientId = getPatientId(state.patient);
    const visitId = getVisitId(state.visit);

    if (patientId) {
      query.set("patient_id", patientId);
    }

    if (visitId) {
      query.set("visit_id", visitId);
    }

    // Clinical Data Entry should read these parameters
    // and load the same record.
    return `/clinical-data-entry.html?${query.toString()}`;
  }

  function setEditLinks() {
    $("editInformationButton").href = editUrl();
    $("editBottomButton").href = editUrl();
  }

  // ---------- View 1: patient list ----------

  async function loadPatients() {
    clearAlert();

    $("listLoading").hidden = false;
    $("patientGrid").replaceChildren();
    $("listEmpty").hidden = true;
    $("patientCount").textContent = "Loading…";

    if (typeof window.Api?.searchPatients !== "function") {
      $("listLoading").hidden = true;
      $("patientCount").textContent = "Patient search unavailable";

      $("emptyTitle").textContent =
        "Patient search API unavailable";

      $("emptyDescription").textContent =
        "The current API client does not expose Api.searchPatients(). Open Patient Search to find a patient, or connect this page to the existing patient-search method.";

      $("listEmpty").hidden = false;

      showAlert(
        "Patient records were not loaded because Api.searchPatients() is unavailable."
      );

      return;
    }

    try {
      // Search only actual backend records.
      // No example patient records are created.
      const response = await window.Api.searchPatients("");
      const result = unwrap(response);

      const records = Array.isArray(result)
        ? result
        : first(
            result?.patients,
            result?.items,
            result?.results,
            result?.data,
            []
          );

      if (!Array.isArray(records)) {
        throw new Error(
          "The patient-search API returned an unexpected response format."
        );
      }

      state.patients = records
        .map(patientFrom)
        .filter(object);

      $("patientCount").textContent =
        `${state.patients.length} patient${state.patients.length === 1 ? "" : "s"}`;

      renderPatientList($("listSearchInput").value);
    } catch (error) {
      console.error("Unable to load patients:", error);

      $("patientCount").textContent = "Could not load patients";

      $("emptyTitle").textContent =
        "Patient records could not be loaded";

      $("emptyDescription").textContent =
        error?.message ||
        "Check the API connection and try again.";

      $("listEmpty").hidden = false;

      showAlert(
        "Patient list loading failed. No sample records have been displayed."
      );
    } finally {
      $("listLoading").hidden = true;
    }
  }

  function renderPatientList(searchTerm = "") {
    const grid = $("patientGrid");

    grid.replaceChildren();

    const query = searchTerm.trim().toLowerCase();

    const filtered = state.patients.filter((patient) => {
      const name = getPatientName(patient) || "";
      const id = getPatientId(patient) ?? "";

      return `${name} ${id}`.toLowerCase().includes(query);
    });

    $("patientCount").textContent =
      `${filtered.length} patient${filtered.length === 1 ? "" : "s"}`;

    $("listEmpty").hidden = filtered.length > 0;

    if (!filtered.length) {
      $("emptyTitle").textContent = state.patients.length
        ? "No matching patients"
        : "No patient records available";

      $("emptyDescription").textContent = state.patients.length
        ? "Try another name or patient ID."
        : "No records were returned by the connected API.";

      return;
    }

    filtered.forEach((patient, index) => {
      const id = getPatientId(patient);
      const name = getPatientName(patient) || "Name not recorded";
      const visits = visitsOf(patient);
      const visit = visits.length
        ? visits[visits.length - 1]
        : null;

      const visitId = getVisitId(visit);

      const visitDate = first(
        visit?.visit_date,
        visit?.date,
        visit?.created_at
      );

      const status = first(
        visit?.status,
        patient?.status,
        "Status unavailable"
      );

      const card = document.createElement("article");
      card.className = "rv-patient-card";
      card.style.animationDelay =
        `${Math.min(index * 35, 210)}ms`;

      const top = document.createElement("div");
      top.className = "rv-patient-card-top";

      const avatar = document.createElement("div");
      avatar.className = "rv-card-avatar";
      avatar.textContent = initials(name);

      const identity = document.createElement("div");
      identity.className = "rv-card-identity";

      const heading = document.createElement("h3");
      heading.textContent = name;

      const idLine = document.createElement("div");
      idLine.className = "rv-card-id";
      idLine.textContent =
        `Patient ID: ${text(id, "Not available")}`;

      const badge = document.createElement("span");
      badge.className =
        `rv-status-badge ${statusClass(status)}`;
      badge.textContent = status;

      identity.append(heading, idLine);
      top.append(avatar, identity, badge);

      const meta = document.createElement("div");
      meta.className = "rv-card-meta";

      const visitCell = document.createElement("div");

      const visitLabel = document.createElement("span");
      visitLabel.textContent = "Latest visit ID";

      const visitValue = document.createElement("strong");
      visitValue.textContent = text(
        visitId,
        "Not available"
      );

      visitCell.append(visitLabel, visitValue);

      const dateCell = document.createElement("div");

      const dateLabel = document.createElement("span");
      dateLabel.textContent = "Visit date";

      const dateValue = document.createElement("strong");
      dateValue.textContent = date(visitDate);

      dateCell.append(dateLabel, dateValue);

      meta.append(visitCell, dateCell);

      const footer = document.createElement("div");
      footer.className = "rv-card-footer";

      const note = document.createElement("small");

      note.textContent = visits.length
        ? `${visits.length} saved visit${visits.length === 1 ? "" : "s"}`
        : "Visit details need to be loaded";

      const openButton = document.createElement("button");

      openButton.type = "button";
      openButton.className = "rv-button rv-button-primary";
      openButton.textContent = "Open & review →";

      // UPDATED: Load the full patient record before choosing a visit.
      openButton.addEventListener("click", async () => {
        const patientId = getPatientId(patient);

        if (
          patientId === undefined ||
          patientId === null ||
          String(patientId).trim() === ""
        ) {
          showAlert(
            "This patient record has no patient ID. It cannot be opened safely."
          );

          return;
        }

        if (
          typeof window.Api?.getPatientIntake !== "function"
        ) {
          showAlert(
            "Patient details could not be loaded because Api.getPatientIntake() is unavailable."
          );

          return;
        }

        openButton.disabled = true;
        openButton.textContent = "Loading visit…";

        clearAlert();

        try {
          // Search results may contain only basic patient information.
          // Fetch the full saved patient record before checking visits.
          const response =
            await window.Api.getPatientIntake(patientId);

          const payload = unwrap(response);
          const fullPatient = patientFrom(payload);

          if (!object(fullPatient)) {
            throw new Error(
              "The patient details API did not return a valid patient record."
            );
          }

          const returnedPatientId =
            getPatientId(fullPatient);

          if (
            returnedPatientId != null &&
            String(returnedPatientId) !== String(patientId)
          ) {
            throw new Error(
              "The API returned a different patient. The record was not opened."
            );
          }

          const fullVisits = visitsOf(fullPatient);

          if (!fullVisits.length) {
            showAlert(
              "The patient details API returned no saved visits. Check whether the clinical entry was saved successfully and whether getPatientIntake() returns the patient's visits."
            );

            return;
          }

          // Prefer the most recent visit using its actual date.
          // If dates are absent or invalid, preserve the API's order
          // for those entries rather than inventing a visit ID.
          const sortedVisits = [...fullVisits].sort((a, b) => {
            const rawDateA = first(
              a?.visit_date,
              a?.date,
              a?.created_at
            );

            const rawDateB = first(
              b?.visit_date,
              b?.date,
              b?.created_at
            );

            const dateA = rawDateA
              ? new Date(rawDateA).getTime()
              : Number.NaN;

            const dateB = rawDateB
              ? new Date(rawDateB).getTime()
              : Number.NaN;

            const validA = Number.isFinite(dateA);
            const validB = Number.isFinite(dateB);

            if (validA && validB) {
              return dateB - dateA;
            }

            if (validA) return -1;
            if (validB) return 1;

            return 0;
          });

          const latestVisit = sortedVisits[0];
          const visitId = getVisitId(latestVisit);

          if (
            visitId === undefined ||
            visitId === null ||
            String(visitId).trim() === ""
          ) {
            showAlert(
              "The patient has saved visit data, but the API did not return a visit ID. Check the visit fields returned by getPatientIntake()."
            );

            return;
          }

          // Open only with IDs returned by the backend.
          await openPatient(patientId, visitId);
        } catch (error) {
          console.error(
            "Unable to open patient visit:",
            error
          );

          showAlert(
            error?.message ||
              "The patient visit could not be loaded. Check the API connection."
          );
        } finally {
          openButton.disabled = false;
          openButton.textContent = "Open & review →";
        }
      });

      footer.append(note, openButton);
      card.append(top, meta, footer);

      grid.appendChild(card);
    });
  }

  $("listSearchInput").addEventListener("input", (event) => {
    renderPatientList(event.target.value);
  });

  $("topSearchForm").addEventListener("submit", (event) => {
    event.preventDefault();

    const query = $("patientSearchInput").value.trim();

    $("listSearchInput").value = query;

    if (detailView.hidden) {
      renderPatientList(query);
    } else {
      window.location.href =
        `/patient-search.html?search=${encodeURIComponent(query)}`;
    }
  });

  $("refreshListButton").addEventListener(
    "click",
    loadPatients
  );

  $("backToListButton").addEventListener("click", () => {
    showListView();
    loadPatients();
  });

  // ---------- View 2: patient details ----------

  async function openPatient(patientId, visitId) {
    showDetailView(patientId, visitId);

    $("detailPatientName").textContent = "Loading patient…";
    $("detailPatientId").textContent = patientId;
    $("detailVisitId").textContent = visitId;

    $("measurementsBody").replaceChildren();

    const loadingRow = document.createElement("tr");
    const loadingCell = document.createElement("td");

    loadingCell.colSpan = 5;
    loadingCell.className = "rv-empty-cell";
    loadingCell.textContent = "Loading saved measurements…";

    loadingRow.appendChild(loadingCell);
    $("measurementsBody").appendChild(loadingRow);

    clearAlert();

    if (
      typeof window.Api?.getPatientIntake !== "function"
    ) {
      showAlert(
        "The existing API client does not expose Api.getPatientIntake(patientId). Patient details cannot be loaded until the correct API method is connected."
      );

      return;
    }

    try {
      const response =
        await window.Api.getPatientIntake(patientId);

      const payload = unwrap(response);
      const patient = patientFrom(payload);

      if (!object(patient)) {
        throw new Error(
          "The patient API did not return a patient record."
        );
      }

      const returnedId = getPatientId(patient);

      if (
        returnedId != null &&
        String(returnedId) !== String(patientId)
      ) {
        throw new Error(
          "The returned patient ID does not match the selected patient."
        );
      }

      const visit = matchVisit(patient, visitId);

      if (!visit) {
        throw new Error(
          "The selected visit was not returned by the API. No other visit has been substituted."
        );
      }

      state.patient = patient;
      state.visit = visit;
      state.measurements =
        normalizeMeasurements(payload, visit);
      state.medicines =
        normalizeMedicines(payload, visit);
      state.issues = [];

      renderPatientDetail(payload, patient, visit);
      setEditLinks();
    } catch (error) {
      console.error(
        "Unable to load selected patient:",
        error
      );

      showAlert(
        error?.message ||
          "The saved patient visit could not be loaded."
      );

      $("detailPatientName").textContent =
        "Record unavailable";

      $("databaseStatus").textContent =
        "Unable to verify";
    }
  }

  function normalizeMeasurements(payload, visit) {
    const sources = [
      visit?.observations,
      visit?.measurements,
      visit?.laboratory_results,
      visit?.clinical_data?.observations,
      visit?.clinical_entry?.observations,
      payload?.observations,
      payload?.measurements,
      payload?.laboratory_results,
      payload?.clinical_entry?.observations
    ];

    const array = sources.find(Array.isArray);

    if (array) {
      return array.map((item) => ({
        label: first(
          item?.label,
          item?.display_name,
          item?.test_name,
          item?.name,
          item?.key,
          "Clinical test"
        ),
        key: first(
          item?.key,
          item?.code,
          item?.name,
          item?.test_name,
          ""
        ),
        value: first(
          item?.value,
          item?.result,
          item?.numeric_value,
          item?.observed_value
        ),
        unit: first(item?.unit, item?.units, ""),
        date: first(
          item?.date,
          item?.test_date,
          item?.observed_at,
          item?.recorded_at
        ),
        source: first(
          item?.source,
          item?.source_document_name,
          item?.document_name,
          ""
        )
      }));
    }

    const flat = first(
      visit?.clinical_data,
      visit?.clinical_entry,
      payload?.clinical_data,
      payload?.clinical_entry,
      visit
    );

    if (!object(flat)) return [];

    const definitions = [
      ["Blood pressure", ["blood_pressure", "bloodPressure", "bp"], "mmHg"],
      ["Height", ["height", "height_cm"], "cm"],
      ["Weight", ["weight", "weight_kg"], "kg"],
      ["BMI", ["bmi", "BMI"], "kg/m²"],
      ["Serum creatinine", ["creatinine", "serum_creatinine"], "mg/dL"],
      ["eGFR", ["egfr", "eGFR", "estimated_gfr"], "mL/min/1.73 m²"],
      ["uACR", ["uacr", "uACR", "urine_acr", "albumin_creatinine_ratio"], "mg/g"],
      ["BUN", ["bun", "BUN", "blood_urea_nitrogen"], "mg/dL"],
      ["HbA1c", ["hba1c", "HbA1c", "hemoglobin_a1c"], "%"],
      ["Sodium", ["sodium", "na", "Na"], "mmol/L"],
      ["Potassium", ["potassium", "k", "K"], "mmol/L"],
      ["Chloride", ["chloride", "cl", "Cl"], "mmol/L"],
      ["Bicarbonate", ["bicarbonate", "hco3", "HCO3"], "mmol/L"],
      ["Hemoglobin", ["hemoglobin", "haemoglobin", "hb", "Hb"], "g/dL"]
    ];

    return definitions
      .map(([label, keys, unit]) => ({
        label,
        key: keys[0],
        value: read(flat, keys),
        unit: first(
          read(flat, [
            `${keys[0]}_unit`,
            `${keys[0]}_units`
          ]),
          unit
        ),
        date: first(
          read(flat, [
            `${keys[0]}_date`,
            "test_date",
            "observed_at"
          ]),
          visit?.visit_date
        ),
        source: ""
      }))
      .filter(
        (item) =>
          item.value !== undefined &&
          item.value !== null &&
          item.value !== ""
      );
  }

  function normalizeMedicines(payload, visit) {
    const candidates = [
      visit?.medicines,
      visit?.medications,
      visit?.visit_medications,
      visit?.clinical_data?.medicines,
      payload?.medicines,
      payload?.medications
    ];

    return candidates.find(Array.isArray) || [];
  }

  function renderPatientDetail(payload, patient, visit) {
    const name = getPatientName(patient);
    const id = getPatientId(patient);
    const visitId = getVisitId(visit);

    $("detailPatientName").textContent =
      text(name, "Name not recorded");

    $("detailPatientId").textContent = text(id);
    $("detailVisitId").textContent = text(visitId);
    $("patientInitials").textContent = initials(name);

    const visitDate = first(
      visit?.visit_date,
      visit?.date,
      visit?.created_at
    );

    const reason = first(
      visit?.visit_reason,
      visit?.reason,
      visit?.chief_complaint
    );

    $("detailVisitSummary").textContent =
      `${date(visitDate)} · ${text(reason, "Visit reason not recorded")}`;

    const status = first(
      visit?.status,
      payload?.status,
      "Status unavailable"
    );

    const statusBadge = $("visitStatusBadge");

    statusBadge.textContent = status;
    statusBadge.className =
      `rv-status-badge ${statusClass(status)}`;

    setText("vName", name);
    setText("vPatientId", id);
    setText("vAge", first(patient?.age, patient?.patient_age));
    setText("vSex", first(patient?.sex, patient?.gender));
    setText("vVisitDate", date(visitDate));
    setText("vVisitReason", reason);

    if (!name) {
      state.issues.push({
        message: "Patient name is missing.",
        error: true
      });
    }

    if (!id) {
      state.issues.push({
        message: "Patient ID is missing.",
        error: true
      });
    }

    if (!visitId) {
      state.issues.push({
        message: "Visit ID is missing.",
        error: true
      });
    }

    const historyValues = [
      [
        "vDiabetes",
        "Diabetes",
        first(visit?.diabetes, patient?.diabetes)
      ],
      [
        "vHypertension",
        "Hypertension",
        first(visit?.hypertension, patient?.hypertension)
      ],
      [
        "vHeartDisease",
        "Heart disease",
        first(visit?.heart_disease, patient?.heart_disease)
      ],
      [
        "vFamilyHistory",
        "Family history of kidney disease",
        first(
          visit?.family_hx_kidney,
          visit?.family_history_kidney,
          patient?.family_hx_kidney,
          patient?.family_history_kidney
        )
      ]
    ];

    let missingHistory = 0;

    historyValues.forEach(([elementId, label, value]) => {
      setText(elementId, yesNo(value));

      if (
        value === undefined ||
        value === null ||
        value === ""
      ) {
        missingHistory++;

        state.issues.push({
          message: `${label} is not recorded.`
        });
      }
    });

    setSectionStatus(
      "historyStatus",
      missingHistory ? `${missingHistory} missing` : "Recorded",
      missingHistory > 0
    );

    renderMeasurements(state.measurements);
    renderMedicines(state.medicines, visit, payload);
    renderDocument(payload, patient, visit);
    renderNotes(payload, visit);

    // This endpoint returned the saved record.
    // No separate write operation occurred during page load.
    $("databaseStatus").textContent = "Record retrieved from API";

    $("doctorStatus").textContent = text(
      first(
        visit?.review_status,
        visit?.status,
        payload?.review_status
      ),
      "Not submitted"
    );

    setSectionStatus(
      "identityStatus",
      name && id && visitId
        ? "Identity loaded"
        : "Check identity",
      !name || !id || !visitId
    );

    updateValidationSummary();
    updateCompleteness();
    updateSubmitAvailability();
  }

  function yesNo(value) {
    if (
      value === undefined ||
      value === null ||
      value === ""
    ) {
      return "Not recorded";
    }

    if (value === true) return "Yes";
    if (value === false) return "No";

    const normalized = String(value).trim().toLowerCase();

    if (
      ["yes", "true", "1", "positive", "present"].includes(normalized)
    ) {
      return "Yes";
    }

    if (
      ["no", "false", "0", "negative", "absent"].includes(normalized)
    ) {
      return "No";
    }

    return String(value);
  }

  function setSectionStatus(id, label, warning) {
    const node = $(id);

    node.textContent = label;
    node.className =
      `rv-section-status ${warning ? "is-warning" : "is-good"}`;
  }

  function validateMeasurement(item) {
    if (
      item.value === undefined ||
      item.value === null ||
      String(item.value).trim() === ""
    ) {
      return {
        label: "Missing",
        className: "is-warning"
      };
    }

    const key = String(item.key || item.label).toLowerCase();

    if (/blood.?pressure|^bp$/.test(key)) {
      const match = String(item.value).match(
        /^\s*(\d{2,3})\s*\/\s*(\d{2,3})\s*$/
      );

      if (!match) {
        return {
          label: "Check format",
          className: "is-error"
        };
      }

      const systolic = Number(match[1]);
      const diastolic = Number(match[2]);

      if (
        systolic < 40 ||
        systolic > 300 ||
        diastolic < 20 ||
        diastolic > 200
      ) {
        return {
          label: "Check value",
          className: "is-error"
        };
      }

      return {
        label: "Recorded",
        className: "is-good"
      };
    }

    // Flag non-numeric values only for expected numeric measurements.
    const numericNames =
      /height|weight|bmi|creatinine|egfr|uacr|albumin.creatinine|bun|hba1c|sodium|potassium|chloride|bicarbonate|hemoglobin/i;

    if (numericNames.test(key)) {
      const number = Number(item.value);

      if (!Number.isFinite(number)) {
        return {
          label: "Check value",
          className: "is-error"
        };
      }

      if (number < 0) {
        return {
          label: "Check value",
          className: "is-error"
        };
      }
    }

    return {
      label: "Recorded",
      className: "is-good"
    };
  }

  function renderMeasurements(measurements) {
    const body = $("measurementsBody");

    body.replaceChildren();

    if (!measurements.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");

      cell.colSpan = 5;
      cell.className = "rv-empty-cell";
      cell.textContent =
        "No saved measurements were returned by the API.";

      row.appendChild(cell);
      body.appendChild(row);

      state.issues.push({
        message:
          "No clinical measurements were returned. Check the saved visit and API response."
      });

      setSectionStatus(
        "measurementStatus",
        "No values returned",
        true
      );

      return;
    }

    let missing = 0;
    let invalid = 0;

    measurements.forEach((item) => {
      const result = validateMeasurement(item);
      const row = document.createElement("tr");

      const cells = [
        item.label,
        text(item.value),
        text(item.unit, "Not specified"),
        date(item.date)
      ];

      cells.forEach((value) => {
        const cell = document.createElement("td");

        cell.textContent = value;
        row.appendChild(cell);
      });

      const statusCell = document.createElement("td");
      const badge = document.createElement("span");

      badge.className =
        `rv-value-state ${result.className}`;

      badge.textContent = result.label;

      statusCell.appendChild(badge);
      row.appendChild(statusCell);
      body.appendChild(row);

      if (result.label === "Missing") {
        missing++;
      }

      if (result.className === "is-error") {
        invalid++;

        state.issues.push({
          message:
            `${item.label} needs checking. Verify the value and unit against its source.`,
          error: true
        });
      }
    });

    const warningCount = missing + invalid;

    setSectionStatus(
      "measurementStatus",
      warningCount
        ? `${warningCount} to check`
        : "Values recorded",
      warningCount > 0
    );
  }

  function renderMedicines(medicines, visit, payload) {
    const list = $("medicinesList");

    list.replaceChildren();

    if (!medicines.length) {
      const note = document.createElement("p");

      note.className = "rv-muted";
      note.textContent =
        "No medicines were returned by the API for this visit.";

      list.appendChild(note);

      state.issues.push({
        message:
          "No medicine entries were returned. Confirm whether any medicines were recorded for this visit."
      });
    } else {
      medicines.forEach((medicine) => {
        const card = document.createElement("article");

        card.className = "rv-medicine-card";

        const name = document.createElement("strong");

        name.textContent = text(
          first(
            medicine?.name,
            medicine?.medicine_name,
            medicine?.drug_name,
            medicine?.medication
          ),
          "Medicine name not recorded"
        );

        const details = document.createElement("p");

        details.textContent = [
          first(
            medicine?.dose,
            medicine?.dosage,
            medicine?.strength
          )
            ? `Dose: ${first(
                medicine?.dose,
                medicine?.dosage,
                medicine?.strength
              )}`
            : "",

          first(
            medicine?.frequency,
            medicine?.intake_frequency
          )
            ? `Frequency: ${first(
                medicine?.frequency,
                medicine?.intake_frequency
              )}`
            : "",

          first(
            medicine?.duration,
            medicine?.duration_days
          )
            ? `Duration: ${first(
                medicine?.duration,
                medicine?.duration_days
              )}`
            : "",

          first(
            medicine?.instructions,
            medicine?.notes
          )
            ? `Instructions: ${first(
                medicine?.instructions,
                medicine?.notes
              )}`
            : ""
        ]
          .filter(Boolean)
          .join(" · ") || "No additional details recorded.";

        card.append(name, details);
        list.appendChild(card);
      });
    }

    const notes = first(
      visit?.notes,
      visit?.visit_notes,
      visit?.symptoms,
      visit?.chief_complaint,
      payload?.notes
    );

    const intakeNotes = first(
      visit?.intake_notes,
      visit?.medicine_intake_notes,
      payload?.intake_notes
    );

    const followup = first(
      visit?.follow_up,
      visit?.followup,
      visit?.follow_up_details,
      visit?.followup_details,
      payload?.follow_up_details
    );

    setText("vNotes", notes);
    setText("vIntakeNotes", intakeNotes);
    setText("vFollowup", followup);

    if (!notes) {
      state.issues.push({
        message: "Symptoms or visit notes are not recorded."
      });
    }

    if (!followup) {
      state.issues.push({
        message: "Follow-up details are not recorded."
      });
    }

    setSectionStatus(
      "notesStatus",
      !notes || !followup
        ? "Check notes"
        : "Recorded",
      !notes || !followup
    );
  }

  // Use only the actual document URL returned by the API.
  function findDocument(payload, patient, visit) {
    const candidates = [
      visit?.source_document,
      visit?.uploaded_document,
      visit?.document,
      visit?.report,
      visit?.source_report,
      patient?.source_document,
      patient?.uploaded_document,
      payload?.source_document,
      payload?.uploaded_document,
      payload?.document,
      payload?.report
    ].filter(Boolean);

    for (const item of candidates) {
      if (typeof item === "string") {
        return {
          url: item,
          name: "Original uploaded report"
        };
      }

      if (!object(item)) continue;

      const url = first(
        item.url,
        item.file_url,
        item.document_url,
        item.download_url,
        item.preview_url,
        item.public_url
      );

      if (url) {
        return {
          url,
          name: first(
            item.original_filename,
            item.file_name,
            item.filename,
            item.name,
            "Original uploaded report"
          ),
          date: first(
            item.uploaded_at,
            item.created_at,
            item.document_date
          ),
          mime: first(
            item.mime_type,
            item.content_type,
            item.file_type,
            ""
          )
        };
      }
    }

    // Some APIs return a direct file path on the visit.
    const directUrl = first(
      visit?.source_document_url,
      visit?.document_url,
      visit?.report_url,
      visit?.file_url,
      payload?.source_document_url,
      payload?.document_url,
      payload?.report_url
    );

    if (directUrl) {
      return {
        url: directUrl,
        name: first(
          visit?.document_name,
          visit?.file_name,
          "Original uploaded report"
        ),
        date: first(
          visit?.document_uploaded_at,
          visit?.created_at
        ),
        mime: first(
          visit?.document_mime_type,
          visit?.mime_type,
          ""
        )
      };
    }

    return null;
  }

  function renderDocument(payload, patient, visit) {
    const image = $("documentImage");
    const pdf = $("documentPdf");
    const placeholder = $("documentPlaceholder");
    const meta = $("documentMeta");
    const openLink = $("openOriginalDocument");

    image.hidden = true;
    image.removeAttribute("src");

    pdf.hidden = true;
    pdf.removeAttribute("src");

    meta.hidden = true;
    placeholder.hidden = false;

    const documentInfo =
      findDocument(payload, patient, visit);

    if (!documentInfo?.url) {
      placeholder.querySelector("strong").textContent =
        "No report preview available";

      placeholder.querySelector("p").textContent =
        "The saved visit API did not return a stored document URL. No image has been substituted.";

      return;
    }

    const url = documentInfo.url;

    // Accept only relative same-app paths or HTTP(S) URLs.
    let safeUrl;

    try {
      const parsed = new URL(
        url,
        window.location.origin
      );

      if (!["http:", "https:"].includes(parsed.protocol)) {
        throw new Error(
          "Unsupported document URL protocol."
        );
      }

      safeUrl = parsed.href;
    } catch {
      placeholder.querySelector("strong").textContent =
        "Document URL is invalid";

      placeholder.querySelector("p").textContent =
        "The API returned a document location that cannot safely be previewed.";

      return;
    }

    const fileName =
      String(documentInfo.name || "").toLowerCase();

    const mime =
      String(documentInfo.mime || "").toLowerCase();

    const isPdf =
      mime.includes("pdf") ||
      fileName.endsWith(".pdf") ||
      /\.pdf(?:$|[?#])/i.test(safeUrl);

    placeholder.hidden = true;
    meta.hidden = false;

    $("documentName").textContent =
      documentInfo.name;

    $("documentDate").textContent =
      documentInfo.date
        ? `Uploaded: ${date(documentInfo.date)}`
        : "Upload date not returned by API";

    openLink.href = safeUrl;

    if (isPdf) {
      pdf.hidden = false;
      pdf.src = safeUrl;
    } else {
      image.hidden = false;

      image.alt =
        `Original uploaded report: ${documentInfo.name}`;

      image.addEventListener(
        "error",
        () => {
          image.hidden = true;
          placeholder.hidden = false;

          placeholder.querySelector("strong").textContent =
            "Report preview could not be loaded";

          placeholder.querySelector("p").textContent =
            "The stored URL exists, but the browser could not retrieve the file. Check the document endpoint and access permissions.";
        },
        { once: true }
      );

      image.src = safeUrl;
    }
  }

  function renderNotes(payload, visit) {
    // Notes are rendered by renderMedicines().
    // This function is retained for compatibility with the existing flow.
  }

  function updateCompleteness() {
    const patient = state.patient;
    const visit = state.visit;

    if (!patient || !visit) return;

    const checks = [
      Boolean(getPatientId(patient)),
      Boolean(getPatientName(patient)),
      Boolean(
        first(
          patient.age,
          patient.patient_age,
          patient.birth_date
        )
      ),
      Boolean(first(patient.sex, patient.gender)),
      Boolean(getVisitId(visit)),
      Boolean(
        first(
          visit.visit_date,
          visit.date,
          visit.created_at
        )
      ),
      Boolean(
        first(
          visit.reason,
          visit.visit_reason,
          visit.chief_complaint
        )
      ),
      state.measurements.length > 0
    ];

    const completed = checks.filter(Boolean).length;
    const percent = Math.round(
      (completed / checks.length) * 100
    );

    $("completionPercent").textContent = `${percent}%`;

    $("completionText").textContent =
      `${completed} of ${checks.length} basic information checks present`;

    $("completionBar").style.width = `${percent}%`;

    const progress = $("completionProgress");

    progress.setAttribute(
      "aria-valuenow",
      String(percent)
    );
  }

  function updateValidationSummary() {
    const list = $("validationList");

    list.replaceChildren();

    $("validationCount").textContent =
      state.issues.length
        ? `${state.issues.length} item(s) to review`
        : "Basic checks passed";

    $("validationMessage").textContent =
      state.issues.length
        ? "Review these warnings and correct errors before submission."
        : "No obvious missing identity details or invalid values were detected by these checks.";

    if (!state.issues.length) {
      const item = document.createElement("li");

      item.className = "is-good";

      item.textContent =
        "No issues were found by the basic checks performed on this page.";

      list.appendChild(item);

      return;
    }

    state.issues.forEach((issue) => {
      const item = document.createElement("li");

      item.className = issue.error ? "is-error" : "";
      item.textContent = issue.message;

      list.appendChild(item);
    });
  }

  function updateSubmitAvailability() {
    const confirmed = $("confirmAccuracy").checked;

    const hasMethod =
      typeof window.Api?.submitVisitForDoctorReview === "function";

    const hasIdentity = Boolean(
      state.patient &&
      state.visit &&
      getPatientId(state.patient) &&
      getVisitId(state.visit)
    );

    const hasBlockingErrors =
      state.issues.some((issue) => issue.error);

    $("submitForReviewButton").disabled =
      !confirmed ||
      !hasMethod ||
      !hasIdentity ||
      hasBlockingErrors ||
      state.submitting;

    if (!hasMethod) {
      $("submitHelp").textContent =
        "Submission is unavailable because the existing API client does not expose submitVisitForDoctorReview(). Review and edit the record, but no submission can be performed by this page yet.";
    } else if (hasBlockingErrors) {
      $("submitHelp").textContent =
        "Correct blocking identity or measurement errors in Clinical Data Entry before submitting.";
    } else if (!confirmed) {
      $("submitHelp").textContent =
        "Check the patient and visit information, then tick the confirmation box.";
    } else {
      $("submitHelp").textContent =
        "The record is ready for the configured doctor-review submission action.";
    }
  }

  $("confirmAccuracy").addEventListener(
    "change",
    updateSubmitAvailability
  );

  $("refreshDetailButton").addEventListener("click", () => {
    const id = getPatientId(state.patient);
    const visitId = getVisitId(state.visit);

    if (id && visitId) {
      openPatient(id, visitId);
    }
  });

  // ---------- Submit confirmation ----------

  function openModal() {
    if ($("submitForReviewButton").disabled) return;

    $("modalPatientName").textContent =
      text(getPatientName(state.patient));

    $("modalPatientId").textContent =
      text(getPatientId(state.patient));

    $("modalVisitId").textContent =
      text(getVisitId(state.visit));

    $("submitModal").hidden = false;

    $("cancelSubmitButton").focus();
  }

  function closeModal() {
    const modal = $("submitModal");

    if (!modal || modal.hidden) return;

    modal.hidden = true;
    $("submitForReviewButton").focus();
  }

  $("submitForReviewButton").addEventListener(
    "click",
    openModal
  );

  $("cancelSubmitButton").addEventListener(
    "click",
    closeModal
  );

  $("submitModal").addEventListener("click", (event) => {
    if (
      event.target === $("submitModal") &&
      !state.submitting
    ) {
      closeModal();
    }
  });

  $("confirmSubmitButton").addEventListener(
    "click",
    async () => {
      if (
        state.submitting ||
        $("submitForReviewButton").disabled
      ) {
        return;
      }

      if (
        typeof window.Api?.submitVisitForDoctorReview !== "function"
      ) {
        closeModal();

        showAlert(
          "Submission was not performed. The existing API client has no submitVisitForDoctorReview() method. No success has been assumed."
        );

        return;
      }

      state.submitting = true;

      $("confirmSubmitButton").disabled = true;
      $("confirmSubmitButton").textContent = "Submitting…";

      $("submitForReviewButton").disabled = true;

      try {
        const patientId = getPatientId(state.patient);
        const visitId = getVisitId(state.visit);

        const result =
          await window.Api.submitVisitForDoctorReview(
            patientId,
            visitId
          );

        if (
          !result ||
          (
            result.success !== true &&
            result.submitted !== true
          )
        ) {
          throw new Error(
            result?.message ||
              "The backend did not confirm that the visit was submitted."
          );
        }

        closeModal();

        toast(
          "The backend confirmed submission for doctor review."
        );

        $("doctorStatus").textContent = text(
          result.status,
          "Submitted for doctor review"
        );

        $("visitStatusBadge").textContent = text(
          result.status,
          "Submitted for doctor review"
        );

        $("visitStatusBadge").className =
          `rv-status-badge ${statusClass(
            result.status || "submitted"
          )}`;

        $("confirmAccuracy").checked = false;

        $("submitHelp").textContent =
          "Submission was confirmed by the backend. Check the displayed status after refreshing.";

        // Reload from the API to display the server's
        // actual persisted status.
        await openPatient(patientId, visitId);
      } catch (error) {
        console.error(
          "Doctor-review submission failed:",
          error
        );

        closeModal();

        showAlert(
          error?.message ||
            "Submission could not be confirmed. Check the saved record and try again."
        );

        toast(
          "Submission was not confirmed.",
          true
        );
      } finally {
        state.submitting = false;

        $("confirmSubmitButton").disabled = false;
        $("confirmSubmitButton").textContent =
          "Confirm submission";

        updateSubmitAvailability();
      }
    }
  );

  // ---------- Initial route ----------

  if (initialPatientId) {
    if (initialVisitId) {
      openPatient(initialPatientId, initialVisitId);
    } else {
      showListView();
      loadPatients();

      showAlert(
        "A patient ID was provided without a visit ID. Select the exact visit before editing or submitting."
      );
    }
  } else {
    showListView();
    loadPatients();
  }
});
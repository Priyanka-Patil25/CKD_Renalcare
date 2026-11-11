
/* public/js/api.js
 * API client for RenalCare.
 * All requests use the current authenticated session.
 */
(function () {
  "use strict";

  const KEY = "rc_auth";

  // --------------------------------------------------------
  // AUTHENTICATION
  // --------------------------------------------------------

  const auth = () => {
    try {
      return JSON.parse(sessionStorage.getItem(KEY) || "null");
    } catch {
      return null;
    }
  };

  // --------------------------------------------------------
  // SHARED API REQUEST HANDLER
  // --------------------------------------------------------

  async function req(method, url, body) {
    const currentAuth = auth();

    const response = await fetch(url, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(currentAuth?.token
          ? { Authorization: "Bearer " + currentAuth.token }
          : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

    // Redirect to login when the authenticated session expires.
    if (response.status === 401 && !url.endsWith("/api/login")) {
      sessionStorage.removeItem(KEY);
      window.location.href = "/index.html";
      throw new Error("Your session expired. Please log in again.");
    }

    let data = null;

    try {
      data = await response.json();
    } catch {
      // Some responses may have no JSON body.
    }

    if (!response.ok) {
      const detail = data?.detail;

      throw new Error(
        typeof detail === "string"
          ? detail
          : `Request failed (${response.status}).`
      );
    }

    return data;
  }

  // --------------------------------------------------------
  // API METHODS
  // --------------------------------------------------------

  window.Api = {
    // ------------------------------------------------------
    // AUTHENTICATION
    // ------------------------------------------------------

    auth,

    login: async (username, password) => {
      const result = await req("POST", "/api/login", {
        username,
        password,
      });

      sessionStorage.setItem(KEY, JSON.stringify(result));
      return result;
    },

    logout: () => {
      sessionStorage.removeItem(KEY);
      window.location.href = "/index.html";
    },

    requireRole: (role) => {
      const currentAuth = auth();

      if (
        !currentAuth ||
        (currentAuth.role !== role && currentAuth.role !== "admin")
      ) {
        window.location.href =
          role === "doctor"
            ? "/doctor-login.html"
            : "/reception-login.html";

        return null;
      }

      return currentAuth;
    },

    // ------------------------------------------------------
    // QUEUE AND PATIENT REGISTRATION
    // ------------------------------------------------------

    getQueue: () =>
      req("GET", "/api/queue"),

    registerPatient: (data) =>
      req("POST", "/api/patients", data),

    searchPatients: (query = "") =>
      req(
        "GET",
        "/api/patients/search?q=" + encodeURIComponent(query)
      ),

    // ------------------------------------------------------
    // RECEPTIONIST — CLINICAL DATA ENTRY
    // ------------------------------------------------------

    // Load patient demographics, conditions, and recent visits.
    getPatientIntake: (id) =>
      req(
        "GET",
        `/api/patients/${encodeURIComponent(id)}/intake`
      ),

    // Save clinical observations, conditions, medicines, and notes.
    saveClinicalEntry: (id, body) =>
      req(
        "POST",
        `/api/patients/${encodeURIComponent(id)}/clinical-entry`,
        body
      ),

    /*
     * Update clinical information for an existing visit.
     *
     * This currently uses the same endpoint as saveClinicalEntry.
     * The backend must support updating the existing visit when
     * body includes its visit_id. Otherwise, a dedicated backend
     * update endpoint will be needed.
     */
    updateClinicalEntry: (id, body) =>
      req(
        "POST",
        `/api/patients/${encodeURIComponent(id)}/clinical-entry`,
        body
      ),

    /*
     * Submit a visit for doctor review.
     *
     * Requires this backend endpoint to exist:
     * POST /api/patients/{patient_id}/visits/{visit_id}/submit-review
     */
    submitVisitForDoctorReview: (patientId, visitId) =>
      req(
        "POST",
        `/api/patients/${encodeURIComponent(patientId)}` +
          `/visits/${encodeURIComponent(visitId)}/submit-review`
      ),

    // ------------------------------------------------------
    // PATIENT HISTORY
    // ------------------------------------------------------

    getPatient: (id) =>
      req(
        "GET",
        `/api/patients/${encodeURIComponent(id)}`
      ),

    // ------------------------------------------------------
    // DOCTOR — VISIT WORKFLOW
    // ------------------------------------------------------

    startVisit: (visitId) =>
      req(
        "POST",
        `/api/visits/${encodeURIComponent(visitId)}/start`
      ),

    saveConsultationNotes: (visitId, body) =>
      req(
        "POST",
        `/api/visits/${encodeURIComponent(visitId)}/notes`,
        { body }
      ),

    completeConsultation: (visitId) =>
      req(
        "POST",
        `/api/visits/${encodeURIComponent(visitId)}/complete`
      ),

    // ------------------------------------------------------
    // DOCTOR — CARE-GAP DECISIONS
    // ------------------------------------------------------

    decideFlag: (id, status, edited_text) =>
      req(
        "POST",
        `/api/flags/${encodeURIComponent(id)}/decision`,
        {
          status,
          edited_text,
        }
      ),

    // ------------------------------------------------------
    // DOCTOR — CLINICAL RESULTS
    // ------------------------------------------------------

    addResults: (id, body) =>
      req(
        "POST",
        `/api/patients/${encodeURIComponent(id)}/results`,
        body
      ),

    // ------------------------------------------------------
    // CKD SCREENING MODEL
    // ------------------------------------------------------

    runScreening: (inputs) =>
      req("POST", "/api/screening", inputs),

    model: () =>
      req("GET", "/api/model"),

    // ------------------------------------------------------
    // KDIGO RISK GRID
    // ------------------------------------------------------

    grid: () =>
      req("GET", "/api/kdigo/grid"),

    // ------------------------------------------------------
    // RAG — GUIDELINE RETRIEVAL
    // ------------------------------------------------------

    queryRag: (question, patient_id) =>
      req("POST", "/api/rag/ask", {
        question,
        patient_id,
      }),

    // ------------------------------------------------------
    // DOCTOR — PATIENT SUMMARY / AGENT WORKFLOW
    // ------------------------------------------------------

    brief: (id) =>
      req(
        "POST",
        `/api/patients/${encodeURIComponent(id)}/brief`
      ),

    // Four-agent workspace (Clinical Data, Risk Assessment, Clinical Management, Diet Recommendation).
    runPipeline: (id) => req("POST", `/api/patients/${encodeURIComponent(id)}/pipeline`),
    lastPipeline: (id) => req("GET", `/api/patients/${encodeURIComponent(id)}/pipeline`),

    // Agent briefing: the agent picks read-only tools and writes a briefing.
    // Response: { answer, trace[], steps, finished, verification{ok,problems,checked}, brain }
    runAgent: (id) =>
      req(
        "POST",
        `/api/patients/${encodeURIComponent(id)}/agent`
      ),

    // Lab-report reader: proposes values from pasted text. Saves nothing.
    // Response: { proposed[{code,value,unit,from_line,warning}], report_date, note }
    proposeLabs: (id, text) =>
      req(
        "POST",
        `/api/patients/${encodeURIComponent(id)}/labs/propose`,
        { text }
      ),
  };
})();

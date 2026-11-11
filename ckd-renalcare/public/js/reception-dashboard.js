/*
 * RenalCare Reception Dashboard
 * Uses the existing authentication, queue and patient-search APIs.
 * No sample patients, invented statuses, or clinical predictions.
 */

document.addEventListener("DOMContentLoaded", () => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) =>
    Array.from(root.querySelectorAll(selector));

  const sidebar = $("#rd-sidebar");
  const overlay = $("#rd-overlay");
  const menuToggle = $("#rd-menu-toggle");
  const searchInput = $("#global-search");
  const searchFeedback = $("#search-feedback");
  const chartContainer = $("#queue-chart");
  const patientQueue = $("#rd-patient-queue");
  const queueBadge = $("#rd-sidebar-queue-count");

  const reducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  let searchTimer = null;
  let searchRequestId = 0;

  const escapeHTML = (value) =>
    String(value ?? "").replace(/[&<>"']/g, (character) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[character]);

  const setFeedback = (message, type = "") => {
    if (!searchFeedback) return;

    searchFeedback.textContent = message;
    searchFeedback.classList.toggle("is-error", type === "error");
    searchFeedback.classList.toggle("is-success", type === "success");
  };

  const normalizeStatus = (value) =>
    String(value ?? "")
      .trim()
      .toLowerCase()
      .replace(/[_-]+/g, " ")
      .replace(/\s+/g, " ");

  const getPatientStatus = (patient) =>
    normalizeStatus(
      patient?.status ??
      patient?.visit_status ??
      patient?.queue_status
    );

  /*
   * Status groups are presentation categories, not new backend statuses.
   * Unknown statuses remain visible as "Other / unclassified".
   */
  const statusGroup = (status) => {
    if (
      /complete|completed|finished|visit done|closed/.test(status)
    ) {
      return "complete";
    }

    if (
      /doctor review|with doctor|submitted|awaiting doctor|under review/.test(status)
    ) {
      return "review";
    }

    if (
      /in progress|processing|intake|being seen|consultation|ongoing/.test(status)
    ) {
      return "progress";
    }

    if (
      /waiting|checked in|checked-in|queued|registered|pending|arrived/.test(status)
    ) {
      return "waiting";
    }

    return "other";
  };

  const formatStatus = (status) => {
    if (!status) return "Status unavailable";
    if (status === "unknown") return "Unknown status";

    return status.replace(/\b\w/g, (letter) => letter.toUpperCase());
  };

  const setStat = (name, value) => {
    const element = $(`[data-stat="${name}"]`);
    if (!element) return;

    if (typeof value !== "number" || !Number.isFinite(value)) {
      element.textContent = "—";
      return;
    }

    if (reducedMotion) {
      element.textContent = String(value);
      return;
    }

    const duration = 420;
    const startTime = performance.now();

    const tick = (now) => {
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);

      element.textContent = String(Math.round(value * eased));

      if (progress < 1) requestAnimationFrame(tick);
    };

    requestAnimationFrame(tick);
  };

  const resetStats = () => {
    setStat("checked-in", null);
    setStat("intake", null);
    setStat("verification", null);
    setStat("doctor-review", null);

    if (queueBadge) {
      queueBadge.hidden = true;
      queueBadge.textContent = "";
    }
  };

  // ---------------- Mobile navigation ----------------

  const closeMenu = () => {
    sidebar?.classList.remove("is-open");
    overlay?.classList.remove("is-visible");

    if (overlay) overlay.hidden = true;

    menuToggle?.setAttribute("aria-expanded", "false");
    menuToggle?.setAttribute("aria-label", "Open navigation");
    document.body.classList.remove("rd-nav-open");
  };

  const openMenu = () => {
    if (!sidebar || !overlay) return;

    sidebar.classList.add("is-open");
    overlay.hidden = false;

    requestAnimationFrame(() => overlay.classList.add("is-visible"));

    menuToggle?.setAttribute("aria-expanded", "true");
    menuToggle?.setAttribute("aria-label", "Close navigation");
    document.body.classList.add("rd-nav-open");
  };

  menuToggle?.addEventListener("click", () => {
    sidebar?.classList.contains("is-open") ? closeMenu() : openMenu();
  });

  overlay?.addEventListener("click", closeMenu);

  $$(".rd-nav-link", sidebar || document).forEach((link) => {
    link.addEventListener("click", closeMenu);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu();
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 900) closeMenu();
  });

  // ---------------- Entrance animations ----------------

  const revealItems = $$(
    ".rd-welcome, .rd-section-heading, .rd-action-card, " +
    ".rd-stat-card, .rd-panel, .rd-footer"
  );

  revealItems.forEach((item, index) => {
    item.classList.add("rd-reveal");
    item.style.setProperty("--rd-reveal-delay", `${(index % 4) * 50}ms`);
  });

  if (reducedMotion || !("IntersectionObserver" in window)) {
    revealItems.forEach((item) => item.classList.add("is-revealed"));
  } else {
    const observer = new IntersectionObserver(
      (entries, currentObserver) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-revealed");
            currentObserver.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08, rootMargin: "0px 0px -20px 0px" }
    );

    revealItems.forEach((item) => observer.observe(item));
  }

  // ---------------- Date and session ----------------

  const dateElement = $("#today-date");

  if (dateElement) {
    dateElement.textContent = new Intl.DateTimeFormat(undefined, {
      weekday: "short",
      day: "numeric",
      month: "short",
      year: "numeric"
    }).format(new Date());
  }

  if (!window.Api?.requireRole) {
    resetStats();

    if (patientQueue) {
      patientQueue.textContent =
        "Authentication service is unavailable. Please sign in again.";
      patientQueue.classList.add("rd-queue-error");
    }

    setFeedback(
      "Authentication service is unavailable. Please reload or sign in again.",
      "error"
    );
    return;
  }

  let staff;

  try {
    staff = window.Api.requireRole("reception");
    if (!staff) return;
  } catch (error) {
    console.warn("Reception session could not be verified.", error);
    setFeedback(
      "Your reception session could not be verified. Please sign in again.",
      "error"
    );
    return;
  }

  const staffName =
    typeof staff?.name === "string" && staff.name.trim()
      ? staff.name.trim()
      : "Reception staff";

  const staffNameElement = $("#rd-staff-name");
  const avatarElement = $("#rd-avatar");

  if (staffNameElement) staffNameElement.textContent = staffName;

  if (avatarElement) {
    avatarElement.textContent = staffName
      .split(/\s+/)
      .slice(0, 2)
      .map((part) => part.charAt(0))
      .join("")
      .toUpperCase() || "RS";
  }

  // ---------------- Logout ----------------

  $("#rd-logout")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;

    if (!window.Api?.logout) {
      setFeedback(
        "The logout service is unavailable. Use your application's sign-out flow.",
        "error"
      );
      return;
    }

    button.disabled = true;

    try {
      await window.Api.logout();
    } catch (error) {
      console.error("Reception logout failed.", error);
      setFeedback("Logout could not be completed. Please try again.", "error");
      button.disabled = false;
    }
  });

  // ---------------- Queue chart ----------------

  const renderQueueChart = (rows) => {
    if (!chartContainer) return;

    chartContainer.replaceChildren();

    if (!rows.length) {
      const message = document.createElement("p");
      message.className = "rd-empty-chart";
      message.textContent =
        "No queue records were returned. Status counts will appear when records are available.";

      chartContainer.appendChild(message);
      chartContainer.setAttribute("aria-label", "No queue records available");
      return;
    }

    const counts = new Map();

    rows.forEach((patient) => {
      const status = getPatientStatus(patient) || "unknown";
      counts.set(status, (counts.get(status) || 0) + 1);
    });

    const entries = [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6);

    const maximum = Math.max(1, ...entries.map((entry) => entry[1]));

    entries.forEach(([status, count], index) => {
      const row = document.createElement("div");
      row.className = "rd-bar-row";
      row.style.setProperty("--rd-bar-delay", `${index * 60}ms`);

      const label = document.createElement("span");
      label.className = "rd-bar-label";
      label.textContent = formatStatus(status);
      label.title = formatStatus(status);

      const track = document.createElement("span");
      track.className = "rd-bar-track";
      track.setAttribute("aria-hidden", "true");

      const fill = document.createElement("span");
      fill.className = "rd-bar-fill";
      fill.style.setProperty("--rd-bar-width", `${(count / maximum) * 100}%`);

      track.appendChild(fill);

      const countLabel = document.createElement("strong");
      countLabel.className = "rd-bar-count";
      countLabel.textContent = String(count);

      row.append(label, track, countLabel);
      chartContainer.appendChild(row);
    });

    chartContainer.setAttribute(
      "aria-label",
      `Queue status counts: ${entries
        .map(([status, count]) => `${formatStatus(status)}: ${count}`)
        .join("; ")}`
    );
  };

  // ---------------- Patient queue list ----------------

  /*
   * These helpers tolerate common response field names.
   * Confirm the exact response schema from your API if your backend
   * uses different names. No clinical values are inferred here.
   */
  const getPatientName = (patient) => {
    const directName =
      patient?.patient_name ??
      patient?.full_name ??
      patient?.name;

    if (typeof directName === "string" && directName.trim()) {
      return directName.trim();
    }

    const first = patient?.first_name ?? patient?.firstName ?? "";
    const last = patient?.last_name ?? patient?.lastName ?? "";
    const combined = `${first} ${last}`.trim();

    return combined || "Name unavailable";
  };

  const getPatientId = (patient) =>
    patient?.patient_id ??
    patient?.patientId ??
    patient?.id ??
    patient?.mrn ??
    "ID unavailable";

  const getVisitDate = (patient) =>
    patient?.visit_date ??
    patient?.visitDate ??
    patient?.created_at ??
    patient?.createdAt ??
    patient?.date ??
    "";

  const formatVisitDate = (value) => {
    if (!value) return "Not provided";

    const parsed = new Date(value);

    if (Number.isNaN(parsed.getTime())) {
      return String(value);
    }

    return new Intl.DateTimeFormat(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric"
    }).format(parsed);
  };

  const makeQueueMessage = (message, className = "rd-queue-empty") => {
    if (!patientQueue) return;

    patientQueue.replaceChildren();

    const item = document.createElement("div");
    item.className = className;
    item.textContent = message;

    patientQueue.appendChild(item);
  };

  const renderPatientQueue = (rows) => {
    if (!patientQueue) return;

    patientQueue.replaceChildren();

    if (!rows.length) {
      makeQueueMessage(
        "No patients were returned by the queue endpoint. This does not necessarily mean that no patients have appointments or completed visits."
      );
      return;
    }

    rows.forEach((patient, index) => {
      const name = getPatientName(patient);
      const patientId = String(getPatientId(patient));
      const rawStatus = getPatientStatus(patient);
      const statusLabel = formatStatus(rawStatus);
      const group = statusGroup(rawStatus);
      const visitDate = formatVisitDate(getVisitDate(patient));

      const row = document.createElement("article");
      row.className = "rd-patient-row";
      row.style.animationDelay = reducedMotion ? "0ms" : `${Math.min(index, 8) * 45}ms`;

      const identity = document.createElement("div");
      identity.className = "rd-patient-identity";

      const avatar = document.createElement("span");
      avatar.className = "rd-patient-avatar";
      avatar.setAttribute("aria-hidden", "true");
      avatar.textContent = name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part.charAt(0))
        .join("")
        .toUpperCase() || "?";

      const identityCopy = document.createElement("div");
      identityCopy.className = "rd-patient-identity-copy";

      const patientName = document.createElement("strong");
      patientName.className = "rd-patient-name";
      patientName.textContent = name;

      const patientIdLabel = document.createElement("span");
      patientIdLabel.className = "rd-patient-id";
      patientIdLabel.textContent = `Patient ID: ${patientId}`;

      identityCopy.append(patientName, patientIdLabel);
      identity.append(avatar, identityCopy);

      const visitMeta = document.createElement("div");
      visitMeta.className = "rd-queue-meta";

      const visitLabel = document.createElement("span");
      visitLabel.className = "rd-queue-meta-label";
      visitLabel.textContent = "Visit date";

      const visitValue = document.createElement("span");
      visitValue.className = "rd-queue-meta-value";
      visitValue.textContent = visitDate;

      visitMeta.append(visitLabel, visitValue);

      const statusMeta = document.createElement("div");
      statusMeta.className = "rd-queue-meta";

      const statusHeading = document.createElement("span");
      statusHeading.className = "rd-queue-meta-label";
      statusHeading.textContent = "Current status";

      const statusPill = document.createElement("span");
      statusPill.className = `rd-status-pill rd-status-${group}`;
      statusPill.textContent = statusLabel;

      statusMeta.append(statusHeading, statusPill);

      row.append(identity, visitMeta, statusMeta);
      patientQueue.appendChild(row);
    });
  };

  // ---------------- Queue statistics ----------------

  const updateQueueStats = (rows) => {
    setStat("checked-in", rows.length);

    const statuses = rows.map(getPatientStatus);

    const countGroup = (group) =>
      statuses.filter((status) => statusGroup(status) === group).length;

    setStat("intake", countGroup("waiting") + countGroup("progress"));
    setStat("verification", statuses.filter((status) =>
      /needs verification|verification|verify/.test(status)
    ).length);
    setStat("doctor-review", countGroup("review"));

    if (queueBadge) {
      queueBadge.textContent = String(rows.length);
      queueBadge.hidden = false;
    }
  };

  const loadQueue = async () => {
    resetStats();

    if (!window.Api?.getQueue) {
      renderQueueChart([]);
      makeQueueMessage(
        "The queue endpoint is not available through the current API client.",
        "rd-queue-error"
      );
      setFeedback("The queue endpoint is not connected.", "error");
      return;
    }

    if (patientQueue) {
      patientQueue.innerHTML = `
        <div class="rd-queue-loading">
          <span class="rd-loading-spinner" aria-hidden="true"></span>
          <span>Loading queue records…</span>
        </div>`;
    }

    try {
      const response = await window.Api.getQueue();

      if (!Array.isArray(response)) {
        throw new Error(
          "The queue endpoint returned an unexpected response. Expected an array of queue records."
        );
      }

      updateQueueStats(response);
      renderQueueChart(response);
      renderPatientQueue(response);
    } catch (error) {
      console.error("Reception queue could not be loaded.", error);

      resetStats();
      renderQueueChart([]);
      makeQueueMessage(
        "Queue information is currently unavailable. Check your connection and try again.",
        "rd-queue-error"
      );

      setFeedback(
        "Queue information is currently unavailable. Please check the connection and try again.",
        "error"
      );
    }
  };

  // ---------------- Patient search ----------------

  const runSearch = async (query) => {
    const requestId = ++searchRequestId;

    if (query.length < 2) {
      setFeedback("");
      return;
    }

    if (!window.Api?.searchPatients) {
      setFeedback(
        "Patient search is not connected on this page. Open Patients to continue."
      );
      return;
    }

    setFeedback("Searching authorized patient records…");

    try {
      const result = await window.Api.searchPatients(query);

      if (requestId !== searchRequestId) return;

      if (!Array.isArray(result)) {
        throw new Error("Patient search returned an unexpected response.");
      }

      if (result.length === 0) {
        setFeedback(
          "No matching records found. Check the patient name or ID and try again."
        );
        return;
      }

      setFeedback(
        `${result.length} matching record(s) found. Press Enter to open patient search.`,
        "success"
      );
    } catch (error) {
      if (requestId !== searchRequestId) return;

      console.warn("Patient search failed.", error);

      setFeedback(
        error?.message ||
          "Patient search is temporarily unavailable. Please try again.",
        "error"
      );
    }
  };

  searchInput?.addEventListener("input", () => {
    window.clearTimeout(searchTimer);

    const query = searchInput.value.trim();

    if (query.length < 2) {
      ++searchRequestId;
      setFeedback("");
      return;
    }

    searchTimer = window.setTimeout(() => runSearch(query), 300);
  });

  searchInput?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;

    event.preventDefault();

    const query = searchInput.value.trim();
    const destination = query
      ? `/patient-search.html?q=${encodeURIComponent(query)}`
      : "/patient-search.html";

    window.location.assign(destination);
  });

  // Load only real records from the existing backend.
  loadQueue();
});
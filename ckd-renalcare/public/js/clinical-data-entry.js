
/*
 * Clinical Data Entry
 * Backend-backed patient search, registration and saving.
 * Successful save -> confirmation modal -> receptionist Review & Submit.
 * No automatic redirect after saving.
 */

document.addEventListener('DOMContentLoaded', () => {
  'use strict';

  const $ = (selector, root = document) => root.querySelector(selector);

  const form = $('#clinical-entry-form');
  const alertBox = $('#cde-alert');
  const existingFields = $('#existing-patient-fields');
  const newFields = $('#new-patient-fields');
  const patientSearch = $('#patient-search');
  const resultsBox = $('#patient-results');
  const selectedId = $('#selected-patient-id');
  const selectedName = $('#selected-patient-name');
  const selectedSummary = $('#selected-patient-summary');
  const saveBtn = $('#save-visit');

  // ------------------------------------------------------------
  // Save confirmation modal
  // ------------------------------------------------------------

  const confirmationModal = $('#save-confirmation-modal');
  const modalTitle = $('#save-modal-title');
  const modalMessage = $('#save-modal-message');
  const modalPatientId = $('#save-modal-patient-id');
  const modalVisitId = $('#save-modal-visit-id');
  const modalIcon = $('#save-modal-icon');
  const modalEyebrow = $('#save-modal-eyebrow');
  const modalReviewButton = $('#save-modal-review');
  const modalStayButton = $('#save-modal-stay');

  let savedPatientId = null;
  let savedVisitId = null;
  let previousFocusedElement = null;

  const modalElementsAvailable = Boolean(
    confirmationModal &&
    modalTitle &&
    modalMessage &&
    modalPatientId &&
    modalVisitId &&
    modalIcon &&
    modalEyebrow &&
    modalReviewButton &&
    modalStayButton
  );

  const closeConfirmation = () => {
    if (!modalElementsAvailable) return;

    confirmationModal.hidden = true;
    document.body.classList.remove('cde-modal-open');

    if (previousFocusedElement?.isConnected) {
      previousFocusedElement.focus();
    }
  };

  const openConfirmation = ({
    title,
    message,
    patientId = '—',
    visitId = '—',
    type = 'success',
    eyebrow = 'CLINICAL ENTRY SAVED'
  }) => {
    if (!modalElementsAvailable) {
      showAlert(message, type === 'error' ? 'error' : 'success');
      return;
    }

    previousFocusedElement = document.activeElement;

    modalTitle.textContent = title;
    modalMessage.textContent = message;
    modalPatientId.textContent = String(patientId ?? '—');
    modalVisitId.textContent = String(visitId ?? '—');
    modalEyebrow.textContent = eyebrow;

    modalIcon.className = 'cde-modal-icon';
    modalIcon.textContent = '✓';

    if (type === 'error') {
      modalIcon.classList.add('error');
      modalIcon.textContent = '!';
    } else if (type === 'info') {
      modalIcon.classList.add('info');
      modalIcon.textContent = 'i';
    }

    // Only a confirmed save can proceed to Review & Submit.
    modalReviewButton.hidden = type !== 'success';

    modalStayButton.textContent =
      type === 'success' ? 'Stay on this page' : 'Close';

    confirmationModal.hidden = false;
    document.body.classList.add('cde-modal-open');

    modalStayButton.focus();
  };

  if (modalElementsAvailable) {
    modalStayButton.addEventListener('click', closeConfirmation);

    modalReviewButton.addEventListener('click', () => {
      if (!savedPatientId) {
        closeConfirmation();

        showAlert(
          'The saved Patient ID is missing. Please verify the save response.',
          'error'
        );

        return;
      }

      const query = new URLSearchParams();
      query.set('patient_id', String(savedPatientId));

      if (
        savedVisitId !== null &&
        savedVisitId !== undefined &&
        savedVisitId !== ''
      ) {
        query.set('visit_id', String(savedVisitId));
      }

      window.location.href =
        `/review-submit.html?${query.toString()}`;
    });

    // Escape closes the popup without submitting the visit.
    document.addEventListener('keydown', event => {
      if (
        event.key === 'Escape' &&
        !confirmationModal.hidden
      ) {
        closeConfirmation();
      }
    });

    // Clicking the dark backdrop closes the popup.
    const modalBackdrop = $('.cde-modal-backdrop', confirmationModal);

    if (modalBackdrop) {
      modalBackdrop.addEventListener('click', closeConfirmation);
    }
  }

  let mode = 'existing';
  let searchTimer = null;
  let searchResults = [];

  const today = new Date();

  const todayString =
    `${today.getFullYear()}-` +
    `${String(today.getMonth() + 1).padStart(2, '0')}-` +
    `${String(today.getDate()).padStart(2, '0')}`;

  $('#visit-date').value = todayString;

  const escapeHTML = value =>
    String(value ?? '').replace(/[&<>"']/g, character => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    })[character]);

  // ------------------------------------------------------------
  // Inline messages
  // ------------------------------------------------------------

  const showAlert = (message, type = 'info', action = null) => {
    if (!alertBox) return;

    alertBox.replaceChildren();

    const messageText = document.createElement('p');
    messageText.className = 'cde-alert-message';
    messageText.textContent = message;
    alertBox.appendChild(messageText);

    if (action) {
      const actionRow = document.createElement('div');
      actionRow.className = 'cde-alert-actions';

      const actionButton = document.createElement('button');
      actionButton.type = 'button';
      actionButton.className = 'cde-button cde-button-primary';
      actionButton.textContent = action.label;
      actionButton.addEventListener('click', action.onClick);

      actionRow.appendChild(actionButton);
      alertBox.appendChild(actionRow);
    }

    alertBox.className = `cde-alert ${type}`;
    alertBox.hidden = false;

    alertBox.setAttribute(
      'role',
      type === 'error' ? 'alert' : 'status'
    );

    alertBox.scrollIntoView({
      behavior: 'smooth',
      block: 'nearest'
    });
  };

  const hideAlert = () => {
    if (!alertBox) return;

    alertBox.hidden = true;
    alertBox.replaceChildren();
  };

  const numeric = id => {
    const element = $(`#${id}`);

    if (!element) return null;

    const value = element.value.trim();

    if (value === '') return null;

    const number = Number(value);

    return Number.isFinite(number) ? number : null;
  };

  // ------------------------------------------------------------
  // Patient mode selection
  // ------------------------------------------------------------

  const setMode = next => {
    mode = next;

    document.querySelectorAll('[data-mode]').forEach(button => {
      const active = button.dataset.mode === mode;

      button.classList.toggle('selected', active);
      button.setAttribute('aria-pressed', String(active));
    });

    existingFields.hidden = mode !== 'existing';
    newFields.hidden = mode !== 'new';

    hideAlert();
    updateProgress();
  };

  document.querySelectorAll('[data-mode]').forEach(button => {
    button.addEventListener('click', () => {
      setMode(button.dataset.mode);
    });
  });

  // ------------------------------------------------------------
  // API and reception authorization
  // ------------------------------------------------------------

  if (!window.Api?.requireRole) {
    showAlert(
      'The API client is unavailable. Return to login and try again.',
      'error'
    );
    return;
  }

  const staff = window.Api.requireRole('reception');

  if (!staff) return;

  const staffName =
    staff.name ||
    staff.full_name ||
    staff.username ||
    'Reception staff';

  $('#cde-staff-name').textContent = staffName;

  $('#cde-avatar').textContent =
    staffName
      .split(/\s+/)
      .slice(0, 2)
      .map(part => part[0] || '')
      .join('')
      .toUpperCase() || 'RS';

  $('#cde-logout').addEventListener('click', () => {
    window.Api.logout();
  });

  // ------------------------------------------------------------
  // Patient search and selection
  // ------------------------------------------------------------

  const renderSearch = rows => {
    searchResults = Array.isArray(rows) ? rows : [];

    resultsBox.replaceChildren();
    resultsBox.hidden = false;

    if (!searchResults.length) {
      const message = document.createElement('p');
      message.className = 'cde-search-result';

      message.textContent =
        'No matching patients. If this is a new patient, choose “Register new patient”.';

      resultsBox.appendChild(message);
      return;
    }

    searchResults.forEach(patient => {
      const id =
        patient.id ??
        patient.study_id ??
        patient.patient_id;

      const name =
        patient.name ||
        patient.display_name ||
        id ||
        'Patient';

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'cde-search-result';

      button.innerHTML = `
        <span>
          <strong>${escapeHTML(name)}</strong>
          <small>
            Patient ID: ${escapeHTML(id)}
            ${patient.sex
              ? ' · ' + escapeHTML(patient.sex)
              : ''}
          </small>
        </span>
        <em>Select patient →</em>
      `;

      button.addEventListener('click', () => {
        selectPatient(String(id), String(name));
      });

      resultsBox.appendChild(button);
    });
  };

  const searchPatients = async () => {
    const query = patientSearch.value.trim();

    if (query.length < 2) {
      resultsBox.hidden = true;

      showAlert(
        'Enter at least 2 characters of the patient name or ID.',
        'info'
      );

      return;
    }

    if (!window.Api.searchPatients) {
      showAlert(
        'Patient search is unavailable in the API client. Check your API update.',
        'error'
      );

      return;
    }

    const searchButton = $('#search-patient-btn');
    searchButton.disabled = true;

    try {
      renderSearch(await window.Api.searchPatients(query));
    } catch (error) {
      showAlert(
        error.message ||
          'Patient search failed. Check the backend connection.',
        'error'
      );
    } finally {
      searchButton.disabled = false;
    }
  };

  $('#search-patient-btn').addEventListener('click', searchPatients);

  patientSearch.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(searchPatients, 350);
  });

  patientSearch.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      searchPatients();
    }
  });

  const selectPatient = async (id, name) => {
    selectedId.value = id;
    selectedName.value = name;
    selectedSummary.hidden = false;
    resultsBox.hidden = true;

    try {
      if (!window.Api.getPatientIntake) {
        throw new Error('Patient history API is unavailable.');
      }

      const patient = await window.Api.getPatientIntake(id);

      selectedName.value = patient.name || name;

      $('#condition-diabetes').checked =
        Boolean(patient.diabetes);

      $('#condition-hypertension').checked =
        Boolean(patient.hypertension);

      $('#condition-heart').checked =
        Boolean(patient.heart_disease);

      $('#condition-family').checked =
        Boolean(patient.family_hx_kidney);

      const latestVisit =
        Array.isArray(patient.visits)
          ? patient.visits[0]
          : null;

      selectedSummary.querySelector('p').textContent =
        latestVisit
          ? `Previous visit: ${latestVisit.visit_date} · ${latestVisit.status}. Verify the history before recording this visit.`
          : 'No previous visit returned. New measurements will be saved to this patient record.';

      showAlert(
        `Selected ${selectedName.value || name} (${id}). Verify the visit date and measurements before saving.`,
        'success'
      );
    } catch (error) {
      showAlert(
        `Patient selected, but existing history could not be loaded: ${error.message || 'request failed'}. Check the connection before saving.`,
        'error'
      );
    }

    updateProgress();
  };

  $('#clear-patient').addEventListener('click', () => {
    selectedId.value = '';
    selectedName.value = '';
    selectedSummary.hidden = true;

    patientSearch.focus();

    hideAlert();
    updateProgress();
  });

  // ------------------------------------------------------------
  // Clinical measurements and BMI
  // ------------------------------------------------------------

  const labFields = {
    sbp: 'sbp',
    dbp: 'dbp',
    bun: 'bun',
    uric_acid: 'uric-acid',
    calcium: 'calcium',
    albumin_serum: 'albumin-serum',
    height_cm: 'height-cm',
    weight_kg: 'weight-kg',
    creatinine: 'creatinine',
    egfr: 'egfr',
    uacr: 'uacr',
    hba1c: 'hba1c',
    potassium: 'potassium',
    sodium: 'sodium',
    phosphorus: 'phosphorus'
  };

  const updateBMI = () => {
    const height = numeric('lab-height-cm');
    const weight = numeric('lab-weight-kg');

    if (height > 0 && weight > 0) {
      const bmi = weight / ((height / 100) ** 2);

      $('#bmi-value').textContent = bmi.toFixed(1);

      $('#bmi-status').textContent =
        'Calculated from entered height and weight';

      $('#bmi-bar').style.width =
        `${Math.min(100, Math.max(5, bmi / 45 * 100))}%`;
    } else {
      $('#bmi-value').textContent = '—';
      $('#bmi-status').textContent = 'Enter height and weight';
      $('#bmi-bar').style.width = '0%';
    }
  };

  ['lab-height-cm', 'lab-weight-kg'].forEach(id => {
    $(`#${id}`).addEventListener('input', updateBMI);
  });

  const updateProgress = () => {
    const identityOk = mode === 'new'
      ? Boolean(
          $('#new-name').value.trim() &&
          numeric('new-age') &&
          $('#new-sex').value
        )
      : Boolean(selectedId.value);

    const visitOk = Boolean($('#visit-date').value);

    const measurementsCount = Object.values(labFields)
      .filter(id => $(`#lab-${id}`).value.trim() !== '')
      .length;

    const score =
      (identityOk ? 40 : 0) +
      (visitOk ? 20 : 0) +
      (measurementsCount ? 25 : 0) +
      ($('#followup-notes').value.trim() ? 10 : 0) +
      ($('#visit-reason').value ? 5 : 0);

    $('#completion-bar').style.width = `${score}%`;

    const progress = $('.cde-progress');

    if (progress) {
      progress.setAttribute('aria-valuenow', String(score));
    }

    $('#completion-text').textContent =
      score === 100
        ? 'Form readiness complete. Verify all values and source dates before saving.'
        : `${score}% form readiness · ${measurementsCount} measurement(s) entered`;
  };

  form.addEventListener('input', updateProgress);
  form.addEventListener('change', updateProgress);

  // ------------------------------------------------------------
  // Validation
  // ------------------------------------------------------------

  const validateRanges = () => {
    const errors = [];

    for (const id of Object.values(labFields)) {
      const element = $(`#lab-${id}`);

      if (!element.value.trim()) continue;

      const value = Number(element.value);
      const minimum = Number(element.min);
      const maximum = Number(element.max);

      if (
        !Number.isFinite(value) ||
        (element.min !== '' && value < minimum) ||
        (element.max !== '' && value > maximum)
      ) {
        const label =
          element.closest('label')
            ?.childNodes[0]
            ?.textContent
            ?.trim() || id;

        errors.push(
          `${label} is outside the allowed entry range.`
        );
      }
    }

    const systolic = numeric('lab-sbp');
    const diastolic = numeric('lab-dbp');

    if (
      systolic !== null &&
      diastolic !== null &&
      systolic <= diastolic
    ) {
      errors.push(
        'Systolic BP should be greater than diastolic BP; verify the entered values.'
      );
    }

    const visitDate = $('#visit-date').value;
    const localToday = new Date();
    localToday.setHours(0, 0, 0, 0);

    const selectedDate = visitDate
      ? new Date(`${visitDate}T00:00:00`)
      : null;

    if (selectedDate && selectedDate > localToday) {
      errors.push('Visit date cannot be in the future.');
    }

    return errors;
  };

  const parseMedicines = () =>
    $('#medicines').value
      .split(/\n|,/)
      .map(value => value.trim())
      .filter(Boolean);

  // ------------------------------------------------------------
  // Submit and save clinical entry
  // ------------------------------------------------------------

  form.addEventListener('submit', async event => {
    event.preventDefault();

    hideAlert();

    const errors = validateRanges();

    if (errors.length) {
      showAlert(errors.join(' '), 'error');
      return;
    }

    if (!$('#visit-date').value) {
      showAlert('Choose a visit date.', 'error');
      return;
    }

    saveBtn.disabled = true;
    saveBtn.querySelector('span').textContent = 'Saving visit…';

    // Clear identifiers from any previous successful save.
    savedPatientId = null;
    savedVisitId = null;

    try {
      let studyId = selectedId.value.trim();
      let visitId = null;

      // Register a new patient first, then save the clinical entry.
      if (mode === 'new') {
        const name = $('#new-name').value.trim();
        const age = numeric('new-age');
        const sex = $('#new-sex').value;

        if (
          !name ||
          age === null ||
          age < 1 ||
          age > 120 ||
          !Number.isInteger(age) ||
          !sex
        ) {
          throw new Error(
            'For a new patient, enter full name, age (1–120) and sex.'
          );
        }

        const registration = await window.Api.registerPatient({
          name,
          age,
          sex,
          reason:
            $('#new-reason').value.trim() ||
            $('#visit-reason').value
        });

        studyId = String(
          registration?.id ??
          registration?.study_id ??
          registration?.patient_id ??
          ''
        );

        if (
          registration?.visit_id &&
          registration?.visit_date === $('#visit-date').value
        ) {
          visitId = registration.visit_id;
        }

        if (!studyId) {
          throw new Error(
            'Patient registration did not return a Patient ID. Check the registration API response.'
          );
        }

        selectedId.value = studyId;
        selectedName.value = name;
      } else if (!studyId) {
        throw new Error(
          'Search for and select an existing patient first.'
        );
      }

      const values = {};

      Object.entries(labFields).forEach(([code, id]) => {
        const value = numeric(`lab-${id}`);

        if (value !== null) {
          values[code] = value;
        }
      });

      const payload = {
        visit_date: $('#visit-date').value,
        visit_id: visitId,
        reason: $('#visit-reason').value,

        values,

        conditions: {
          diabetes: $('#condition-diabetes').checked,
          hypertension: $('#condition-hypertension').checked,
          heart_disease: $('#condition-heart').checked,
          family_hx_kidney: $('#condition-family').checked
        },

        medicines: parseMedicines(),
        notes: $('#followup-notes').value.trim(),
        source: $('#measurement-source').value
      };

      if (!window.Api.saveClinicalEntry) {
        throw new Error(
          'Clinical entry save API is unavailable. Check public/js/api.js.'
        );
      }

      // Only show success after the save API resolves successfully.
      const saved = await window.Api.saveClinicalEntry(
        studyId,
        payload
      );

      if (
        !saved ||
        saved.saved === false ||
        saved.success === false
      ) {
        throw new Error(
          saved?.message ||
          'The server did not confirm that the clinical entry was saved.'
        );
      }

      // Retain identifiers for Review & Submit.
      savedPatientId = studyId;
      savedVisitId = saved.visit_id ?? visitId;

      selectedId.value = studyId;
      selectedName.value =
        selectedName.value || $('#new-name').value.trim();

      const added = saved.observations?.added ?? 0;
      const updated = saved.observations?.updated ?? 0;
      const duplicates =
        saved.observations?.duplicates_ignored ?? 0;

      // Show the modal only after the backend request succeeds.
      openConfirmation({
        title: 'Visit saved successfully',

        message:
          'The server confirmed the clinical entry was saved. ' +
          'Please continue to Review & Submit to check the saved patient ' +
          'details, visit date, measurements, medicines and notes before ' +
          'submitting the visit for the next stage.',

        patientId: savedPatientId,
        visitId: savedVisitId ?? 'Not returned',
        type: 'success',
        eyebrow: 'SAVE CONFIRMED'
      });

      // Also show an inline confirmation.
      showAlert(
        `SAVE CONFIRMED. Patient ID: ${studyId}. ` +
        `Visit ID: ${savedVisitId ?? 'not returned'}. ` +
        `${added} new measurement(s), ${updated} updated, ` +
        `${duplicates} duplicate(s) ignored. ` +
        'Continue to Review & Submit to verify the saved visit.',
        'success'
      );

      // No automatic redirect. The receptionist chooses when to continue.
    } catch (error) {
      const message =
        `SAVE NOT CONFIRMED. ${error.message ||
          'Could not save the clinical visit. Check the API response and database connection.'} ` +
        'The backend has not confirmed the save. Please verify the connection and try again.';

      showAlert(message, 'error');

      openConfirmation({
        title: 'Visit was not confirmed as saved',

        message:
          message +
          ' Do not proceed to review as though the save succeeded. ' +
          'Resolve the error and retry.',

        patientId: selectedId.value || 'Not available',
        visitId: 'Not confirmed',
        type: 'error',
        eyebrow: 'SAVE FAILED'
      });
    } finally {
      saveBtn.disabled = false;

      saveBtn.querySelector('span').textContent =
        'Save & Continue to Review';
    }
  });

  // ------------------------------------------------------------
  // Clear unsaved form fields
  // This does not delete database records.
  // ------------------------------------------------------------

  $('#reset-form').addEventListener('click', () => {
    if (!confirm(
      'Clear the unsaved measurements, notes and medicine entries? Saved database records will not be deleted.'
    )) {
      return;
    }

    Object.values(labFields).forEach(id => {
      $(`#lab-${id}`).value = '';
    });

    $('#followup-notes').value = '';
    $('#medicines').value = '';

    [
      'condition-diabetes',
      'condition-hypertension',
      'condition-heart',
      'condition-family'
    ].forEach(id => {
      $(`#${id}`).checked = false;
    });

    updateBMI();
    updateProgress();

    showAlert(
      'Unsaved measurements, notes and medicines were cleared. Saved database records were not deleted.',
      'info'
    );
  });

  // ------------------------------------------------------------
  // Support opening with a patient ID in the URL
  // ------------------------------------------------------------

  const queryPatientId =
    new URLSearchParams(window.location.search)
      .get('patient_id');

  if (queryPatientId) {
    patientSearch.value = queryPatientId;
    searchPatients();
  }

  updateBMI();
  updateProgress();
});

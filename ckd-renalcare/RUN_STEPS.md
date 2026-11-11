# RenalCare - integrated project (new UI + FULL backend)

Windows, run everything inside the `backend` folder.

1. Install packages (once):
   pip install -r requirements.txt
2. Create DB + user (once, in psql as postgres):
   CREATE USER ckd WITH PASSWORD 'ckd123' SUPERUSER;
   CREATE DATABASE ckd OWNER ckd;
3. Load tables (PowerShell; this wipes and recreates tables):
   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U ckd -h localhost -p 5432 -d ckd -f schema.sql
4. Set the DB address in the SAME terminal you start the server in:
   PowerShell:  $env:DATABASE_URL = "postgresql://ckd:ckd123@localhost:5432/ckd"
   cmd:         set DATABASE_URL=postgresql://ckd:ckd123@localhost:5432/ckd
5. Load demo data + logins:  python seed.py
6. (once) python train_model.py
   (then step 6b below: python load_guidelines.py)
7. Start:  uvicorn main:app --port 8000
8. Open http://localhost:8000

Logins: reception1 / reception123 (Reception), dr.morgan / doctor123 (Doctor)

Workflow: Reception > Clinical Data Entry (register/select patient, save) > Review & Submit
(confirm + submit for doctor review) > Doctor sees the patient in the queue.

New in this integration: endpoints GET /api/patients/{id}/intake, POST /api/patients/{id}/clinical-entry,
POST /api/patients/{id}/visits/{visit_id}/submit-review (backend/intake.py); visits.submitted_at column
(added automatically on startup if your DB is older).
Tests: python -m pytest tests

## Added in this version: the four agents, wired to KDIGO (RAG)

New step after step 6 (once): `python load_guidelines.py`. It loads the two KDIGO PDFs in `backend/guidelines/` into the RAG
knowledge base (a few minutes; semantic search if sentence-transformers is installed, otherwise keyword search).

Doctor page > open a patient > **Agent workspace** > "Run the four agents". Order follows the project workflow:
Clinical Data Agent > Risk Assessment Agent > Clinical Management Agent > Diet Recommendation Agent (backend/orchestrator.py).
- Plain code reads every number. No agent changes a clinical value. No LLM is needed.
- Management and Diet only quote KDIGO passages found by RAG, each with document and PDF page. No passage = "Insufficient evidence", no advice.
- Every output is a draft that needs doctor review. One agent failing does not hide the others. Each run is saved in agent_runs.
- Endpoints (doctor only): POST /api/patients/{id}/pipeline (run), GET /api/patients/{id}/pipeline (last saved run).
- Guidelines: KDIGO 2024 CKD (main source) and the KDIGO 2026 AKI-AKD **public review draft** (not final, labelled as a draft).
  Page numbers are PDF page numbers, not the printed S-numbers.

Repaired: the reception menu linked to 5 pages that did not exist (patient-search, queue-workflow, reports-documents,
reception-account, reception-dashboard), which gave a 404. They now redirect to the reception dashboard. The Reports/documents
and Account pages are still not built, so those two links just open the dashboard.

Known limits: care-gap source labels (caregaps.py) are still marked "verify" and were not re-checked against the KDIGO PDF;
the screening model is trained on US NHANES data; keyword retrieval is weaker than semantic search (install sentence-transformers
and re-run load_guidelines.py); no patient portal or report-approval flow yet.
Tests: python -m pytest tests (65 pass here, including 4 new pipeline tests).

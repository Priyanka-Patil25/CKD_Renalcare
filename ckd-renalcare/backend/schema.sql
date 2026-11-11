-- RenalCare / CKD decision support: PostgreSQL schema (v1)
-- Run:  psql -U postgres -d ckd -f schema.sql
-- Design rules:
--   * Study IDs, not hospital IDs. patients.display_name is for the DEMO only.
--     With real hospital data, leave it NULL and never store names or phone numbers.
--   * Results live in ONE long table (observations). The unique key
--     (patient_id, code, observed_on) means the same test on the same day entered
--     twice (e.g. a repeated report) is merged, not duplicated.
--   * Care-gap flags keep the doctor's decision (accept / edit / dismiss).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP TABLE IF EXISTS audit_log, agent_runs, guideline_chunks, screening_results,
  risk_assessments, care_gap_flags, notes, visit_medications, observations,
  visits, patients, auth_sessions, staff CASCADE;

CREATE TABLE staff (
  id            BIGSERIAL PRIMARY KEY,
  username      TEXT UNIQUE NOT NULL,
  full_name     TEXT NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('doctor','reception','admin')),
  password_hash TEXT NOT NULL,                 -- pbkdf2$iterations$salt$hash
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE auth_sessions (
  token      TEXT PRIMARY KEY,
  staff_id   BIGINT NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE patients (
  id               BIGSERIAL PRIMARY KEY,
  study_id         TEXT UNIQUE NOT NULL,       -- e.g. PT-10482 or DEMO-001
  display_name     TEXT,                       -- DEMO ONLY, NULL for real data
  sex              TEXT CHECK (sex IN ('M','F')),
  birth_year       INT,
  diabetes         BOOLEAN NOT NULL DEFAULT FALSE,
  hypertension     BOOLEAN NOT NULL DEFAULT FALSE,
  heart_disease    BOOLEAN NOT NULL DEFAULT FALSE,
  family_hx_kidney BOOLEAN NOT NULL DEFAULT FALSE,
  dm_years         NUMERIC,
  htn_years        NUMERIC,
  is_synthetic     BOOLEAN NOT NULL DEFAULT FALSE,   -- never train on these
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE visits (
  id               BIGSERIAL PRIMARY KEY,
  patient_id       BIGINT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  visit_no         INT  NOT NULL,
  visit_date       DATE NOT NULL,
  token            TEXT,                        -- queue token, per day: A-01
  status           TEXT NOT NULL DEFAULT 'waiting'
                   CHECK (status IN ('waiting','in_consultation','completed','cancelled')),
  reason           TEXT,
  age_at_visit     INT,
  doctor_stage     TEXT,                        -- stage as assessed by the doctor
  submitted_at     TIMESTAMPTZ,                 -- reception submitted it for doctor review
  submitted_by     BIGINT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (patient_id, visit_no),
  UNIQUE (visit_date, token)
);
CREATE INDEX visits_day_idx ON visits (visit_date, status);

-- One row per measurement. code examples:
--  creatinine, egfr, uacr, bun, sodium, potassium, calcium, phosphorus, hba1c,
--  albumin_serum, uric_acid, sbp, dbp, height_cm, weight_kg, urine_sg, urine_blood
CREATE TABLE observations (
  id          BIGSERIAL PRIMARY KEY,
  patient_id  BIGINT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  visit_id    BIGINT REFERENCES visits(id) ON DELETE SET NULL,
  code        TEXT NOT NULL,
  value_num   NUMERIC,
  value_text  TEXT,                              -- e.g. dipstick '1+'
  unit        TEXT,
  observed_on DATE NOT NULL,
  source      TEXT NOT NULL DEFAULT 'manual',    -- chart | manual | upload | lab_feed
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (patient_id, code, observed_on)
);
CREATE INDEX obs_patient_code_idx ON observations (patient_id, code, observed_on);

CREATE TABLE visit_medications (
  id         BIGSERIAL PRIMARY KEY,
  visit_id   BIGINT NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
  patient_id BIGINT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  drug       TEXT NOT NULL,                      -- as written, e.g. ramipril
  drug_class TEXT NOT NULL DEFAULT 'other',      -- ACEi | ARB | SGLT2i | NSAID | metformin | other
  compliant  BOOLEAN
);
CREATE INDEX vmeds_visit_idx ON visit_medications (visit_id);

CREATE TABLE notes (
  id         BIGSERIAL PRIMARY KEY,
  visit_id   BIGINT NOT NULL REFERENCES visits(id) ON DELETE CASCADE,
  staff_id   BIGINT REFERENCES staff(id),
  body       TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Output of the care-gap engine. The doctor's choice is stored here.
CREATE TABLE care_gap_flags (
  id          BIGSERIAL PRIMARY KEY,
  patient_id  BIGINT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  code        TEXT NOT NULL,                     -- NSAID, NO_RASI, RAPID_DECLINE ...
  level       TEXT NOT NULL CHECK (level IN ('high','medium','info')),
  title       TEXT NOT NULL,
  detail      TEXT NOT NULL,
  source      TEXT NOT NULL,                     -- guideline label
  status      TEXT NOT NULL DEFAULT 'pending'
              CHECK (status IN ('pending','accepted','edited','dismissed','resolved')),
  edited_text TEXT,
  decided_by  BIGINT REFERENCES staff(id),
  decided_at  TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (patient_id, code)
);

-- KDIGO stage/risk snapshot each time it is calculated
CREATE TABLE risk_assessments (
  id          BIGSERIAL PRIMARY KEY,
  patient_id  BIGINT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
  visit_id    BIGINT REFERENCES visits(id) ON DELETE SET NULL,
  egfr        NUMERIC,
  uacr        NUMERIC,
  g_cat       TEXT,
  a_cat       TEXT,
  kdigo_risk  TEXT,
  egfr_slope  NUMERIC,                           -- mL/min/1.73m2 per year
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Screening model runs (only meaningful for patients with no kidney labs)
CREATE TABLE screening_results (
  id            BIGSERIAL PRIMARY KEY,
  patient_id    BIGINT REFERENCES patients(id) ON DELETE CASCADE,
  visit_id      BIGINT REFERENCES visits(id) ON DELETE SET NULL,
  inputs        JSONB NOT NULL,
  score         NUMERIC NOT NULL,
  level         TEXT NOT NULL CHECK (level IN ('low','watch','high')),
  explanation   JSONB,
  model_version TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Guideline text for RAG. Full-text search now; add pgvector later if you need embeddings.
CREATE TABLE guideline_chunks (
  id         BIGSERIAL PRIMARY KEY,
  doc        TEXT NOT NULL,                      -- 'KDIGO 2024 CKD'
  section    TEXT,
  page       INT,
  text       TEXT NOT NULL,
  tsv        TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
  embedding  real[],                             -- vector from the embedding model (rag/index.py)
  embedder   TEXT,                               -- which model made it; never mix models
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX guideline_tsv_idx ON guideline_chunks USING GIN (tsv);

-- Every agent step is logged here so the doctor (and the examiner) can see what happened.
CREATE TABLE agent_runs (
  id         BIGSERIAL PRIMARY KEY,
  patient_id BIGINT REFERENCES patients(id) ON DELETE SET NULL,
  visit_id   BIGINT REFERENCES visits(id) ON DELETE SET NULL,
  agent      TEXT NOT NULL,                      -- reader | guideline_finder | writer
  input      JSONB,
  output     JSONB,
  status     TEXT NOT NULL DEFAULT 'ok',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
  id       BIGSERIAL PRIMARY KEY,
  staff_id BIGINT REFERENCES staff(id),
  action   TEXT NOT NULL,
  entity   TEXT,
  entity_id TEXT,
  detail   JSONB,
  at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

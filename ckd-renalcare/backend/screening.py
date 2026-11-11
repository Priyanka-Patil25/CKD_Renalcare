"""Screening model wrapper. Loads the saved random forest, gives a 3-level result and
a per-feature explanation (SHAP).

Use it ONLY for patients with no kidney labs (no eGFR / uACR). It is a 'worth testing' nudge.
When eGFR and uACR exist the KDIGO rules in kdigo.py are the answer.
"""
import json
from pathlib import Path
import numpy as np, pandas as pd, joblib

HERE = Path(__file__).parent
MODEL_PATH = HERE / "models" / "screening_rf.joblib"
META_PATH = HERE / "models" / "screening_meta.json"

FEATURE_LABELS = {
    "age": "Age", "bmi": "BMI", "bp_systolic": "Systolic BP", "bp_diastolic": "Diastolic BP",
    "blood_urea_nitrogen": "BUN", "uric_acid": "Uric acid", "calcium": "Calcium",
    "albumin_serum": "Serum albumin", "gender": "Sex", "diabetes_status": "Diabetes",
}
RANGES = {  # soft checks to catch unit mistakes (values outside are still accepted but warned)
    "age": (18, 90), "bmi": (12, 70), "bp_systolic": (70, 240), "bp_diastolic": (35, 140),
    "blood_urea_nitrogen": (2, 120), "uric_acid": (1, 15), "calcium": (6, 12), "albumin_serum": (1.5, 6),
}

_pipe = None
_meta = None
_explainer = None


def _load():
    global _pipe, _meta
    if _pipe is None:
        try:
            _pipe = joblib.load(MODEL_PATH)
            _meta = json.loads(META_PATH.read_text())
        except Exception:                      # missing file or different scikit-learn version
            import train_model
            train_model.main()
            _pipe = joblib.load(MODEL_PATH)
            _meta = json.loads(META_PATH.read_text())
    return _pipe, _meta


def meta():
    return _load()[1]


def normalise(inputs: dict) -> pd.DataFrame:
    """Accepts friendly input and returns a one-row frame with the 10 model columns."""
    sex = str(inputs.get("sex", inputs.get("gender", ""))).strip().lower()
    gender = {"m": "Male", "male": "Male", "f": "Female", "female": "Female"}.get(sex)
    dm = inputs.get("diabetes", inputs.get("diabetes_status"))
    if isinstance(dm, bool) or str(dm).lower() in ("y", "yes", "true", "n", "no", "false"):
        dm = "yes" if str(dm).lower() in ("y", "yes", "true") else "no"
    elif str(dm).lower() == "borderline":
        dm = "borderline"
    else:
        dm = None
    row = {
        "age": inputs.get("age"), "bmi": inputs.get("bmi"),
        "bp_systolic": inputs.get("sbp", inputs.get("bp_systolic")),
        "bp_diastolic": inputs.get("dbp", inputs.get("bp_diastolic")),
        "blood_urea_nitrogen": inputs.get("bun", inputs.get("blood_urea_nitrogen")),
        "uric_acid": inputs.get("uric_acid"), "calcium": inputs.get("calcium"),
        "albumin_serum": inputs.get("albumin", inputs.get("albumin_serum")),
        "gender": gender, "diabetes_status": dm,
    }
    for k, v in row.items():
        if k not in ("gender", "diabetes_status"):
            row[k] = None if v in (None, "") else float(v)
    return pd.DataFrame([row])[_load()[1]["features"]]


def level_of(score, m):
    return "high" if score >= m["high_line"] else ("watch" if score >= m["watch_line"] else "low")


def _explain(pipe, X):
    """SHAP values for the positive class, folded back onto the 10 original inputs."""
    global _explainer
    import shap
    rf = pipe.named_steps["model"]
    if _explainer is None:
        _explainer = shap.TreeExplainer(rf)
    Z = pipe.named_steps["prep"].transform(X)
    sv = _explainer.shap_values(Z)
    sv = np.asarray(sv)
    vals = sv[0, :, 1] if sv.ndim == 3 else (sv[1][0] if isinstance(sv, list) else sv[0])
    names = [n.split("__", 1)[1] for n in pipe.named_steps["prep"].get_feature_names_out()]
    folded = {}
    for n, v in zip(names, vals):
        base = "gender" if n.startswith("gender_") else ("diabetes_status" if n.startswith("diabetes_status_") else n)
        folded[base] = folded.get(base, 0.0) + float(v)
    return folded


def predict(inputs: dict, explain: bool = True) -> dict:
    pipe, m = _load()
    X = normalise(inputs)
    score = float(pipe.predict_proba(X)[0, 1])
    missing = [FEATURE_LABELS[c] for c in X.columns if pd.isna(X.iloc[0][c])]
    warnings = []
    for c, (lo, hi) in RANGES.items():
        v = X.iloc[0][c]
        if pd.notna(v) and not (lo <= v <= hi):
            warnings.append(f"{FEATURE_LABELS[c]} = {v:g} is outside the usual range {lo}-{hi}. Check the unit.")
    out = {
        "score": round(score, 3), "level": level_of(score, m), "model_version": m["version"],
        "watch_line": m["watch_line"], "high_line": m["high_line"],
        "missing_inputs": missing, "warnings": warnings,
        "message": {
            "low": "Below the screening line. Routine follow-up per the doctor's judgement.",
            "watch": "Above the screening line (catches about 9 in 10 people with CKD). Consider an eGFR and uACR test.",
            "high": "Well above the screening line. An eGFR and uACR test is strongly suggested.",
        }[level_of(score, m)],
        "disclaimer": "Screening nudge only. Not a diagnosis. The score is not a percentage chance.",
        "explanation": [],
    }
    if explain:
        try:
            f = _explain(pipe, X)
            tot = max(sum(abs(v) for v in f.values()), 1e-9)
            items = sorted(f.items(), key=lambda kv: -abs(kv[1]))
            out["explanation"] = [{"feature": FEATURE_LABELS.get(k, k), "value": round(v, 3),
                                   "share": round(abs(v) / tot * 100), "direction": "raises" if v > 0 else "lowers"}
                                  for k, v in items]
        except Exception as e:                       # explanation must never break the prediction
            out["explanation_error"] = str(e)[:120]
    return out

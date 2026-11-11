"""Train the screening model and save it.

Recipe (decided with the team, 20 Oct 2026):
  data   : NHANES 2017-2018 + 2021-2023 combined (data/nhanes_2017_2023_clean.csv)
  split  : 80/20 of the 2021-2023 rows (stratified, seed 42) -> locked test set.
           All 2017-2018 rows are added to the TRAIN side only.
  inputs : 10 simple features. eGFR, creatinine, uACR and the stage columns are
           NEVER inputs (they define the label, so using them is leakage).
  model  : Random forest, 300 trees, min_samples_leaf=5, balanced_subsample.
  cut-off: 'watch' line = score that catches 90% of CKD in out-of-fold TRAIN scores.
           'high' line = 0.5.  The test set is opened once, here, for the report.

Run:  python train_model.py        (about 30 seconds)
"""
import json, sys, datetime
from pathlib import Path
import numpy as np, pandas as pd
import joblib, sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score, average_precision_score, roc_curve, confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

HERE = Path(__file__).parent
RS = 42
NUM = ["age", "bmi", "bp_systolic", "bp_diastolic", "blood_urea_nitrogen", "uric_acid", "calcium", "albumin_serum"]
CAT = ["gender", "diabetes_status"]
BANNED = {"serum_creatinine", "egfr", "albumin_creatinine_ratio", "g_cat", "a_cat", "ckd", "ckd_stage", "ckd_present",
          "cycle", "participant_id", "ethnicity"}
VERSION = "rf-nhanes1723-v1"


def make_pipeline():
    prep = ColumnTransformer([
        ("num", SimpleImputer(strategy="median"), NUM),
        ("cat", Pipeline([("f", SimpleImputer(strategy="constant", fill_value="missing")),
                          ("o", OneHotEncoder(handle_unknown="ignore", sparse_output=False))]), CAT),
    ])
    rf = RandomForestClassifier(300, min_samples_leaf=5, class_weight="balanced_subsample", random_state=RS, n_jobs=-1)
    return Pipeline([("prep", prep), ("model", rf)])


def line_for_recall(y, s, target=0.90):
    fpr, tpr, thr = roc_curve(y, s)
    return float(thr[np.where(tpr >= target)[0][0]])


def main(out_dir=HERE / "models", data_path=HERE / "data" / "nhanes_2017_2023_clean.csv"):
    assert not (set(NUM) | set(CAT)) & BANNED, "leakage: a banned column is in the inputs"
    d = pd.read_csv(data_path)
    is17 = d["cycle"] == "2017-2018"
    n23 = d[~is17].reset_index(drop=True)
    tr23, te23 = train_test_split(n23, test_size=0.20, stratify=n23["ckd"], random_state=RS)
    train = pd.concat([tr23, d[is17]], ignore_index=True)
    Xtr, ytr = train[NUM + CAT], train["ckd"]
    Xte, yte = te23[NUM + CAT], te23["ckd"]

    pipe = make_pipeline()
    cv = StratifiedKFold(5, shuffle=True, random_state=RS)
    oof = cross_val_predict(pipe, Xtr, ytr, cv=cv, method="predict_proba")[:, 1]
    watch = line_for_recall(ytr, oof, 0.90)
    pipe.fit(Xtr, ytr)
    s = pipe.predict_proba(Xte)[:, 1]

    def conf(th):
        tn, fp, fn, tp = confusion_matrix(yte, (s >= th).astype(int)).ravel()
        return dict(TP=int(tp), FN=int(fn), FP=int(fp), TN=int(tn), recall=round(tp / (tp + fn), 3),
                    precision=round(tp / (tp + fp), 3), specificity=round(tn / (tn + fp), 3))

    meta = dict(
        version=VERSION, trained_at=datetime.datetime.now().isoformat(timespec="seconds"),
        sklearn=sklearn.__version__, n_train=int(len(Xtr)), n_train_ckd=int(ytr.sum()),
        n_test=int(len(Xte)), n_test_ckd=int(yte.sum()),
        features=NUM + CAT, watch_line=round(watch, 4), high_line=0.5,
        test_auc=round(float(roc_auc_score(yte, s)), 3), test_pr_auc=round(float(average_precision_score(yte, s)), 3),
        at_watch_line=conf(watch), at_high_line=conf(0.5),
        note="Screening only. Not for patients who already have eGFR/uACR. Scores are not probabilities.",
    )
    out_dir = Path(out_dir); out_dir.mkdir(exist_ok=True, parents=True)
    joblib.dump(pipe, out_dir / "screening_rf.joblib")
    (out_dir / "screening_meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()

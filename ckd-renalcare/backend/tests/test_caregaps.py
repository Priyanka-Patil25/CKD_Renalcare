import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from datetime import date, timedelta
import caregaps as cg

D0 = date(2026, 1, 1)
def V(days=0, **k): return cg.Visit(date=D0 + timedelta(days=days), **k)
def codes(vs, today=None): return {f.code for f in cg.evaluate(vs, today or vs[-1].date)}

def test_parse_uacr():
    assert cg.parse_uacr("1+ / 150") == 150 and cg.parse_uacr("neg / 18") == 18
    assert cg.parse_uacr(None) is None and cg.parse_uacr(42) == 42

def test_no_labs_diabetic():  assert "NO_LABS" in codes([V(diabetes=True)])
def test_no_labs_healthy():   assert codes([V()]) == set()

def test_nsaid_low_egfr():    assert "NSAID" in codes([V(egfr=50, uacr=10, meds={"nsaid"})])
def test_nsaid_ok_egfr():     assert "NSAID" not in codes([V(egfr=75, uacr=10, meds={"nsaid"})])
def test_nsaid_brand_name():  assert "NSAID" in codes([V(egfr=40, uacr=10, meds={"diclofenac"})])

def test_metformin_bands():
    assert "METFORMIN_STOP" in codes([V(egfr=28, uacr=10, meds={"metformin"})])
    c = codes([V(egfr=40, uacr=10, meds={"metformin"})])
    assert "METFORMIN_DOSE" in c and "METFORMIN_STOP" not in c
    assert not {"METFORMIN_STOP", "METFORMIN_DOSE"} & codes([V(egfr=70, uacr=10, meds={"metformin"})])

def test_sglt2i_boundary():
    assert "NO_SGLT2I" in codes([V(egfr=20, uacr=50, diabetes=True)])
    assert "NO_SGLT2I" not in codes([V(egfr=19, uacr=50, diabetes=True)])
    assert "NO_SGLT2I" not in codes([V(egfr=40, uacr=50, diabetes=True, meds={"sglt2i"})])
    assert "NO_SGLT2I" not in codes([V(egfr=40, uacr=50, diabetes=False)])       # A2, no diabetes
    assert "NO_SGLT2I" in codes([V(egfr=70, uacr=250, diabetes=False)])           # uACR >= 200

def test_rasi_levels():
    f = {f.code: f for f in cg.evaluate([V(egfr=70, uacr=50, diabetes=True)])}
    assert f["NO_RASI"].level == "high"
    f = {f.code: f for f in cg.evaluate([V(egfr=70, uacr=50, diabetes=False)])}
    assert f["NO_RASI"].level == "medium"
    assert "NO_RASI" not in codes([V(egfr=70, uacr=500, meds={"arb"})])
    assert "NO_RASI" not in codes([V(egfr=70, uacr=10)])

def test_slope_rapid_and_stable():
    fall = [V(0, egfr=60), V(180, egfr=54), V(365, egfr=48)]
    flat = [V(0, egfr=60), V(180, egfr=60), V(365, egfr=59)]
    assert "RAPID_DECLINE" in codes(fall) and "RAPID_DECLINE" not in codes(flat)

def test_slope_needs_enough_data():
    assert cg.egfr_slope([V(0, egfr=60), V(30, egfr=40)]) is None            # 2 points
    assert cg.egfr_slope([V(0, egfr=60), V(30, egfr=50), V(60, egfr=40)]) is None   # too short a span

def test_overdue_by_risk():
    # low risk: 11 months is fine, 14 is overdue
    lo = [V(0, egfr=95, uacr=5, diabetes=True)]
    assert "UACR_OVERDUE" not in codes(lo, D0 + timedelta(days=330))
    assert "UACR_OVERDUE" in codes(lo, D0 + timedelta(days=430))
    # very high risk: 5 months is already overdue
    vh = [V(0, egfr=25, uacr=400)]
    assert "UACR_OVERDUE" in codes(vh, D0 + timedelta(days=150))

def test_uacr_missing():     assert "UACR_MISSING" in codes([V(egfr=80, diabetes=True)])

def test_referral():
    assert "REFER" in codes([V(egfr=28, uacr=10)])
    assert "REFER" in codes([V(egfr=80, uacr=800)])          # ACR above 700
    assert "REFER" not in codes([V(egfr=80, uacr=350)])      # 300-700 alone is NOT a referral reason in KDIGO Fig 48
    assert "REFER" not in codes([V(egfr=50, uacr=100)])

def test_egfr_drop_over_20_percent():
    assert "EGFR_DROP20" in codes([V(0, egfr=60, uacr=10), V(120, egfr=45, uacr=10)])
    assert "EGFR_DROP20" not in codes([V(0, egfr=60, uacr=10), V(120, egfr=52, uacr=10)])
    assert "REFER" in codes([V(0, egfr=60, uacr=10), V(120, egfr=45, uacr=10)])

def test_bp_needs_two_high():
    assert "BP_HIGH" in codes([V(0, egfr=70, uacr=40, sbp=150), V(90, egfr=70, uacr=40, sbp=146)])
    assert "BP_HIGH" not in codes([V(0, egfr=70, uacr=40, sbp=150), V(90, egfr=70, uacr=40, sbp=130)])

def test_confirm_flag():
    assert "CONFIRM" in codes([V(0, egfr=55, uacr=10)])
    assert "CONFIRM" not in codes([V(0, egfr=55, uacr=10), V(120, egfr=54, uacr=10)])

def test_risk_grid_corners():
    assert cg.risk_of(95, 10) == "low" and cg.risk_of(50, 10) == "moderate"
    assert cg.risk_of(50, 100) == "high" and cg.risk_of(50, 400) == "very high"
    assert cg.risk_of(20, 5) == "very high" and cg.risk_of(None, 5) is None

def test_ordering_high_first():
    f = cg.evaluate([V(egfr=25, uacr=400, diabetes=True, meds={"nsaid"})])
    assert f[0].level == "high" and f[-1].level != "high" or all(x.level == "high" for x in f)

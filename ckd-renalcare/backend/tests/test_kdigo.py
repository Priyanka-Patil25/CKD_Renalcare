import kdigo


def test_egfr_hand_calculated():
    # worked by hand from the CKD-EPI 2021 formula
    assert abs(kdigo.egfr_ckdepi_2021(1.0, 60, "M") - 86.2) < 0.6
    assert abs(kdigo.egfr_ckdepi_2021(0.8, 50, "F") - 89.7) < 0.6


def test_egfr_goes_down_with_creatinine_and_age():
    assert kdigo.egfr_ckdepi_2021(2.0, 60, "M") < kdigo.egfr_ckdepi_2021(1.0, 60, "M")
    assert kdigo.egfr_ckdepi_2021(1.0, 80, "M") < kdigo.egfr_ckdepi_2021(1.0, 40, "M")


def test_boundaries():
    assert [kdigo.g_cat(x) for x in (95, 90, 89.9, 60, 59.9, 45, 44.9, 30, 29.9, 15, 14.9)] == \
           ["G1", "G1", "G2", "G2", "G3a", "G3a", "G3b", "G3b", "G4", "G4", "G5"]
    assert [kdigo.a_cat(x) for x in (5, 29.9, 30, 300, 300.1)] == ["A1", "A1", "A2", "A2", "A3"]


def test_grid_corners_and_g4_rule():
    assert kdigo.risk_of(95, 5) == "low" and kdigo.risk_of(50, 5) == "moderate"
    assert kdigo.risk_of(50, 100) == "high" and kdigo.risk_of(35, 100) == "very high"
    assert kdigo.risk_of(20, None) == "very high"          # G4 is very high even without uACR
    assert kdigo.risk_of(70, None) is None                 # cannot grade without uACR


def test_summary_text():
    s = kdigo.summary(40, 260)
    assert s["stage_text"] == "G3b A2" and s["risk"] == "very high" and s["monitor_months"] == 4
    assert kdigo.summary(None, None)["stage_text"] == "Not enough results"


def test_figure13_monitoring_frequency():
    from kdigo import monitor_months
    assert monitor_months(95, 10) == 12      # G1 A1: screen once a year
    assert monitor_months(50, 100) == 6      # G3a A2: 2 per year
    assert monitor_months(40, 100) == 4      # G3b A2: 3 per year
    assert monitor_months(40, 10) == 6       # G3b A1: 2 per year
    assert monitor_months(20, 500) == 3      # G4 A3: 4+ per year
    assert monitor_months(None, 50) is None

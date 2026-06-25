from app.analytics.engine import prerequisite_met

def test_simple_prereq():
    ok, _ = prerequisite_met("MGT101", {"MGT101"}, 0)
    assert ok

def test_missing_prereq():
    ok, reason = prerequisite_met("MGT101", set(), 0)
    assert not ok and "MGT101" in reason

def test_hours():
    ok, _ = prerequisite_met("إكمال 90 ساعة معتمدة", set(), 91)
    assert ok

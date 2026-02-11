from baby_cry_detection.monitor.calibration import (
    build_stop_summary,
    load_control,
    set_override,
    start_calibration,
    stop_calibration,
)


def test_start_and_stop_calibration_roundtrip(tmp_path):
    control = start_calibration(tmp_path, phase="phase1", interval_seconds=25)
    assert control.active is True
    assert control.phase == "phase1"
    assert control.interval_seconds == 25

    previous, current = stop_calibration(tmp_path)
    assert previous.active is True
    assert current.active is False


def test_set_override_validates_phase_parameters(tmp_path):
    start_calibration(tmp_path, phase="phase2", interval_seconds=15)

    updated, key, value = set_override(tmp_path, "CAT_WEIGHT", "1.4")
    assert updated.active is True
    assert key == "CAT_WEIGHT"
    assert float(value) == 1.4

    loaded = load_control(tmp_path)
    assert loaded.overrides["CAT_WEIGHT"] == 1.4


def test_stop_summary_contains_replayable_commands(tmp_path):
    start_calibration(tmp_path, phase="phase1", interval_seconds=12)
    set_override(tmp_path, "PRIMARY_CRY_THRESHOLD", "0.7")

    previous, _ = stop_calibration(tmp_path)
    summary = build_stop_summary(previous)

    assert "/cal_start phase1 12" in summary
    assert "/cal_set PRIMARY_CRY_THRESHOLD 0.7" in summary

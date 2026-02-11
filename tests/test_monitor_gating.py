from baby_cry_detection.monitor.gating import GatingEngine


def test_gating_confirms_and_respects_cooldown():
    gate = GatingEngine(
        baby_threshold=0.4,
        cat_weight=1.0,
        margin_threshold=0.1,
        cat_suppress_threshold=0.7,
        confirm_n=2,
        confirm_m=3,
        cooldown_seconds=120,
    )

    d1 = gate.evaluate(primary_score=0.8, baby_score=0.8, cat_score=0.1)
    d2 = gate.evaluate(primary_score=0.9, baby_score=0.9, cat_score=0.1)
    d3 = gate.evaluate(primary_score=0.9, baby_score=0.9, cat_score=0.1)

    assert not d1.ready_for_alert
    assert d2.ready_for_alert
    assert not d3.ready_for_alert


def test_cat_suppression_blocks_alert():
    gate = GatingEngine(
        baby_threshold=0.4,
        cat_weight=1.0,
        margin_threshold=0.1,
        cat_suppress_threshold=0.3,
        confirm_n=1,
        confirm_m=1,
        cooldown_seconds=0,
    )

    decision = gate.evaluate(primary_score=0.9, baby_score=0.45, cat_score=0.8)

    assert decision.suppressed_by_cat
    assert not decision.ready_for_alert

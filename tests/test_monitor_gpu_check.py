from baby_cry_detection.monitor import gpu_check


def test_gpu_check_missing_binary(monkeypatch):
    monkeypatch.setattr(gpu_check.shutil, "which", lambda _: None)
    ok, message = gpu_check.run_gpu_check()
    assert not ok
    assert "not found" in message

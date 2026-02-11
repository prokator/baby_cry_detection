import json

from baby_cry_detection.monitor.ollama_validator import OllamaValidator


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _FakeSession:
    def __init__(self, payload):
        self.payload = payload

    def post(self, url, json=None, timeout=None):
        del url, json, timeout
        return _FakeResponse(self.payload)


def test_validator_allow():
    inner = json.dumps({"decision": "allow", "reason": "baby dominates"})
    validator = OllamaValidator(base_url="http://localhost:11434", model="llama3.2")
    validator._session = _FakeSession({"response": inner})

    result = validator.validate(primary_score=0.7, baby_score=0.8, cat_score=0.1)
    assert result.allow


def test_validator_block():
    inner = json.dumps({"decision": "block", "reason": "cat likely"})
    validator = OllamaValidator(base_url="http://localhost:11434", model="llama3.2")
    validator._session = _FakeSession({"response": inner})

    result = validator.validate(primary_score=0.6, baby_score=0.4, cat_score=0.7)
    assert not result.allow

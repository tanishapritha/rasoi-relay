from unittest.mock import Mock

from ask_sdk_core.exceptions import AskSdkException
from fastapi.testclient import TestClient

from app.alexa import endpoint
from app.main import app


def _payload(skill_id: str) -> dict:
    return {
        "version": "1.0",
        "context": {
            "System": {
                "application": {"applicationId": skill_id},
                "user": {"userId": "amzn1.ask.account.test-user"},
            }
        },
        "request": {
            "type": "LaunchRequest",
            "requestId": "amzn1.echo-api.request.test",
            "timestamp": "2026-10-11T00:00:00Z",
            "locale": "en-IN",
        },
    }


def test_alexa_endpoint_is_disabled_without_skill_id(monkeypatch) -> None:
    monkeypatch.setattr(endpoint.settings, "alexa_skill_id", "")
    with TestClient(app) as client:
        response = client.post("/api/v1/alexa", json=_payload("amzn1.ask.skill.test"))
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ALEXA_NOT_CONFIGURED"


def test_alexa_endpoint_rejects_wrong_skill_id_before_dispatch(monkeypatch) -> None:
    monkeypatch.setattr(endpoint.settings, "alexa_skill_id", "amzn1.ask.skill.expected")
    dispatch = Mock()
    monkeypatch.setattr(endpoint.webservice_handler, "verify_request_and_dispatch", dispatch)
    with TestClient(app) as client:
        response = client.post("/api/v1/alexa", json=_payload("amzn1.ask.skill.other"))
    assert response.status_code == 403
    dispatch.assert_not_called()


def test_alexa_endpoint_rejects_unverified_request(monkeypatch) -> None:
    monkeypatch.setattr(endpoint.settings, "alexa_skill_id", "amzn1.ask.skill.expected")

    def reject_request(headers: dict, body: str) -> str:
        raise AskSdkException("invalid signature")

    monkeypatch.setattr(endpoint.webservice_handler, "verify_request_and_dispatch", reject_request)
    with TestClient(app) as client:
        response = client.post("/api/v1/alexa", json=_payload("amzn1.ask.skill.expected"))
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ALEXA_REQUEST_VERIFICATION_FAILED"


def test_alexa_endpoint_rejects_malformed_json(monkeypatch) -> None:
    monkeypatch.setattr(endpoint.settings, "alexa_skill_id", "amzn1.ask.skill.expected")
    with TestClient(app) as client:
        response = client.post("/api/v1/alexa", content=b"{")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_ALEXA_JSON"

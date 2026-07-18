from fastapi.testclient import TestClient
from app.telegram.webhook_demo import app


def test_telegram_webhook_receives_update():
    client = TestClient(app)
    payload = {"update_id": 12345, "message": {"text": "hello"}}
    resp = client.post("/telegram/webhook", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"received": True}

from app.schemas.chat import ChatResponse


def test_chat_endpoint_returns_investigation_result(client, monkeypatch):
    from app.api.v1.routes import chat as chat_route

    monkeypatch.setattr(
        chat_route,
        "investigate",
        lambda db, project_id, message, lookback_minutes: ChatResponse(
            answer="JWT tokens were expiring, causing authentication failures.",
            evidence=[],
            tool_calls=[],
            confidence="high",
            model_name="qwen3:4b-q4_K_M",
            analysis_mode="llm",
        ),
    )

    response = client.post("/api/v1/chat", json={"message": "Why did SmartHub fail around 3 PM?"})

    assert response.status_code == 200
    body = response.json()
    assert body["analysis_mode"] == "llm"
    assert "JWT" in body["answer"]


def test_chat_endpoint_rejects_too_short_message(client):
    response = client.post("/api/v1/chat", json={"message": "hi"})

    assert response.status_code == 422

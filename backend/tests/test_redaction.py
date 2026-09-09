from app.services.redaction import redact_text, redact_value


def test_redact_text_masks_bearer_token():
    assert "Bearer [REDACTED]" in redact_text("calling api with Bearer abc123.def456")
    assert "abc123" not in redact_text("calling api with Bearer abc123.def456")


def test_redact_text_masks_jwt():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc123signature"
    redacted = redact_text(f"token was {jwt} expired")
    assert jwt not in redacted
    assert "[REDACTED_JWT]" in redacted


def test_redact_text_masks_password_field():
    redacted = redact_text("login failed password=hunter2secret")
    assert "hunter2secret" not in redacted
    assert "[REDACTED]" in redacted


def test_redact_text_leaves_normal_message_untouched():
    message = "request timed out after 30s"
    assert redact_text(message) == message


def test_redact_value_recurses_into_dict_and_list():
    value = {"headers": ["Authorization: Bearer secrettoken123"], "note": "ok"}
    redacted = redact_value(value)
    assert "secrettoken123" not in str(redacted)
    assert redacted["note"] == "ok"

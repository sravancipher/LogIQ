from app.services.health_service import compute_status


def test_compute_status_healthy_when_no_errors():
    assert compute_status(error_logs=0, total_logs=100) == "healthy"


def test_compute_status_critical_at_or_above_30_percent():
    assert compute_status(error_logs=30, total_logs=100) == "critical"
    assert compute_status(error_logs=100, total_logs=100) == "critical"


def test_compute_status_degraded_below_30_percent():
    assert compute_status(error_logs=1, total_logs=100) == "degraded"
    assert compute_status(error_logs=29, total_logs=100) == "degraded"

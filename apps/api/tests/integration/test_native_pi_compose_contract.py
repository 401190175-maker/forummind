from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_compose_contains_a_private_and_health_checked_native_runtime() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "pi-runtime:" in compose
    assert "PI_RUNTIME_TOKEN: ${PI_RUNTIME_TOKEN:?PI_RUNTIME_TOKEN is required}" in compose
    assert "PI_SESSION_ROOT: /var/lib/forummind/pi-sessions" in compose
    assert "pi_sessions:" in compose
    assert "condition: service_healthy" in compose
    assert '"8010"' in compose
    assert "healthcheck:" in compose


def test_compose_does_not_publish_the_runtime_port_to_the_host() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    runtime_block = compose.split("  pi-runtime:", 1)[1].split("\n  # --- 后端 API", 1)[0]

    assert "ports:" not in runtime_block
    assert "expose:" in runtime_block

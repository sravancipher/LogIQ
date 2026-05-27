import argparse
import json
import os
from pathlib import Path

import requests


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def _resolve_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_config() -> dict[str, object]:
    provider = os.getenv("LLM_PROVIDER", "openai_compatible").strip().lower()
    base_url = (os.getenv("LLM_BASE_URL") or "").strip()
    model = (os.getenv("LLM_MODEL") or "").strip()

    if provider == "ollama":
        print("Using Ollama provider. Ensure OLLAMA_BASE_URL and OLLAMA_MODEL are set, or defaults will be used.")
        if not base_url:
            base_url = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").strip()
        if not model:
            model = (os.getenv("OLLAMA_MODEL") or "qwen3:4b-q4_K_M").strip()
    else:
        print("Using OpenAI-compatible provider. Ensure LLM_BASE_URL and LLM_MODEL are set, or defaults will be used.")
        if not base_url:
            base_url = "http://provider.h100.ams.val.akash.pub:32527/v1"
        if not model:
            model = "Qwen/Qwen3.6-35B-A3B-FP8"

    api_key = (os.getenv("LLM_API_KEY") or "").strip()

    timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    deep_analysis = _resolve_bool(os.getenv("LLM_DEEP_ANALYSIS"), default=False)

    return {
        "provider": provider,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "api_key": api_key,
        "timeout": timeout,
        "temperature": temperature,
        "deep_analysis": deep_analysis,
    }


def _request_ollama(config: dict[str, object], prompt: str) -> str:
    response = requests.post(
        f"{config['base_url']}/api/generate",
        json={
            "model": config["model"],
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": config["temperature"],
                "think": config["deep_analysis"],
            },
        },
        timeout=float(config["timeout"]),
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("response", ""))


def _request_openai_compatible(config: dict[str, object], prompt: str) -> str:
    headers = {"Content-Type": "application/json"}
    api_key = str(config["api_key"])
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.post(
        f"{config['base_url']}/chat/completions",
        headers=headers,
        json={
            "model": config["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": config["temperature"],
        },
        timeout=float(config["timeout"]),
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload["choices"][0]["message"]["content"])


def _run_once(prompt: str) -> int:
    project_root = Path(__file__).resolve().parents[1]
    _load_env_file(project_root / ".env")
    config = _resolve_config()

    print("LLM test starting with config:")
    print(json.dumps({k: ("***" if k == "api_key" and v else v) for k, v in config.items()}, indent=2))

    try:
        provider = str(config["provider"])
        if provider in {"openai", "openai_compatible", "openai-compatible", "akash"}:
            content = _request_openai_compatible(config, prompt)
        else:
            content = _request_ollama(config, prompt)
    except requests.RequestException as exc:
        print(f"LLM request failed: {exc}")
        return 1
    except (KeyError, ValueError, IndexError, TypeError) as exc:
        print(f"Could not parse LLM response: {exc}")
        return 1

    print("\nRaw model output:\n")
    print(content)

    try:
        parsed = json.loads(content)
        print("\nParsed JSON output:\n")
        print(json.dumps(parsed, indent=2))
    except json.JSONDecodeError:
        print("\nOutput is not JSON. This may be fine for a quick connectivity test.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a direct LLM integration test against configured provider.")
    parser.add_argument(
        "--prompt",
        default=(
            "Analyze this monitoring event and respond in strict JSON with keys: "
            "root_cause, incident_summary, suggestion, confidence, action_plan. "
            "Event: Connection timeout after 30s in payment-service charge operation."
        ),
        help="Prompt to send to the model",
    )
    args = parser.parse_args()
    return _run_once(args.prompt)


if __name__ == "__main__":
    raise SystemExit(main())

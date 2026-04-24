#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = []
# ///
"""
Gemini REST API research tool.

Zero-dependency script that queries the Gemini REST API directly,
saves all sessions to disk for persistent research history.

Usage:
    python gemini-research.py list-models
    python gemini-research.py generate "prompt" [--model MODEL]
    python gemini-research.py deep-research "prompt" [--poll-interval 45] [--timeout 3600]
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "https://generativelanguage.googleapis.com"
DEFAULT_MODEL = "gemini-2.5-pro"
DEEP_RESEARCH_AGENT = "deep-research-pro-preview-12-2025"
DEFAULT_POLL_INTERVAL = 45  # seconds
DEFAULT_TIMEOUT = 3600  # 1 hour
ENV_FILE = Path.home() / ".claude" / "gemini.env"
RESEARCH_DIR = Path.home() / "source" / "repos" / "research"


# ---------------------------------------------------------------------------
# API Key
# ---------------------------------------------------------------------------

def load_api_key() -> str:
    """Load API key from .env file first, then fall back to env var."""
    # 1. Try dedicated .env file
    if ENV_FILE.exists():
        try:
            text = ENV_FILE.read_text(encoding="utf-8").strip()
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                if line.startswith("GEMINI_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip("\"'")
                    if key:
                        return key
        except OSError:
            pass

    # 2. Fall back to environment variable
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key

    print("ERROR: No API key found.", file=sys.stderr)
    print(f"  Set key in {ENV_FILE} or GEMINI_API_KEY env var.", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# HTTP Helper
# ---------------------------------------------------------------------------

def api_request(method: str, path: str, body=None, api_key: str = "", model: str = "") -> dict:
    """
    Make an HTTP request to the Gemini API.

    Args:
        method: HTTP method (GET, POST)
        path: API path (e.g., /v1beta/models)
        body: Request body (dict, will be JSON-encoded)
        api_key: API key for auth
        model: Model name for error messages (optional)

    Returns:
        Parsed JSON response as dict.

    Raises:
        SystemExit on fatal errors (auth, not found, etc.)
    """
    # Build URL with API key as query param
    sep = "&" if "?" in path else "?"
    url = f"{API_BASE}{path}{sep}key={api_key}"

    headers = {"Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body else None

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass

        if e.code in (401, 403):
            print(f"ERROR: Authentication failed ({e.code}).", file=sys.stderr)
            print("  Check your API key is valid and has Gemini API access.", file=sys.stderr)
            if error_body:
                print(f"  Detail: {error_body[:500]}", file=sys.stderr)
            sys.exit(1)
        elif e.code == 404:
            print(f"ERROR: Endpoint not found ({e.code}): {path}", file=sys.stderr)
            print("  The model or endpoint may not be available yet.", file=sys.stderr)
            if error_body:
                print(f"  Detail: {error_body[:500]}", file=sys.stderr)
            sys.exit(1)
        elif e.code == 429:
            if model:
                print(f"ERROR: Model '{model}' is unavailable (quota exhausted or rate limited).", file=sys.stderr)
                print(f"  DO NOT RETRY WITH A DIFFERENT MODEL. Report this error to the user.", file=sys.stderr)
                print(f"  The user must explicitly choose to use a different model.", file=sys.stderr)
            else:
                print(f"ERROR: Rate limited ({e.code}).", file=sys.stderr)
                print(f"  DO NOT RETRY. Report this error to the user.", file=sys.stderr)
            if error_body:
                print(f"  Detail: {error_body[:500]}", file=sys.stderr)
            sys.exit(1)
        elif e.code == 503:
            if model:
                print(f"ERROR: Model '{model}' is temporarily unavailable (503 Service Unavailable).", file=sys.stderr)
                print(f"  DO NOT RETRY WITH A DIFFERENT MODEL. Report this error to the user.", file=sys.stderr)
                print(f"  The user must explicitly choose to use a different model.", file=sys.stderr)
            else:
                print(f"ERROR: Service unavailable ({e.code}).", file=sys.stderr)
                print(f"  DO NOT RETRY. Report this error to the user.", file=sys.stderr)
            if error_body:
                print(f"  Detail: {error_body[:500]}", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"ERROR: HTTP {e.code} from API.", file=sys.stderr)
            if error_body:
                print(f"  Detail: {error_body[:500]}", file=sys.stderr)
            sys.exit(1)
    except urllib.error.URLError as e:
        print(f"ERROR: Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Session Saving
# ---------------------------------------------------------------------------

def save_session(mode: str, prompt: str, response_text: str, metadata: dict) -> Path:
    """
    Save a research session to disk.

    Creates:
        ~/source/repos/research/{mode}/YYYY-MM-DD_HHMMSS/
            prompt.md
            response.md
            metadata.json

    Returns:
        Path to the session directory.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    session_dir = RESEARCH_DIR / mode / timestamp

    # Handle collision (same second)
    if session_dir.exists():
        i = 1
        while (RESEARCH_DIR / mode / f"{timestamp}_{i}").exists():
            i += 1
        session_dir = RESEARCH_DIR / mode / f"{timestamp}_{i}"

    session_dir.mkdir(parents=True, exist_ok=True)

    # Write prompt
    (session_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    # Write response
    (session_dir / "response.md").write_text(response_text, encoding="utf-8")

    # Write metadata
    metadata["saved_at"] = datetime.now().isoformat()
    metadata["session_dir"] = str(session_dir)
    (session_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return session_dir


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list_models(api_key: str) -> None:
    """List available Gemini models."""
    print("Fetching models...", file=sys.stderr)
    result = api_request("GET", "/v1beta/models", api_key=api_key)

    models = result.get("models", [])
    if not models:
        print("No models returned.")
        return

    # Filter to generative models and sort by name
    generative = [
        m for m in models
        if any(method.endswith("generateContent") for method in m.get("supportedGenerationMethods", []))
    ]

    print(f"\n{'Model Name':<50} {'Display Name':<35} {'Input Limit':>12}")
    print("-" * 100)

    for m in sorted(generative, key=lambda x: x.get("name", "")):
        name = m.get("name", "").replace("models/", "")
        display = m.get("displayName", "")
        input_limit = m.get("inputTokenLimit", "?")
        print(f"{name:<50} {display:<35} {str(input_limit):>12}")

    print(f"\nTotal generative models: {len(generative)}")


def cmd_generate(prompt: str, model: str, api_key: str, prompt_file: str = None) -> None:
    """Generate content synchronously and save the session."""
    # Handle prompt file
    if prompt_file:
        try:
            file_path = Path(prompt_file)
            prompt = file_path.read_text(encoding="utf-8")
            print(f"Loaded prompt from {prompt_file} ({len(prompt)} chars)", file=sys.stderr)
        except Exception as e:
            print(f"ERROR: Could not read prompt file: {e}", file=sys.stderr)
            sys.exit(1)

    if not prompt:
        print("ERROR: No prompt provided.", file=sys.stderr)
        sys.exit(1)

    print(f"Generating with {model}...", file=sys.stderr)
    start_time = time.time()

    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    path = f"/v1beta/models/{model}:generateContent"
    result = api_request("POST", path, body=body, api_key=api_key, model=model)

    elapsed = time.time() - start_time

    # Extract text from response
    response_text = ""
    candidates = result.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        response_text = "\n".join(p.get("text", "") for p in parts if "text" in p)

    if not response_text:
        print("WARNING: Empty response from model.", file=sys.stderr)
        response_text = "(empty response)"

    # Print response to stdout
    print(response_text)

    # Extract usage metadata
    usage = result.get("usageMetadata", {})
    metadata = {
        "mode": "generate",
        "model": model,
        "prompt_length": len(prompt),
        "response_length": len(response_text),
        "elapsed_seconds": round(elapsed, 2),
        "prompt_token_count": usage.get("promptTokenCount"),
        "candidates_token_count": usage.get("candidatesTokenCount"),
        "total_token_count": usage.get("totalTokenCount"),
        "finish_reason": candidates[0].get("finishReason") if candidates else None,
    }

    # Save session
    session_dir = save_session("generate", prompt, response_text, metadata)
    print(f"\nSession saved: {session_dir}", file=sys.stderr)


def cmd_deep_research(prompt: str, api_key: str, poll_interval: int, timeout: int, prompt_file: str = None) -> None:
    """Run deep research with polling and save the session."""
    # Handle prompt file
    if prompt_file:
        try:
            file_path = Path(prompt_file)
            prompt = file_path.read_text(encoding="utf-8")
            print(f"Loaded prompt from {prompt_file} ({len(prompt)} chars)", file=sys.stderr)
        except Exception as e:
            print(f"ERROR: Could not read prompt file: {e}", file=sys.stderr)
            sys.exit(1)

    if not prompt:
        print("ERROR: No prompt provided.", file=sys.stderr)
        sys.exit(1)

    print(f"Starting deep research (poll every {poll_interval}s, timeout {timeout}s)...", file=sys.stderr)
    start_time = time.time()

    # Start the research interaction
    body = {
        "model": f"models/{DEEP_RESEARCH_AGENT}",
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    # Create the interaction
    result = api_request("POST", "/v1beta/interactions", body=body, api_key=api_key)

    interaction_name = result.get("name", "")
    if not interaction_name:
        print("ERROR: No interaction name returned. Deep research may not be available.", file=sys.stderr)
        print(f"  Response: {json.dumps(result, indent=2)[:500]}", file=sys.stderr)
        sys.exit(1)

    print(f"Interaction created: {interaction_name}", file=sys.stderr)

    # Poll for completion
    response_text = ""
    final_status = "unknown"
    poll_count = 0

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout:
            print(f"ERROR: Timeout after {timeout}s.", file=sys.stderr)
            final_status = "timeout"
            break

        time.sleep(poll_interval)
        poll_count += 1

        print(f"  Polling ({poll_count}, {int(elapsed)}s elapsed)...", file=sys.stderr)

        poll_result = api_request("GET", f"/v1beta/{interaction_name}", api_key=api_key)

        # Check status
        done = poll_result.get("done", False)
        state = poll_result.get("metadata", {}).get("state", "")

        if state:
            print(f"  State: {state}", file=sys.stderr)

        if done:
            final_status = "completed"
            # Extract response from the result
            response_result = poll_result.get("result", {})
            candidates = response_result.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                response_text = "\n".join(p.get("text", "") for p in parts if "text" in p)
            break

    total_elapsed = time.time() - start_time

    if not response_text and final_status == "completed":
        print("WARNING: Research completed but response was empty.", file=sys.stderr)
        response_text = "(empty response)"

    if response_text:
        print(response_text)

    # Save session
    metadata = {
        "mode": "deep-research",
        "agent": DEEP_RESEARCH_AGENT,
        "interaction_name": interaction_name,
        "status": final_status,
        "poll_count": poll_count,
        "poll_interval_seconds": poll_interval,
        "timeout_seconds": timeout,
        "elapsed_seconds": round(total_elapsed, 2),
        "prompt_length": len(prompt),
        "response_length": len(response_text),
    }

    session_dir = save_session("deep-research", prompt, response_text, metadata)
    print(f"\nSession saved: {session_dir}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="gemini-research",
        description="Gemini REST API research tool. Zero dependencies.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list-models
    subparsers.add_parser("list-models", help="List available Gemini models")

    # generate
    gen_parser = subparsers.add_parser("generate", help="Generate content (sync)")
    gen_parser.add_argument("prompt", nargs="?", default="", help="The prompt text")
    gen_parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model name (default: {DEFAULT_MODEL})")
    gen_parser.add_argument("--prompt-file", default=None, help="Read prompt from file instead of argument")

    # deep-research
    dr_parser = subparsers.add_parser("deep-research", help="Deep research (async polling)")
    dr_parser.add_argument("prompt", nargs="?", default="", help="The research prompt")
    dr_parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL,
                           help=f"Poll interval in seconds (default: {DEFAULT_POLL_INTERVAL})")
    dr_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                           help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT})")
    dr_parser.add_argument("--prompt-file", default=None, help="Read prompt from file instead of argument")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    api_key = load_api_key()

    if args.command == "list-models":
        cmd_list_models(api_key)
    elif args.command == "generate":
        cmd_generate(args.prompt, args.model, api_key, getattr(args, "prompt_file", None))
    elif args.command == "deep-research":
        cmd_deep_research(
            args.prompt, api_key,
            args.poll_interval, args.timeout,
            getattr(args, "prompt_file", None)
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

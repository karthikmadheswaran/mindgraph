"""Service-account bootstrap for Vertex AI on hosts without gcloud ADC (e.g. Railway).

Production runs Vertex (USE_VERTEX=1) but Railway has no Application Default
Credentials file. If GOOGLE_CREDENTIALS_JSON (the full service-account key JSON,
pasted as a string) is present, this materializes it to a private temp file ONCE
and points ADC at it via GOOGLE_APPLICATION_CREDENTIALS — BEFORE any Vertex client
is constructed. That single env var is the uniform way to authenticate BOTH the
langchain `ChatVertexAI` client (app/llm.py) and the google-genai Vertex client
(app/embeddings.py): both read ADC, so neither needs an explicit credentials arg.

Precedence: an explicit GOOGLE_CREDENTIALS_JSON always wins. If it is absent we
leave the environment untouched, so local `gcloud auth application-default login`
ADC (the eval-harness path) keeps working unchanged.

Security: the credential value is NEVER logged. The temp file is created 0600 in
the OS temp dir (outside the repo tree), so it can't be committed. The repo is
public — the key must live ONLY in the Railway env var, never in a file in git.
"""

from __future__ import annotations

import json
import os
import tempfile

_BOOTSTRAPPED = False


def ensure_adc() -> None:
    """Materialize GOOGLE_CREDENTIALS_JSON to an ADC key file, if present.

    Idempotent and safe to call from multiple import sites (app/llm.py and
    app/embeddings.py both call it before building their Vertex clients).
    No-op when GOOGLE_CREDENTIALS_JSON is unset — local ADC is used instead.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return
    _BOOTSTRAPPED = True

    raw = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not raw or not raw.strip():
        # No inline key — fall back to whatever ADC the host already provides
        # (local: gcloud application_default_credentials.json). No-op.
        return

    try:
        json.loads(raw)  # validate it parses; do NOT log the contents
    except json.JSONDecodeError as exc:
        # Message intentionally does not echo the value.
        raise RuntimeError(
            "GOOGLE_CREDENTIALS_JSON is set but is not valid JSON — paste the "
            "full service-account key file contents, unmodified."
        ) from exc

    fd, path = tempfile.mkstemp(prefix="mindgraph-gcp-sa-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(raw)
    try:
        os.chmod(path, 0o600)  # best-effort; no-op on platforms without POSIX perms
    except OSError:
        pass

    # Explicit JSON wins over any pre-existing ADC for this process.
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path

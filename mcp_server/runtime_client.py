import httpx


class RuntimeAPIError(RuntimeError):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class RuntimeAPIClient:
    def __init__(self, base_url: str, timeout: float = 30.0, transport=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
        )

    def ask(self, input: str, session_id: str | None = None, mode: str = "default", context: dict | None = None):
        request_body = {
            "input": input,
            "session_id": session_id,
            "mode": mode,
            "context": dict(context or {}),
        }

        try:
            response = self._client.post("/runtime/ask", json=request_body)
        except httpx.TimeoutException as exc:
            raise RuntimeAPIError("Runtime API request timed out") from exc
        except httpx.RequestError as exc:
            raise RuntimeAPIError(f"Runtime API request failed: {exc}") from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeAPIError("Runtime API returned invalid JSON", status_code=response.status_code) from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeAPIError(
                f"Runtime API returned HTTP {response.status_code}",
                status_code=response.status_code,
                payload=payload,
            )

        return payload

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

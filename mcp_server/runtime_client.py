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
        return self._post_runtime(
            "/runtime/ask",
            input=input,
            session_id=session_id,
            mode=mode,
            context=context,
        )

    def frame(self, input: str, session_id: str | None = None, mode: str = "default", context: dict | None = None):
        return self._post_runtime(
            "/runtime/frame",
            input=input,
            session_id=session_id,
            mode=mode,
            context=context,
        )

    def validate(self, answer: str, context_packet: dict, validation_mode: str = "deterministic"):
        request_body = {
            "answer": answer,
            "context_packet": dict(context_packet or {}),
            "validation_mode": validation_mode,
        }
        return self._post_json("/runtime/validate", request_body)

    def _post_runtime(self, path, input, session_id=None, mode="default", context=None):
        request_body = {
            "input": input,
            "session_id": session_id,
            "mode": mode,
            "context": dict(context or {}),
        }
        return self._post_json(path, request_body)

    def _post_json(self, path, request_body):
        try:
            response = self._client.post(path, json=request_body)
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

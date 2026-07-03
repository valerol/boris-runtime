import json
import os

from dotenv import load_dotenv

class LLM:

    def __init__(self, api_key=None, load_environment=True):
        if load_environment:
            load_dotenv()
        self.api_key = os.getenv("OPENAI_API_KEY") if api_key is None else api_key
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.import_error = None
        self.client = self._build_client() if self.api_key else None

    def _build_client(self):
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:
            self.import_error = exc
            return None

        return OpenAI(api_key=self.api_key)

    def generate(self, context: dict):
        if not self.client:
            if self.api_key and self.import_error:
                return (
                    "OPENAI_SDK_NOT_INSTALLED: OPENAI_API_KEY is configured, "
                    "but the openai package is not installed."
                )

            user_input = context.get("input", "")
            return (
                "LOCAL_STUB_RESPONSE: OpenAI API key is not configured. "
                f"Received input: {user_input}"
            )

        prompt = f"""
You are inside BORIS Runtime.
Return only a concise, user-facing answer in plain text.
Do not include JSON, debug trace, SIMA, BOIS, runtime state, or internal fields.

Context:
{context}
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "BORIS structured executor"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )

        return self._to_user_answer(response.choices[0].message.content)

    def interpret_semantics(self, user_input: str):
        if not self.client:
            return self._local_semantic_interpretation(user_input)

        prompt = f"""
Return only valid JSON with this exact shape:
{{
  "semantic_summary": "...",
  "user_intent_hypothesis": "...",
  "context_entities": [],
  "ambiguity_score": 0.0,
  "risk_flags": [],
  "requires_clarification_hint": false
}}

Interpret the user's input semantically. Do not answer the user, do not choose
ANSWER or CLARIFICATION, and do not route the request.

Input:
{user_input}
"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "BORIS semantic interpreter"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )

        return self._normalize_semantic_interpretation(
            response.choices[0].message.content,
            user_input
        )

    def _to_user_answer(self, content):
        if not content:
            return ""

        text = content.strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text

        extracted = self._find_user_text(parsed)
        return extracted if extracted else "I processed the request, but no user-facing answer was returned."

    def _find_user_text(self, value):
        if isinstance(value, str):
            return value

        if isinstance(value, dict):
            for key in ("answer", "message", "content", "text", "summary"):
                nested = value.get(key)
                found = self._find_user_text(nested)
                if found:
                    return found

            for nested in value.values():
                found = self._find_user_text(nested)
                if found:
                    return found

        if isinstance(value, list):
            for nested in value:
                found = self._find_user_text(nested)
                if found:
                    return found

        return None

    def _normalize_semantic_interpretation(self, content, user_input):
        try:
            parsed = json.loads(content) if isinstance(content, str) else content
        except (TypeError, json.JSONDecodeError):
            parsed = {}

        if not isinstance(parsed, dict):
            parsed = {}

        fallback = self._local_semantic_interpretation(user_input)
        normalized = {
            "semantic_summary": str(
                parsed.get("semantic_summary") or fallback["semantic_summary"]
            ),
            "user_intent_hypothesis": str(
                parsed.get("user_intent_hypothesis")
                or fallback["user_intent_hypothesis"]
            ),
            "context_entities": parsed.get("context_entities")
            if isinstance(parsed.get("context_entities"), list)
            else fallback["context_entities"],
            "ambiguity_score": self._bounded_score(
                parsed.get("ambiguity_score"),
                fallback["ambiguity_score"]
            ),
            "risk_flags": parsed.get("risk_flags")
            if isinstance(parsed.get("risk_flags"), list)
            else fallback["risk_flags"],
            "requires_clarification_hint": bool(
                parsed.get(
                    "requires_clarification_hint",
                    fallback["requires_clarification_hint"]
                )
            )
        }
        return normalized

    def _local_semantic_interpretation(self, user_input):
        text = (user_input or "").strip()
        word_count = len(text.split())
        ambiguity_score = 0.85 if word_count <= 2 else 0.25
        requires_clarification = ambiguity_score > 0.6
        intent = "The user is asking for a response to the provided request."

        if not text:
            ambiguity_score = 1.0
            requires_clarification = True
            intent = "The user did not provide a request."

        return {
            "semantic_summary": text or "No user input was provided.",
            "user_intent_hypothesis": intent,
            "context_entities": [],
            "ambiguity_score": ambiguity_score,
            "risk_flags": [],
            "requires_clarification_hint": requires_clarification
        }

    @staticmethod
    def _bounded_score(value, fallback):
        try:
            score = float(value)
        except (TypeError, ValueError):
            return fallback

        return min(1.0, max(0.0, score))

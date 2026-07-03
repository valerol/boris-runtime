import json
import os

from dotenv import load_dotenv
from openai import OpenAI

class LLM:

    def __init__(self, api_key=None, load_environment=True):
        if load_environment:
            load_dotenv()
        self.api_key = os.getenv("OPENAI_API_KEY") if api_key is None else api_key
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def generate(self, context: dict):
        if not self.client:
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

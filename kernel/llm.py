import os

from dotenv import load_dotenv
from openai import OpenAI

class LLM:

    def __init__(self):
        load_dotenv()
        self.api_key = os.getenv("OPENAI_API_KEY")
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
Return structured reasoning output.

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

        return response.choices[0].message.content

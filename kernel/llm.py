from openai import OpenAI
import os

class LLM:

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def generate(self, context: dict):

        prompt = f"""
You are inside BORIS Runtime.
Return structured reasoning output.

Context:
{context}
"""

        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "BORIS structured executor"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )

        return response.choices[0].message.content

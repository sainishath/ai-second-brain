"""
generator.py — LLM Generation Layer
Supports: Claude (Anthropic), GPT-4o (OpenAI), Ollama (local)
"""

import os
from typing import List, Dict, Generator
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config", ".env"))

PROVIDER = os.getenv("LLM_PROVIDER", "claude")

# ─── System Prompts ───────────────────────────────────────────

SYSTEM_PROMPT = """You are the user's personal AI Second Brain — an intelligent knowledge assistant with access to their saved notes, articles, research, videos, and documents.

Your job:
1. Answer questions using ONLY the provided context from their knowledge base.
2. Be specific — cite which source(s) you're drawing from.
3. Identify patterns and connections across different saved content.
4. If the context doesn't contain enough information, say so clearly.
5. Be concise but complete. Think like a brilliant research assistant.

Always ground your answers in the user's actual saved content. Never hallucinate or invent sources."""

CHAT_PROMPT_TEMPLATE = """Here is relevant content from your knowledge base:

{context}

─────────────────────────────────────────

User question: {question}

Answer using the above sources. Reference specific titles/sources when relevant."""

# ─── Generator ────────────────────────────────────────────────

class Generator:
    def __init__(self):
        self.provider = PROVIDER
        self._setup()

    def _setup(self):
        if self.provider == "claude":
            import anthropic
            self.client = anthropic.Anthropic(
                api_key=os.getenv("ANTHROPIC_API_KEY")
            )
            self.model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")

        elif self.provider == "openai":
            import openai
            self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model = os.getenv("OPENAI_MODEL", "gpt-4o")

        elif self.provider == "ollama":
            from ollama import Client
            self.client = Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
            self.model = os.getenv("OLLAMA_MODEL", "llama3.2")
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

    def generate(self, question: str, context: str, history: List[Dict] = None) -> str:
        """Generate a response given a question and retrieved context."""
        user_message = CHAT_PROMPT_TEMPLATE.format(
            context=context,
            question=question,
        )

        messages = []
        if history:
            messages.extend(history[-6:])  # Keep last 3 turns
        messages.append({"role": "user", "content": user_message})

        if self.provider == "claude":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
            return response.content[0].text

        elif self.provider == "openai":
            all_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
            response = self.client.chat.completions.create(
                model=self.model,
                messages=all_messages,
                max_tokens=2048,
            )
            return response.choices[0].message.content

        elif self.provider == "ollama":
            all_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
            response = self.client.chat(
                model=self.model,
                messages=all_messages,
            )
            return response["message"]["content"]

    def stream(self, question: str, context: str) -> Generator[str, None, None]:
        """Stream a response token by token (Claude only for now)."""
        user_message = CHAT_PROMPT_TEMPLATE.format(
            context=context,
            question=question,
        )

        if self.provider == "claude":
            with self.client.messages.stream(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    yield text

        elif self.provider == "openai":
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                stream=True,
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        elif self.provider == "ollama":
            stream = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                stream=True,
            )
            for chunk in stream:
                if chunk["message"]["content"]:
                    yield chunk["message"]["content"]

        else:
            # Fallback: non-streaming
            yield self.generate(question, context)


# Singleton
_generator = None

def get_generator() -> 'Generator':
    global _generator
    if _generator is None:
        _generator = Generator()
    return _generator

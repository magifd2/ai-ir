"""LLM client using OpenAI-compatible API."""

from __future__ import annotations

import re
from typing import Any

import openai
from json_repair import repair_json
from openai import OpenAI

from aiir.config import LLMConfig


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks emitted by some LLMs.

    Handles both closed blocks (DeepSeek-R1, QwQ) and unclosed blocks
    (truncated output or models that omit the closing tag).

    Args:
        text: Raw LLM response text.

    Returns:
        Text with thinking blocks removed and surrounding whitespace stripped.
    """
    # Remove complete <think>...</think> blocks (DOTALL: . matches newlines)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Remove unclosed <think> block (opening tag through end of string)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)
    return text.strip()


class LLMClient:
    """Client for OpenAI-compatible LLM APIs.

    Supports any endpoint that implements the OpenAI chat completions API,
    including OpenAI, Azure OpenAI, Ollama, and other compatible services.
    """

    def __init__(self, config: LLMConfig) -> None:
        """Initialize the LLM client.

        Args:
            config: LLM configuration including base_url, api_key, and model.
        """
        self.config = config
        self._client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat completion request and return the response text.

        Args:
            system_prompt: System message to set context and behavior.
            user_prompt: User message containing the request.
            response_format: Optional response format dict (e.g. {"type": "json_object"}).

        Returns:
            The model's response as a string.
        """
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def complete_json(self, system_prompt: str, user_prompt: str) -> str:
        """Request JSON output from the LLM.

        Attempts JSON mode (``response_format={"type": "json_object"}``).
        Falls back to plain text mode if the endpoint does not support it
        (e.g. local LLMs that only accept ``"json_schema"`` or ``"text"``).

        Args:
            system_prompt: System message (should describe the expected JSON schema).
            user_prompt: User message containing the request.

        Returns:
            The model's JSON response as a string.
        """
        try:
            raw = self.complete(
                system_prompt,
                user_prompt,
                response_format={"type": "json_object"},
            )
        except openai.BadRequestError:
            # Endpoint does not support json_object mode; rely on prompt alone.
            raw = self.complete(system_prompt, user_prompt)
        # Normalize: strip <think> blocks, markdown code fences, and repair
        # minor JSON issues (reasoning models and some local LLMs add these).
        return repair_json(_strip_think_tags(raw or ""))

"""LLM client using OpenAI-compatible API."""

from __future__ import annotations

import re
from typing import Any

import openai
from json_repair import repair_json
from openai import OpenAI

from aiir.config import LLMConfig


# Tags whose entire content should be discarded (reasoning/thinking blocks).
# Covers: DeepSeek-R1/QwQ/Llama (<think>), Claude extended thinking (<thinking>),
# generic reasoning models (<reasoning>, <reflection>, <scratchpad>, <analysis>).
_REASONING_TAGS = r"think|thinking|reasoning|reflection|scratchpad|analysis"

_RE_CLOSED = re.compile(
    rf"<({_REASONING_TAGS})>.*?</\1>", re.DOTALL | re.IGNORECASE
)
_RE_UNCLOSED = re.compile(
    rf"<(?:{_REASONING_TAGS})>.*$", re.DOTALL | re.IGNORECASE
)
# Mistral uses square-bracket tokens: [THINK]...[/THINK]
_RE_MISTRAL = re.compile(r"\[THINK\].*?\[/THINK\]", re.DOTALL | re.IGNORECASE)
# DeepSeek-R1 / Hunyuan wrap the final answer in <answer>...</answer>.
# Extract the content rather than discarding it.
_RE_ANSWER = re.compile(r"<answer>(.*?)</answer>", re.DOTALL | re.IGNORECASE)


def _strip_reasoning_blocks(text: str) -> str:
    """Remove reasoning/thinking blocks emitted by various LLM models.

    Handles:
    - ``<think>``, ``<thinking>``, ``<reasoning>``, ``<reflection>``,
      ``<scratchpad>``, ``<analysis>`` — closed and unclosed variants
      (DeepSeek-R1, QwQ, Llama, Claude extended thinking, …)
    - ``[THINK]…[/THINK]`` — Mistral square-bracket format
    - ``<answer>…</answer>`` — DeepSeek-R1/Hunyuan answer wrapper:
      content is *extracted* (not discarded)

    Args:
        text: Raw LLM response text.

    Returns:
        Text with reasoning blocks removed and surrounding whitespace stripped.
    """
    text = _RE_CLOSED.sub("", text)
    text = _RE_UNCLOSED.sub("", text)
    text = _RE_MISTRAL.sub("", text)
    # If an <answer> wrapper remains, extract its content.
    m = _RE_ANSWER.search(text)
    if m:
        text = m.group(1)
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
        # Normalize: strip reasoning blocks, markdown code fences, and repair
        # minor JSON issues (reasoning models and some local LLMs add these).
        return repair_json(_strip_reasoning_blocks(raw or ""))

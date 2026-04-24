"""
PromptTemplate and ChatTemplate — the core template primitives.

PromptTemplate wraps a single string with named variables: {variable_name}.
ChatTemplate composes multiple role-specific templates into a message list.

Design:
  - Variables use Python str.format_map() — simple, zero dependencies
  - Missing variables raise TemplateRenderError (fail fast, not silently)
  - Templates are immutable; render() always returns a new object
  - ChatTemplate supports both string literals and PromptTemplate instances per message
"""
from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from typing import Any

from worker.llm.types import Message, Role


class TemplateRenderError(ValueError):
    """Raised when required template variables are missing or invalid."""
    pass


@dataclass(frozen=True)
class PromptTemplate:
    """
    A single-string prompt template with named {variable} placeholders.

    Usage:
        t = PromptTemplate("Analyse the {topic} niche for {channel_name}.")
        msg = t.render(topic="finance", channel_name="WealthPro")
        message = t.to_message(Role.user, topic="finance", channel_name="WealthPro")
    """

    template: str
    input_variables: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Auto-extract variable names if not provided
        if not self.input_variables:
            vars_ = tuple(
                v
                for _, v, _, _ in string.Formatter().parse(self.template)
                if v is not None
            )
            object.__setattr__(self, "input_variables", vars_)

    def render(self, **kwargs: Any) -> str:
        missing = set(self.input_variables) - set(kwargs)
        if missing:
            raise TemplateRenderError(
                f"Missing template variables: {sorted(missing)}. "
                f"Required: {sorted(self.input_variables)}"
            )
        try:
            return self.template.format_map(kwargs)
        except (KeyError, IndexError) as exc:
            raise TemplateRenderError(f"Template render failed: {exc}") from exc

    def to_message(self, role: Role, **kwargs: Any) -> Message:
        return Message(role=role, content=self.render(**kwargs))

    def partial(self, **fixed_kwargs: Any) -> "PromptTemplate":
        """Return a new template with some variables already filled in."""
        rendered = self.template.format_map(_PartialDict(fixed_kwargs))
        return PromptTemplate(rendered)

    @classmethod
    def from_string(cls, text: str) -> "PromptTemplate":
        return cls(template=text)

    def __repr__(self) -> str:
        preview = self.template[:60].replace("\n", "\\n")
        return f"PromptTemplate(vars={list(self.input_variables)!r}, template={preview!r}...)"


class _PartialDict(dict):
    """dict subclass that leaves missing keys unreplaced (for partial rendering)."""
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@dataclass(frozen=True)
class ChatTemplate:
    """
    Multi-message template. Each slot is (Role, PromptTemplate | str).
    All messages share the same render kwargs.

    Usage:
        tmpl = ChatTemplate([
            (Role.system, SYSTEM_PROMPT),
            (Role.user, PromptTemplate("Channel: {channel_name}\\nNiche: {niche}\\n{task}")),
        ])
        messages = tmpl.render(channel_name="WealthPro", niche="finance", task="Scout 10 topics")
    """

    messages: tuple[tuple[Role, PromptTemplate | str], ...]

    def render(self, **kwargs: Any) -> list[Message]:
        result: list[Message] = []
        for role, content in self.messages:
            if isinstance(content, PromptTemplate):
                result.append(content.to_message(role, **kwargs))
            else:
                result.append(Message(role=role, content=content))
        return result

    @property
    def input_variables(self) -> tuple[str, ...]:
        all_vars: list[str] = []
        for _, content in self.messages:
            if isinstance(content, PromptTemplate):
                all_vars.extend(content.input_variables)
        return tuple(dict.fromkeys(all_vars))

    @classmethod
    def from_dicts(cls, messages: list[dict]) -> "ChatTemplate":
        """
        Build from a list of {"role": "system|user|assistant", "template": "string"} dicts.
        """
        slots = [
            (Role(m["role"]), PromptTemplate(m["template"]))
            for m in messages
        ]
        return cls(messages=tuple(slots))

    def with_system(self, system_prompt: str) -> "ChatTemplate":
        """Prepend or replace the system message."""
        rest = [(r, t) for r, t in self.messages if r != Role.system]
        return ChatTemplate(messages=tuple([(Role.system, system_prompt)] + rest))

    def __repr__(self) -> str:
        roles = [r.value for r, _ in self.messages]
        return f"ChatTemplate(roles={roles}, vars={list(self.input_variables)!r})"

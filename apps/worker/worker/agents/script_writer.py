"""
Deprecated compatibility wrapper.

Use `worker.agents.scriptwriter.ScriptwriterAgent` with `.run(...)` instead.
"""
from __future__ import annotations

import warnings

from worker.agents.scriptwriter import ScriptwriterAgent, ScriptwriterInput


class ScriptWriterAgent(ScriptwriterAgent):
    def __init__(self, *args, **kwargs) -> None:
        warnings.warn(
            "ScriptWriterAgent is deprecated. Use ScriptwriterAgent.run(...) with ScriptwriterInput.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)

    async def generate(
        self,
        *,
        topic: str,
        tone: str,
        target_duration_seconds: int = 600,
        keywords: list[str] | None = None,
        channel_niche: str = "general",
        additional_context: str | None = None,
    ) -> dict:
        out = await self.run(
            ScriptwriterInput(
                topic=topic,
                niche=channel_niche,
                tone=tone,
                target_duration_seconds=target_duration_seconds,
                keywords=keywords or [],
                style_notes=additional_context or "",
            )
        )
        body_sections = [s.content for s in out.sections if s.type not in {"hook", "cta", "outro"}]
        cta_section = next((s.content for s in out.sections if s.type == "cta"), "")
        return {
            "title": out.title,
            "hook": out.hook,
            "body": "\n\n".join(body_sections).strip(),
            "cta": cta_section,
            "keywords": list(out.keyword_placement.keys()),
            "estimated_duration_seconds": out.estimated_duration_seconds,
        }

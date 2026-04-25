"""
Deprecated compatibility wrapper.

Use `worker.agents.metadata.MetadataAgent` with `.run(...)` instead.
"""
from __future__ import annotations

import warnings

from worker.agents.metadata import MetadataAgent, MetadataInput


class SEOAnalyzerAgent(MetadataAgent):
    def __init__(self, *args, **kwargs) -> None:
        warnings.warn(
            "SEOAnalyzerAgent is deprecated. Use MetadataAgent.run(...) with MetadataInput.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)

    async def analyze(
        self,
        *,
        title: str,
        script_body: str,
        keywords: list[str],
        niche: str = "general",
    ) -> dict:
        out = await self.run(
            MetadataInput(
                title=title,
                script=script_body,
                niche=niche,
                target_keywords=keywords,
            )
        )
        keyword_values = list(out.keyword_density.values())
        keyword_coverage = round((sum(keyword_values) / len(keyword_values)) * 300, 2) if keyword_values else 0.0
        title_score = 9.0 if len(out.optimized_title) <= 100 else 6.0
        overall = round(min(10.0, max(0.0, (title_score * 0.4) + (keyword_coverage * 0.6))), 2)
        return {
            "overall_score": overall,
            "title_score": round(title_score, 2),
            "keyword_coverage": keyword_coverage,
            "suggested_title": out.optimized_title,
            "suggested_tags": out.tags,
            "improvement_notes": out.card_suggestions,
            "description": out.description,
            "hashtags": out.hashtags,
            "chapters": [c.model_dump() for c in out.chapters],
        }

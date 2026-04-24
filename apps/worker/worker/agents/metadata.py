"""
MetadataAgent — generates SEO-optimised YouTube metadata from a script.

Produces title, description, tags, chapters, hashtags, and card suggestions.
All output is ready to paste into YouTube Studio.
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field

from worker.agents.base import BaseAgent
from worker.agents.schemas import AgentInput, AgentOutput

# ── schemas ───────────────────────────────────────────────────────────────────

class MetadataInput(AgentInput):
    title: str
    script: str
    niche: str
    target_keywords: list[str] = Field(default_factory=list)
    channel_name: str = ""
    language: str = "en"
    monetization_enabled: bool = True


class Chapter(BaseModel):
    title: str
    start_seconds: int
    description: str


class MetadataOutput(AgentOutput):
    optimized_title: str
    title_variants: list[str]
    description: str
    tags: list[str]
    chapters: list[Chapter]
    category: str
    default_language: str
    hashtags: list[str]
    end_screen_suggestion: str
    card_suggestions: list[str]
    keyword_density: dict[str, float]
    character_counts: dict[str, int]


# ── prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """You are a YouTube SEO specialist generating metadata for faceless educational channels.

Constraints:
- Title: max 100 chars, keyword in first 60 chars, CTR-optimized
- Description: 500-1000 chars, primary keyword in first 2 sentences, timestamps, links section
- Tags: max 500 total chars, mix of exact-match and broad keywords
- Chapters must start at 0:00 and cover the full video
- Hashtags: 3-5 relevant, placed at end of description
- category: the most accurate YouTube category ID name

Description structure:
  1. Hook sentence (keyword)
  2. What this video covers (2-3 sentences)
  3. Chapter timestamps
  4. Resources / free tools mentioned
  5. About the channel (1 sentence)
  6. #Hashtags

Return ONLY valid JSON, no markdown."""

_SCHEMA = """{
  "optimized_title": "string (max 100 chars)",
  "title_variants": ["variant 1 (A/B option)", "variant 2"],
  "description": "string (full YouTube description)",
  "tags": ["tag1", "tag2", "tag3"],
  "chapters": [
    {"title": "string", "start_seconds": 0, "description": "string"}
  ],
  "category": "Education",
  "default_language": "en",
  "hashtags": ["#tag1", "#tag2"],
  "end_screen_suggestion": "string",
  "card_suggestions": ["string", "string"],
  "keyword_density": {"keyword": 0.025},
  "character_counts": {"title": 72, "description": 680, "tags_total": 380}
}"""

# ── agent ─────────────────────────────────────────────────────────────────────

class MetadataAgent(BaseAgent[MetadataInput, MetadataOutput]):
    agent_name = "metadata"
    default_temperature = 0.3

    async def execute(self, inp: MetadataInput) -> MetadataOutput:
        script_preview = inp.script[:2000] + ("..." if len(inp.script) > 2000 else "")
        user = (
            f"Channel: {inp.channel_name or 'unnamed'}\n"
            f"Niche: {inp.niche}\n"
            f"Language: {inp.language}\n"
            f"Original title: {inp.title}\n"
            f"Target keywords: {', '.join(inp.target_keywords)}\n"
            f"Monetization: {'enabled' if inp.monetization_enabled else 'disabled'}\n\n"
            f"=== SCRIPT PREVIEW ===\n{script_preview}\n\n"
            f"Generate full YouTube metadata. Return JSON:\n{_SCHEMA}"
        )
        raw = await self._call_llm(_SYSTEM, user, temperature=0.3, json_mode=True)
        data = self._parse_json(raw)
        return self._hydrate(data)

    async def mock_execute(self, inp: MetadataInput) -> MetadataOutput:
        rng = random.Random(self._seed(inp.input_hash()))
        topic = inp.title
        kws = inp.target_keywords or [inp.niche, topic.split()[0].lower()]
        primary_kw = kws[0] if kws else inp.niche

        # Build optimised title (keyword near front, power word, number if possible)
        opt_title = (
            inp.title if len(inp.title) <= 80
            else inp.title[:77] + "..."
        )

        # Build full description
        description_parts = [
            f"{primary_kw.title()} explained step-by-step — this video covers everything you need to get results.",
            f"",
            f"In this video, you'll learn: the core framework, common mistakes to avoid, and a real case study "
            f"with numbers. Whether you're new to {inp.niche} or looking to level up, this breakdown gives you "
            f"a clear system you can apply immediately.",
            f"",
            f"⏱ CHAPTERS",
            f"0:00 — Introduction",
            f"1:30 — Why Most People Struggle With {topic[:40]}",
            f"4:00 — The Step-by-Step Framework",
            f"7:30 — Real Case Study & Results",
            f"10:00 — Common Mistakes to Avoid",
            f"12:30 — Your Action Plan",
            f"",
            f"📥 FREE RESOURCES",
            f"→ Audit Template: [link in pinned comment]",
            f"→ Full Checklist PDF: [description link]",
            f"",
            f"About this channel: We break down complex {inp.niche} topics into clear, actionable frameworks "
            f"{'for ' + inp.channel_name if inp.channel_name else '— no fluff, just results'}.",
            f"",
            f"#{primary_kw.replace(' ', '')} #{inp.niche.replace(' ', '')} #education",
        ]
        description = "\n".join(description_parts)

        tags = list(dict.fromkeys([
            primary_kw,
            f"{primary_kw} for beginners",
            f"how to {primary_kw}",
            f"{primary_kw} tips",
            inp.niche,
            f"{inp.niche} tutorial",
            f"{inp.niche} for beginners",
            "educational video",
            "how to",
            topic.lower(),
            f"{topic.lower()} guide",
            f"learn {primary_kw}",
            "faceless youtube",
            "step by step",
        ]))[:15]

        chapters = [
            Chapter(title="Introduction", start_seconds=0,
                    description="Overview of what you'll learn and why it matters"),
            Chapter(title=f"Why Most People Struggle With {topic[:40]}", start_seconds=90,
                    description="Root causes and common misconceptions explained"),
            Chapter(title="The Step-by-Step Framework", start_seconds=240,
                    description="Phase 1: Audit. Phase 2: Prioritise. Phase 3: Execute."),
            Chapter(title="Real Case Study & Results", start_seconds=450,
                    description="Concrete example with actual numbers and timeline"),
            Chapter(title="Common Mistakes to Avoid", start_seconds=600,
                    description="The 3 mistakes that derail most people — and the fixes"),
            Chapter(title="Your Action Plan", start_seconds=750,
                    description="Exactly what to do in the next 24 hours"),
        ]

        keyword_density = {kw: round(rng.uniform(0.015, 0.035), 3) for kw in kws[:4]}

        return MetadataOutput(
            optimized_title=opt_title,
            title_variants=[
                f"The Complete {topic} Guide ({rng.randint(2024, 2025)})",
                f"How to {topic}: Step-by-Step for Beginners",
                f"{topic}: What Nobody Tells You",
            ],
            description=description,
            tags=tags,
            chapters=chapters,
            category="Education",
            default_language=inp.language,
            hashtags=[
                f"#{primary_kw.replace(' ', '')}",
                f"#{inp.niche.replace(' ', '')}",
                "#education",
            ],
            end_screen_suggestion=(
                f"Add 'next video' card pointing to your most-watched video in the {inp.niche} playlist. "
                "Show subscribe button at 20 seconds from end."
            ),
            card_suggestions=[
                f"At 3:00 — link to your '{inp.niche} beginner guide' video",
                "At 8:00 — link to the free audit template mentioned in the script",
            ],
            keyword_density=keyword_density,
            character_counts={
                "title": len(opt_title),
                "description": len(description),
                "tags_total": sum(len(t) + 1 for t in tags),
            },
        )

    @staticmethod
    def _hydrate(data: dict) -> MetadataOutput:
        return MetadataOutput(
            optimized_title=data.get("optimized_title", ""),
            title_variants=data.get("title_variants", []),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            chapters=[Chapter(**c) for c in data.get("chapters", [])],
            category=data.get("category", "Education"),
            default_language=data.get("default_language", "en"),
            hashtags=data.get("hashtags", []),
            end_screen_suggestion=data.get("end_screen_suggestion", ""),
            card_suggestions=data.get("card_suggestions", []),
            keyword_density=data.get("keyword_density", {}),
            character_counts=data.get("character_counts", {}),
        )

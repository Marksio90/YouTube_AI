"""
ResearchAgent — structured content research brief for a given topic.

Produces key facts, statistics with source hints, a detailed content outline,
and differentiation angles. Output feeds directly into ScriptwriterAgent.
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field

from worker.agents.base import BaseAgent
from worker.agents.schemas import AgentInput, AgentOutput

# ── schemas ───────────────────────────────────────────────────────────────────

class ResearchInput(AgentInput):
    topic: str
    niche: str
    depth: Literal["quick", "standard", "deep"] = "standard"
    focus_areas: list[str] = Field(default_factory=list)
    target_audience: str = "general"


class Statistic(BaseModel):
    fact: str
    value: str
    source_hint: str
    year: int | None = None


class ContentSection(BaseModel):
    title: str
    key_points: list[str]
    estimated_duration_seconds: int
    talking_points: list[str]


class ResearchOutput(AgentOutput):
    topic: str
    summary: str
    key_facts: list[str]
    statistics: list[Statistic]
    content_outline: list[ContentSection]
    seo_keywords: list[str]
    competitor_angles: list[str]
    unique_angles: list[str]
    suggested_expert_references: list[str]
    research_confidence: float = Field(ge=0.0, le=1.0)


# ── prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """You are a professional content researcher for faceless YouTube channels.
You produce research briefs that scriptwriters use to create authoritative educational videos.

Standards:
- Statistics must include a realistic source_hint (e.g. "Harvard Business Review, 2023")
- Key facts must be non-obvious — avoid Wikipedia-level generalities
- Unique angles must genuinely differentiate from standard YouTube coverage
- Content outline sections must sum to a realistic total video duration
- Research confidence reflects how well-established the evidence base is (0.0–1.0)

Return ONLY valid JSON, no markdown."""

_SCHEMA = """{
  "summary": "string (3-4 sentences on the topic landscape)",
  "key_facts": ["fact1", "fact2"],
  "statistics": [
    {"fact": "string", "value": "string", "source_hint": "string", "year": 2024}
  ],
  "content_outline": [
    {
      "title": "string",
      "key_points": ["point1", "point2"],
      "estimated_duration_seconds": 120,
      "talking_points": ["expanded point1", "expanded point2"]
    }
  ],
  "seo_keywords": ["kw1", "kw2"],
  "competitor_angles": ["common coverage angle 1"],
  "unique_angles": ["differentiated angle 1"],
  "suggested_expert_references": ["type of expert to cite"],
  "research_confidence": 0.85
}"""

_DEPTH_SPEC = {
    "quick":    "Provide 3 key facts, 2 statistics, 4 outline sections, 4 keywords.",
    "standard": "Provide 6 key facts, 4 statistics, 6 outline sections, 6 keywords.",
    "deep":     "Provide 10 key facts, 6 statistics, 8 outline sections, 8 keywords. Include contrarian viewpoints.",
}

_SECTION_TEMPLATES = [
    ("Hook & Opening Statement", ["Counter-intuitive fact", "Stakes established"], 90,
     ["Open with a stat that surprises even informed viewers",
      "Make the audience feel they're about to learn something they cannot find elsewhere"]),
    ("The Core Problem Explained", ["Root cause", "Common misconceptions", "Cost of inaction"], 150,
     ["Explain why the surface-level understanding fails people",
      "Use a relatable analogy — 'it's like...' framing works well here"]),
    ("Framework: Step 1", ["Core principle", "Step-by-step breakdown", "Pitfall to avoid"], 180,
     ["Make the first method immediately actionable",
      "Show the before/after contrast so the benefit is visceral"]),
    ("Framework: Step 2", ["Building on Step 1", "Advanced application", "Expected results"], 150,
     ["Deepen the strategy — this separates basic from intermediate",
      "Cite the type of practitioner who validates this approach"]),
    ("Real-World Case Study", ["Specific scenario", "Quantified outcomes", "Key success factor"], 120,
     ["Anchor the theory in a believable, specific example with numbers",
      "Exact figures (even estimated) build trust more than vague descriptions"]),
    ("Common Mistakes & Fixes", ["Mistake 1 + fix", "Mistake 2 + fix", "Mistake 3 + fix"], 120,
     ["Frame from personal experience to lower defensiveness",
      "Each fix must be immediately executable — no 'consult a professional'"]),
    ("Advanced Insight", ["Non-obvious principle", "Contrarian take", "Edge case"], 150,
     ["This section rewards viewers who make it past the midpoint",
      "A genuine contrarian insight sharply increases comment engagement"]),
    ("Action Plan & CTA", ["Top 3 takeaways", "Prioritised next steps", "Subscribe prompt"], 90,
     ["Restate the 3 key points with fresh phrasing — not copy-paste",
      "Give exactly one concrete action for today, not a list of ten"]),
]

# ── agent ─────────────────────────────────────────────────────────────────────

class ResearchAgent(BaseAgent[ResearchInput, ResearchOutput]):
    agent_name = "research"
    default_temperature = 0.4

    async def execute(self, inp: ResearchInput) -> ResearchOutput:
        focus = (
            f"\nFocus especially on: {', '.join(inp.focus_areas)}"
            if inp.focus_areas else ""
        )
        user = (
            f"Topic: {inp.topic}\n"
            f"Niche: {inp.niche}\n"
            f"Target audience: {inp.target_audience}\n"
            f"Depth: {inp.depth} — {_DEPTH_SPEC[inp.depth]}{focus}\n\n"
            f"Return JSON:\n{_SCHEMA}"
        )
        raw = await self._call_llm(_SYSTEM, user, temperature=0.4, json_mode=True)
        data = self._parse_json(raw)
        return self._hydrate(inp.topic, data)

    async def mock_execute(self, inp: ResearchInput) -> ResearchOutput:
        rng = random.Random(self._seed(inp.input_hash()))
        n_sections = {"quick": 4, "standard": 6, "deep": 8}[inp.depth]
        n_facts    = {"quick": 3, "standard": 6, "deep": 10}[inp.depth]
        n_stats    = {"quick": 2, "standard": 4, "deep": 6}[inp.depth]
        n_kw       = {"quick": 4, "standard": 6, "deep": 8}[inp.depth]

        sections = [
            ContentSection(
                title=title,
                key_points=points,
                estimated_duration_seconds=int(dur * rng.uniform(0.85, 1.15)),
                talking_points=tp,
            )
            for title, points, dur, tp in _SECTION_TEMPLATES[:n_sections]
        ]

        return ResearchOutput(
            topic=inp.topic,
            summary=(
                f"{inp.topic} is a high-engagement topic in the {inp.niche} space with above-average "
                "advertiser interest and strong educational video potential. Retention data across similar "
                "keyword clusters shows >62% average view duration when structured as a problem-solution "
                "framework. The keyword cluster has seen 34% YoY search growth and remains under-served "
                "by quality long-form content."
            ),
            key_facts=[
                f"Over 70% of {inp.niche} beginners make the same 3 foundational mistakes",
                f"The average practitioner wastes 40% of their effort on low-leverage approaches",
                f"Top-performing channels in this niche publish between 8-12 minute videos",
                "Most existing tutorials on this topic are 18+ months old and miss recent shifts",
                f"Search volume for '{inp.topic}' has grown 34% year-over-year",
                "Viewers who watch past the 3-minute mark on this topic have an 8x higher subscribe rate",
                "Only 12% of videos covering this topic include quantified, verifiable outcomes",
                "The top 1% of practitioners share a single non-obvious habit undocumented in mainstream sources",
                f"Ad CPMs for {inp.niche}-adjacent keywords range from $8 to $22",
                "Channels using case-study formats in this niche average 2.3x more comments per view",
            ][:n_facts],
            statistics=[
                Statistic(fact="Practitioners using a structured framework see significantly better outcomes",
                          value="3.2x improvement vs. ad-hoc approach",
                          source_hint="McKinsey Global Institute meta-analysis", year=2023),
                Statistic(fact="Average time to measurable results with correct methodology",
                          value="6–8 weeks", source_hint="Peer-reviewed industry study", year=2024),
                Statistic(fact="Annual cost of ignoring this topic for the average professional",
                          value="$4,200–$18,000 in missed opportunity",
                          source_hint="Independent financial modelling, N=2,400", year=2023),
                Statistic(fact="Percentage of online content on this topic that is outdated or misleading",
                          value="67%", source_hint="Content quality audit across 1,200 articles", year=2024),
                Statistic(fact="YouTube viewer retention improvement when problem-solution format is used",
                          value="+28% avg view duration",
                          source_hint="Creator analytics aggregator report", year=2024),
                Statistic(fact="Increase in subscriber conversion when specific numbers are cited in title",
                          value="+41% CTR vs. generic titles", source_hint="A/B test dataset, N=180 channels", year=2023),
            ][:n_stats],
            content_outline=sections,
            seo_keywords=[
                inp.topic.lower(),
                f"{inp.topic.lower()} for beginners",
                f"how to {inp.topic.lower()}",
                f"{inp.topic.lower()} tips 2024",
                f"best {inp.topic.lower()} strategy",
                f"{inp.topic.lower()} mistakes",
                f"{inp.niche} {inp.topic.lower()}",
                f"{inp.topic.lower()} complete guide",
            ][:n_kw],
            competitor_angles=[
                "Generic listicle with surface-level advice and no evidence",
                "Heavily sponsored reviews that obscure objective analysis",
                "Beginner content that never addresses the intermediate plateau",
            ],
            unique_angles=[
                f"First-principles breakdown of why standard {inp.topic} advice systematically fails",
                "Cost-benefit analysis with real numbers most creators are afraid to show",
                "Systematic framework vs. ad-hoc tips — process beats tactics every time",
            ],
            suggested_expert_references=[
                f"Certified {inp.niche} professional with 10+ years of documented practice",
                "Academic researcher with peer-reviewed publications in this domain",
                "Practitioner with a publicly documented, quantified case study",
            ],
            research_confidence=round(rng.uniform(0.78, 0.94), 2),
        )

    @staticmethod
    def _hydrate(topic: str, data: dict) -> ResearchOutput:
        return ResearchOutput(
            topic=topic,
            summary=data.get("summary", ""),
            key_facts=data.get("key_facts", []),
            statistics=[Statistic(**s) for s in data.get("statistics", [])],
            content_outline=[ContentSection(**s) for s in data.get("content_outline", [])],
            seo_keywords=data.get("seo_keywords", []),
            competitor_angles=data.get("competitor_angles", []),
            unique_angles=data.get("unique_angles", []),
            suggested_expert_references=data.get("suggested_expert_references", []),
            research_confidence=float(data.get("research_confidence", 0.8)),
        )

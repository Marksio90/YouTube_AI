"""
ScriptwriterAgent — writes a full narration-ready video script.

Takes topic + research brief and returns a structured script with hook,
sectioned body, CTA, production notes, and estimated duration.
"""
from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel, Field

from worker.agents.base import BaseAgent
from worker.agents.schemas import AgentInput, AgentOutput

# ── schemas ───────────────────────────────────────────────────────────────────

class ScriptwriterInput(AgentInput):
    topic: str
    niche: str
    research: dict = Field(default_factory=dict)
    tone: Literal["educational", "entertaining", "inspirational", "analytical", "conversational"] = "educational"
    target_duration_seconds: int = Field(default=600, ge=60, le=3600)
    keywords: list[str] = Field(default_factory=list)
    hook_style: Literal["question", "statistic", "story", "controversy", "promise"] = "statistic"
    call_to_action: str = "subscribe and turn on notifications for more"
    style_notes: str = ""


class ScriptSection(BaseModel):
    type: Literal["hook", "intro", "main", "transition", "cta", "outro"]
    title: str
    content: str
    duration_seconds: int
    production_notes: str = ""


class ScriptwriterOutput(AgentOutput):
    title: str
    description_short: str
    hook: str
    sections: list[ScriptSection]
    word_count: int
    estimated_duration_seconds: int
    readability_level: Literal["basic", "intermediate", "advanced"]
    keyword_placement: dict[str, list[str]]
    production_notes: str

    @property
    def body(self) -> str:
        body_sections = [s.content for s in self.sections if s.type not in {"hook", "cta", "outro"}]
        return "\n\n".join(body_sections).strip()

    @property
    def cta(self) -> str:
        return next((s.content for s in self.sections if s.type == "cta"), "")

    @property
    def keywords(self) -> list[str]:
        return list(self.keyword_placement.keys())


# ── prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """You are an expert YouTube scriptwriter for faceless educational channels.
You write compelling, well-paced narration scripts that retain viewers through to the end.

Script standards:
- Hook must land within the first 30 seconds — no slow introductions
- Each section should have a natural micro-cliffhanger or open loop to the next
- Narration pace: 140-160 words per minute (avoid dense paragraphs)
- Use conversational language — contractions, second person ("you"), rhetorical questions
- Keywords appear naturally in the first 60 seconds and in section titles
- CTA is specific, not generic ("smash the bell")
- Production notes guide the video editor on B-roll and graphic cues

Return ONLY valid JSON, no markdown."""

_SCHEMA = """{
  "title": "string (max 80 chars, optimised for CTR)",
  "description_short": "string (2 sentence video summary for metadata)",
  "hook": "string (full hook text, 30-45 seconds of narration)",
  "sections": [
    {
      "type": "hook|intro|main|transition|cta|outro",
      "title": "string",
      "content": "string (full narration text for this section)",
      "duration_seconds": 90,
      "production_notes": "string (B-roll cues, graphic overlays, pacing notes)"
    }
  ],
  "word_count": 1200,
  "estimated_duration_seconds": 540,
  "readability_level": "intermediate",
  "keyword_placement": {"keyword": ["first 60s", "section 2 title"]},
  "production_notes": "string (overall production guidance)"
}"""

# ── mock script content ───────────────────────────────────────────────────────

def _mock_script_sections(topic: str, niche: str, tone: str, target_dur: int, hook_style: str, cta: str) -> list[ScriptSection]:
    hook_openers = {
        "question":    f"What if everything you thought you knew about {topic} was keeping you stuck?",
        "statistic":   f"Here's a number that shocked me: 73% of people who try {topic} give up within 60 days — not because it doesn't work, but because they were never shown the right approach.",
        "story":       f"Two years ago, I made every mistake you can make with {topic}. Today I'm going to save you from every single one of them.",
        "controversy": f"I'm going to say something that most {niche} channels will never admit: most of the advice online about {topic} is completely backwards.",
        "promise":     f"By the end of this video, you'll have a clear, step-by-step system for {topic} that you can start using today — no fluff, no theory, just what actually works.",
    }
    hook_text = hook_openers.get(hook_style, hook_openers["statistic"])

    # Proportionally distribute duration
    section_ratios = [0.08, 0.07, 0.20, 0.20, 0.18, 0.12, 0.10, 0.05]
    durations = [max(30, int(target_dur * r)) for r in section_ratios]

    wpm = 150
    def words(dur: int) -> str:
        return f"[{int(dur * wpm / 60)} words of narration]"

    return [
        ScriptSection(
            type="hook",
            title="Opening Hook",
            content=hook_text + f"\n\nStay with me — because what I'm about to show you changes how you approach {topic} completely.",
            duration_seconds=durations[0],
            production_notes="Cold open — no intro music yet. Tight cut on first word. B-roll: abstract visuals matching the hook concept.",
        ),
        ScriptSection(
            type="intro",
            title="What We're Covering Today",
            content=(
                f"In this video, I'm breaking down {topic} into a framework anyone can follow. "
                f"We'll cover the three things most people get wrong, the exact steps to fix them, "
                f"and a real case study with numbers. No filler — let's get into it.\n\n"
                f"{words(durations[1])}"
            ),
            duration_seconds=durations[1],
            production_notes="Intro music fades in briefly then out. Show chapter timestamps as graphics overlay. Fast cuts.",
        ),
        ScriptSection(
            type="main",
            title=f"Why Most People Fail at {topic}",
            content=(
                f"Let's start with the uncomfortable truth: the standard advice on {topic} is designed "
                f"for people who already understand the fundamentals. If you're newer to {niche}, "
                f"following that advice is like trying to run before you can walk — it looks right, but it sets you up to fail.\n\n"
                f"The three root causes I see most often are: first, skipping the diagnosis phase. "
                f"Second, optimising for the wrong metric. And third — this one surprises people — "
                f"doing too much too soon instead of building one system at a time.\n\n"
                f"{words(durations[2])}"
            ),
            duration_seconds=durations[2],
            production_notes="Use animated text to highlight the three causes as they're named. B-roll: relatable 'failure' visuals — not cringe stock footage.",
        ),
        ScriptSection(
            type="main",
            title="The Framework: A Step-by-Step System",
            content=(
                f"Here's the framework I've refined over time for {topic}. I call it the Three-Phase approach, and it works because it matches how the {niche} actually operates, not how it's typically taught.\n\n"
                f"Phase one is Audit. Before you change anything, you need a clear picture of where you stand. "
                f"This takes about 20 minutes and involves three specific measurements I'll walk you through.\n\n"
                f"Phase two is Prioritise. Once you have your audit, you rank your opportunities by impact-to-effort ratio. "
                f"You're looking for the 20% of changes that will drive 80% of your results.\n\n"
                f"Phase three is Execute and Iterate. You implement your top priority, measure the outcome after 14 days, then adjust. "
                f"This cycle continues until you've systematically moved through your opportunity list.\n\n"
                f"{words(durations[3])}"
            ),
            duration_seconds=durations[3],
            production_notes="Animated diagram of the three phases. Use numbered callouts. Slow down pacing here — this is the value-dense section.",
        ),
        ScriptSection(
            type="main",
            title="Real Case Study: The Numbers",
            content=(
                f"Let me make this concrete with a case study. "
                f"A practitioner in the {niche} space applied this exact framework starting with a baseline audit. "
                f"In week one, the audit revealed three critical bottlenecks — all were things they thought were fine.\n\n"
                f"After applying Phase two prioritisation, they focused on only one change in the first 14 days. "
                f"The result? A 31% improvement in their primary metric. Not by doing more — by doing less, but deliberately.\n\n"
                f"By week eight, the compounding effect of systematic iteration had produced a 3x improvement from baseline. "
                f"Same resources, same time investment — different approach entirely.\n\n"
                f"{words(durations[4])}"
            ),
            duration_seconds=durations[4],
            production_notes="Chart animation showing the 3x improvement curve. Highlight key numbers with graphic callouts. Pause 2 seconds after '3x improvement'.",
        ),
        ScriptSection(
            type="main",
            title="The Three Mistakes That Kill Progress",
            content=(
                f"Now, before you go implement this, let me flag the three mistakes that derail most people even with a solid framework.\n\n"
                f"Mistake one: measuring too early. Results in {niche} typically lag the action by 10-14 days. "
                f"If you check your metrics at day 3 and see nothing, you haven't failed — you're just measuring too soon.\n\n"
                f"Mistake two: optimising for vanity metrics. Clicks, views, and followers are not outcomes — "
                f"they're inputs. Focus on the downstream metric that actually reflects your goal.\n\n"
                f"Mistake three: paralysis by analysis. The audit phase is designed to take 20 minutes, not 20 days. "
                f"An imperfect plan executed beats a perfect plan left on the whiteboard every time.\n\n"
                f"{words(durations[5])}"
            ),
            duration_seconds=durations[5],
            production_notes="Bold text overlays for each mistake number. Use a visual checkmark when transitioning to the fix.",
        ),
        ScriptSection(
            type="cta",
            title="Your Action Step & Next Video",
            content=(
                f"Here's your single action step for today: run the 20-minute audit. "
                f"That's it — just the audit. Don't optimise yet. Don't change anything. "
                f"Just get the baseline data, because without it, everything else is guesswork.\n\n"
                f"I've linked a free audit template in the description — it's the same one from the case study.\n\n"
                f"If this was useful, {cta}. And if you want to go deeper, the next video covers Phase two in detail: "
                f"exactly how to prioritise your opportunities when everything feels urgent.\n\n"
                f"{words(durations[6])}"
            ),
            duration_seconds=durations[6],
            production_notes="End-screen graphics appear at 20 seconds remaining. Show next video thumbnail. Point gesture cue for voiceover artist at 'next video'.",
        ),
        ScriptSection(
            type="outro",
            title="Outro",
            content=f"See you in the next one.",
            duration_seconds=durations[7],
            production_notes="Outro music in. Channel logo fade. End screen holds for 20 seconds.",
        ),
    ]


# ── agent ─────────────────────────────────────────────────────────────────────

class ScriptwriterAgent(BaseAgent[ScriptwriterInput, ScriptwriterOutput]):
    # Contract: output always guarantees `title`, `hook`, `sections`, `body`, `cta`,
    # `keywords`, and `estimated_duration_seconds`.
    agent_name = "scriptwriter"
    default_temperature = 0.75

    async def execute(self, inp: ScriptwriterInput) -> ScriptwriterOutput:
        research_block = ""
        if inp.research:
            outline = inp.research.get("content_outline", [])
            facts = inp.research.get("key_facts", [])
            stats = inp.research.get("statistics", [])
            stat_str = "; ".join(
                f"{s.get('value', '')} ({s.get('source_hint', '')})"
                for s in stats[:3]
            )
            outline_titles = ", ".join(s.get("title", "") for s in outline[:6])
            research_block = (
                f"\n\n=== RESEARCH BRIEF ===\n"
                f"Key facts: {'; '.join(facts[:5])}\n"
                f"Statistics: {stat_str}\n"
                f"Outline sections: {outline_titles}"
            )

        user = (
            f"Topic: {inp.topic}\n"
            f"Niche: {inp.niche}\n"
            f"Tone: {inp.tone}\n"
            f"Target duration: {inp.target_duration_seconds} seconds\n"
            f"Hook style: {inp.hook_style}\n"
            f"Keywords to include: {', '.join(inp.keywords)}\n"
            f"CTA: {inp.call_to_action}\n"
            + (f"Style notes: {inp.style_notes}\n" if inp.style_notes else "")
            + research_block
            + f"\n\nWrite the complete script. Return JSON:\n{_SCHEMA}"
        )
        raw = await self._call_llm(_SYSTEM, user, temperature=0.75, json_mode=True)
        data = self._parse_json(raw)
        return self._hydrate(data)

    async def mock_execute(self, inp: ScriptwriterInput) -> ScriptwriterOutput:
        rng = random.Random(self._seed(inp.input_hash()))
        sections = _mock_script_sections(
            inp.topic, inp.niche, inp.tone,
            inp.target_duration_seconds, inp.hook_style, inp.call_to_action,
        )
        total_dur = sum(s.duration_seconds for s in sections)
        word_count = int(total_dur * 150 / 60)

        return ScriptwriterOutput(
            title=f"The Complete {inp.topic} System: Step-by-Step for {inp.niche.title()} ({rng.randint(2024, 2025)})",
            description_short=(
                f"Learn the exact framework for {inp.topic} that produces measurable results in 6-8 weeks. "
                f"Includes a real case study, the three most common mistakes, and a free audit template."
            ),
            hook=sections[0].content,
            sections=sections,
            word_count=word_count,
            estimated_duration_seconds=total_dur,
            readability_level="intermediate",
            keyword_placement={kw: ["first 60 seconds", "section 2 title"] for kw in inp.keywords[:3]},
            production_notes=(
                "This script targets 8-10 minute final cut. Use Epidemic Sound license tracks. "
                "B-roll sourcing: Pexels, Unsplash for stills, Pixabay for motion. "
                "Chapters should be added at section boundaries for YouTube chapter generation."
            ),
        )

    @staticmethod
    def _hydrate(data: dict) -> ScriptwriterOutput:
        return ScriptwriterOutput(
            title=data.get("title", ""),
            description_short=data.get("description_short", ""),
            hook=data.get("hook", ""),
            sections=[ScriptSection(**s) for s in data.get("sections", [])],
            word_count=int(data.get("word_count", 0)),
            estimated_duration_seconds=int(data.get("estimated_duration_seconds", 0)),
            readability_level=data.get("readability_level", "intermediate"),
            keyword_placement=data.get("keyword_placement", {}),
            production_notes=data.get("production_notes", ""),
        )

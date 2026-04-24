"""
TemplateRegistry — global catalog of all prompt templates.

Built-in templates cover every agent in the system.
Custom templates can be registered at runtime.

Usage:
    # Get a registered template and render it
    tmpl = templates.get_chat("agent.scout")
    messages = tmpl.render(niche="finance", channel_name="WealthPro", count=15)

    # Register your own
    templates.register("my_task", PromptTemplate("Summarise {topic} in 3 bullets."))

    # List all registered names
    templates.list()  # ["agent.scout", "agent.research", ...]
"""
from __future__ import annotations

import structlog

from worker.llm.templates.template import ChatTemplate, PromptTemplate, TemplateRenderError
from worker.llm.types import Role

log = structlog.get_logger(__name__)


class TemplateRegistry:
    def __init__(self) -> None:
        self._templates: dict[str, PromptTemplate | ChatTemplate] = {}

    def register(self, name: str, template: PromptTemplate | ChatTemplate) -> None:
        self._templates[name] = template

    def register_chat(self, name: str, system: str, user_template: str) -> None:
        """Shortcut: register a 2-message (system + user) ChatTemplate."""
        self._templates[name] = ChatTemplate(messages=(
            (Role.system, system),
            (Role.user, PromptTemplate(user_template)),
        ))

    def get(self, name: str) -> PromptTemplate:
        tmpl = self._templates.get(name)
        if tmpl is None:
            raise KeyError(f"Template '{name}' not registered. Available: {self.list()}")
        if not isinstance(tmpl, PromptTemplate):
            raise TypeError(f"Template '{name}' is a ChatTemplate — use get_chat()")
        return tmpl

    def get_chat(self, name: str) -> ChatTemplate:
        tmpl = self._templates.get(name)
        if tmpl is None:
            raise KeyError(f"Template '{name}' not registered. Available: {self.list()}")
        if not isinstance(tmpl, ChatTemplate):
            raise TypeError(f"Template '{name}' is a PromptTemplate — use get()")
        return tmpl

    def list(self) -> list[str]:
        return sorted(self._templates.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._templates


# ── built-in agent templates ──────────────────────────────────────────────────

def _build_registry() -> TemplateRegistry:
    r = TemplateRegistry()

    # ── ScoutAgent ────────────────────────────────────────────────────────────
    r.register_chat(
        "agent.scout",
        system=(
            "You are a YouTube content intelligence analyst for faceless (no-face) channels.\n"
            "You identify trending, monetizable video opportunities in a given niche.\n"
            "For each opportunity provide: title, content_angle, search_volume_tier (low/medium/high/very_high),\n"
            "competition (low/medium/high), monetization_potential (low/medium/high), trend (rising/stable/declining/viral),\n"
            "estimated_views_30d, target_audience (1 sentence), hook_suggestion, keywords (3-5), urgency (evergreen/timely/urgent).\n"
            "Return ONLY valid JSON, no markdown."
        ),
        user_template=(
            "Niche: {niche}\n"
            "Channel: {channel_name}\n"
            "Scouting window: last {days_back} days\n"
            "Competitors: {competitors}\n"
            "Generate exactly {count} ranked opportunities.\n"
            "{filters}\n\n"
            "Return JSON matching: {schema}"
        ),
    )

    # ── OpportunityScorerAgent ────────────────────────────────────────────────
    r.register_chat(
        "agent.opportunity_scorer",
        system=(
            "You are a YouTube content opportunity analyst scoring topics for faceless educational channels.\n"
            "Score each topic across 5 dimensions (0-10 each): search_demand, competition (inverse),\n"
            "monetization, timeliness, channel_fit.\n"
            "Thresholds: pursue ≥7.5 | consider 6.0-7.4 | monitor 4.5-5.9 | skip <4.5\n"
            "Return ONLY valid JSON, no markdown."
        ),
        user_template=(
            "Topic: {topic}\n"
            "Description: {description}\n"
            "Niche: {niche}\n"
            "Keywords: {keywords}\n"
            "Channel: {channel_subscribers} subscribers, ~{channel_avg_views} avg views\n"
            "{existing_block}\n\n"
            "Score this opportunity. Return JSON: {schema}"
        ),
    )

    # ── ResearchAgent ─────────────────────────────────────────────────────────
    r.register_chat(
        "agent.research",
        system=(
            "You are a professional content researcher for faceless YouTube channels.\n"
            "You produce research briefs with verified statistics, structured content outline, and differentiation angles.\n"
            "Statistics must include a realistic source_hint. Key facts must be non-obvious.\n"
            "Return ONLY valid JSON, no markdown."
        ),
        user_template=(
            "Topic: {topic}\n"
            "Niche: {niche}\n"
            "Target audience: {target_audience}\n"
            "Depth: {depth} — {depth_instruction}\n"
            "{focus_block}\n\n"
            "Return JSON: {schema}"
        ),
    )

    # ── ScriptwriterAgent ─────────────────────────────────────────────────────
    r.register_chat(
        "agent.scriptwriter",
        system=(
            "You are an expert YouTube scriptwriter for faceless educational channels.\n"
            "You write compelling, well-paced narration scripts that retain viewers through to the end.\n"
            "Script standards:\n"
            "- Hook must land within the first 30 seconds\n"
            "- Each section has a natural micro-cliffhanger to the next\n"
            "- Narration pace: 140-160 words per minute\n"
            "- Use conversational language — contractions, second person\n"
            "- CTA is specific, not generic\n"
            "Return ONLY valid JSON, no markdown."
        ),
        user_template=(
            "Topic: {topic}\n"
            "Niche: {niche}\n"
            "Tone: {tone}\n"
            "Target duration: {target_duration_seconds} seconds\n"
            "Hook style: {hook_style}\n"
            "Keywords: {keywords}\n"
            "CTA: {call_to_action}\n"
            "{style_notes_block}"
            "{research_block}\n\n"
            "Write the complete script. Return JSON: {schema}"
        ),
    )

    # ── ComplianceAgent ───────────────────────────────────────────────────────
    r.register_chat(
        "agent.compliance",
        system=(
            "You are a YouTube content policy specialist and brand safety analyst.\n"
            "Review content for: Community Guidelines violations, copyright risk, advertiser-friendliness,\n"
            "age-restricted content triggers, misleading claims, spam signals, unqualified medical/legal/financial advice.\n"
            "Severity: blocking (removed/demonetized) | warning (restricted distribution) | info (best practice)\n"
            "advertiser_friendly_score: 0=demonetized, 10=fully brand-safe\n"
            "Return ONLY valid JSON, no markdown."
        ),
        user_template=(
            "Platform: {platform}\n"
            "Monetization: {monetization}\n"
            "Target audience: {target_audience}\n"
            "Niche: {niche}\n\n"
            "=== TITLE ===\n{title}\n\n"
            "=== DESCRIPTION ===\n{description}\n\n"
            "=== TAGS ===\n{tags}\n\n"
            "=== SCRIPT (preview) ===\n{script_preview}\n\n"
            "Review for compliance. Return JSON: {schema}"
        ),
    )

    # ── ThumbnailAgent ────────────────────────────────────────────────────────
    r.register_chat(
        "agent.thumbnail",
        system=(
            "You are a YouTube thumbnail designer and CTR optimization specialist.\n"
            "You create concepts for faceless channels — no faces, no people.\n"
            "Each concept needs: headline_text (max 5 words), layout, color_scheme (5 hex colors),\n"
            "composition description, visual_elements list, ai_image_prompt (DALL-E ready), predicted_ctr_score.\n"
            "Principles: high contrast at 168x94px, numbers prominent, no red/green combinations.\n"
            "Return ONLY valid JSON, no markdown."
        ),
        user_template=(
            "Video title: {title}\n"
            "Topic: {topic}\n"
            "Niche: {niche}\n"
            "Channel style: {channel_style}\n"
            "Generate {count} distinct concepts.\n"
            "{preferences_block}\n\n"
            "Return JSON: {schema}"
        ),
    )

    # ── MetadataAgent ─────────────────────────────────────────────────────────
    r.register_chat(
        "agent.metadata",
        system=(
            "You are a YouTube SEO specialist generating metadata for faceless educational channels.\n"
            "Title: max 100 chars, keyword in first 60 chars.\n"
            "Description: 500-1000 chars, keyword in first 2 sentences, timestamps, links, hashtags.\n"
            "Tags: max 500 total chars, mix exact-match and broad keywords.\n"
            "Return ONLY valid JSON, no markdown."
        ),
        user_template=(
            "Channel: {channel_name}\n"
            "Niche: {niche}\n"
            "Original title: {title}\n"
            "Target keywords: {keywords}\n"
            "Language: {language}\n\n"
            "=== SCRIPT PREVIEW ===\n{script_preview}\n\n"
            "Generate full YouTube metadata. Return JSON: {schema}"
        ),
    )

    # ── OptimizationAgent ─────────────────────────────────────────────────────
    r.register_chat(
        "agent.optimization",
        system=(
            "You are a YouTube growth strategist specialising in content performance optimisation.\n"
            "For each suggestion: category, priority, current (quoted text), suggested (fully written fix),\n"
            "impact (which metric, estimated change), effort (easy/medium/hard), expected_metric_delta.\n"
            "Predicted deltas must be conservative and evidence-based.\n"
            "Return ONLY valid JSON, no markdown."
        ),
        user_template=(
            "Niche: {niche}\n"
            "Goals: {goals}\n"
            "Channel avg CTR: {channel_avg_ctr}\n"
            "Channel avg AVD: {channel_avg_avd_seconds}s\n\n"
            "=== TITLE ===\n{title}\n\n"
            "=== CURRENT METADATA ===\n{metadata_block}\n\n"
            "=== SCRIPT PREVIEW ===\n{script_preview}\n"
            "{analytics_block}\n\n"
            "Generate optimisation report. Return JSON: {schema}"
        ),
    )

    # ── TopicResearcher (legacy) ───────────────────────────────────────────────
    r.register_chat(
        "agent.topic_researcher.discover",
        system=(
            "You are a YouTube content strategist specializing in no-face (faceless) channels.\n"
            "Identify high-potential video topics for a given niche.\n"
            "Return ONLY valid JSON. No markdown, no explanation."
        ),
        user_template=(
            "Channel niche: {niche}\n"
            "Channel name: {channel_name}\n"
            "Generate exactly {count} high-potential topic ideas for a faceless YouTube channel.\n"
            "{avoid_block}\n\n"
            "Return JSON: {schema}"
        ),
    )

    r.register_chat(
        "agent.topic_researcher.score",
        system=(
            "You are a YouTube SEO and trend analyst.\n"
            "Score the given topic on its current viability for a faceless YouTube channel.\n"
            "Return ONLY valid JSON."
        ),
        user_template=(
            "Niche: {niche}\n"
            "Topic title: {title}\n"
            "Description: {description}\n"
            "Keywords: {keywords}\n\n"
            "Score this topic. Return JSON: {schema}"
        ),
    )

    # ── Recommender (legacy) ──────────────────────────────────────────────────
    r.register_chat(
        "agent.recommender",
        system=(
            "You are a YouTube channel growth strategist specializing in faceless content.\n"
            "Analyze performance data and generate concrete, actionable recommendations.\n"
            "Return ONLY valid JSON. No markdown, no preamble."
        ),
        user_template=(
            "Channel: {channel_name}\n"
            "Niche: {niche}\n\n"
            "=== TOP PERFORMING VIDEOS ===\n{top_videos_block}\n\n"
            "=== ANALYTICS SUMMARY ===\n{analytics_block}\n\n"
            "=== EXISTING TOPIC PIPELINE ===\n{topics_block}\n\n"
            "Generate recommendations. Return JSON: {schema}"
        ),
    )

    return r


# ── global singleton ──────────────────────────────────────────────────────────

templates = _build_registry()

"""
ThumbnailAgent — generates visual thumbnail concepts with DALL-E-ready prompts.

Returns multiple concepts with hex color schemes, composition guidance,
and a ready-to-use AI image generation prompt for each.
"""
from __future__ import annotations

import random
import uuid
from typing import Literal

from pydantic import BaseModel, Field

from worker.agents.base import BaseAgent
from worker.agents.schemas import AgentInput, AgentOutput

# ── schemas ───────────────────────────────────────────────────────────────────

class ThumbnailInput(AgentInput):
    title: str
    topic: str
    niche: str
    channel_style: Literal["clean_modern", "bold_contrast", "minimal", "dark_premium", "colorful_pop"] = "clean_modern"
    count: int = Field(default=3, ge=1, le=5)
    style_preferences: list[str] = Field(default_factory=list)
    avoid_elements: list[str] = Field(default_factory=list)


class ColorScheme(BaseModel):
    primary: str
    secondary: str
    text: str
    background: str
    accent: str


class ThumbnailConcept(BaseModel):
    concept_id: str
    headline_text: str
    sub_text: str | None = None
    layout: Literal["bold_text", "split_layout", "chart_focus", "before_after", "number_list", "minimal_icon"]
    color_scheme: ColorScheme
    composition: str
    visual_elements: list[str]
    ai_image_prompt: str
    predicted_ctr_score: float = Field(ge=0.0, le=10.0)


class ThumbnailOutput(AgentOutput):
    concepts: list[ThumbnailConcept]
    top_pick_id: str
    split_test_recommendation: str
    design_rationale: str


# ── prompts ───────────────────────────────────────────────────────────────────

_SYSTEM = """You are a YouTube thumbnail designer and CTR optimization specialist.
You create thumbnail concepts for faceless (no-face) channels — no people, no faces.

For each concept:
- headline_text: max 5 words, bold, immediately readable at small sizes
- sub_text: optional supporting text (max 3 words)
- layout: bold_text | split_layout | chart_focus | before_after | number_list | minimal_icon
- color_scheme: 5 hex colors (primary, secondary, text, background, accent)
- composition: 1-2 sentence description of how elements are arranged
- visual_elements: list of non-human visual assets to include
- ai_image_prompt: ready to paste into DALL-E 3 or Midjourney
- predicted_ctr_score: 0-10, your confidence in CTR relative to niche baseline

Thumbnail principles:
- High contrast text readable at 168x94px (mobile YouTube)
- No faces, no people — abstract, data, charts, objects, icons only
- Avoid red/green combinations (accessibility)
- Numbers in the title should appear visually prominent

Return ONLY valid JSON, no markdown."""

_SCHEMA = """{
  "concepts": [
    {
      "concept_id": "string",
      "headline_text": "string (max 5 words)",
      "sub_text": "string or null",
      "layout": "bold_text",
      "color_scheme": {
        "primary": "#hex",
        "secondary": "#hex",
        "text": "#hex",
        "background": "#hex",
        "accent": "#hex"
      },
      "composition": "string",
      "visual_elements": ["element1", "element2"],
      "ai_image_prompt": "string",
      "predicted_ctr_score": 7.5
    }
  ],
  "top_pick_id": "string",
  "split_test_recommendation": "string",
  "design_rationale": "string"
}"""

# ── style palettes ────────────────────────────────────────────────────────────

_PALETTES: dict[str, list[dict]] = {
    "clean_modern": [
        {"primary": "#1A1A2E", "secondary": "#16213E", "text": "#E6E6E6", "background": "#0F3460", "accent": "#E94560"},
        {"primary": "#2D2D2D", "secondary": "#404040", "text": "#FFFFFF", "background": "#1A1A1A", "accent": "#F7B731"},
        {"primary": "#003049", "secondary": "#D62828", "text": "#F1FAEE", "background": "#023E8A", "accent": "#F77F00"},
    ],
    "bold_contrast": [
        {"primary": "#FF0000", "secondary": "#CC0000", "text": "#FFFFFF", "background": "#000000", "accent": "#FFDD00"},
        {"primary": "#FF6B35", "secondary": "#F7C59F", "text": "#EBEBD3", "background": "#004E89", "accent": "#1A936F"},
        {"primary": "#6A0572", "secondary": "#AB83A1", "text": "#FFFFFF", "background": "#1B0000", "accent": "#F9C80E"},
    ],
    "minimal": [
        {"primary": "#F5F5F5", "secondary": "#E0E0E0", "text": "#212121", "background": "#FFFFFF", "accent": "#1565C0"},
        {"primary": "#FAFAFA", "secondary": "#EEEEEE", "text": "#333333", "background": "#FFFFFF", "accent": "#E53935"},
        {"primary": "#F8F9FA", "secondary": "#DEE2E6", "text": "#212529", "background": "#FFFFFF", "accent": "#198754"},
    ],
    "dark_premium": [
        {"primary": "#0D0D0D", "secondary": "#1A1A1A", "text": "#D4AF37", "background": "#050505", "accent": "#C0A060"},
        {"primary": "#111111", "secondary": "#222222", "text": "#FFFFFF", "background": "#0A0A0A", "accent": "#00B4D8"},
        {"primary": "#1C1C1C", "secondary": "#2C2C2C", "text": "#E8E8E8", "background": "#141414", "accent": "#7B2FBE"},
    ],
    "colorful_pop": [
        {"primary": "#FF595E", "secondary": "#FFCA3A", "text": "#FFFFFF", "background": "#6A4C93", "accent": "#8AC926"},
        {"primary": "#3A86FF", "secondary": "#FF006E", "text": "#FFFFFF", "background": "#FFBE0B", "accent": "#FB5607"},
        {"primary": "#06D6A0", "secondary": "#118AB2", "text": "#FFFFFF", "background": "#073B4C", "accent": "#FFD166"},
    ],
}

_LAYOUTS: list[str] = ["bold_text", "split_layout", "chart_focus", "before_after", "number_list", "minimal_icon"]

_VISUAL_ELEMENT_POOLS = {
    "finance": ["bar chart trending up", "gold coins", "dollar sign icon", "stock ticker display",
                "piggy bank silhouette", "growth arrow", "credit card graphic"],
    "tech":    ["circuit board pattern", "code terminal screenshot", "AI neural network graphic",
                "laptop with glowing screen", "data flow visualization", "microchip close-up"],
    "health":  ["DNA helix", "brain scan graphic", "clock with food icons", "molecular structure",
                "cell microscopy visual", "heartbeat EKG line"],
    "default": ["upward trending graph", "magnifying glass on data", "checklist with checkmarks",
                "lightbulb icon", "calendar grid", "speedometer dial", "puzzle pieces"],
}


def _get_visual_elements(niche: str, rng: random.Random) -> list[str]:
    n = niche.lower()
    for key in _VISUAL_ELEMENT_POOLS:
        if key in n:
            pool = _VISUAL_ELEMENT_POOLS[key]
            return rng.sample(pool, min(3, len(pool)))
    return rng.sample(_VISUAL_ELEMENT_POOLS["default"], 3)


def _build_dalle_prompt(topic: str, elements: list[str], layout: str, palette: dict, style: str) -> str:
    return (
        f"YouTube thumbnail, {style.replace('_', ' ')} style, no people no faces, "
        f"topic '{topic}', layout '{layout.replace('_', ' ')}', "
        f"featuring {', '.join(elements)}, "
        f"background color {palette['background']}, "
        f"accent color {palette['accent']}, "
        f"ultra-high contrast, bold typography space reserved on {'left' if layout == 'split_layout' else 'center'}, "
        f"16:9 aspect ratio, 1280x720px, professional digital art, flat design with depth"
    )


# ── agent ─────────────────────────────────────────────────────────────────────

class ThumbnailAgent(BaseAgent[ThumbnailInput, ThumbnailOutput]):
    agent_name = "thumbnail"
    default_temperature = 0.8

    async def execute(self, inp: ThumbnailInput) -> ThumbnailOutput:
        avoid = f"\nAvoid: {', '.join(inp.avoid_elements)}" if inp.avoid_elements else ""
        prefs = f"\nStyle preferences: {', '.join(inp.style_preferences)}" if inp.style_preferences else ""
        user = (
            f"Video title: {inp.title}\n"
            f"Topic: {inp.topic}\n"
            f"Niche: {inp.niche}\n"
            f"Channel style: {inp.channel_style}\n"
            f"Generate {inp.count} distinct thumbnail concepts.{prefs}{avoid}\n\n"
            f"Return JSON:\n{_SCHEMA}"
        )
        raw = await self._call_llm(_SYSTEM, user, temperature=0.8, json_mode=True)
        data = self._parse_json(raw)
        return self._hydrate(data)

    async def mock_execute(self, inp: ThumbnailInput) -> ThumbnailOutput:
        rng = random.Random(self._seed(inp.input_hash()))
        palettes = _PALETTES.get(inp.channel_style, _PALETTES["clean_modern"])
        layouts = _LAYOUTS.copy()
        rng.shuffle(layouts)

        # Derive short headline from title
        words = inp.title.split()
        headline = " ".join(words[:4]) if len(words) > 4 else inp.title

        concepts: list[ThumbnailConcept] = []
        for i in range(inp.count):
            palette = palettes[i % len(palettes)]
            layout = layouts[i % len(layouts)]
            elements = _get_visual_elements(inp.niche, rng)
            cid = str(uuid.uuid4())[:8]

            concepts.append(ThumbnailConcept(
                concept_id=cid,
                headline_text=headline.upper() if layout == "bold_text" else headline,
                sub_text=["Step-by-Step", "Full Guide", "Real Results", None][i % 4],
                layout=layout,
                color_scheme=ColorScheme(**palette),
                composition=(
                    f"{'Large bold headline centered over' if layout == 'bold_text' else 'Left-side text block beside'} "
                    f"the primary visual element. Background is {palette['background']} with "
                    f"{palette['accent']} accent strip along the {'bottom' if i % 2 == 0 else 'left side'}."
                ),
                visual_elements=elements,
                ai_image_prompt=_build_dalle_prompt(inp.topic, elements, layout, palette, inp.channel_style),
                predicted_ctr_score=round(rng.uniform(6.0, 9.2), 1),
            ))

        top_pick = max(concepts, key=lambda c: c.predicted_ctr_score)
        return ThumbnailOutput(
            concepts=concepts,
            top_pick_id=top_pick.concept_id,
            split_test_recommendation=(
                f"A/B test concept '{concepts[0].concept_id}' (bold text layout) against "
                f"concept '{concepts[1].concept_id if len(concepts) > 1 else concepts[0].concept_id}' "
                f"({concepts[1].layout if len(concepts) > 1 else 'alternate'} layout). "
                f"Run for minimum 500 impressions per variant before declaring a winner."
            ),
            design_rationale=(
                f"Concepts prioritize high-contrast text legibility at 168x94px mobile size. "
                f"All designs avoid human faces to align with faceless channel format. "
                f"Color palette '{inp.channel_style}' selected to match brand consistency. "
                f"Top pick achieves the highest predicted CTR through {top_pick.layout.replace('_',' ')} layout."
            ),
        )

    @staticmethod
    def _hydrate(data: dict) -> ThumbnailOutput:
        concepts = [
            ThumbnailConcept(
                **{**c, "color_scheme": ColorScheme(**c["color_scheme"])}
            )
            for c in data.get("concepts", [])
        ]
        return ThumbnailOutput(
            concepts=concepts,
            top_pick_id=data.get("top_pick_id", concepts[0].concept_id if concepts else ""),
            split_test_recommendation=data.get("split_test_recommendation", ""),
            design_rationale=data.get("design_rationale", ""),
        )

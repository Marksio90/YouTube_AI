from __future__ import annotations

import json
import re
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.agents.base import BaseAgent

logger = structlog.get_logger(__name__)

MAX_SCRIPT_CHARS = 6_000
MAX_TITLE_CHARS = 180
MAX_NICHE_CHARS = 80
MAX_KEYWORDS = 30
MAX_TAGS = 20
MAX_NOTES = 12

SYSTEM_PROMPT = """You are a senior YouTube SEO strategist and content performance analyst.

Your job is to analyze a YouTube video title, script excerpt, niche and target keywords.
Score the content with strict, practical SEO reasoning.

Scoring criteria, each from 0.0 to 10.0:
- Keyword density and placement in title, hook, body and likely metadata
- Search intent alignment
- Title click-through potential
- Watch-time optimization signals
- Trend and niche relevance
- Clarity of topic promise
- Discoverability for long-tail search

Rules:
- Return valid JSON only.
- Do not include markdown.
- Do not include explanations outside JSON.
- Use numbers for scores.
- Scores must stay between 0.0 and 10.0.
- Suggested tags must be short, searchable and relevant.
- Improvement notes must be specific, actionable and non-generic.
"""

SEO_OUTPUT_SCHEMA = {
    "overall_score": 8.5,
    "title_score": 9.0,
    "keyword_coverage": 7.5,
    "search_intent_match": 8.0,
    "ctr_potential": 8.0,
    "watch_time_signal_score": 8.0,
    "trend_relevance": 7.0,
    "suggested_title": "Improved title if needed",
    "suggested_tags": ["tag1", "tag2"],
    "improvement_notes": ["specific action 1", "specific action 2"],
    "detected_primary_intent": "informational",
    "risk_flags": ["weak hook", "keyword missing in title"],
}


class SEOAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    overall_score: float = Field(ge=0.0, le=10.0)
    title_score: float = Field(ge=0.0, le=10.0)
    keyword_coverage: float = Field(ge=0.0, le=10.0)
    search_intent_match: float = Field(ge=0.0, le=10.0)
    ctr_potential: float = Field(default=0.0, ge=0.0, le=10.0)
    watch_time_signal_score: float = Field(default=0.0, ge=0.0, le=10.0)
    trend_relevance: float = Field(default=0.0, ge=0.0, le=10.0)

    suggested_title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    suggested_tags: list[str] = Field(default_factory=list, max_length=MAX_TAGS)
    improvement_notes: list[str] = Field(default_factory=list, max_length=MAX_NOTES)

    detected_primary_intent: str = Field(default="unknown", max_length=80)
    risk_flags: list[str] = Field(default_factory=list, max_length=MAX_NOTES)

    @field_validator(
        "overall_score",
        "title_score",
        "keyword_coverage",
        "search_intent_match",
        "ctr_potential",
        "watch_time_signal_score",
        "trend_relevance",
        mode="before",
    )
    @classmethod
    def normalize_score(cls, value: Any) -> float:
        if isinstance(value, str):
            value = value.replace(",", ".").strip()

        score = float(value)
        return round(max(0.0, min(10.0, score)), 2)

    @field_validator("suggested_title", "detected_primary_intent", mode="before")
    @classmethod
    def normalize_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        return re.sub(r"\s+", " ", text)

    @field_validator("suggested_tags", "improvement_notes", "risk_flags", mode="before")
    @classmethod
    def normalize_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            value = [item.strip() for item in value.split(",")]

        if not isinstance(value, list):
            return []

        normalized: list[str] = []
        seen: set[str] = set()

        for item in value:
            text = re.sub(r"\s+", " ", str(item or "").strip())
            if not text:
                continue

            dedupe_key = text.lower()
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            normalized.append(text)

        return normalized


class SEOAnalyzerAgent(BaseAgent):
    async def analyze(
        self,
        *,
        title: str,
        script_body: str,
        keywords: list[str],
        niche: str = "general",
    ) -> dict[str, Any]:
        result = await self.analyze_typed(
            title=title,
            script_body=script_body,
            keywords=keywords,
            niche=niche,
        )
        return result.model_dump()

    async def analyze_typed(
        self,
        *,
        title: str,
        script_body: str,
        keywords: list[str],
        niche: str = "general",
    ) -> SEOAnalysisResult:
        clean_title = self._clean_title(title)
        clean_script = self._clean_script(script_body)
        clean_niche = self._clean_niche(niche)
        clean_keywords = self._clean_keywords(keywords)

        user_message = self._build_user_message(
            title=clean_title,
            script_body=clean_script,
            keywords=clean_keywords,
            niche=clean_niche,
        )

        logger.info(
            "seo_analyzer.analysis_started",
            title=clean_title[:80],
            niche=clean_niche,
            keyword_count=len(clean_keywords),
            script_chars=len(clean_script),
        )

        raw = await self._call(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            temperature=0.25,
        )

        payload = self._parse_json_response(raw)
        result = self._validate_result(payload=payload, fallback_title=clean_title)

        logger.info(
            "seo_analyzer.analysis_completed",
            title=clean_title[:80],
            niche=clean_niche,
            overall_score=result.overall_score,
            title_score=result.title_score,
            keyword_coverage=result.keyword_coverage,
            search_intent_match=result.search_intent_match,
            suggested_tags_count=len(result.suggested_tags),
            risk_flags_count=len(result.risk_flags),
        )

        return result

    def _build_user_message(
        self,
        *,
        title: str,
        script_body: str,
        keywords: list[str],
        niche: str,
    ) -> str:
        truncated_body = self._truncate_script(script_body)

        return f"""Analyze this YouTube content for SEO.

Input:
Title: {title}
Niche: {niche}
Target keywords: {", ".join(keywords)}
Script excerpt:
{truncated_body}

Return ONLY valid JSON matching this structure:
{json.dumps(SEO_OUTPUT_SCHEMA, ensure_ascii=False, indent=2)}

Additional requirements:
- suggested_title must improve CTR without becoming clickbait.
- suggested_tags must include a mix of broad, niche and long-tail tags.
- improvement_notes must be concrete changes to title, hook, structure, keywords or retention.
- risk_flags must identify SEO or content risks that may hurt discovery.
"""

    def _validate_result(self, *, payload: dict[str, Any], fallback_title: str) -> SEOAnalysisResult:
        enriched_payload = dict(payload)

        if not enriched_payload.get("suggested_title"):
            enriched_payload["suggested_title"] = fallback_title

        if "ctr_potential" not in enriched_payload:
            enriched_payload["ctr_potential"] = enriched_payload.get("title_score", 0.0)

        if "watch_time_signal_score" not in enriched_payload:
            enriched_payload["watch_time_signal_score"] = enriched_payload.get("overall_score", 0.0)

        if "trend_relevance" not in enriched_payload:
            enriched_payload["trend_relevance"] = enriched_payload.get("overall_score", 0.0)

        try:
            return SEOAnalysisResult.model_validate(enriched_payload)
        except ValidationError as exc:
            logger.warning(
                "seo_analyzer.validation_failed",
                errors=exc.errors(include_url=False),
                payload_preview=str(enriched_payload)[:800],
            )
            repaired_payload = self._repair_payload(enriched_payload, fallback_title=fallback_title)
            return SEOAnalysisResult.model_validate(repaired_payload)

    def _repair_payload(self, payload: dict[str, Any], *, fallback_title: str) -> dict[str, Any]:
        return {
            "overall_score": payload.get("overall_score", 0.0),
            "title_score": payload.get("title_score", 0.0),
            "keyword_coverage": payload.get("keyword_coverage", 0.0),
            "search_intent_match": payload.get("search_intent_match", 0.0),
            "ctr_potential": payload.get("ctr_potential", payload.get("title_score", 0.0)),
            "watch_time_signal_score": payload.get(
                "watch_time_signal_score",
                payload.get("overall_score", 0.0),
            ),
            "trend_relevance": payload.get("trend_relevance", payload.get("overall_score", 0.0)),
            "suggested_title": payload.get("suggested_title") or fallback_title,
            "suggested_tags": payload.get("suggested_tags") or [],
            "improvement_notes": payload.get("improvement_notes") or [],
            "detected_primary_intent": payload.get("detected_primary_intent") or "unknown",
            "risk_flags": payload.get("risk_flags") or [],
        }

    def _parse_json_response(self, raw: str) -> dict[str, Any]:
        content = raw.strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            extracted = self._extract_json_object(content)
            if extracted is None:
                logger.error(
                    "seo_analyzer.json_parse_failed",
                    response_preview=content[:800],
                )
                raise ValueError("SEO analyzer returned invalid JSON without a detectable JSON object.")

            try:
                parsed = json.loads(extracted)
            except json.JSONDecodeError as exc:
                logger.error(
                    "seo_analyzer.extracted_json_parse_failed",
                    response_preview=extracted[:800],
                )
                raise ValueError("SEO analyzer returned malformed JSON object.") from exc

        if not isinstance(parsed, dict):
            raise ValueError("SEO analyzer JSON response must be an object.")

        return parsed

    def _extract_json_object(self, content: str) -> str | None:
        fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL)
        if fenced_match:
            return fenced_match.group(1).strip()

        start = content.find("{")
        end = content.rfind("}")

        if start == -1 or end == -1 or end <= start:
            return None

        return content[start : end + 1]

    def _clean_title(self, title: str) -> str:
        clean = re.sub(r"\s+", " ", str(title or "").strip())

        if not clean:
            raise ValueError("title cannot be empty.")

        if len(clean) > MAX_TITLE_CHARS:
            return clean[:MAX_TITLE_CHARS].rstrip()

        return clean

    def _clean_script(self, script_body: str) -> str:
        clean = str(script_body or "").replace("\x00", " ").strip()
        clean = re.sub(r"[ \t]+", " ", clean)
        clean = re.sub(r"\n{3,}", "\n\n", clean)

        if not clean:
            raise ValueError("script_body cannot be empty.")

        return clean

    def _clean_niche(self, niche: str) -> str:
        clean = re.sub(r"\s+", " ", str(niche or "general").strip())

        if not clean:
            return "general"

        return clean[:MAX_NICHE_CHARS].rstrip()

    def _clean_keywords(self, keywords: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for keyword in keywords or []:
            clean = re.sub(r"\s+", " ", str(keyword or "").strip())
            if not clean:
                continue

            dedupe_key = clean.lower()
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            normalized.append(clean)

            if len(normalized) >= MAX_KEYWORDS:
                break

        if not normalized:
            raise ValueError("keywords must contain at least one non-empty keyword.")

        return normalized

    def _truncate_script(self, script_body: str) -> str:
        if len(script_body) <= MAX_SCRIPT_CHARS:
            return script_body

        truncated = script_body[:MAX_SCRIPT_CHARS].rstrip()
        last_sentence_end = max(
            truncated.rfind("."),
            truncated.rfind("!"),
            truncated.rfind("?"),
            truncated.rfind("\n"),
        )

        if last_sentence_end > MAX_SCRIPT_CHARS * 0.65:
            truncated = truncated[: last_sentence_end + 1].rstrip()

        return f"{truncated}\n\n[TRUNCATED_FOR_SEO_ANALYSIS]"

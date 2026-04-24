import json

from worker.agents.base import BaseAgent

SYSTEM_PROMPT = "You are a YouTube SEO specialist. Return valid JSON only."
SCHEMA = '{"overall_score":8.5,"title_score":9.0,"keyword_coverage":7.5,"suggested_title":"...","suggested_tags":["..."],"improvement_notes":["..."]}'


class SEOAnalyzerAgent(BaseAgent):
    async def analyze(self, *, title: str, script_body: str, keywords: list[str], niche: str = "general") -> dict:
        body_excerpt = script_body[:2000] + "..." if len(script_body) > 2000 else script_body
        msg = f"Title: {title}\nNiche: {niche}\nKeywords: {', '.join(keywords)}\nScript: {body_excerpt}\n\nReturn ONLY JSON: {SCHEMA}"
        raw = await self._call(system=SYSTEM_PROMPT, messages=[{"role": "user", "content": msg}], temperature=0.3)
        return json.loads(raw)

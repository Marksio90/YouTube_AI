"""
AI agent layer — all agents, schemas, providers, and errors.

New agents (full BaseAgent interface with tracing + provider abstraction):
  ScoutAgent             — discovers content opportunities in a niche
  OpportunityScorerAgent — multi-dimensional opportunity scoring
  ResearchAgent          — structured research brief for a topic
  ScriptwriterAgent      — full narration-ready script generation
  ComplianceAgent        — YouTube policy and advertiser-friendliness review
  ThumbnailAgent         — thumbnail concepts with DALL-E-ready prompts
  MetadataAgent          — SEO-optimised title, description, tags, chapters
  OptimizationAgent      — data-driven content improvement recommendations

Legacy agents (migrated to new BaseAgent, backward-compatible API):
  TopicResearcherAgent   — discover() + score() for tasks/topics.py
  RecommenderAgent       — generate() for tasks/recommendations.py
  ScriptWriterAgent, SEOAnalyzerAgent, ComplianceCheckerAgent — tasks/ai.py

Provider selection via env:
  LLM_PROVIDER=openai   → OpenAIProvider (default, gpt-4o-mini)
  LLM_PROVIDER=local    → LocalLLMProvider (Ollama / LM Studio)
"""

from worker.agents.base import BaseAgent
from worker.agents.schemas import AgentInput, AgentOutput, AgentTrace, ExecutionStatus
from worker.agents.errors import (
    AgentError,
    AgentExecutionError,
    AgentValidationError,
    AgentTimeoutError,
    ProviderError,
)
from worker.agents.providers import (
    LLMProvider,
    LLMResponse,
    OpenAIProvider,
    LocalLLMProvider,
    get_provider,
)

# ── new agents ────────────────────────────────────────────────────────────────
from worker.agents.scout import ScoutAgent, ScoutInput, ScoutOutput
from worker.agents.opportunity_scorer import (
    OpportunityScorerAgent,
    OpportunityScorerInput,
    OpportunityScorerOutput,
)
from worker.agents.research import ResearchAgent, ResearchInput, ResearchOutput
from worker.agents.scriptwriter import ScriptwriterAgent, ScriptwriterInput, ScriptwriterOutput
from worker.agents.compliance import ComplianceAgent, ComplianceInput, ComplianceOutput
from worker.agents.thumbnail import ThumbnailAgent, ThumbnailInput, ThumbnailOutput
from worker.agents.metadata import MetadataAgent, MetadataInput, MetadataOutput
from worker.agents.optimization import OptimizationAgent, OptimizationInput, OptimizationOutput

# ── legacy agents (backward-compatible) ──────────────────────────────────────
from worker.agents.topic_researcher import TopicResearcherAgent
from worker.agents.recommender import RecommenderAgent
from worker.agents.script_writer import ScriptWriterAgent
from worker.agents.seo_analyzer import SEOAnalyzerAgent
from worker.agents.compliance_checker import ComplianceCheckerAgent

__all__ = [
    # base
    "BaseAgent",
    "AgentInput",
    "AgentOutput",
    "AgentTrace",
    "ExecutionStatus",
    # errors
    "AgentError",
    "AgentExecutionError",
    "AgentValidationError",
    "AgentTimeoutError",
    "ProviderError",
    # providers
    "LLMProvider",
    "LLMResponse",
    "OpenAIProvider",
    "LocalLLMProvider",
    "get_provider",
    # new agents
    "ScoutAgent", "ScoutInput", "ScoutOutput",
    "OpportunityScorerAgent", "OpportunityScorerInput", "OpportunityScorerOutput",
    "ResearchAgent", "ResearchInput", "ResearchOutput",
    "ScriptwriterAgent", "ScriptwriterInput", "ScriptwriterOutput",
    "ComplianceAgent", "ComplianceInput", "ComplianceOutput",
    "ThumbnailAgent", "ThumbnailInput", "ThumbnailOutput",
    "MetadataAgent", "MetadataInput", "MetadataOutput",
    "OptimizationAgent", "OptimizationInput", "OptimizationOutput",
    # legacy
    "TopicResearcherAgent",
    "RecommenderAgent",
    "ScriptWriterAgent",
    "SEOAnalyzerAgent",
    "ComplianceCheckerAgent",
]

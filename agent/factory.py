"""Construct the fixed workflow at the original boilerplate factory boundary."""

from agent.ai import AIService, DeterministicAI, LLMRankingAI
from agent.graph import build
from agent.orchestration import CompanionService
from agent.repositories import Repository
from config.settings import Settings


class GraphFactory:
    @staticmethod
    def create(repository: Repository, settings: Settings, ai: AIService | None = None) -> CompanionService:
        provider = ai or (LLMRankingAI(settings) if settings.ai_provider == "llm" else DeterministicAI())
        service = CompanionService(repository, settings, provider)
        service.graph = build(service)
        return service

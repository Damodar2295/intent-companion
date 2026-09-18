"""Fixed business workflow and a provider-neutral ranking boundary."""

from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from agent.business import matching, value
from agent.business.intent import BusinessIntentEngine
from agent.business.models import BusinessExperience
from agent.domain import Evidence, Recommendation
from agent.repositories import Abstain, NotFound


class State(TypedDict, total=False):
    business_id: str
    intent_id: str
    customer: object
    intent: object
    recommendations: list
    items: dict
    products: list
    exclusions: list
    summary: dict
    totals: dict
    provider: str
    experience: object


class BusinessService:
    def __init__(self, store, settings, ai):
        self.store, self.settings, self.ai = store, settings, ai
        self.engine = BusinessIntentEngine(store, settings)
        graph = StateGraph(State)
        previous = START
        for name in ["guard", "retrieve", "calculate", "rank", "compose"]:
            graph.add_node(name, getattr(self, name))
            graph.add_edge(previous, name)
            previous = name
        graph.add_edge(previous, END)
        self.graph = graph.compile()

    def guard(self, state):
        customer = self.store.business(state["business_id"])
        intent = self.engine.refresh(customer, self.store.intent(state["intent_id"]))
        if intent.confirmation == "dismissed":
            raise Abstain("This business goal was dismissed. Restore it explicitly to see recommendations.")
        return {"customer": customer, "intent": intent}

    def retrieve(self, state):
        recs, items, products, exclusions = matching.match(
            self.store, self.settings, state["customer"], state["intent"]
        )
        return {"recommendations": recs, "items": items, "products": products, "exclusions": exclusions}

    def calculate(self, state):
        summary, totals = value.calculate(state["recommendations"], state["items"], state["intent"])
        return {"summary": summary, "totals": totals}

    async def rank(self, state):
        # Adapt only non-financial IDs/category/evidence to the existing validated ranking contract.
        recs = [
            Recommendation(
                recommendation_id=r.recommendation_id,
                recommendation_type="benefit",
                title=r.title,
                description=r.description,
                category="membership",
                product_ids=r.product_ids,
                relevance_score=r.score,
                evidence=[
                    Evidence(
                        evidence_id=f"e:{i}:{e.source_id}",
                        type="catalog" if e.origin == "catalog" else "rule",
                        source_id=e.source_id,
                        fact=e.fact,
                    )
                    for i, e in enumerate(r.evidence)
                ],
                source_ids=[e.source_id for e in r.evidence],
                conditions=r.conditions,
                explanation=r.category,
            )
            for r in state["recommendations"]
        ]
        ranked = await self.ai.rank_recommendations(recs, state["intent"].categories)
        by_id = {r.recommendation_id: r for r in state["recommendations"]}
        return {
            "recommendations": [by_id[r.recommendation_id] for r in ranked.recommendations],
            "provider": ranked.mode,
        }

    def compose(self, state):
        if self.store.business(state["business_id"]) != state["customer"]:
            raise Abstain("Business preferences or consent changed. Regenerate.")
        refreshed = self.engine.refresh(state["customer"], state["intent"])
        if refreshed.confirmation == "dismissed":
            raise Abstain("Business intent was dismissed during generation.")
        return {
            "experience": BusinessExperience(
                experience_id=f"bexp-{uuid4().hex}",
                business_id=state["business_id"],
                status="ready",
                intent=refreshed,
                recommendations=state["recommendations"],
                products=state["products"],
                spend_summary=state["summary"],
                totals_by_product=state["totals"],
                exclusions=state["exclusions"],
                provider_mode=state["provider"],
                trace=[
                    "Permission and goal ownership checked",
                    "Intent and current priorities understood",
                    "Supplier acceptance and held products verified",
                    "Spend and value calculated separately",
                    "Approved opportunities ranked",
                ],
            )
        }

    async def run(self, business_id, intent_id):
        self.store.business(business_id)
        stored = self.store.intent(intent_id)
        if stored.business_id != business_id:
            raise NotFound("Unknown intent for this business")
        try:
            result = await self.graph.ainvoke({"business_id": business_id, "intent_id": intent_id})
            experience = result["experience"]
        except Abstain as exc:
            experience = BusinessExperience(
                experience_id=f"bexp-{uuid4().hex}",
                business_id=business_id,
                status="abstained",
                abstention_reasons=[str(exc)],
            )
        self.store.put("business_experience", experience.experience_id, experience.model_dump(mode="json"))
        return experience

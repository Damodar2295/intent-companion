from agent.llm.contracts import LLMError, ModelRoute

OPERATIONS = {
    "intent.entity_extraction": "lightweight",
    "recommendation.ranking": "standard",
    "business.goal_extraction": "lightweight",
    "search.requirements_generation": "lightweight",
    "search.plan_generation": "lightweight",
    "recommendation.explanation": "standard",
}


class ModelRouter:
    def __init__(self, routes: dict[str, ModelRoute]):
        if set(routes) - OPERATIONS.keys():
            raise ValueError("Unknown model operation")
        for operation, route in routes.items():
            if route.model_class not in {OPERATIONS[operation], "standard"}:
                raise ValueError(f"Route model class does not match operation: {operation}")
        self.routes = dict(routes)

    def resolve(self, operation: str, model_class: str | None = None) -> ModelRoute:
        if operation not in self.routes:
            raise LLMError("Model operation is not configured")
        route = self.routes[operation]
        if model_class is not None and model_class != route.model_class:
            raise LLMError("Requested model class is not configured for this operation")
        return route

    def describe(self) -> dict[str, dict[str, str]]:
        """Safe route metadata for diagnostics; never exposes keys or endpoints."""
        return {
            operation: {
                "adapter": route.adapter,
                "model_class": route.model_class,
                "model_configured": str(bool(route.model)),
            }
            for operation, route in sorted(self.routes.items())
        }

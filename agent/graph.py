"""Bounded LangGraph execution; no autonomous tools, retries or agent loops."""

from langgraph.graph import END, START, StateGraph

from agent.orchestration import CompanionService, WorkflowState


def build(service: CompanionService):
    graph = StateGraph(WorkflowState)
    stages = [
        ("guard", service.guard),
        ("retrieve", service.retrieve),
        ("calculate", service.calculate),
        ("rank", service.rank),
        ("compose", service.compose),
    ]
    previous = START
    for name, action in stages:
        graph.add_node(name, action)
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    return graph.compile()

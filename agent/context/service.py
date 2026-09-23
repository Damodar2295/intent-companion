"""Deterministic context compression; never invents facts or sends customer identity onward."""

import re

from agent.context.models import ContextRequest, ContextResponse


def estimate(text: str) -> int:
    return max(1, int(len(re.findall(r"\S+", text)) * 1.3))


def trim(text: str, budget: int) -> str:
    words = text.split()
    return " ".join(words[: max(1, int(budget / 1.3))])


class ContextBuilder:
    def build(self, request: ContextRequest) -> ContextResponse:
        budget = request.token_budget
        messages = list(request.messages)
        evidence = list(request.evidence)
        warnings = []
        # Evidence is selected by explicit IDs only; no arbitrary catalog or hidden profile data is added.
        allowed = {evidence_id for message in messages for evidence_id in message.evidence_ids}
        evidence = [message for message in evidence if set(message.evidence_ids) & allowed]
        selected = []
        selected.extend(message for message in messages if message.role == "system")
        selected.extend(message for message in messages[-request.preserve_last_messages :] if message.role != "system")
        selected.extend(evidence)
        unique = []
        keys = set()
        for message in selected:
            key = (message.role, message.content, tuple(message.evidence_ids))
            if key not in keys:
                keys.add(key)
                unique.append(message)
        # Drop lowest-priority non-system messages first, retaining the latest conversation turns.
        dropped = 0
        while sum(estimate(message.content) for message in unique) > budget:
            candidates = [m for m in unique if m.role != "system"]
            if not candidates:
                break
            victim = min(enumerate(unique), key=lambda pair: (pair[1].priority, pair[0]))[0]
            unique.pop(victim)
            dropped += 1
        used = sum(estimate(message.content) for message in unique)
        if used > budget:
            system = next((m for m in unique if m.role == "system"), None)
            if system:
                remaining = max(1, budget - sum(estimate(m.content) for m in unique if m is not system))
                index = unique.index(system)
                unique[index] = system.model_copy(update={"content": trim(system.content, remaining)})
                used = sum(estimate(m.content) for m in unique)
                warnings.append("System context was deterministically truncated to fit the budget.")
        if dropped:
            warnings.append(f"Pruned {dropped} lower-priority context messages.")
        status = "PARTIAL" if warnings else "READY"
        diagnostics = (
            {
                "input_messages": len(request.messages),
                "input_evidence": len(request.evidence),
                "output_messages": len(unique),
                "dropped_messages": dropped,
                "estimated_input_tokens": sum(estimate(m.content) for m in request.messages),
                "estimated_output_tokens": used,
                "compression_ratio": round(used / max(1, sum(estimate(m.content) for m in request.messages)), 4),
            }
            if request.debug
            else None
        )
        return ContextResponse(
            status=status,
            messages=unique,
            estimated_tokens=used,
            token_budget=budget,
            diagnostics=diagnostics,
            warnings=warnings,
        )

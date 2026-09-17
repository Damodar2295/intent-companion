import type { Recommendation, ValueSummary } from "./types";
import { money } from "./format";

export function EvidenceDetails({
  recommendation,
}: {
  recommendation: Recommendation;
}) {
  return (
    <details className="evidence">
      <summary>
        Why you’re seeing this <span>↗</span>
      </summary>
      <div className="evidence-content">
        <p>{recommendation.explanation}</p>
        <ul>
          {recommendation.evidence.map((e) => (
            <li key={e.evidence_id}>
              <span className="evidence-type">{e.type}</span>
              {e.fact}
            </li>
          ))}
        </ul>
        <p className="source-ids">
          Source IDs: {recommendation.source_ids.join(" · ")}
        </p>
      </div>
    </details>
  );
}

export function RecommendationTile({
  recommendation,
  card,
}: {
  recommendation: Recommendation;
  card: string;
}) {
  const value = recommendation.value.find((v) => v.product_id === card);
  return (
    <article className="recommendation-tile">
      <div className="tile-top">
        <span
          className={`category-icon ${recommendation.category}`}
          aria-hidden="true"
        >
          {(
            {
              dining: "⌁",
              hotel: "⌂",
              entertainment: "▥",
              shopping: "◇",
              lounge: "☷",
              travel: "↗",
            } as Record<string, string>
          )[recommendation.category] || "✧"}
        </span>
        <span className="eyebrow">{recommendation.category}</span>
        {value && (
          <span className="value-chip">
            {money(value.amount, value.currency)} potential
          </span>
        )}
      </div>
      <h3>{recommendation.title}</h3>
      <p>{recommendation.description}</p>
      {recommendation.conditions.length > 0 && (
        <details className="conditions">
          <summary>Mock conditions</summary>
          <ul>
            {recommendation.conditions.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </details>
      )}
      <EvidenceDetails recommendation={recommendation} />
    </article>
  );
}

export function ValuePanel({
  value,
  title,
}: {
  value?: ValueSummary;
  title: string;
}) {
  return (
    <section className="value-panel" id="value">
      <div className="eyebrow">Your illustrative trip value</div>
      <div className="value-large">
        {value && Object.keys(value.totals_by_currency).length
          ? Object.entries(value.totals_by_currency).map(
              ([currency, amount]) => (
                <div key={currency}>
                  {money(amount, currency)} <small>{currency}</small>
                </div>
              ),
            )
          : "Not valued"}
      </div>
      <p>
        Potential value with <strong>{title}</strong>
      </p>
      <span className="small-tag">Synthetic · not guaranteed</span>
      <details className="value-details">
        <summary>
          See the calculation <span>↗</span>
        </summary>
        <div>
          <p>
            Separate mock spending groups may combine. Within a group, only the
            highest alternative counts.
          </p>
          {value?.breakdown.map((v) => (
            <div className="value-line" key={v.source_id}>
              <div>
                <strong>{money(v.amount, v.currency)}</strong>
                <span className={v.included_in_total ? "included" : "excluded"}>
                  {v.included_in_total ? "Counted" : "Not added"}
                </span>
              </div>
              <code>{v.source_id}</code>
              <p>{v.calculation_rule}</p>
              <p>{v.exclusion_reason}</p>
              <ul>
                {v.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </details>
      <p className="value-disclaimer">
        {value?.disclaimer || "No verified monetary calculation is available."}
      </p>
    </section>
  );
}

import { useEffect, useState } from "react";
import { api } from "./api";

export function IntentControls({
  owner,
  intent,
  business = false,
  status,
  onChange,
}: {
  owner: string;
  intent: string;
  business?: boolean;
  status?: string;
  onChange: () => Promise<void>;
}) {
  const [current, setCurrent] = useState(status || "unconfirmed");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    if (status) setCurrent(status);
    else if (!business)
      void api<{ status: string }>(
        `/intents/${intent}/feedback?owner_id=${encodeURIComponent(owner)}`,
      )
        .then((r) => {
          if (active) setCurrent(r.status);
        })
        .catch(() => {
          if (active) setError("Unable to load intent feedback.");
        });
    return () => {
      active = false;
    };
  }, [status, intent, owner, business]);
  async function act(action: string) {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ status: string }>(
        `${business ? "/business" : ""}/intents/${intent}/feedback`,
        "POST",
        { owner_id: owner, action },
      );
      setCurrent(result.status);
      await onChange();
    } catch {
      setError("Unable to update intent. Please retry.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="intent-controls">
      <div>
        <span className="eyebrow">YOUR INTENT · {current}</span>
        <h3>Does this reflect your plans?</h3>
        <p>You decide whether this intent should guide your experience.</p>
      </div>
      <div className="control-actions">
        {current === "dismissed" ? (
          <button
            className="button"
            disabled={busy}
            onClick={() => void act("restore")}
          >
            Restore intent
          </button>
        ) : (
          <>
            <button
              className="button secondary"
              disabled={busy || current === "confirmed"}
              onClick={() => void act("confirm")}
            >
              {current === "confirmed" ? "Intent confirmed" : "Confirm intent"}
            </button>
            <button
              className="text-button"
              disabled={busy}
              onClick={() => void act("dismiss")}
            >
              Not relevant
            </button>
          </>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
    </section>
  );
}

type MerchantResult = {
  status: string;
  merchant_name?: string;
  message: string;
  source?: string;
  last_verified?: string;
  accepted_products: { id: string; name: string }[];
  offers: { id: string; title: string; conditions: string[] }[];
};
export function MerchantLookup({
  owner,
  business = false,
}: {
  owner: string;
  business?: boolean;
}) {
  const [code, setCode] = useState(business ? "DEMO-PACKAGING" : "DEMO-DINING");
  const [result, setResult] = useState<MerchantResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function lookup() {
    setBusy(true);
    setResult(null);
    setError("");
    try {
      setResult(
        await api<MerchantResult>("/merchant/resolve", "POST", {
          owner_type: business ? "business" : "consumer",
          owner_id: owner,
          code,
        }),
      );
    } catch {
      setError("Unable to resolve this merchant. Please retry.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="merchant-lookup" id="merchant">
      <summary>
        At the merchant <span>Try a QR lookup simulation</span>
      </summary>
      <p>
        Choose a demonstration code, just as a QR would identify a merchant.
        Acceptance and offers come from the catalog.
      </p>
      <div className="merchant-examples">
        {[
          [business ? "DEMO-PACKAGING" : "DEMO-DINING", "Acceptance + offer"],
          ["DEMO-NO-OFFER", "Acceptance only"],
          ["DEMO-UNKNOWN", "Unable to verify"],
        ].map(([value, title]) => (
          <button
            className="button secondary"
            key={value}
            onClick={() => {
              setCode(value);
              setResult(null);
            }}
          >
            {title}
          </button>
        ))}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void lookup();
        }}
      >
        <label>
          Merchant code
          <input
            required
            value={code}
            onChange={(e) => {
              setCode(e.target.value);
              setResult(null);
            }}
          />
        </label>
        <button disabled={busy} className="button">
          {busy ? "Checking…" : "Simulate QR lookup"}
        </button>
      </form>
      {error && <p role="alert">{error}</p>}
      {result && (
        <div className="merchant-result" role="status">
          <span className="eyebrow">{result.status}</span>
          <h3>{result.merchant_name || "Lookup unavailable"}</h3>
          <p>{result.message}</p>
          {result.status === "verified" && (
            <>
              <h4>Accepted held cards</h4>
              {result.accepted_products.length ? (
                result.accepted_products.map((p) => <p key={p.id}>{p.name}</p>)
              ) : (
                <p>No held card has verified acceptance here.</p>
              )}
              <h4>Offers to explore</h4>
              {result.offers.length ? (
                result.offers.map((o) => (
                  <div key={o.id}>
                    <strong>{o.title}</strong>
                    <ul>
                      {o.conditions.map((c) => (
                        <li key={c}>{c}</li>
                      ))}
                    </ul>
                  </div>
                ))
              ) : (
                <p>
                  No verified applicable offer. Acceptance does not imply a
                  benefit.
                </p>
              )}
              <small>
                {result.source} · Checked {result.last_verified}
              </small>
            </>
          )}
        </div>
      )}
    </details>
  );
}

export function SupplementaryExplore() {
  const [interested, setInterested] = useState(false);
  const [notice, setNotice] = useState(false);
  return (
    <details className="merchant-lookup">
      <summary>Traveling together?</summary>
      <label className="shared-interest">
        <input
          type="checkbox"
          checked={interested}
          onChange={(e) => {
            setInterested(e.target.checked);
            setNotice(false);
          }}
        />{" "}
        I want to explore shared spending
      </label>
      {interested && (
        <div className="merchant-result">
          <h3>Explore a supplementary-card concept</h3>
          <p>
            A local demonstration of an additional-card journey. No eligibility,
            fee, reward or acceptance claims are made.
          </p>
          <button className="button secondary" onClick={() => setNotice(true)}>
            Explore supplementary card
          </button>
          {notice && (
            <p role="status">
              Demo exploration only. No application has been submitted.
            </p>
          )}
        </div>
      )}
    </details>
  );
}

export type Preference =
  | "fine dining"
  | "museums"
  | "luxury hotels"
  | "shopping"
  | "dining"
  | "culture";
export type Scenario = {
  scenario_id: string;
  customer_id: string;
  title: string;
  subtitle: string;
  signal_ids: string[];
};
export type Customer = {
  customer_id: string;
  display_name: string;
  lifecycle_stage: "prospect" | "member";
  existing_cards: string[];
  stated_preferences: Preference[];
  suppressed_preferences: Preference[];
  consent: { allowed: boolean; purpose: string };
};
export type Evidence = {
  evidence_id: string;
  type: string;
  source_id: string;
  fact: string;
  weight: number | null;
};
export type Intent = {
  intent_id: string;
  destination: string;
  start_date: string;
  end_date: string;
  purpose: string;
  intent_stage: string;
  confidence: number;
  evidence: Evidence[];
  expires_at: string;
  signal_ids: string[];
};
export type Value = {
  source_id: string;
  product_id: string;
  value_type: string;
  amount: string;
  currency: string;
  calculation_rule: string;
  assumptions: string[];
  included_in_total: boolean;
  exclusion_reason: string | null;
};
export type ValueSummary = {
  product_id: string;
  totals_by_currency: Record<string, string>;
  breakdown: Value[];
  disclaimer: string;
};
export type Recommendation = {
  recommendation_id: string;
  recommendation_type: string;
  title: string;
  description: string;
  category: string;
  product_ids: string[];
  relevance_score: number;
  evidence: Evidence[];
  value: Value[];
  source_ids: string[];
  conditions: string[];
  explanation: string;
};
export type Experience = {
  experience_id: string;
  customer_id: string;
  lifecycle_stage: "prospect" | "member";
  intent: Intent | null;
  headline: string;
  summary: string;
  recommended_cards: Recommendation[];
  benefits: Recommendation[];
  offers: Recommendation[];
  rewards: Recommendation[];
  merchants: Recommendation[];
  value_summary: ValueSummary[];
  preferences_used: Preference[];
  status: "ready" | "abstained";
  abstention_reasons: string[];
  provider_mode: string;
  fallback_reason: string | null;
  trace: { stage: string; description: string; count: number }[];
};
export type Detection = {
  status: string;
  intent: Intent | null;
  abstention_reasons: string[];
};

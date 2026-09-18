export type Category =
  | "ingredients"
  | "packaging"
  | "equipment"
  | "software"
  | "travel"
  | "employees";
export type Goal = "expansion" | "client_growth" | "replenishment";
export type Business = {
  business_id: string;
  name: string;
  industry: string;
  priorities: Category[];
  consent: { allowed: boolean; purpose: string };
};
export type BusinessScenario = {
  scenario_id: string;
  business_id: string;
  goal_id: string;
  title: string;
  subtitle: string;
  goal_text: string;
  signal_ids: string[];
  default_priorities: Category[];
};
export type Spend = {
  observation_id: string;
  category: Category;
  amount: string;
  currency: string;
  payment_method: "held_card" | "other" | "undecided";
  status: "observed" | "planned";
  period_start: string;
  period_end: string;
  observed_on: string;
};
export type Signal = {
  event_id: string;
  business_id: string;
  goal_id: string;
  goal_type: Goal;
  event_type: string;
  timestamp: string;
  consent: { allowed: boolean; purpose: string };
  category: Category | null;
  spend: Spend | null;
  synthetic: true;
};
export type BIntent = {
  intent_id: string;
  goal_id: string;
  goal_type: Goal;
  confidence: number;
  intent_stage: string;
  confirmation: string;
  evidence: {
    source_id: string;
    origin: string;
    fact: string;
    weight: number;
  }[];
  spend: Spend[];
};
export type BValue = {
  source_id: string;
  product_id: string;
  observation_id: string;
  amount: string;
  value_type: string;
  points: string | null;
  calculation_rule: string;
  period: string;
  assumptions: string[];
  included_in_total: boolean;
  exclusion_reason: string | null;
};
export type BRecommendation = {
  recommendation_id: string;
  title: string;
  description: string;
  category: Category;
  supplier: string;
  product_ids: string[];
  evidence: BIntent["evidence"];
  conditions: string[];
  values: BValue[];
  value_note: string | null;
};
export type BExperience = {
  status: string;
  intent: BIntent | null;
  recommendations: BRecommendation[];
  products: { item_id: string; name: string }[];
  spend_summary: Record<string, string>;
  totals_by_product: Record<string, Record<string, string>>;
  abstention_reasons: string[];
  exclusions: string[];
  trace: string[];
  provider_mode: string;
};
export type Draft = {
  goal_type: Goal | null;
  categories: Category[];
  time_horizon: string | null;
  evidence_excerpts: string[];
  provider_mode: string;
  needs_clarification: boolean;
  explanation: string;
};

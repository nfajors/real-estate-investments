/** API types (mirror apps/api/app/schemas.py and the engine's result shape). */

export type Role = "owner" | "admin" | "analyst" | "viewer";

export interface Membership {
  org_id: string;
  org_name: string;
  org_slug: string;
  role: Role;
  plan: string;
}

export interface Me {
  user: { id: string; email: string; name: string };
  memberships: Membership[];
}

export interface Headline {
  result_id: string;
  scenario_id: string;
  calculated_at: string;
  noi_year1: number;
  cap_rate: number;
  irr_levered: number | null;
  irr_unlevered: number | null;
  npv: number | null;
  equity_multiple: number | null;
  cash_on_cash: number | null;
  dscr: number | null;
  ltv: number | null;
  risk_score: number | null;
  risk_level: "low" | "moderate" | "high" | null;
  price_per_unit: number | null;
  price_per_sf: number | null;
  equity_invested: number | null;
  exit_value: number | null;
}

export interface Property {
  id: string;
  name: string;
  property_type: string;
  address: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  status: string;
  purchase_price: number | null;
  acquisition_date: string | null;
  hold_period_years: number;
  units: number | null;
  rentable_sf: number | null;
  year_built: number | null;
  description: string | null;
  attributes: Record<string, unknown>;
  valuation_inputs: Record<string, unknown>;
  is_demo: boolean;
  owner_id: string | null;
  owner_name?: string | null;
  created_at: string;
  updated_at: string;
  latest: Headline | null;
}

export interface UnitType {
  name: string;
  units: number;
  in_place_rent_monthly: number;
  market_rent_monthly?: number | null;
  sf_per_unit?: number | null;
}

export interface ExpenseLine {
  name: string;
  amount_annual: number;
  growth?: number | null;
}

export interface Loan {
  name?: string;
  loan_type?: string;
  amount?: number | null;
  ltv?: number | null;
  rate_type?: "fixed" | "floating";
  interest_rate?: number;
  index_rate?: number;
  spread?: number;
  amortization_years?: number;
  term_years?: number;
  io_years?: number;
  origination_fee_pct?: number;
  exit_fee_pct?: number;
  min_dscr_covenant?: number | null;
  max_ltv_covenant?: number | null;
}

export interface Assumptions {
  purchase_price: number;
  hold_period_years: number;
  closing_costs_pct: number;
  upfront_capex: number;
  units?: number | null;
  rentable_sf?: number | null;
  revenue_mode: "unit_mix" | "per_sf" | "lump_sum";
  unit_mix: UnitType[];
  rent_psf_annual: number;
  gross_potential_rent: number;
  other_income: number;
  rent_growth: number;
  rent_growth_by_year?: number[] | null;
  other_income_growth: number;
  vacancy_rate: number;
  credit_loss_rate: number;
  opex_mode: "line_items" | "ratio";
  expense_lines: ExpenseLine[];
  opex_ratio: number;
  management_fee_pct: number;
  opex_growth: number;
  capex_reserve_annual: number;
  capex_growth: number;
  exit_cap_rate: number;
  selling_costs_pct: number;
  discount_rate: number;
  loan?: Loan | null;
  preferred_equity?: { amount: number; pref_rate: number; accrual_rate?: number } | null;
  [k: string]: unknown;
}

export interface Scenario {
  id: string;
  property_id: string;
  name: string;
  description: string | null;
  is_base: boolean;
  assumptions: Assumptions;
  created_at: string;
  updated_at: string;
}

export interface YearRow {
  year: number;
  gross_potential_rent: number;
  vacancy_loss: number;
  credit_loss: number;
  other_income: number;
  effective_gross_income: number;
  operating_expenses: number;
  expense_detail: Record<string, number>;
  noi: number;
  capex_reserve: number;
  cash_flow_before_debt: number;
  debt_service: number;
  interest: number;
  principal: number;
  pref_distribution: number;
  btcf: number;
  loan_balance: number;
  dscr: number | null;
  debt_yield: number | null;
  cash_on_cash: number | null;
}

export interface Metrics {
  noi_year1: number;
  egi_year1: number;
  opex_year1: number;
  expense_ratio_year1: number | null;
  going_in_cap_rate: number;
  exit_cap_rate: number;
  irr_unlevered: number | null;
  irr_levered: number | null;
  npv_unlevered: number;
  npv_levered: number;
  equity_multiple_unlevered: number | null;
  equity_multiple_levered: number | null;
  cash_on_cash_year1: number | null;
  avg_cash_on_cash: number | null;
  dscr_year1: number | null;
  min_dscr: number | null;
  debt_yield_year1: number | null;
  ltv: number | null;
  ltc: number | null;
  loan_amount: number;
  equity_invested: number;
  total_project_cost: number;
  price_per_unit: number | null;
  price_per_sf: number | null;
  breakeven_occupancy: number | null;
  profit_levered: number;
  profit_unlevered: number;
}

export interface RiskFactor {
  factor: string;
  points: number;
  message: string;
}

export interface Flag {
  field: string;
  severity?: string;
  message: string;
}

export interface UnderwritingResult {
  engine_version: string;
  metrics: Metrics;
  annual: YearRow[];
  sources_and_uses: {
    purchase_price: number;
    closing_costs: number;
    upfront_capex: number;
    loan_fees: number;
    total_uses: number;
    senior_loan: number;
    preferred_equity: number;
    common_equity: number;
    total_sources: number;
  };
  exit: {
    exit_year: number;
    forward_noi: number;
    exit_cap_rate: number;
    gross_sale_price: number;
    selling_costs: number;
    net_sale_proceeds: number;
    loan_payoff: number;
    loan_exit_fee: number;
    pref_redemption: number;
    net_proceeds_to_equity: number;
  };
  unlevered_cash_flows: number[];
  levered_cash_flows: number[];
  debt_schedule: { year: number; beginning_balance: number; interest: number; principal: number; debt_service: number; ending_balance: number }[];
  warnings: Flag[];
  covenant_breaches: { year: number; covenant: string; threshold: number; actual: number }[];
  audit_trace: { metric: string; formula: string; inputs?: Record<string, unknown>; value: unknown }[];
  calc_ms: number;
  assumptions: Assumptions;
  risk: { score: number; level: string; factors: RiskFactor[] };
}

export interface StoredResult extends UnderwritingResult {
  id: string;
  scenario_id: string;
  calculated_at: string;
  stale: boolean;
}

export interface DocumentRec {
  id: string;
  property_id: string;
  name: string;
  type: string;
  mime_type: string;
  size_bytes: number;
  status: "uploaded" | "processing" | "extracted" | "failed";
  page_count: number | null;
  extractor: string | null;
  error: string | null;
  created_at: string;
}

export interface Page {
  page_number: number;
  label: string | null;
  text: string;
  width: number | null;
  height: number | null;
  image_url: string | null;
  cells: [string, unknown][] | null;
}

export interface Extraction {
  id: string;
  document_id: string;
  property_id: string;
  field_path: string;
  label: string | null;
  value: unknown;
  original_value: unknown;
  unit: string | null;
  confidence: number;
  source_page: number | null;
  source_ref: string | null;
  source_excerpt: string | null;
  source_bbox: { x0: number; top: number; x1: number; bottom: number } | null;
  citation_verified: boolean;
  extractor: string;
  status: "pending" | "accepted" | "edited" | "rejected" | "superseded";
  verified_by: string | null;
  verified_at: string | null;
  version: number;
}

export interface FieldDef {
  label: string;
  kind: "currency" | "percent" | "integer" | "number" | "years" | "text" | "unit_mix";
  group: string;
}

export interface Financing {
  id: string;
  property_id: string;
  name: string;
  type: "permanent" | "bridge" | "construction" | "interest_only";
  rate_type: "fixed" | "floating";
  loan_amount: number | null;
  ltv: number | null;
  interest_rate: number;
  index_rate: number;
  spread: number;
  term_years: number;
  amortization_years: number;
  io_period: number;
  fees: Record<string, number>;
  covenants: Record<string, number>;
  preferred_equity: { amount: number; pref_rate: number; accrual_rate?: number } | null;
  is_active: boolean;
}

export interface ScenarioComparisonRow {
  scenario_id: string;
  name: string;
  is_base: boolean;
  key_assumptions: Record<string, number>;
  metrics: Headline | null;
}

export interface PropertyTypeDef {
  key: string;
  label: string;
  revenue_mode: string;
  fields: { key: string; label: string; type: "number" | "percent" | "text" | "select"; options?: string[] }[];
  defaults: Record<string, number | string>;
}

export interface Feature {
  label: string;
  default: boolean;
  phase: number;
  enabled: boolean;
}

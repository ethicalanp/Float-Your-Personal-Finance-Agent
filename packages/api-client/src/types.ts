/**
 * Core type definitions matching backend FastAPI schemas.
 */

// --- Auth & Consent Types ---
export interface AuthCapabilitiesResponse {
  google: boolean;
  phone: boolean;
  email: boolean;
  google_client_id?: string | null;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
  terms_accepted: boolean;
  privacy_accepted?: boolean;
  ai_data_processing_consent: boolean;
  consent_version?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface GoogleAuthRequest {
  id_token: string;
}

export interface PhoneOtpRequest {
  phone_number: string;
}

export interface PhoneOtpVerifyRequest {
  phone_number: string;
  otp: string;
  full_name?: string;
}

export interface PasswordResetRequest {
  email: string;
}

export interface PasswordResetConfirmRequest {
  token: string;
  new_password: string;
}

export interface SetPasswordRequest {
  password: string;
}

export interface ReauthRequest {
  method: "password" | "google" | "phone";
  password?: string;
  id_token?: string;
  phone_number?: string;
  otp?: string;
}

export interface PhoneLinkRequest {
  phone_number: string;
  otp?: string;
}

export interface EmailVerifyRequest {
  email?: string;
}

export interface EmailVerifyConfirmRequest {
  token: string;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface AuthResponse {
  access_token: string;
  refresh_token?: string;
  token_type: string;
  user_id: string;
  email?: string;
  full_name: string;
  consent_given?: boolean;
}

export interface MessageResponse {
  message: string;
  cooldown_seconds?: number;
}

export interface UserSessionItem {
  id: string;
  created_at: string;
  last_active_at: string;
  user_agent?: string;
  ip_address_mask?: string;
  is_current?: boolean;
}

export interface AuthMethodItem {
  id: string;
  provider: string;
  identifier?: string;
  created_at: string;
}

export interface AuthMethodsResponse {
  has_password: boolean;
  methods: AuthMethodItem[];
}

export interface UserProfileResponse {
  id: string;
  email?: string;
  phone_number?: string;
  full_name: string;
  is_active: boolean;
  terms_accepted: boolean;
  privacy_accepted: boolean;
  ai_data_processing_consent: boolean;
}

export interface ConsentUpdateRequest {
  terms_accepted?: boolean;
  privacy_accepted?: boolean;
  ai_data_processing_consent?: boolean;
  consent_version?: string;
}

export interface ConsentState {
  terms_accepted: boolean;
  privacy_accepted?: boolean;
  ai_data_processing_consent: boolean;
  consent_version?: string;
  updated_at?: string;
}

export interface ConsentResponse {
  status: string;
  user_id: string;
  consent: ConsentState;
}

// --- Plan & Statement Types ---
export interface AccountResponse {
  id: string;
  user_id: string;
  name: string;
  account_type: "savings" | "checking" | "credit_card" | string;
  institution_name: string;
  account_number_mask: string;
  currency: string;
  current_balance: number;
  created_at: string;
}

export interface CreateAccountRequest {
  name: string;
  account_type: string;
  institution_name: string;
  account_number_mask?: string;
  currency?: "INR";
  initial_balance?: number;
}

export interface UploadStatementRequest {
  account_id: string;
  format?: "csv" | "sms";
  content: string;
}

export interface StatementUploadSummary {
  account_id: string;
  total_parsed: number;
  imported_count: number;
  duplicates_skipped: number;
  sample_imported: Array<{
    date: string;
    description: string;
    amount: number;
    transaction_type: string;
    category: string;
  }>;
}

export interface CategorySpending {
  category: string;
  total_amount: number;
  count: number;
}

export interface MonthlyBreakdown {
  month: string;
  inflow: number;
  outflow: number;
  net: number;
}

export interface CashFlowSummary {
  period_start?: string;
  period_end?: string;
  total_inflow: number;
  total_outflow: number;
  net_savings: number;
  savings_rate?: number;
  monthly_breakdown: MonthlyBreakdown[];
  top_categories: CategorySpending[];
}

// --- Protect Types ---
export interface ScamCheckRequest {
  message: string;
  language_hint?: "en" | "ml" | "manglish";
}

export interface ScamAnalysis {
  is_scam: boolean;
  risk_tier: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  risk_score: number;
  reasons: string[];
  recommendations: string[];
  detected_patterns: string[];
  helpline_contact?: string;
}

export interface ScamCheckResponse {
  status: string;
  analysis: ScamAnalysis;
}

export interface RecoveryCaseCreateRequest {
  scam_type: string;
  amount_lost?: number;
  platform?: string;
  incident_summary: string;
  bank_name?: string;
}

export interface RecoveryCaseResponse {
  id: string;
  user_id: string;
  scam_type: string;
  amount_lost?: number;
  platform?: string;
  status: "reported" | "in_progress" | "resolved" | string;
  incident_summary: string;
  created_at: string;
  checklist?: Array<{
    step: number;
    title: string;
    description: string;
    completed: boolean;
    priority: "CRITICAL" | "HIGH" | "MEDIUM";
  }>;
}

export interface RecoveryCaseUpdateRequest {
  status?: "reported" | "in_progress" | "resolved";
  notes?: string;
}

export interface VerifiedContact {
  id: string;
  institution_name: string;
  category: "bank" | "police" | "regulator" | "telecom";
  official_phone: string;
  official_email?: string;
  official_portal?: string;
  helpline_type: string;
  verified_at: string;
}

// --- Borrow Types ---
export interface BorrowAssessResponse {
  assessment_id: string;
  readiness_band: "Tier 1 - Strong" | "Tier 2 - Moderate" | "Tier 3 - Building" | string;
  readiness_score?: number;
  summary: string;
  positive_factors: string[];
  areas_for_improvement: string[];
  recommended_actions: string[];
  legal_disclaimer: string;
  assessed_at: string;
}

// --- Assistant & RAG Types ---
export interface CitationItem {
  chunk_id: string;
  source_title: string;
  source_url?: string;
  publisher?: string;
  publication_date?: string;
}

export interface KnowledgeQuestionRequest {
  question: string;
  language_hint?: "en" | "ml" | "manglish";
}

export interface KnowledgeAnswerResponse {
  status: "answered" | "insufficient_evidence" | "refusal" | "degraded_fallback";
  answer: string;
  citations: CitationItem[];
  confidence: "high" | "medium" | "low";
  disclaimer: string;
  refusal_reason?: string | null;
  degraded?: boolean;
  trace_id?: string;
}

export interface AssistantChatRequest {
  question: string;
  language_hint?: "en" | "ml" | "manglish";
}

export interface AssistantChatResponse {
  status: "success" | "clarification_needed" | "insufficient_evidence" | "refusal" | "degraded_fallback";
  answer: string;
  suggested_next_actions?: string[];
  citations?: CitationItem[];
  disclaimer?: string;
  trace_id?: string;
}

export interface ConversationPurgeRequest {
  confirm: boolean;
  confirmation_phrase: "DELETE_MY_CONVERSATIONS";
}

export interface ConversationPurgeResponse {
  status: "purged";
  deleted_messages_count: number;
  purged_at: string;
}

// --- Budget Plan & Recurring Types ---
export interface BudgetPlanItem {
  id: string;
  month: string;
  version: number;
  monthly_income_paise: number;
  extra_income_paise: number;
  total_income_paise: number;
  income_mode: "fixed" | "irregular_avg" | "irregular_conservative";
  irregular_months: number;
  needs_pct: number;
  wants_pct: number;
  savings_pct: number;
  needs_paise: number;
  wants_paise: number;
  savings_paise: number;
  category_mappings: Record<string, "needs" | "wants" | "savings">;
  updated_at: string;
}

export interface BudgetPlanActuals {
  has_transactions: boolean;
  transaction_count: number;
  actual_needs_paise: number;
  actual_wants_paise: number;
  actual_savings_paise: number;
  recurring_needs_paise: number;
  warnings: string[];
}

export interface BudgetPlanOverviewResponse {
  month: string;
  plan: BudgetPlanItem | null;
  actuals: BudgetPlanActuals;
  irregular_avg_paise: number;
  presets: Record<string, { needs: number; wants: number; savings: number }>;
  default_category_mappings: Record<string, "needs" | "wants" | "savings">;
  educational_disclaimer: string;
}

export interface BudgetPlanUpsertRequest {
  month?: string;
  monthly_income_paise: number;
  extra_income_paise?: number;
  income_mode?: "fixed" | "irregular_avg" | "irregular_conservative";
  irregular_months?: number;
  needs_pct: number;
  wants_pct: number;
  savings_pct: number;
  category_mappings?: Record<string, "needs" | "wants" | "savings">;
  expected_version?: number | null;
}

export interface RecurringCommitmentItem {
  id: string;
  user_id: string;
  name: string;
  category: string;
  amount_type: "fixed" | "variable_band";
  expected_amount: number;
  min_amount: number | null;
  max_amount: number | null;
  frequency: "weekly" | "monthly" | "quarterly" | "yearly";
  due_rule_day: number;
  merchant: string | null;
  merchant_keywords?: string[] | null;
  start_date?: string | null;
  end_date?: string | null;
  version: number;
  is_active: boolean;
  origin: string;
  created_at: string;
}

export interface DeclareCommitmentRequest {
  name: string;
  category: string;
  amount_type?: "fixed" | "variable_band";
  expected_amount: number;
  min_amount?: number | null;
  max_amount?: number | null;
  frequency: "weekly" | "monthly" | "quarterly" | "yearly";
  due_rule_day: number;
  merchant?: string | null;
  merchant_keywords?: string[] | null;
  start_date?: string | null;
  end_date?: string | null;
  origin?: "declared" | "suggested_confirmed";
}

export interface UpdateCommitmentRequest {
  name?: string;
  category?: string;
  amount_type?: "fixed" | "variable_band";
  expected_amount?: number;
  min_amount?: number | null;
  max_amount?: number | null;
  frequency?: "weekly" | "monthly" | "quarterly" | "yearly";
  due_rule_day?: number;
  merchant?: string | null;
  merchant_keywords?: string[] | null;
  start_date?: string | null;
  end_date?: string | null;
  is_active?: boolean;
  expected_version?: number;
}

export interface BillReminderItem {
  occurrence_id: string;
  commitment_id: string;
  name: string;
  category: string;
  due_date: string;
  expected_amount: number;
  status: string;
  days_delta: number;
  mismatch_flag?: string | null;
  mismatch_reason?: string | null;
}

export interface BillRemindersResponse {
  due_soon: BillReminderItem[];
  overdue: BillReminderItem[];
}

export interface RecurringSuggestionItem {
  merchant: string;
  suggested_name: string;
  category: string;
  expected_amount: number;
  frequency: "monthly";
  due_rule_day: number;
  confidence: "high" | "medium";
  detected_occurrences_count: number;
}

export interface SipCalculatorRequest {
  monthly_sip_paise: number;
  lumpsum_paise?: number;
  years: number;
  expected_return_pct?: number;
  adjust_for_inflation?: boolean;
  inflation_pct?: number;
}

export interface SipScenarioOut {
  label: string;
  annual_return_pct: string;
  nominal_corpus_paise: number;
  real_corpus_paise: number;
  total_invested_paise: number;
  nominal_gain_paise: number;
}

export interface SipProjectionResponse {
  monthly_sip_paise: number;
  lumpsum_paise: number;
  years: number;
  expected_return_pct: string;
  adjust_for_inflation: boolean;
  inflation_pct: string;
  total_invested_paise: number;
  projected_nominal_paise: number;
  projected_real_paise: number;
  illustrative_scenarios: SipScenarioOut[];
  assumptions: string[];
  disclaimer: string;
}

export interface InsuranceGapRequest {
  annual_income_paise: number;
  dependants: number;
  existing_life_cover_paise: number;
  existing_health_cover_paise: number;
  liabilities_paise?: number;
}

export interface InsuranceGapResponse {
  annual_income_paise: number;
  dependants: number;
  existing_life_cover_paise: number;
  recommended_life_cover_paise: number;
  life_cover_gap_paise: number;
  life_status: "covered" | "gap" | "no_dependants_note";
  existing_health_cover_paise: number;
  recommended_health_cover_paise: number;
  health_cover_gap_paise: number;
  health_status: "covered" | "gap";
  assumptions: string[];
  disclaimer: string;
}

export interface TaxCompareRequest {
  gross_income_paise: number;
  is_salaried?: boolean;
  deduction_80c_paise?: number;
  deduction_80d_paise?: number;
  other_deductions_paise?: number;
}

export interface RegimeBreakdownOut {
  regime: string;
  gross_income_paise: number;
  total_deductions_paise: number;
  taxable_income_paise: number;
  slab_tax_paise: number;
  rebate_87a_paise: number;
  cess_paise: number;
  total_tax_paise: number;
}

export interface TaxComparisonResponse {
  version: string;
  financial_year: string;
  as_of: string;
  source_url: string;
  verified: boolean;
  needs_verified_parameters: boolean;
  old_regime: RegimeBreakdownOut;
  new_regime: RegimeBreakdownOut;
  lower_tax_regime: "old" | "new" | "equal";
  estimated_difference_paise: number;
  educational_notice: string;
}

// --- Float Health Score Types ---
export interface HealthScoreComponent {
  key: string;
  label: string;
  status: "available" | "insufficient_data";
  score?: number | null;
  weight: number;
  value_display: string;
  why: string;
  educational_tip: string;
}

export interface FloatPathStep {
  priority: number;
  pillar: "Protect" | "Plan" | "Borrow-ready";
  title: string;
  why: string;
  href: string;
}

export interface HealthScoreHistoryPoint {
  recorded_at: string;
  score?: number | null;
  band: string;
  formula_version: string;
}

export interface HealthScoreResponse {
  formula_version: string;
  month: string;
  overall_score?: number | null;
  band: "strong" | "steady" | "building" | "needs_attention" | "insufficient_data";
  confidence: "high" | "medium" | "low";
  available_components: number;
  total_components: number;
  has_essential_insurance?: boolean | null;
  components: HealthScoreComponent[];
  best_next_action?: FloatPathStep | null;
  float_path: FloatPathStep[];
  history: HealthScoreHistoryPoint[];
  delta_from_previous?: number | null;
  version_changed: boolean;
  disclaimer: string;
}

export interface HealthInsuranceFlagRequest {
  has_essential_insurance: boolean | null;
}

// --- Goals & Emergency Fund Types ---
export interface GoalItemOut {
  id: string;
  name: string;
  target_amount_paise: number;
  saved_paise: number;
  over_saved_paise: number;
  remaining_paise: number;
  target_date: string;
  priority: number;
  version: number;
  months_remaining: number;
  is_past_due: boolean;
  is_funded: boolean;
  suggested_monthly_paise: number;
  allocated_monthly_paise: number;
  feasible: boolean;
  progress_pct: number;
}

export interface GoalsOverviewResponse {
  ist_month: string;
  budget_savings_paise?: number | null;
  total_suggested_monthly_paise: number;
  has_allocation_conflict: boolean;
  shortfall_paise: number;
  goals: GoalItemOut[];
}

export interface CreateGoalRequest {
  name: string;
  target_amount_paise: number;
  saved_paise?: number;
  target_date: string;
  priority?: number;
}

export interface UpdateGoalRequest {
  name?: string;
  target_amount_paise?: number;
  saved_paise?: number;
  target_date?: string;
  priority?: number;
  expected_version?: number;
}

export interface EmergencyFundResponse {
  ist_month: string;
  target_months: number;
  needs_paise: number;
  essential_recurring_paise: number;
  essential_monthly_paise: number;
  target_amount_paise: number;
  saved_paise: number;
  liquid_accounts_paise: number;
  effective_saved_paise: number;
  over_saved_paise: number;
  remaining_paise: number;
  progress_pct: number;
  version: number;
}

export interface UpdateEmergencyFundRequest {
  target_months: number;
  saved_paise: number;
  expected_version?: number;
}

// --- Subscriptions & Net Worth Types ---
export interface SubscriptionLeakItem {
  leak_key: string;
  merchant: string;
  rules_triggered: string[];
  monthly_amount_paise: number;
  annual_cost_paise: number;
  decision: "undecided" | "keep" | "cancel";
  explanation: string;
}

export interface SubscriptionLeaksResponse {
  total_leaks: number;
  estimated_yearly_savings_paise: number;
  potential_yearly_savings_paise: number;
  leaks: SubscriptionLeakItem[];
}

export interface NetWorthItem {
  id: string;
  name: string;
  item_type: "asset" | "liability";
  category: string;
  amount_paise: number;
  version: number;
  valued_at: string;
  is_stale: boolean;
  days_since_update: number;
}

export interface NetWorthSnapshot {
  id: string;
  snapshot_date: string;
  total_assets_paise: number;
  total_liabilities_paise: number;
  net_worth_paise: number;
}

export interface NetWorthOverviewResponse {
  total_assets_paise: number;
  total_liabilities_paise: number;
  net_worth_paise: number;
  is_negative: boolean;
  stale_count: number;
  items: NetWorthItem[];
  snapshots: NetWorthSnapshot[];
}

export interface CreateNetWorthItemRequest {
  name: string;
  item_type: "asset" | "liability";
  category?: string;
  amount_paise: number;
  valued_at?: string;
}

export interface UpdateNetWorthItemRequest {
  name?: string;
  category?: string;
  amount_paise?: number;
  valued_at?: string;
  expected_version?: number;
}

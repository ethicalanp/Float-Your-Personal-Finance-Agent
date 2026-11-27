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

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

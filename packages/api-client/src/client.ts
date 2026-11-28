import { ApiError } from "./errors.ts";
import type {
  AccountResponse,
  AssistantChatRequest,
  AssistantChatResponse,
  AuthCapabilitiesResponse,
  AuthResponse,
  BillRemindersResponse,
  BorrowAssessResponse,
  BudgetPlanItem,
  BudgetPlanOverviewResponse,
  BudgetPlanUpsertRequest,
  CashFlowSummary,
  ConsentResponse,
  ConsentUpdateRequest,
  ConversationPurgeResponse,
  CreateAccountRequest,
  CreateGoalRequest,
  CreateNetWorthItemRequest,
  DeclareCommitmentRequest,
  EmergencyFundResponse,
  GoalsOverviewResponse,
  HealthInsuranceFlagRequest,
  HealthScoreResponse,
  InsuranceGapRequest,
  InsuranceGapResponse,
  KnowledgeAnswerResponse,
  KnowledgeQuestionRequest,
  LoginRequest,
  NetWorthOverviewResponse,
  RecoveryCaseCreateRequest,
  RecoveryCaseResponse,
  RecoveryCaseUpdateRequest,
  RecurringCommitmentItem,
  RecurringSuggestionItem,
  RegisterRequest,
  ScamCheckRequest,
  ScamCheckResponse,
  SipCalculatorRequest,
  SipProjectionResponse,
  StatementUploadSummary,
  SubscriptionLeaksResponse,
  TaxCompareRequest,
  TaxComparisonResponse,
  UpdateCommitmentRequest,
  UpdateEmergencyFundRequest,
  UpdateGoalRequest,
  UpdateNetWorthItemRequest,
  UploadStatementRequest,
  UserProfileResponse,
  VerifiedContact,
} from "./types.ts";

export interface ClientConfig {
  baseUrl?: string;
  token?: string;
  fetch?: typeof fetch;
}

export class FloatApiClient {
  private baseUrl: string;
  private token?: string;
  private fetchFn: typeof fetch;

  constructor(config: ClientConfig = {}) {
    const rawBase =
      config.baseUrl ||
      (typeof process !== "undefined"
        ? process.env.NEXT_PUBLIC_API_URL || process.env.PFA_API_URL || process.env.API_BASE_URL
        : undefined) ||
      "http://127.0.0.1:8000";
    this.baseUrl = rawBase.replace(/\/+$/, "");
    this.token = config.token;
    this.fetchFn = config.fetch || (typeof fetch !== "undefined" ? fetch.bind(globalThis) : (null as unknown as typeof fetch));
  }

  setToken(token: string | undefined): void {
    this.token = token;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${path.startsWith("/") ? "" : "/"}${path}`;
    const headers = new Headers(options.headers || {});

    if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }

    if (this.token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${this.token}`);
    }

    const response = await this.fetchFn(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let payload: unknown;
      try {
        payload = await response.json();
      } catch {
        payload = await response.text();
      }
      throw new ApiError(response.status, payload as any);
    }

    if (response.status === 204) {
      return undefined as unknown as T;
    }

    return response.json() as Promise<T>;
  }

  // --- Auth & Consent ---
  readonly auth = {
    getCapabilities: (): Promise<AuthCapabilitiesResponse> =>
      this.request<AuthCapabilitiesResponse>("/api/v1/auth/capabilities", {
        method: "GET",
      }),

    register: (data: RegisterRequest): Promise<AuthResponse> =>
      this.request<AuthResponse>("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    login: (data: LoginRequest): Promise<AuthResponse> =>
      this.request<AuthResponse>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    google: (data: { id_token: string }): Promise<AuthResponse> =>
      this.request<AuthResponse>("/api/v1/auth/google", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    requestPhoneOtp: (data: { phone_number: string }): Promise<{ message: string; cooldown_seconds?: number }> =>
      this.request("/api/v1/auth/phone/request-otp", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    verifyPhoneOtp: (data: { phone_number: string; otp: string; full_name?: string }): Promise<AuthResponse> =>
      this.request<AuthResponse>("/api/v1/auth/phone/verify-otp", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    refresh: (data: { refresh_token: string }): Promise<AuthResponse> =>
      this.request<AuthResponse>("/api/v1/auth/refresh", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    logout: (data?: { refresh_token?: string }): Promise<{ message: string }> =>
      this.request("/api/v1/auth/logout", {
        method: "POST",
        body: JSON.stringify(data || {}),
      }),

    logoutAll: (): Promise<{ message: string }> =>
      this.request("/api/v1/auth/logout-all", {
        method: "POST",
      }),

    getSessions: (): Promise<any[]> =>
      this.request("/api/v1/auth/sessions", {
        method: "GET",
      }),

    revokeSession: (sessionId: string): Promise<{ message: string }> =>
      this.request(`/api/v1/auth/sessions/${sessionId}`, {
        method: "DELETE",
      }),

    getMethods: (): Promise<{ has_password: boolean; methods: any[] }> =>
      this.request("/api/v1/auth/methods", {
        method: "GET",
      }),

    linkGoogle: (data: { id_token: string }): Promise<{ message: string }> =>
      this.request("/api/v1/auth/link/google", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    linkPhone: (data: { phone_number: string; otp?: string }): Promise<{ message: string }> =>
      this.request("/api/v1/auth/link/phone", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    verifyLinkPhoneOtp: (data: { phone_number: string; otp: string }): Promise<{ message: string }> =>
      this.request("/api/v1/auth/link/phone/verify-otp", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    setPassword: (data: { password: string }): Promise<{ message: string }> =>
      this.request("/api/v1/auth/password", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    reauth: (data: { method: "password" | "google" | "phone"; password?: string; id_token?: string; phone_number?: string; otp?: string }): Promise<AuthResponse> =>
      this.request<AuthResponse>("/api/v1/auth/reauth", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    unlinkMethod: (provider: string): Promise<{ message: string }> =>
      this.request(`/api/v1/auth/link/${provider}`, {
        method: "DELETE",
      }),

    requestPasswordReset: (data: { email: string }): Promise<{ message: string }> =>
      this.request("/api/v1/auth/password-reset/request", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    confirmPasswordReset: (data: { token: string; new_password: string }): Promise<{ message: string }> =>
      this.request("/api/v1/auth/password-reset/confirm", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    requestEmailVerification: (data?: { email?: string }): Promise<{ message: string }> =>
      this.request("/api/v1/auth/verify-email/request", {
        method: "POST",
        body: JSON.stringify(data || {}),
      }),

    confirmEmailVerification: (data: { token: string }): Promise<{ message: string }> =>
      this.request("/api/v1/auth/verify-email/confirm", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    getProfile: (): Promise<UserProfileResponse> =>
      this.request<UserProfileResponse>("/api/v1/auth/me", {
        method: "GET",
      }),

    getConsent: (): Promise<ConsentResponse> =>
      this.request<ConsentResponse>("/api/v1/auth/consent", {
        method: "GET",
      }),

    updateConsent: (data: ConsentUpdateRequest): Promise<ConsentResponse> =>
      this.request<ConsentResponse>("/api/v1/auth/consent", {
        method: "POST",
        body: JSON.stringify(data),
      }),
  };

  // --- Plan ---
  readonly plan = {
    getAccounts: (): Promise<AccountResponse[]> =>
      this.request<AccountResponse[]>("/api/v1/plan/accounts", {
        method: "GET",
      }),

    createAccount: (data: CreateAccountRequest): Promise<AccountResponse> =>
      this.request<AccountResponse>("/api/v1/plan/accounts", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    uploadStatement: (data: UploadStatementRequest): Promise<StatementUploadSummary> =>
      this.request<StatementUploadSummary>("/api/v1/plan/upload-statement", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    getCashFlow: (): Promise<CashFlowSummary> =>
      this.request<CashFlowSummary>("/api/v1/plan/cash-flow", {
        method: "GET",
      }),

    getBudget: (month?: string): Promise<BudgetPlanOverviewResponse> =>
      this.request<BudgetPlanOverviewResponse>(
        `/api/v1/plan/budget${month ? `?month=${encodeURIComponent(month)}` : ""}`,
        { method: "GET" }
      ),

    getBudgetHistory: (month?: string): Promise<BudgetPlanItem[]> =>
      this.request<BudgetPlanItem[]>(
        `/api/v1/plan/budget/history${month ? `?month=${encodeURIComponent(month)}` : ""}`,
        { method: "GET" }
      ),

    upsertBudget: (data: BudgetPlanUpsertRequest): Promise<BudgetPlanItem> =>
      this.request<BudgetPlanItem>("/api/v1/plan/budget", {
        method: "PUT",
        body: JSON.stringify(data),
      }),

    calculateSip: (data: SipCalculatorRequest): Promise<SipProjectionResponse> =>
      this.request<SipProjectionResponse>("/api/v1/plan/calculators/sip", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    calculateInsuranceGap: (data: InsuranceGapRequest): Promise<InsuranceGapResponse> =>
      this.request<InsuranceGapResponse>("/api/v1/plan/calculators/insurance-gap", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    compareTaxRegimes: (data: TaxCompareRequest): Promise<TaxComparisonResponse> =>
      this.request<TaxComparisonResponse>("/api/v1/plan/calculators/tax-compare", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    getHealthScore: (month?: string): Promise<HealthScoreResponse> =>
      this.request<HealthScoreResponse>(
        `/api/v1/plan/health-score${month ? `?month=${encodeURIComponent(month)}` : ""}`,
        { method: "GET" }
      ),

    updateHealthInsuranceFlag: (data: HealthInsuranceFlagRequest): Promise<HealthScoreResponse> =>
      this.request<HealthScoreResponse>("/api/v1/plan/health-score/insurance", {
        method: "PUT",
        body: JSON.stringify(data),
      }),

    getGoals: (month?: string): Promise<GoalsOverviewResponse> =>
      this.request<GoalsOverviewResponse>(
        `/api/v1/plan/goals${month ? `?month=${encodeURIComponent(month)}` : ""}`,
        { method: "GET" }
      ),

    createGoal: (data: CreateGoalRequest): Promise<GoalsOverviewResponse> =>
      this.request<GoalsOverviewResponse>("/api/v1/plan/goals", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    updateGoal: (goalId: string, data: UpdateGoalRequest): Promise<GoalsOverviewResponse> =>
      this.request<GoalsOverviewResponse>(`/api/v1/plan/goals/${goalId}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),

    deleteGoal: (goalId: string): Promise<GoalsOverviewResponse> =>
      this.request<GoalsOverviewResponse>(`/api/v1/plan/goals/${goalId}`, {
        method: "DELETE",
      }),

    getEmergencyFund: (month?: string): Promise<EmergencyFundResponse> =>
      this.request<EmergencyFundResponse>(
        `/api/v1/plan/emergency-fund${month ? `?month=${encodeURIComponent(month)}` : ""}`,
        { method: "GET" }
      ),

    updateEmergencyFund: (data: UpdateEmergencyFundRequest): Promise<EmergencyFundResponse> =>
      this.request<EmergencyFundResponse>("/api/v1/plan/emergency-fund", {
        method: "PUT",
        body: JSON.stringify(data),
      }),

    getSubscriptionLeaks: (): Promise<SubscriptionLeaksResponse> =>
      this.request<SubscriptionLeaksResponse>("/api/v1/plan/subscriptions/leaks", {
        method: "GET",
      }),

    setSubscriptionLeakDecision: (
      leakKey: string,
      decision: "keep" | "cancel"
    ): Promise<SubscriptionLeaksResponse> =>
      this.request<SubscriptionLeaksResponse>(
        `/api/v1/plan/subscriptions/leaks/${encodeURIComponent(leakKey)}`,
        {
          method: "PUT",
          body: JSON.stringify({ decision }),
        }
      ),

    getNetWorth: (): Promise<NetWorthOverviewResponse> =>
      this.request<NetWorthOverviewResponse>("/api/v1/plan/net-worth", {
        method: "GET",
      }),

    createNetWorthItem: (data: CreateNetWorthItemRequest): Promise<NetWorthOverviewResponse> =>
      this.request<NetWorthOverviewResponse>("/api/v1/plan/net-worth/items", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    updateNetWorthItem: (
      itemId: string,
      data: UpdateNetWorthItemRequest
    ): Promise<NetWorthOverviewResponse> =>
      this.request<NetWorthOverviewResponse>(`/api/v1/plan/net-worth/items/${itemId}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),

    deleteNetWorthItem: (itemId: string): Promise<NetWorthOverviewResponse> =>
      this.request<NetWorthOverviewResponse>(`/api/v1/plan/net-worth/items/${itemId}`, {
        method: "DELETE",
      }),

    createNetWorthSnapshot: (snapshotDate?: string): Promise<NetWorthOverviewResponse> =>
      this.request<NetWorthOverviewResponse>("/api/v1/plan/net-worth/snapshots", {
        method: "POST",
        body: JSON.stringify(snapshotDate ? { snapshot_date: snapshotDate } : {}),
      }),
  };

  // --- Recurring ---
  readonly recurring = {
    listCommitments: (includePaused = true): Promise<RecurringCommitmentItem[]> =>
      this.request<RecurringCommitmentItem[]>(
        `/api/v1/recurring/commitments?include_paused=${includePaused}`,
        { method: "GET" }
      ),

    createCommitment: (data: DeclareCommitmentRequest): Promise<RecurringCommitmentItem> =>
      this.request<RecurringCommitmentItem>("/api/v1/recurring/commitments", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    updateCommitment: (id: string, data: UpdateCommitmentRequest): Promise<RecurringCommitmentItem> =>
      this.request<RecurringCommitmentItem>(`/api/v1/recurring/commitments/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),

    deleteCommitment: (id: string): Promise<void> =>
      this.request<void>(`/api/v1/recurring/commitments/${id}`, {
        method: "DELETE",
      }),

    getReminders: (): Promise<BillRemindersResponse> =>
      this.request<BillRemindersResponse>("/api/v1/recurring/reminders", {
        method: "GET",
      }),

    getSuggestions: (): Promise<RecurringSuggestionItem[]> =>
      this.request<RecurringSuggestionItem[]>("/api/v1/recurring/suggestions", {
        method: "GET",
      }),

    runMatch: (): Promise<{ matched_count: number }> =>
      this.request<{ matched_count: number }>("/api/v1/recurring/match", {
        method: "POST",
      }),
  };

  // --- Protect ---
  readonly protect = {
    checkScam: (message: string, languageHint?: "en" | "ml" | "manglish"): Promise<ScamCheckResponse> => {
      const payload: ScamCheckRequest = { message, language_hint: languageHint };
      return this.request<ScamCheckResponse>("/api/v1/protect/check", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },

    getRecoveryCases: (): Promise<RecoveryCaseResponse[]> =>
      this.request<RecoveryCaseResponse[]>("/api/v1/protect/recovery-cases", {
        method: "GET",
      }),

    createRecoveryCase: (data: RecoveryCaseCreateRequest): Promise<RecoveryCaseResponse> =>
      this.request<RecoveryCaseResponse>("/api/v1/protect/recovery-cases", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    updateRecoveryCase: (id: string, data: RecoveryCaseUpdateRequest): Promise<RecoveryCaseResponse> =>
      this.request<RecoveryCaseResponse>(`/api/v1/protect/recovery-cases/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),

    getVerifiedContacts: (): Promise<VerifiedContact[]> =>
      this.request<VerifiedContact[]>("/api/v1/protect/verified-contacts", {
        method: "GET",
      }),

    searchVerifiedContacts: (query: string): Promise<VerifiedContact[]> =>
      this.request<VerifiedContact[]>(`/api/v1/protect/verified-contacts/search?q=${encodeURIComponent(query)}`, {
        method: "GET",
      }),
  };

  // --- Borrow ---
  readonly borrow = {
    assess: (): Promise<BorrowAssessResponse> =>
      this.request<BorrowAssessResponse>("/api/v1/borrow/assess", {
        method: "POST",
      }),
  };

  // --- Assistant ---
  readonly assistant = {
    askKnowledge: (data: KnowledgeQuestionRequest): Promise<KnowledgeAnswerResponse> =>
      this.request<KnowledgeAnswerResponse>("/api/v1/assistant/knowledge", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    chat: (data: AssistantChatRequest): Promise<AssistantChatResponse> =>
      this.request<AssistantChatResponse>("/api/v1/assistant/chat", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    purgeConversations: (): Promise<ConversationPurgeResponse> =>
      this.request<ConversationPurgeResponse>("/api/v1/assistant/conversations", {
        method: "DELETE",
        body: JSON.stringify({
          confirm: true,
          confirmation_phrase: "DELETE_MY_CONVERSATIONS",
        }),
      }),
  };
}

/**
 * Feature flag registry.
 * Planned features appear only when their backend endpoints exist.
 * Do not build active UI against endpoints that don't exist yet.
 */
export const FEATURES = {
  // Active backend capabilities (v1)
  PLAN_STATEMENT_UPLOAD: true,
  PLAN_CASH_FLOW: true,
  PROTECT_SCAM_CHECK: true,
  PROTECT_RECOVERY_CASES: true,
  PROTECT_FIRST_HOUR_CHECKLIST: true,
  PROTECT_VERIFIED_CONTACTS: true,
  BORROW_READINESS_ASSESS: true,
  ASSISTANT_KNOWLEDGE_RAG: true,
  ASSISTANT_MULTI_TURN_CHAT: true,
  DPDP_CONVERSATION_PURGE: true,

  // Planned features (strictly hidden until backend endpoints exist)
  HEALTH_SCORE_CALCULATOR: false,
  BUDGETING_LIMITS: false,
  FINANCIAL_GOAL_TRACKER: false,
  CREDIT_BUREAU_PULL: false,
  DIRECT_ACCOUNT_AGGREGATOR: false,
} as const;

export type FeatureKey = keyof typeof FEATURES;

export function isFeatureEnabled(key: FeatureKey): boolean {
  return Boolean(FEATURES[key]);
}

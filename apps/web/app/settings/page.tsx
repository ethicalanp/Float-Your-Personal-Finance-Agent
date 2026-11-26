"use client";

import { useState, useEffect } from "react";
import {
  ShieldCheck,
  Globe,
  AlertTriangle,
  CheckCircle2,
  Sliders,
  KeyRound,
  Mail,
  Phone,
  Sun,
  Moon,
  Monitor,
  Trash2,
  Plus,
  Laptop,
  LogOut,
  AlertCircle,
} from "lucide-react";
import AppShell from "@/components/AppShell";
import { GoogleSignInButton } from "@/components/GoogleSignInButton";
import { getApiClient } from "@/lib/api";
import { FEATURES } from "@/lib/features";
import { useTheme } from "@/components/ThemeToggle";

interface AuthMethod {
  id: string;
  provider: string;
  identifier: string;
  created_at: string;
}

interface UserSessionItem {
  id: string;
  created_at: string;
  last_active_at: string;
  user_agent: string;
  ip_address_mask: string;
}

export default function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const [consentGranted, setConsentGranted] = useState(false);
  const [loadingConsent, setLoadingConsent] = useState(true);
  const [updatingConsent, setUpdatingConsent] = useState(false);
  const [purging, setPurging] = useState(false);
  const [purgeSuccess, setPurgeSuccess] = useState<string | null>(null);
  const [purgeError, setPurgeError] = useState<string | null>(null);
  const [confirmPhrase, setConfirmPhrase] = useState("");
  const [showPurgeModal, setShowPurgeModal] = useState(false);
  const [language, setLanguage] = useState("en");

  const [capabilities, setCapabilities] = useState<{
    google: boolean;
    phone: boolean;
    email: boolean;
    google_client_id?: string | null;
  }>({
    google: false,
    phone: false,
    email: true,
  });

  // Auth methods state
  const [methods, setMethods] = useState<AuthMethod[]>([]);
  const [hasPassword, setHasPassword] = useState(false);
  const [loadingMethods, setLoadingMethods] = useState(true);
  const [methodError, setMethodError] = useState<string | null>(null);
  const [methodSuccess, setMethodSuccess] = useState<string | null>(null);

  // Link Phone modal state
  const [showLinkPhoneModal, setShowLinkPhoneModal] = useState(false);
  const [linkPhone, setLinkPhone] = useState("+91 ");
  const [linkOtp, setLinkOtp] = useState("");
  const [linkOtpSent, setLinkOtpSent] = useState(false);
  const [linkLoading, setLinkLoading] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);

  // Set Password modal state
  const [showSetPasswordModal, setShowSetPasswordModal] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [settingPassword, setSettingPassword] = useState(false);

  // Active sessions state
  const [sessions, setSessions] = useState<UserSessionItem[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const [sessionSuccess, setSessionSuccess] = useState<string | null>(null);

  const api = getApiClient();

  async function loadCapabilities() {
    try {
      const res = await fetch("/api/auth/capabilities");
      if (res.ok) {
        const data = await res.json();
        setCapabilities({
          google: Boolean(data.google),
          phone: Boolean(data.phone),
          email: Boolean(data.email ?? true),
          google_client_id: data.google_client_id || null,
        });
      }
    } catch {
      // fallback
    }
  }

  async function loadMethods() {
    try {
      setLoadingMethods(true);
      const res = await fetch("/api/auth/methods");
      if (res.ok) {
        const data = await res.json();
        setHasPassword(Boolean(data.has_password));
        setMethods(data.methods || []);
      }
    } catch {
      // ignore
    } finally {
      setLoadingMethods(false);
    }
  }

  async function loadSessions() {
    try {
      setLoadingSessions(true);
      const res = await fetch("/api/auth/sessions");
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch {
      // ignore
    } finally {
      setLoadingSessions(false);
    }
  }

  useEffect(() => {
    async function loadSettings() {
      try {
        const res = await fetch("/api/auth/me");
        if (res.ok) {
          const data = await res.json();
          setConsentGranted(Boolean(data.consent?.ai_data_processing_consent));
        }
      } catch {
        // fallback
      } finally {
        setLoadingConsent(false);
      }
    }

    loadSettings();
    loadCapabilities();
    loadMethods();
    loadSessions();
  }, []);

  async function handleToggleConsent() {
    setUpdatingConsent(true);
    const nextState = !consentGranted;
    try {
      const res = await fetch("/api/auth/consent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          terms_accepted: true,
          privacy_accepted: true,
          ai_data_processing_consent: nextState,
          consent_version: "2026.1",
        }),
      });
      if (res.ok) {
        setConsentGranted(nextState);
      }
    } catch {
      // ignore
    } finally {
      setUpdatingConsent(false);
    }
  }

  async function handlePurgeConversations() {
    if (confirmPhrase !== "DELETE_MY_CONVERSATIONS") return;
    setPurging(true);
    setPurgeError(null);
    try {
      await api.assistant.purgeConversations();
      setPurgeSuccess("All assistant conversations and memory chunks have been permanently deleted.");
      setShowPurgeModal(false);
      setConfirmPhrase("");
    } catch (err: any) {
      setPurgeError(err.message || "Failed to purge conversations. Please try again.");
    } finally {
      setPurging(false);
    }
  }

  // Auth methods actions
  const totalMethodsCount = methods.length + (hasPassword ? 1 : 0);
  const isSoleMethod = totalMethodsCount <= 1;

  async function handleUnlinkMethod(provider: string) {
    if (isSoleMethod) return;
    setMethodError(null);
    setMethodSuccess(null);
    try {
      const res = await fetch(`/api/auth/methods/${provider}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Failed to unlink method.");
      }
      setMethodSuccess(`Unlinked ${provider} successfully.`);
      await loadMethods();
    } catch (err: any) {
      setMethodError(err.message || "Failed to unlink.");
    }
  }

  async function submitLinkGoogleToken(idToken: string) {
    setMethodError(null);
    setMethodSuccess(null);
    try {
      const res = await fetch("/api/auth/link/google", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: idToken }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const requestId = data?.error?.request_id || res.headers.get("x-request-id");
        const baseMsg = data?.error?.message || "Failed to link Google account.";
        throw new Error(requestId ? `${baseMsg} (Request ID: ${requestId})` : baseMsg);
      }
      setMethodSuccess("Google account linked successfully.");
      await loadMethods();
    } catch (err: any) {
      setMethodError(err.message || "Failed to link Google.");
    }
  }

  async function handleRequestLinkPhoneOtp() {
    setLinkLoading(true);
    setLinkError(null);
    try {
      const cleanPhone = linkPhone.replace(/[\s-]/g, "");
      const res = await fetch("/api/auth/link/phone", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: cleanPhone }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Failed to send link OTP.");
      }
      setLinkOtpSent(true);
    } catch (err: any) {
      setLinkError(err.message || "Failed to send link OTP.");
    } finally {
      setLinkLoading(false);
    }
  }

  async function handleVerifyLinkPhoneOtp() {
    setLinkLoading(true);
    setLinkError(null);
    try {
      const cleanPhone = linkPhone.replace(/[\s-]/g, "");
      const res = await fetch("/api/auth/link/phone/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: cleanPhone, otp: linkOtp }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Failed to verify phone OTP.");
      }
      setShowLinkPhoneModal(false);
      setLinkOtp("");
      setLinkOtpSent(false);
      setMethodSuccess("Phone number linked successfully.");
      await loadMethods();
    } catch (err: any) {
      setLinkError(err.message || "Failed to verify phone OTP.");
    } finally {
      setLinkLoading(false);
    }
  }

  async function handleSetPassword() {
    if (newPassword.length < 8) {
      setMethodError("Password must be at least 8 characters long.");
      return;
    }
    setSettingPassword(true);
    setMethodError(null);
    try {
      const res = await fetch("/api/auth/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: newPassword }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Failed to set password.");
      }
      setShowSetPasswordModal(false);
      setNewPassword("");
      setMethodSuccess("Password created successfully. Other sessions have been revoked.");
      await loadMethods();
      await loadSessions();
    } catch (err: any) {
      setMethodError(err.message || "Failed to set password.");
    } finally {
      setSettingPassword(false);
    }
  }

  // Session actions
  async function handleRevokeSession(sessionId: string) {
    setSessionError(null);
    setSessionSuccess(null);
    try {
      const res = await fetch(`/api/auth/sessions/${sessionId}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Failed to revoke session.");
      }
      setSessionSuccess("Session revoked successfully.");
      await loadSessions();
    } catch (err: any) {
      setSessionError(err.message || "Failed to revoke session.");
    }
  }

  async function handleLogoutAll() {
    setSessionError(null);
    try {
      const res = await fetch("/api/auth/logout-all", { method: "POST" });
      if (res.ok) {
        window.location.href = "/login";
      }
    } catch {
      window.location.href = "/login";
    }
  }

  const hasGoogleLinked = methods.some((m) => m.provider === "google");
  const hasPhoneLinked = methods.some((m) => m.provider === "phone");

  return (
    <AppShell>
      <div className="max-w-4xl mx-auto space-y-8 pb-12">
        {/* Header */}
        <div>
          <span className="cnl-kicker">Account &amp; Security Preferences</span>
          <h1 className="text-2xl sm:text-3xl font-serif font-normal text-ink mt-2">
            Settings
          </h1>
          <p className="text-xs sm:text-sm text-mute mt-1">
            Control your authentication credentials, active sessions, privacy consents, and appearance.
          </p>
        </div>

        {/* Section 1: Sign-in Methods */}
        <div data-testid="signin-methods-section" className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <KeyRound className="h-5 w-5 text-accent" />
              <h3 className="text-base font-serif font-medium text-ink">Sign-in Methods</h3>
            </div>
          </div>
          <p className="text-xs text-mute">
            Manage your linked sign-in credentials. At least one authentication method must always be retained.
          </p>

          {methodError && (
            <div role="alert" className="flex items-start gap-2 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 p-3 text-xs text-red-800 dark:text-red-300">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <span>{methodError}</span>
            </div>
          )}

          {methodSuccess && (
            <div role="status" className="flex items-center gap-2 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-900/50 p-3 text-xs text-emerald-800 dark:text-emerald-300">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>{methodSuccess}</span>
            </div>
          )}

          <div className="space-y-3 pt-2">
            {/* Password Method */}
            {hasPassword ? (
              <div className="flex items-center justify-between rounded-2xl border border-line bg-soft/30 p-4">
                <div className="flex items-center gap-3">
                  <Mail className="h-4 w-4 text-mute" />
                  <div>
                    <div className="text-xs font-semibold text-ink">Password</div>
                    <div className="text-[11px] text-mute">Configured account password</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                    ACTIVE
                  </span>
                  <button
                    type="button"
                    onClick={() => handleUnlinkMethod("password")}
                    disabled={isSoleMethod}
                    title={isSoleMethod ? "Cannot remove sole authentication method" : "Unlink password"}
                    className="p-1.5 rounded-lg text-mute hover:text-red-600 disabled:opacity-40 disabled:hover:text-mute"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between rounded-2xl border border-dashed border-line bg-soft/10 p-4">
                <div className="flex items-center gap-3">
                  <Mail className="h-4 w-4 text-mute" />
                  <div>
                    <div className="text-xs font-semibold text-ink">Password</div>
                    <div className="text-[11px] text-mute">No password configured on this account</div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setShowSetPasswordModal(true)}
                  className="inline-flex items-center gap-1 rounded-xl bg-soft px-3 py-1.5 text-xs font-semibold text-ink hover:bg-soft/80"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Set Password</span>
                </button>
              </div>
            )}

            {/* Google Method */}
            {capabilities.google && (
              hasGoogleLinked ? (
                <div className="flex items-center justify-between rounded-2xl border border-line bg-soft/30 p-4">
                  <div className="flex items-center gap-3">
                    <div className="h-4 w-4 rounded-full bg-red-500 text-white flex items-center justify-center text-[10px] font-bold">
                      G
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-ink">Google Account</div>
                      <div className="text-[11px] text-mute">
                        {methods.find((m) => m.provider === "google")?.identifier || "Linked"}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                      LINKED
                    </span>
                    <button
                      type="button"
                      onClick={() => handleUnlinkMethod("google")}
                      disabled={isSoleMethod}
                      title={isSoleMethod ? "Cannot remove sole authentication method" : "Unlink Google"}
                      className="p-1.5 rounded-lg text-mute hover:text-red-600 disabled:opacity-40 disabled:hover:text-mute"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-2xl border border-dashed border-line bg-soft/10 p-4">
                  <div className="flex items-center gap-3">
                    <div className="h-4 w-4 rounded-full bg-red-500 text-white flex items-center justify-center text-[10px] font-bold">
                      G
                    </div>
                    <div>
                      <div className="text-xs font-semibold text-ink">Google Account</div>
                      <div className="text-[11px] text-mute">Link your Google identity for 1-click access</div>
                    </div>
                  </div>
                  <div className="w-full sm:w-auto sm:min-w-[240px]">
                    <GoogleSignInButton
                      clientId={capabilities.google_client_id}
                      onCredential={submitLinkGoogleToken}
                      onError={setMethodError}
                      text="continue_with"
                      dataTestId="google-link-btn"
                    />
                  </div>
                </div>
              )
            )}

            {/* Phone Method */}
            {capabilities.phone && (
              hasPhoneLinked ? (
                <div data-testid="phone-signin-method" className="flex items-center justify-between rounded-2xl border border-line bg-soft/30 p-4">
                  <div className="flex items-center gap-3">
                    <Phone className="h-4 w-4 text-mute" />
                    <div>
                      <div className="text-xs font-semibold text-ink">Phone OTP</div>
                      <div className="text-[11px] text-mute font-mono">
                        {methods.find((m) => m.provider === "phone")?.identifier || "Linked"}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
                      LINKED
                    </span>
                    <button
                      type="button"
                      onClick={() => handleUnlinkMethod("phone")}
                      disabled={isSoleMethod}
                      title={isSoleMethod ? "Cannot remove sole authentication method" : "Unlink Phone"}
                      className="p-1.5 rounded-lg text-mute hover:text-red-600 disabled:opacity-40 disabled:hover:text-mute"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ) : (
                <div data-testid="phone-signin-method" className="flex items-center justify-between rounded-2xl border border-dashed border-line bg-soft/10 p-4">
                  <div className="flex items-center gap-3">
                    <Phone className="h-4 w-4 text-mute" />
                    <div>
                      <div className="text-xs font-semibold text-ink">Phone OTP</div>
                      <div className="text-[11px] text-mute">Link an Indian mobile (+91) for OTP sign-in</div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowLinkPhoneModal(true)}
                    className="inline-flex items-center gap-1 rounded-xl bg-soft px-3 py-1.5 text-xs font-semibold text-ink hover:bg-soft/80"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Link Phone</span>
                  </button>
                </div>
              )
            )}
          </div>
        </div>

        {/* Modal: Set Password */}
        {showSetPasswordModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-sm rounded-2xl border border-line bg-card p-6 shadow-xl space-y-4">
              <h3 className="text-sm font-semibold text-ink">Set Account Password</h3>
              <p className="text-xs text-mute">
                Create a secure password with at least 8 characters. Setting a password will revoke other active sessions.
              </p>
              <label htmlFor="modal-set-password" className="block text-xs font-semibold uppercase tracking-wider text-mute">
                New Password
              </label>
              <input
                id="modal-set-password"
                aria-label="New Password"
                type="password"
                minLength={8}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="Enter password (min 8 chars)"
                className="w-full rounded-lg border border-line bg-soft px-3 py-2 text-xs text-ink"
              />
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowSetPasswordModal(false)}
                  className="rounded-lg border border-line px-3 py-1.5 text-xs text-mute"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSetPassword}
                  disabled={settingPassword || newPassword.length < 8}
                  className="rounded-lg bg-ink px-4 py-1.5 text-xs font-semibold text-bg disabled:opacity-50"
                >
                  {settingPassword ? "Saving..." : "Set Password"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Modal: Link Phone OTP */}
        {showLinkPhoneModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
            <div className="w-full max-w-sm rounded-2xl border border-line bg-card p-6 shadow-xl space-y-4">
              <h3 className="text-sm font-semibold text-ink">Link Phone Number</h3>
              {linkError && (
                <div className="rounded-lg bg-red-50 dark:bg-red-950/30 p-2 text-xs text-red-700">
                  {linkError}
                </div>
              )}
              {!linkOtpSent ? (
                <>
                  <label htmlFor="modal-link-phone" className="block text-xs text-mute">
                    Enter your Indian phone number starting with +91:
                  </label>
                  <input
                    id="modal-link-phone"
                    aria-label="Mobile Phone Number"
                    type="tel"
                    value={linkPhone}
                    onChange={(e) => setLinkPhone(e.target.value)}
                    placeholder="+91 98765 43210"
                    className="w-full rounded-lg border border-line bg-soft px-3 py-2 text-xs text-ink font-mono"
                  />
                  <div className="flex justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setShowLinkPhoneModal(false)}
                      className="rounded-lg border border-line px-3 py-1.5 text-xs text-mute"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleRequestLinkPhoneOtp}
                      disabled={linkLoading || !linkPhone}
                      className="rounded-lg bg-ink px-4 py-1.5 text-xs font-semibold text-bg disabled:opacity-50"
                    >
                      {linkLoading ? "Sending..." : "Send OTP"}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <label htmlFor="modal-link-otp" className="block text-xs text-mute">
                    Enter the 6-digit OTP sent to {linkPhone}:
                  </label>
                  <input
                    id="modal-link-otp"
                    aria-label="6-Digit OTP Code"
                    type="text"
                    maxLength={6}
                    value={linkOtp}
                    onChange={(e) => setLinkOtp(e.target.value.replace(/\D/g, ""))}
                    placeholder="123456"
                    className="w-full rounded-lg border border-line bg-soft px-3 py-2 text-center text-sm font-mono tracking-widest text-ink"
                  />
                  <div className="flex justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setLinkOtpSent(false)}
                      className="rounded-lg border border-line px-3 py-1.5 text-xs text-mute"
                    >
                      Back
                    </button>
                    <button
                      type="button"
                      onClick={handleVerifyLinkPhoneOtp}
                      disabled={linkLoading || linkOtp.length < 6}
                      className="rounded-lg bg-ink px-4 py-1.5 text-xs font-semibold text-bg disabled:opacity-50"
                    >
                      {linkLoading ? "Verifying..." : "Confirm & Link"}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* Section 2: Active Sessions */}
        <div data-testid="sessions-section" className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Laptop className="h-5 w-5 text-accent" />
              <h3 className="text-base font-serif font-medium text-ink">Active Sessions</h3>
            </div>
            <button
              type="button"
              onClick={handleLogoutAll}
              className="inline-flex items-center gap-1.5 rounded-xl border border-red-300 dark:border-red-900 bg-red-50 dark:bg-red-950/20 px-3.5 py-1.5 text-xs font-semibold text-red-700 dark:text-red-300 hover:bg-red-100 transition-colors"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span>Log Out All Devices</span>
            </button>
          </div>
          <p className="text-xs text-mute">
            Devices and browser sessions currently signed into your Float account.
          </p>

          {sessionError && (
            <div role="alert" className="rounded-xl bg-red-50 dark:bg-red-950/30 p-2.5 text-xs text-red-700">
              {sessionError}
            </div>
          )}

          {sessionSuccess && (
            <div role="status" className="rounded-xl bg-emerald-50 dark:bg-emerald-950/30 p-2.5 text-xs text-emerald-800">
              {sessionSuccess}
            </div>
          )}

          <div className="space-y-2.5 pt-1">
            {sessions.map((sess, idx) => (
              <div
                key={sess.id}
                className="flex items-center justify-between rounded-2xl border border-line bg-soft/20 p-3.5 text-xs"
              >
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-ink truncate max-w-xs sm:max-w-md">
                      {sess.user_agent || "Browser Session"}
                    </span>
                    {idx === 0 && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-agent/10 text-agent">
                        CURRENT
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-mute flex items-center gap-2">
                    <span>IP: {sess.ip_address_mask}</span>
                    <span>•</span>
                    <span>Active: {new Date(sess.last_active_at).toLocaleDateString()}</span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => handleRevokeSession(sess.id)}
                  className="rounded-lg p-1.5 text-mute hover:text-red-600 transition-colors"
                  title="Revoke this session"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Section 3: Privacy & DPDP Consent */}
        <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-4">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-accent" />
            <h3 className="text-base font-serif font-medium text-ink">Data Protection &amp; Consent</h3>
          </div>
          <p className="text-xs text-mute">
            Under India&apos;s Digital Personal Data Protection (DPDP) Act 2023, you have full sovereignty over your data.
          </p>

          <div className="pt-2 flex items-center justify-between rounded-2xl border border-line bg-soft/30 p-4">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-ink">AI Financial Insights Consent</span>
              <p className="text-[11px] text-mute max-w-md">
                Allows Float AI to analyze masked bank statements and plan recommendations.
              </p>
            </div>
            <button
              onClick={handleToggleConsent}
              disabled={loadingConsent || updatingConsent}
              className={`rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
                consentGranted
                  ? "bg-emerald-600 text-white hover:bg-emerald-700"
                  : "bg-neutral-300 dark:bg-neutral-700 text-neutral-800 dark:text-neutral-200"
              }`}
            >
              {updatingConsent ? "Updating..." : consentGranted ? "Granted" : "Revoked"}
            </button>
          </div>

          <div className="pt-2 flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-ink">Erase Assistant Conversation History</span>
              <p className="text-[11px] text-mute">Permanently deletes messages and memory embeddings.</p>
            </div>
            <button
              onClick={() => setShowPurgeModal(true)}
              className="rounded-xl border border-rose-300 dark:border-rose-900 bg-rose-50 dark:bg-rose-950/30 px-3 py-1.5 text-xs font-semibold text-rose-700 dark:text-rose-300"
            >
              Purge History
            </button>
          </div>

          {showPurgeModal && (
            <div className="rounded-2xl border border-red-300 bg-red-50/60 dark:bg-red-950/20 p-4 space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-red-900 dark:text-red-200">
                <AlertTriangle className="h-4 w-4 text-red-600" />
                <span>Confirm Permanent Deletion</span>
              </div>
              <p className="text-xs text-red-800 dark:text-red-300">
                Type <strong>DELETE_MY_CONVERSATIONS</strong> to confirm:
              </p>
              <input
                type="text"
                value={confirmPhrase}
                onChange={(e) => setConfirmPhrase(e.target.value)}
                placeholder="DELETE_MY_CONVERSATIONS"
                className="w-full rounded-lg border border-red-300 bg-card px-3 py-1.5 text-xs text-ink"
              />
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setShowPurgeModal(false)}
                  className="rounded-lg border border-line px-3 py-1 text-xs text-mute"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handlePurgeConversations}
                  disabled={purging || confirmPhrase !== "DELETE_MY_CONVERSATIONS"}
                  className="rounded-lg bg-red-600 px-3 py-1 text-xs font-bold text-white hover:bg-red-700 disabled:opacity-40"
                >
                  {purging ? "Purging..." : "Confirm"}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Section 4: Appearance & Theme */}
        <div data-testid="theme-settings-section" className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-3">
          <div className="flex items-center gap-2">
            <Sun className="h-5 w-5 text-accent" />
            <h3 className="text-base font-serif font-medium text-ink">Appearance & Theme</h3>
          </div>
          <p className="text-xs text-mute">
            Choose how Float looks to you. Select a light, dark, or system synchronized color palette.
          </p>
          <div className="pt-2 grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[
              { mode: "light" as const, label: "Light Mode", desc: "Crisp editorial palette", icon: Sun },
              { mode: "dark" as const, label: "Dark Mode", desc: "High contrast dark palette", icon: Moon },
              { mode: "system" as const, label: "System Sync", desc: "Matches device settings", icon: Monitor },
            ].map((item) => {
              const Icon = item.icon;
              const isSelected = theme === item.mode;
              return (
                <button
                  key={item.mode}
                  type="button"
                  onClick={() => setTheme(item.mode)}
                  className={`flex flex-col items-start rounded-2xl border p-4 text-left transition-all ${
                    isSelected
                      ? "border-accent bg-accent/5 ring-1 ring-accent"
                      : "border-line bg-soft/20 hover:border-mute hover:bg-soft/50"
                  }`}
                  data-testid={item.mode === "light" ? "theme-option-light" : item.mode === "dark" ? "theme-option-dark" : "theme-option-system"}
                >
                  <div className="flex w-full items-center justify-between pb-2">
                    <Icon className={`h-4 w-4 ${isSelected ? "text-accent" : "text-mute"}`} />
                    {isSelected && (
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-accent/10 text-accent">
                        ACTIVE
                      </span>
                    )}
                  </div>
                  <span className="text-xs font-semibold text-ink">{item.label}</span>
                  <span className="text-[11px] text-mute">{item.desc}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Section 5: Language & Region */}
        <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-3">
          <div className="flex items-center gap-2">
            <Globe className="h-5 w-5 text-accent" />
            <h3 className="text-base font-serif font-medium text-ink">Language &amp; Region</h3>
          </div>
          <p className="text-xs text-mute">
            Select your preferred interface language.
          </p>
          <div className="pt-2 flex flex-wrap gap-2">
            {[
              { code: "en", label: "English" },
              { code: "ml", label: "മലയാളം (Malayalam)" },
              { code: "manglish", label: "Manglish" },
            ].map((lang) => (
              <button
                key={lang.code}
                onClick={() => setLanguage(lang.code)}
                className={`rounded-xl px-4 py-2 text-xs font-medium border transition-colors ${
                  language === lang.code
                    ? "border-accent bg-accent/10 text-accent font-semibold"
                    : "border-line bg-soft/50 text-mute hover:text-ink"
                }`}
              >
                {lang.label}
              </button>
            ))}
          </div>
        </div>

        {/* Section 6: Feature Flag Registry */}
        <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-3">
          <div className="flex items-center gap-2">
            <Sliders className="h-5 w-5 text-accent" />
            <h3 className="text-base font-serif font-medium text-ink">Feature Flag Registry</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2">
            {Object.entries(FEATURES).map(([key, enabled]) => (
              <div
                key={key}
                className="flex items-center justify-between rounded-xl border border-line bg-soft/30 p-2.5 text-xs"
              >
                <span className="font-mono text-[11px] text-ink">{key}</span>
                <span
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                    enabled ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" : "bg-soft text-faint"
                  }`}
                >
                  {enabled ? "ACTIVE" : "PLANNED"}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </AppShell>
  );
}

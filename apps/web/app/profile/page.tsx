"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  User as UserIcon,
  ShieldCheck,
  KeyRound,
  Laptop,
  Download,
  Trash2,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Sun,
  Moon,
  Monitor,
  Bell,
} from "lucide-react";
import AppShell from "@/components/AppShell";
import { useTheme, ThemeMode } from "@/components/ThemeToggle";
import { DICTIONARY, Language, getActiveLanguage, setActiveLanguage } from "@/lib/i18n";

interface ProfileData {
  user_id: string;
  full_name: string;
  email: string | null;
  phone_number: string | null;
  preferred_language: Language;
  locale: string;
  notification_preferences: {
    security_alerts: boolean;
    recurring_reminders: boolean;
    product_updates: boolean;
  };
  methods: string[];
  consent: {
    terms_accepted: boolean;
    ai_data_processing_consent: boolean;
    consent_version: string;
  };
  deletion_requested_at: string | null;
  deletion_scheduled_for: string | null;
  created_at: string;
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "F";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function ProfilePage() {
  const { theme, setTheme } = useTheme();
  const [lang, setLang] = useState<Language>("en");

  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Editable form state
  const [fullName, setFullName] = useState("");
  const [preferredLang, setPreferredLang] = useState<Language>("en");
  const [notifPrefs, setNotifPrefs] = useState({
    security_alerts: true,
    recurring_reminders: true,
    product_updates: false,
  });

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const isSubmitting = useRef(false);

  // Export state
  const [exporting, setExporting] = useState(false);

  // Delete account dialog state
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [reauthPassword, setReauthPassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    setLang(getActiveLanguage());
    loadProfile();
  }, []);

  async function loadProfile() {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await fetch("/api/me", { cache: "no-store" });
      const data = await res.json().catch(() => null);
      if (!res.ok || !data) {
        throw new Error(data?.error?.message || "Failed to load profile.");
      }
      setProfile(data);
      setFullName(data.full_name || "");
      const loadedLang = (data.preferred_language as Language) || "en";
      setPreferredLang(loadedLang);
      setActiveLanguage(loadedLang);
      setLang(loadedLang);
      if (data.notification_preferences) {
        setNotifPrefs({
          security_alerts: Boolean(data.notification_preferences.security_alerts ?? true),
          recurring_reminders: Boolean(data.notification_preferences.recurring_reminders ?? true),
          product_updates: Boolean(data.notification_preferences.product_updates ?? false),
        });
      }
    } catch (err: any) {
      setLoadError(err.message || "Unable to load profile.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveProfile(e: React.FormEvent) {
    e.preventDefault();
    if (isSubmitting.current) return;
    isSubmitting.current = true;
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(null);

    try {
      const locale = preferredLang === "ml" ? "ml-IN" : "en-IN";
      const res = await fetch("/api/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: fullName,
          preferred_language: preferredLang,
          locale,
          notification_preferences: notifPrefs,
        }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const msg =
          data?.error?.message ||
          data?.detail?.[0]?.msg ||
          "Could not update profile. Please check your input.";
        throw new Error(msg);
      }

      setProfile(data);
      setFullName(data.full_name);
      setActiveLanguage(preferredLang);
      setLang(preferredLang);
      setSaveSuccess("Profile preferences saved.");
    } catch (err: any) {
      // Preserve user input on error
      setSaveError(err.message || "Failed to update profile.");
    } finally {
      setSaving(false);
      isSubmitting.current = false;
    }
  }

  async function handleExportData() {
    if (exporting) return;
    setExporting(true);
    setSaveError(null);
    try {
      const res = await fetch("/api/me/export", { method: "POST" });
      const data = await res.json().catch(() => null);
      if (!res.ok || !data) {
        throw new Error(data?.error?.message || "Failed to export data.");
      }
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "float-dpdp-export.json";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setSaveSuccess("Your DPDP data export has started downloading.");
    } catch (err: any) {
      setSaveError(err.message || "Data export failed.");
    } finally {
      setExporting(false);
    }
  }

  async function handleDeleteAccount(e: React.FormEvent) {
    e.preventDefault();
    if (deleting) return;
    if (confirmText.trim().toUpperCase() !== "DELETE") {
      setDeleteError('Please type "DELETE" to confirm account deletion.');
      return;
    }
    setDeleting(true);
    setDeleteError(null);

    try {
      // Step-up re-auth if password provided
      if (reauthPassword.trim()) {
        const reauthRes = await fetch("/api/auth/reauth", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password: reauthPassword }),
        });
        if (!reauthRes.ok) {
          const rErr = await reauthRes.json().catch(() => null);
          throw new Error(rErr?.error?.message || "Re-authentication failed.");
        }
      }

      const res = await fetch("/api/me", { method: "DELETE" });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(data?.error?.message || "Account deletion request failed.");
      }

      setProfile((prev) =>
        prev
          ? {
              ...prev,
              deletion_requested_at: data.deletion_requested_at,
              deletion_scheduled_for: data.deletion_scheduled_for,
            }
          : prev
      );
      setShowDeleteModal(false);
      setConfirmText("");
      setReauthPassword("");
      setSaveSuccess(data.message || "Account deletion scheduled.");
    } catch (err: any) {
      setDeleteError(err.message || "Unable to schedule deletion.");
    } finally {
      setDeleting(false);
    }
  }

  async function handleCancelDeletion() {
    setSaveError(null);
    try {
      const res = await fetch("/api/me/delete/cancel", { method: "POST" });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(data?.error?.message || "Could not cancel deletion.");
      }
      setProfile(data);
      setSaveSuccess("Scheduled account deletion has been cancelled.");
    } catch (err: any) {
      setSaveError(err.message || "Failed to cancel deletion.");
    }
  }

  const t = DICTIONARY[lang]?.profile || DICTIONARY.en.profile;

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-serif font-normal text-ink flex items-center gap-2.5">
            <UserIcon className="h-6 w-6 text-accent" />
            <span>{t.title}</span>
          </h1>
          <p className="mt-1 text-sm text-mute">{t.subtitle}</p>
        </div>

        {/* Skeleton loading state */}
        {loading && (
          <div data-testid="profile-skeleton" className="space-y-4 animate-pulse">
            <div className="h-28 rounded-2xl bg-soft" />
            <div className="h-64 rounded-2xl bg-soft" />
          </div>
        )}

        {/* Load error state */}
        {!loading && loadError && (
          <div role="alert" className="rounded-2xl border border-red-500/30 bg-red-500/10 p-5 text-sm text-red-600 dark:text-red-400">
            <div className="flex items-center justify-between gap-4">
              <span>{loadError}</span>
              <button
                type="button"
                onClick={loadProfile}
                className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700"
              >
                Retry
              </button>
            </div>
          </div>
        )}

        {!loading && profile && (
          <>
            {/* Grace Period Notice */}
            {profile.deletion_scheduled_for && (
              <div
                role="status"
                data-testid="deletion-grace-notice"
                className="rounded-2xl border border-amber-500/40 bg-amber-500/10 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4"
              >
                <div className="flex items-start gap-3">
                  <AlertTriangle className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
                  <div>
                    <h2 className="text-sm font-semibold text-ink">{t.graceNotice}</h2>
                    <p className="text-xs text-mute mt-1">
                      Scheduled for: <strong className="text-ink">{profile.deletion_scheduled_for}</strong>. Your sessions
                      were revoked and conversations purged. You may cancel before the grace period ends.
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleCancelDeletion}
                  data-testid="cancel-deletion-btn"
                  className="shrink-0 rounded-xl border border-line bg-card px-4 py-2 text-xs font-semibold text-ink hover:bg-soft"
                >
                  Cancel Deletion
                </button>
              </div>
            )}

            {saveError && (
              <div role="alert" className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-xs text-red-600 dark:text-red-400">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>{saveError}</span>
              </div>
            )}

            {saveSuccess && (
              <div role="status" className="flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-xs text-emerald-700 dark:text-emerald-400">
                <CheckCircle2 className="h-4 w-4 shrink-0" />
                <span>{saveSuccess}</span>
              </div>
            )}

            {/* Avatar & Identity Header */}
            <section className="rounded-2xl border border-line bg-card p-6 flex items-center gap-4">
              <div
                aria-hidden="true"
                data-testid="profile-avatar"
                className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-accent text-lg font-bold text-white"
              >
                {getInitials(profile.full_name)}
              </div>
              <div className="min-w-0">
                <div className="text-base font-semibold text-ink truncate" data-testid="profile-display-name">
                  {profile.full_name}
                </div>
                <div className="text-xs text-mute truncate">
                  {profile.email || profile.phone_number || "No primary contact"}
                </div>
              </div>
            </section>

            {/* Profile & Preferences Form */}
            <form onSubmit={handleSaveProfile} className="rounded-2xl border border-line bg-card p-6 space-y-5">
              <div>
                <label htmlFor="profile-full-name" className="block text-xs font-semibold uppercase tracking-wider text-mute mb-1.5">
                  {t.displayName}
                </label>
                <input
                  id="profile-full-name"
                  type="text"
                  required
                  maxLength={100}
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full rounded-xl border border-line bg-bg px-3.5 py-2.5 text-sm text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="profile-language" className="block text-xs font-semibold uppercase tracking-wider text-mute mb-1.5">
                    {t.language}
                  </label>
                  <select
                    id="profile-language"
                    value={preferredLang}
                    onChange={(e) => setPreferredLang(e.target.value as Language)}
                    className="w-full rounded-xl border border-line bg-bg px-3.5 py-2.5 text-sm text-ink focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
                  >
                    <option value="en">English (en-IN)</option>
                    <option value="ml">മലയാളം (ml-IN)</option>
                    <option value="manglish">Manglish (en-IN)</option>
                  </select>
                </div>

                <div>
                  <span className="block text-xs font-semibold uppercase tracking-wider text-mute mb-1.5">
                    {t.theme}
                  </span>
                  <div className="flex rounded-xl bg-soft p-1 gap-1" role="group" aria-label="Theme preference">
                    {(["light", "dark", "system"] as ThemeMode[]).map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => setTheme(mode)}
                        className={`flex-1 flex items-center justify-center gap-1.5 rounded-lg py-2 text-xs font-medium capitalize transition-colors ${
                          theme === mode ? "bg-card text-ink shadow-sm" : "text-mute hover:text-ink"
                        }`}
                      >
                        {mode === "light" && <Sun className="h-3.5 w-3.5" />}
                        {mode === "dark" && <Moon className="h-3.5 w-3.5" />}
                        {mode === "system" && <Monitor className="h-3.5 w-3.5" />}
                        <span>{mode}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Notification Preferences */}
              <div className="pt-2 border-t border-line/60 space-y-2.5">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-mute">
                  <Bell className="h-3.5 w-3.5" />
                  <span>Notification Preferences</span>
                </div>
                <label className="flex items-center gap-2.5 text-sm text-ink cursor-pointer">
                  <input
                    type="checkbox"
                    checked={notifPrefs.security_alerts}
                    onChange={(e) => setNotifPrefs((p) => ({ ...p, security_alerts: e.target.checked }))}
                    className="rounded border-line text-accent focus:ring-accent"
                  />
                  <span>Security &amp; fraud alerts</span>
                </label>
                <label className="flex items-center gap-2.5 text-sm text-ink cursor-pointer">
                  <input
                    type="checkbox"
                    checked={notifPrefs.recurring_reminders}
                    onChange={(e) => setNotifPrefs((p) => ({ ...p, recurring_reminders: e.target.checked }))}
                    className="rounded border-line text-accent focus:ring-accent"
                  />
                  <span>Recurring payment reminders</span>
                </label>
                <label className="flex items-center gap-2.5 text-sm text-ink cursor-pointer">
                  <input
                    type="checkbox"
                    checked={notifPrefs.product_updates}
                    onChange={(e) => setNotifPrefs((p) => ({ ...p, product_updates: e.target.checked }))}
                    className="rounded border-line text-accent focus:ring-accent"
                  />
                  <span>Product updates</span>
                </label>
              </div>

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={saving}
                  data-testid="save-profile-btn"
                  className="rounded-xl bg-ink px-5 py-2.5 text-sm font-semibold text-bg hover:opacity-90 disabled:opacity-50"
                >
                  {saving ? "Saving..." : "Save Profile"}
                </button>
              </div>
            </form>

            {/* Sign-in Methods, Active Sessions & Consent Summary */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="rounded-2xl border border-line bg-card p-5 flex flex-col justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-xs font-semibold text-ink">
                    <KeyRound className="h-4 w-4 text-accent" />
                    <span>Sign-In Methods</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {profile.methods.map((m) => (
                      <span key={m} className="rounded-full bg-soft px-2.5 py-0.5 text-xs font-medium capitalize text-ink">
                        {m}
                      </span>
                    ))}
                  </div>
                </div>
                <Link href="/settings#methods" className="text-xs font-semibold text-accent hover:underline">
                  Manage methods →
                </Link>
              </div>

              <div className="rounded-2xl border border-line bg-card p-5 flex flex-col justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-xs font-semibold text-ink">
                    <Laptop className="h-4 w-4 text-accent" />
                    <span>Active Sessions</span>
                  </div>
                  <p className="mt-2 text-xs text-mute">Review signed-in devices or log out everywhere.</p>
                </div>
                <Link href="/settings#sessions" className="text-xs font-semibold text-accent hover:underline">
                  View active sessions →
                </Link>
              </div>

              <div className="rounded-2xl border border-line bg-card p-5 flex flex-col justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2 text-xs font-semibold text-ink">
                    <ShieldCheck className="h-4 w-4 text-accent" />
                    <span>DPDP Consent</span>
                  </div>
                  <p className="mt-2 text-xs text-mute">
                    Terms: {profile.consent.terms_accepted ? "Accepted" : "Pending"} · AI:{" "}
                    {profile.consent.ai_data_processing_consent ? "Active" : "Paused"}
                  </p>
                </div>
                <Link href="/consent" className="text-xs font-semibold text-accent hover:underline">
                  Review consent →
                </Link>
              </div>
            </div>

            {/* DPDP Data Rights: Export & Delete Account */}
            <section className="rounded-2xl border border-line bg-card p-6 space-y-4">
              <h2 className="text-base font-semibold text-ink">DPDP Data Rights</h2>
              <div className="flex flex-col sm:flex-row gap-3">
                <button
                  type="button"
                  onClick={handleExportData}
                  disabled={exporting}
                  data-testid="export-data-btn"
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-line bg-soft px-4 py-2.5 text-xs font-semibold text-ink hover:bg-soft/80 disabled:opacity-50"
                >
                  <Download className="h-4 w-4" />
                  <span>{exporting ? "Exporting..." : t.downloadData}</span>
                </button>

                <button
                  type="button"
                  onClick={() => setShowDeleteModal(true)}
                  data-testid="open-delete-account-btn"
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-2.5 text-xs font-semibold text-red-600 dark:text-red-400 hover:bg-red-500/20"
                >
                  <Trash2 className="h-4 w-4" />
                  <span>{t.deleteAccount}</span>
                </button>
              </div>

              {showDeleteModal && (
                <form
                  onSubmit={handleDeleteAccount}
                  data-testid="delete-account-dialog"
                  className="mt-4 rounded-xl border border-red-500/40 bg-bg p-4 space-y-3"
                >
                  <div className="text-sm font-semibold text-red-600 dark:text-red-400">
                    Confirm Account Deletion (14-Day Grace Period)
                  </div>
                  <p className="text-xs text-mute">
                    This revokes all sessions, purges conversations, anonymizes audit logs, and schedules deletion.
                  </p>
                  {deleteError && (
                    <div role="alert" className="text-xs text-red-600 dark:text-red-400">
                      {deleteError}
                    </div>
                  )}
                  <div>
                    <label htmlFor="delete-confirm-input" className="block text-xs font-medium text-ink mb-1">
                      Type <code>DELETE</code> to confirm
                    </label>
                    <input
                      id="delete-confirm-input"
                      type="text"
                      required
                      value={confirmText}
                      onChange={(e) => setConfirmText(e.target.value)}
                      placeholder="DELETE"
                      className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink"
                    />
                  </div>
                  <div>
                    <label htmlFor="delete-reauth-password" className="block text-xs font-medium text-ink mb-1">
                      Confirm Password (Step-up Re-authentication)
                    </label>
                    <input
                      id="delete-reauth-password"
                      type="password"
                      value={reauthPassword}
                      onChange={(e) => setReauthPassword(e.target.value)}
                      placeholder="Required if your session is older than 10 minutes"
                      className="w-full rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink"
                    />
                  </div>
                  <div className="flex gap-2 justify-end">
                    <button
                      type="button"
                      onClick={() => setShowDeleteModal(false)}
                      className="rounded-lg border border-line px-3 py-1.5 text-xs font-medium text-ink"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={deleting}
                      data-testid="confirm-delete-account-btn"
                      className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 disabled:opacity-50"
                    >
                      {deleting ? "Scheduling..." : "Schedule Deletion"}
                    </button>
                  </div>
                </form>
              )}
            </section>
          </>
        )}
      </div>
    </AppShell>
  );
}

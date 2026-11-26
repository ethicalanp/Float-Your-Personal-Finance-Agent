"use client";

import { useState, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";
import { Logo } from "@/components/Logo";
import { WarpedFloatBackground } from "@/components/WarpedFloatBackground";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    setError(null);
    setLoading(true);

    try {
      const res = await fetch("/api/auth/password-reset/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Password reset token is invalid or expired.");
      }

      setSuccess(true);
      setTimeout(() => {
        router.push("/login");
      }, 2500);
    } catch (err: any) {
      setError(err.message || "Failed to reset password.");
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <div className="text-center space-y-4">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-600">
          <AlertCircle className="h-6 w-6" />
        </div>
        <h2 className="text-base font-semibold text-ink">Missing Reset Token</h2>
        <p className="text-xs text-mute">
          This password reset link is invalid or incomplete. Please request a new link.
        </p>
        <div className="pt-2">
          <Link href="/forgot-password" className="text-xs font-semibold text-accent hover:underline">
            Request new reset link
          </Link>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="text-center space-y-4">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
          <CheckCircle2 className="h-6 w-6" />
        </div>
        <h2 className="text-base font-semibold text-ink">Password Reset Successfully</h2>
        <p className="text-xs text-mute">
          Your new password is set. Redirecting you to the sign-in screen...
        </p>
        <div className="pt-2">
          <Link href="/login" className="text-xs font-semibold text-accent hover:underline">
            Proceed to Sign In
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div>
      <noscript>
        <div className="mb-4 rounded-lg bg-amber-500/10 border border-amber-500/30 p-3 text-xs text-amber-800 dark:text-amber-200">
          JavaScript is required to reset your password securely.
        </div>
      </noscript>
      <form method="post" action="#" onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div
            role="alert"
            className="flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300"
          >
            <AlertCircle className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <div>
          <label htmlFor="newPassword" className="block text-xs font-semibold uppercase tracking-wider text-mute">
            New Password (min 8 characters)
          </label>
          <input
            id="newPassword"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="••••••••••••"
            className="mt-1.5 block w-full rounded-lg border border-line bg-soft/50 px-3.5 py-2.5 text-sm text-ink placeholder-faint focus:border-accent focus:bg-card focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>

        <div>
          <label htmlFor="confirmPassword" className="block text-xs font-semibold uppercase tracking-wider text-mute">
            Confirm New Password
          </label>
          <input
            id="confirmPassword"
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="••••••••••••"
            className="mt-1.5 block w-full rounded-lg border border-line bg-soft/50 px-3.5 py-2.5 text-sm text-ink placeholder-faint focus:border-accent focus:bg-card focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </div>

        <button
          type="submit"
          disabled={loading || newPassword.length < 8}
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-bg transition-all hover:opacity-90 disabled:opacity-50"
        >
          <span>{loading ? "Updating..." : "Update Password"}</span>
          <ArrowRight className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <WarpedFloatBackground>
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <Link href="/" aria-label="Float Home">
            <Logo />
          </Link>
        </div>
        <h1 className="mt-6 text-center text-3xl font-serif font-normal tracking-tight text-ink">
          Set New Password
        </h1>
        <p className="mt-2 text-center text-sm text-mute">
          Enter and confirm your new secure account password.
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="rounded-2xl border border-line bg-card/95 backdrop-blur-md p-6 shadow-xl sm:p-8">
          <Suspense fallback={<div className="p-4 text-center text-xs text-mute">Loading form...</div>}>
            <ResetPasswordForm />
          </Suspense>
        </div>
      </div>
    </WarpedFloatBackground>
  );
}

"use client";

import { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, AlertCircle, ArrowRight, Mail } from "lucide-react";
import { Logo } from "@/components/Logo";
import { WarpedFloatBackground } from "@/components/WarpedFloatBackground";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [loading, setLoading] = useState(Boolean(token));
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resendSuccess, setResendSuccess] = useState(false);

  useEffect(() => {
    if (!token) return;

    async function verify() {
      try {
        const res = await fetch("/api/auth/verify-email/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token }),
        });

        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.error?.message || "Invalid or expired verification token.");
        }

        setSuccess(true);
      } catch (err: any) {
        setError(err.message || "Failed to verify email.");
      } finally {
        setLoading(false);
      }
    }

    verify();
  }, [token]);

  async function handleResend() {
    setError(null);
    try {
      const res = await fetch("/api/auth/verify-email/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Failed to send verification link.");
      }
      setResendSuccess(true);
    } catch (err: any) {
      setError(err.message || "Failed to request link.");
    }
  }

  return (
    <div className="rounded-2xl border border-line bg-card/95 backdrop-blur-md p-6 shadow-xl sm:p-8 text-center space-y-4">
      {loading ? (
        <div className="py-6 space-y-3">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          <p className="text-sm font-medium text-ink">Verifying your email address...</p>
        </div>
      ) : success ? (
        <div className="space-y-4">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600">
            <CheckCircle2 className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-semibold text-ink">Email Verified</h2>
          <p className="text-xs text-mute">
            Your email address has been successfully verified. You can now access all Float features.
          </p>
          <div className="pt-2">
            <Link
              href="/home"
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-ink text-bg px-5 py-2.5 text-xs font-semibold hover:opacity-90 transition-opacity"
            >
              <span>Continue to Float</span>
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      ) : error ? (
        <div className="space-y-4">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-50 dark:bg-red-950/30 text-red-600">
            <AlertCircle className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-semibold text-ink">Verification Failed</h2>
          <p className="text-xs text-red-700 dark:text-red-400">{error}</p>
          <div className="pt-2 flex flex-col gap-2">
            <button
              type="button"
              onClick={handleResend}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-soft text-ink px-4 py-2.5 text-xs font-semibold hover:bg-soft/80"
            >
              <Mail className="h-4 w-4" />
              <span>Resend Verification Link</span>
            </button>
            <Link href="/home" className="text-xs text-accent hover:underline pt-1">
              Return to dashboard
            </Link>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-accent/10 text-accent">
            <Mail className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-semibold text-ink">Verify Your Email</h2>
          <p className="text-xs text-mute">
            A confirmation email was sent to your registered email address. Click the link in the message to activate all capabilities.
          </p>
          {resendSuccess && (
            <div className="rounded-lg bg-emerald-50 dark:bg-emerald-950/30 p-2.5 text-xs text-emerald-800 dark:text-emerald-300">
              New verification email sent. Please check your inbox.
            </div>
          )}
          <div className="pt-2">
            <button
              type="button"
              onClick={handleResend}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-ink text-bg px-4 py-2.5 text-xs font-semibold hover:opacity-90"
            >
              <span>Send New Verification Link</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <WarpedFloatBackground>
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <Link href="/" aria-label="Float Home">
            <Logo />
          </Link>
        </div>
        <h1 className="mt-6 text-center text-3xl font-serif font-normal tracking-tight text-ink">
          Email Verification
        </h1>
        <p className="mt-2 text-center text-sm text-mute">
          Securing your Float account and verified contact channels.
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <Suspense fallback={<div className="p-6 text-center text-xs text-mute">Loading...</div>}>
          <VerifyEmailContent />
        </Suspense>
      </div>
    </WarpedFloatBackground>
  );
}

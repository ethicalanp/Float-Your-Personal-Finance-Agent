"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, AlertCircle, CheckCircle2 } from "lucide-react";
import { Logo } from "@/components/Logo";
import { WarpedFloatBackground } from "@/components/WarpedFloatBackground";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await fetch("/api/auth/password-reset/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Failed to submit request");
      }

      setSubmitted(true);
    } catch (err: any) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  }

  return (
    <WarpedFloatBackground>
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <Link href="/" aria-label="Float Home">
            <Logo />
          </Link>
        </div>
        <h1 className="mt-6 text-center text-3xl font-serif font-normal tracking-tight text-ink">
          Reset your password
        </h1>
        <p className="mt-2 text-center text-sm text-mute">
          Enter your registered email and we&apos;ll send instructions to reset your password.
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="rounded-2xl border border-line bg-card/95 backdrop-blur-md p-6 shadow-xl sm:p-8">
          {submitted ? (
            <div className="space-y-4 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 dark:bg-emerald-950/30 text-emerald-600">
                <CheckCircle2 className="h-6 w-6" />
              </div>
              <h2 className="text-base font-semibold text-ink">Check your email</h2>
              <p className="text-xs text-mute">
                If <span className="font-semibold text-ink">{email}</span> is registered with Float,
                a password reset link has been dispatched.
              </p>
              <div className="pt-4">
                <Link
                  href="/login"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-accent hover:underline"
                >
                  Return to sign in
                </Link>
              </div>
            </div>
          ) : (
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
                  <label htmlFor="email" className="block text-xs font-semibold uppercase tracking-wider text-mute">
                    Email Address
                  </label>
                  <input
                    id="email"
                    type="email"
                    required
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="priya@example.com"
                    className="mt-1.5 block w-full rounded-lg border border-line bg-soft/50 px-3.5 py-2.5 text-sm text-ink placeholder-faint focus:border-accent focus:bg-card focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                </div>

                <button
                  type="submit"
                  disabled={loading || !email}
                  className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-bg transition-all hover:opacity-90 disabled:opacity-50"
                >
                  <span>{loading ? "Sending..." : "Send Reset Link"}</span>
                  <ArrowRight className="h-4 w-4" />
                </button>

                <div className="pt-2 text-center text-xs text-mute">
                  Remember your password?{" "}
                  <Link href="/login" className="font-semibold text-accent hover:underline">
                    Sign in
                  </Link>
                </div>
              </form>
            </div>
          )}
        </div>
      </div>
    </WarpedFloatBackground>
  );
}

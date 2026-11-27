"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, AlertCircle, Phone, Mail, RotateCw } from "lucide-react";
import { Logo } from "@/components/Logo";
import { GoogleSignInButton } from "@/components/GoogleSignInButton";
import { WarpedFloatBackground } from "@/components/WarpedFloatBackground";

export default function SignupPage() {
  const router = useRouter();

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
  const [authMode, setAuthMode] = useState<"email" | "phone">("email");

  // Email form state
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [termsAccepted, setTermsAccepted] = useState(true);
  const [privacyAccepted, setPrivacyAccepted] = useState(true);
  const [aiConsent, setAiConsent] = useState(true);

  // Phone form state
  const [phone, setPhone] = useState("+91 ");
  const [otp, setOtp] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [otpMessage, setOtpMessage] = useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [attemptsRemaining, setAttemptsRemaining] = useState<number | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const isSubmitting = useRef(false);

  useEffect(() => {
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
        } else {
          setCapabilities({ google: false, phone: false, email: true });
        }
      } catch {
        setCapabilities({ google: false, phone: false, email: true });
      }
    }
    loadCapabilities();
  }, []);

  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  async function submitGoogleToken(idToken: string) {
    if (isSubmitting.current) return;
    isSubmitting.current = true;
    setError(null);
    setLoading(true);

    try {
      const res = await fetch("/api/auth/google", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: idToken }),
      });

      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const requestId = data?.error?.request_id || res.headers.get("x-request-id");
        const baseMsg = data?.error?.message || "Google sign-up was unsuccessful.";
        throw new Error(requestId ? `${baseMsg} (Request ID: ${requestId})` : baseMsg);
      }

      router.push("/home");
      router.refresh();
    } catch (err: any) {
      setError(err.message || "Failed to sign up with Google.");
    } finally {
      setLoading(false);
      isSubmitting.current = false;
    }
  }

  async function handleEmailSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!termsAccepted || !privacyAccepted) {
      setError("Please accept the Terms of Service and Privacy Policy to continue.");
      return;
    }
    if (isSubmitting.current) return;
    isSubmitting.current = true;
    setError(null);
    setLoading(true);

    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          full_name: fullName,
          email,
          password,
          terms_accepted: termsAccepted,
          privacy_accepted: privacyAccepted,
          ai_data_processing_consent: aiConsent,
          consent_version: "2026.1",
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Registration failed.");
      }

      router.push("/home");
      router.refresh();
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred.");
    } finally {
      setLoading(false);
      isSubmitting.current = false;
    }
  }

  async function handleRequestOtp(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!termsAccepted || !privacyAccepted) {
      setError("Please accept the Terms of Service and Privacy Policy to continue.");
      return;
    }
    if (isSubmitting.current || resendCooldown > 0) return;
    isSubmitting.current = true;
    setError(null);
    setLoading(true);

    try {
      const cleanPhone = phone.replace(/[\s-]/g, "");
      const res = await fetch("/api/auth/phone/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone_number: cleanPhone }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error?.message || "Failed to send OTP code.");
      }

      setOtpSent(true);
      setResendCooldown(data.cooldown_seconds || 30);
      setAttemptsRemaining(5);
      setOtpMessage(data.message || "A 6-digit OTP code has been sent to your phone.");
    } catch (err: any) {
      setError(err.message || "Failed to send OTP.");
    } finally {
      setLoading(false);
      isSubmitting.current = false;
    }
  }

  async function handleVerifyOtp(e: React.FormEvent) {
    e.preventDefault();
    if (isSubmitting.current) return;
    isSubmitting.current = true;
    setError(null);
    setLoading(true);

    try {
      const cleanPhone = phone.replace(/[\s-]/g, "");
      const res = await fetch("/api/auth/phone/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone_number: cleanPhone,
          otp,
          full_name: fullName || undefined,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        if (attemptsRemaining !== null && attemptsRemaining > 1) {
          setAttemptsRemaining((prev) => (prev ? prev - 1 : null));
        }
        throw new Error(data.error?.message || "Invalid or expired OTP code.");
      }

      router.push("/home");
      router.refresh();
    } catch (err: any) {
      setError(err.message || "Failed to verify OTP.");
    } finally {
      setLoading(false);
      isSubmitting.current = false;
    }
  }

  return (
    <WarpedFloatBackground>
      <main id="main-content" tabIndex={-1} className="outline-none">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <Link href="/" aria-label="Float Home">
            <Logo />
          </Link>
        </div>
        <h1 className="mt-6 text-center text-3xl font-serif font-normal tracking-tight text-ink">
          Create your Float account
        </h1>
        <p className="mt-2 text-center text-sm text-mute">
          India&apos;s intelligent personal finance, fraud protection and borrow planner.
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="rounded-2xl border border-line bg-card/95 backdrop-blur-md p-6 shadow-xl sm:p-8">
          {capabilities.google && (
            <div className="mb-6 flex flex-col items-center">
              <GoogleSignInButton
                clientId={capabilities.google_client_id}
                onCredential={submitGoogleToken}
                onError={setError}
                text="signup_with"
                disabled={loading || isSubmitting.current}
                dataTestId="google-signup-btn"
              />

              <div className="relative my-6 w-full flex items-center justify-center">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-line" />
                </div>
                <span className="relative bg-card px-3 text-xs uppercase tracking-wider text-mute">
                  or sign up with
                </span>
              </div>
            </div>
          )}

          {capabilities.phone && (
            <div data-testid="phone-auth-option" className="mb-6 flex rounded-xl bg-soft p-1">
              <button
                type="button"
                onClick={() => {
                  setAuthMode("email");
                  setError(null);
                }}
                className={`flex-1 flex items-center justify-center gap-2 rounded-lg py-2 text-xs font-semibold transition-all ${
                  authMode === "email" ? "bg-card text-ink shadow-sm" : "text-mute hover:text-ink"
                }`}
              >
                <Mail className="h-4 w-4" />
                <span>Email</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setAuthMode("phone");
                  setError(null);
                }}
                className={`flex-1 flex items-center justify-center gap-2 rounded-lg py-2 text-xs font-semibold transition-all ${
                  authMode === "phone" ? "bg-card text-ink shadow-sm" : "text-mute hover:text-ink"
                }`}
              >
                <Phone className="h-4 w-4" />
                <span>Phone OTP</span>
              </button>
            </div>
          )}

          {error && (
            <div
              role="alert"
              aria-live="polite"
              className="mb-6 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300"
            >
              <AlertCircle className="h-5 w-5 shrink-0 text-red-600 dark:text-red-400 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {otpMessage && authMode === "phone" && (
            <div
              role="status"
              aria-live="polite"
              className="mb-4 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 p-3 text-xs text-emerald-800 dark:text-emerald-300"
            >
              {otpMessage}
            </div>
          )}

          {/* Fallback for disabled JavaScript */}
          <noscript>
            <div className="mb-4 rounded-lg bg-amber-500/10 border border-amber-500/30 p-3 text-xs text-amber-800 dark:text-amber-200">
              JavaScript is required to sign up securely. Please enable JavaScript in your browser settings.
            </div>
          </noscript>

          {authMode === "email" || !capabilities.phone ? (
            <form method="post" action="#" className="space-y-4" onSubmit={handleEmailSubmit}>
              <div>
                <label htmlFor="fullName" className="block text-xs font-semibold uppercase tracking-wider text-mute">
                  Full Name
                </label>
                <input
                  id="fullName"
                  type="text"
                  required
                  autoComplete="name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Priya Sharma"
                  className="mt-1.5 block w-full rounded-lg border border-line bg-soft/50 px-3.5 py-2.5 text-sm text-ink placeholder-faint focus:border-accent focus:bg-card focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>

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

              <div>
                <label htmlFor="password" className="block text-xs font-semibold uppercase tracking-wider text-mute">
                  Password (min 8 characters)
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  minLength={8}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  className="mt-1.5 block w-full rounded-lg border border-line bg-soft/50 px-3.5 py-2.5 text-sm text-ink placeholder-faint focus:border-accent focus:bg-card focus:outline-none focus:ring-1 focus:ring-accent"
                />
              </div>

              <div className="space-y-3 pt-2">
                <label className="flex items-start gap-2.5 text-xs text-mute cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={termsAccepted && privacyAccepted}
                    onChange={(e) => {
                      setTermsAccepted(e.target.checked);
                      setPrivacyAccepted(e.target.checked);
                    }}
                    className="mt-0.5 rounded border-line text-accent focus:ring-accent"
                  />
                  <span>
                    I agree to the{" "}
                    <Link href="/terms" className="text-accent underline" target="_blank">
                      Terms of Service
                    </Link>{" "}
                    and{" "}
                    <Link href="/privacy" className="text-accent underline" target="_blank">
                      Privacy Policy
                    </Link>
                    .
                  </span>
                </label>

                <label className="flex items-start gap-2.5 text-xs text-mute cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={aiConsent}
                    onChange={(e) => setAiConsent(e.target.checked)}
                    className="mt-0.5 rounded border-line text-accent focus:ring-accent"
                  />
                  <span>
                    I consent to privacy-first AI financial insight generation under the DPDP Act.
                  </span>
                </label>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-bg transition-all hover:opacity-90 disabled:opacity-50"
              >
                <span>{loading ? "Creating account..." : "Create Account"}</span>
                <ArrowRight className="h-4 w-4" />
              </button>
            </form>
          ) : (
            <div data-testid="phone-signup-section" className="space-y-4">
              {!otpSent ? (
                <form method="post" action="#" onSubmit={handleRequestOtp} className="space-y-4">
                  <div>
                    <label htmlFor="phoneName" className="block text-xs font-semibold uppercase tracking-wider text-mute">
                      Full Name (Optional)
                    </label>
                    <input
                      id="phoneName"
                      type="text"
                      autoComplete="name"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="Priya Sharma"
                      className="mt-1.5 block w-full rounded-lg border border-line bg-soft/50 px-3.5 py-2.5 text-sm text-ink placeholder-faint focus:border-accent focus:bg-card focus:outline-none focus:ring-1 focus:ring-accent"
                    />
                  </div>

                  <div>
                    <label htmlFor="phone" className="block text-xs font-semibold uppercase tracking-wider text-mute">
                      Mobile Phone (+91 Indian numbers only)
                    </label>
                    <input
                      id="phone"
                      type="tel"
                      required
                      autoComplete="tel"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      placeholder="+91 98765 43210"
                      pattern="^\+?91[\s-]?[6-9]\d{9}$"
                      title="Please enter a valid 10-digit Indian mobile number starting with +91"
                      className="mt-1.5 block w-full rounded-lg border border-line bg-soft/50 px-3.5 py-2.5 text-sm text-ink placeholder-faint focus:border-accent focus:bg-card focus:outline-none focus:ring-1 focus:ring-accent font-mono"
                    />
                  </div>

                  <div className="space-y-3 pt-2">
                    <label className="flex items-start gap-2.5 text-xs text-mute cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={termsAccepted && privacyAccepted}
                        onChange={(e) => {
                          setTermsAccepted(e.target.checked);
                          setPrivacyAccepted(e.target.checked);
                        }}
                        className="mt-0.5 rounded border-line text-accent focus:ring-accent"
                      />
                      <span>
                        I agree to the{" "}
                        <Link href="/terms" className="text-accent underline" target="_blank">
                          Terms of Service
                        </Link>{" "}
                        and{" "}
                        <Link href="/privacy" className="text-accent underline" target="_blank">
                          Privacy Policy
                        </Link>
                        .
                      </span>
                    </label>
                  </div>

                  <button
                    type="submit"
                    disabled={loading || !phone}
                    className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-bg transition-all hover:opacity-90 disabled:opacity-50"
                  >
                    <span>{loading ? "Sending OTP..." : "Send OTP"}</span>
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </form>
              ) : (
                <form method="post" action="#" onSubmit={handleVerifyOtp} className="space-y-4">
                  <div>
                    <div className="flex items-center justify-between">
                      <label htmlFor="otp" className="block text-xs font-semibold uppercase tracking-wider text-mute">
                        6-Digit OTP Code
                      </label>
                      {attemptsRemaining !== null && (
                        <span className="text-xs text-mute font-medium">
                          {attemptsRemaining} {attemptsRemaining === 1 ? "attempt" : "attempts"} left
                        </span>
                      )}
                    </div>
                    <input
                      id="otp"
                      type="text"
                      maxLength={6}
                      required
                      autoComplete="one-time-code"
                      inputMode="numeric"
                      value={otp}
                      onChange={(e) => setOtp(e.target.value.replace(/\D/g, ""))}
                      placeholder="123456"
                      className="mt-1.5 block w-full rounded-lg border border-line bg-soft/50 px-3.5 py-2.5 text-sm text-center tracking-widest font-mono text-ink placeholder-faint focus:border-accent focus:bg-card focus:outline-none focus:ring-1 focus:ring-accent text-lg"
                    />
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <button
                      type="button"
                      onClick={() => handleRequestOtp()}
                      disabled={loading || resendCooldown > 0}
                      className="flex items-center gap-1.5 text-xs text-accent hover:underline disabled:text-mute disabled:no-underline"
                    >
                      <RotateCw className="h-3 w-3" />
                      <span>
                        {resendCooldown > 0 ? `Resend OTP in ${resendCooldown}s` : "Resend OTP"}
                      </span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setOtpSent(false);
                        setOtp("");
                        setError(null);
                      }}
                      className="text-xs text-mute hover:text-ink underline"
                    >
                      Change number
                    </button>
                  </div>

                  <button
                    type="submit"
                    disabled={loading || otp.length < 6}
                    className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-bg transition-all hover:opacity-90 disabled:opacity-50"
                  >
                    <span>{loading ? "Verifying..." : "Verify & Create Account"}</span>
                    <ArrowRight className="h-4 w-4" />
                  </button>
                </form>
              )}
            </div>
          )}

          <div className="mt-6 text-center text-xs text-mute">
            Already have an account?{" "}
            <Link href="/login" className="font-semibold text-accent hover:underline">
              Sign in
            </Link>
          </div>
        </div>
      </div>
      </main>
    </WarpedFloatBackground>
  );
}

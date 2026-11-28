"use client";

import { useState, useEffect, Suspense, useRef } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, AlertCircle, Phone, Mail, RotateCw, Eye, EyeOff } from "lucide-react";
import { Logo } from "@/components/Logo";
import { GoogleSignInButton } from "@/components/GoogleSignInButton";
import { WarpedFloatBackground } from "@/components/WarpedFloatBackground";

function sanitizeReturnTo(url: string | null): string {
  if (!url) return "/home";
  // Safe relative paths only, no protocol-relative or absolute redirection
  if (url.startsWith("/") && !url.startsWith("//") && !url.includes("://")) {
    return url;
  }
  return "/home";
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const rawFrom = searchParams.get("from") || searchParams.get("return_to");
  const from = sanitizeReturnTo(rawFrom);

  const [capabilities, setCapabilities] = useState<{
    google: boolean;
    phone: boolean;
    email: boolean;
    google_client_id?: string | null;
  }>({
    google: false,
    phone: false,
    email: true,
    google_client_id: null,
  });
  const [authMode, setAuthMode] = useState<"email" | "phone">("email");

  // Email state
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  // Phone state
  const [phone, setPhone] = useState("+91 ");
  const [otp, setOtp] = useState("");
  const [otpSent, setOtpSent] = useState(false);
  const [otpMessage, setOtpMessage] = useState<string | null>(null);
  const [resendCooldown, setResendCooldown] = useState(0);
  const [retryAfterCountdown, setRetryAfterCountdown] = useState(0);
  const [attemptsRemaining, setAttemptsRemaining] = useState<number | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const isSubmitting = useRef(false);

  // Load capabilities
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
          setCapabilities({ google: false, phone: false, email: true, google_client_id: null });
        }
      } catch {
        setCapabilities({ google: false, phone: false, email: true, google_client_id: null });
      }
    }
    loadCapabilities();
  }, []);

  // Cooldown timers
  useEffect(() => {
    if (resendCooldown <= 0) return;
    const timer = setInterval(() => {
      setResendCooldown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [resendCooldown]);

  useEffect(() => {
    if (retryAfterCountdown <= 0) return;
    const timer = setInterval(() => {
      setRetryAfterCountdown((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(timer);
  }, [retryAfterCountdown]);

  // Submit verified Google credential token to BFF
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
        const msg = data?.error?.message || "Google sign-in was unsuccessful. Please try again.";
        throw new Error(requestId ? `${msg} (Request ID: ${requestId})` : msg);
      }

      router.push(from);
      router.refresh();
    } catch (err: any) {
      setError(err.message || "Failed to sign in with Google.");
    } finally {
      setLoading(false);
      isSubmitting.current = false;
    }
  }

  // Email login submit
  async function handleEmailSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (isSubmitting.current) return;
    isSubmitting.current = true;
    setError(null);
    setLoading(true);

    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const requestId = data?.error?.request_id || res.headers.get("x-request-id");
        if (res.status === 429) {
          const retrySec = Number(res.headers.get("Retry-After")) || 30;
          setRetryAfterCountdown(retrySec);
          throw new Error(
            `Too many attempts. Please wait ${retrySec} seconds.${requestId ? ` (Request ID: ${requestId})` : ""}`
          );
        }
        const baseMsg =
          data?.error?.message ||
          (res.status === 401
            ? "Invalid email or password."
            : res.status === 403
            ? "Account locked or unverified."
            : "Login failed. Please try again.");
        throw new Error(requestId ? `${baseMsg} (Request ID: ${requestId})` : baseMsg);
      }

      router.push(from);
      router.refresh();
    } catch (err: any) {
      setError(err.message || "An unexpected network error occurred.");
    } finally {
      setLoading(false);
      isSubmitting.current = false;
    }
  }

  // Request phone OTP
  async function handleRequestOtp(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (isSubmitting.current || resendCooldown > 0 || retryAfterCountdown > 0) return;
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

      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const requestId = data?.error?.request_id || res.headers.get("x-request-id");
        if (res.status === 429) {
          const retrySec = Number(res.headers.get("Retry-After")) || 45;
          setRetryAfterCountdown(retrySec);
          throw new Error(
            `Too many OTP requests. Please wait ${retrySec} seconds.${requestId ? ` (Request ID: ${requestId})` : ""}`
          );
        }
        const msg = data?.error?.message || "Failed to send OTP code.";
        throw new Error(requestId ? `${msg} (Request ID: ${requestId})` : msg);
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

  // Verify phone OTP
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
        body: JSON.stringify({ phone_number: cleanPhone, otp }),
      });

      const data = await res.json().catch(() => null);
      if (!res.ok) {
        const requestId = data?.error?.request_id || res.headers.get("x-request-id");
        if (attemptsRemaining !== null && attemptsRemaining > 1) {
          setAttemptsRemaining((prev) => (prev ? prev - 1 : null));
        }
        const msg = data?.error?.message || "Invalid or expired OTP code.";
        throw new Error(requestId ? `${msg} (Request ID: ${requestId})` : msg);
      }

      router.push(from);
      router.refresh();
    } catch (err: any) {
      setError(err.message || "Failed to verify OTP.");
    } finally {
      setLoading(false);
      isSubmitting.current = false;
    }
  }

  return (
    <div className="rounded-2xl border border-line bg-card/95 backdrop-blur-md p-6 shadow-xl sm:p-8">
      {/* Google Sign-In button (Rendered if capabilities.google is true) */}
      {capabilities.google && (
        <div className="mb-6 flex flex-col items-center">
          <GoogleSignInButton
            clientId={capabilities.google_client_id}
            onCredential={submitGoogleToken}
            onError={setError}
            text="continue_with"
            disabled={loading || isSubmitting.current}
            dataTestId="google-login-btn"
          />

          <div className="relative my-6 w-full flex items-center justify-center">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-line" />
            </div>
            <span className="relative bg-card px-3 text-xs uppercase tracking-wider text-mute">
              or continue with
            </span>
          </div>
        </div>
      )}

      {/* Capability-based method selection (Email vs Phone) */}
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

      {/* Error alert with retry countdown */}
      {error && (
        <div
          role="alert"
          aria-live="polite"
          className="mb-6 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300"
        >
          <AlertCircle className="h-5 w-5 shrink-0 text-red-600 dark:text-red-400 mt-0.5" />
          <div className="flex-1">
            <span>{error}</span>
            {retryAfterCountdown > 0 && (
              <span className="block mt-1 font-mono text-xs font-semibold">
                Retry in {retryAfterCountdown}s
              </span>
            )}
          </div>
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
          JavaScript is required to sign in securely. Please enable JavaScript in your browser settings.
        </div>
      </noscript>

      {/* Email + Password Flow */}
      {authMode === "email" || !capabilities.phone ? (
        <form method="post" action="#" className="space-y-4" onSubmit={handleEmailSubmit}>
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
            <div className="flex items-center justify-between">
              <label htmlFor="password" className="block text-xs font-semibold uppercase tracking-wider text-mute">
                Password
              </label>
              <Link
                href="/forgot-password"
                className="text-xs text-accent hover:underline focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
              >
                Forgot password?
              </Link>
            </div>
            <div className="relative mt-1.5">
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="block w-full rounded-lg border border-line bg-soft/50 px-3.5 py-2.5 pr-10 text-sm text-ink placeholder-faint focus:border-accent focus:bg-card focus:outline-none focus:ring-1 focus:ring-accent"
              />
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="absolute inset-y-0 right-0 flex items-center px-3 text-mute hover:text-ink focus:outline-none focus-visible:text-ink"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading || retryAfterCountdown > 0}
            className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 py-3 text-sm font-semibold text-bg transition-all hover:opacity-90 disabled:opacity-50"
          >
            <span>{loading ? "Signing in..." : "Sign In"}</span>
            <ArrowRight className="h-4 w-4" />
          </button>
        </form>
      ) : (
        /* Phone OTP Flow */
        <div data-testid="phone-login-section" className="space-y-4">
          {!otpSent ? (
            <form method="post" action="#" onSubmit={handleRequestOtp} className="space-y-4">
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

              <button
                type="submit"
                disabled={loading || !phone || retryAfterCountdown > 0}
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
                  disabled={loading || resendCooldown > 0 || retryAfterCountdown > 0}
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
                <span>{loading ? "Verifying..." : "Verify & Sign In"}</span>
                <ArrowRight className="h-4 w-4" />
              </button>
            </form>
          )}
        </div>
      )}

      <div className="mt-6 text-center text-xs text-mute">
        Don&apos;t have an account yet?{" "}
        <Link href="/signup" className="font-semibold text-accent hover:underline">
          Create an account
        </Link>
      </div>
    </div>
  );
}

export default function LoginPage() {
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
          Welcome back to Float
        </h1>
        <p className="mt-2 text-center text-sm text-mute">
          Sign in to access your financial plan, fraud protection, and borrow insights.
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <Suspense fallback={<div className="p-8 text-center text-xs text-mute">Loading login...</div>}>
          <LoginForm />
        </Suspense>
      </div>
      </main>
    </WarpedFloatBackground>
  );
}

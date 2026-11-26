import Link from "next/link";
import { Download, Smartphone, ShieldCheck, ArrowRight, ShieldAlert, KeyRound, Clock } from "lucide-react";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";

export default function DownloadPage() {
  const apkUrl = process.env.NEXT_PUBLIC_APK_URL || "";
  const appVersion = process.env.NEXT_PUBLIC_APP_VERSION || "0.1.0-alpha";
  const apkSha256 = process.env.NEXT_PUBLIC_APK_SHA256 || "";

  const isApkAvailable = Boolean(apkUrl && apkUrl.trim());

  return (
    <div className="min-h-screen bg-bg text-ink flex flex-col">
      <Navbar />

      <main className="flex-1 py-12 sm:py-16">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 space-y-12">
          {/* Header */}
          <div className="text-center space-y-3">
            <span className="cnl-kicker text-xs font-semibold text-accent uppercase tracking-wider">
              Float Mobile
            </span>
            <h1 className="text-4xl font-serif font-normal tracking-tight text-ink sm:text-5xl">
              Get Float on Your Phone
            </h1>
            <p className="text-sm text-mute max-w-xl mx-auto leading-relaxed">
              Real-time SMS scam detection, statement parsing, and emergency fraud recovery right in your pocket.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-start">
            {/* Android Card */}
            <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`flex h-12 w-12 items-center justify-center rounded-2xl ${
                    isApkAvailable
                      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400"
                      : "bg-soft text-mute"
                  }`}>
                    <Smartphone className="h-6 w-6" />
                  </div>
                  <div>
                    <h2 className="text-lg font-serif font-medium text-ink">Android (Direct APK)</h2>
                    <span className="text-xs text-mute">
                      {isApkAvailable ? `v${appVersion} • Android 9.0+` : "Android 9.0+"}
                    </span>
                  </div>
                </div>
                <span
                  data-testid="android-status-badge"
                  className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                    isApkAvailable
                      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300"
                      : "bg-soft text-faint"
                  }`}
                >
                  {isApkAvailable ? "AVAILABLE" : "COMING SOON"}
                </span>
              </div>

              {isApkAvailable ? (
                <>
                  {/* QR Code SVG */}
                  <div className="flex flex-col items-center justify-center rounded-2xl border border-line bg-soft/30 p-6 text-center space-y-2">
                    <div className="p-3 bg-white rounded-xl shadow-sm">
                      <svg className="h-32 w-32 text-black" viewBox="0 0 100 100" fill="currentColor">
                        <rect x="10" y="10" width="25" height="25" rx="3" />
                        <rect x="65" y="10" width="25" height="25" rx="3" />
                        <rect x="10" y="65" width="25" height="25" rx="3" />
                        <rect x="15" y="15" width="15" height="15" fill="white" />
                        <rect x="70" y="15" width="15" height="15" fill="white" />
                        <rect x="15" y="70" width="15" height="15" fill="white" />
                        <rect x="19" y="19" width="7" height="7" />
                        <rect x="74" y="19" width="7" height="7" />
                        <rect x="19" y="74" width="7" height="7" />
                        <rect x="42" y="15" width="16" height="6" />
                        <rect x="42" y="27" width="8" height="14" />
                        <rect x="56" y="32" width="6" height="18" />
                        <rect x="42" y="55" width="14" height="8" />
                        <rect x="65" y="55" width="25" height="8" />
                        <rect x="65" y="70" width="10" height="20" />
                        <rect x="80" y="80" width="10" height="10" />
                      </svg>
                    </div>
                    <span className="text-[11px] text-faint">Scan with phone camera to download APK</span>
                  </div>

                  {apkSha256 && (
                    <div className="rounded-xl border border-line bg-soft/30 p-3 space-y-1">
                      <div className="flex items-center gap-1.5 text-[10px] font-semibold text-mute uppercase tracking-wider">
                        <KeyRound className="h-3 w-3" />
                        <span>SHA-256 Checksum</span>
                      </div>
                      <p className="font-mono text-[10px] text-ink break-all select-all">
                        {apkSha256}
                      </p>
                    </div>
                  )}

                  <a
                    href={apkUrl}
                    download
                    data-testid="android-download-button"
                    className="flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 py-3 text-xs font-semibold text-bg hover:opacity-90 transition-all shadow-sm"
                  >
                    <Download className="h-4 w-4" />
                    <span>Download Android APK</span>
                  </a>

                  {/* Play Protect & Unknown Sources Guidance */}
                  <div className="space-y-3 text-xs text-mute border-t border-line pt-4">
                    <div className="flex items-start gap-2 text-ink">
                      <ShieldAlert className="h-4 w-4 text-accent shrink-0 mt-0.5" />
                      <span className="font-semibold text-[11px]">
                        Google Play Protect / Unknown Sources Guidance
                      </span>
                    </div>
                    <ul className="space-y-1.5 text-[11px] text-mute list-disc list-inside">
                      <li>
                        When prompted by your browser, tap <strong>Download anyway</strong>.
                      </li>
                      <li>
                        If Google Play Protect shows &quot;Blocked by Play Protect&quot;, tap{" "}
                        <strong>More details</strong> &rarr; <strong>Install anyway</strong>. Float is open-source and signed.
                      </li>
                      <li>
                        Grant SMS reading permission solely for offline on-device scam checking.
                      </li>
                    </ul>
                  </div>
                </>
              ) : (
                /* Disabled / Coming Soon State */
                <div className="space-y-6 text-center py-4">
                  <div className="rounded-2xl border border-dashed border-line bg-soft/20 p-8 space-y-3">
                    <Clock className="mx-auto h-10 w-10 text-mute/50" />
                    <h3 className="text-sm font-medium text-ink">Android APK Coming Soon</h3>
                    <p className="text-xs text-mute max-w-xs mx-auto leading-relaxed">
                      Our production APK build is currently undergoing final security checks. In the meantime, use Float Web on Chrome.
                    </p>
                  </div>

                  <button
                    disabled
                    data-testid="android-download-button"
                    className="flex w-full items-center justify-center gap-2 rounded-xl border border-line bg-soft/50 px-4 py-3 text-xs font-semibold text-faint cursor-not-allowed shadow-none"
                  >
                    <Download className="h-4 w-4" />
                    <span>APK Build In Progress</span>
                  </button>
                </div>
              )}
            </div>

            {/* iOS Card (Preserved Stub) */}
            <div className="rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-soft text-mute">
                    <Smartphone className="h-6 w-6" />
                  </div>
                  <div>
                    <h2 className="text-lg font-serif font-medium text-ink">Apple iOS (App Store)</h2>
                    <span className="text-xs text-mute">iPhone & iPad</span>
                  </div>
                </div>
                <span className="text-[10px] font-bold bg-soft text-faint px-2 py-0.5 rounded-full">
                  COMING SOON
                </span>
              </div>

              <div className="rounded-2xl border border-line bg-soft/30 p-8 text-center space-y-3">
                <ShieldCheck className="mx-auto h-12 w-12 text-mute/50" />
                <h3 className="text-sm font-medium text-ink">iOS App In Development</h3>
                <p className="text-xs text-mute leading-relaxed">
                  Our TestFlight beta and App Store release are currently undergoing review. In the meantime, Float Web is fully responsive on Safari iOS.
                </p>
              </div>

              <Link
                href="/home"
                className="flex w-full items-center justify-center gap-2 rounded-xl border border-line bg-soft/50 px-4 py-3 text-xs font-semibold text-ink hover:bg-soft transition-all"
              >
                <span>Use Responsive Web App</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}

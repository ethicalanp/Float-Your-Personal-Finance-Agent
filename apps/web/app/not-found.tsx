import Link from "next/link";
import { Search, Home, ArrowLeft } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-screen bg-bg text-ink flex items-center justify-center p-4">
      <div className="w-full max-w-md rounded-3xl border border-line bg-card p-6 sm:p-8 shadow-sm space-y-6 text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-soft text-mute">
          <Search className="h-7 w-7" />
        </div>

        <div className="space-y-2">
          <span className="cnl-kicker text-xs font-semibold text-accent uppercase tracking-wider">
            404 Error
          </span>
          <h1 className="text-3xl font-serif font-medium text-ink">Page Not Found</h1>
          <p className="text-xs text-mute leading-relaxed">
            The page you are looking for doesn&apos;t exist, has been removed, or is temporarily unavailable.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
          <Link
            href="/home"
            className="flex w-full items-center justify-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-xs font-semibold text-bg hover:opacity-90 transition-all shadow-sm"
          >
            <Home className="h-4 w-4" />
            <span>Go to Dashboard</span>
          </Link>

          <Link
            href="/"
            className="flex w-full items-center justify-center gap-2 rounded-xl border border-line bg-soft/40 px-4 py-2.5 text-xs font-semibold text-ink hover:bg-soft transition-all"
          >
            <ArrowLeft className="h-4 w-4" />
            <span>Landing Page</span>
          </Link>
        </div>
      </div>
    </div>
  );
}

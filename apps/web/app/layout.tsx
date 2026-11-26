import type { Metadata, Viewport } from "next";
import { landingContent } from "@/content/landing";
import OfflineBanner from "@/components/OfflineBanner";
import GetAppPrompt from "@/components/GetAppPrompt";
import "./globals.css";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export const metadata: Metadata = {
  title: landingContent.meta.title,
  description: landingContent.meta.description,
  keywords: [
    "personal finance India",
    "scam check",
    "fraud detection",
    "Malayalam scam detector",
    "Manglish SMS",
    "cash flow planner",
    "borrow readiness",
  ],
  authors: [{ name: "Float Technologies" }],
  openGraph: {
    title: landingContent.meta.title,
    description: landingContent.meta.description,
    type: "website",
    locale: "en_IN",
    siteName: "Float",
  },
  twitter: {
    card: "summary_large_image",
    title: landingContent.meta.title,
    description: landingContent.meta.description,
  },
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='14' fill='%23111211'/><circle cx='16' cy='16' r='6' fill='%23e4572e'/></svg>",
  },
};

const THEME_SCRIPT = `
(function() {
  try {
    var stored = localStorage.getItem('float_theme');
    var theme = stored || 'system';
    var isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.documentElement.setAttribute('data-scheme', isDark ? 'dark' : 'light');
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-screen bg-bg text-ink font-sans antialiased selection:bg-accent/20 selection:text-ink">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-4 focus:py-2 focus:text-white focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-white"
        >
          Skip to main content
        </a>
        <OfflineBanner />
        {children}
        <GetAppPrompt />
      </body>
    </html>
  );
}

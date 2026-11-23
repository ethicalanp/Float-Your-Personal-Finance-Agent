import type { Metadata, Viewport } from "next";
import { landingContent } from "@/content/landing";
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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-bg text-ink font-sans antialiased selection:bg-accent/20 selection:text-ink">
        {children}
      </body>
    </html>
  );
}

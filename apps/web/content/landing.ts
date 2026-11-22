export interface NavLink {
  label: string;
  href: string;
}

export interface PillarItem {
  id: "plan" | "protect" | "borrow";
  tag: string;
  title: string;
  subtitle: string;
  description: string;
  features: string[];
  mockData: {
    label: string;
    detail: string;
    badge?: string;
  }[];
}

export interface HowItWorksStep {
  step: string;
  title: string;
  description: string;
  actionNote: string;
}

export interface SecurityStatement {
  title: string;
  description: string;
}

export interface FaqItem {
  question: string;
  answer: string;
}

export interface FooterLink {
  label: string;
  href: string;
}

export interface LandingContent {
  meta: {
    title: string;
    description: string;
  };
  header: {
    navLinks: NavLink[];
    loginText: string;
    loginHref: string;
    signupText: string;
    signupHref: string;
  };
  hero: {
    kicker: string;
    headline: string;
    subheadline: string;
    primaryCta: {
      label: string;
      href: string;
    };
    secondaryCta: {
      label: string;
      href: string;
    };
    pillNote: string;
  };
  pillarsSection: {
    kicker: string;
    title: string;
    description: string;
    pillars: PillarItem[];
  };
  howItWorks: {
    kicker: string;
    title: string;
    description: string;
    steps: HowItWorksStep[];
  };
  liveDemo: {
    kicker: string;
    title: string;
    description: string;
    disclaimer: string;
    samplePrompts: {
      label: string;
      text: string;
    }[];
    inputPlaceholder: string;
    buttonText: string;
    loadingText: string;
    errorText: string;
    serviceUnavailableText: string;
  };
  security: {
    kicker: string;
    title: string;
    description: string;
    statements: SecurityStatement[];
  };
  faq: {
    kicker: string;
    title: string;
    description: string;
    items: FaqItem[];
  };
  finalCta: {
    kicker: string;
    title: string;
    description: string;
    ctaButton: {
      label: string;
      href: string;
    };
    secondaryButton: {
      label: string;
      href: string;
    };
  };
  footer: {
    brandTagline: string;
    legalDisclaimer: string;
    navColumns: {
      title: string;
      links: FooterLink[];
    }[];
    copyright: string;
  };
}

export const landingContent: LandingContent = {
  meta: {
    title: "Float — Plan, Protect, and Borrow Responsibly in India",
    description:
      "A calm personal finance agent helping people in India plan cash flow, verify scam messages in multiple languages, and understand borrowing readiness honestly.",
  },
  header: {
    navLinks: [
      { label: "Features", href: "#features" },
      { label: "How it works", href: "#how-it-works" },
      { label: "Live Check", href: "#live-check" },
      { label: "Security", href: "#security" },
      { label: "FAQ", href: "#faq" },
    ],
    loginText: "Log in",
    loginHref: "/login",
    signupText: "Sign up",
    signupHref: "/signup",
  },
  hero: {
    kicker: "Personal Finance in India",
    headline: "Plan your money.\nProtect from scams.\nBorrow responsibly.",
    subheadline:
      "Float helps people in India understand cash flow from statements or SMS, verify suspicious messages in English, Malayalam, and Manglish, and evaluate borrowing readiness with plain-language reasons.",
    primaryCta: {
      label: "Sign up",
      href: "/signup",
    },
    secondaryCta: {
      label: "Try the scam check",
      href: "#live-check",
    },
    pillNote: "No credit cards required · Transparent analysis",
  },
  pillarsSection: {
    kicker: "The Three Pillars",
    title: "Three essentials for financial peace of mind",
    description:
      "Every tool in Float is built around clarity and user control. No hidden scores, no predatory lending pushes, and no automated money movements.",
    pillars: [
      {
        id: "plan",
        tag: "01 / Cash Flow",
        title: "Plan",
        subtitle: "Clarity on where money goes every month",
        description:
          "Import your bank statements or transactional SMS to see real cash flow, categorize spending trends, and track recurring bills with zero guesswork.",
        features: [
          "Import bank statements (PDF, CSV) or transactional SMS records",
          "Automated monthly cash-flow summary and recurring payment tracker",
          "Plain breakdowns of discretionary expenses versus fixed liabilities",
        ],
        mockData: [
          { label: "Fixed Monthly Outflows", detail: "₹18,400", badge: "Tracked" },
          { label: "Upcoming Subscriptions", detail: "3 renewals due this week", badge: "Calm" },
          { label: "Estimated Savings Buffer", detail: "2.4 months expenses", badge: "Healthy" },
        ],
      },
      {
        id: "protect",
        tag: "02 / Scam Shield",
        title: "Protect",
        subtitle: "Immediate fraud defense in local languages",
        description:
          "Check suspicious SMS, WhatsApp, and Telegram messages in English, Malayalam, and Manglish. Get a first-hour recovery checklist, verified emergency contacts, and ready-to-file complaint drafts.",
        features: [
          "Instant heuristic risk classification (Safe, Suspicious, Dangerous)",
          "Support for regional vernacular scripts and transliterations (Manglish)",
          "First-hour action checklist and official cybercrime helpline details (1930 / cybercrime.gov.in)",
          "Pre-formatted complaint draft with exact transaction markers",
        ],
        mockData: [
          { label: "Analyzed SMS / Message", detail: "Kerala Electricity bill cancellation link", badge: "Dangerous" },
          { label: "Identified Risk", detail: "Urgency hook + Fake APK download APK", badge: "Critical" },
          { label: "Helpline Ready", detail: "National Cyber Crime 1930", badge: "Available" },
        ],
      },
      {
        id: "borrow",
        tag: "03 / Credit Health",
        title: "Borrow",
        subtitle: "Indicative readiness without high-pressure sales",
        description:
          "See an indicative borrowing readiness assessment with plain-language explanations. Understand your debt-to-income balance and timing before taking on new debt.",
        features: [
          "Transparent debt-to-income assessment based on your verified inflows",
          "Clear reasons explaining your current readiness status",
          "Zero third-party lead selling or sponsored credit card offers",
        ],
        mockData: [
          { label: "Indicative Status", detail: "Prudent to defer new credit", badge: "Indicative" },
          { label: "Key Factor", detail: "Recent salary delay & variable inflow", badge: "Transparent" },
          { label: "Suggested Focus", detail: "Build 30-day liquid reserve first", badge: "Honest" },
        ],
      },
    ],
  },
  howItWorks: {
    kicker: "Workflow",
    title: "How Float works",
    description:
      "Simple, honest steps designed to put you in complete command of your personal finances.",
    steps: [
      {
        step: "01",
        title: "Create account & give consent",
        description:
          "Sign up with your email and choose granular permissions for which data sources you want to analyze. Consent is always explicit and revocable.",
        actionNote: "Explicit opt-in required for every data source",
      },
      {
        step: "02",
        title: "Add your data safely",
        description:
          "Upload your bank statement files or paste transactional notification text. Sensitive identifiers such as account numbers are masked immediately.",
        actionNote: "End-to-end masking on ingestion",
      },
      {
        step: "03",
        title: "See insights and checks",
        description:
          "Explore your monthly net cash flow, run scam checks on suspicious messages, and review indicative borrowing readiness with clear reasons.",
        actionNote: "Instant plain-language explanations",
      },
      {
        step: "04",
        title: "Act on recommendations",
        description:
          "Take concrete steps: review unneeded subscriptions, block reported scam numbers, or use our first-hour recovery guide if money was sent.",
        actionNote: "Actionable checklists and complaint drafts",
      },
    ],
  },
  liveDemo: {
    kicker: "Live Protection Demo",
    title: "Try the scam check right now",
    description:
      "Paste any suspicious text message, WhatsApp forward, or payment request below. Our live API analyzes known urgency patterns, malicious links, APK downloads, and payment threats in English, Malayalam, and Manglish.",
    disclaimer:
      "This check runs anonymously against Float's live backend. Float does not store, share, or log your submitted message text.",
    samplePrompts: [
      {
        label: "Kerala Electricity (Manglish)",
        text: "Dear consumer, your electricity power will be disconnected tonight at 9:30 PM because previous month bill was not updated. Immediately call 9876543210 or install KSEB.apk",
      },
      {
        label: "UPI Cashback Fraud (English)",
        text: "Congratulations! You have won a scratch card reward of Rs. 4,999 on PhonePe. Click here to claim your direct bank transfer instantly: http://tinyurl.com/claim-reward-upi",
      },
      {
        label: "Normal Bank OTP (Safe)",
        text: "123456 is your OTP for transaction of INR 450.00 at Swiggy using HDFC Bank card ending 8812. Valid for 10 mins. Do not share OTP with anyone.",
      },
    ],
    inputPlaceholder:
      "Paste an SMS, WhatsApp message, or email here (e.g., 'Your electricity bill is pending, download app now')...",
    buttonText: "Check Message",
    loadingText: "Analyzing message indicators...",
    errorText: "Failed to connect to the scam check service. Please try again.",
    serviceUnavailableText:
      "The scam detection service is temporarily undergoing scheduled updates (503). Rule-based protection will resume shortly.",
  },
  security: {
    kicker: "Honest Security",
    title: "Security built on verified safeguards",
    description:
      "We avoid vague buzzwords. Here are the exact architectural rules we enforce across all Float data pipelines.",
    statements: [
      {
        title: "Masked Account Identifiers",
        description:
          "Account numbers, card numbers, and PII are masked at the parser layer before analysis or display.",
      },
      {
        title: "Explicit Consent Architecture",
        description:
          "No background scraping or automatic data syncing without your deliberate confirmation per session.",
      },
      {
        title: "Encrypted at Rest & in Transit",
        description:
          "Sensitive session tokens and stored credentials use standard cryptographic encryption (TLS in transit, AES-256 at rest).",
      },
      {
        title: "No Money Movement",
        description:
          "Float is purely an analytical assistant. We have no access to initiate payments, trigger debits, or move funds.",
      },
    ],
  },
  faq: {
    kicker: "Frequently Asked Questions",
    title: "Clear answers to essential questions",
    description:
      "Everything you need to know about what Float does — and what it deliberately does not do.",
    items: [
      {
        question: "Is Float a credit score or credit bureau?",
        answer:
          "No. Float is not a credit rating bureau (like CIBIL, Experian, or CRIF High Mark) and does not provide an official credit score. Our Borrow pillar offers indicative readiness feedback based solely on your own cash flow and debt obligations to help you make informed personal decisions.",
      },
      {
        question: "Does Float move my money or execute transactions?",
        answer:
          "No. Float never moves money, never initiates UPI transfers, and has no direct debit authority. It is strictly an analytical and advisory tool designed to provide you with visibility and fraud warnings.",
      },
      {
        question: "What data does Float use?",
        answer:
          "Float only processes the bank statements (PDF/CSV) or message texts you explicitly choose to upload or paste. We parse transaction dates, amounts, merchant descriptions, and fraud signals. We never ask for ATM PINs, net banking passwords, or OTPs.",
      },
      {
        question: "Can I delete my data?",
        answer:
          "Yes. You can delete your uploaded statements and account history at any time from your settings. When deleted, your records and parsed summaries are permanently purged from our primary database.",
      },
      {
        question: "Which languages are supported by the scam check?",
        answer:
          "Float currently evaluates messages in English, Malayalam script, and Manglish (Malayalam written in Latin script), covering the most prevalent regional online scam formats encountered across South India.",
      },
    ],
  },
  finalCta: {
    kicker: "Get Started",
    title: "Take control of your money with calm clarity.",
    description:
      "Join Float today to plan your monthly budget, protect yourself from sophisticated digital fraud, and evaluate borrowing options honestly.",
    ctaButton: {
      label: "Create your free account",
      href: "/signup",
    },
    secondaryButton: {
      label: "Try scam check live",
      href: "#live-check",
    },
  },
  footer: {
    brandTagline:
      "Honest financial planning, scam protection, and borrowing clarity for India.",
    legalDisclaimer:
      "Float provides indicative information only. It is not a credit score, financial advice or a lender's decision.",
    navColumns: [
      {
        title: "Product",
        links: [
          { label: "Plan", href: "#features" },
          { label: "Protect", href: "#live-check" },
          { label: "Borrow", href: "#features" },
          { label: "How it works", href: "#how-it-works" },
        ],
      },
      {
        title: "Trust & Safety",
        links: [
          { label: "Security Safeguards", href: "#security" },
          { label: "Helpline 1930", href: "https://cybercrime.gov.in" },
          { label: "Report Fraud", href: "#live-check" },
        ],
      },
      {
        title: "Legal",
        links: [
          { label: "Privacy Policy", href: "/privacy" },
          { label: "Terms of Service", href: "/terms" },
          { label: "Disclaimer", href: "#faq" },
        ],
      },
    ],
    copyright: "© 2026 Float Technologies. All rights reserved.",
  },
};

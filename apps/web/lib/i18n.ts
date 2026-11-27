export type Language = "en" | "ml" | "manglish";

export interface TranslationMetadata {
  language: Language;
  needsReview: boolean;
  verified: boolean;
}

export const I18N_METADATA: Record<Language, TranslationMetadata> = {
  en: {
    language: "en",
    needsReview: false,
    verified: true,
  },
  ml: {
    language: "ml",
    needsReview: true,
    verified: false, // Explicitly marked as not human-reviewed
  },
  manglish: {
    language: "manglish",
    needsReview: true,
    verified: false, // Explicitly marked as not human-reviewed
  },
};

export const DICTIONARY = {
  en: {
    nav: {
      home: "Home",
      protect: "Protect",
      borrow: "Borrow",
      assistant: "Float.ai",
      settings: "Settings",
      logout: "Log Out",
    },
    common: {
      loading: "Loading...",
      error: "Something went wrong",
      retry: "Retry",
      save: "Save",
      submit: "Submit",
      cancel: "Cancel",
      privacyMode: "Privacy Mode",
      disclaimerTitle: "Important Legal Notice",
      indicativeOnly: "Indicative readiness only. Not financial or legal advice.",
      helpline1930: "Call National Cybercrime Helpline 1930",
    },
    home: {
      title: "Plan & Cash Flow",
      subtitle: "Understand your income, spending, and monthly savings trajectory.",
      uploadStatement: "Upload Bank Statement",
      uploadHelp: "Upload monthly CSV statement (Max 10 MB). Processed strictly on device/backend.",
      dragDrop: "Drag & drop your statement CSV here, or click to browse",
      uploading: "Uploading and analyzing transactions...",
      inflow: "Total Inflow",
      outflow: "Total Outflow",
      netSavings: "Net Savings",
      topCategories: "Top Spending Categories",
      monthlyTrend: "Monthly Net Flow",
      emptyState: "No transaction data yet. Upload your first statement to generate insights.",
      duplicateWarning: "This statement has already been uploaded. Duplicate transactions were skipped.",
    },
    protect: {
      title: "Protect Against Fraud",
      subtitle: "Verify suspicious messages, track recovery, and access verified helpline contacts.",
      tabScamCheck: "Scam Checker",
      tabChecklist: "First-Hour Checklist",
      tabRecovery: "Recovery Cases",
      tabContacts: "Verified Contacts",
      pastePlaceholder: "Paste suspicious SMS, WhatsApp, or email message text here...",
      checkButton: "Analyze Message",
      emergencyNotice: "If you lost money in the last 2 hours, call 1930 immediately.",
    },
    borrow: {
      title: "Borrow Readiness",
      subtitle: "Indicative credit readiness based on historical cash-flow stability.",
      checkButton: "Assess My Readiness",
      disclaimer: "Indicative readiness only. Float is not a lender or credit rating agency.",
    },
    assistant: {
      title: "Float.ai",
      subtitle: "Ask questions regarding banking rules, fraud protections, and cash flow.",
      placeholder: "Ask Float.ai about cyber fraud, 1930 helpline, or cash flow...",
      send: "Send",
      consentNotice: "AI data processing consent is required before using Float.ai.",
      citations: "Official Regulatory Sources",
    },
    settings: {
      title: "Settings & Privacy",
      subtitle: "Manage your authentication credentials, active sessions, and DPDP consent preferences.",
      signinMethods: "Sign-in Methods",
      activeSessions: "Active Sessions",
      consentPreferences: "Consent Preferences",
    },
    plan: {
      title: "Monthly Budget Plan",
      subtitle: "Allocate your monthly take-home income across Needs, Wants, and Savings (educational only).",
      savePlan: "Save Budget Plan",
      resetDefault: "Reset to 50/30/20",
      unallocated: "Unallocated",
      disclaimer: "Educational budgeting tool only — not investment advice.",
      tabsLabel: "Plan sections",
      budgetTab: "Budget",
      recurringTab: "Recurring & bills",
      dueSoonTitle: "Due soon",
      noDueSoon: "No bills due in the next 7 days.",
      candidatesTitle: "Recurring candidates",
      reviewCandidates: "Review candidates",
      viewRecurring: "View Recurring & bills",
    },
    recurring: {
      title: "Recurring Payments & Bills",
      subtitle: "Track rent, EMIs, SIPs, and subscriptions with deterministic due-soon reminders.",
      addCommitment: "Add Recurring Payment",
      dueSoon: "Due Soon & Overdue",
      candidatesInbox: "Detected Candidates",
    },
    profile: {
      title: "Your Profile",
      subtitle: "Manage your display name, language, theme, and DPDP data rights.",
      displayName: "Display Name",
      language: "Preferred Language",
      theme: "Theme Preference",
      downloadData: "Download My Data",
      deleteAccount: "Delete Account",
      graceNotice: "Account deletion scheduled",
    },
  },
  ml: {
    nav: {
      home: "ഹോം",
      protect: "സുരക്ഷ",
      borrow: "വായ്പ തയ്യാറെടുപ്പ്",
      assistant: "അസിസ്റ്റന്റ്",
      settings: "സെറ്റിംഗ്സ്",
      logout: "ലോഗ് ഔട്ട്",
    },
    common: {
      loading: "ലോഡ് ചെയ്യുന്നു...",
      error: "എന്തോ തകരാർ സംഭവിച്ചു",
      retry: "വീണ്ടും ശ്രമിക്കുക",
      save: "സേവ് ചെയ്യുക",
      submit: "സമർപ്പിക്കുക",
      cancel: "റദ്ദാക്കുക",
      privacyMode: "സ്വകാര്യതാ മോഡ്",
      disclaimerTitle: "പ്രധാനപ്പെട്ട അറിയിപ്പ്",
      indicativeOnly: "സൂചക തയ്യാറെടുപ്പ് മാത്രം. സാമ്പത്തിക ഉപദേശമല്ല.",
      helpline1930: "ദേശീയ സൈബർ ഹെൽപ്പ്‌ലൈൻ 1930 വിളിക്കുക",
    },
    home: {
      title: "പ്ലാൻ & പണമിടപാടുകൾ",
      subtitle: "നിങ്ങളുടെ വരുമാനം, ചെലവ്, മാസ സമ്പാദ്യം എന്നിവ മനസ്സിലാക്കുക.",
      uploadStatement: "ബാങ്ക് സ്റ്റേറ്റ്‌മെന്റ് അപ്‌ലോഡ് ചെയ്യുക",
      uploadHelp: "CSV സ്റ്റേറ്റ്‌മെന്റ് അപ്‌ലോഡ് ചെയ്യുക (പരമാവധി 10 MB).",
      dragDrop: "CSV ഫയൽ ഇവിടെ ഇടുക അല്ലെങ്കിൽ തിരഞ്ഞെടുക്കുക",
      uploading: "അപ്‌ലോഡ് ചെയ്തു പരിശോധിക്കുന്നു...",
      inflow: "ആകെ വരുമാനം",
      outflow: "ആകെ ചെലവ്",
      netSavings: "മാസ സമ്പാദ്യം",
      topCategories: "പ്രധാന ചെലവുകൾ",
      monthlyTrend: "പ്രതിമാസ മാറ്റങ്ങൾ",
      emptyState: "ഇടപാടുകൾ ലഭ്യമല്ല. വിശകലനത്തിനായി സ്റ്റേറ്റ്‌മെന്റ് അപ്‌ലോഡ് ചെയ്യുക.",
      duplicateWarning: "ഈ സ്റ്റേറ്റ്‌മെന്റ് ഇതിനകം അപ്‌ലോഡ് ചെയ്തതാണ്. ആവർത്തിച്ച ഇടപാടുകൾ ഒഴിവാക്കി.",
    },
    protect: {
      title: "തട്ടിപ്പുകളിൽ നിന്ന് സുരക്ഷ",
      subtitle: "സംശയാസ്പദമായ സന്ദേശങ്ങൾ പരിശോധിക്കുക, ഹെൽപ്പ്‌ലൈൻ നമ്പറുകൾ കണ്ടെത്തുക.",
      tabScamCheck: "തട്ടിപ്പ് പരിശോധന",
      tabChecklist: "ആദ്യ മണിക്കൂർ ചെക്ക്‌ലിസ്റ്റ്",
      tabRecovery: "പരാതികൾ",
      tabContacts: "പരിശോധിച്ച നമ്പറുകൾ",
      pastePlaceholder: "സംശയാസ്പദമായ സന്ദേശം ഇവിടെ പേസ്റ്റ് ചെയ്യുക...",
      checkButton: "പരിശോധിക്കുക",
      emergencyNotice: "കഴിഞ്ഞ 2 മണിക്കൂറിനുള്ളിൽ പണം നഷ്ടപ്പെട്ടെങ്കിൽ ഉടൻ 1930 വിളിക്കുക.",
    },
    borrow: {
      title: "വായ്പ തയ്യാറെടുപ്പ്",
      subtitle: "പണമിടപാടുകളുടെ സ്ഥിരത അടിസ്ഥാനമാക്കിയുള്ള തയ്യാറെടുപ്പ്.",
      checkButton: "പരിശോധിക്കുക",
      disclaimer: "സൂചക തയ്യാറെടുപ്പ് മാത്രം. ഫ്ലോട്ട് വായ്പ നൽകുന്ന സ്ഥാപനമല്ല.",
    },
    assistant: {
      title: "Float.ai",
      subtitle: "ബാങ്കിംഗ് നിയമങ്ങൾ, സൈബർ സുരക്ഷ എന്നിവയെക്കുറിച്ച് ചോദിക്കുക.",
      placeholder: "Float.ai-യോട് സൈബർ തട്ടിപ്പ്, 1930 ഹെൽപ്പ്‌ലൈൻ എന്നിവയെക്കുറിച്ച് ചോദിക്കുക...",
      send: "അയക്കുക",
      consentNotice: "Float.ai ഉപയോഗിക്കാൻ AI ഡാറ്റാ അനുമതി ആവശ്യമാണ്.",
      citations: "ഔദ്യോഗിക ഉറവിടങ്ങൾ",
    },
    settings: {
      title: "സെറ്റിംഗ്സ് & സ്വകാര്യത",
      subtitle: "ലോഗിൻ രീതികളും അനുമതികളും പരിശോധിക്കുക.",
      signinMethods: "ലോഗിൻ രീതികൾ",
      activeSessions: "സജീവ സെഷനുകൾ",
      consentPreferences: "അനുമതി മുൻഗണനകൾ",
    },
    // needsReview
    plan: {
      title: "പ്രതിമാസ ബജറ്റ് പ്ലാൻ",
      subtitle: "വരുമാനം ആവശ്യങ്ങൾ, ആഗ്രഹങ്ങൾ, സമ്പാദ്യം എന്നിവയിലേക്ക് വീതിക്കുക (പഠനത്തിന് മാത്രം).",
      savePlan: "ബജറ്റ് സേവ് ചെയ്യുക",
      resetDefault: "50/30/20-ലേക്ക് മാറ്റുക",
      unallocated: "ബാക്കിയുള്ളത്",
      disclaimer: "പഠന ആവശ്യങ്ങൾക്ക് മാത്രം — നിക്ഷേപ ഉപദേശമല്ല.",
      tabsLabel: "പ്ലാൻ വിഭാഗങ്ങൾ", // needsReview
      budgetTab: "ബജറ്റ്", // needsReview
      recurringTab: "ആവർത്തിച്ചുള്ള പേയ്‌മെന്റുകൾ", // needsReview
      dueSoonTitle: "ഉടൻ വരുന്നത്", // needsReview
      noDueSoon: "അടുത്ത 7 ദിവസത്തിനുള്ളിൽ ബില്ലുകളൊന്നുമില്ല.", // needsReview
      candidatesTitle: "കണ്ടെത്തിയ ആവർത്തിച്ചുള്ള പേയ്‌മെന്റുകൾ", // needsReview
      reviewCandidates: "പരിശോധിക്കുക", // needsReview
      viewRecurring: "ആവർത്തിച്ചുള്ള പേയ്‌മെന്റുകൾ കാണുക", // needsReview
    },
    // needsReview
    recurring: {
      title: "ആവർത്തിച്ചുള്ള പേയ്‌മെന്റുകൾ",
      subtitle: "വാടക, ഇഎംഐ, എസ്ഐപി, സബ്സ്ക്രിപ്ഷനുകൾ എന്നിവ ട്രാക്ക് ചെയ്യുക.",
      addCommitment: "പുതിയ പേയ്‌മെന്റ് ചേർക്കുക",
      dueSoon: "ഉടൻ വരുന്നത്",
      candidatesInbox: "കണ്ടെത്തിയ പേയ്‌മെന്റുകൾ",
    },
    profile: {
      title: "നിങ്ങളുടെ പ്രൊഫൈൽ", // needsReview
      subtitle: "പേര്, ഭാഷ, തീം, DPDP ഡാറ്റ അവകാശങ്ങൾ എന്നിവ നിയന്ത്രിക്കുക.",
      displayName: "പ്രദർശന നാമം",
      language: "ഭാഷാ മുൻഗണന",
      theme: "തീം മുൻഗണന",
      downloadData: "എന്റെ ഡാറ്റ ഡൗൺലോഡ് ചെയ്യുക",
      deleteAccount: "അക്കൗണ്ട് ഇല്ലാതാക്കുക",
      graceNotice: "അക്കൗണ്ട് ഇല്ലാതാക്കൽ ഷെഡ്യൂൾ ചെയ്തു",
    },
  },
  manglish: {
    nav: {
      home: "Home",
      protect: "Protect Cheyyuka",
      borrow: "Loan Readiness",
      assistant: "Float.ai",
      settings: "Settings",
      logout: "Log Out",
    },
    common: {
      loading: "Loading aakunnu...",
      error: "Enthekilum kuzhappam undayi",
      retry: "Veendum try cheyyuka",
      save: "Save Cheyyuka",
      submit: "Submit Cheyyuka",
      cancel: "Cancel",
      privacyMode: "Privacy Mode",
      disclaimerTitle: "Pradhana Notice",
      indicativeOnly: "Indicative readiness mathram. Financial advice alla.",
      helpline1930: "National Cyber Helpline 1930 vilikkuka",
    },
    home: {
      title: "Plan & Cash Flow",
      subtitle: "Ningalude income, spending, monthly savings manassilaakkuka.",
      uploadStatement: "Bank Statement Upload Cheyyuka",
      uploadHelp: "CSV statement upload cheyyuka (Max 10 MB).",
      dragDrop: "CSV file ivide drop cheyyuka, or click cheythu browse cheyyuka",
      uploading: "Upload cheythu analyze cheyyunnu...",
      inflow: "Total Inflow",
      outflow: "Total Outflow",
      netSavings: "Net Savings",
      topCategories: "Top Categories",
      monthlyTrend: "Monthly Trend",
      emptyState: "Transactions onnum illa. Statement upload cheyyuka.",
      duplicateWarning: "Ee statement munpe upload cheythathaanu. Duplicates skip cheythu.",
    },
    protect: {
      title: "Scams ninnu Protect Cheyyuka",
      subtitle: "Suspicious messages check cheyyuka, helpline contacts kandethuka.",
      tabScamCheck: "Scam Check",
      tabChecklist: "First-Hour Checklist",
      tabRecovery: "Recovery Cases",
      tabContacts: "Verified Contacts",
      pastePlaceholder: "Suspicious message ivide paste cheyyuka...",
      checkButton: "Analyze Cheyyuka",
      emergencyNotice: "Last 2 hours-il panam nashtappettengil udan 1930 vilikkuka.",
    },
    borrow: {
      title: "Loan Readiness",
      subtitle: "Cash-flow stability vechu readiness check cheyyuka.",
      checkButton: "Readiness Check Cheyyuka",
      disclaimer: "Indicative readiness mathram. Float lender alla.",
    },
    assistant: {
      title: "Float.ai",
      subtitle: "Banking rules, cyber protection kurichu chodikkuka.",
      placeholder: "Float.ai-yodu cyber fraud, 1930 helpline kurichu chodikkuka...",
      send: "Send",
      consentNotice: "Float.ai use cheyyan AI consent aavashyamaanu.",
      citations: "Official Sources",
    },
    settings: {
      title: "Settings & Privacy",
      subtitle: "Login credentials, active sessions, consent preferences manage cheyyuka.",
      signinMethods: "Sign-in Methods",
      activeSessions: "Active Sessions",
      consentPreferences: "Consent Preferences",
    },
    // needsReview
    plan: {
      title: "Monthly Budget Plan",
      subtitle: "Monthly income Needs, Wants, Savings aayi split cheyyuka (educational mathram).",
      savePlan: "Budget Plan Save Cheyyuka",
      resetDefault: "50/30/20 Reset",
      unallocated: "Unallocated",
      disclaimer: "Educational planning tool mathram — investment advice alla.",
      tabsLabel: "Plan sections", // needsReview
      budgetTab: "Budget", // needsReview
      recurringTab: "Recurring & bills", // needsReview
      dueSoonTitle: "Due soon", // needsReview
      noDueSoon: "Adutha 7 divasathil bills onnumilla.", // needsReview
      candidatesTitle: "Recurring candidates", // needsReview
      reviewCandidates: "Review candidates", // needsReview
      viewRecurring: "Recurring & bills nokkuka", // needsReview
    },
    // needsReview
    recurring: {
      title: "Recurring Payments & Bills",
      subtitle: "Rent, EMI, SIP, subscriptions reminders track cheyyuka.",
      addCommitment: "Recurring Payment Add Cheyyuka",
      dueSoon: "Due Soon & Overdue",
      candidatesInbox: "Detected Candidates",
    },
    profile: {
      title: "Ningalude Profile", // needsReview
      subtitle: "Display name, language, theme, DPDP data rights manage cheyyuka.",
      displayName: "Display Name",
      language: "Preferred Language",
      theme: "Theme Preference",
      downloadData: "Ente Data Download Cheyyuka",
      deleteAccount: "Account Delete Cheyyuka",
      graceNotice: "Account deletion schedule cheythu",
    },
  },
} as const;

export function getActiveLanguage(): Language {
  if (typeof window === "undefined") return "en";
  const stored = localStorage.getItem("float_lang") as Language;
  if (stored && (stored === "en" || stored === "ml" || stored === "manglish")) {
    return stored;
  }
  return "en";
}

export function setActiveLanguage(lang: Language): void {
  if (typeof window !== "undefined") {
    localStorage.setItem("float_lang", lang);
  }
}

/**
 * Returns translated string dictionary for selected language, falling back to English.
 */
export function getTranslation(lang: Language = "en") {
  const dict = DICTIONARY[lang];
  if (!dict) return DICTIONARY.en;
  return dict;
}

/**
 * Currency formatter with Indian numbering (Lakh/Crore) and privacy masking.
 */
export function formatINR(
  amount: number,
  options?: { hideAmount?: boolean; compact?: boolean }
): string {
  if (options?.hideAmount) {
    return "₹ ••••••";
  }

  const abs = Math.abs(amount);
  const sign = amount < 0 ? "-" : "";

  if (options?.compact) {
    if (abs >= 10000000) {
      return `${sign}₹ ${(abs / 10000000).toFixed(2)} Cr`;
    }
    if (abs >= 100000) {
      return `${sign}₹ ${(abs / 100000).toFixed(2)} L`;
    }
  }

  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2,
  }).format(amount);
}

/**
 * Formats dates strictly in Indian Standard Time (IST - Asia/Kolkata).
 */
export function formatISTDate(
  date: Date | string | number,
  formatStyle: "short" | "medium" | "full" = "medium"
): string {
  const d = typeof date === "string" || typeof date === "number" ? new Date(date) : date;
  if (isNaN(d.getTime())) return "Invalid Date";

  const optionsMap: Record<string, Intl.DateTimeFormatOptions> = {
    short: { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "Asia/Kolkata" },
    medium: { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" },
    full: {
      day: "numeric",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Kolkata",
      timeZoneName: "short",
    },
  };

  return new Intl.DateTimeFormat("en-IN", optionsMap[formatStyle]).format(d);
}

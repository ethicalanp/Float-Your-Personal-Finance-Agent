import re
from typing import Any

# Malayalam Unicode range: \u0D00-\u0D7F
MALAYALAM_UNICODE_PATTERN = re.compile(r'[\u0D00-\u0D7F]')

MANGLISH_MARKERS = [
    "cheyyuka", "cheyyu", "cheyyanam", "kittum", "kittiyirikkunnu", "adakkuka",
    "adakkillel", "aayi", "aano", "panam", "linkil", "vannu", "ivide", "entha",
    "koodi", "aakanam", "njangal", "ningal", "nalkuka", "ayakkuka", "poya", "undakum",
]

# Indicator categories with weighted score
INDICATORS: dict[str, dict[str, Any]] = {
    "urgency": {
        "weight": 25,
        "en": [
            "immediately", "urgent", "urgently", "within 24 hours", "within 2 hours",
            "account blocked", "account will be blocked", "electricity disconnected tonight",
            "power cut tonight", "last warning", "final notice", "suspended", "deactivated",
            "action required now", "legal action", "arrest warrant",
        ],
        "ml": [
            "ഉടൻ തന്നെ", "അടിയന്തിരമായി", "അക്കൗണ്ട് ബ്ലോക്ക് ചെയ്യപ്പെടും", "ഇന്നു രാത്രി വൈദ്യുതി വിച്ഛേദിക്കും",
            "അവസാന മുന്നറിയിപ്പ്", "സസ്പെൻഡ് ചെയ്യും", "നിയമനടപടി",
        ],
        "manglish": [
            "urgent aayi", "udan thanne", "account block aayi", "block aakum", "cut aakum",
            "electricity cut aakum", "last warning", "case aakum", "police pidikkum",
        ],
        "explanation": "High urgency language pressurizing immediate action without giving time to verify.",
    },
    "credential_harvesting": {
        "weight": 35,
        "en": [
            "share otp", "share your otp", "send otp", "enter pin", "share pin", "enter password",
            "verify kyc", "update kyc", "complete kyc", "update pan", "verify pan",
            "aadhaar link", "click here to verify", "update your details",
        ],
        "ml": [
            "ഒടിപി അയക്കുക", "പിൻ നൽകുക", "കെവൈസി അപ്ഡേറ്റ്", "പാൻ കാർഡ് ലിങ്ക് ചെയ്യുക",
            "ലിങ്കിൽ ക്ലിക്ക് ചെയ്യുക", "വിവരങ്ങൾ നൽകുക",
        ],
        "manglish": [
            "otp share cheyyu", "otp ayakkuka", "pin parayuka", "kyc update cheyyu",
            "linkil click cheyyu", "pan link cheyyuka",
        ],
        "explanation": (
            "Demands for confidential credentials (OTP, PIN, KYC/PAN details). "
            "Legitimate institutions never ask for these via chat/SMS."
        ),
    },
    "dangerous_actions": {
        "weight": 30,
        "en": [
            "install apk", "download apk", "download app", "install anydesk",
            "install quicksupport", "install teamviewer", "install rustdesk",
            "transfer to secure account", "pay penalty fee",
        ],
        "ml": [
            "എപികെ ഇൻസ്റ്റാൾ ചെയ്യുക", "ആപ്പ് ഡൗൺലോഡ് ചെയ്യുക", "സുരക്ഷിത അക്കൗണ്ടിലേക്ക് മാറ്റുക",
        ],
        "manglish": [
            "apk install cheyyu", "app download cheyyuka", "anydesk install cheyyu", "panam transfer cheyyu",
        ],
        "explanation": (
            "Request to download unverified third-party APKs or screen-sharing tools "
            "that grant attackers full remote access."
        ),
    },
    "lottery_reward": {
        "weight": 20,
        "en": [
            "you have won", "lottery winner", "congratulations you won", "cash prize",
            "claim reward", "claim cashback", "free gift", "kbc lottery",
        ],
        "ml": [
            "സമ്മാനം ലഭിച്ചു", "ലോട്ടറി അടിച്ചു", "ക്യാഷ്ബാക്ക് ക്ലെയിം ചെയ്യുക", "സൗജന്യ സമ്മാനം",
        ],
        "manglish": [
            "lottery adichu", "prize kittiyirikkunnu", "cashback claim cheyyu", "gift kittum",
        ],
        "explanation": "Unsolicited reward/lottery claim bait, commonly used in advance-fee fraud.",
    },
    "impersonation": {
        "weight": 15,
        "en": [
            "sbi alert", "hdfc bank alert", "icici bank", "axis bank", "trai",
            "telecom department", "cbi", "mumbai police", "cyber cell", "fedex parcel",
            "customs clearance", "eb bill department",
        ],
        "ml": [
            "എസ്ബിഐ", "ബാങ്ക് അറിയിപ്പ്", "പോലീസ് അറിയിപ്പ്", "വൈദ്യുതി ബോർഡ്", "പാഴ്സൽ കസ്റ്റംസ്",
        ],
        "manglish": [
            "sbi alert", "bankil ninnu", "police alert", "eb department", "fedex parcel",
        ],
        "explanation": "Mentions official agencies or banks in unverified text to induce false authority.",
    },
}

URL_REGEX = re.compile(r'https?://[^\s]+|bit\.ly/[^\s]+|tinyurl\.com/[^\s]+|t\.me/[^\s]+|wa\.me/[^\s]+|\.apk\b')


def detect_language(text: str) -> str:
    """Identify if the text is Malayalam, Manglish, or English."""
    if MALAYALAM_UNICODE_PATTERN.search(text):
        return "ml"

    text_lower = text.lower()
    manglish_hits = sum(1 for marker in MANGLISH_MARKERS if marker in text_lower)
    if manglish_hits >= 2:
        return "manglish"

    return "en"


def analyze_scam_message(message: str) -> dict[str, Any]:
    """Run baseline rule-based scam detection across English, Malayalam, and Manglish."""
    if not message or not message.strip():
        return {
            "language": "en",
            "risk_score": 0.0,
            "risk_tier": "SAFE",
            "is_scam": False,
            "detected_indicators": [],
            "summary": "Empty message provided.",
            "recommendations": ["No content to analyze."],
        }

    lang = detect_language(message)
    msg_lower = message.lower()

    detected_indicators: list[dict[str, Any]] = []
    total_score = 0

    # 1. Check categorized linguistic triggers
    for key, rule in INDICATORS.items():
        found_keywords = []

        # Check all keywords in the detected language + English as common mixing occurs
        kw_list = rule.get(lang, []) + rule.get("en", [])
        for kw in set(kw_list):
            if kw in msg_lower:
                found_keywords.append(kw)

        if found_keywords:
            weight = rule["weight"]
            total_score += weight
            detected_indicators.append({
                "category": key,
                "weight": weight,
                "matched_patterns": found_keywords[:3],
                "explanation": rule["explanation"],
            })

    # 2. Check for suspicious links / shorteners / APK attachments
    link_matches = URL_REGEX.findall(message)
    if link_matches:
        link_weight = 25
        total_score += link_weight
        detected_indicators.append({
            "category": "suspicious_links",
            "weight": link_weight,
            "matched_patterns": link_matches[:3],
            "explanation": (
                "Contains links or file attachments designed to route you to phishing sites or malicious APKs."
            ),
        })

    # Clamp score to 100
    risk_score = min(total_score, 100)

    # Risk Tier classification
    if risk_score >= 60:
        risk_tier = "CRITICAL" if risk_score >= 80 else "HIGH"
        is_scam = True
        summary = f"This message exhibits strong characteristics of a financial scam ({risk_tier} RISK)."
        recommendations = [
            "DO NOT click any links, open attachments, or download APK files.",
            "DO NOT share your OTP, UPI PIN, or bank credentials with anyone.",
            "Block the sender and report the message to 1930 or cybercrime.gov.in.",
            "Verify your account status directly via your bank's official mobile application.",
        ]
    elif risk_score >= 35:
        risk_tier = "MEDIUM"
        is_scam = True
        summary = "This message contains suspicious urgency or requests. Proceed with extreme caution."
        recommendations = [
            "Do not click links or call numbers provided inside the message.",
            "Contact your bank or service provider through their verified customer support number.",
        ]
    elif risk_score >= 15:
        risk_tier = "LOW"
        is_scam = False
        summary = "Minor suspicious elements detected, but no explicit credential theft patterns found."
        recommendations = [
            "Review sender details carefully before taking any financial action.",
        ]
    else:
        risk_tier = "SAFE"
        is_scam = False
        summary = "No obvious scam or phishing patterns detected in this message."
        recommendations = [
            "Message appears normal. Always follow standard security hygiene.",
        ]

    return {
        "language": lang,
        "risk_score": float(risk_score),
        "risk_tier": risk_tier,
        "is_scam": is_scam,
        "detected_indicators": detected_indicators,
        "summary": summary,
        "recommendations": recommendations,
    }

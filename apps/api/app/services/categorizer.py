import re

# Category keyword dictionaries
CATEGORY_RULES: dict[str, list[str]] = {
    "Food & Dining": [
        "swiggy", "zomato", "mcdonald", "starbucks", "domino", "pizza", "kfc",
        "burger", "restaurant", "cafe", "bistro", "diner", "eats", "barbeque",
        "biryani", "chai", "coffee", "haldiram", "subway", "bar", "pub",
    ],
    "Groceries": [
        "blinkit", "zepto", "instamart", "bigbasket", "dmart", "spencer",
        "supermarket", "grofers", "nature basket", "more retail", "reliance fresh",
        "vegetable", "fruits", "provision", "kirana", "dairy", "milk", "bakery",
    ],
    "Utilities": [
        "electricity", "bescom", "kseb", "tneb", "mseb", "uppcl", "water",
        "broadband", "wifi", "airtel", "jio", "vodafone", "vi", "bsnl",
        "gas", "indane", "hp gas", "bharat gas", "piped gas", "recharge",
        "dth", "tata play", "dish tv", "postpaid", "bill desk",
    ],
    "Rent & Housing": [
        "rent", "society", "maintenance", "landlord", "apartment", "house rent",
        "flats", "housing", "nobroker", "nestaway", "mygate",
    ],
    "Transportation": [
        "uber", "ola", "rapido", "metro", "irctc", "railway", "redbus", "abhibus",
        "petrol", "fuel", "diesel", "cng", "indian oil", "iocl", "bpcl", "hpcl",
        "shell", "fastag", "toll", "parking", "auto", "flight", "indigo", "air india",
    ],
    "Shopping": [
        "amazon", "flipkart", "myntra", "ajio", "nykaa", "tata cliq", "meesho",
        "zara", "h&m", "retail", "lifestyle", "westside", "croma", "reliance digital",
        "ikea", "decathlon", "lenskart", "titan",
    ],
    "Income & Salary": [
        "salary", "payroll", "stipend", "dividend", "interest credited", "bonus",
        "reimbursement", "cashback", "refund", "credit interest",
    ],
    "Investments": [
        "zerodha", "groww", "kuvera", "upstox", "angel one", "indmoney",
        "mutual fund", "sip", "camsonline", "kfintech", "fixed deposit", "recurring deposit",
        "coin", "etf", "securities", "national pension", "nps", "ppf",
    ],
    "Healthcare": [
        "pharmacy", "apollo", "medplus", "1mg", "pharmeasy", "netmeds",
        "hospital", "clinic", "diagnostic", "dr.", "doctor", "lab", "pathology",
        "dental", "opticals", "practo",
    ],
    "Transfers": [
        "neft", "rtgs", "imps", "upi p2p", "sent to", "received from",
        "transfer to", "transfer from", "to account", "from account",
    ],
}


def categorize_transaction(description: str, transaction_type: str = "debit") -> tuple[str, str | None]:
    """Classify transaction into a category and detect candidate merchant."""
    if not description:
        return ("Other", None)

    desc_lower = description.lower()

    # If it's an income/credit and has salary keywords
    if transaction_type.lower() == "credit":
        for keyword in CATEGORY_RULES["Income & Salary"]:
            if keyword in desc_lower:
                return ("Income & Salary", _extract_merchant(desc_lower, keyword))

    # Match rules in priority order
    for category, keywords in CATEGORY_RULES.items():
        if category == "Income & Salary" and transaction_type.lower() != "credit":
            continue
        for keyword in keywords:
            # Word boundary or substring check
            pattern = rf"(?:\b|_){re.escape(keyword)}(?:\b|_)"
            if re.search(pattern, desc_lower) or keyword in desc_lower:
                merchant = _extract_merchant(desc_lower, keyword)
                return (category, merchant)

    # Fallback to Transfers or Other based on transaction nature
    if "upi" in desc_lower or "transfer" in desc_lower or "sent" in desc_lower or "received" in desc_lower:
        return ("Transfers", None)

    return ("Other", None)


def _extract_merchant(desc: str, matched_keyword: str) -> str:
    """Format a clean display name for the matched merchant keyword."""
    return matched_keyword.title()

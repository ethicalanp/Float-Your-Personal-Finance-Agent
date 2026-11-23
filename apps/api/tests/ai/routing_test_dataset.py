from app.ai.agent.models import RouteClass

# Labelled dataset of 105 utterances across English, Malayalam, and Manglish
ROUTING_DATASET: list[tuple[str, RouteClass, str]] = [
    # =========================================================================
    # 1. English - Personal Finance (10)
    # =========================================================================
    ("How much did I spend this month?", RouteClass.PERSONAL_FINANCE, "en"),
    ("Show me my total expenses for January.", RouteClass.PERSONAL_FINANCE, "en"),
    ("What are my active recurring subscriptions?", RouteClass.PERSONAL_FINANCE, "en"),
    ("List all my recurring bills like Netflix and gym.", RouteClass.PERSONAL_FINANCE, "en"),
    ("Can you give me a category breakdown of my spending?", RouteClass.PERSONAL_FINANCE, "en"),
    ("Show my monthly cash flow and trend for the last 30 days.", RouteClass.PERSONAL_FINANCE, "en"),
    ("Compare my spending in January with December.", RouteClass.PERSONAL_FINANCE, "en"),
    ("What was my largest expense category recently?", RouteClass.PERSONAL_FINANCE, "en"),
    ("Summarize my income and spending.", RouteClass.PERSONAL_FINANCE, "en"),
    ("How much did I spend on dining and groceries?", RouteClass.PERSONAL_FINANCE, "en"),

    # =========================================================================
    # 2. English - Knowledge (10)
    # =========================================================================
    ("What is the RBI zero liability policy for unauthorized transactions?", RouteClass.KNOWLEDGE, "en"),
    ("Explain the Banking Ombudsman grievance redressal process.", RouteClass.KNOWLEDGE, "en"),
    ("How much deposit insurance is provided by DICGC per bank?", RouteClass.KNOWLEDGE, "en"),
    ("What are the RBI rules on credit card billing cycles?", RouteClass.KNOWLEDGE, "en"),
    ("What is card tokenization according to RBI guidelines?", RouteClass.KNOWLEDGE, "en"),
    ("What are my rights if an ATM does not dispense cash?", RouteClass.KNOWLEDGE, "en"),
    ("What are RBI master directions on digital payment security?", RouteClass.KNOWLEDGE, "en"),
    ("What is the time limit to report unauthorized bank transactions?", RouteClass.KNOWLEDGE, "en"),
    ("Explain the chargeback rules for UPI failures.", RouteClass.KNOWLEDGE, "en"),
    ("What is the role of the RBI Ombudsman in banking complaints?", RouteClass.KNOWLEDGE, "en"),

    # =========================================================================
    # 3. English - Credit Readiness (7)
    # =========================================================================
    ("Can I get a personal loan right now?", RouteClass.CREDIT_READINESS, "en"),
    ("Check my borrow readiness assessment.", RouteClass.CREDIT_READINESS, "en"),
    ("What is my indicative loan eligibility?", RouteClass.CREDIT_READINESS, "en"),
    ("What is my credit readiness band?", RouteClass.CREDIT_READINESS, "en"),
    ("Am I ready to apply for a bank loan?", RouteClass.CREDIT_READINESS, "en"),
    ("Evaluate my borrow readiness.", RouteClass.CREDIT_READINESS, "en"),
    ("What is my cibil score status and loan readiness?", RouteClass.CREDIT_READINESS, "en"),

    # =========================================================================
    # 4. English - Protect / Fraud Override (10)
    # =========================================================================
    ("I received a fake call asking for my OTP.", RouteClass.PROTECT, "en"),
    ("Money deducted from my bank account without permission!", RouteClass.PROTECT, "en"),
    ("I got a scam message asking me to download an APK file.", RouteClass.PROTECT, "en"),
    ("Someone did an unauthorized transaction on my card.", RouteClass.PROTECT, "en"),
    ("I clicked a phishing link and my account was debited.", RouteClass.PROTECT, "en"),
    ("A scammer caller claims to be Mumbai police and threatens digital arrest.", RouteClass.PROTECT, "en"),
    ("How do I report a cybercrime fraud on the 1930 helpline?", RouteClass.PROTECT, "en"),
    ("My debit card was stolen and used at an ATM.", RouteClass.PROTECT, "en"),
    ("I lost money in a Telegram part time job scam.", RouteClass.PROTECT, "en"),
    ("Help, my bank account is hacked!", RouteClass.PROTECT, "en"),

    # =========================================================================
    # 5. English - Combined (5)
    # =========================================================================
    ("Compare my monthly spending with RBI recommended savings guidelines.", RouteClass.COMBINED, "en"),
    ("Are my card transactions compliant with RBI tokenization rules?", RouteClass.COMBINED, "en"),
    ("Can I afford this loan EMI based on my cash flow and RBI debt guidelines?", RouteClass.COMBINED, "en"),
    ("Review my expenses against RBI zero liability norms.", RouteClass.COMBINED, "en"),
    ("Check my statement and compare with RBI ombudsman limits.", RouteClass.COMBINED, "en"),

    # =========================================================================
    # 6. English - Out of Scope (6)
    # =========================================================================
    ("Which stock should I buy for 10x profit tomorrow?", RouteClass.OUT_OF_SCOPE, "en"),
    ("Give me intraday trading tips for Nifty options.", RouteClass.OUT_OF_SCOPE, "en"),
    ("Should I invest in Bitcoin or Ethereum?", RouteClass.OUT_OF_SCOPE, "en"),
    ("Can you file my ITR tax return for this year?", RouteClass.OUT_OF_SCOPE, "en"),
    ("What is the weather forecast for Kochi tomorrow?", RouteClass.OUT_OF_SCOPE, "en"),
    ("Who won the cricket match yesterday?", RouteClass.OUT_OF_SCOPE, "en"),

    # =========================================================================
    # 7. English - Unclear / Greetings (6)
    # =========================================================================
    ("Hi", RouteClass.UNCLEAR, "en"),
    ("Hello", RouteClass.UNCLEAR, "en"),
    ("Hey there", RouteClass.UNCLEAR, "en"),
    ("help", RouteClass.UNCLEAR, "en"),
    ("What can you do?", RouteClass.UNCLEAR, "en"),
    ("Tell me something", RouteClass.UNCLEAR, "en"),

    # =========================================================================
    # 8. Malayalam - Personal Finance (8)
    # =========================================================================
    ("ഈ മാസം ഞാൻ എത്ര പണം ചെലവാക്കി?", RouteClass.PERSONAL_FINANCE, "ml"),
    ("എന്റെ കഴിഞ്ഞ മാസത്തെ ചെലവുകൾ കാണിക്കുക.", RouteClass.PERSONAL_FINANCE, "ml"),
    ("എന്റെ റിക്കറിംഗ് ബില്ലുകൾ ഏതൊക്കെയാണ്?", RouteClass.PERSONAL_FINANCE, "ml"),
    ("എന്റെ വരുമാനവും ചെലവും താരതമ്യം ചെയ്യുക.", RouteClass.PERSONAL_FINANCE, "ml"),
    ("ഭക്ഷണത്തിനായി ഞാൻ എത്ര രൂപ ചെലവാക്കി?", RouteClass.PERSONAL_FINANCE, "ml"),
    ("എന്റെ പ്രതിമാസ ക്യാഷ് ഫ്ലോ സ്റ്റേറ്റ്മെന്റ് പരിശോധിക്കുക.", RouteClass.PERSONAL_FINANCE, "ml"),
    ("സബ്സ്ക്രിപ്ഷൻ പേയ്മെന്റുകൾ എത്രയുണ്ട്?", RouteClass.PERSONAL_FINANCE, "ml"),
    ("കഴിഞ്ഞ മാസത്തെ ചെലവ് ചുരുക്കം പറയൂ.", RouteClass.PERSONAL_FINANCE, "ml"),

    # =========================================================================
    # 9. Malayalam - Knowledge (6)
    # =========================================================================
    ("ആർബിഐ നിയമപ്രകാരം തട്ടിപ്പ് നടന്നാൽ ബാങ്ക് നഷ്ടപരിഹാരം നൽകുമോ?", RouteClass.KNOWLEDGE, "ml"),
    ("ബാങ്കിംഗ് ഓംബുഡ്സ്മാൻ പരാതി നൽകുന്നത് എങ്ങനെയാണ്?", RouteClass.KNOWLEDGE, "ml"),
    ("ഡെപ്പോസിറ്റ് ഇൻഷുറൻസ് പരിധി എത്രയാണ്?", RouteClass.KNOWLEDGE, "ml"),
    ("ക്രെഡിറ്റ് കാർഡ് സംബന്ധിച്ച ആർബിഐ ചട്ടങ്ങൾ എന്തൊക്കെയാണ്?", RouteClass.KNOWLEDGE, "ml"),
    ("എടിഎം പണം നൽകിയില്ലെങ്കിൽ ആർബിഐ നിയമം എന്താണ്?", RouteClass.KNOWLEDGE, "ml"),
    ("പരാതി പരിഹാര സംവിധാനങ്ങൾ എന്തൊക്കെയാണ്?", RouteClass.KNOWLEDGE, "ml"),

    # =========================================================================
    # 10. Malayalam - Credit Readiness (5)
    # =========================================================================
    ("എനിക്ക് ഇപ്പോൾ വായ്പ ലഭിക്കുമോ?", RouteClass.CREDIT_READINESS, "ml"),
    ("എന്റെ വായ്പാ യോഗ്യത പരിശോധിക്കുക.", RouteClass.CREDIT_READINESS, "ml"),
    ("എന്റെ ലോൺ തയ്യാറെടുപ്പ് നില എന്താണ്?", RouteClass.CREDIT_READINESS, "ml"),
    ("ക്രെഡിറ്റ് സ്കോർ പരിശോധിക്കാമോ?", RouteClass.CREDIT_READINESS, "ml"),
    ("എനിക്ക് പേഴ്സണൽ ലോൺ കിട്ടാൻ സാധ്യതയുണ്ടോ?", RouteClass.CREDIT_READINESS, "ml"),

    # =========================================================================
    # 11. Malayalam - Protect / Fraud Override (8)
    # =========================================================================
    ("എന്റെ അക്കൗണ്ടിൽ നിന്ന് ഒടിപി ഇല്ലാതെ പണം പോയി!", RouteClass.PROTECT, "ml"),
    ("വ്യാജ കോളിലൂടെ തട്ടിപ്പുകാരൻ പണം അപഹരിച്ചു.", RouteClass.PROTECT, "ml"),
    ("സൈബർ ക്രൈം 1930 ഹെൽപ്പ്‌ലൈനിൽ എങ്ങനെ പരാതിപ്പെടാം?", RouteClass.PROTECT, "ml"),
    ("ഡിജിറ്റൽ അറസ്റ്റ് തട്ടിപ്പിൽ പെട്ടുപോയി, സഹായിക്കൂ.", RouteClass.PROTECT, "ml"),
    ("എന്റെ എടിഎം കാർഡ് മോഷണം പോയി, അക്കൗണ്ട് മരവിപ്പിക്കണം.", RouteClass.PROTECT, "ml"),
    ("ടെലിഗ്രാം പാർട്ട് ടൈം ജോലി തട്ടിപ്പ് പരാതി.", RouteClass.PROTECT, "ml"),
    ("വ്യാജ എപികെ ഫയൽ ഇൻസ്റ്റാൾ ചെയ്ത ശേഷം പണം നഷ്ടപ്പെട്ടു.", RouteClass.PROTECT, "ml"),
    ("അക്കൗണ്ട് ഹാക്ക് ചെയ്യപ്പെട്ടു, ഉടൻ പരാതി നൽകണം.", RouteClass.PROTECT, "ml"),

    # =========================================================================
    # 12. Malayalam - Out of Scope / Unclear (4)
    # =========================================================================
    ("ഏത് ഓഹരിയിലാണ് നാളെ നിക്ഷേപിക്കേണ്ടത്?", RouteClass.OUT_OF_SCOPE, "ml"),
    ("ക്രിപ്റ്റോ ട്രേഡിംഗ് ലാഭകരമാണോ?", RouteClass.OUT_OF_SCOPE, "ml"),
    ("നമസ്കാരം", RouteClass.UNCLEAR, "ml"),
    ("ഹലോ", RouteClass.UNCLEAR, "ml"),

    # =========================================================================
    # 13. Manglish - Personal Finance (8)
    # =========================================================================
    ("Ee maasam ethra chelavu aayi?", RouteClass.PERSONAL_FINANCE, "manglish"),
    ("Ente last month expense summary tharumo?", RouteClass.PERSONAL_FINANCE, "manglish"),
    ("Recurring bills list nokkanam.", RouteClass.PERSONAL_FINANCE, "manglish"),
    ("Foodinu ethra paisa spend cheythu?", RouteClass.PERSONAL_FINANCE, "manglish"),
    ("Ente monthly varumanam and chelavu compare cheyyu.", RouteClass.PERSONAL_FINANCE, "manglish"),
    ("Gym subscription ethra aayi?", RouteClass.PERSONAL_FINANCE, "manglish"),
    ("Category breakdown kaanikku.", RouteClass.PERSONAL_FINANCE, "manglish"),
    ("Ethra paisa ithuvare spend cheythu?", RouteClass.PERSONAL_FINANCE, "manglish"),

    # =========================================================================
    # 14. Manglish - Knowledge (5)
    # =========================================================================
    ("RBI rules for unauthorized card transaction enthannu?", RouteClass.KNOWLEDGE, "manglish"),
    ("Ombudsman complaint enganeya file cheyyuka?", RouteClass.KNOWLEDGE, "manglish"),
    ("Deposit insurance ethra kittum bank pottiyal?", RouteClass.KNOWLEDGE, "manglish"),
    ("Zero liability policy rules explain cheyyumo?", RouteClass.KNOWLEDGE, "manglish"),
    ("Card tokenization rule enthanu?", RouteClass.KNOWLEDGE, "manglish"),

    # =========================================================================
    # 15. Manglish - Credit Readiness (5)
    # =========================================================================
    ("Enikku loan kittumo nokkamo?", RouteClass.CREDIT_READINESS, "manglish"),
    ("Borrow readiness score ethrayanu?", RouteClass.CREDIT_READINESS, "manglish"),
    ("Loan eligibility check cheyyuka.", RouteClass.CREDIT_READINESS, "manglish"),
    ("Personal loan edukkaan ready aano njan?", RouteClass.CREDIT_READINESS, "manglish"),
    ("Cibil score status nokku.", RouteClass.CREDIT_READINESS, "manglish"),

    # =========================================================================
    # 16. Manglish - Protect / Fraud Override (8)
    # =========================================================================
    ("Akkountil ninnu ariyathe panam poyi!", RouteClass.PROTECT, "manglish"),
    ("Scam call vannu otp chodichu, njan koduthu.", RouteClass.PROTECT, "manglish"),
    ("Fake link click cheythu account block aayi.", RouteClass.PROTECT, "manglish"),
    ("Thattippu aano ithu? Digital arrest ennu paranju call vannu.", RouteClass.PROTECT, "manglish"),
    ("Police call cheythu, money transfer cheyyan parayunnu.", RouteClass.PROTECT, "manglish"),
    ("1930 cybercrime helpline il call cheyyanam.", RouteClass.PROTECT, "manglish"),
    ("ATM card stolen aayi, unauthorized withdrawal nadannu.", RouteClass.PROTECT, "manglish"),
    ("Telegram task scam il paisa poyi, complaint engane kodukkum?", RouteClass.PROTECT, "manglish"),

    # =========================================================================
    # 17. Manglish - Out of Scope / Unclear (4)
    # =========================================================================
    ("Ethu stock vangnam profit kittan?", RouteClass.OUT_OF_SCOPE, "manglish"),
    ("Trading tips tharumo?", RouteClass.OUT_OF_SCOPE, "manglish"),
    ("Hai", RouteClass.UNCLEAR, "manglish"),
    ("Halo", RouteClass.UNCLEAR, "manglish"),
]

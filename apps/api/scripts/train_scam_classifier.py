#!/usr/bin/env python
"""Train TF-IDF Scam Classifier and compare side-by-side against the Rule-Based Baseline."""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import classification_report, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

from app.services.scam_classifier import ScamClassifier
from app.services.scam_detector import analyze_scam_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Seed dataset of Malayalam, Manglish, and English financial messages
SEED_DATASET: list[dict[str, Any]] = [
    # Malayalam Scams (is_scam=1)
    {
        "text": "പ്രിയ ഉപഭോക്താവേ, നിങ്ങളുടെ ബാങ്ക് അക്കൗണ്ട് ഇന്ന് രാത്രി ബ്ലോക്ക് ചെയ്യപ്പെടും. ഉടൻ കെവൈസി അപ്ഡേറ്റ് ചെയ്യുക.",
        "is_scam": 1,
        "lang": "ml",
    },
    {
        "text": "ഇന്നു രാത്രി 9:30 ന് വൈദ്യുതി വിച്ഛേദിക്കും. ബിൽ ഉടൻ അടക്കാൻ ഈ നമ്പറിലേക്ക് വിളിക്കുക അല്ലെങ്കിൽ പാൻ ലിങ്ക് ചെയ്യുക.",
        "is_scam": 1,
        "lang": "ml",
    },
    {
        "text": "നിങ്ങൾക്ക് 25 ലക്ഷം രൂപ ലോട്ടറി അടിച്ചിരിക്കുന്നു. സമ്മാനത്തുക ലഭിക്കാൻ പ്രോസസ്സിംഗ് ഫീസ് ആയി 5000 രൂപ അയക്കുക.",
        "is_scam": 1,
        "lang": "ml",
    },
    {
        "text": "എസ്ബിഐ സുരക്ഷാ അറിയിപ്പ്: നിങ്ങളുടെ ഒടിപി 492019 ഷെയർ ചെയ്യുക. അല്ലാത്തപക്ഷം അക്കൗണ്ട് റദ്ദാക്കും.",
        "is_scam": 1,
        "lang": "ml",
    },
    {
        "text": "ബാങ്ക് മാനേജർ വിളിക്കുന്നു. അക്കൗണ്ട് വെരിഫിക്കേഷനായി പാൻ കാർഡ് നമ്പറും എടിഎം പിൻ നമ്പറും നൽകുക.",
        "is_scam": 1,
        "lang": "ml",
    },
    {
        "text": "പ്രധാൻ മന്ത്രി യോജന പ്രകാരം 50,000 രൂപ ലോൺ ഉടൻ ലഭ്യമാണ്. ഈ ആപ്പ് ഡൗൺലോഡ് ചെയ്ത് ഇൻസ്റ്റാൾ ചെയ്യുക http://bit.ly/pmloan",
        "is_scam": 1,
        "lang": "ml",
    },
    {
        "text": "പാർട്ട് ടൈം ജോലി വഴി ദിവസം 3000 രൂപ സമ്പാദിക്കാം. യൂട്യൂബ് വീഡിയോകൾ ലൈക്ക് ചെയ്യൂ. രജിസ്ട്രേഷന് ക്ലിക്ക് ചെയ്യൂ.",
        "is_scam": 1,
        "lang": "ml",
    },
    {
        "text": "നിങ്ങളുടെ ക്രെഡിറ്റ് കാർഡ് റിവാർഡ് പോയിന്റുകൾ കാലഹരണപ്പെടാൻ പോകുന്നു. പണമായി മാറ്റാൻ ഒടിപി നൽകുക.",
        "is_scam": 1,
        "lang": "ml",
    },
    {
        "text": "പോലീസ് ഡിപ്പാർട്ട്മെന്റ്: നിങ്ങളുടെ പേരിൽ മയക്കുമരുന്ന് പാഴ്സൽ വന്നിട്ടുണ്ട്. അറസ്റ്റ് വാറണ്ട് ഒഴിവാക്കാൻ ഫീസ് അടക്കുക.",
        "is_scam": 1,
        "lang": "ml",
    },
    {
        "text": "വിദേശത്ത് ഉയർന്ന ശമ്പളമുള്ള ജോലി. വിസ ഫീസ് 10000 രൂപ അയക്കുക.",
        "is_scam": 1,
        "lang": "ml",
    },

    # Manglish Scams (is_scam=1)
    {
        "text": "Dear customer, ningalude bank account block aayi. Udan thanne kyc update cheyyan linkil click cheyyu.",
        "is_scam": 1,
        "lang": "manglish",
    },
    {
        "text": (
            "Innu rathri electricity cut aakum. Bill adakkillel line cut aakum. "
            "Contact electricity officer udan thanne."
        ),
        "is_scam": 1,
        "lang": "manglish",
    },
    {
        "text": "Ningalkku 10 lakh lottery kittiyirikkunnu. Panam kittan registration fee 2500 ayakkuka.",
        "is_scam": 1,
        "lang": "manglish",
    },
    {
        "text": "Police arrest warrant vannu. Case aavathirikkan udan panam transfer cheyyuka.",
        "is_scam": 1,
        "lang": "manglish",
    },
    {
        "text": "SBI account deactivate aakum. OTP share cheythu verify cheyyu.",
        "is_scam": 1,
        "lang": "manglish",
    },
    {
        "text": "AnyDesk app install cheyyu ningalude refund kittan. Fast aayi cheyyu.",
        "is_scam": 1,
        "lang": "manglish",
    },
    {
        "text": "GPay cashback 2000 rupiya kittan pin type cheythu claim cheyyuka.",
        "is_scam": 1,
        "lang": "manglish",
    },
    {
        "text": "Part-time work from home. Daily 5000 sambadhikkam. Telegram groupil join cheyyu.",
        "is_scam": 1,
        "lang": "manglish",
    },
    {
        "text": "Urgent aayi credit card details update cheyyu, illenkil account suspend cheyyum.",
        "is_scam": 1,
        "lang": "manglish",
    },
    {
        "text": "Customs officer call cheyyunnu. Parcel release cheyyan fee adakkuka.",
        "is_scam": 1,
        "lang": "manglish",
    },

    # English Scams (is_scam=1)
    {
        "text": "Urgent: Your HDFC Bank account will be blocked within 24 hours. Click here to verify KYC immediately.",
        "is_scam": 1,
        "lang": "en",
    },
    {
        "text": "Electricity power disconnected tonight at 9:30 PM due to unpaid bill. Call electricity officer now.",
        "is_scam": 1,
        "lang": "en",
    },
    {
        "text": (
            "Congratulations! You have won $1,000,000 in international lottery. Pay $200 processing fee to claim prize."
        ),
        "is_scam": 1,
        "lang": "en",
    },
    {
        "text": (
            "Income Tax Department: Tax refund of Rs 15,400 approved. Enter your ATM card details and PIN to credit."
        ),
        "is_scam": 1,
        "lang": "en",
    },
    {
        "text": (
            "FedEx Security Alert: Your package containing illegal narcotics is seized. "
            "Transfer bail money to avoid arrest."
        ),
        "is_scam": 1,
        "lang": "en",
    },
    {
        "text": "Customer Care: Install QuickSupport app to resolve failed transaction and get instant refund.",
        "is_scam": 1,
        "lang": "en",
    },
    {
        "text": "Work from home! Earn Rs 4000 daily by rating Google hotels. Contact HR on WhatsApp now.",
        "is_scam": 1,
        "lang": "en",
    },
    {
        "text": "Your Netflix membership expired. Update payment details within 2 hours to avoid cancellation.",
        "is_scam": 1,
        "lang": "en",
    },
    {
        "text": "SBI Alert: Share the 6-digit OTP sent to your phone to activate 5G SIM card service.",
        "is_scam": 1,
        "lang": "en",
    },
    {
        "text": (
            "Immediate action required: Suspicious login from Russia detected. "
            "Click link to secure account password."
        ),
        "is_scam": 1,
        "lang": "en",
    },

    # Malayalam Legitimate Messages (is_scam=0)
    {
        "text": "നിങ്ങളുടെ അക്കൗണ്ടിൽ നിന്നും 500 രൂപ പിൻവലിച്ചു. ബാക്കി ബാലൻസ് 14,250 രൂപ. നന്ദി.",
        "is_scam": 0,
        "lang": "ml",
    },
    {
        "text": "മെയ് മാസത്തെ വൈദ്യുതി ബിൽ 640 രൂപ വിജയകരമായി അടച്ചു. കെ.എസ്.ഇ.ബി.",
        "is_scam": 0,
        "lang": "ml",
    },
    {
        "text": "പ്രിയ രമേശ്, സുഖമാണോ? അടുത്ത ഞായറാഴ്ച നമുക്ക് നാട്ടിൽ വെച്ച് കാണാം.",
        "is_scam": 0,
        "lang": "ml",
    },
    {
        "text": "നിങ്ങളുടെ ആമസോൺ ഓർഡർ ഇന്ന് വൈകുന്നേരത്തോടെ ഡെലിവറി ചെയ്യും. ട്രാക്ക് ചെയ്യുക.",
        "is_scam": 0,
        "lang": "ml",
    },
    {
        "text": "ജോലിക്ക് ആവശ്യമായ ബയോഡാറ്റ ഇമെയിൽ വഴി അയച്ചിട്ടുണ്ട്. ദയവായി പരിശോധിക്കുക.",
        "is_scam": 0,
        "lang": "ml",
    },
    {
        "text": "സ്കൂൾ ഫീസ് അടക്കാനുള്ള അവസാന തീയതി അടുത്ത മാസം പത്താം തീയതിയാണ്.",
        "is_scam": 0,
        "lang": "ml",
    },
    {
        "text": "നിങ്ങളുടെ മൊബൈൽ റീചാർജ് വിജയകരമായി പൂർത്തിയായി. 28 ദിവസത്തേക്ക് അൺലിമിറ്റഡ് കോളുകൾ.",
        "is_scam": 0,
        "lang": "ml",
    },
    {
        "text": "ഡോക്ടറുമായുള്ള അപ്പോയിന്റ്മെന്റ് നാളെ രാവിലെ 10 മണിക്ക് നിശ്ചയിച്ചിരിക്കുന്നു.",
        "is_scam": 0,
        "lang": "ml",
    },
    {
        "text": "ക്രെഡിറ്റ് കാർഡ് പ്രതിമാസ സ്റ്റേറ്റ്മെന്റ് നിങ്ങളുടെ ഇമെയിലിലേക്ക് അയച്ചിട്ടുണ്ട്.",
        "is_scam": 0,
        "lang": "ml",
    },
    {
        "text": "വീട്ടിലേക്ക് വരുമ്പോൾ കുറച്ച് പച്ചക്കറികളും പാലും വാങ്ങി വരിക.",
        "is_scam": 0,
        "lang": "ml",
    },

    # Manglish Legitimate Messages (is_scam=0)
    {
        "text": "Njan ninnude accountil 1000 rupiya GPay cheythittund, kitiyo ennu nokku.",
        "is_scam": 0,
        "lang": "manglish",
    },
    {
        "text": "Naale class undo ennu ariyille? Timetable groupil share cheyyaamo.",
        "is_scam": 0,
        "lang": "manglish",
    },
    {
        "text": "Swiggy order deliver aayi. Food kazhikkam vaa.",
        "is_scam": 0,
        "lang": "manglish",
    },
    {
        "text": "Flight ticket book aayi. PNR details WhatsAppil ayachittund.",
        "is_scam": 0,
        "lang": "manglish",
    },
    {
        "text": "Cinema tickets book cheyyan njan nokkam. Ethu theatre aano nallathu?",
        "is_scam": 0,
        "lang": "manglish",
    },
    {
        "text": "Electricity bill pay cheythu receipt vannittund. Ellaam clear aayi.",
        "is_scam": 0,
        "lang": "manglish",
    },
    {
        "text": "Interview nannaayi poyi. Adutha week result ariyaam ennu paranju.",
        "is_scam": 0,
        "lang": "manglish",
    },
    {
        "text": "Meeting 4 manikku reschedule cheythittund, Zoom link calendaril undu.",
        "is_scam": 0,
        "lang": "manglish",
    },
    {
        "text": "Happy birthday Rahul! Have a wonderful day and year ahead.",
        "is_scam": 0,
        "lang": "manglish",
    },
    {
        "text": "Veettil ethi, safe aayi travel cheythu. Nale vilikkaam.",
        "is_scam": 0,
        "lang": "manglish",
    },

    # English Legitimate Messages (is_scam=0)
    {
        "text": "Your account xx4901 has been credited with INR 45,000.00 on 01-Nov-26 for salary transfer.",
        "is_scam": 0,
        "lang": "en",
    },
    {
        "text": "Your OTP for login to Zerodha is 839201. Valid for 5 minutes. Do not share this with anyone.",
        "is_scam": 0,
        "lang": "en",
    },
    {
        "text": "Hi team, please find attached the revised project roadmap for Q4.",
        "is_scam": 0,
        "lang": "en",
    },
    {
        "text": "Thank you for dining at Taj Vivanta. Your bill of Rs 3,420 has been paid via credit card.",
        "is_scam": 0,
        "lang": "en",
    },
    {
        "text": "Your train ticket for 12626 Kerala Express has been confirmed. Seat: B3-42.",
        "is_scam": 0,
        "lang": "en",
    },
    {
        "text": "Your monthly utility bill payment of Rs 1,120 has been processed successfully.",
        "is_scam": 0,
        "lang": "en",
    },
    {
        "text": "Can we catch up for a coffee tomorrow evening around 6 PM near Infopark?",
        "is_scam": 0,
        "lang": "en",
    },
    {
        "text": "Reminder: Your dentist appointment is scheduled for tomorrow at 3:30 PM with Dr. Thomas.",
        "is_scam": 0,
        "lang": "en",
    },
    {
        "text": "Uber receipt: Your ride to Cochin International Airport was Rs 620. Thanks for riding.",
        "is_scam": 0,
        "lang": "en",
    },
    {
        "text": "Your passport renewal appointment is confirmed at PSK Cochin on 15-Nov-26.",
        "is_scam": 0,
        "lang": "en",
    },
]


def evaluate_baseline_rule(texts: list[str]) -> tuple[np.ndarray, float]:
    """Evaluate deterministic rule baseline and measure latency."""
    preds = []
    latencies = []
    for txt in texts:
        t0 = time.perf_counter()
        res = analyze_scam_message(txt)
        latencies.append((time.perf_counter() - t0) * 1000)
        # Rules flag HIGH or CRITICAL as scam
        is_scam = 1 if res.get("risk_tier") in ("HIGH", "CRITICAL") else 0
        preds.append(is_scam)
    avg_latency = float(np.mean(latencies))
    return np.array(preds), avg_latency


def evaluate_tfidf_model(classifier: ScamClassifier, texts: list[str]) -> tuple[np.ndarray, float]:
    """Evaluate TF-IDF statistical model and measure latency."""
    preds = []
    latencies = []
    for txt in texts:
        t0 = time.perf_counter()
        prob = classifier.predict_proba(txt)
        latencies.append((time.perf_counter() - t0) * 1000)
        preds.append(1 if prob >= 0.50 else 0)
    avg_latency = float(np.mean(latencies))
    return np.array(preds), avg_latency


def train_and_compare_scam_models(output_dir: Path) -> dict[str, Any]:
    """Train TF-IDF scam model and benchmark against Rule Baseline."""
    texts = [item["text"] for item in SEED_DATASET]
    labels = [item["is_scam"] for item in SEED_DATASET]

    # Stratified 75% Train, 25% Test
    x_train, x_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.25, random_state=42, stratify=labels
    )
    logger.info("Dataset: %d total (%d train, %d test)", len(texts), len(x_train), len(x_test))

    # 1. Train TF-IDF classifier
    classifier = ScamClassifier()
    train_res = classifier.train(x_train, y_train)
    logger.info("Trained TF-IDF classifier: %s", train_res)

    # 2. Evaluate Rule Baseline on Test Set
    rule_preds, rule_latency = evaluate_baseline_rule(x_test)
    y_test_arr = np.array(y_test)

    rule_precision = float(precision_score(y_test_arr, rule_preds, zero_division=0))
    rule_recall = float(recall_score(y_test_arr, rule_preds, zero_division=0))
    rule_f1 = float(f1_score(y_test_arr, rule_preds, zero_division=0))

    # 3. Evaluate TF-IDF on Test Set
    tfidf_preds, tfidf_latency = evaluate_tfidf_model(classifier, x_test)
    tfidf_precision = float(precision_score(y_test_arr, tfidf_preds, zero_division=0))
    tfidf_recall = float(recall_score(y_test_arr, tfidf_preds, zero_division=0))
    tfidf_f1 = float(f1_score(y_test_arr, tfidf_preds, zero_division=0))

    logger.info("=== COMPARISON RESULTS ===")
    logger.info(
        "Rule Baseline: Precision=%.4f, Recall=%.4f, F1=%.4f, Latency=%.2f ms",
        rule_precision, rule_recall, rule_f1, rule_latency,
    )
    logger.info(
        "TF-IDF Model:  Precision=%.4f, Recall=%.4f, F1=%.4f, Latency=%.2f ms",
        tfidf_precision, tfidf_recall, tfidf_f1, tfidf_latency,
    )

    comparison = {
        "dataset_size": len(texts),
        "test_size": len(x_test),
        "rule_baseline": {
            "precision": round(rule_precision, 4),
            "recall": round(rule_recall, 4),
            "f1": round(rule_f1, 4),
            "avg_latency_ms": round(rule_latency, 2),
        },
        "tfidf_classifier": {
            "precision": round(tfidf_precision, 4),
            "recall": round(tfidf_recall, 4),
            "f1": round(tfidf_f1, 4),
            "avg_latency_ms": round(tfidf_latency, 2),
        },
        "f1_improvement": round(tfidf_f1 - rule_f1, 4),
        "classification_report_tfidf": classification_report(
            y_test_arr, tfidf_preds, target_names=["Legitimate", "Scam"], output_dict=True
        ),
    }

    # Save artifacts
    output_dir.mkdir(parents=True, exist_ok=True)
    comparison_path = output_dir / "scam_model_comparison.json"
    comparison_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")

    model_path = output_dir / "scam_tfidf_model.joblib"
    classifier.save(model_path)
    logger.info("Saved comparison to %s and model to %s", comparison_path, model_path)

    return comparison


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate multilingual scam classifier")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    train_and_compare_scam_models(output_dir=args.output_dir)


if __name__ == "__main__":
    main()

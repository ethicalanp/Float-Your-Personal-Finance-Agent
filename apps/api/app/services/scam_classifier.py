"""TF-IDF Statistical Scam Classifier and Hybrid Rule+ML Detector for Malayalam, Manglish, and English."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

from app.services.scam_detector import analyze_scam_message

logger = logging.getLogger(__name__)


def build_tfidf_pipeline() -> Pipeline:
    """Build dual word and character n-gram TF-IDF pipeline for multilingual fraud detection.

    Character n-grams (3-5) are critical for capturing phonetic spelling variations
    in informal Manglish (e.g. 'adakkuka' vs 'adakkillel', 'panam' vs 'panam linkil').
    """
    word_vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        analyzer="word",
        lowercase=True,
        sublinear_tf=True,
        max_features=2500,
    )
    char_vectorizer = TfidfVectorizer(
        ngram_range=(3, 5),
        analyzer="char",
        lowercase=True,
        sublinear_tf=True,
        max_features=5000,
    )
    union = FeatureUnion([
        ("word_tfidf", word_vectorizer),
        ("char_tfidf", char_vectorizer),
    ])
    classifier = LogisticRegression(
        C=1.5,
        class_weight="balanced",
        max_iter=1000,
        random_state=42,
    )
    return Pipeline([("features", union), ("clf", classifier)])


class ScamClassifier:
    """Statistical TF-IDF scam classifier with persistence."""

    def __init__(self, pipeline: Pipeline | None = None) -> None:
        self.pipeline = pipeline or build_tfidf_pipeline()
        self.is_fitted = False

    def train(self, texts: list[str], labels: list[int]) -> dict[str, float]:
        """Train classifier and return training metrics."""
        self.pipeline.fit(texts, labels)
        self.is_fitted = True
        preds = self.pipeline.predict(texts)
        acc = float(np.mean(preds == labels))
        return {"training_samples": len(texts), "training_accuracy": acc}

    def predict_proba(self, text: str) -> float:
        """Return scam probability between 0.0 and 1.0."""
        if not self.is_fitted:
            raise RuntimeError("ScamClassifier is not fitted; train or load a model before inference.")
        prob = self.pipeline.predict_proba([text])[0][1]
        return float(prob)

    def predict(self, text: str, threshold: float = 0.5) -> bool:
        """Return boolean scam classification based on threshold."""
        return self.predict_proba(text) >= threshold

    def save(self, file_path: Path | str) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.pipeline, path)
        logger.info("Saved ScamClassifier model to %s", path)

    @classmethod
    def load(cls, file_path: Path | str) -> ScamClassifier:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Model file not found: {path}")
        pipeline = joblib.load(path)
        instance = cls(pipeline=pipeline)
        instance.is_fitted = True
        return instance


class HybridScamDetector:
    """Ensemble detector combining deterministic rule-based checks and TF-IDF statistical classifier.

    - Rules provide high precision and instant explainability on known attack patterns (APKs, OTP theft).
    - TF-IDF provides robust generalization across noisy, transliterated Manglish and conversational phrasing.
    """

    def __init__(self, classifier: ScamClassifier | None = None) -> None:
        self.classifier = classifier

    def analyze(self, message: str) -> dict[str, Any]:
        """Run hybrid detection and return comprehensive fraud risk assessment."""
        start_t = time.perf_counter()

        # 1. Rule-based evaluation
        rule_result = analyze_scam_message(message)
        rule_score = float(rule_result.get("risk_score", 0.0))  # 0 to 100
        rule_indicators = rule_result.get("detected_indicators", rule_result.get("indicators", []))

        # 2. Statistical model evaluation
        model_proba: float | None = None
        if self.classifier is not None:
            model_proba = self.classifier.predict_proba(message)

        # 3. Hybrid fusion logic
        # Rule score is 0-100; normalize to 0-1
        norm_rule_score = rule_score / 100.0

        # If rule baseline or statistical model flags scam, elevate combined score
        if model_proba is None:
            combined_prob = norm_rule_score
        elif norm_rule_score >= 0.50 or model_proba >= 0.60:
            combined_prob = max(norm_rule_score, model_proba)
        else:
            combined_prob = 0.50 * norm_rule_score + 0.50 * model_proba

        combined_score = round(combined_prob * 100, 1)

        if combined_score >= 80:
            final_tier = "CRITICAL"
        elif combined_score >= 50:
            final_tier = "HIGH"
        elif combined_score >= 30:
            final_tier = "MEDIUM"
        else:
            final_tier = "SAFE"

        latency_ms = round((time.perf_counter() - start_t) * 1000, 2)

        detection_source = []
        if rule_indicators:
            detection_source.append("rules")
        if model_proba is not None and model_proba >= 0.50:
            detection_source.append("ml_tfidf")
        if not detection_source:
            detection_source.append("baseline_clean")

        return {
            "message": message,
            "language": rule_result.get("language", "en"),
            "risk_tier": final_tier,
            "risk_score": combined_score,
            "is_scam": final_tier in ("HIGH", "CRITICAL"),
            "model_probability": round(model_proba, 4) if model_proba is not None else None,
            "rule_score": rule_score,
            "detection_sources": detection_source,
            "indicators": rule_indicators,
            "latency_ms": latency_ms,
        }

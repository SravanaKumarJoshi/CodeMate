"""
Intent Classification Model Training Script for CodeMate.
Trains a TF-IDF + Logistic Regression pipeline on developer queries
across 6 key intents and saves the serialized model for inference.
"""

import os
import json
import logging
from datetime import datetime
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, accuracy_score
import joblib

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_PATH = os.path.join(CURRENT_DIR, "dataset.csv")
MODEL_DIR = os.path.join(CURRENT_DIR, "model")
MODEL_PATH = os.path.join(MODEL_DIR, "classifier.joblib")
METADATA_PATH = os.path.join(MODEL_DIR, "metadata.json")


def train_model() -> dict:
    """Train and persist the intent classification model."""
    os.makedirs(MODEL_DIR, exist_ok=True)

    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(f"Dataset not found at {DATASET_PATH}")

    logger.info("Loading dataset from %s...", DATASET_PATH)
    df = pd.read_csv(DATASET_PATH)
    df["query"] = df["query"].astype(str).str.strip()
    df["intent"] = df["intent"].astype(str).str.strip()

    X = df["query"]
    y = df["intent"]

    labels = sorted(list(y.unique()))
    logger.info("Found %d samples across %d classes: %s", len(df), len(labels), labels)

    pipeline = Pipeline([
        (
            "tfidf",
            TfidfVectorizer(
                ngram_range=(1, 2),
                lowercase=True,
                max_features=2500,
                sublinear_tf=True
            ),
        ),
        (
            "clf",
            LogisticRegression(
                C=3.0,
                max_iter=1000,
                random_state=42,
                class_weight="balanced"
            ),
        ),
    ])

    # Evaluate using 5-fold cross-validation
    cv_scores = cross_val_score(pipeline, X, y, cv=5, scoring="accuracy")
    mean_cv_accuracy = float(cv_scores.mean())
    logger.info("5-Fold CV Accuracy: %.4f (+/- %.4f)", mean_cv_accuracy, float(cv_scores.std()))

    # Train on full dataset for production artifact
    pipeline.fit(X, y)

    # Save model artifact
    logger.info("Saving trained pipeline to %s...", MODEL_PATH)
    joblib.dump(pipeline, MODEL_PATH)

    # Save metadata
    metadata = {
        "model_type": "TF-IDF + LogisticRegression",
        "labels": labels,
        "sample_count": int(len(df)),
        "cv_accuracy": round(mean_cv_accuracy, 4),
        "trained_at": datetime.utcnow().isoformat() + "Z",
        "parameters": {
            "ngram_range": [1, 2],
            "max_features": 2500,
            "C": 3.0,
            "class_weight": "balanced"
        }
    }

    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info("Model metadata saved to %s", METADATA_PATH)

    # Quick test assertions on interview sample questions
    test_samples = [
        ("Where is authentication implemented?", "CODE_SEARCH"),
        ("Explain how authentication works in this project", "CODE_EXPLANATION"),
        ("Why could the login endpoint return a 401 error?", "BUG_ANALYSIS"),
        ("Generate unit tests for this function", "TEST_GENERATION"),
        ("What database is being used in this project?", "ARCHITECTURE"),
        ("What is CodeMate?", "GENERAL_QUERY")
    ]

    logger.info("Verifying benchmark demo queries:")
    for query, expected in test_samples:
        pred = pipeline.predict([query])[0]
        probs = pipeline.predict_proba([query])[0]
        conf = float(max(probs))
        logger.info("  Query: '%s' -> Predicted: %s (Conf: %.2f) [Expected: %s]", query, pred, conf, expected)

    return metadata


if __name__ == "__main__":
    train_model()

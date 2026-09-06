import json
import logging
from typing import Any, Optional
import joblib
from app.config import settings

logger = logging.getLogger(__name__)

_cached_model: Optional[Any] = None
_cached_metadata: Optional[dict] = None


def is_model_loaded() -> bool:
    """Check if ML model exists and can be loaded."""
    return settings.ML_MODEL_PATH.exists()


def get_model():
    """Load or return cached serialized scikit-learn intent classifier."""
    global _cached_model
    if _cached_model is None:
        if not settings.ML_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Trained model not found at {settings.ML_MODEL_PATH}. "
                "Run `python ml/train.py` to train the classifier."
            )
        logger.info("Loading intent classification model from %s", settings.ML_MODEL_PATH)
        _cached_model = joblib.load(settings.ML_MODEL_PATH)
    return _cached_model


def get_model_metadata() -> dict:
    """Load or return cached model metadata."""
    global _cached_metadata
    if _cached_metadata is None:
        if settings.ML_METADATA_PATH.exists():
            try:
                with open(settings.ML_METADATA_PATH, "r", encoding="utf-8") as f:
                    _cached_metadata = json.load(f)
            except Exception as err:
                logger.warning("Could not read metadata: %s", err)
                _cached_metadata = {}
        else:
            _cached_metadata = {}
    return _cached_metadata

import logging
from typing import Dict, Any
from app.ml.model_loader import get_model

logger = logging.getLogger(__name__)

# Fallback default when query is completely empty
DEFAULT_INTENT = "GENERAL_QUERY"


def classify_intent(query: str) -> Dict[str, Any]:
    """
    Classifies user query into one of 6 developer intents:
    - CODE_SEARCH
    - CODE_EXPLANATION
    - BUG_ANALYSIS
    - TEST_GENERATION
    - ARCHITECTURE
    - GENERAL_QUERY
    """
    cleaned_query = (query or "").strip()
    if not cleaned_query:
        return {
            "intent": DEFAULT_INTENT,
            "confidence": 1.0,
            "probabilities": {DEFAULT_INTENT: 1.0}
        }

    try:
        model = get_model()
        pred = model.predict([cleaned_query])[0]
        probs = model.predict_proba([cleaned_query])[0]
        classes = model.classes_

        prob_dict = {
            cls_name: round(float(prob), 4)
            for cls_name, prob in zip(classes, probs)
        }
        confidence = round(float(max(probs)), 4)

        return {
            "intent": str(pred),
            "confidence": confidence,
            "probabilities": prob_dict
        }
    except Exception as err:
        logger.error("Intent classification failed for '%s': %s", cleaned_query, err)
        return {
            "intent": DEFAULT_INTENT,
            "confidence": 0.5,
            "probabilities": {DEFAULT_INTENT: 0.5}
        }

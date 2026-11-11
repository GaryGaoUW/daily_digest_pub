from typing import Any, Dict

MOCK_RESPONSES: Dict[str, Dict[str, Any]] = {
    "news": {
        "tickers": ["TSLA", "CNQ.TO"],
        "top": [
            "[MOCK] World leaders meet to close the climate finance gap.",
            "[MOCK] A new open-source model tops a coding benchmark.",
            "[MOCK] Fed officials signal patience on rate cuts.",
        ],
        "items": [
            {"ref": 0, "category": "world", "headline": "[MOCK] Leaders meet to discuss climate finance",
             "summary": "[MOCK] Leaders discussed how to fund climate adaptation in developing countries."},
            {"ref": 1, "category": "tech", "headline": "[MOCK] New open-source model tops coding benchmark",
             "summary": "[MOCK] An open-source model took the lead on a widely used coding benchmark."},
            {"ref": 2, "category": "finance", "headline": "[MOCK] Fed officials signal patience on rates",
             "summary": "[MOCK] Several Fed officials said they are in no hurry to cut rates."},
        ],
    },
    "market": {
        "overview": "[MOCK] US indexes closed slightly higher led by tech; the TSX dipped as commodities fell.",
        "highlights": [
            {"symbol": "NVDA", "note": "[MOCK] Among the top gainers, leading the tech sector."},
            {"symbol": "SHOP.TO", "note": "[MOCK] Reports earnings this week; volatility may rise."},
        ],
    },
    "reading": {
        "title": "[MOCK] Why sleep matters more than you think",
        "passage": (
            "Scientists have long suspected that sleep plays a role in memory, but only recently have they "
            "begun to understand how. During deep sleep, the brain replays the events of the day, "
            "strengthening the connections that matter and pruning those that do not."
        ),
        "sentences": [
            {"en": "Scientists have long suspected that sleep plays a role in memory, but only recently have they begun to understand how.",
             "plain": "Scientists long thought sleep helps memory, but they only recently started to see how it works."},
            {"en": "During deep sleep, the brain replays the events of the day, strengthening the connections that matter and pruning those that do not.",
             "plain": "In deep sleep the brain goes over the day again, keeping useful links and removing useless ones."},
        ],
        "skeleton": [
            {
                "sentence": "but only recently have they begun to understand how.",
                "subject": "they",
                "predicate": "have begun",
                "object": "to understand how",
                "modifiers": [{"text": "only recently", "role": "time adverbial at the front, triggers inversion"}],
                "note": "When 'only + adverbial' starts a clause, the auxiliary 'have' moves before the subject.",
            }
        ],
        "collocations": [
            {"phrase": "play a role in", "meaning": "to be involved in or contribute to",
             "usage": "More neutral than 'cause'; it signals contribution, not direct causation.",
             "example": "Diet plays a key role in long-term health."},
        ],
    },
}

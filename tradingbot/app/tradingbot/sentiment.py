"""Stimmungsanalyse für Schlagzeilen. Ergebnis je Text: -1 (sehr negativ) bis +1 (sehr positiv)."""
from __future__ import annotations

import json
import logging
import math
import os
import re

log = logging.getLogger(__name__)

# Kleines Finanz-Lexikon (englisch + deutsch). Gewichte grob von -3 bis +3.
LEXICON: dict[str, float] = {
    # positiv
    "beat": 2, "beats": 2, "surge": 2.5, "surges": 2.5, "soar": 2.5, "soars": 2.5, "jump": 1.5, "jumps": 1.5,
    "rally": 2, "rallies": 2, "record": 1.5, "upgrade": 2, "upgraded": 2, "outperform": 2, "growth": 1,
    "profit": 1.5, "profits": 1.5, "strong": 1, "gain": 1.5, "gains": 1.5, "raises": 1.5, "raised": 1,
    "bullish": 2, "buyback": 1.5, "dividend": 1, "approval": 2, "approved": 2, "partnership": 1,
    "expands": 1, "breakthrough": 2.5, "rebound": 1.5, "optimistic": 1.5, "exceeds": 2, "tops": 1.5,
    "steigt": 1.5, "gewinn": 1.5, "rekord": 1.5, "übertrifft": 2, "hochgestuft": 2, "erholung": 1.5,
    # negativ
    "miss": -2, "misses": -2, "plunge": -3, "plunges": -3, "crash": -3, "tumble": -2.5, "tumbles": -2.5,
    "fall": -1.5, "falls": -1.5, "drop": -1.5, "drops": -1.5, "slump": -2, "downgrade": -2, "downgraded": -2,
    "loss": -1.5, "losses": -1.5, "weak": -1, "lawsuit": -2, "probe": -1.5, "investigation": -2,
    "fraud": -3, "recall": -2, "layoffs": -1.5, "bankruptcy": -3, "default": -2.5, "warning": -1.5,
    "warns": -2, "cuts": -1.5, "bearish": -2, "sanctions": -1.5, "tariff": -1, "tariffs": -1.5,
    "war": -2, "attack": -2, "recession": -2.5, "inflation": -1, "selloff": -2, "sell-off": -2,
    "fine": -1.5, "fined": -2, "halt": -1.5, "halted": -2, "delay": -1, "delayed": -1, "hack": -2,
    "breach": -2, "strike": -1, "crisis": -2.5, "fears": -1.5, "uncertainty": -1,
    "fällt": -1.5, "verlust": -1.5, "einbruch": -2.5, "krise": -2.5, "warnung": -1.5, "krieg": -2,
    "herabgestuft": -2, "insolvenz": -3, "klage": -2, "rezession": -2.5,
}
NEGATIONS = {"not", "no", "never", "without", "nicht", "kein", "keine", "ohne"}
WORD = re.compile(r"[a-zäöüß\-]+")


def lexicon_score(text: str) -> float:
    words = WORD.findall(text.lower())
    total = 0.0
    for i, w in enumerate(words):
        v = LEXICON.get(w)
        if v is None:
            continue
        if any(x in NEGATIONS for x in words[max(0, i - 3):i]):
            v = -0.5 * v
        total += v
    return math.tanh(total / 4)


class SentimentEngine:
    def __init__(self, engine: str = "lexicon", model: str = "claude-haiku-5-5"):
        self.engine = engine
        self.model = model
        self._client = None
        if engine == "claude":
            if not os.getenv("ANTHROPIC_API_KEY"):
                log.warning("ANTHROPIC_API_KEY fehlt, nutze Lexikon-Analyse.")
                self.engine = "lexicon"
            else:
                import anthropic
                self._client = anthropic.Anthropic()

    def score_many(self, texts: list[str]) -> list[float]:
        if not texts:
            return []
        if self.engine == "claude":
            try:
                return self._claude_scores(texts)
            except Exception as e:  # Netzwerk/API-Fehler dürfen den Bot nicht stoppen
                log.warning("Claude-Sentiment fehlgeschlagen (%s), nutze Lexikon.", e)
        return [lexicon_score(t) for t in texts]

    def _claude_scores(self, texts: list[str]) -> list[float]:
        numbered = "\n".join(f"{i}: {t[:400]}" for i, t in enumerate(texts))
        prompt = (
            "Bewerte für jede der folgenden Finanznachrichten, wie sie den Aktienkurs der genannten "
            "Firma (oder bei allgemeinen Nachrichten den Gesamtmarkt) kurzfristig beeinflusst. "
            "Skala von -1 (sehr negativ) bis 1 (sehr positiv), 0 = neutral. "
            'Antworte nur mit JSON: {"scores": [zahl, ...]} in derselben Reihenfolge.\n\n' + numbered
        )
        msg = self._client.messages.create(
            model=self.model, max_tokens=1024, messages=[{"role": "user", "content": prompt}]
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        scores = json.loads(text[text.index("{"): text.rindex("}") + 1])["scores"]
        if len(scores) != len(texts):
            raise ValueError("Anzahl der Bewertungen passt nicht")
        return [max(-1.0, min(1.0, float(s))) for s in scores]

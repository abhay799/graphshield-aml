"""Durable test-only model classes serialized by CI fixture generation."""

from __future__ import annotations

import numpy as np


class DeterministicBooster:
    def __init__(self, feature_names: list[str]) -> None:
        self._feature_names = list(feature_names)

    def feature_name(self) -> list[str]:
        return list(self._feature_names)

    def predict(self, data, pred_contrib: bool = False):
        values = np.asarray(data, dtype=float)
        if values.ndim == 1:
            values = values.reshape(1, -1)
        if pred_contrib:
            signs = np.where(np.arange(values.shape[1]) % 2 == 0, 0.01, -0.01)
            return np.column_stack((np.tile(signs, (values.shape[0], 1)), np.zeros(values.shape[0])))
        return np.full(values.shape[0], 0.8)


class DeterministicGraphModel:
    def __init__(self, feature_names: list[str]) -> None:
        self.feature_name_ = list(feature_names)
        self.booster_ = DeterministicBooster(feature_names)

    def predict_proba(self, data):
        positive = np.full(len(data), 0.8)
        return np.column_stack((1.0 - positive, positive))


class DeterministicCalibrator:
    def predict_proba(self, scores):
        values = np.asarray(scores, dtype=float).reshape(-1)
        return np.column_stack((1.0 - values, values))

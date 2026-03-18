"""
Machine Learning Engine — training, prediction, and model management.

Supports Random Forest, Gradient Boosting, and LSTM models.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

from config.settings import get_settings
from database.session import get_session
from database import repository as repo
from ml_models.features import build_features, get_feature_columns
from utils.logging_config import get_logger

logger = get_logger("ml_engine")


class MLEngine:
    """Manages ML model training, evaluation, and prediction."""

    def __init__(self):
        self._settings = get_settings()
        self._model_dir = Path(self._settings.ml_model_dir)
        self._model_dir.mkdir(parents=True, exist_ok=True)
        self._models: Dict[str, Any] = {}
        self._scalers: Dict[str, StandardScaler] = {}

    # ── Training ────────────────────────────────────────────────────────

    async def train_model(self, df: pd.DataFrame, symbol: str,
                          model_type: str = "random_forest") -> dict:
        """
        Train a model on OHLCV data for a symbol.
        Returns performance metrics.
        """
        feat_df = build_features(df)
        if len(feat_df) < 100:
            logger.warning("Insufficient data for training", symbol=symbol, rows=len(feat_df))
            return {"error": "Insufficient data"}

        feature_cols = get_feature_columns(feat_df)
        X = feat_df[feature_cols].values
        y = feat_df["target"].values

        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Time-series cross-validation
        tscv = TimeSeriesSplit(n_splits=5)
        scores = []

        for train_idx, val_idx in tscv.split(X_scaled):
            X_train, X_val = X_scaled[train_idx], X_scaled[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            model = self._create_model(model_type)
            model.fit(X_train, y_train)
            preds = model.predict(X_val)
            scores.append(accuracy_score(y_val, preds))

        # Final model on training data only (avoid data leakage)
        split_idx = int(len(X_scaled) * 0.8)
        X_train_final = X_scaled[:split_idx]
        y_train_final = y[:split_idx]
        X_test = X_scaled[split_idx:]
        y_test = y[split_idx:]

        model = self._create_model(model_type)
        model.fit(X_train_final, y_train_final)

        # Evaluate on held-out test set
        y_pred = model.predict(X_test)

        metrics = {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "precision": float(precision_score(y_test, y_pred, zero_division=0)),
            "recall": float(recall_score(y_test, y_pred, zero_division=0)),
            "f1": float(f1_score(y_test, y_pred, zero_division=0)),
            "cv_mean_accuracy": float(np.mean(scores)),
            "cv_std_accuracy": float(np.std(scores)),
            "training_samples": len(X_scaled),
        }

        # Save model and scaler
        model_key = f"{symbol}_{model_type}"
        model_path = self._model_dir / f"{model_key}.pkl"
        scaler_path = self._model_dir / f"{model_key}_scaler.pkl"
        joblib.dump(model, model_path)
        joblib.dump(scaler, scaler_path)

        self._models[model_key] = model
        self._scalers[model_key] = scaler

        # Save to database
        session = await get_session()
        try:
            await repo.save_ml_model_record(
                session,
                model_name=model_key,
                model_type=model_type,
                symbol=symbol,
                accuracy=metrics["accuracy"],
                precision_score=metrics["precision"],
                recall_score=metrics["recall"],
                f1_score=metrics["f1"],
                parameters=json.dumps(metrics),
                file_path=str(model_path),
                is_active=True,
            )
        finally:
            await session.close()

        logger.info("Model trained", symbol=symbol, model_type=model_type, metrics=metrics)
        return metrics

    def _create_model(self, model_type: str):
        if model_type == "random_forest":
            return RandomForestClassifier(
                n_estimators=200, max_depth=10, min_samples_split=20,
                min_samples_leaf=10, random_state=42, n_jobs=-1,
            )
        elif model_type == "gradient_boosting":
            return GradientBoostingClassifier(
                n_estimators=150, max_depth=5, learning_rate=0.05,
                min_samples_split=20, random_state=42,
            )
        else:
            raise ValueError(f"Unknown model type: {model_type}")

    # ── Prediction ──────────────────────────────────────────────────────

    def predict(self, df: pd.DataFrame, symbol: str,
                model_type: str = "random_forest") -> Optional[Dict]:
        """
        Predict using a trained model.
        Returns prediction dict with direction and probability.
        """
        model_key = f"{symbol}_{model_type}"
        model = self._models.get(model_key)
        scaler = self._scalers.get(model_key)

        if model is None or scaler is None:
            model, scaler = self._load_model(model_key)
            if model is None:
                return None

        feat_df = build_features(df)
        if feat_df.empty:
            return None

        feature_cols = get_feature_columns(feat_df)
        X_latest = feat_df[feature_cols].iloc[[-1]].values
        X_scaled = scaler.transform(X_latest)

        pred = model.predict(X_scaled)[0]
        proba = model.predict_proba(X_scaled)[0]

        # Handle models trained on single class (only one column in proba)
        if len(proba) == 1:
            return {
                "direction": "BUY" if pred == 1 else "SELL",
                "probability": float(proba[0]),
                "buy_prob": float(proba[0]) if pred == 1 else 0.0,
                "sell_prob": float(proba[0]) if pred == 0 else 0.0,
            }

        return {
            "direction": "BUY" if pred == 1 else "SELL",
            "probability": float(max(proba)),
            "buy_prob": float(proba[1]) if len(proba) > 1 else float(proba[0]),
            "sell_prob": float(proba[0]),
        }

    def _load_model(self, model_key: str) -> Tuple[Any, Any]:
        """Load model and scaler from disk."""
        model_path = self._model_dir / f"{model_key}.pkl"
        scaler_path = self._model_dir / f"{model_key}_scaler.pkl"
        if model_path.exists() and scaler_path.exists():
            model = joblib.load(model_path)
            scaler = joblib.load(scaler_path)
            self._models[model_key] = model
            self._scalers[model_key] = scaler
            logger.info("Model loaded", model_key=model_key)
            return model, scaler
        return None, None

    # ── Signal filtering ────────────────────────────────────────────────

    def filter_signal(self, df: pd.DataFrame, symbol: str,
                      signal_direction: str,
                      model_type: str = "random_forest",
                      min_probability: float = 0.55) -> bool:
        """
        Use ML to confirm/reject a signal.
        Returns True if ML agrees with the signal direction.
        """
        prediction = self.predict(df, symbol, model_type)
        if prediction is None:
            return True  # No model available, don't filter

        if prediction["direction"] == signal_direction:
            return prediction["probability"] >= min_probability
        return False

    # ── Batch training ──────────────────────────────────────────────────

    async def train_all_pairs(self, data: Dict[str, pd.DataFrame],
                              model_type: str = "random_forest") -> Dict[str, dict]:
        """Train models for all available pairs."""
        results = {}
        for symbol, df in data.items():
            try:
                metrics = await self.train_model(df, symbol, model_type)
                results[symbol] = metrics
            except Exception as e:
                logger.error("Training failed", symbol=symbol, error=str(e))
                results[symbol] = {"error": str(e)}
        return results

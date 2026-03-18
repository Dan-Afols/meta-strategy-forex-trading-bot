"""
LSTM model for time-series price prediction.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from config.settings import get_settings
from utils.logging_config import get_logger

logger = get_logger("lstm_model")

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


if TORCH_AVAILABLE:
    class LSTMNet(nn.Module):
        """LSTM neural network for price direction prediction."""

        def __init__(self, input_size: int, hidden_size: int = 64,
                     num_layers: int = 2, dropout: float = 0.2):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                dropout=dropout,
                batch_first=True,
            )
            self.fc1 = nn.Linear(hidden_size, 32)
            self.relu = nn.ReLU()
            self.dropout = nn.Dropout(dropout)
            self.fc2 = nn.Linear(32, 2)  # Binary classification

        def forward(self, x):
            lstm_out, _ = self.lstm(x)
            last_hidden = lstm_out[:, -1, :]
            out = self.fc1(last_hidden)
            out = self.relu(out)
            out = self.dropout(out)
            out = self.fc2(out)
            return out


class LSTMPredictor:
    """LSTM-based predictor for time-series forecasting."""

    def __init__(self, sequence_length: int = 30):
        self.sequence_length = sequence_length
        self._settings = get_settings()
        self._model_dir = Path(self._settings.ml_model_dir)
        self._models = {}

    def _prepare_sequences(self, features: np.ndarray,
                           targets: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Create sequences for LSTM input."""
        X, y = [], []
        for i in range(self.sequence_length, len(features)):
            X.append(features[i - self.sequence_length:i])
            y.append(targets[i])
        return np.array(X), np.array(y)

    async def train(self, df: pd.DataFrame, symbol: str,
                    epochs: int = 50, batch_size: int = 32) -> dict:
        """Train LSTM model."""
        if not TORCH_AVAILABLE:
            return {"error": "PyTorch not available"}

        from ml_models.features import build_features, get_feature_columns
        from sklearn.preprocessing import StandardScaler

        feat_df = build_features(df)
        if len(feat_df) < self.sequence_length + 50:
            return {"error": "Insufficient data for LSTM training"}

        feature_cols = get_feature_columns(feat_df)
        X_raw = feat_df[feature_cols].values
        y_raw = feat_df["target"].values

        # Scale
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X_raw)

        # Create sequences
        X_seq, y_seq = self._prepare_sequences(X_scaled, y_raw)

        # Split
        split = int(len(X_seq) * 0.8)
        X_train, X_test = X_seq[:split], X_seq[split:]
        y_train, y_test = y_seq[:split], y_seq[split:]

        # Convert to tensors
        X_train_t = torch.FloatTensor(X_train)
        y_train_t = torch.LongTensor(y_train)
        X_test_t = torch.FloatTensor(X_test)
        y_test_t = torch.LongTensor(y_test)

        train_dataset = TensorDataset(X_train_t, y_train_t)
        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=False)

        # Model
        input_size = X_train.shape[2]
        model = LSTMNet(input_size=input_size)
        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

        # Training
        model.train()
        for epoch in range(epochs):
            total_loss = 0
            for batch_X, batch_y in train_loader:
                optimizer.zero_grad()
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

        # Evaluate
        model.eval()
        with torch.no_grad():
            test_outputs = model(X_test_t)
            _, predicted = torch.max(test_outputs, 1)
            accuracy = (predicted == y_test_t).float().mean().item()

        # Save
        model_key = f"{symbol}_lstm"
        model_path = self._model_dir / f"{model_key}.pt"
        torch.save({
            "model_state": model.state_dict(),
            "input_size": input_size,
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist(),
        }, model_path)

        self._models[model_key] = (model, scaler)
        logger.info("LSTM trained", symbol=symbol, accuracy=accuracy)

        return {"accuracy": accuracy, "epochs": epochs, "samples": len(X_seq)}

    def predict(self, df: pd.DataFrame, symbol: str) -> Optional[dict]:
        """Predict using trained LSTM model."""
        if not TORCH_AVAILABLE:
            return None

        from ml_models.features import build_features, get_feature_columns
        from sklearn.preprocessing import StandardScaler

        model_key = f"{symbol}_lstm"
        cached = self._models.get(model_key)

        if cached:
            model, scaler = cached
        else:
            model_path = self._model_dir / f"{model_key}.pt"
            if not model_path.exists():
                return None
            checkpoint = torch.load(model_path, weights_only=True)
            model = LSTMNet(input_size=checkpoint["input_size"])
            model.load_state_dict(checkpoint["model_state"])
            scaler = StandardScaler()
            scaler.mean_ = np.array(checkpoint["scaler_mean"])
            scaler.scale_ = np.array(checkpoint["scaler_scale"])
            self._models[model_key] = (model, scaler)

        feat_df = build_features(df)
        if len(feat_df) < self.sequence_length:
            return None

        feature_cols = get_feature_columns(feat_df)
        X_raw = feat_df[feature_cols].tail(self.sequence_length).values
        X_scaled = scaler.transform(X_raw)
        X_tensor = torch.FloatTensor(X_scaled).unsqueeze(0)

        model.eval()
        with torch.no_grad():
            output = model(X_tensor)
            proba = torch.softmax(output, dim=1).numpy()[0]

        return {
            "direction": "BUY" if proba[1] > proba[0] else "SELL",
            "probability": float(max(proba)),
            "buy_prob": float(proba[1]),
            "sell_prob": float(proba[0]),
        }

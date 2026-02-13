"""
Hybrid LSTM+Transformer Model
===============================
Architecture: LSTM layers -> Transformer encoder -> Dense output.
LSTM captures sequential patterns, Transformer captures long-range dependencies.
Output: probability of bullish movement (sigmoid).
"""

import logging

import tensorflow as tf
from tensorflow import keras
from keras import layers

from config.settings import LSTM_LAYERS, ML_CONFIG, TRANSFORMER_CONFIG

logger = logging.getLogger(__name__)


class TransformerEncoderBlock(layers.Layer):
    """Single Transformer encoder block with multi-head attention + feed-forward."""

    def __init__(self, d_model: int, n_heads: int, ff_dim: int, dropout: float = 0.1, **kwargs):
        super().__init__(**kwargs)
        self.attention = layers.MultiHeadAttention(
            num_heads=n_heads, key_dim=d_model // n_heads,
        )
        self.ffn = keras.Sequential([
            layers.Dense(ff_dim, activation='relu'),
            layers.Dense(d_model),
        ])
        self.layernorm1 = layers.LayerNormalization(epsilon=1e-6)
        self.layernorm2 = layers.LayerNormalization(epsilon=1e-6)
        self.dropout1 = layers.Dropout(dropout)
        self.dropout2 = layers.Dropout(dropout)

    def call(self, inputs, training=False):
        # Multi-head self-attention + residual
        attn_output = self.attention(inputs, inputs, training=training)
        attn_output = self.dropout1(attn_output, training=training)
        out1 = self.layernorm1(inputs + attn_output)

        # Feed-forward + residual
        ffn_output = self.ffn(out1)
        ffn_output = self.dropout2(ffn_output, training=training)
        return self.layernorm2(out1 + ffn_output)

    def get_config(self):
        config = super().get_config()
        config.update({
            'd_model': self.attention.key_dim * self.attention.num_heads,
            'n_heads': self.attention.num_heads,
            'ff_dim': self.ffn.layers[0].units,
            'dropout': self.dropout1.rate,
        })
        return config


class HybridLSTMTransformer:
    """Hybrid LSTM + Transformer model for price direction prediction."""

    def __init__(
        self,
        lstm1_units: int = LSTM_LAYERS['lstm1_units'],
        lstm2_units: int = LSTM_LAYERS['lstm2_units'],
        dropout_rate: float = LSTM_LAYERS['dropout_rate'],
        n_heads: int = TRANSFORMER_CONFIG['n_heads'],
        d_model: int = TRANSFORMER_CONFIG['d_model'],
        ff_dim: int = TRANSFORMER_CONFIG['ff_dim'],
        transformer_dropout: float = TRANSFORMER_CONFIG['transformer_dropout'],
        dense_units: int = TRANSFORMER_CONFIG['dense_units'],
        learning_rate: float = ML_CONFIG['learning_rate'],
    ):
        self.lstm1_units = lstm1_units
        self.lstm2_units = lstm2_units
        self.dropout_rate = dropout_rate
        self.n_heads = n_heads
        self.d_model = d_model
        self.ff_dim = ff_dim
        self.transformer_dropout = transformer_dropout
        self.dense_units = dense_units
        self.learning_rate = learning_rate
        self.model: keras.Model | None = None

    def build(self, input_shape: tuple[int, int]) -> keras.Model:
        """Build the hybrid LSTM+Transformer model.

        Args:
            input_shape: (lookback_window, n_features).

        Returns:
            Compiled Keras model.
        """
        inputs = layers.Input(shape=input_shape)

        # LSTM branch: captures sequential patterns
        x = layers.LSTM(
            self.lstm1_units, return_sequences=True,
            name='lstm_1',
        )(inputs)
        x = layers.Dropout(self.dropout_rate)(x)
        x = layers.LSTM(
            self.lstm2_units, return_sequences=True,
            name='lstm_2',
        )(x)
        x = layers.Dropout(self.dropout_rate)(x)

        # Project LSTM output to d_model dimension for Transformer
        x = layers.Dense(self.d_model, name='projection')(x)

        # Transformer encoder: captures long-range dependencies
        x = TransformerEncoderBlock(
            d_model=self.d_model,
            n_heads=self.n_heads,
            ff_dim=self.ff_dim,
            dropout=self.transformer_dropout,
            name='transformer_encoder',
        )(x)

        # Global average pooling over the sequence dimension
        x = layers.GlobalAveragePooling1D()(x)

        # Dense classification head
        x = layers.Dense(self.dense_units, activation='relu', name='dense_head')(x)
        x = layers.Dropout(self.dropout_rate)(x)
        outputs = layers.Dense(1, activation='sigmoid', name='output')(x)

        self.model = keras.Model(inputs=inputs, outputs=outputs, name='hybrid_lstm_transformer')

        self.model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=self.learning_rate),
            loss='binary_crossentropy',
            metrics=['accuracy'],
        )

        logger.info(f"Model built: input_shape={input_shape}, params={self.model.count_params():,}")
        return self.model

    def summary(self) -> str:
        """Return model summary as string."""
        if self.model is None:
            return "Model not built yet."
        string_list = []
        self.model.summary(print_fn=lambda x: string_list.append(x))
        return "\n".join(string_list)

    def predict(self, X) -> float:
        """Predict bullish probability for a single sample.

        Args:
            X: Input array of shape (1, lookback_window, n_features).

        Returns:
            Probability of bullish movement (0-1).
        """
        if self.model is None:
            raise RuntimeError("Model not built. Call build() first.")
        return float(self.model.predict(X, verbose=0)[0][0])

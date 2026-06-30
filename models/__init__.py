def __getattr__(name):
    if name == "HybridLSTMTransformer":
        from models.hybrid_model import HybridLSTMTransformer
        return HybridLSTMTransformer
    if name == "ModelTrainer":
        from models.trainer import ModelTrainer
        return ModelTrainer
    if name == "PricePredictor":
        from models.predictor import PricePredictor
        return PricePredictor
    raise AttributeError(f"module 'models' has no attribute {name!r}")

__all__ = ['HybridLSTMTransformer', 'ModelTrainer', 'PricePredictor']

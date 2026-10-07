import numpy as np

def interaction_features(X, center, scale):
    composition = X[:, 13:26]
    environment = np.tanh((X[:, 42:66] - center) / scale)
    interactions = (composition[:, :, np.newaxis] * environment[:, np.newaxis, :]).reshape((X.shape[0], 312))
    return np.concatenate((composition, environment, interactions), axis=1)

def fit(X_train,y_train):
    fractions = X_train[:, 13:22]
    remaining = np.maximum(0.0, 1.0 - np.sum(fractions, axis=1))
    coverage = np.column_stack((fractions, remaining))
    prevalence = np.mean(coverage, axis=0)
    rarity = np.sum(coverage / np.sqrt(prevalence + 0.02), axis=1)
    weights = np.clip(rarity / np.mean(rarity), 0.5, 2.0)
    weights = weights / np.mean(weights)
    center = np.mean(X_train[:, 42:66], axis=0)
    scale = np.maximum(np.std(X_train[:, 42:66], axis=0), 1.0e-8)
    features = interaction_features(X_train, center, scale)
    base = train_model("e011", X_train[:, :42], y_train, {})
    trend = train_model("ridge", features, y_train, {"alpha": 100.0}, sample_weight=weights)
    residual = y_train - trend.predict(features)
    correction = train_model("catboost", X_train, residual, {"iterations": 900, "depth": 6, "learning_rate": 0.04, "l2_leaf_reg": 8.0, "loss_function": "RMSE", "subsample": 0.85}, sample_weight=weights)
    return (base, trend, correction, center, scale)

def predict(state,X_eval):
    base, trend, correction, center, scale = state
    features = interaction_features(X_eval, center, scale)
    return 0.65 * base.predict(X_eval[:, :42]) + 0.35 * (trend.predict(features) + correction.predict(X_eval))

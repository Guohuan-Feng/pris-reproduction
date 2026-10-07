import numpy as np

def basis(X, center, scale):
    comp = X[:, 13:26]
    env = np.tanh((X[:, [42, 43, 48, 49, 54, 55, 60, 61]] - center) / scale)
    gate = (X[:, 17] > 0).astype(float)
    products = (comp[:, :, np.newaxis] * env[:, np.newaxis, :] * gate[:, np.newaxis, np.newaxis]).reshape((X.shape[0], 104))
    return np.concatenate((comp, env, products), axis=1)

def fit(X_train, y_train):
    env = X_train[:, [42, 43, 48, 49, 54, 55, 60, 61]]
    center = np.mean(env, axis=0)
    scale = np.maximum(np.std(env, axis=0), 1e-8)
    fractions = X_train[:, 13:22]
    remainder = np.maximum(1.0 - np.sum(fractions, axis=1), 0.0)
    coverage = np.column_stack((fractions, remainder))
    prevalence = np.mean(coverage, axis=0)
    weights = np.sum(coverage / np.sqrt(prevalence + 0.02), axis=1)
    weights = weights / np.mean(weights)
    weights = np.clip(weights, 0.5, 2.0)
    weights = weights / np.mean(weights)
    trend_X = basis(X_train, center, scale)
    base = train_model("e011", X_train[:, :42], y_train, {})
    trend = train_model("ridge", trend_X, y_train, {"alpha": 100.0}, sample_weight=weights)
    residual = y_train - trend.predict(trend_X)
    nonlinear = train_model("catboost", X_train, residual, {"iterations": 900, "depth": 6, "learning_rate": 0.04, "l2_leaf_reg": 8.0, "loss_function": "RMSE", "subsample": 0.85}, sample_weight=weights)
    return (base, trend, nonlinear, center, scale)

def predict(state, X_eval):
    base, trend, nonlinear, center, scale = state
    return 0.65 * base.predict(X_eval[:, :42]) + 0.35 * (trend.predict(basis(X_eval, center, scale)) + nonlinear.predict(X_eval))

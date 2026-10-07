import numpy as np

def trend_basis(X, center, scale):
    composition = X[:, 13:26]
    environment = np.tanh((X[:, [42,43,48,49,54,55,60,61]] - center) / scale)
    gate = (X[:, 17] > 0).astype(float)
    products = (composition[:, :, None] * environment[:, None, :] * gate[:, None, None]).reshape((X.shape[0], 104))
    return np.column_stack((composition, environment, products))

def fit(X_train,y_train):
    environment = X_train[:, [42,43,48,49,54,55,60,61]]
    center = np.mean(environment, axis=0)
    scale = np.maximum(np.std(environment, axis=0), 1e-8)
    basis = trend_basis(X_train, center, scale)
    base = train_model("e011", X_train[:, :42], y_train, {})
    trend = train_model("ridge", basis, y_train, {"alpha": 100.0})
    fractions = X_train[:, 13:22]
    remainder = np.maximum(1.0 - np.sum(fractions, axis=1), 0.0)
    coverage = np.column_stack((fractions, remainder))
    prevalence = np.mean(coverage, axis=0)
    scores = np.sum(coverage / np.sqrt(prevalence + 0.02), axis=1)
    weights = np.clip(scores / np.mean(scores), 0.5, 2.0)
    weights = weights / np.mean(weights)
    residual = y_train - trend.predict(basis)
    correction = train_model("catboost", X_train, residual, {"iterations": 900, "depth": 6, "learning_rate": 0.04, "l2_leaf_reg": 8.0, "loss_function": "RMSE", "subsample": 0.85}, sample_weight=weights)
    return (base, trend, correction, center, scale)

def predict(state,X_eval):
    base, trend, correction, center, scale = state
    basis = trend_basis(X_eval, center, scale)
    return 0.65 * base.predict(X_eval[:, :42]) + 0.35 * (trend.predict(basis) + correction.predict(X_eval))

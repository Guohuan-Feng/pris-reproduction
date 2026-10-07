import numpy as np

def trend_basis(X, center, scale):
    composition = X[:, 13:26]
    environment = np.tanh((X[:, [42,43,48,49,54,55,60,61]] - center) / scale)
    oxygen = (X[:, 17] > 0).astype(float)
    interactions = (composition[:, :, None] * environment[:, None, :] * oxygen[:, None, None]).reshape((X.shape[0], 104))
    curvature = environment * environment
    return np.concatenate((composition, environment, interactions, curvature), axis=1)

def fit(X_train,y_train):
    environment = X_train[:, [42,43,48,49,54,55,60,61]]
    center = np.mean(environment, axis=0)
    scale = np.maximum(np.std(environment, axis=0), 1e-8)
    basis = trend_basis(X_train, center, scale)
    trend = train_model("ridge", basis, y_train, {"alpha": 100.0})
    residual = y_train - trend.predict(basis)
    correction = train_model("catboost", X_train, residual, {"iterations": 900, "depth": 6, "learning_rate": 0.04, "l2_leaf_reg": 8.0, "loss_function": "RMSE", "subsample": 0.85})
    baseline = train_model("e011", X_train[:, :42], y_train, {})
    return (center, scale, trend, correction, baseline)

def predict(state,X_eval):
    center, scale, trend, correction, baseline = state
    basis = trend_basis(X_eval, center, scale)
    return 0.65 * baseline.predict(X_eval[:, :42]) + 0.35 * (trend.predict(basis) + correction.predict(X_eval))

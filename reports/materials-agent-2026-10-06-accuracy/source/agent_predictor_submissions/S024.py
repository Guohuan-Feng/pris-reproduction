import numpy as np

def trend_basis(X, center, scale):
    composition = X[:, 13:26]
    environment = np.tanh((X[:, [42,43,48,49,54,55,60,61]] - center) / scale)
    oxygen = (X[:, 17] > 0).astype(float)
    products = (composition[:, :, None] * environment[:, None, :] * oxygen[:, None, None]).reshape(X.shape[0], 104)
    return np.concatenate((composition, environment, products), axis=1)

def fit(X_train,y_train):
    environment = X_train[:, [42,43,48,49,54,55,60,61]]
    center = np.mean(environment, axis=0)
    scale = np.maximum(np.std(environment, axis=0), 1e-8)
    basis = trend_basis(X_train, center, scale)
    trend = train_model("ridge", basis, y_train, {"alpha": 100.0})
    residual = y_train - trend.predict(basis)
    residual_scale = max(float(np.median(np.abs(residual))), 0.05)
    magnitude = np.abs(residual / residual_scale)
    transformed = np.sign(residual) * np.log(magnitude + np.sqrt(1.0 + magnitude * magnitude))
    nonlinear = train_model("catboost", X_train, transformed, {"iterations": 900, "depth": 6, "learning_rate": 0.04, "l2_leaf_reg": 8.0, "loss_function": "RMSE", "subsample": 0.85})
    baseline = train_model("e011", X_train[:, :42], y_train, {})
    return (center, scale, residual_scale, trend, nonlinear, baseline)

def predict(state,X_eval):
    center, scale, residual_scale, trend, nonlinear, baseline = state
    basis = trend_basis(X_eval, center, scale)
    transformed = nonlinear.predict(X_eval)
    residual = 0.5 * residual_scale * (np.exp(transformed) - np.exp(-transformed))
    return 0.65 * baseline.predict(X_eval[:, :42]) + 0.35 * (trend.predict(basis) + residual)

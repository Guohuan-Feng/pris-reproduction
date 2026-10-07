import numpy as np

def trend_basis(X, center, scale):
    composition = X[:, 13:26]
    environment = np.tanh((X[:, [42,43,48,49,54,55,60,61]] - center) / scale)
    oxygen = (X[:, 17] > 0).astype(float)
    products = (composition[:, :, np.newaxis] * environment[:, np.newaxis, :] * oxygen[:, np.newaxis, np.newaxis]).reshape((X.shape[0], 104))
    return np.concatenate((composition, environment, products), axis=1)

def fit(X_train,y_train):
    environment = X_train[:, [42,43,48,49,54,55,60,61]]
    center = np.mean(environment, axis=0)
    scale = np.maximum(np.std(environment, axis=0), 1e-8)
    basis = trend_basis(X_train, center, scale)
    base = train_model("e011", X_train[:, :42], y_train, {})
    trend = train_model("ridge", basis, y_train, {"alpha": 100.0})
    residual = y_train - trend.predict(basis)
    nonlinear = train_model("catboost", X_train, residual, {"iterations": 900, "depth": 6, "learning_rate": 0.04, "l2_leaf_reg": 8.0, "loss_function": "RMSE", "subsample": 0.85})
    return (base, trend, nonlinear, center, scale)

def predict(state,X_eval):
    base, trend, nonlinear, center, scale = state
    basis = trend_basis(X_eval, center, scale)
    return 0.65 * base.predict(X_eval[:, :42]) + 0.35 * (trend.predict(basis) + nonlinear.predict(X_eval))

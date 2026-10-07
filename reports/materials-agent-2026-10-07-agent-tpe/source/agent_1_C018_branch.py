import numpy as np

def trend_basis(X, center, scale):
    composition = X[:, 13:26]
    environment = np.tanh((X[:, [42,43,48,49,54,55,60,61]] - center) / scale)
    products = (composition[:, :, np.newaxis] * environment[:, np.newaxis, :]).reshape((X.shape[0], 104))
    return np.concatenate((composition, environment, products), axis=1)

def fit(X_train,y_train):
    environment = X_train[:, [42,43,48,49,54,55,60,61]]
    center = np.mean(environment, axis=0)
    scale = np.maximum(np.std(environment, axis=0), 1e-8)
    basis = trend_basis(X_train, center, scale)
    target = y_train
    trend = train_model("ridge", basis, target, {"alpha": 30.0})
    residual = target - trend.predict(basis)
    nonlinear = train_model("catboost", X_train, residual, {'iterations': 1200, 'depth': 6, 'learning_rate': 0.05, 'l2_leaf_reg': 4.0, 'loss_function': 'RMSE', 'subsample': 0.85})
    return (trend, nonlinear, center, scale)

def predict(state,X_eval):
    trend, nonlinear, center, scale = state
    basis = trend_basis(X_eval, center, scale)
    branch = trend.predict(basis) + nonlinear.predict(X_eval)
    return branch

import numpy as np

def fit(X_train,y_train):
    fractions = X_train[:, 13:22]
    remainder = np.maximum(0.0, 1.0 - np.sum(fractions, axis=1))
    composition = np.column_stack((fractions, remainder))
    prevalence = np.mean(composition, axis=0)
    rarity = np.sum(composition / np.sqrt(prevalence + 0.02), axis=1)
    weights = rarity / np.mean(rarity)
    weights = np.clip(weights, 0.5, 2.0)
    weights = weights / np.mean(weights)
    base = train_model("e011", X_train[:, :42], y_train, {})
    linear = train_model("ridge", X_train[:, 13:26], y_train, {"alpha": 10.0}, sample_weight=weights)
    residual = y_train - linear.predict(X_train[:, 13:26])
    nonlinear = train_model("catboost", X_train, residual, {"iterations": 900, "depth": 6, "learning_rate": 0.04, "l2_leaf_reg": 8.0, "loss_function": "RMSE", "subsample": 0.85}, sample_weight=weights)
    return (base, linear, nonlinear)

def predict(state,X_eval):
    return 0.65 * state[0].predict(X_eval[:, :42]) + 0.35 * (state[1].predict(X_eval[:, 13:26]) + state[2].predict(X_eval))

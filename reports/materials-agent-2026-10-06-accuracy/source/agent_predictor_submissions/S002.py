import numpy as np

def composition_weights(X):
    fractions = X[:, 13:22]
    remainder = np.maximum(1.0 - np.sum(fractions, axis=1), 0.0)
    components = np.column_stack((fractions, remainder))
    prevalence = np.mean(components, axis=0)
    rarity = np.sum(components / np.sqrt(prevalence[None, :] + 0.02), axis=1)
    weights = np.clip(rarity / np.mean(rarity), 0.5, 2.0)
    return weights / np.mean(weights)

def fit(X_train,y_train):
    weights = composition_weights(X_train)
    base = train_model("e011", X_train[:, :42], y_train, {})
    square = train_model("catboost", X_train, y_train, {"iterations": 900, "depth": 6, "learning_rate": 0.04, "l2_leaf_reg": 8.0, "loss_function": "RMSE", "subsample": 0.85}, sample_weight=weights)
    robust = train_model("catboost", X_train, y_train, {"iterations": 900, "depth": 6, "learning_rate": 0.04, "l2_leaf_reg": 8.0, "loss_function": "Huber:delta=0.5", "subsample": 0.85}, sample_weight=weights)
    return (base, square, robust)

def predict(state,X_eval):
    return 0.65 * state[0].predict(X_eval[:, :42]) + 0.20 * state[1].predict(X_eval) + 0.15 * state[2].predict(X_eval)

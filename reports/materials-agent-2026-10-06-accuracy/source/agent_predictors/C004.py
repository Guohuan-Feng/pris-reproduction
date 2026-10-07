import numpy as np

def coverage_weights(X):
    fractions = X[:, 13:22]
    remaining = np.maximum(0.0, 1.0 - np.sum(fractions, axis=1))
    composition = np.column_stack((fractions, remaining))
    prevalence = np.mean(composition, axis=0)
    rarity = np.sum(composition / np.sqrt(prevalence + 0.02), axis=1)
    normalized = rarity / np.mean(rarity)
    bounded = np.clip(normalized, 0.5, 2.0)
    return bounded / np.mean(bounded)

def fit(X_train,y_train):
    base = train_model("e011", X_train[:, :42], y_train, {})
    oxygen = X_train[:, 17] > 0.0
    weights = coverage_weights(X_train)
    wo = weights[oxygen] / np.mean(weights[oxygen])
    wn = weights[np.logical_not(oxygen)] / np.mean(weights[np.logical_not(oxygen)])
    params = {"iterations": 900, "depth": 6, "learning_rate": 0.04, "l2_leaf_reg": 8.0, "loss_function": "RMSE", "subsample": 0.85}
    oxygen_model = train_model("catboost", X_train[oxygen], y_train[oxygen], params, sample_weight=wo)
    no_oxygen_model = train_model("catboost", X_train[np.logical_not(oxygen)], y_train[np.logical_not(oxygen)], params, sample_weight=wn)
    return (base, oxygen_model, no_oxygen_model)

def predict(state,X_eval):
    oxygen = X_eval[:, 17] > 0.0
    specialist = np.where(oxygen, state[1].predict(X_eval), state[2].predict(X_eval))
    return 0.65 * state[0].predict(X_eval[:, :42]) + 0.35 * specialist

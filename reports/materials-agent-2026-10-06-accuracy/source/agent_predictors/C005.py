import numpy as np

def fit(X_train,y_train):
    fractions = X_train[:,13:22]
    remainder = np.maximum(0.0, 1.0 - np.sum(fractions, axis=1))
    composition = np.column_stack((fractions, remainder))
    prevalence = np.mean(composition, axis=0)
    rarity = np.sum(composition / np.sqrt(prevalence + 0.02), axis=1)
    weights = rarity / np.mean(rarity)
    weights = np.clip(weights, 0.5, 2.0)
    weights = weights / np.mean(weights)
    oxygen = X_train[:,17] > 0.0
    oxygen_weights = weights * np.where(oxygen, 1.0, 0.25)
    oxygen_weights = oxygen_weights / np.mean(oxygen_weights)
    other_weights = weights * np.where(oxygen, 0.25, 1.0)
    other_weights = other_weights / np.mean(other_weights)
    base = train_model("e011", X_train[:,:42], y_train, {})
    oxygen_model = train_model("catboost", X_train, y_train, {"iterations":900,"depth":6,"learning_rate":0.04,"l2_leaf_reg":8.0,"loss_function":"RMSE","subsample":0.85}, sample_weight=oxygen_weights)
    other_model = train_model("catboost", X_train, y_train, {"iterations":900,"depth":6,"learning_rate":0.04,"l2_leaf_reg":8.0,"loss_function":"RMSE","subsample":0.85}, sample_weight=other_weights)
    return (base, oxygen_model, other_model)

def predict(state,X_eval):
    base, oxygen_model, other_model = state
    oxygen = X_eval[:,17] > 0.0
    correction = np.where(oxygen, oxygen_model.predict(X_eval), other_model.predict(X_eval))
    return 0.65 * base.predict(X_eval[:,:42]) + 0.35 * correction

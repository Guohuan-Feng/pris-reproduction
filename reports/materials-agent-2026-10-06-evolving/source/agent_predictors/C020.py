import numpy as np

def fit(X_train,y_train):
    base = train_model("e011", X_train[:, :66], y_train, {})
    transformed = np.sign(y_train) * np.log1p(np.abs(y_train))
    booster = train_model("hgb", X_train, transformed, {"max_iter": 300, "max_leaf_nodes": 15, "min_samples_leaf": 20, "learning_rate": 0.05, "l2_regularization": 10.0, "loss": "squared_error"})
    return (base, booster)

def predict(state,X_eval):
    base_prediction = state[0].predict(X_eval[:, :66])
    transformed_prediction = state[1].predict(X_eval)
    booster_prediction = np.sign(transformed_prediction) * np.expm1(np.abs(transformed_prediction))
    return 0.8 * base_prediction + 0.2 * booster_prediction

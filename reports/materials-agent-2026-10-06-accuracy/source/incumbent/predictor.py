import numpy as np

def fit(X_train,y_train):
    base = train_model("e011", X_train, y_train, {})
    target = np.sign(y_train) * np.log1p(np.abs(y_train))
    booster = train_model("hgb", X_train, target, {"max_iter": 300, "max_leaf_nodes": 15, "min_samples_leaf": 20, "learning_rate": 0.05, "l2_regularization": 10, "loss": "squared_error"})
    return (base, booster)

def predict(state,X_eval):
    base = state[0].predict(X_eval)
    transformed = state[1].predict(X_eval)
    restored = np.sign(transformed) * np.expm1(np.abs(transformed))
    return 0.8 * base + 0.2 * restored

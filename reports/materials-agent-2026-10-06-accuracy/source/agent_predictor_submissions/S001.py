import numpy as np

def fit(X_train,y_train):
    anchor = train_model("e011", X_train[:, :42], y_train, {})
    squared = train_model("catboost", X_train, y_train, {"iterations": 1000, "depth": 6, "learning_rate": 0.035, "l2_leaf_reg": 8.0, "loss_function": "RMSE", "subsample": 0.85})
    robust = train_model("catboost", X_train, y_train, {"iterations": 1000, "depth": 6, "learning_rate": 0.035, "l2_leaf_reg": 8.0, "loss_function": "Huber:delta=0.5", "subsample": 0.85})
    return (anchor, squared, robust)

def predict(state,X_eval):
    anchor = state[0].predict(X_eval[:, :42])
    squared = state[1].predict(X_eval)
    robust = state[2].predict(X_eval)
    return 0.65 * anchor + 0.20 * squared + 0.15 * robust

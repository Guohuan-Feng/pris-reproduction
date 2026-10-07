def fit(X_train,y_train):
    base = train_model("e011", X_train, y_train, {})
    median = train_model("hgb", X_train, y_train, {"loss": "absolute_error", "max_iter": 200, "max_leaf_nodes": 15, "min_samples_leaf": 20, "learning_rate": 0.05, "l2_regularization": 1.0})
    return {"base": base, "median": median}

def predict(state,X_eval):
    return 0.8 * state["base"].predict(X_eval) + 0.2 * state["median"].predict(X_eval)

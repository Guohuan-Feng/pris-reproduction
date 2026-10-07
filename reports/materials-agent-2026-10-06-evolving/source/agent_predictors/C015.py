def fit(X_train,y_train):
    routed = train_model("e011", X_train, y_train, {})
    randomized = train_model("extra_trees", X_train, y_train, {"n_estimators": 400, "min_samples_leaf": 3, "max_features": 0.8})
    return (routed, randomized)

def predict(state,X_eval):
    return 0.8 * state[0].predict(X_eval) + 0.2 * state[1].predict(X_eval)

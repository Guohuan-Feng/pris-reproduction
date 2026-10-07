def fit(X_train,y_train):
    return train_model("e011", X_train, y_train, {})

def predict(state,X_eval):
    return state.predict(X_eval)

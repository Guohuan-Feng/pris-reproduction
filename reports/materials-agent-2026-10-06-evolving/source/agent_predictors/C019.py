def fit(X_train,y_train):
    base = train_model('e011', X_train, y_train, {})
    residual = y_train - base.predict(X_train)
    correction = train_model('hgb', X_train, residual, {'max_iter': 300, 'max_leaf_nodes': 15, 'min_samples_leaf': 20, 'learning_rate': 0.05, 'l2_regularization': 10.0, 'loss': 'squared_error'})
    return (base, correction)

def predict(state,X_eval):
    return state[0].predict(X_eval) + 0.2 * state[1].predict(X_eval)

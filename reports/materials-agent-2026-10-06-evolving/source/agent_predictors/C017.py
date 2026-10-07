def fit(X_train,y_train):
    base = train_model('e011', X_train, y_train, {})
    boost = train_model('hgb', X_train, y_train, {'max_iter': 300, 'max_leaf_nodes': 15, 'min_samples_leaf': 20, 'learning_rate': 0.05, 'l2_regularization': 10, 'loss': 'squared_error'})
    return (base, boost)

def predict(state,X_eval):
    return 0.8 * state[0].predict(X_eval) + 0.2 * state[1].predict(X_eval)

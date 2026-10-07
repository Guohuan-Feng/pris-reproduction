import numpy as np

def trend_features(X, center, scale):
    composition = X[:,13:26]
    environment = np.tanh((X[:,[42,43,48,49,54,55,60,61]] - center) / scale)
    oxygen = (X[:,17] > 0).astype(float)
    products = (composition[:,:,None] * environment[:,None,:] * oxygen[:,None,None]).reshape((X.shape[0],104))
    return np.concatenate((composition,environment,products),axis=1)

def fit(X_train,y_train):
    environment = X_train[:,[42,43,48,49,54,55,60,61]]
    center = np.mean(environment,axis=0)
    scale = np.maximum(np.std(environment,axis=0),1e-8)
    fractions = X_train[:,13:22]
    remainder = np.maximum(1.0 - np.sum(fractions,axis=1),0.0)
    coverage = np.column_stack((fractions,remainder))
    prevalence = np.mean(coverage,axis=0)
    weights = np.sum(coverage / np.sqrt(prevalence + 0.02),axis=1)
    weights = weights / np.mean(weights)
    weights = np.clip(weights,0.5,2.0)
    weights = weights / np.mean(weights)
    features = trend_features(X_train,center,scale)
    trend = train_model("ridge",features,y_train,{"alpha":100.0},sample_weight=weights)
    residuals = y_train - trend.predict(features)
    residual = train_model("catboost",X_train,residuals,{"iterations":900,"depth":6,"learning_rate":0.04,"l2_leaf_reg":8.0,"subsample":0.85,"loss_function":"Huber:delta=0.5"},sample_weight=weights)
    base = train_model("e011",X_train[:,:42],y_train,{})
    return (center,scale,trend,residual,base)

def predict(state,X_eval):
    center,scale,trend,residual,base = state
    features = trend_features(X_eval,center,scale)
    return 0.65 * base.predict(X_eval[:,:42]) + 0.35 * (trend.predict(features) + residual.predict(X_eval))

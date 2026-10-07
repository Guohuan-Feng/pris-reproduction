import numpy as np

def trend_basis(X, center, scale):
    composition = X[:,13:26]
    environment = np.tanh((X[:,[44,46,50,52,56,58,62,64]] - center) / scale)
    oxygen = (X[:,17] > 0).astype(float)
    products = (composition[:,:,None] * environment[:,None,:] * oxygen[:,None,None]).reshape((X.shape[0],104))
    return np.concatenate((composition,environment,products),axis=1)

def fit(X_train,y_train):
    environment = X_train[:,[44,46,50,52,56,58,62,64]]
    center = np.mean(environment,axis=0)
    scale = np.maximum(np.std(environment,axis=0),1e-8)
    fractions = X_train[:,13:22]
    remaining = np.maximum(1.0-np.sum(fractions,axis=1),0.0)
    coverage = np.column_stack((fractions,remaining))
    prevalence = np.mean(coverage,axis=0)
    weights = np.sum(coverage / np.sqrt(prevalence[None,:]+0.02),axis=1)
    weights = weights / np.mean(weights)
    weights = np.clip(weights,0.5,2.0)
    weights = weights / np.mean(weights)
    basis = trend_basis(X_train,center,scale)
    trend = train_model("ridge",basis,y_train,{"alpha":100.0},sample_weight=weights)
    residual = y_train - trend.predict(basis)
    nonlinear = train_model("catboost",X_train,residual,{"iterations":900,"depth":6,"learning_rate":0.04,"l2_leaf_reg":8.0,"loss_function":"RMSE","subsample":0.85},sample_weight=weights)
    baseline = train_model("e011",X_train[:,:42],y_train,{})
    return (center,scale,trend,nonlinear,baseline)

def predict(state,X_eval):
    center,scale,trend,nonlinear,baseline = state
    basis = trend_basis(X_eval,center,scale)
    return 0.65*baseline.predict(X_eval[:,:42])+0.35*(trend.predict(basis)+nonlinear.predict(X_eval))

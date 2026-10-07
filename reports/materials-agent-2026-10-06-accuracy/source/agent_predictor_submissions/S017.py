import numpy as np

def trend_basis(X, center, scale):
    composition = X[:,13:26]
    environment = np.tanh((X[:,[42,43,48,49,54,55,60,61]] - center) / scale)
    oxygen = (X[:,17] > 0).astype(float)
    products = (composition[:,:,None] * environment[:,None,:] * oxygen[:,None,None]).reshape((X.shape[0],104))
    return np.column_stack((composition, environment, products))

def fit(X_train,y_train):
    center = np.mean(X_train[:,[42,43,48,49,54,55,60,61]], axis=0)
    scale = np.maximum(np.std(X_train[:,[42,43,48,49,54,55,60,61]], axis=0),1e-8)
    basis = trend_basis(X_train,center,scale)
    fractions = X_train[:,13:22]
    remaining = np.maximum(1.0-np.sum(fractions,axis=1),0.0)
    coverage = np.column_stack((fractions,remaining))
    prevalence = np.mean(coverage,axis=0)
    rarity = np.sum(coverage / np.sqrt(prevalence+0.02),axis=1)
    weights = np.clip(rarity / np.mean(rarity),0.5,2.0)
    weights = weights / np.mean(weights)
    baseline = train_model("e011",X_train[:,:42],y_train,{})
    trend = train_model("ridge",basis,y_train,{"alpha":100.0},sample_weight=weights)
    residual = y_train-trend.predict(basis)
    augmented = np.column_stack((X_train,basis[:,21:93]))
    correction = train_model("catboost",augmented,residual,{"iterations":900,"depth":6,"learning_rate":0.04,"l2_leaf_reg":8.0,"loss_function":"RMSE","subsample":0.85},sample_weight=weights)
    return (baseline,trend,correction,center,scale)

def predict(state,X_eval):
    baseline,trend,correction,center,scale = state
    basis = trend_basis(X_eval,center,scale)
    augmented = np.column_stack((X_eval,basis[:,21:93]))
    return 0.65*baseline.predict(X_eval[:,:42])+0.35*(trend.predict(basis)+correction.predict(augmented))

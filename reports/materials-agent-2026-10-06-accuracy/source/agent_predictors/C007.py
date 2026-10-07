import numpy as np

def coverage_weights(X):
    fractions = np.clip(X[:,13:22],0.0,1.0)
    remaining = np.maximum(0.0,1.0-np.sum(fractions,axis=1))
    composition = np.column_stack((fractions,remaining))
    prevalence = np.mean(composition,axis=0)
    score = np.sum(composition / np.sqrt(prevalence + 0.02),axis=1)
    weights = score / np.mean(score)
    weights = np.clip(weights,0.5,2.0)
    return weights / np.mean(weights)

def main_basis(X,center,scale):
    environment = X[:,[42,43,48,49,54,55,60,61]]
    bounded = np.tanh((environment-center)/scale)
    return np.column_stack((X[:,13:26],bounded))

def fit(X_train,y_train):
    environment = X_train[:,[42,43,48,49,54,55,60,61]]
    center = np.mean(environment,axis=0)
    scale = np.maximum(np.std(environment,axis=0),1e-8)
    weights = coverage_weights(X_train)
    base = train_model("e011",X_train[:,:42],y_train,{})
    basis = main_basis(X_train,center,scale)
    trend = train_model("ridge",basis,y_train,{"alpha":100.0},sample_weight=weights)
    residuals = y_train-trend.predict(basis)
    residual_model = train_model("catboost",X_train,residuals,{"iterations":900,"depth":6,"learning_rate":0.04,"l2_leaf_reg":8.0,"loss_function":"RMSE","subsample":0.85},sample_weight=weights)
    return (base,trend,residual_model,center,scale)

def predict(state,X_eval):
    base,trend,residual_model,center,scale = state
    basis = main_basis(X_eval,center,scale)
    return 0.65*base.predict(X_eval[:,:42])+0.35*(trend.predict(basis)+residual_model.predict(X_eval))

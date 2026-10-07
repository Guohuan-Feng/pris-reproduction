import numpy as np

def basis(X,mu,scale):
    c = X[:,13:26]
    e = np.tanh((X[:,[42,43,48,49,54,55,60,61]]-mu)/scale)
    gate = (X[:,17]>0).astype(float)
    products = (c[:,:,None]*e[:,None,:]*gate[:,None,None]).reshape((X.shape[0],104))
    return np.column_stack((c,e,products))

def fit(X_train,y_train):
    env = X_train[:,[42,43,48,49,54,55,60,61]]
    mu = np.mean(env,axis=0)
    scale = np.maximum(np.std(env,axis=0),1e-8)
    presence = (X_train[:,13:26]>0).astype(float)
    keys = np.sum(presence*np.power(2.0,np.arange(13)),axis=1)
    unique_keys,inverse,counts = np.unique(keys,return_inverse=True,return_counts=True)
    w = 1.0/np.sqrt(counts[inverse])
    w = w/np.mean(w)
    w = np.clip(w,0.5,2.0)
    w = w/np.mean(w)
    z = basis(X_train,mu,scale)
    trend = train_model("ridge",z,y_train,{"alpha":100.0},sample_weight=w)
    residual = y_train-trend.predict(z)
    correction = train_model("catboost",X_train,residual,{"iterations":900,"depth":6,"learning_rate":0.04,"l2_leaf_reg":8.0,"loss_function":"RMSE","subsample":0.85},sample_weight=w)
    anchor = train_model("e011",X_train[:,:42],y_train,{})
    return (mu,scale,trend,correction,anchor)

def predict(state,X_eval):
    mu,scale,trend,correction,anchor = state
    z = basis(X_eval,mu,scale)
    return 0.65*anchor.predict(X_eval[:,:42])+0.35*(trend.predict(z)+correction.predict(X_eval))

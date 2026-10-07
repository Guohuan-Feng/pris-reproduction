import numpy as np

def basis(X,mu,sd):
    c = X[:,13:26]
    e = np.tanh((X[:,[42,43,48,49,54,55,60,61]]-mu)/sd)
    p = (c[:,:,None]*e[:,None,:]*(X[:,17]>0)[:,None,None]).reshape((X.shape[0],104))
    return np.concatenate((c,e,p),axis=1)

def attenuate(B,bmu,bsd,precision,cut):
    z = (B-bmu)/bsd
    h = np.maximum(np.sum(np.dot(z,precision)*z,axis=1),0.0)
    a = np.minimum(1.0,np.sqrt(cut/np.maximum(h,1e-12)))
    return np.concatenate((B[:,:13],B[:,13:]*a[:,None]),axis=1)

def fit(X_train,y_train):
    mu = np.mean(X_train[:,[42,43,48,49,54,55,60,61]],axis=0)
    sd = np.maximum(np.std(X_train[:,[42,43,48,49,54,55,60,61]],axis=0),1e-8)
    B = basis(X_train,mu,sd)
    bmu = np.mean(B,axis=0)
    bsd = np.maximum(np.std(B,axis=0),1e-8)
    z = (B-bmu)/bsd
    precision = np.linalg.inv(np.dot(z.T,z)+100.0*np.eye(B.shape[1]))
    h = np.maximum(np.sum(np.dot(z,precision)*z,axis=1),0.0)
    cut = np.maximum(np.quantile(h,0.95),1e-12)
    A = attenuate(B,bmu,bsd,precision,cut)
    f = X_train[:,13:22]
    f = np.concatenate((f,np.maximum(1.0-np.sum(f,axis=1),0.0)[:,None]),axis=1)
    prevalence = np.mean(f,axis=0)
    w = np.sum(f/np.sqrt(prevalence+0.02),axis=1)
    w = w/np.mean(w)
    w = np.clip(w,0.5,2.0)
    w = w/np.mean(w)
    base = train_model("e011",X_train[:,:42],y_train,{})
    trend = train_model("ridge",A,y_train,{"alpha":100.0},sample_weight=w)
    residual = y_train-trend.predict(A)
    model = train_model("catboost",X_train,residual,{"iterations":900,"depth":6,"learning_rate":0.04,"l2_leaf_reg":8.0,"loss_function":"RMSE","subsample":0.85},sample_weight=w)
    return (mu,sd,bmu,bsd,precision,cut,base,trend,model)

def predict(state,X_eval):
    mu,sd,bmu,bsd,precision,cut,base,trend,model = state
    B = basis(X_eval,mu,sd)
    A = attenuate(B,bmu,bsd,precision,cut)
    return 0.65*base.predict(X_eval[:,:42])+0.35*(trend.predict(A)+model.predict(X_eval))

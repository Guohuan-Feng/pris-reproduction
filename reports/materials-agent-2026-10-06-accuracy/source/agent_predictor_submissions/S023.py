import numpy as np

def basis_parts(X, env_mean, env_scale):
    composition = X[:,13:26]
    environment = np.tanh((X[:,[42,43,48,49,54,55,60,61]]-env_mean)/env_scale)
    main = np.concatenate((composition, environment), axis=1)
    products = (composition[:,:,None]*environment[:,None,:]*(X[:,17]>0)[:,None,None]).reshape((X.shape[0],104))
    return main, products

def fit(X_train,y_train):
    env_mean = np.mean(X_train[:,[42,43,48,49,54,55,60,61]],axis=0)
    env_scale = np.maximum(np.std(X_train[:,[42,43,48,49,54,55,60,61]],axis=0),1e-8)
    main, products = basis_parts(X_train,env_mean,env_scale)
    main_mean = np.mean(main,axis=0)
    main_scale = np.maximum(np.std(main,axis=0),1e-8)
    product_mean = np.mean(products,axis=0)
    z = (main-main_mean)/main_scale
    projection = np.linalg.solve(z.T@z+100.0*np.eye(21),z.T@(products-product_mean))
    residual_products = products-product_mean-z@projection
    basis = np.concatenate((main,residual_products),axis=1)
    trend = train_model("ridge",basis,y_train,{"alpha":100.0})
    residual = train_model("catboost",X_train,y_train-trend.predict(basis),{"iterations":900,"depth":6,"learning_rate":0.04,"l2_leaf_reg":8.0,"loss_function":"RMSE","subsample":0.85})
    baseline = train_model("e011",X_train[:,:42],y_train,{})
    return (env_mean,env_scale,main_mean,main_scale,product_mean,projection,trend,residual,baseline)

def predict(state,X_eval):
    env_mean,env_scale,main_mean,main_scale,product_mean,projection,trend,residual,baseline = state
    main, products = basis_parts(X_eval,env_mean,env_scale)
    residual_products = products-product_mean-((main-main_mean)/main_scale)@projection
    basis = np.concatenate((main,residual_products),axis=1)
    return 0.65*baseline.predict(X_eval[:,:42])+0.35*(trend.predict(basis)+residual.predict(X_eval))

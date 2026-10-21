import numpy as np
import pandas as pd
import torch

from bricks.model import LinearRegression
from bricks.scaler import StandardScaler
from bricks.split import train_test_split

FEATURES = ["area", "rooms", "age", "distance"]


def load(path="data/houses.csv"):
    df = pd.read_csv(path)
    return df[FEATURES].to_numpy(float), df["price"].to_numpy(float)


def r2(y, pred):
    return 1 - ((y - pred) ** 2).sum() / ((y - y.mean()) ** 2).sum()


def run(path="data/houses.csv", epochs=400, lr=0.05, seed=0):
    X, y = load(path)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, seed=seed)
    scaler = StandardScaler().fit(X_tr)
    X_tr, X_te = scaler.transform(X_tr), scaler.transform(X_te)
    t = lambda a: torch.tensor(a, dtype=torch.float32)
    model = LinearRegression(X.shape[1], lr=lr)
    losses = model.fit(t(X_tr), t(y_tr).reshape(-1, 1), epochs=epochs)
    pred = model.predict(t(X_te)).numpy().ravel()
    return {"losses": losses, "r2_test": float(r2(y_te, pred)), "mse_test": float(((y_te - pred) ** 2).mean()),
            "n_train": len(X_tr), "n_test": len(X_te), "pred_shape": pred.shape}


if __name__ == "__main__":
    res = run()
    print(f"R² на тесте: {res['r2_test']:.3f}, MSE: {res['mse_test']:.3f}")

import pandas as pd
import torch


def load_points(path="data/points.csv"):
    df = pd.read_csv(path)
    X = torch.tensor(df[["x1", "x2"]].values, dtype=torch.float32)
    y = torch.tensor(df["label"].values, dtype=torch.long)
    return X, y

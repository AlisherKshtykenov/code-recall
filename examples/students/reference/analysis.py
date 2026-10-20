import matplotlib.pyplot as plt
import pandas as pd

from recall import show


def load(path="data/students.csv"):
    return pd.read_csv(path)


def clean(df):
    df = df.dropna(subset=["score"]).copy()
    df["name"] = df["name"].str.strip()
    df["group"] = df["group"].str.strip().str.lower()
    df = df[(df["score"] >= 0) & (df["score"] <= 100)]
    return df.drop_duplicates().reset_index(drop=True)


def summary(df):
    out = df.groupby("group").agg(students=("name", "nunique"), mean_score=("score", "mean"), best=("score", "max"))
    out["mean_score"] = out["mean_score"].round(1)
    return out.sort_values("mean_score", ascending=False)


if __name__ == "__main__":
    df = clean(load())
    show(df.head(10), title="после чистки")
    table = summary(df)
    show(table, title="по группам")
    table["mean_score"].plot.bar(title="средняя оценка по группам")
    plt.tight_layout()
    plt.show()

import matplotlib.pyplot as plt
import torch
import torch.nn.functional as F

from data_utils import load_points
from model import MLP


def train(model, X, y, steps=200, lr=0.05):
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    losses = []
    for _ in range(steps):
        optimizer.zero_grad()
        loss = F.cross_entropy(model(X), y)
        loss.backward()
        optimizer.step()
        losses.append(loss.item())
    return losses


if __name__ == "__main__":
    torch.manual_seed(0)
    X, y = load_points()
    model = MLP()
    losses = train(model, X, y)
    acc = (model(X).argmax(1) == y).float().mean().item()
    print(f"лосс {losses[0]:.3f} -> {losses[-1]:.3f}, точность {acc:.1%}")
    plt.plot(losses)
    plt.title("лосс по шагам")
    plt.show()
    torch.save(model.state_dict(), "results/mlp.pt")

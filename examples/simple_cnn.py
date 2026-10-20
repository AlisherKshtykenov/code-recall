import torch
import torch.nn as nn
import torch.nn.functional as F


# Простая свёрточная сеть для CIFAR-10
class SimpleCNN(nn.Module):
    def __init__(self, num_classes=10):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 16, 3, padding=1)
        self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
        self.pool = nn.MaxPool2d(2)
        self.fc = nn.Linear(32 * 8 * 8, num_classes)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        return self.fc(x.flatten(1))


model = SimpleCNN()
optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
X = torch.randn(64, 3, 32, 32)
y = torch.randint(0, 10, (64,))

for epoch in range(5):
    optimizer.zero_grad()
    loss = F.cross_entropy(model(X), y)
    loss.backward()
    optimizer.step()
    print(epoch, loss.item())

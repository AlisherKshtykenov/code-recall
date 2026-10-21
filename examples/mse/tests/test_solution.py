import torch

from solution import loss


def test_value():
    assert torch.isclose(loss(torch.tensor([1.0, 2.0, 3.0]), torch.tensor([1.0, 4.0, 0.0])), torch.tensor(13 / 3))

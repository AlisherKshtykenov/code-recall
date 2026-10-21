import torch

from solution import loss


def test_quadratic_near_zero():
    assert torch.isclose(loss(torch.tensor([0.5]), torch.tensor([0.0])), torch.tensor(0.125))


def test_linear_far():
    assert torch.isclose(loss(torch.tensor([3.0]), torch.tensor([0.0])), torch.tensor(2.5))

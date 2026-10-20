import torch

from model import MLP


def test_output_shape(seed):
    model = MLP()
    assert model(torch.randn(8, 2)).shape == (8, 2)


def test_parameter_count():
    assert sum(p.numel() for p in MLP().parameters()) == 1218


def test_custom_sizes():
    model = MLP(in_dim=3, hidden=16, out_dim=4)
    assert model(torch.randn(5, 3)).shape == (5, 4)

"""normalize против torchvision.transforms.functional.normalize (значения, dtype, inplace, ошибки, градиенты)
и compute_mean_std против прямого подсчёта torch по всем пикселям каждого канала."""
import pytest
import torch
import torchvision.transforms.functional as TF
from torch.utils.data import DataLoader, TensorDataset

from likelib import assert_like, close
from solution import compute_mean_std, normalize

torch.manual_seed(0)
MEAN3, STD3 = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]  # статистики ImageNet


@pytest.mark.parametrize("shape, mean, std", [
    ((3, 8, 8), MEAN3, STD3),          # одна картинка RGB
    ((4, 3, 8, 8), MEAN3, STD3),       # батч
    ((2, 5, 3, 6, 6), MEAN3, STD3),    # видео: (B, T, C, H, W)
    ((1, 16, 16), [0.5], [0.25]),      # серая картинка
    ((2, 1, 64, 64), 0.5, 0.25),       # числа вместо списков
    ((3, 4, 4), (0.1, 0.2, 0.3), (1.0, 2.0, 3.0)),  # кортежи
    ((0, 3, 4, 4), MEAN3, STD3),       # пустой батч
    ((3, 4, 4), MEAN3, [-0.2, 0.3, 0.5]),  # отрицательный std разрешён (просто меняет знак)
])
def test_values_like_torchvision(shape, mean, std):
    assert_like(normalize, TF.normalize, torch.rand(shape), mean, std)


@pytest.mark.parametrize("dtype", [torch.float16, torch.float32, torch.float64])
def test_dtype_kept(dtype):
    x = torch.rand(2, 3, 5, 5).to(dtype)
    out = normalize(x, MEAN3, STD3)
    assert out.dtype == dtype, f"dtype должен сохраниться: {dtype}, а получился {out.dtype}"
    assert close(out, TF.normalize(x, MEAN3, STD3), rtol=1e-3, atol=1e-3), "значения как у torchvision"


def test_tensor_mean_std():
    assert_like(normalize, TF.normalize, torch.rand(3, 4, 4), torch.tensor(MEAN3), torch.tensor(STD3))


def test_not_inplace_keeps_input():
    x = torch.rand(3, 4, 4)
    before = x.clone()
    out = normalize(x, MEAN3, STD3)
    assert out is not x and torch.equal(x, before), "inplace=False: вход не меняется, результат — новый тензор"


def test_inplace_changes_input_and_returns_it():
    x = torch.rand(3, 4, 4)
    want = TF.normalize(x.clone(), MEAN3, STD3)
    out = normalize(x, MEAN3, STD3, inplace=True)
    assert out is x and torch.allclose(x, want), "inplace=True: меняется сам вход, он же и возвращается"


@pytest.mark.parametrize("x, mean, std", [
    (torch.randint(0, 255, (3, 4, 4), dtype=torch.uint8), MEAN3, STD3),  # uint8 — сначала во float
    (torch.rand(4, 4), [0.5], [0.2]),                                     # нет оси каналов
    (torch.rand(3, 4, 4), MEAN3, [0.2, 0.0, 0.2]),                        # std = 0
    (torch.rand(3, 4, 4), [0.5] * 2, [0.2] * 2),                          # каналов в mean меньше
    ([1.0, 2.0], [1.0], [1.0]),                                           # не тензор
])
def test_errors_like_torchvision(x, mean, std):
    assert_like(normalize, TF.normalize, x, mean, std)


def test_gradient_like_torchvision():
    base = torch.rand(2, 3, 5, 5)
    a, b = base.clone().requires_grad_(), base.clone().requires_grad_()
    w = torch.rand(2, 3, 5, 5)
    (normalize(a, MEAN3, STD3) * w).sum().backward()
    (TF.normalize(b, MEAN3, STD3) * w).sum().backward()
    assert torch.allclose(a.grad, b.grad), "градиент по входу как у torchvision: w / std"


def reference_stats(x, unbiased=False):
    per_channel = x.transpose(0, 1).reshape(x.shape[1], -1).double()
    return per_channel.mean(dim=1).float(), per_channel.std(dim=1, unbiased=unbiased).float()


@pytest.mark.parametrize("shape", [(10, 3, 8, 8), (1, 1, 4, 4), (7, 2, 3, 5)])
@pytest.mark.parametrize("unbiased", [False, True])
def test_mean_std_of_tensor(shape, unbiased):
    x = torch.rand(shape) * 3 + 1
    mean, std = compute_mean_std(x, unbiased=unbiased)
    want_mean, want_std = reference_stats(x, unbiased)
    assert mean.shape == (shape[1],) and torch.allclose(mean, want_mean, atol=1e-5), "mean каждого канала по всем пикселям"
    assert torch.allclose(std, want_std, atol=1e-5), "std каждого канала по всем пикселям"


@pytest.mark.parametrize("batch_size", [1, 3, 8, 32])
def test_mean_std_from_loader_equals_full(batch_size):
    x, y = torch.rand(20, 3, 6, 6), torch.randint(0, 2, (20,))
    loader = DataLoader(TensorDataset(x, y), batch_size=batch_size)
    mean, std = compute_mean_std(loader)
    want_mean, want_std = reference_stats(x)
    assert torch.allclose(mean, want_mean, atol=1e-5) and torch.allclose(std, want_std, atol=1e-5), "по батчам — то же, что по всему датасету"


def test_normalized_data_has_zero_mean_unit_std():
    x = torch.rand(16, 3, 10, 10) * torch.tensor([1.0, 5.0, 0.2]).view(1, 3, 1, 1)
    mean, std = compute_mean_std(x)
    z = normalize(x, mean, std)
    m, s = reference_stats(z)
    assert torch.allclose(m, torch.zeros(3), atol=1e-4) and torch.allclose(s, torch.ones(3), atol=1e-4), "после normalize: mean 0, std 1 в каждом канале"


def test_constant_channel_has_zero_std():
    x = torch.rand(4, 2, 3, 3)
    x[:, 1] = 0.7
    _, std = compute_mean_std(x)
    assert std[1] == 0, "у константного канала std = 0 (и normalize тогда откажет — делить нельзя)"


def test_empty_dataset_is_error():
    with pytest.raises(ValueError):
        compute_mean_std([])

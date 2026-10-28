"""normalize_images своими руками: normalize — как torchvision.transforms.functional.normalize,
compute_mean_std — mean и std каждого канала по всему датасету (их и передают в normalize)."""
import torch


def normalize(tensor, mean, std, inplace=False):
    """(x - mean[c]) / std[c] для каждого канала c. Картинка — (..., C, H, W)."""
    if not isinstance(tensor, torch.Tensor):  # работаем только с тензорами
        raise TypeError(f"img should be Tensor Image. Got {type(tensor)}")
    if not tensor.is_floating_point():  # uint8 0..255 сначала переведите в float (to_dtype / 255)
        raise TypeError(f"Input tensor should be a float tensor. Got {tensor.dtype}.")
    if tensor.ndim < 3:  # нужны хотя бы каналы, высота и ширина
        raise ValueError(f"Expected tensor to be a tensor image of size (..., C, H, W). Got tensor.size() = {tensor.size()}")
    if not inplace:
        tensor = tensor.clone()  # не трогаем вход (градиент через clone проходит)
    mean = torch.as_tensor(mean, dtype=tensor.dtype, device=tensor.device)  # список, кортеж, число, тензор -> тензор нужного dtype
    std = torch.as_tensor(std, dtype=tensor.dtype, device=tensor.device)
    if (std == 0).any():  # деление на ноль (в т.ч. после округления в float16)
        raise ValueError(f"std evaluated to zero after conversion to {tensor.dtype}, leading to division by zero.")
    if mean.ndim == 1:
        mean = mean.view(-1, 1, 1)  # (C,) -> (C, 1, 1): вычитается из каждого пикселя своего канала
    if std.ndim == 1:
        std = std.view(-1, 1, 1)
    return tensor.sub_(mean).div_(std)  # на месте: в копии или (inplace=True) в самом входе


def _batches(data):
    """Тензор (N, C, H, W) или итерируемое из батчей (тензоры или пары (x, y), как в DataLoader)."""
    if isinstance(data, torch.Tensor):
        yield data
        return
    for batch in data:
        yield batch[0] if isinstance(batch, (tuple, list)) else batch  # из (x, y) берём x


def compute_mean_std(data, unbiased=False):
    """mean и std каждого канала по всем картинкам и пикселям: два тензора формы (C,).
    Считается по батчам (весь датасет в память не нужен): суммы x и x² в float64."""
    total = total_sq = None  # Σx и Σx² по каждому каналу
    count = 0  # сколько пикселей в канале
    for x in _batches(data):
        if x.ndim != 4:
            raise ValueError(f"нужны батчи (N, C, H, W), а пришло {tuple(x.shape)}")
        x = x.to(torch.float64)  # точность накопления
        per_channel = x.transpose(0, 1).reshape(x.shape[1], -1)  # (C, N·H·W): все пиксели канала в строку
        s, sq = per_channel.sum(dim=1), (per_channel * per_channel).sum(dim=1)
        total, total_sq = (s, sq) if total is None else (total + s, total_sq + sq)
        count += per_channel.shape[1]
    if count == 0:
        raise ValueError("пустой датасет: не по чему считать mean и std")
    mean = total / count  # E[x]
    var = (total_sq / count - mean * mean).clamp(min=0)  # E[x²] − E[x]² (clamp — от ошибок округления)
    if unbiased:
        if count < 2:
            raise ValueError("для unbiased=True нужно хотя бы 2 пикселя")
        var = var * count / (count - 1)  # поправка Бесселя
    return mean.to(torch.float32), var.sqrt().to(torch.float32)

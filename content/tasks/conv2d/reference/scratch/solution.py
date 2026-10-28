"""conv2d своими руками — как torch.nn.functional.conv2d: stride, padding (число, пара, "same", "valid"), dilation, groups.
Идея: вырезать все окна (unfold), умножить каждое окно на каждое ядро и сложить (einsum)."""
import torch


def _pair(v):
    return (v, v) if isinstance(v, int) else tuple(v)  # 2 -> (2, 2), (2, 1) -> (2, 1)


def conv2d(input, weight, bias=None, stride=1, padding=0, dilation=1, groups=1):
    """input (N, C_in, H, W) или (C_in, H, W); weight (C_out, C_in/groups, kH, kW); bias (C_out,) -> (N, C_out, H_out, W_out)."""
    unbatched = input.dim() == 3
    if unbatched:
        input = input.unsqueeze(0)  # одна картинка -> батч из одной
    if input.dim() != 4:
        raise RuntimeError(f"Expected 3D (unbatched) or 4D (batched) input to conv2d, but got input of size: {list(input.shape)}")
    N, C, H, W = input.shape
    C_out, C_per_group, kh, kw = weight.shape
    if C != C_per_group * groups:  # каналов входа должно хватить на все группы
        raise RuntimeError(f"Given groups={groups}, weight of size {list(weight.shape)}, expected input{list(input.shape)} "
                           f"to have {C_per_group * groups} channels, but got {C} channels instead")
    if C_out % groups:
        raise RuntimeError(f"Given groups={groups}, expected weight to be divisible by {groups} at dimension 0")
    sh, sw = _pair(stride)
    dh, dw = _pair(dilation)

    if isinstance(padding, str):
        if padding == "valid":
            top = bottom = left = right = 0  # без отступов
        elif padding == "same":  # выход того же размера, что вход
            if (sh, sw) != (1, 1):
                raise RuntimeError("padding='same' is not supported for strided convolutions")
            total_h, total_w = dh * (kh - 1), dw * (kw - 1)  # сколько всего добавить по высоте и ширине
            top, left = total_h // 2, total_w // 2  # при нечётной сумме лишний ряд — снизу и справа (как в torch)
            bottom, right = total_h - top, total_w - left
        else:
            raise RuntimeError(f"Invalid padding string: '{padding}'")
    else:
        ph, pw = _pair(padding)
        top = bottom = ph
        left = right = pw

    Hp, Wp = H + top + bottom, W + left + right  # размер после отступов
    eff_h, eff_w = dh * (kh - 1) + 1, dw * (kw - 1) + 1  # размер ядра с учётом dilation (с «дырками»)
    if Hp < eff_h or Wp < eff_w:
        raise RuntimeError(f"Calculated padded input size per channel: ({Hp} x {Wp}). Kernel size: ({eff_h} x {eff_w}). "
                           "Kernel size can't be greater than actual input size")
    padded = input.new_zeros(N, C, Hp, Wp)  # нули вокруг картинки
    padded[:, :, top:top + H, left:left + W] = input  # градиент через присваивание в срез проходит

    windows = padded.unfold(2, eff_h, sh).unfold(3, eff_w, sw)  # (N, C, H_out, W_out, eff_h, eff_w): все окна
    windows = windows[..., ::dh, ::dw]  # dilation: берём каждый dh-й и dw-й пиксель окна -> (…, kh, kw)
    H_out, W_out = windows.shape[2], windows.shape[3]
    windows = windows.reshape(N, groups, C_per_group, H_out, W_out, kh, kw)  # каналы — по группам
    kernels = weight.reshape(groups, C_out // groups, C_per_group, kh, kw)  # ядра — по тем же группам
    # для каждой группы g и ядра o: Σ по каналам c и пикселям окна (i, j) — окно × ядро
    out = torch.einsum("ngchwij,gocij->ngohw", windows, kernels).reshape(N, C_out, H_out, W_out)
    if bias is not None:
        out = out + bias.view(1, -1, 1, 1)  # сдвиг своего канала выхода
    return out.squeeze(0) if unbatched else out

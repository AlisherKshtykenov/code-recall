"""max_pool2d своими руками — как torch.nn.functional.max_pool2d: kernel_size, stride, padding, dilation,
ceil_mode, return_indices. Каждое окно -> его максимум (ничья — первый по порядку, NaN «побеждает»)."""
import torch


def _pair(v):
    return (v, v) if isinstance(v, int) else tuple(v)


def _out_size(L, k, s, p, d, ceil_mode):
    """Сколько окон помещается по оси — по формуле torch (с правилом для ceil_mode)."""
    span = L + 2 * p - d * (k - 1) - 1
    out = (span + (s - 1 if ceil_mode else 0)) // s + 1
    if ceil_mode and (out - 1) * s >= L + p:  # последнее окно должно начинаться внутри картинки или левого отступа
        out -= 1
    return out


def max_pool2d(input, kernel_size, stride=None, padding=0, dilation=1, ceil_mode=False, return_indices=False):
    """input (N, C, H, W) или (C, H, W) -> максимум каждого окна; с return_indices — и где он был (индекс в H·W)."""
    unbatched = input.dim() == 3
    if unbatched:
        input = input.unsqueeze(0)
    if input.dim() != 4:
        raise RuntimeError(f"non-empty 3D or 4D (batch mode) tensor expected for input, but got {list(input.shape)}")
    N, C, H, W = input.shape
    kh, kw = _pair(kernel_size)
    sh, sw = _pair(stride) if stride not in (None, []) else (kh, kw)  # по умолчанию шаг = размеру окна
    ph, pw = _pair(padding)
    dh, dw = _pair(dilation)
    for p, k, d in ((ph, kh, dh), (pw, kw, dw)):
        if p > ((k - 1) * d + 1) // 2:  # отступ не больше половины окна — иначе окно может состоять из одних отступов
            raise RuntimeError(f"pad should be at most half of effective kernel size, but got pad={p}, kernel_size={k} and dilation={d}")
    Ho, Wo = _out_size(H, kh, sh, ph, dh, ceil_mode), _out_size(W, kw, sw, pw, dw, ceil_mode)
    if Ho <= 0 or Wo <= 0:
        raise RuntimeError(f"Given input size: ({C}x{H}x{W}). Calculated output size: ({C}x{Ho}x{Wo}). Output size is too small")

    eff_h, eff_w = dh * (kh - 1) + 1, dw * (kw - 1) + 1  # окно с учётом dilation
    Hp = max((Ho - 1) * sh + eff_h, H + ph)  # высота с отступами (ceil_mode может потребовать больше снизу)
    Wp = max((Wo - 1) * sw + eff_w, W + pw)
    fill = torch.finfo(input.dtype).min if input.is_floating_point() else torch.iinfo(input.dtype).min
    padded = input.new_full((N, C, Hp, Wp), float("-inf") if input.is_floating_point() else fill)  # −inf никогда не максимум
    padded[:, :, ph:ph + H, pw:pw + W] = input  # градиент через присваивание в срез проходит

    windows = padded.unfold(2, eff_h, sh).unfold(3, eff_w, sw)[:, :, :Ho, :Wo, ::dh, ::dw]  # (N, C, Ho, Wo, kh, kw)
    values, arg = windows.reshape(N, C, Ho, Wo, kh * kw).max(dim=-1)  # максимум окна и его номер в окне (первый при ничьей)
    out = values.squeeze(0) if unbatched else values
    if not return_indices:
        return out
    rows = torch.arange(Ho).view(1, 1, Ho, 1) * sh - ph + (arg // kw) * dh  # строка максимума во входе
    cols = torch.arange(Wo).view(1, 1, 1, Wo) * sw - pw + (arg % kw) * dw  # столбец максимума во входе
    indices = rows * W + cols  # плоский индекс в H·W (так его возвращает torch)
    return out, (indices.squeeze(0) if unbatched else indices)

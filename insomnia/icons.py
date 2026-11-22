"""Ay simgesi: tepsi simgeleri ve program simgesi buradan çizilir."""

import math

from PIL import Image, ImageDraw

GRAY = (140, 140, 140)
GOLD = (224, 176, 64)
RED = (255, 123, 107)
ORANGE = (240, 169, 74)
BLUE = (108, 176, 238)
DARK = (27, 27, 29)

ACTION_COLORS = {"none": GOLD, "shutdown": RED, "restart": ORANGE, "hibernate": BLUE}

_STAR = [(22.5, 5.5), (23.5, 8), (26, 9), (23.5, 10), (22.5, 12.5), (21.5, 10), (19, 9), (21.5, 8)]


def _moon_mask(size: int) -> Image.Image:
    """32 birimlik çizim alanında hilal ve yıldız; 4 kat büyük çizilip küçültülür."""
    big = size * 4
    k = big / 27  # şekil 32 birimin 3..26 x 5,5..28,5 bölümünü kaplar; boşluğu kırp

    def p(x, y):
        return ((x - 1.5) * k, (y - 3.5) * k)

    mask = Image.new("L", (big, big), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((*p(14 - 11, 17.5 - 11), *p(14 + 11, 17.5 + 11)), fill=255)
    draw.ellipse((*p(20 - 9, 12.5 - 9), *p(20 + 9, 12.5 + 9)), fill=0)
    draw.polygon([p(x, y) for x, y in _STAR], fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def moon(color=GOLD, size: int = 64) -> Image.Image:
    """Saydam zemin üzerinde tek renk ay (tepsi için)."""
    image = Image.new("RGBA", (size, size), color + (0,))
    image.putalpha(_moon_mask(size))
    return image


TRACK = (74, 74, 78)
RING_STEPS = 32  # halka bu kadar basamakta azalır; simge her saniye yeniden çizilmez


def ring_step(remaining: float, total: float, infinite: bool = False) -> int:
    """Kalan sürenin halkadaki basamağı (0 = boş, RING_STEPS = dolu)."""
    if infinite:
        return RING_STEPS
    if total <= 0 or remaining <= 0:
        return 0
    return max(1, min(RING_STEPS, math.ceil(remaining * RING_STEPS / total)))


def ring_moon(color=GOLD, step: int = RING_STEPS, size: int = 64) -> Image.Image:
    """Çevresinde kalan süreyi gösteren halka olan ay (oturum sürerken tepsi için).

    Halka saat 12'den başlar ve süre azaldıkça saat yönünde kısalır; penceredeki
    kadranla aynı anlamı taşır.
    """
    big = size * 4
    width = big * 3.4 / 32
    box = (width / 2, width / 2, big - 1 - width / 2, big - 1 - width / 2)
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.arc(box, 0, 360, fill=TRACK + (255,), width=round(width))
    step = max(0, min(RING_STEPS, step))
    if step:
        draw.arc(box, -90, -90 + 360 * step / RING_STEPS, fill=color + (255,), width=round(width))
    image = image.resize((size, size), Image.LANCZOS)
    inner = round(size * 0.6)
    offset = (size - inner) // 2
    image.paste(moon(color, inner), (offset, offset), moon(color, inner))
    return image


def app_icon(size: int = 256) -> Image.Image:
    """Koyu, köşeleri yuvarlak kare üzerinde altın ay (exe ve pencere için)."""
    big = size * 4
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.22, fill=DARK + (255,))
    tile = tile.resize((size, size), Image.LANCZOS)
    inner = int(size * 0.66)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    layer.paste(moon(GOLD, inner), ((size - inner) // 2, (size - inner) // 2))
    return Image.alpha_composite(tile, layer)

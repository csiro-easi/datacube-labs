""" Geometric operations on GeoBox class
"""

from typing import Optional, Tuple
from affine import Affine

from ._base import GeoBox

# pylint: disable=invalid-name
MaybeInt = Optional[int]
MaybeFloat = Optional[float]


def flipy(gbox: GeoBox) -> GeoBox:
    """
    :returns: GeoBox covering the same region but with Y-axis flipped
    """
    H, W = gbox.shape
    A = Affine.translation(0, H)*Affine.scale(1, -1)
    A = gbox.affine*A
    return GeoBox(W, H, A, gbox.crs)


def flipx(gbox: GeoBox) -> GeoBox:
    """
    :returns: GeoBox covering the same region but with X-axis flipped
    """
    H, W = gbox.shape
    A = Affine.translation(W, 0)*Affine.scale(-1, 1)
    A = gbox.affine*A
    return GeoBox(W, H, A, gbox.crs)


def translate_pix(gbox: GeoBox, tx: float, ty: float) -> GeoBox:
    """
    Shift GeoBox in pixel plane. (0,0) of the new GeoBox will be at the same
    location as pixel (tx, ty) in the original GeoBox.
    """
    H, W = gbox.shape
    A = gbox.affine*Affine.translation(tx, ty)
    return GeoBox(W, H, A, gbox.crs)


def pad(gbox: GeoBox, padx: int, pady: MaybeInt = None) -> GeoBox:
    """
    Expand GeoBox by fixed number of pixels on each side
    """
    pady = padx if pady is None else pady

    H, W = gbox.shape
    A = gbox.affine*Affine.translation(-padx, -pady)
    return GeoBox(W + padx*2, H + pady*2, A, gbox.crs)


def zoom_out(gbox: GeoBox, factor: float) -> GeoBox:
    """
    factor > 1 --> smaller width/height, fewer but bigger pixels
    factor < 1 --> bigger width/height, more but smaller pixels

    :returns: GeoBox covering the same region but with bigger pixels (i.e. lower resolution)
    """
    from math import ceil

    H, W = (max(1, ceil(s/factor)) for s in gbox.shape)
    A = gbox.affine*Affine.scale(factor, factor)
    return GeoBox(W, H, A, gbox.crs)


def zoom_to(gbox: GeoBox, shape: Tuple[int, int]) -> GeoBox:
    """
    :returns: GeoBox covering the same region but with different number of pixels
              and therefore resolution.
    """
    H, W = gbox.shape
    h, w = shape

    sx, sy = W/float(w), H/float(h)
    A = gbox.affine*Affine.scale(sx, sy)
    return GeoBox(w, h, A, gbox.crs)


def rotate(gbox: GeoBox, deg: float) -> GeoBox:
    """
    Rotate GeoBox around the center.

    It's as if you stick a needle through the center of the GeoBox footprint
    and rotate it counter clock wise by supplied number of degrees.

    Note that from pixel point of view image rotates the other way. If you have
    source image with an arrow pointing right, and you rotate GeoBox 90 degree,
    in that view arrow should point down (this is assuming usual case of inverted
    y-axis)
    """
    h, w = gbox.shape
    c0 = gbox.transform*(w*0.5, h*0.5)
    A = Affine.rotation(deg, c0)*gbox.transform
    return GeoBox(w, h, A, gbox.crs)


def affine_transform_pix(gbox: GeoBox, transform: Affine) -> GeoBox:
    """
    Apply affine transform on pixel side.

    :param transform: Affine matrix mapping from new pixel coordinate space to
    pixel coordinate space of input gbox

    :returns: GeoBox of the same pixel shape but covering different region,
    pixels in the output gbox relate to input geobox via `transform`

    X_old_pix = transform * X_new_pix

    """
    H, W = gbox.shape
    A = gbox.affine*transform
    return GeoBox(W, H, A, gbox.crs)

"""ASCE 7-16 英制公式与工程单位的换算。"""

METERS_PER_FOOT = 0.3048
FEET_PER_METER = 1.0 / METERS_PER_FOOT
# 1 psf = 47.880259 Pa
PASCAL_PER_PSF = 47.88025898033584
KN_PER_M2_PER_PSF = PASCAL_PER_PSF / 1000.0
METERS_PER_SECOND_PER_MPH = 1609.344 / 3600.0
STANDARD_GRAVITY = 9.80665


def to_mps(speed: float, unit: str) -> float:
    if unit == "m/s":
        return speed
    if unit == "km/h":
        return speed / 3.6
    if unit == "mph":
        return speed * METERS_PER_SECOND_PER_MPH
    raise ValueError(f"不能识别风速单位 {unit}。")


def to_kn_m2(value: float, unit: str) -> float:
    if unit == "KN/m2":
        return value
    if unit == "psf":
        return value * KN_PER_M2_PER_PSF
    raise ValueError(f"不能识别面荷载单位 {unit}。")

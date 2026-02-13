from typing import List, Tuple

def clamp(value, lower_bound, upper_bound):
    if value < lower_bound:
        return lower_bound
    if value > upper_bound:
        return upper_bound
    return value


def lerp(ps: Tuple[int, int], pe: Tuple[int, int], percent: float) -> Tuple[int, int]:
    return (
        ps[0] + (pe[0] - ps[0]) * percent,
        ps[1] + (pe[1] - ps[1]) * percent,
    )
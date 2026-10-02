import pytest
from fr_lore_index.sum.add_nums import add_nums

def test_add_nums():
    assert add_nums(2, 3) == 5
    assert add_nums(-1, 1) == 0
    assert add_nums(0, 0) == 0
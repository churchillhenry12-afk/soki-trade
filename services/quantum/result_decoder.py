from __future__ import annotations


def decode_binary_selection(strategy_ids: list[str], bits: list[int]) -> list[str]:
    if len(strategy_ids) != len(bits) or any(bit not in {0, 1} for bit in bits):
        raise ValueError("binary result does not match the strategy universe")
    return [strategy_id for strategy_id, bit in zip(strategy_ids, bits, strict=True) if bit]

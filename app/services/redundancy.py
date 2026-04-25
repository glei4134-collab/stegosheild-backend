"""
抗压缩冗余编码模块

使用三重复制 + 投票机制实现社交媒体压缩 survivability

每个 bit 复制 3 次，提取时使用投票机制恢复
允许最多 1 位错误，即 3 位中有 2 位正确即可恢复
"""

from typing import Tuple


def encode_with_redundancy(payload: bytes, redundancy: int = 3) -> bytes:
    """
    对 payload 添加冗余编码
    
    Args:
        payload: 原始 payload 字节
        redundancy: 冗余次数（默认 3）
    
    Returns:
        带冗余的 payload 字节
    """
    result = bytearray()
    
    for byte in payload:
        # 每个字节的每一位重复 'redundancy' 次
        for i in range(8):
            bit = (byte >> (7 - i)) & 1
            # 将 bit 重复 redundancy 次
            result.extend([bit] * redundancy)
    
    # 添加校验码：原始 payload 的 CRC32
    import zlib
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    result.extend(int_to_bits(crc, 32))
    
    return bytes(result)


def decode_with_redundancy(encoded_payload: bytes, redundancy: int = 3) -> Tuple[bytes, bool]:
    """
    使用投票机制解码冗余编码
    
    Args:
        encoded_payload: 带冗余的 payload 字节
        redundancy: 冗余次数（必须与编码时一致）
    
    Returns:
        (恢复的 payload, 是否校验成功)
    """
    # 移除校验码，获取实际数据位
    total_bits = len(encoded_payload) - 32
    if total_bits < 0 or total_bits % redundancy != 0:
        return b'', False
    
    data_bits = total_bits // redundancy * redundancy
    
    # 提取校验码
    stored_crc = bits_to_int(encoded_payload[data_bits:data_bits + 32])
    
    # 投票恢复每个 bit
    result_bits = []
    for i in range(0, data_bits, redundancy):
        chunk = encoded_payload[i:i + redundancy]
        # 投票：取多数
        bit = 1 if sum(chunk) > redundancy // 2 else 0
        result_bits.append(bit)
    
    # 转换为字节
    payload_bytes = bits_to_bytes(result_bits)
    
    # 验证 CRC
    import zlib
    calculated_crc = zlib.crc32(payload_bytes) & 0xFFFFFFFF
    is_valid = (calculated_crc == stored_crc)
    
    return payload_bytes, is_valid


def int_to_bits(value: int, num_bits: int) -> list:
    """将整数转换为位列表"""
    return [(value >> (num_bits - 1 - i)) & 1 for i in range(num_bits)]


def bits_to_int(bits: list) -> int:
    """将位列表转换为整数"""
    result = 0
    for bit in bits:
        result = (result << 1) | bit
    return result


def bits_to_bytes(bits: list) -> bytes:
    """将位列表转换为字节"""
    result = bytearray()
    for i in range(0, len(bits), 8):
        byte_bits = bits[i:i + 8]
        if len(byte_bits) < 8:
            break
        result.append(bits_to_int(byte_bits))
    return bytes(result)


def calculate_redundancy_overhead(redundancy: int) -> float:
    """计算冗余开销"""
    return redundancy * 8 + 32  # payload bits * redundancy + CRC32


def estimate_capacity_with_redundancy(original_capacity: int, redundancy: int = 3) -> int:
    """
    计算添加冗余后的有效容量
    
    Args:
        original_capacity: 原始容量（字节）
        redundancy: 冗余次数
    
    Returns:
        有效容量（字节）
    """
    # 每个字节变成 8*redundancy 位，加上 32 位 CRC
    overhead_per_byte = redundancy - 1 + 32 / 8
    return int(original_capacity / (overhead_per_byte + 1))
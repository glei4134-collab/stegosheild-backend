"""
增强容量 LSB 隐写
- RGB 三通道
- 2位 LSB
- 支持文本和文件嵌入

API v2:
- 使用长度前缀协议，不再依赖 END_MARKER
- embed_enhanced: 支持 secret_bytes 参数
- extract_enhanced: 返回原始字节数据

Payload 格式: [LENGTH:4][DATA...]
- LENGTH: 4字节大端序，表示后续数据的长度
"""

import io
import struct
import numpy as np
from PIL import Image

LSB_BITS = 2
PAYLOAD_HEADER_SIZE = 4


def _prepare_payload(data: bytes) -> str:
    """将数据转为二进制字符串"""
    return ''.join(f'{b:08b}' for b in data)


def _read_payload(bits_str: str) -> bytes:
    """将二进制字符串转回数据"""
    chars = []
    for i in range(0, len(bits_str) - 7, 8):
        char_bits = bits_str[i:i+8]
        if len(char_bits) == 8:
            chars.append(int(char_bits, 2))
    return bytes(chars)


def embed_enhanced(image_path_or_file, secret_text: str = None, secret_data: bytes = None, file_name: str = None, secret_bytes: bytes = None, lsb_bits: int = LSB_BITS) -> bytes:
    """嵌入数据到图片

    Args:
        image_path_or_file: 图片路径或文件对象
        secret_text: 要嵌入的文本（旧接口兼容）
        secret_data: 要嵌入的原始数据（旧接口兼容，用于文件）
        file_name: 文件名（旧接口兼容）
        secret_bytes: 要嵌入的原始字节数据（新接口，优先使用）
        lsb_bits: LSB 位数

    Returns:
        bytes: 嵌入后的图片数据

    Raises:
        ValueError: 当数据超过容量时
    """
    if hasattr(image_path_or_file, 'read'):
        image_path_or_file.seek(0)
        img = Image.open(image_path_or_file).convert('RGB')
    elif isinstance(image_path_or_file, Image.Image):
        img = image_path_or_file.convert('RGB')
    elif isinstance(image_path_or_file, bytes):
        img = Image.open(io.BytesIO(image_path_or_file)).convert('RGB')
    else:
        img = Image.open(image_path_or_file).convert('RGB')

    arr = np.array(img, dtype=np.uint8)
    h, w = arr.shape[:2]

    if secret_bytes is not None:
        payload_data = secret_bytes
    elif file_name and secret_data:
        payload_data = file_name.encode('utf-8') + b'|||' + secret_data
    else:
        payload_data = secret_text.encode('utf-8')

    payload_with_length = struct.pack('>I', len(payload_data)) + payload_data

    payload_bits = _prepare_payload(payload_with_length)
    payload_len = len(payload_bits)

    capacity_bits = h * w * 3 * lsb_bits
    if payload_len > capacity_bits:
        raise ValueError(f"数据太大: 需要 {payload_len} bits, 最大 {capacity_bits} bits")

    arr_flat = arr.flatten()
    bit_index = 0

    for i in range(len(arr_flat)):
        if bit_index >= payload_len:
            break

        val = int(arr_flat[i])
        new_val = val & ~((1 << lsb_bits) - 1)

        for b in range(lsb_bits):
            if bit_index < payload_len:
                if payload_bits[bit_index] == '1':
                    new_val |= (1 << b)
                bit_index += 1

        arr_flat[i] = np.uint8(new_val)

    arr = arr_flat.reshape(h, w, 3)

    buf = io.BytesIO()
    Image.fromarray(arr, 'RGB').save(buf, format='PNG')
    return buf.getvalue()


def extract_enhanced(image_path_or_file, lsb_bits: int = LSB_BITS) -> bytes:
    """从图片提取数据

    Args:
        image_path_or_file: 图片路径或文件对象

    Returns:
        bytes: 原始 payload 数据

    Raises:
        ValueError: 当数据格式无效时
    """
    if hasattr(image_path_or_file, 'read'):
        image_path_or_file.seek(0)
        img = Image.open(image_path_or_file).convert('RGB')
    elif isinstance(image_path_or_file, bytes):
        img = Image.open(io.BytesIO(image_path_or_file)).convert('RGB')
    else:
        img = Image.open(image_path_or_file).convert('RGB')

    arr = np.array(img, dtype=np.uint8)
    h, w = arr.shape[:2]
    arr_flat = arr.flatten()

    bits = []
    for val in arr_flat:
        for b in range(lsb_bits):
            bits.append(str((val >> b) & 1))

    bits_str = ''.join(bits)
    data = _read_payload(bits_str)

    if len(data) < PAYLOAD_HEADER_SIZE:
        raise ValueError('Payload 数据过短，无法读取长度')

    payload_length = struct.unpack('>I', data[:PAYLOAD_HEADER_SIZE])[0]
    actual_data = data[PAYLOAD_HEADER_SIZE:]

    if payload_length > len(actual_data):
        raise ValueError(f'Payload 长度声明 ({payload_length}) 超过实际数据长度 ({len(actual_data)})')

    return actual_data[:payload_length]


def calculate_capacity(image_path_or_file, lsb_bits: int = LSB_BITS) -> int:
    """计算容量"""
    if hasattr(image_path_or_file, 'read'):
        img = Image.open(image_path_or_file).convert('RGB')
    else:
        img = Image.open(image_path_or_file).convert('RGB')

    arr = np.array(img)
    h, w = arr.shape[:2]
    capacity_bits = h * w * 3 * lsb_bits
    capacity_bytes = capacity_bits // 8
    return capacity_bytes - PAYLOAD_HEADER_SIZE


def embed(image_path_or_file, secret_text: str, method: str = 'lsb') -> bytes:
    """兼容旧接口"""
    return embed_enhanced(image_path_or_file, secret_text=secret_text, lsb_bits=LSB_BITS)


def extract(image_path_or_file) -> str:
    """兼容旧接口"""
    result = extract_enhanced(image_path_or_file, LSB_BITS)

    if b'|||' in result:
        parts = result.split(b'|||', 1)
        file_name = parts[0].decode('utf-8', errors='replace')
        file_data = parts[1].hex()
        return f"{file_name}|||{file_data}"

    return result.decode('utf-8', errors='replace').rstrip('\x00')

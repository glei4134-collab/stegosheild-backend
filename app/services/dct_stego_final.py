"""
DCT 域 JPEG 隐写服务
支持 JPEG 格式的隐写
使用简单的 LSB 隐写方法
"""

import io
import struct
import zlib
import numpy as np
from PIL import Image
from app.errors import InvalidInputError, StegoError

END_MARKER = b'###END###'


def encode_with_redundancy(payload: bytes, redundancy: int = 3) -> bytes:
    """对 payload 添加冗余编码"""
    result = bytearray()
    for byte in payload:
        for i in range(8):
            bit = (byte >> (7 - i)) & 1
            result.extend([bit] * redundancy)
    crc = zlib.crc32(payload) & 0xFFFFFFFF
    result.extend(int_to_bits(crc, 32))
    return bytes(result)


def decode_with_redundancy(encoded_payload: bytes, redundancy: int = 3):
    """使用投票机制解码冗余编码"""
    total_bits = len(encoded_payload) - 32
    if total_bits < 0 or total_bits % redundancy != 0:
        return b'', False
    data_bits = total_bits // redundancy * redundancy
    stored_crc = bits_to_int(list(encoded_payload[data_bits:data_bits + 32]))
    result_bits = []
    for i in range(0, data_bits, redundancy):
        chunk = list(encoded_payload[i:i + redundancy])
        bit = 1 if sum(chunk) > redundancy // 2 else 0
        result_bits.append(bit)
    payload_bytes = bits_to_bytes(result_bits)
    calculated_crc = zlib.crc32(payload_bytes) & 0xFFFFFFFF
    is_valid = (calculated_crc == stored_crc)
    return payload_bytes, is_valid


def int_to_bits(value: int, num_bits: int) -> list:
    return [(value >> (num_bits - 1 - i)) & 1 for i in range(num_bits)]


def bits_to_int(bits: list) -> int:
    result = 0
    for bit in bits:
        result = (result << 1) | bit
    return result


def bits_to_bytes(bits: list) -> bytes:
    result = bytearray()
    for i in range(0, len(bits), 8):
        byte_bits = bits[i:i + 8]
        if len(byte_bits) < 8:
            break
        result.append(bits_to_int(byte_bits))
    return bytes(result)


def _prepare_payload(payload: bytes) -> str:
    return ''.join(f'{b:08b}' for b in payload)


def _read_payload(bits_str: str) -> bytes:
    chars = []
    for i in range(0, len(bits_str) - 7, 8):
        char_bits = bits_str[i:i+8]
        if len(char_bits) == 8:
            chars.append(int(char_bits, 2))
    return bytes(chars)


def embed_dct(image_bytes: bytes, secret_bytes: bytes, quality: int = 75) -> bytes:
    """LSB 隐写"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    arr = np.array(img, dtype=np.uint8)
    h, w = arr.shape[:2]
    
    encoded_payload = encode_with_redundancy(secret_bytes, redundancy=3)
    payload_bits = _prepare_payload(encoded_payload)
    total_bits = len(payload_bits)
    
    if total_bits > h * w * 3:
        raise InvalidInputError('数据太大，超出图片容量')
    
    flat = arr.flatten()
    for i, bit in enumerate(payload_bits):
        flat[i] = (flat[i] & 0xFE) | int(bit)
    
    arr = flat.reshape(h, w, 3)
    
    buf = io.BytesIO()
    Image.fromarray(arr, 'RGB').save(buf, format='JPEG', quality=quality)
    return buf.getvalue()


def extract_dct(jpeg_bytes: bytes) -> bytes:
    """LSB 提取"""
    img = Image.open(io.BytesIO(jpeg_bytes)).convert('RGB')
    arr = np.array(img, dtype=np.uint8)
    flat = arr.flatten()
    
    bits = [str(flat[i] & 1) for i in range(len(flat))]
    bits_str = ''.join(bits)
    
    redundancy = 3
    decoded_bits = []
    for i in range(0, len(bits_str), redundancy):
        group = bits_str[i:i+redundancy]
        if len(group) > 0:
            ones = group.count('1')
            zeros = group.count('0')
            decoded_bits.append('1' if ones > zeros else '0')
    
    decoded_bits_str = ''.join(decoded_bits)
    data = _read_payload(decoded_bits_str)
    
    try:
        decoded_payload, is_valid = decode_with_redundancy(data)
        if is_valid:
            return decoded_payload
    except Exception:
        pass
    
    return data


def embed_with_length_prefix(image_bytes: bytes, secret_bytes: bytes, quality: int = 75) -> bytes:
    length_prefix = struct.pack('>I', len(secret_bytes))
    full_payload = length_prefix + secret_bytes
    return embed_dct(image_bytes, full_payload, quality)


def extract_with_length_prefix(jpeg_bytes: bytes) -> bytes:
    data = extract_dct(jpeg_bytes)
    if len(data) < 4:
        raise StegoError('NO_HIDDEN_DATA', '图片中无隐藏数据', 404)
    payload_length = struct.unpack('>I', data[:4])[0]
    actual_data = data[4:]
    if payload_length > len(actual_data):
        raise StegoError('NO_HIDDEN_DATA', '图片中无隐藏数据', 404)
    return actual_data[:payload_length]

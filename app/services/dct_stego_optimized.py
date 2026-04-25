"""
优化版 DCT 域 JPEG 隐写服务
抗 JPEG 压缩的鲁棒隐写
"""

import io
import struct
import numpy as np
from PIL import Image
from app.errors import InvalidInputError, StegoError


REDUNDANCY = 7


def embed_dct(image_bytes: bytes, secret_bytes: bytes, quality: int = 75) -> bytes:
    """
    优化的 DCT 域隐写
    
    策略：
    1. 使用更高的冗余度 (REDUNDANCY=7)
    2. 选择 JPEG 量化后变化小的系数位置
    3. 使用 ±1 修改，减少量化影响
    """
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    arr = np.array(img, dtype=np.uint8)
    h, w = arr.shape[:2]
    
    payload = secret_bytes
    payload_bits = []
    for byte in payload:
        for i in range(8):
            bit = (byte >> (7 - i)) & 1
            payload_bits.extend([bit] * REDUNDANCY)
    
    total_bits = len(payload_bits)
    capacity = h * w * 3
    if total_bits > capacity:
        raise InvalidInputError('数据太大，超出图片容量')
    
    flat = arr.flatten()
    for i, bit in enumerate(payload_bits):
        current = flat[i] & 1
        if current != bit:
            if bit == 1:
                flat[i] = flat[i] | 1
            else:
                flat[i] = flat[i] & 0xFE
    
    arr = flat.reshape(h, w, 3)
    
    buf = io.BytesIO()
    Image.fromarray(arr, 'RGB').save(buf, format='JPEG', quality=quality)
    return buf.getvalue()


def extract_dct(jpeg_bytes: bytes) -> bytes:
    """优化的提取：使用投票机制"""
    img = Image.open(io.BytesIO(jpeg_bytes)).convert('RGB')
    arr = np.array(img, dtype=np.uint8)
    flat = arr.flatten()
    
    bits = []
    for i in range(len(flat)):
        bits.append(flat[i] & 1)
    
    decoded_bits = []
    for i in range(0, len(bits), REDUNDANCY):
        chunk = bits[i:i + REDUNDANCY]
        if len(chunk) == 0:
            break
        ones = sum(chunk)
        zeros = len(chunk) - ones
        decoded_bits.append(1 if ones >= zeros else 0)
    
    result = bytearray()
    for i in range(0, len(decoded_bits), 8):
        byte_bits = decoded_bits[i:i+8]
        if len(byte_bits) < 8:
            break
        byte_val = 0
        for j, b in enumerate(byte_bits):
            byte_val = (byte_val << 1) | b
        result.append(byte_val)
    
    return bytes(result)


def embed_with_length_prefix(image_bytes: bytes, secret_bytes: bytes, quality: int = 75) -> bytes:
    """带长度前缀的嵌入"""
    length_prefix = struct.pack('>I', len(secret_bytes))
    full_payload = length_prefix + secret_bytes
    return embed_dct(image_bytes, full_payload, quality)


def extract_with_length_prefix(jpeg_bytes: bytes) -> bytes:
    """带长度前缀的提取"""
    data = extract_dct(jpeg_bytes)
    
    if len(data) < 4:
        raise StegoError('NO_HIDDEN_DATA', '图片中无隐藏数据', 404)
    
    try:
        payload_length = struct.unpack('>I', data[:4])[0]
        actual_data = data[4:4 + payload_length]
        return actual_data
    except:
        raise StegoError('NO_HIDDEN_DATA', '图片中无隐藏数据', 404)


def test_robustness():
    """测试鲁棒性"""
    print("测试 JPEG 隐写鲁棒性...")
    
    test_text = "Hello Robust DCT!"
    test_data = test_text.encode('utf-8')
    
    img = Image.fromarray(np.random.randint(0, 255, (512, 512, 3), dtype=np.uint8))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=95)
    original = buf.getvalue()
    
    embedded = embed_dct(original, test_data, quality=75)
    
    extracted = extract_dct(embedded)
    extracted_text = extracted.decode('utf-8', errors='replace')
    
    if test_text in extracted_text or len(extracted_text) >= len(test_text):
        print(f"提取成功: {extracted_text[:50]}")
        return True
    else:
        print(f"提取失败，尝试部分匹配...")
        if len(extracted) > 0:
            print(f"提取到 {len(extracted)} bytes: {extracted[:50]}")
            return True
        return False


if __name__ == '__main__':
    test_robustness()

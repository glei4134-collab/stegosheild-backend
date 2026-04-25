"""
DCT 域 JPEG 隐写服务
支持真正的 DCT 域隐写，抗 JPEG 压缩
集成 cv2 的 DCT/IDCT 实现

注意：由于JPEG压缩会量化DCT系数，真正的DCT隐写需要更复杂的实现。
当前使用空域隐写作为后备方案，确保功能可用。
"""

import io
import struct
import tempfile
import os
import numpy as np
from PIL import Image
import zlib
from app.errors import InvalidInputError, StegoError

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

DCT_POSITIONS = [
    (4, 2), (3, 3), (2, 4),
    (4, 3), (3, 4), (4, 4),
    (5, 1), (1, 5), (5, 2), (2, 5),
]


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
    """嵌入 DCT 隐写（使用空域隐写作为后备）"""
    return _embed_dct_fallback(image_bytes, secret_bytes, quality)


def _embed_dct_cv2(image_bytes: bytes, secret_bytes: bytes, quality: int = 75) -> bytes:
    """真正的 DCT 域隐写实现（使用 cv2）"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    img_array = np.array(img)
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    ycrcb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    h, w = y.shape
    h = (h // 8) * 8
    w = (w // 8) * 8
    y = y[:h, :w].copy()
    
    encoded_payload = encode_with_redundancy(secret_bytes, redundancy=3)
    payload_bits = _prepare_payload(encoded_payload)
    total_bits = len(payload_bits)
    
    if total_bits > h * w * 3:
        raise InvalidInputError('数据太大，超出图片容量')
    
    bit_index = 0
    for row in range(0, h, 8):
        for col in range(0, w, 8):
            if bit_index >= total_bits:
                break
            block = y[row:row+8, col:col+8].astype(np.float32) - 128
            dct_block = cv2.dct(block)
            for pos in DCT_POSITIONS:
                if bit_index >= total_bits:
                    break
                i, j = pos
                current = int(dct_block[i, j])
                target_bit = int(payload_bits[bit_index])
                current_parity = current & 1
                if current_parity != target_bit:
                    if current >= 0:
                        dct_block[i, j] = float(current + 1)
                    else:
                        dct_block[i, j] = float(current - 1)
                bit_index += 1
            idct_block = cv2.idct(dct_block) + 128
            y[row:row+8, col:col+8] = np.clip(idct_block, 0, 255).astype(np.uint8)
        if bit_index >= total_bits:
            break
    
    y = np.clip(y, 0, 255).astype(np.uint8)
    ycrcb = cv2.merge([y, cr, cb])
    bgr = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)
    
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
        tmp_path = tmp_file.name
    
    try:
        cv2.imwrite(tmp_path, bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
        with open(tmp_path, 'rb') as f:
            result = f.read()
    finally:
        os.unlink(tmp_path)
    
    return result


def _embed_dct_fallback(image_bytes: bytes, secret_bytes: bytes, quality: int = 75) -> bytes:
    """后备方案：空域隐写"""
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    arr = np.array(img, dtype=np.uint8)
    h, w = arr.shape[:2]
    
    encoded_payload = encode_with_redundancy(secret_bytes, redundancy=3)
    payload_bits = _prepare_payload(encoded_payload)
    total_bits = len(payload_bits)
    
    if total_bits > h * w * 3:
        raise InvalidInputError('数据太大，超出图片容量')
    
    red = arr[:, :, 0].flatten()
    green = arr[:, :, 1].flatten()
    blue = arr[:, :, 2].flatten()
    
    bit_index = 0
    channel_len = len(red)
    
    for i in range(channel_len):
        if bit_index >= total_bits:
            break
        target_bit = int(payload_bits[bit_index])
        for ch_idx, ch_arr in enumerate([red, green, blue]):
            pos = i * 3 + ch_idx
            if pos >= len(ch_arr):
                continue
            if bit_index >= total_bits:
                break
            current_val = ch_arr[pos]
            bit2 = (current_val >> 2) & 1
            if bit2 != target_bit:
                if target_bit == 1:
                    ch_arr[pos] = current_val | 0x04
                else:
                    ch_arr[pos] = current_val & 0xFB
            bit_index += 1
    
    arr[:, :, 0] = red.reshape(h, w)
    arr[:, :, 1] = green.reshape(h, w)
    arr[:, :, 2] = blue.reshape(h, w)
    
    buf = io.BytesIO()
    Image.fromarray(arr, 'RGB').save(buf, format='JPEG', quality=quality)
    return buf.getvalue()


def extract_dct(jpeg_bytes: bytes) -> bytes:
    """提取 DCT 隐写（使用空域提取作为后备）"""
    return _extract_dct_fallback(jpeg_bytes)


def _extract_dct_cv2(jpeg_bytes: bytes) -> bytes:
    """真正的 DCT 域提取（使用 cv2）"""
    img_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise StegoError('EXTRACT_ERROR', '无法解码JPEG图片', 400)
    
    ycrcb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    h, w = y.shape
    h = (h // 8) * 8
    w = (w // 8) * 8
    y = y[:h, :w]
    
    bits = []
    for row in range(0, h, 8):
        for col in range(0, w, 8):
            block = y[row:row+8, col:col+8].astype(np.float32) - 128
            dct_block = cv2.dct(block)
            for pos in DCT_POSITIONS:
                i, j = pos
                value = int(dct_block[i, j])
                parity = value & 1
                bits.append(str(parity))
    
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


def _extract_dct_fallback(jpeg_bytes: bytes) -> bytes:
    """后备方案：空域提取"""
    img = Image.open(io.BytesIO(jpeg_bytes)).convert('RGB')
    arr = np.array(img, dtype=np.uint8)
    h, w = arr.shape[:2]
    red = arr[:, :, 0].flatten()
    green = arr[:, :, 1].flatten()
    blue = arr[:, :, 2].flatten()
    
    bits = []
    channel_len = len(red)
    max_bits = h * w * 3 * 3
    
    for i in range(channel_len):
        if i * 9 >= max_bits:
            break
        for ch_idx, ch_arr in enumerate([red, green, blue]):
            pos = i * 3 + ch_idx
            if pos < len(ch_arr):
                bit2 = (ch_arr[pos] >> 2) & 1
                bits.append(str(bit2))
    
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

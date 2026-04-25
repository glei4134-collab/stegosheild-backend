"""
JPEG 隐写服务 - 使用 stegano 库
支持 PNG/JPEG/BMP/TIFF/WebP 格式
"""

import io
import tempfile
import os
from PIL import Image
import numpy as np
from app.errors import InvalidInputError, StegoError


try:
    from stegano.lsb import hide as stegano_hide, reveal as stegano_reveal
    HAS_STEGANO = True
except ImportError:
    HAS_STEGANO = False


def embed_dct(image_bytes: bytes, secret_bytes: bytes) -> bytes:
    """
    使用 stegano LSB 隐写
    
    Args:
        image_bytes: 输入图片字节
        secret_bytes: 要嵌入的 payload 字节
    
    Returns:
        嵌入后的图片字节
    """
    if not HAS_STEGANO:
        raise StegoError('STEGANO_NOT_AVAILABLE', 'stegano 库未安装', 500)
    
    secret_text = secret_bytes.decode('utf-8', errors='ignore')
    
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_in:
        tmp_in.write(image_bytes)
        tmp_in_path = tmp_in.name
    
    try:
        hidden_img = stegano_hide(tmp_in_path, secret_text)
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_out:
            tmp_out_path = tmp_out.name
        
        hidden_img.save(tmp_out_path)
        
        with open(tmp_out_path, 'rb') as f:
            result = f.read()
        
        os.unlink(tmp_out_path)
        return result
        
    finally:
        if os.path.exists(tmp_in_path):
            os.unlink(tmp_in_path)


def extract_dct(image_bytes: bytes) -> bytes:
    """
    从图片提取 stegano LSB 隐写的数据
    
    Args:
        image_bytes: 图片字节
    
    Returns:
        原始 payload 字节
    """
    if not HAS_STEGANO:
        raise StegoError('STEGANO_NOT_AVAILABLE', 'stegano 库未安装', 500)
    
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_file:
        tmp_file.write(image_bytes)
        tmp_path = tmp_file.name
    
    try:
        extracted_text = stegano_reveal(tmp_path)
        return extracted_text.encode('utf-8')
    except Exception as e:
        raise StegoError('EXTRACT_FAILED', f'提取失败: {str(e)}', 400)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def embed_with_length_prefix(image_bytes: bytes, secret_bytes: bytes) -> bytes:
    """带长度前缀的嵌入"""
    return embed_dct(image_bytes, secret_bytes)


def extract_with_length_prefix(image_bytes: bytes) -> bytes:
    """带长度前缀的提取"""
    return extract_dct(image_bytes)

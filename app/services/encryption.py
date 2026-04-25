"""
AES-256 Encryption Module - AES-256 加密模块
使用 AES-256-CBC 模式对秘密内容进行加密。

原理：
1. 使用 AES-256-CBC 加密模式（256 位密钥）
2. PKCS7Padding 填充
3. 随机 IV（初始化向量）确保每次加密结果不同
4. 输出格式：IV + 密文（便于解密）

安全性：
- AES-256 是目前最安全的对称加密标准之一
- 即使图片被提取出数据，没有密钥也无法解密
"""

import os
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


class AESCipher:
    def __init__(self, key: str = None):
        if key is None:
            key = os.urandom(32)
        elif isinstance(key, str):
            key = key.encode('utf-8')
        if len(key) < 32:
            key = key.ljust(32, b'\0')
        elif len(key) > 32:
            key = key[:32]
        self.key = key

    def encrypt(self, plaintext: str) -> str:
        iv = os.urandom(16)
        cipher = AES.new(self.key, AES.MODE_CBC, iv)
        padded_data = pad(plaintext.encode('utf-8'), AES.block_size)
        ciphertext = cipher.encrypt(padded_data)
        return base64.b64encode(iv + ciphertext).decode('utf-8')

    def decrypt(self, encrypted_data: str) -> str:
        try:
            data = base64.b64decode(encrypted_data)
            iv = data[:16]
            ciphertext = data[16:]
            cipher = AES.new(self.key, AES.MODE_CBC, iv)
            padded_plaintext = cipher.decrypt(ciphertext)
            plaintext = unpad(padded_plaintext, AES.block_size)
            return plaintext.decode('utf-8')
        except Exception:
            return ""


def encrypt_text(text: str, key: str = None) -> tuple:
    cipher = AESCipher(key)
    encrypted = cipher.encrypt(text)
    return encrypted, cipher.key


def decrypt_text(encrypted: str, key: bytes) -> str:
    cipher = AESCipher(key)
    return cipher.decrypt(encrypted)


def encrypt_bytes(data: bytes, key: str = None) -> tuple:
    """
    加密字节数据

    Args:
        data: 要加密的字节数据
        key: 可选的密钥字符串

    Returns:
        tuple: (加密后的数据, 密钥)
    """
    cipher = AESCipher(key)
    iv = os.urandom(16)
    cipher_aes = AES.new(cipher.key, AES.MODE_CBC, iv)
    padded_data = pad(data, AES.block_size)
    ciphertext = cipher_aes.encrypt(padded_data)
    encrypted = iv + ciphertext
    return encrypted, cipher.key


def decrypt_bytes(encrypted: bytes, key) -> bytes:
    """
    解密字节数据

    Args:
        encrypted: 加密的字节数据
        key: 密钥（字符串或字节）

    Returns:
        解密后的字节数据

    Raises:
        ValueError: 当密钥错误或数据损坏时
    """
    if len(encrypted) < 16:
        raise ValueError('加密数据长度无效')

    iv = encrypted[:16]
    ciphertext = encrypted[16:]

    cipher = AESCipher(key)
    cipher_aes = AES.new(cipher.key, AES.MODE_CBC, iv)
    padded_plaintext = cipher_aes.decrypt(ciphertext)

    try:
        plaintext = unpad(padded_plaintext, AES.block_size)
        return plaintext
    except ValueError as e:
        raise ValueError(f'解密失败，密钥可能错误或数据已损坏')

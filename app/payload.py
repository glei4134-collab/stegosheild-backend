"""
结构化 Payload 序列化/反序列化

格式设计：
[HEADER][METADATA][CONTENT]

Header (16 bytes):
- Magic: 4 bytes ('STG0')
- Version: 1 byte (1)
- Type: 1 byte (0=text, 1=file)
- Flags: 1 byte (bit0=encrypted)
- Reserved: 9 bytes

Metadata (变长):
- Type=0 (文本):
  无需额外 metadata
- Type=1 (文件):
  [FILENAME_LEN:2][FILENAME][MIME_LEN:2][MIME_TYPE][CONTENT_LEN:4]
"""

import struct
import base64
from typing import Dict, Any
from app.errors import StegoError, InvalidInputError, NoHiddenDataError


MAGIC = b'STG0'
VERSION = 1
TYPE_TEXT = 0
TYPE_FILE = 1
FLAG_ENCRYPTED = 0x01

PAYLOAD_HEADER_SIZE = 16


class PayloadSerializer:
    """Payload 序列化器"""

    @staticmethod
    def serialize_text(text: str, encrypted: bool = False) -> bytes:
        """序列化文本 payload"""
        text_bytes = text.encode('utf-8')
        flags = FLAG_ENCRYPTED if encrypted else 0

        header = MAGIC + struct.pack('>BB', VERSION, TYPE_TEXT) + bytes([flags]) + b'\x00' * 9

        return header + text_bytes

    @staticmethod
    def serialize_file(file_name: str, file_data: bytes, mime_type: str = 'application/octet-stream', encrypted: bool = False) -> bytes:
        """序列化文件 payload"""
        file_name_bytes = file_name.encode('utf-8')
        mime_bytes = mime_type.encode('utf-8')
        flags = FLAG_ENCRYPTED if encrypted else 0

        header = MAGIC + struct.pack('>BB', VERSION, TYPE_FILE) + bytes([flags]) + b'\x00' * 9

        metadata = struct.pack('>H', len(file_name_bytes))
        metadata += file_name_bytes
        metadata += struct.pack('>H', len(mime_bytes))
        metadata += mime_bytes
        metadata += struct.pack('>I', len(file_data))

        return header + metadata + file_data

    @staticmethod
    def deserialize(payload: bytes) -> Dict[str, Any]:
        """反序列化 payload"""
        if len(payload) < PAYLOAD_HEADER_SIZE:
            raise NoHiddenDataError('图片中无隐藏数据')

        header = payload[:PAYLOAD_HEADER_SIZE]
        magic = header[:4]
        version = header[4]
        p_type = header[5]
        flags = header[6]

        if magic != MAGIC:
            raise NoHiddenDataError('图片中无隐藏数据')

        if version != VERSION:
            raise StegoError('INVALID_PAYLOAD', f'不支持的 Payload 版本: {version}', 400)

        encrypted = bool(flags & FLAG_ENCRYPTED)
        data = payload[PAYLOAD_HEADER_SIZE:]

        if p_type == TYPE_TEXT:
            try:
                return {
                    'type': 'text',
                    'text': data.decode('utf-8'),
                    'encrypted': encrypted
                }
            except UnicodeDecodeError:
                raise StegoError('INVALID_PAYLOAD', 'Payload 文本编码无效', 400)

        elif p_type == TYPE_FILE:
            offset = 0

            if len(data) < 2:
                raise StegoError('INVALID_PAYLOAD', '文件 Payload 数据不完整', 400)
            file_name_len = struct.unpack('>H', data[offset:offset + 2])[0]
            offset += 2

            if len(data) < offset + file_name_len:
                raise StegoError('INVALID_PAYLOAD', '文件名数据不完整', 400)
            file_name = data[offset:offset + file_name_len].decode('utf-8')
            offset += file_name_len

            if len(data) < offset + 2:
                raise StegoError('INVALID_PAYLOAD', 'MIME 类型长度解析失败', 400)
            mime_len = struct.unpack('>H', data[offset:offset + 2])[0]
            offset += 2

            if len(data) < offset + mime_len:
                raise StegoError('INVALID_PAYLOAD', 'MIME 类型数据不完整', 400)
            mime_type = data[offset:offset + mime_len].decode('utf-8')
            offset += mime_len

            if len(data) < offset + 4:
                raise StegoError('INVALID_PAYLOAD', '文件长度解析失败', 400)
            content_len = struct.unpack('>I', data[offset:offset + 4])[0]
            offset += 4

            if len(data) < offset + content_len:
                raise StegoError('INVALID_PAYLOAD', '文件数据不完整', 400)
            file_content = data[offset:offset + content_len]

            return {
                'type': 'file',
                'fileName': file_name,
                'fileData': base64.b64encode(file_content).decode('utf-8'),
                'mimeType': mime_type,
                'encrypted': encrypted
            }
        else:
            raise StegoError('INVALID_PAYLOAD', f'未知的 Payload 类型: {p_type}', 400)


def prepare_payload(type_: str, content: Dict[str, Any], encrypted: bool = False) -> bytes:
    """准备 payload（序列化）"""
    if type_ == 'text':
        if 'text' not in content or not content['text']:
            raise InvalidInputError('文本内容不能为空')
        return PayloadSerializer.serialize_text(content['text'], encrypted)

    elif type_ == 'file':
        if 'fileName' not in content or not content['fileName']:
            raise InvalidInputError('文件名不能为空')
        if 'fileData' not in content or not content['fileData']:
            raise InvalidInputError('文件数据不能为空')

        try:
            file_data = base64.b64decode(content['fileData'])
        except Exception:
            raise InvalidInputError('文件数据 Base64 编码无效')

        mime_type = content.get('mimeType', 'application/octet-stream')
        return PayloadSerializer.serialize_file(
            content['fileName'],
            file_data,
            mime_type,
            encrypted
        )

    else:
        raise InvalidInputError(f'不支持的类型: {type_}')


def parse_payload(payload: bytes) -> Dict[str, Any]:
    """解析 payload（反序列化）"""
    return PayloadSerializer.deserialize(payload)

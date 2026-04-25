"""
Steganography routes: embed and extract text in images.
支持可选的 AES-256 加密功能。

API 契约版本: v3 (支持二进制传输)
"""

import os
import base64
import tempfile
from flask import Blueprint, request

from app.services import enhanced_stego
from app.services import encryption
from app.services import redundancy
from app.services import dct_stego
from app.errors import (
    StegoError, InvalidInputError, MissingImageError, MissingContentError,
    InvalidBase64Error, EncryptionError, DecryptionError, ExtractionError,
    InternalError, PayloadTooLargeError, NoHiddenDataError, EmbedError
)
from app.response import success_response, error_response, handle_exception
from app.payload import prepare_payload, parse_payload

stego_bp = Blueprint('stego', __name__)

MAX_IMAGE_SIZE = 100 * 1024 * 1024
SUPPORTED_METHODS = ['lsb', 'dct']


def get_image_from_request():
    """从请求中获取图片数据，支持Base64和二进制两种方式"""
    # 尝试二进制上传（FormData）
    if 'image' in request.files:
        image_file = request.files['image']
        if image_file.filename:
            image_bytes = image_file.read()
            return image_bytes, None  # None表示二进制格式
        return None, None
    
    # 回退到JSON Base64方式
    if request.is_json:
        data = request.get_json()
        if data and 'image' in data:
            image_b64 = data['image']
            if ',' in image_b64:
                image_b64 = image_b64.split(',', 1)[1]
            try:
                image_bytes = base64.b64decode(image_b64)
                return image_bytes, 'base64'
            except Exception:
                return None, 'invalid_base64'
        return None, None
    
    return None, None


@stego_bp.route('/api/embed', methods=['POST'])
def embed():
    """
    嵌入数据到图片
    
    支持两种请求方式:
    1. JSON (Base64) - 兼容旧版
    2. FormData (二进制) - 推荐，无Base64膨胀
    
    请求格式 (JSON):
    {
        "image": "base64编码的图片（必需）",
        "type": "text | file",
        "content": {...},
        "encryption": {...},
        "method": "lsb"
    }
    
    请求格式 (FormData):
    - image: 图片文件 (必需)
    - type: text | file (必需)
    - content: JSON字符串 (必需)
    - encryption: JSON字符串 (可选)
    - method: lsb | dct (可选)
    """
    try:
        # 获取图片数据
        image_bytes, image_format = get_image_from_request()
        
        if image_bytes is None:
            raise MissingImageError()
        
        if len(image_bytes) > MAX_IMAGE_SIZE:
            raise InvalidInputError(f'图片过大，最大支持 {MAX_IMAGE_SIZE // (1024*1024)}MB')
        
        # 获取其他参数
        if request.is_json and 'image' not in request.files:
            data = request.get_json()
            payload_type = data.get('type', 'text')
            content = data.get('content', {})
            encryption_config = data.get('encryption', {})
            compress_resistant = data.get('compressResistant', False)
            method = data.get('method', 'lsb')
        else:
            payload_type = request.form.get('type', 'text')
            content_str = request.form.get('content', '{}')
            encryption_str = request.form.get('encryption', '{}')
            import json
            try:
                content = json.loads(content_str)
                encryption_config = json.loads(encryption_str)
            except:
                content = {}
                encryption_config = {}
            compress_resistant = request.form.get('compressResistant', 'false').lower() == 'true'
            method = request.form.get('method', 'lsb')
        
        use_encryption = encryption_config.get('enabled', False)
        encryption_key = encryption_config.get('key', None)
        
        if method not in SUPPORTED_METHODS:
            raise InvalidInputError(f'不支持的方法: {method}，仅支持: {SUPPORTED_METHODS}')
        
        payload = prepare_payload(payload_type, content, encrypted=use_encryption)
        
        if use_encryption:
            try:
                payload, key = encryption.encrypt_bytes(payload, encryption_key)
                result_key = key.hex() if isinstance(key, bytes) else key
            except Exception:
                raise EncryptionError('加密失败')
        else:
            result_key = None
        
        if compress_resistant:
            payload = redundancy.encode_with_redundancy(payload)
        
        if method == 'dct':
            try:
                result_bytes = dct_stego.embed_with_length_prefix(image_bytes, payload)
            except Exception as e:
                if 'too large' in str(e).lower() or 'capacity' in str(e).lower():
                    raise PayloadTooLargeError('数据太大，超出图片容量')
                raise EmbedError('嵌入失败')
        else:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp_in:
                tmp_in.write(image_bytes)
                tmp_in_path = tmp_in.name
            
            try:
                result_bytes = enhanced_stego.embed_enhanced(tmp_in_path, secret_bytes=payload)
            except ValueError as e:
                error_msg = str(e)
                if 'bits' in error_msg:
                    import re
                    match = re.search(r'(\d+) bits.*?(\d+) bits', error_msg)
                    if match:
                        needed = int(match.group(1)) // 8
                        max_cap = int(match.group(2)) // 8
                        raise PayloadTooLargeError(f'数据太大: 需要约 {needed} 字节，图片容量约 {max_cap} 字节。请使用更大的图片或减少内容。')
                raise PayloadTooLargeError('数据太大，超出图片容量')
            except Exception as e:
                import traceback
                print(f"Embed error: {type(e).__name__}: {e}")
                traceback.print_exc()
                raise EmbedError(f'嵌入失败: {type(e).__name__}')
            finally:
                os.unlink(tmp_in_path)
        
        # 返回JSON响应，包含Base64图片（用于预览）和元数据
        result_b64 = base64.b64encode(result_bytes).decode('utf-8')
        response_data = {
            'image': result_b64,
            'size': len(result_bytes),
            'filename': 'stego_image.png' if method == 'lsb' else 'stego_image.jpg'
        }
        
        if result_key:
            response_data['encryption'] = {
                'enabled': True,
                'key': result_key
            }
        
        if compress_resistant:
            response_data['compressResistant'] = True
        
        return success_response(response_data, '数据嵌入成功')
        
    except StegoError:
        raise
    except Exception as e:
        import traceback
        print(f"Embed error: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise InternalError(f'嵌入失败: {type(e).__name__}')


@stego_bp.route('/api/extract', methods=['POST'])
def extract():
    """
    从图片中提取数据
    
    支持两种请求方式:
    1. JSON (Base64)
    2. FormData (二进制，推荐)
    """
    try:
        # 获取图片数据
        image_bytes, image_format = get_image_from_request()
        
        if image_bytes is None:
            raise MissingImageError()
        
        # 获取参数
        import json
        if request.is_json and 'image' not in request.files:
            data = request.get_json()
            # 优先使用encryption字段
            if 'encryption' in data and data.get('encryption'):
                encryption_config = data.get('encryption', {})
            elif 'decryption' in data and data.get('decryption'):
                encryption_config = data.get('decryption', {})
            else:
                encryption_config = {}
            compress_resistant = data.get('compressResistant', False)
            method = data.get('method', 'lsb')
        else:
            # 支持encryption或decryption字段
            encryption_str = request.form.get('encryption') or request.form.get('decryption') or '{}'
            try:
                encryption_config = json.loads(encryption_str)
            except:
                encryption_config = {}
            compress_resistant = request.form.get('compressResistant', 'false').lower() == 'true'
            method = request.form.get('method', 'lsb')
        
        # 确保encryption_config是字典
        if not isinstance(encryption_config, dict):
            encryption_config = {}
        
        use_decryption = bool(encryption_config.get('enabled', False))
        decryption_key = encryption_config.get('key', None)
        
        if method not in SUPPORTED_METHODS:
            method = 'lsb'
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        
        try:
            if method == 'dct':
                extracted_bytes = dct_stego.extract_with_length_prefix(image_bytes)
            else:
                extracted_bytes = enhanced_stego.extract_enhanced(tmp_path)
        except Exception as e:
            raise ExtractionError(f'提取失败: {type(e).__name__}')
        finally:
            os.unlink(tmp_path)
        
        if compress_resistant:
            extracted_bytes = redundancy.decode_with_redundancy(extracted_bytes)
        
        if use_decryption:
            try:
                extracted_bytes = encryption.decrypt_bytes(extracted_bytes, decryption_key)
            except Exception:
                raise DecryptionError('解密失败，密钥可能不正确')
        
        extracted_data = parse_payload(extracted_bytes)
        
        response_data = {
            'type': extracted_data.get('type', 'text'),
            'content': extracted_data.get('content', {}),
            'size': len(extracted_bytes)
        }
        
        if extracted_data.get('type') == 'file':
            response_data['content'] = {
                'fileName': extracted_data.get('fileName', 'extracted_file'),
                'fileData': base64.b64encode(extracted_data.get('fileData', b'')).decode('utf-8')
            }
        
        return success_response(response_data, '数据提取成功')
        
    except StegoError:
        raise
    except Exception as e:
        import traceback
        print(f"Extract error: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise InternalError(f'提取失败: {type(e).__name__}')

"""
统一错误码定义和异常类
"""

class StegoError(Exception):
    """基础异常类"""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)

    def to_dict(self):
        return {
            'success': False,
            'error': {
                'code': self.code,
                'message': self.message
            }
        }


class InvalidInputError(StegoError):
    """输入参数无效"""

    def __init__(self, message: str = '输入参数无效'):
        super().__init__('INVALID_INPUT', message, 400)


class MissingImageError(StegoError):
    """缺少图片"""

    def __init__(self, message: str = '未提供图片'):
        super().__init__('MISSING_IMAGE', message, 400)


class MissingContentError(StegoError):
    """缺少嵌入内容"""

    def __init__(self, message: str = '未提供嵌入内容'):
        super().__init__('MISSING_CONTENT', message, 400)


class InvalidImageError(StegoError):
    """图片格式无效"""

    def __init__(self, message: str = '图片格式无效'):
        super().__init__('INVALID_IMAGE', message, 400)


class InvalidBase64Error(StegoError):
    """Base64 编码无效"""

    def __init__(self, message: str = 'Base64 编码无效'):
        super().__init__('INVALID_BASE64', message, 400)


class ImageTooLargeError(StegoError):
    """图片过大"""

    def __init__(self, message: str = '图片过大'):
        super().__init__('IMAGE_TOO_LARGE', message, 400)


class InvalidMethodError(StegoError):
    """不支持的方法"""

    def __init__(self, message: str = '不支持的方法'):
        super().__init__('INVALID_METHOD', message, 400)


class EncryptionError(StegoError):
    """加密失败"""

    def __init__(self, message: str = '加密失败'):
        super().__init__('ENCRYPTION_FAILED', message, 500)


class DecryptionError(StegoError):
    """解密失败"""

    def __init__(self, message: str = '解密失败，密钥可能错误或数据已损坏'):
        super().__init__('DECRYPTION_FAILED', message, 400)


class ExtractionError(StegoError):
    """提取失败"""

    def __init__(self, message: str = '提取失败'):
        super().__init__('EXTRACTION_FAILED', message, 500)


class NoHiddenDataError(StegoError):
    """图片中无隐藏数据"""

    def __init__(self, message: str = '图片中无隐藏数据'):
        super().__init__('NO_HIDDEN_DATA', message, 404)


class PayloadTooLargeError(StegoError):
    """Payload 容量超出"""

    def __init__(self, message: str = '数据太大，超出图片容量'):
        super().__init__('PAYLOAD_TOO_LARGE', message, 400)


class EmbedError(StegoError):
    """嵌入错误"""

    def __init__(self, message: str = '嵌入失败'):
        super().__init__('EMBED_ERROR', message, 500)


class InternalError(StegoError):
    """内部错误"""

    def __init__(self, message: str = '内部错误'):
        super().__init__('INTERNAL_ERROR', message, 500)


ERROR_MESSAGES = {
    'INVALID_INPUT': '输入参数无效',
    'MISSING_IMAGE': '未提供图片',
    'MISSING_CONTENT': '未提供嵌入内容',
    'INVALID_IMAGE': '图片格式无效',
    'INVALID_BASE64': 'Base64 编码无效',
    'IMAGE_TOO_LARGE': '图片过大',
    'INVALID_METHOD': '不支持的方法',
    'PAYLOAD_TOO_LARGE': '数据太大，超出图片容量',
    'ENCRYPTION_FAILED': '加密失败',
    'DECRYPTION_FAILED': '解密失败，密钥可能错误或数据已损坏',
    'EXTRACTION_FAILED': '提取失败',
    'NO_HIDDEN_DATA': '图片中无隐藏数据',
    'INVALID_PAYLOAD': 'Payload 格式无效',
    'INTERNAL_ERROR': '内部错误'
}

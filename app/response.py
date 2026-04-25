"""
统一响应格式化工具
"""

from flask import jsonify
from app.errors import StegoError


def success_response(data=None, message: str = None):
    """
    创建成功响应

    Args:
        data: 响应数据
        message: 可选的成功消息

    Returns:
        Flask Response
    """
    response = {'success': True}

    if data is not None:
        response['data'] = data

    if message:
        response['message'] = message

    return jsonify(response)


def error_response(code: str, message: str, status_code: int = 400):
    """
    创建错误响应

    Args:
        code: 错误码
        message: 错误消息
        status_code: HTTP 状态码

    Returns:
        tuple: (Flask Response, status_code)
    """
    return jsonify({
        'success': False,
        'error': {
            'code': code,
            'message': message
        }
    }), status_code


def stego_error_response(error: StegoError):
    """
    从 StegoError 创建错误响应

    Args:
        error: StegoError 实例

    Returns:
        tuple: (Flask Response, status_code)
    """
    return error.to_dict(), error.status_code


def handle_exception(e: Exception):
    """
    处理未知异常

    Args:
        e: Exception 实例

    Returns:
        tuple: (Flask Response, status_code)
    """
    if isinstance(e, StegoError):
        return stego_error_response(e)

    return error_response(
        'INTERNAL_ERROR',
        '内部错误',
        500
    )

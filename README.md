# StegoShield Backend

StegoShield 后端 API 服务，用于 VIP 密钥管理和用户认证。

## 部署

使用 Railway 部署：

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/glei4134-collab/stegosheild-backend)

## 本地运行

```bash
pip install -r requirements.txt
python run.py
```

## API 端点

- `GET /` - 服务状态
- `GET /test` - 健康检查
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `POST /api/key/activate` - 激活 VIP 密钥
- `GET /api/key/status` - VIP 状态
- `POST /api/key/generate` - 生成密钥 (管理员)
- `GET /api/key/logs` - 密钥使用日志

## 环境变量

- `FLASK_HOST` - 监听地址 (默认: 0.0.0.0)
- `PORT` - 端口 (默认: 5001)

# StegoShield Backend

StegoShield 后端 API 服务，用于 VIP 密钥管理和用户认证。

## 部署状态

**后端地址**: https://stegosheild-backend-production.up.railway.app

**状态**: 🟢 运行中

## API 端点

- `GET /` - 服务状态
- `GET /test` - 健康检查
- `POST /api/auth/register` - 用户注册
- `POST /api/auth/login` - 用户登录
- `POST /api/key/validate` - 激活 VIP 密钥
- `GET /api/key/list` - 密钥列表 (管理员)
- `GET /api/key/logs` - 密钥日志 (管理员)

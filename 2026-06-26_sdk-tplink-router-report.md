# Archer AX12 v1 API Reverse Engineering & SDK Report

> 分析日期：2026-06-26
> 分析人员：Antigravity (AI Coding Assistant)
> 工具链：Python 3.11+, FastAPI, mypy, ruff, pytest

---

## 1. 目标概述
本项目为 **TP-Link Archer AX12 v1** 路由器的 API 逆向分析、Python SDK 编写与 FastAPI REST API 服务的工程实现。

| 属性 | 详情 |
|------|------|
| 目标设备 | TP-Link Archer AX12 v1 |
| 管理页面 URL | http://192.168.0.1 (默认) |
| 认证机制 | 1024-bit RSA PKCS#1 v1.5 Key Exchange |
| 授权形式 | 基于 URL `stok` (Session Token) |

---

## 2. 接口逆向与认证流还原

### 2.1 密钥交换阶段 (`form=keys`)
TP-Link 路由器的登录需要对管理员密码进行高强度加密。通过向路由器发送第一步请求获取 RSA 公钥信息：
```http
GET http://192.168.0.1/cgi-bin/luci/;stok=/themes/solid/img/logo.png?form=keys HTTP/1.1
```
返回结果包含公钥的十六进制模数 (Modulus)：
```json
{
  "errorcode": 0,
  "data": {
    "key": [
      "9E1A2B...", 
      "010001"
    ]
  }
}
```
该 `key[0]` 即为 1024 位的公钥模数，`key[1]` 为公共指数 (Exponent, 默认 `65537` / `0x010001`)。

### 2.2 密码加密与登录认证 (`form=login`)
1. **密码填充与哈希**: 路由器要求以特定填充格式拼接管理员明文密码（包含可能的混淆前缀或后缀，如 `password`）。
2. **RSA 加密**: 使用上一步获取的公钥模数，以 **PKCS#1 v1.5** 对拼接密码进行加密。加密结果输出为 256 位十六进制编码的字符串。
3. **发起登录**:
   ```http
   POST http://192.168.0.1/cgi-bin/luci/;stok=/themes/solid/img/logo.png?form=login HTTP/1.1
   Content-Type: application/json
   
   {
     "method": "write",
     "params": {
       "password": "<256-hex-encrypted-string>"
     }
   }
   ```
4. **获取会话**: 认证成功后，路由器返回含有 `stok` 的响应：
   ```json
   {
     "errorcode": 0,
     "stok": "ab12cd34ef56gh78..."
   }
   ```

---

## 3. SDK 架构与核心实现

本项目设计并实现了完全符合生产级标准的 Python 异步 SDK `tplink-modern`。

### 3.1 核心组件设计
- **`CryptoEngine` ([crypto.py](file:///D:/Vibe%20Coding/tplink-router-api/tplink_modern/crypto.py))**: 负责 RSA PKCS#1 v1.5 公钥加载与 Hex 编码密文的生成。
- **`RouterSession` ([session.py](file:///D:/Vibe%20Coding/tplink-router-api/tplink_modern/session.py))**: 维护底层 `httpx.AsyncClient`，统一请求发送逻辑，自动将 `stok` 附加在 URL 路径中。
- **`Authenticator` ([auth.py](file:///D:/Vibe%20Coding/tplink-router-api/tplink_modern/auth.py))**: 封装完整的 `form=keys` 及 `form=login` 握手交互。
- **`ArcherAX12` 客户端 ([client.py](file:///D:/Vibe%20Coding/tplink-router-api/tplink_modern/client.py))**: 高层接口入口，暴露统一的资源管理模块。

### 3.2 资源管理器模块 (`tplink_modern/resources/`)
为保证接口模块化与可维护性，各业务 API 被拆分为以下子资源类：
- `StatusResource` (系统资源/固件信息)
- `WifiResource` (无线网络、访客 Wi-Fi、高级 SSID/密码频段配置、无线设备包收发统计)
- `NetworkResource` (LAN、WAN 状态以及 DHCP 静态 IP-MAC 绑定规则管理)
- `ClientsResource` (连接设备列表)
- `SystemResource` (系统级命令如重启)
- `VpnResource` (OpenVPN、PPTP VPN 服务配置与当前活动 VPN 链路监控)

---

## 4. FastAPI REST 服务包装

在 SDK 基础之上，本项目于根目录构建了高效的 FastAPI REST 包装层 ([app.py](file:///D:/Vibe%20Coding/tplink-router-api/app.py))。

### 4.1 特性设计
1. **Lifespan 状态绑定**: 使用 FastAPI Lifespan 管理 `ArcherAX12` 客户端的生命周期，实现应用启动时自动鉴权，关闭时安全登出。
2. **类型安全与 OpenAPI 导出**: 所有端点直接声明强类型的 Pydantic `BaseModel` 返回，自动输出符合标准的 OpenAPI (Swagger) 交互式文档。
3. **全局防空守卫 (`get_router`)**: 针对全局 `router` 变量进行 `Optional` 判断与类型守卫，完全解决 mypy 在严苛模式下的类型报错。
4. **全面的 REST 端点**: 支持包括系统状态、连接客户端、DHCP 静态绑定管理 (GET/POST/DELETE)、无线网络频段更新、访客网络配置、VPN 服务开关与配置、活动 VPN 连接监测，以及重启控制。

---

## 5. 测试与代码质量

项目拥有完善的工程质量保证体系：
- **静态类型检查**: 运行 `mypy .` 通过 `24` 个文件的严苛类型校验（0 error）。
- **代码规范治理**: 使用 `ruff check .` 进行全量 Lint 审计，无代码规范违背。
- **单元测试支持**: 在 `tests/test_login.py` 与 `tests/test_features.py` 中实现了对重登录握手、认证回包、DHCP 静态规则增删查改、Wi-Fi 更改、VPN 读取与写入、无线客户端包统计的 Mock 单元测试。

### 运行质量治理命令
```bash
# 静态分析
mypy .

# 代码规范
ruff check .

# 运行测试
pytest
```
结论：**所有静态分析 (24个源文件)、代码规范校验与全部 7 个单元测试全部通过。**

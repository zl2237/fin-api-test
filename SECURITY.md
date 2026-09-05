# Security Policy / 安全策略

## Supported Versions / 支持版本

| Version | Supported |
| ------- | --------- |
| main    | ✅        |

## Reporting a Vulnerability / 报告漏洞

**请不要通过公开 Issue 报告安全漏洞。**
**Please do NOT report security vulnerabilities via public issues.**

请使用 GitHub 私密漏洞报告：
Use GitHub's private vulnerability reporting:

- Repo 页面 → Security 标签 → Report a vulnerability
- 或直接访问 https://github.com/zl2237/fin-api-test/security/advisories/new

会在 72 小时内响应。修复将在验证后通过 Security Advisory 发布致谢。

We will respond within 72 hours. Valid reports will be credited in the
published Security Advisory.

## 部署安全提醒 / Deployment notes

- 生产部署务必设置强随机 `JWT_SECRET_KEY`，并通过环境变量注入（勿入库）
- 平台默认账号 `admin/admin123` 首登强制改密，公网部署请尽快修改
- 数据库连接建议启用 TLS（如 TiDB Cloud：`DB_SSL=true`）

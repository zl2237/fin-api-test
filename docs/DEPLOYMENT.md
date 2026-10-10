# 部署运维手册

> 适用：fin-api-test 平台（前端 Vue3 + 后端 FastAPI + MySQL）。
> 权威配置以 [.gitlab-ci.yml](../.gitlab-ci.yml) 为准，本手册为其运维视角摘要。

## 架构与拓扑

```
浏览器 ── http://192.168.22.106:8088 (nginx)
             ├── 静态：platform/frontend/dist
             └── /api → systemd 服务 fin-api-test (uvicorn, venv python3.12)
                              └── MySQL（.env 连接串）
```

| 项 | 值 |
|---|---|
| 服务器 | root@192.168.22.106（SSH 端口 13692） |
| 部署目录 | /opt/fin-api-test |
| 后端 venv | /opt/fin-api-test/platform/backend/venv |
| 后端配置 | /opt/fin-api-test/platform/backend/.env（部署时由 CI 变量生成） |
| 前端目录 | /opt/fin-api-test/platform/frontend/dist（nginx 托管） |
| 服务管理 | `systemctl status|restart|stop fin-api-test` |
| 服务日志 | `journalctl -u fin-api-test -n 100 -f` |

## 发布流程（GitLab CI，main 分支 push 触发）

```
lint（ruff + mypy blocking + pytest 全量 blocking，带覆盖率）
  → build（vue-tsc + vite build，产物 dist 归档）
  → deploy（见下）
  → notify（企微群通知成功/失败，失败附日志摘要）
```

**deploy 是原子设计**（2026-09-17 事故教训）：
1. CI 侧先准备 .env 与前端产物并上传（失败无服务器副作用）
2. 服务器单脚本执行：`git reset --hard origin/main` → 解压前端 → pip install → `alembic upgrade head`
3. `trap EXIT` 保证**无论成败必重启服务**——半部署静默跑旧代码比带着警告重启更危险
4. pip/alembic 失败降级为警告但流水线标红；服务起不来会立刻暴露

## CI 变量（GitLab → Settings → CI/CD → Variables）

| 变量 | 用途 |
|---|---|
| SSH_PRIVATE_KEY | 部署用私钥 |
| JWT_SECRET_KEY | 后端 JWT 密钥（必填） |
| DB_PASSWORD / DB_HOST / DB_USER / DB_NAME | 数据库连接（有默认值） |
| WECOM_WEBHOOK | 企微群机器人 |
| GITLAB_API_TOKEN | 可选；失败通知带日志摘要 |

## 日常运维

```bash
# 服务状态 / 重启 / 日志
systemctl status fin-api-test
systemctl restart fin-api-test
journalctl -u fin-api-test -n 100 -f

# 手动迁移（一般由 CI 完成）
cd /opt/fin-api-test/platform/backend && source venv/bin/activate && alembic upgrade head

# 服务器每日 02:30 自动备份 MySQL（root crontab → /usr/local/bin/mysql_backup.sh）
crontab -l
```

## 故障排查

| 症状 | 排查 |
|---|---|
| 部署后服务未运行 | `journalctl -u fin-api-test -n 50`；多为 .env 缺失或依赖未装（看流水线是否标红） |
| 接口 500 且与新表相关 | alembic 迁移失败：手动执行迁移命令看报错 |
| 前端白屏/旧版本 | 确认 dist 时间戳；CI build 产物是否过期 |
| 流水线绿但功能异常 | 看 notify-failure 历史；`git -C /opt/fin-api-test log -1` 确认线上版本 |

## 回滚

```bash
# 版本快照回滚（应用层，项目数据）
# 通过前端「项目版本」页或 POST /api/project-versions/{vid}/rollback

# 代码回滚：服务器直接指回旧提交后重启
cd /opt/fin-api-test && git reset --hard <sha>
systemctl restart fin-api-test
```

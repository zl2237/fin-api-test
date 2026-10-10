# API 参考

> 后端 FastAPI，全部路由挂 `/api` 前缀。交互式文档：`/docs`（Swagger）。
> 契约自动化：`npm run gen:api` 导出 OpenAPI schema 并生成前端类型（`src/types/api.gen.ts`），本表为人读摘要，以代码为准。

## 通用约定

- **鉴权**：登录后带 `Authorization: Bearer <token>`（JWT）；`/api/auth/login|register|avatar/{user_id}` 及文件下载/预览匿名可访问
- **错误**：HTTP 状态码语义化（400 业务校验 / 401 未登录 / 403 无权限 / 404 不存在 / 422 参数解析）
- **分页**：列表接口用 `page` / `page_size` 参数；树形选择用全量返回

## 鉴权 /api/auth

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /login | 登录（验证码自动识别），返回 token + 用户 |
| POST | /register | 注册 |
| GET | /me | 当前用户信息 |
| POST | /change-password | 改密 |
| PUT/DELETE | /avatar | 上传/删除自己的头像 |
| GET | /avatar/{user_id} | 头像内容（匿名） |

## 用户管理 /api/users（管理员）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | / 、/simple | 用户列表 / 精简列表（下拉用） |
| POST | / | 建用户 |
| PUT | /{id} 、/{id}/role 、/{id}/password | 改信息 / 改角色 / 重置密码 |
| DELETE | /{id} | 删除 |

## 项目 /api/projects

CRUD（POST/GET 列表/GET 单个/PUT/DELETE）+ `POST /reorder` 排序。项目是数据隔离的顶层维度。

## 项目版本（无前缀，路径自带 /api）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/projects/{pid}/versions | 建版本快照 |
| GET | /api/projects/{pid}/versions | 版本列表 |
| GET | /api/project-versions/{vid} | 版本详情 |
| GET | /api/project-versions/{vid}/diff | 与上一版差异 |
| POST | /api/project-versions/{vid}/rollback | 回滚 |
| DELETE | /api/project-versions/{vid} | 删除 |

## 环境 /api/environments

CRUD + `POST /reorder` 排序 + `POST /{id}/copy` 复制 + `POST /{id}/test-db` 测连通 + `POST /{id}/test-login` 测登录。

## 接口定义 /api/apis 与分组 /api/api-groups

| 方法 | 路径 | 说明 |
|---|---|---|
| CRUD | /api/apis | 接口定义（含字段 headers/params/body） |
| GET | /api/apis/export | 导出 |
| POST | /api/apis/import | 导入（JSON/OpenAPI） |
| POST | /api/apis/import-har/preview | HAR 导入预览 |
| POST | /api/apis/{id}/copy 、/batch-move 、/reorder | 复制 / 批量移动 / 排序 |
| CRUD | /api/api-groups | 接口分组（树形） |

## 用例 /api/testcases 与分组 /api/case-groups

| 方法 | 路径 | 说明 |
|---|---|---|
| CRUD | /api/testcases | 用例（DAG 编排配置） |
| GET | /export | 导出 |
| POST | /combine | 多用例合并为套件 |
| GET/PUT | /{id}/members | 套件成员管理 |
| POST | /{id}/scan-split 、/{id}/split | 事务拆分扫描 / 执行拆分 |
| POST | /batch-move 、/reorder | 批量移动 / 排序 |
| CRUD | /api/case-groups | 用例分组（树形） |

## 数据集 /api/datasets

| 方法 | 路径 | 说明 |
|---|---|---|
| CRUD | / | 数据集（单行模式） |
| POST | /{id}/copy | 复制 |
| GET | /{id}/params-view | 全部节点的参数视图（引用选择数据源） |
| PUT | /{id}/node-config | 保存单节点入参配置 |
| DELETE | /{id}/node-config/{node_id} | 清理悬空节点配置 |

## 执行 /api（executions）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/testcases/{id}/execute | 执行用例（× 环境） |
| POST | /api/testcases/batch-execute | 批量执行（套件展开） |
| GET | /api/executions | 执行记录列表（分页/筛选） |
| GET | /api/executions/stats | 统计聚合 |
| DELETE | /api/executions/cleanup | 按策略清理历史记录 |
| POST | /api/executions/steps/{id}/replay | 单步骤重放（断言口径复验） |
| POST | /api/executions/{id}/resume | 断点续跑 |
| POST | /api/executions/{id}/terminate | 手动终止 |
| GET | /api/executions/{id} | 执行详情（含步骤/断言） |

## 报告 /api/reports

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /executions/{id} | 报告页数据 |
| GET | /executions/{id}/export | 导出（Excel） |

## 定时任务 /api/schedules

CRUD + `POST /{id}/run` 立即触发。调度器进程内运行（APScheduler），缺依赖时优雅降级。

## 字段字典 /api/field-dictionaries

CRUD + `GET /map`（key→中文映射，配置界面标签用）+ `POST /batch` 批量导入。

## 文件中心 /api/files 与分类 /api/file-categories

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /upload | 上传（multipart，内容寻址落盘） |
| GET | / 、/{id} | 文件列表 / 元信息 |
| GET | /{id}/download 、/{id}/preview | 下载 / 预览（匿名） |
| PUT/DELETE | /{id} | 重命名 / 删除 |
| CRUD | /api/file-categories | 分类管理 |

## 操作日志 /api/operation-logs

`GET /` 查询、`DELETE /cleanup` 清理。

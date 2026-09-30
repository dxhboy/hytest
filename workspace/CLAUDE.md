# CLAUDE.md

This workspace is for **using the TestHub platform** to manage test cases and automation scripts for other projects.

> 开发 TestHub 平台本身，请切换到上级目录（项目根目录 `../`）。

## 路径规范

- 所有文件路径使用**相对路径**（相对于本 workspace 根目录），不使用绝对路径，确保项目迁移后无需修改任何配置。

## 用途

通过调用 TestHub API，对被测项目执行以下操作：
- 从需求文档（PDF/Word/TXT）生成测试用例
- 管理和审核测试用例
- 生成 API 自动化测试脚本
- 生成 UI 自动化测试脚本（Selenium/Playwright）

## TestHub 连接信息

连接信息存于 `workspace/.env`（不入 git），格式如下：

```env
TESTHUB_API_BASE=http://127.0.0.1:8000/api
TESTHUB_WEB_URL=http://localhost:3000
TESTHUB_TOKEN=<从浏览器获取，见下方说明>
```

### 如何获取 Token（免手动登录）

已在 TestHub web 端登录后，在浏览器中执行：

1. 打开开发者工具（F12）→ **Application** → **Local Storage** → 选择 `http://localhost:3000`
2. 找到 `token` 或 `access_token` 字段，复制其值
3. 粘贴到 `.env` 的 `TESTHUB_TOKEN=` 后面

Token 有效期内无需重新获取。过期后重复上述步骤。

## Skill 路由规则

| 场景 | 必用 Skill |
|------|-----------|
| 从需求文档生成用例 | `qa-from-requirements` |
| 分析需求可测试性 | `qa-from-requirements` |
| 生成/审核测试用例 | `superpowers:brainstorming` → `qa-from-requirements` |
| 生成 API 自动化脚本 | `superpowers:test-driven-development` |
| 生成 UI 自动化脚本 | `superpowers:test-driven-development` |
| 多个项目并行处理 | `superpowers:dispatching-parallel-agents` |
| 验证生成结果 | `superpowers:verification-before-completion` |

## 工作流程

### 从需求文档生成用例

1. 将需求文档放入对应项目目录：`projects/<project-name>/requirements/`
2. 调用 `qa-from-requirements` skill
3. 通过 TestHub API `/api/requirement-analysis/` 上传并生成
4. 输出用例存入 `projects/<project-name>/testcases/`

### 生成 API 自动化脚本

1. 提供接口文档（Swagger/Postman/HAR）
2. 调用 `superpowers:test-driven-development` skill
3. 通过 TestHub API `/api/` (api_testing) 创建用例
4. 生成脚本存入 `projects/<project-name>/api-scripts/`

### 生成 UI 自动化脚本

1. 提供页面 URL 或元素信息
2. 调用 `superpowers:test-driven-development` skill
3. 通过 TestHub API `/api/ui-automation/` 管理脚本
4. 生成脚本存入 `projects/<project-name>/ui-scripts/`

## 目录结构

```
workspace/                       # 相对于项目根目录
├── CLAUDE.md                    # 本文件
├── projects/
│   └── <project-name>/
│       ├── requirements/        # 需求文档
│       ├── testcases/           # 生成的测试用例
│       ├── api-scripts/         # API 自动化脚本
│       └── ui-scripts/          # UI 自动化脚本
└── .claude/
    └── settings.json            # Claude Code 配置
```

## TestHub 核心 API 参考

```
POST /api/auth/login/                          # 获取 JWT Token
GET  /api/projects/                            # 项目列表
POST /api/requirement-analysis/tasks/          # 创建需求分析任务
GET  /api/requirement-analysis/tasks/{id}/     # 查询任务状态
POST /api/testcases/                           # 创建测试用例
GET  /api/testcases/                           # 用例列表
POST /api/ui-automation/test-cases/            # 创建 UI 自动化用例
POST /api/                                     # API 测试用例（api_testing router）
```

## 启动 TestHub（如未运行）

```bash
# 后端（从项目根目录）
cd ..
source venv/Scripts/activate
python manage.py runserver

# 前端（从项目根目录）
cd ../frontend
"D:/software/Node/node.exe" node_modules/vite/bin/vite.js
```
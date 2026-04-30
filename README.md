# FundAgent

基金本子多 Agent 辅助撰写 Web 应用，支持 3 种 Agent 切换，各自独立对话历史

## Agent 说明

| Agent | 模型 | 说明 |
|-------|------|------|
| **研究背景 Agent** | Kimi k2.6 | 自动联网搜索文献，撰写"研究背景"段落 |
| **初稿 Agent** | DeepSeek Chat | 撰写完整基金初稿 |
| **段落修改 Agent** | DeepSeek Chat | 对已有段落进行修改润色，输出修改说明表格 |

## 配置

在项目根目录创建 `.env` 文件（GBK 编码）：

```env
DEEPSEEK_API_KEY=sk-your-deepseek-api-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

SEARCH_API_KEY=sk-your-moonshot-api-key
```

### 获取 API Key

- **DeepSeek API Key**：[platform.deepseek.com](https://platform.deepseek.com/) — 用于初稿 Agent 和段落修改 Agent
- **Moonshot (Kimi) API Key**：[platform.moonshot.cn](https://platform.moonshot.cn/console) — 用于研究背景 Agent 的联网搜索

## 启动

```bash
cd FundAgent
python app.py
```

浏览器访问 `http://127.0.0.1:8000`

## 项目结构

```
FundAgent/
├── app.py              # FastAPI 后端，路由 + LLM 调用
├── .env                # API Key 配置（GBK 编码）
├── prompts/            # Agent system prompt 文件
│   ├── background.md   # 研究背景 Agent prompt
│   ├── draft.md        # 初稿 Agent prompt
│   └── reviser.md      # 段落修改 Agent prompt
├── static/             # 前端静态文件
│   └── index.html      # 单页 Web 应用
├── test_kimi/          # Kimi API 测试脚本
└── README.md
```

# astrbot_plugin_deepsider

把 [DeepSider2API](https://github.com/WWDELE114514/DeepSider2API) 网关接入 AstrBot，让机器人可以：

- 查询账号池每个账号的剩余积分 / 总积分
- 列出可用模型（chat / image / video）
- 查询某个账号的专属邀请码
- **指定账号与模型**生成图片
- 与文本模型对话

> 本插件通过 HTTP 调用本地运行的 **DeepSider2API 网关**（`deepsider2api.exe`），不直接访问 DeepSider。
> 功能与同项目的 MCP server（`cmd/mcp`）一致，灵感来源即该 MCP。

## 前置

1. 运行 DeepSider2API 网关（默认 `http://127.0.0.1:7863`）。
2. AstrBot 与网关在**同一台机器**（或网络可达）。

## 安装

把本仓库克隆到 AstrBot 的插件目录：

```bash
cd AstrBot/data/plugins
git clone https://github.com/WWDELE114514/DeepSider2API-AstrBot.git astrbot_plugin_deepsider
```

然后在 AstrBot WebUI 的「插件」页重载该插件。若缺依赖，插件会自动按 `requirements.txt` 安装（`httpx`）。

## 配置

WebUI →「插件」→「DeepSider 网关」→ 配置：

| 配置项 | 说明 | 默认 |
| :--- | :--- | :--- |
| `base_url` | 网关地址 | `http://127.0.0.1:7863` |
| `api_key` | 网关管理密钥（`config.json` 的 `api_key`） | `change_me` |
| `default_image_model` | `/生图` 未指定模型时使用 | `pro/gemini-3.1-flash-lite-image` |
| `default_chat_model` | `/对话` 未指定模型时使用 | `auto` |

## 指令

| 指令（别名） | 说明 |
| :--- | :--- |
| `/积分`（`/ds积分` `/余额`） | 各账号剩余积分 + 总积分 |
| `/模型 [chat\|image\|video]`（`/ds模型`） | 列出模型 |
| `/邀请 <邮箱或 id>`（`/ds邀请`） | 查询该账号的邀请码 / 邀请链接 / 邀请统计 |
| `/生图 <提示词> [--model botId] [--account 邮箱] [--size 1024x1024] [--ratio 1:1] [--resolution 1k]` | 生成图片 |
| `/对话 <内容> [--model botId]`（`/ds聊`） | 文本对话 |

### 示例

```
/积分
/模型 image
/邀请 qweasdzxc8620@qq.com
/生图 一只戴着帽子的橘猫，赛博朋克风格 --model pro/gemini-3.1-flash-lite-image --account qweasdzxc8620@qq.com
/生图 赛博朋克城市 --size 1792x1024
/对话 用一句话介绍你自己 --model auto
```

> 图片由网关**转存**后以永久链接返回（`image.persist=true` 时），避免 DeepSider 的 24 小时失效。

## 依赖

- `httpx`（见 `requirements.txt`）
- AstrBot 版本：建议 `>=4.16`

## License

MIT。灵感来源：[DeepSider2API](https://github.com/WWDELE114514/DeepSider2API)（模型编排部分参考 [workbuddy2api-panel-plus](https://github.com/JACKY199503/workbuddy2api-panel-plus) 系）。

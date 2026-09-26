"""DeepSider 网关 AstrBot 插件。

通过 DeepSider2API 网关（deepsider2api.exe）提供的 HTTP 接口，让机器人可以：
  - 查询账号池各账号的剩余积分 / 总积分
  - 列出可用模型（chat / image / video）
  - 查询指定账号的专属邀请码
  - 指定模型生成图片
  - 与文本模型对话

灵感与功能对齐自同项目的 MCP server（DeepSider2API 仓库 cmd/mcp）。
"""

import re

import httpx

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

_OPT_RE = re.compile(r"--(\w+)\s+(\S+)")


@register(
    "deepsider",
    "WWDELE114514",
    "DeepSider 网关：查积分/邀请码、按模型生成图片、对话",
    "1.1.0",
)


class DeepSiderPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config

    # ------------------------------------------------------------------ 工具
    def _base(self) -> str:
        return str(self.config.get("base_url") or "http://127.0.0.1:7863").rstrip("/")

    def _headers(self) -> dict:
        return {
            "Authorization": "Bearer " + str(self.config.get("api_key") or "change_me"),
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None):
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                self._base() + path, headers=self._headers(), params=params
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, body: dict, timeout: float = 300):
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                self._base() + path, headers=self._headers(), json=body
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _args(event: AstrMessageEvent) -> str:
        """去掉消息开头的指令词（含别名），返回后面的参数文本。"""
        text = (event.message_str or "").strip()
        if text.startswith("/"):
            text = text[1:]
        parts = text.split(None, 1)
        return parts[1].strip() if len(parts) > 1 else ""

    @staticmethod
    def _parse_opts(raw: str):
        """解析 `--key value` 选项，返回 (剩余文本, {key: value})。"""
        opts = {m.group(1): m.group(2) for m in _OPT_RE.finditer(raw)}
        return _OPT_RE.sub("", raw).strip(), opts

    @staticmethod
    def _split_model_prompt(text: str, default_model: str):
        """支持 `模型 描述` 或 `描述`（用默认模型）。

        botId 形如 `pro/gemini-3.1-flash-lite-image`（ASCII 且含 `/`），
        因此仅当第一个词是 ASCII 且含 `/` 时才当作模型，否则整段视为描述。
        """
        parts = text.split(None, 1)
        if parts:
            first = parts[0]
            if "/" in first and first.isascii():
                prompt = parts[1].strip() if len(parts) > 1 else ""
                return first, prompt
        return default_model, text

    # -------------------------------------------------------------- 指令实现
    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("积分", alias={"ds积分", "ds余额", "余额", "账号", "ds账号"})
    async def credits(self, event: AstrMessageEvent):
        """查看账号池各账号剩余积分、套餐、状态、失败次数与总积分"""
        try:
            data = await self._get("/api/panel/accounts")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[deepsider] 查询积分失败: {exc}")
            yield event.plain_result(f"查询失败：{exc}")
            return

        accounts = data.get("accounts", [])
        if not accounts:
            yield event.plain_result("账号池为空，请先在网关面板添加账号。")
            return

        lines = ["DeepSider 账号积分："]
        total = 0.0
        for acc in accounts:
            credit = float(acc.get("credit_remaining") or 0)
            status = "启用" if acc.get("enabled") else "停用"
            name = acc.get("email") or acc.get("name") or "-"
            extra = ""
            fails = int(acc.get("fail_count") or 0)
            if fails > 0:
                extra = f" | 失败{fails}"
            lines.append(
                f"· {name} | {credit:.0f} | {acc.get('plan_name') or '-'} | {status}{extra}"
            )
            if acc.get("enabled"):
                total += credit
        lines.append(f"\n合计（启用）：{total:.0f} 积分 / 共 {len(accounts)} 个账号")
        yield event.plain_result("\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("模型", alias={"ds模型"})
    async def models(self, event: AstrMessageEvent):
        """列出模型：/模型 [chat|image|video]"""
        want = self._args(event).lower() or "all"
        try:
            data = await self._get("/api/panel/models")
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[deepsider] 查询模型失败: {exc}")
            yield event.plain_result(f"查询失败：{exc}")
            return

        lines = [f"DeepSider 模型（{want}）："]
        count = 0
        for model in data.get("models", []):
            if model.get("disabled"):
                continue
            bot_id = model.get("botId")
            if not bot_id:
                continue
            kind = "chat"
            if model.get("isDrawing") or model.get("classification") == "image":
                kind = "image"
            elif model.get("asyncGenerateVideo") or model.get("classification") == "video":
                kind = "video"
            if want != "all" and want != kind:
                continue
            lines.append(f"· [{kind}] {model.get('title') or bot_id} | {bot_id} | {model.get('credits')}分")
            count += 1
            if count >= 40:
                lines.append("……（仅显示前 40 个）")
                break
        if count == 0:
            yield event.plain_result(f"没有匹配「{want}」的模型。")
            return
        yield event.plain_result("\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("邀请", alias={"ds邀请", "邀请码"})
    async def invitation(self, event: AstrMessageEvent):
        """查询账号邀请码：/邀请 <账号邮箱或 id>"""
        account = self._args(event)
        if not account:
            yield event.plain_result("用法：/邀请 <账号邮箱或 id>")
            return
        try:
            data = await self._get("/api/panel/invitation", params={"account": account})
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[deepsider] 查询邀请码失败: {exc}")
            yield event.plain_result(f"查询失败：{exc}")
            return

        code = data.get("invitation_id") or ""
        link = f"https://web.deepsider.online/?c={code}"
        yield event.plain_result(
            f"账号：{data.get('email') or account}\n"
            f"邀请码：{code}\n"
            f"邀请链接：{link}\n"
            f"已邀请：{data.get('invited_count') or 0} 人 ｜ 奖励积分：{data.get('reward_credits') or 0}"
        )

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("生成图片", alias={"生图", "画图", "绘图", "ds生图"})
    async def generate_image(self, event: AstrMessageEvent):
        """生成图片：/生成图片 <模型botId> <描述>  或  /生成图片 <描述>

        可追加选项：--account 邮箱  --size 1024x1024  --ratio 1:1  --resolution 1k
        """
        raw = self._args(event)
        if not raw:
            yield event.plain_result(
                "用法：/生成图片 <模型botId> <描述>\n"
                "示例：/生成图片 pro/gemini-3.1-flash-lite-image 一只戴着帽子的橘猫\n"
                "也可省略模型（用默认模型）：/生成图片 赛博朋克城市"
            )
            return

        text, opts = self._parse_opts(raw)
        default_model = self.config.get("default_image_model") or "pro/gemini-3.1-flash-lite-image"
        model, prompt = self._split_model_prompt(text, default_model)
        if opts.get("model"):
            model = opts["model"]
        if not prompt:
            yield event.plain_result("请提供图片描述。示例：/生成图片 " + model + " 一只橘猫")
            return

        body = {
            "prompt": prompt,
            "model": model,
            "account": opts.get("account", ""),
            "size": opts.get("size", ""),
            "ratio": opts.get("ratio", ""),
            "resolution": opts.get("resolution", ""),
        }
        yield event.plain_result(f"🎨 正在用 {model} 生成图片，请稍候…")
        try:
            data = await self._post("/api/panel/generate", body, timeout=300)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[deepsider] 生成图片失败: {exc}")
            yield event.plain_result(f"生成失败：{exc}")
            return

        chain = []
        for item in data.get("data") or []:
            url = item.get("url")
            if url:
                chain.append(Comp.Image.fromURL(url))
        if not chain:
            yield event.plain_result("生成失败：没有返回图片。")
            return
        chain.append(Comp.Plain(f"\n模型：{data.get('model')}"))
        yield event.chain_result(chain)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("对话", alias={"ds对话", "ds聊", "ds问"})
    async def chat(self, event: AstrMessageEvent):
        """文本对话：/对话 <模型botId> <内容>  或  /对话 <内容>"""
        raw = self._args(event)
        if not raw:
            yield event.plain_result(
                "用法：/对话 <内容>（默认模型 auto）\n示例：/对话 用一句话介绍你自己"
            )
            return

        text, opts = self._parse_opts(raw)
        default_model = self.config.get("default_chat_model") or "auto"
        model, prompt = self._split_model_prompt(text, default_model)
        if opts.get("model"):
            model = opts["model"]
        if not prompt:
            yield event.plain_result("请提供对话内容。")
            return

        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            data = await self._post("/v1/chat/completions", body, timeout=300)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[deepsider] 对话失败: {exc}")
            yield event.plain_result(f"对话失败：{exc}")
            return

        choices = data.get("choices") or []
        if not choices:
            yield event.plain_result("对话失败：无回复。")
            return
        content = (choices[0].get("message") or {}).get("content") or ""
        yield event.plain_result(content)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("总积分", alias={"ds总积分", "总余额"})
    async def total_credits(self, event: AstrMessageEvent):
        """只返回启用账号的总剩余积分"""
        try:
            data = await self._get("/api/panel/accounts")
        except Exception as exc:  # noqa: BLE001
            yield event.plain_result(f"查询失败：{exc}")
            return
        total = 0.0
        enabled = 0
        for acc in data.get("accounts", []):
            if acc.get("enabled"):
                total += float(acc.get("credit_remaining") or 0)
                enabled += 1
        yield event.plain_result(f"总剩余积分：{total:.0f}（{enabled} 个启用账号）")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("刷新", alias={"ds刷新"})
    async def refresh(self, event: AstrMessageEvent):
        """刷新指定账号的积分/套餐状态：/刷新 <账号邮箱或 id>"""
        key = self._args(event)
        if not key:
            yield event.plain_result("用法：/刷新 <账号邮箱或 id>")
            return
        try:
            data = await self._get("/api/panel/accounts")
        except Exception as exc:  # noqa: BLE001
            yield event.plain_result(f"查询失败：{exc}")
            return

        target = None
        for acc in data.get("accounts", []):
            if acc.get("id") == key or (acc.get("email") or "").lower() == key.lower():
                target = acc
                break
        if not target:
            yield event.plain_result(f"找不到账号：{key}")
            return

        try:
            await self._post(f"/api/panel/accounts/{target['id']}/refresh", {})
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[deepsider] 刷新账号失败: {exc}")
            yield event.plain_result(f"刷新失败：{exc}")
            return

        try:
            data2 = await self._get("/api/panel/accounts")
            for acc in data2.get("accounts", []):
                if acc.get("id") == target["id"]:
                    yield event.plain_result(
                        f"已刷新 {acc.get('email') or key}："
                        f"{float(acc.get('credit_remaining') or 0):.0f} 积分 | {acc.get('plan_name') or '-'}"
                    )
                    return
        except Exception:  # noqa: BLE001
            pass
        yield event.plain_result("已刷新。")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("密钥", alias={"ds密钥", "dskeys"})
    async def keys(self, event: AstrMessageEvent):
        """列出网关 API 密钥及各自用量"""
        try:
            data = await self._get("/api/panel/keys")
        except Exception as exc:  # noqa: BLE001
            yield event.plain_result(f"查询失败：{exc}")
            return
        keys = data.get("keys", [])
        if not keys:
            yield event.plain_result("还没有 API 密钥，可在网关面板「API 密钥」页创建。")
            return
        lines = ["DeepSider API 密钥："]
        for key in keys:
            status = "启用" if key.get("enabled") else "停用"
            lines.append(
                f"· {key.get('name') or '-'} | {key.get('prefix')}... | 用量 {key.get('usage') or 0} | {status}"
            )
        yield event.plain_result("\n".join(lines))

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("帮助", alias={"ds帮助", "dshelp", "ds菜单", "菜单"})
    async def help(self, event: AstrMessageEvent):
        """列出所有指令（QQ 下以合并转发形式发送）"""
        sections = [
            (
                "📊 账号与积分",
                [
                    "/积分 — 各账号 积分/套餐/状态/失败次数 + 总积分",
                    "/总积分 — 只回启用账号总积分",
                    "/刷新 <邮箱或 id> — 刷新该账号积分/套餐状态",
                    "/邀请 <邮箱或 id> — 查邀请码 / 邀请链接 / 邀请统计",
                    "/密钥 — 列出网关 API 密钥及各自用量",
                ],
            ),
            (
                "🎨 模型与生成",
                [
                    "/模型 [chat|image|video] — 列出可用模型",
                    "/生成图片 <模型> <描述> [选项] — 生成图片（模型可省略）",
                    "  选项：--account 邮箱  --size 1024x1024  --ratio 1:1  --resolution 1k",
                    "/对话 <模型> <内容> — 文本对话（模型可省略）",
                ],
            ),
            (
                "ℹ️ 说明",
                [
                    "模型填 DeepSider 的 botId，用 /模型 查看",
                    "省略模型时使用配置里的默认模型",
                    "所有指令仅管理员可用",
                ],
            ),
        ]
        text_all = "\n\n".join(f"【{t}】\n" + "\n".join(lines) for t, lines in sections)

        try:
            platform = event.get_platform_name()
        except Exception:  # noqa: BLE001
            platform = ""

        if platform == "aiocqhttp":
            uin = "10000"
            try:
                uin = str(event.get_self_id() or "10000")
            except Exception:  # noqa: BLE001
                pass
            nodes = [
                Comp.Node(
                    uin=uin,
                    name="DeepSider 网关",
                    content=[Comp.Plain(f"【{t}】\n" + "\n".join(lines))],
                )
                for t, lines in sections
            ]
            yield event.chain_result([Comp.Nodes(nodes)])
        else:
            yield event.plain_result(text_all)

    async def terminate(self):
        """插件卸载 / 停用时调用。"""
        logger.info("[deepsider] 插件已停用")

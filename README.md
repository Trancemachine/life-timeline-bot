# 🗓️ 生活记录 Bot

飞书 Bot：语音/文字记录每天经历，自动写入日历，按项目查询时间线。

## 零服务器方案

```
GitHub（托管代码） → Vercel（免费运行 + HTTPS域名） → 飞书日历
```

---

## 一、GitHub 部署代码

### 1.1 创建 GitHub 仓库

打开 [github.com](https://github.com) → 点 `+` → `New repository` → 名称随便填（如 `life-timeline-bot`）→ 公开/私有都可以 → `Create repository`

### 1.2 上传代码

在终端执行（替换 `<你的用户名>`）：

```bash
cd D:\Program Files\life-timeline-bot

git init
git add .
git commit -m "init"
git remote add origin https://github.com/<你的用户名>/life-timeline-bot.git
git branch -M main
git push -u origin main
```

> 如果没装 Git：去 https://git-scm.com/downloads/win 下载安装

---

## 二、部署到 Vercel（免费）

### 2.1 注册 Vercel

打开 [vercel.com](https://vercel.com) → 点 `Sign Up` → **用 GitHub 登录**（最方便）

### 2.2 导入仓库导入

登录后点 `Add New...` → `Project` → 找到 `life-timeline-bot` → `Import`

### 2.3 配置环境变量

在部署页面点 `Environment Variables`，添加以下 6 个：

| Name | Value |
|------|-------|
| `FEISHU_APP_ID` | `cli_aa8b536a13791cb5` |
| `FEISHU_APP_SECRET` | `e1IB8HDhsuDu5Ze6v5eXrlCxOmItQg5K` |
| `FEISHU_BASE_TOKEN` | `T35sbKGYga8LF0szmECc72pOnbb` |
| `FEISHU_EVENT_TABLE_ID` | `tblFHJR46ABafFCh` |
| `FEISHU_PROJECT_TABLE_ID` | `tblKk3IrM28O25X3` |
| `FEISHU_CALENDAR_ID` | （留空自动用主日历） |

不要勾选 "Use in Preview" 和 "Use in Development"，只勾 **Production**

### 2.4 部署

点 `Deploy` → 等待 ~1 分钟 → 部署完成后会显示一个 URL，类似：

```
https://life-timeline-bot.vercel.app
```

**复制这个 URL，下一步要用。**

---

## 三、配置飞书应用

打开 [飞书开发者后台](https://open.feishu.cn/app) → 点击应用 `cli_aa8b536a13791cb5`

### 3.1 开通权限

左侧 → `权限管理` → 搜索并开通以下权限（每个点「开通」）：

- `im:message`（收发消息）
- `im:message:send_as_bot`（以 bot 身份发消息）  
- `calendar:calendar`（读写日历）
- `calendar:calendar.event`（管理日历事件）
- `speech_to_text`（语音转文字）
- `drive:drive`（上传图片）
- `drive:drive:upload`（上传文件）

### 3.2 配置事件订阅

左侧 → `事件与回调` → `回调配置`

- 回调 URL 填：`https://<vercel域名>/webhook/event`
  - 例：`https://life-timeline-bot.vercel.app/webhook/event`

点「保存」→ 如果能保存成功说明连通了

### 3.3 添加事件

还是在 `事件与回调` → `添加事件`：

- 搜索 `im.message.receive_v1` → 添加

### 3.4 添加机器人能力

左侧 → `应用功能` → `机器人` → 开启

### 3.5 发布应用

左侧 → `版本管理与发布` → `创建版本` → 填写版本号（如 `1.0.0`）和更新说明 → `保存` → `发布`

> 发布需要审核，约 1 分钟 → 在飞书搜索应用名就可以发消息了

---

## 四、测试效果

在飞书搜索你的 Bot → 发消息：

```
4.22学了科目二半天
```

收到回复：

```
✅ 已记录
📅 4月22日
📝 学了科目二半天
🏷 考驾照
```

打开飞书日历 → 4月22日 → 看到这条事件 ✅

查询：

```
学车时间线
```

收到时间线回复。

---

## 五、调试

访问 `https://<vercel域名>/health` 会返回 `{"status": "ok"}`

如果 Bot 没响应，检查：
1. Vercel 的日志：Vercel Dashboard → Project → Deployments → 点最新部署 → `Functions` → 看最近调用
2. 飞书开发者后台 → `事件与回调` → 查看最近回调记录

---

## 六、将 Base 分享给机器人

Bot 代码运行在 Vercel 上，使用 app_id+app_secret（bot 身份）访问飞书 API。Base 需要授权给 bot 才能读写：

1. 打开 Base 链接：**https://my.feishu.cn/base/T35sbKGYga8LF0szmECc72pOnbb**
2. 点右上角「共享」
3. 搜索你的机器人应用名称 → 添加为「编辑者」
4. 保存

## 七、配置自定义项目归类

编辑 `config/config.example.yaml` 里的 `projects` 段，可以自定义项目关键词。

在 Vercel 上部署时如果改了关键词，手动更新 `src/nlp.py` 里的 `_match_project` 函数用到的配置，或者通过环境变量传入 JSON。

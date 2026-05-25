# 生活记录 Bot

飞书 Bot：语音/文字记录每天经历，自动写入日历，按项目查询时间线（文字+图片）。

## 架构

```
语音/文字 → 飞书 → 阿里云函数计算（FC）→ 多维表格（Base）存储 + 日历写入 → 回复确认
                                              ↓
                                        查询时 → 从 Base 读取 → 文字时间线 + 图片时间轴
```

---

## 一、代码部署到阿里云函数计算（FC）

### 1.1 安装 Serverless Devs

打开终端（PowerShell），运行：

```bash
npm install @serverless-devs/s -g
```

> 如果没装 Node.js：去 https://nodejs.org 下载 LTS 版安装

### 1.2 配置阿里云账号

```bash
s config add
```

按提示输入：
- **Aliyun Access Key ID** 和 **Aliyun Access Key Secret**
  - 去 https://ram.console.aliyun.com/manage/ak 获取（或创建）
- **Account ID**：你的阿里云主账号 ID
  - 去控制台右上角头像 → 「安全设置」→ 查看「账号 ID」

### 1.3 配置环境变量

在项目目录创建 `.env` 文件（或者直接设置系统环境变量）：

```
FEISHU_APP_ID=cli_aa8b536a13791cb5
FEISHU_APP_SECRET=e1IB8HDhsuDu5Ze6v5eXrlCxOmItQg5K
FEISHU_BASE_TOKEN=你Base的token
FEISHU_EVENT_TABLE_ID=你事件表的table_id
FEISHU_PROJECT_TABLE_ID=你项目表的table_id
FEISHU_CALENDAR_ID=
```

> `FEISHU_CALENDAR_ID` 留空会自动用主日历

### 1.4 部署

```bash
cd "D:\Program Files\life-timeline-bot"
s deploy
```

等待约 2 分钟（第一次会安装依赖包并打包上传）。部署完成会输出一个**公网 URL**，类似：

```
https://bot-handler-xxxx.cn-hangzhou.fcapp.run
```

**复制这个 URL，下一步要用。**

---

## 二、创建多维表格（Base）

### 2.1 新建 Base

1. 打开飞书 → 左侧点「多维表格」
2. 点「新建」→ 选择「空白多维表格」
3. 名称填「生活记录」
4. 创建成功后，浏览器地址栏的 URL 是 `https://xxx.feishu.cn/base/XXXXXXXXXXXXX`
   - **复制最后那串 27 位的 token**（例如 `T35sbKGYga8LF0szmECc72pOnbb`）

### 2.2 建「项目表」

1. 在 Base 底部点「+」新建一个数据表
2. 表名改「项目表」
3. 创建字段：

| 字段名 | 字段类型 |
|--------|---------|
| 项目名称 | 文本 |
| 别名 | 文本 |

4. 添加几条项目数据（这是自动归类用的"字典"）：

| 项目名称 | 别名 |
|---------|------|
| 考驾照 | 学车,驾照,科二,科三 |
| 找工作 | 面试,offer,招聘 |
| 健身 | 拉背,卧推,跑步 |
| 法务 | 法院,诉讼,律师 |
| 学习 | 看书,听课,复习 |

### 2.3 建「事件表」

1. 再点「+」建一个表，表名改「事件表」
2. 创建字段：

| 字段名 | 字段类型 | 备注 |
|--------|---------|------|
| 日期时间 | 日期 | 格式选 `yyyy-MM-dd HH:mm` |
| 结束时间 | 日期 | 格式选 `yyyy-MM-dd HH:mm`，可选 |
| 事件内容 | 文本 | |
| 原始消息 | 文本 | |
| 项目标签 | 关联 | 关联到「项目表」的「项目名称」，打开多选 |

### 2.4 拿到配置值

| 名称 | 从哪拿 |
|------|--------|
| base_app_token | Base URL 里那段 27 位字符串 |
| event_table_id | 点进事件表，URL 里有 `?table=tblxxxxx` |
| project_table_id | 点进项目表，URL 里有 `?table=tblxxxxx` |

---

## 三、配置飞书应用

打开 https://open.feishu.cn/app → 点应用 `cli_aa8b536a13791cb5`

### 3.1 开通权限

左侧 → 权限管理 → 搜索并开通以下权限：

| 权限 | 说明 |
|------|------|
| `im:message` | 收发消息 |
| `im:message:send_as_bot` | 以 bot 身份发消息 |
| `calendar:calendar` | 读写日历 |
| `calendar:calendar.event` | 管理日历事件 |
| `speech_to_text` | 语音转文字 |
| `bitable:app` | 读写多维表格 |
| `drive:drive` | 上传图片 |

### 3.2 配置事件回调

左侧 → 事件与回调 → 回调配置

- 回调 URL 填：`https://你的FC域名/webhook/event`
  - 例如：`https://bot-handler-xxxx.cn-hangzhou.fcapp.run/webhook/event`
- 点「保存」

### 3.3 添加事件

左侧 → 事件与回调 → 点「添加事件」→ 搜索 `im.message.receive_v1` → 添加

### 3.4 开启机器人

左侧 → 应用功能 → 机器人 → 开启

### 3.5 发布应用

左侧 → 版本管理与发布 → 创建版本 → 版本号 `1.0.0` → 保存 → 发布

> 审核约 1 分钟。通过后在飞书搜索应用名就可以发消息了。

### 3.6 分享 Base 给机器人

1. 打开刚才创建的 Base（飞书里点「多维表格」→ 找「生活记录」）
2. 右上角点「共享」
3. 搜索你的机器人应用名称 → 添加为「编辑者」

---

## 四、测试

在飞书里找到你的 Bot，发消息：

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

查时间线：

```
学车时间线
```

收到文字时间线 + 图片时间轴。

**支持的输入格式：**

| 输入示例 | 效果 |
|---------|------|
| `4.22学了科目二半天` | 4月22日全天 |
| `4.22号10点面了xx公司` | 4月22日 10:00 |
| `今天10点到12点练车` | 今天 10:00-12:00 |
| `昨天下午3点去法院立案` | 昨天 15:00 + 归入法务 |
| `考驾照时间线` | 显示考驾照的所有记录+时间轴图片 |
| `健身时间轴` | 显示健身记录 |

---

## 五、调试

- **健康检查**：访问 `https://你的FC域名/health` → 返回 `{"status": "ok"}`
- **查看日志**：`s logs -t`（在项目目录运行）
- **重新部署**：改完代码后运行 `s deploy`
- **飞书回调日志**：开发者后台 → 事件与回调 → 查看最近记录

---

## 六、自定义项目归类

编辑 `src/nlp.py` 里的 `projects` 关键词配置，或者在 FC 环境变量中传入自定义 JSON。

## 七、文件说明

| 文件 | 用途 |
|------|------|
| `src/bot.py` | Flask Webhook 主入口，处理消息收发 |
| `src/feishu_client.py` | 飞书 API 封装（语音识别、消息、Base、日历） |
| `src/nlp.py` | NLP 解析（日期提取、项目匹配） |
| `src/timeline.py` | 时间线生成（文字 + matplotlib 图片） |
| `fc_handler.py` | 阿里云 FC 入口 |
| `s.yaml` | Serverless Devs 部署配置 |
| `config/config.yaml` | 本地配置（不提交到 Git） |

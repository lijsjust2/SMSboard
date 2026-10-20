# SmsBoard — SmsForwarder 配套看板

接收 SmsForwarder 推送的短信/通话/心跳，提供 Web 看板：累计统计、记录查询、**手机工作时长**、**实时电量**、设备在线状态与离线 PushPlus 告警。

**三种部署形态，前端完全相同：**

| 形态 | 适用 | 数据存储 | 特性差异 |
|---|---|---|---|
| Docker（NAS/云服务器） | 推荐，功能最全 | SQLite | WebSocket 实时 + 离线 PushPlus 告警 |
| **Cloudflare Worker** | 免服务器、全球访问 | R2 | 读取时推导在线状态，无 WS（前端自动轮询）、无离线推送 |
| 本地开发调试 | 开发者 | SQLite | 同 Docker |

```
SmsForwarder(手机)                         SmsBoard
 ├─ Webhook通道-短信 ──┐                    ┌─ 验签 → 入库
 ├─ Webhook通道-通话 ──┼── POST JSON ────►  ├─ 实时推送/轮询
 └─ 定时任务-心跳(5min)─┘  (带Key地址鉴权)   └─ 离线判定 → PushPlus 告警(Docker版)
```

## 一、部署

### Docker（Linux NAS / 云服务器，推荐）

```bash
cd smsboard
docker compose up -d --build
```

访问 `http://<服务器IP>:9990`，首次运行会进入初始化页，设置管理员账号密码后进入看板。

### 本地开发调试（Windows）

```powershell
# 后端
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --host 0.0.0.0 --port 9990

# 前端（开发热更）
cd frontend
npm install
npm run dev     # http://localhost:5173，已代理到 9990
```

## 二、SmsForwarder 手机端配置（App 内操作，无需改 App）

### 1. 新建 3 个 Webhook 发送通道

「发送通道 → 新建通道 → Webhook」。推荐使用 **Bark 式带 Key 地址**（看板「设置」页可查看和复制，无需配置签名）：

```
http://<看板服务器IP>:9990/api/push/<推送Key>
```

也可使用签名方式 `http://<看板服务器IP>:9990/api/webhook`（需在设置页配置 Secret 并在通道里开启签名）。

| 通道名 | URL | 请求参数(JSON) |
|---|---|---|
| 看板-短信 | 同上 | `{"type":"sms","from":"[from]","content":"[content]","sim":"[card_slot]","device":"[device_mark]","time":"[receive_time:yyyy-MM-dd HH:mm:ss]","timestamp":[timestamp],"sign":"[sign]"}` |
| 看板-通话 | 同上 | `{"type":"call","from":"[from]","content":"[content]","sim":"[card_slot]","device":"[device_mark]","time":"[receive_time:yyyy-MM-dd HH:mm:ss]","timestamp":[timestamp],"sign":"[sign]"}` |
| 看板-心跳 | 同上 | `{"type":"heartbeat","battery":"{{BATTERY_PCT}}","plugged":"{{BATTERY_PLUGGED}}","info":"{{BATTERY_INFO}}","device":"[device_mark]","time":"[CURRENT_TIME]","timestamp":[timestamp],"sign":"[sign]"}` |

**三个通道都**：
- 请求类型：`POST`；Content-Type 自动识别为 JSON（参数以 `{` 开头即可）
- Key 方式无需签名（`sign` 字段可保留不填）；签名方式则勾选「签名」并填 Secret
- 「响应校验」留空或填 `ok`（服务端返回 `{"code":200,"msg":"ok"}`）

### 2. 转发规则

- 短信规则：消息类型勾「短信」→ 发送通道选「看板-短信」（已有 pushplus 规则可并存，多选通道）
- 通话规则：新建规则，消息类型勾「通话」→ 发送通道选「看板-通话」；App「通用设置」需开启**转发通话**相关开关

### 3. 心跳定时任务

「自动任务 → 定时任务」新建，Cron 用 **7 位 Quartz 格式（第一位是秒）**：

```
0 0/5 * * * ?
```

（每 5 分钟的第 0 秒执行一次。⚠️ 不要用 `* * * * * ? *` 或把间隔填在秒位，否则会每秒发一次）发送通道选「看板-心跳」。

间隔可调，但需与看板「设置」页的心跳间隔一致；离线阈值在看板设置页直接配置（默认 15 分钟无心跳判离线）。

## 三、多设备支持

- 每台手机安装 SmsForwarder 后，在「通用设置 → 设备标记」里设置**不同的标记**（如 `旧手机-OPPO`、`备机-Redmi`），推送时会带在 `device` 字段
- 看板按标记**自动发现设备**，在「设备管理」页可重命名、备注、删除
- SIM 卡同样按消息中的卡槽信息（`{{CARD_SLOT}}`）自动发现，归属到对应设备下，可设置别名（如"主卡-联通"）
- 仪表盘/记录/电量/工作时长均支持按设备（及 SIM 卡）筛选；离线告警按设备独立判定与推送

## 四、GitHub Actions 自动构建 Docker 镜像

仓库自带 `.github/workflows/docker-release.yml`（参考 Frpc-WebUI 做法）：

1. **推送到 Docker Hub**：在仓库 Settings → Secrets → Actions 添加 `DOCKERHUB_USERNAME` 和 `DOCKERHUB_TOKEN`，打 tag（`v1.0.0`）或手动触发并勾选「是否推送到 Docker Hub」，自动构建 **amd64 + arm64** 双架构镜像并推送
2. **Release 附带离线镜像**：触发时自动构建 amd64 本地镜像，`docker save` 打包为 `smsboard-docker-amd64-<版本>.tar.gz` 附到 GitHub Release，无公网环境可 `docker load -i` 离线导入
3. 支持手动 `workflow_dispatch`：可只构建、可同时创建 Release、可选择是否推送 Hub

## 五、Cloudflare Pages 部署（edgetunnel 同款，免服务器）

Worker 版是同 API 的 JS 后端（`worker/dist/_worker.js`，Pages 高级模式），前端已预构建提交在 `worker/dist`，数据存 **R2**。**零构建，连接 Git 即可部署**：

### 部署步骤

1. **Fork 本仓库**到你的 GitHub 账号（欢迎点个 Star ⭐）
2. Cloudflare Dashboard → **Workers 和 Pages** → 创建应用程序 → **Pages** → **连接到 Git** → 选中你 Fork 的项目 → **开始设置**
3. 在「设置构建和部署」页面：
   - 构建命令：**留空**（前端已预构建）
   - 构建输出目录：**`/worker/dist`**
   - 展开「环境变量（高级）」→ 添加变量：名称 **`ADMIN`**，值填你的管理员密码 → **保存并部署**
4. 部署完成后，**绑定 R2 存储**（存消息数据）：
   - Pages 项目 → **设置** 选项卡 → **绑定** → **+ 添加** → **R2 存储桶**
   - 变量名称填 **`R2`**，选择一个已有的桶或新建一个（如 `smsboard`）→ **保存后重试部署**
5. 访问 `https://<项目名>.pages.dev/admin`，输入 `ADMIN` 环境变量里设置的管理员密码即可登录

### 绑定自定义域（可选）

Pages 控制台 → **自定义域** 选项卡 → **设置自定义域** → 填入次级域名（如 `sms.yourdomain.com`，不要用根域名）→ 按提示到你的 DNS 服务商添加 CNAME 记录指向 `<项目名>.pages.dev` → **激活域**

### 手机端配置

推送地址为：`https://<你的域名或 pages.dev 域>/api/push/<Key>`。Key 在看板「系统设置 → 推送 Key 管理」查看（用 ADMIN 部署时已自动生成），其余配置与 Docker 版完全相同。

### Worker 版差异

- 无 WebSocket：页面数据自动降级为轮询（消息页 20 秒/仪表盘 30 秒），顶部状态灯显示"未连接"属正常
- 无 PushPlus 离线推送：在线/离线状态在打开页面时实时推导
- 数据在 R2 桶内：`config/settings.json` 为配置，`data/` 为消息与心跳

> 前端或后端代码更新后，`worker/dist` 需要同步重建（Actions 的 Deploy workflow 会自动做，或本地 `npm run build` 后复制）。
>
> 也可以用一键按钮部署为标准 Worker：<https://deploy.workers.cloudflare.com/?url=https://github.com/lijsjust2/SMSboard>，或用仓库自带的「Deploy Cloudflare Worker」workflow 手动部署。

1. 访问 `https://<worker名>.<子域>.workers.dev`，首次进入设置管理员账号（推送 Key 自动生成）
2. 「系统设置」第 1 步的推送地址变为：`https://<worker域>/api/push/<Key>`，手机端配置方法完全相同
3. **Worker 版差异**（由架构决定）：
   - 无 WebSocket：页面数据自动降级为轮询（消息页 20 秒/仪表盘 30 秒），顶部状态灯显示"未连接"属正常
   - 无 PushPlus 离线推送：在线/离线状态在打开页面时实时推导
   - 数据存 R2：控制台 → R2 → `smsboard` 桶，`config/settings.json` 为配置，`data/` 为消息与心跳

## 六、安全提示

- **云服务器部署**：验证码属敏感数据。务必在设置页配置 Secret、`SMSBOARD_ALLOW_UNSIGNED=false`，并建议加 HTTPS 反代与防火墙白名单
- 数据库为 SQLite 单文件，位于 `backend/data/`，注意备份
- 修改管理员密码：删除 `backend/data/smsboard.db` 后重启（会清空全部数据）；或直接改库

## 七、测试

```bash
cd backend
pip install -r requirements.txt
pytest tests -q
```

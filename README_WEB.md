# AIMusicMed Web：本地启动与单机部署

这套交付面向少于 5 位受邀用户的腾讯云香港 2 核 2 GB Ubuntu 轻量应用服务器。Caddy 是唯一公网入口，自动申请 HTTPS；`/api/v1/*` 去掉前缀后转发到 FastAPI，其余请求转发到 vinext 前端。API、worker 和 SQLite/私有音频均不直接暴露公网。

## 当前上线前置条件

生产邮件使用腾讯云 SES API，不使用 SMTP。公网启用前必须确认 CAM 子用户具备 `QcloudSESFullAccess` 或等价的最小 SES 权限、验证码模板已审核通过，并实测中国大陆收件；同时保持 `AIMUSICMED_DEV_AUTH_CODES=false`，不要在公网返回验证码。

当前 2 GB 主机必须保持 `AIMUSICMED_GLOBAL_TASK_CONCURRENCY=1`。这表示整个平台同一时间只处理一个音频生成任务；不要按用户数把并发放大。运行 15 分钟音频混音或开放两个后台任务并发前，先升级到至少 4 GB 内存并重新压测。

内置公共曲库位于宿主机项目目录的 `music_library/`，仅以只读方式挂载到 worker 的 `/app/music_library`，不打进 Python 镜像。部署代码时可以单独同步曲库，日常代码升级无需重复上传或重建约 1 GB 的音乐素材。

## 已核对的真实入口

- API：`python -m uvicorn webapp.main:app --host 0.0.0.0 --port 8000`
- worker：`python -m webapp.worker`
- 前端构建：`npm run build`
- 前端生产服务：`npm run start -- --hostname 0.0.0.0 --port 3000`
- worker 依赖 `ffmpeg` 生成 MP3；Python 镜像已经安装。

## 本地 Docker 启动

要求 Docker Engine 和 Docker Compose v2。

```bash
cp deploy/.env.example deploy/.env
# 编辑 deploy/.env，替换全部 CHANGE_ME 和管理员邮箱
docker compose --env-file deploy/.env config --quiet
docker compose --env-file deploy/.env run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile
docker compose --env-file deploy/.env build
docker compose --env-file deploy/.env up -d
docker compose --env-file deploy/.env ps
docker compose --env-file deploy/.env logs -f api worker web caddy
```

本地只做 HTTP 联调时，不建议修改生产 Caddy 配置。可分别启动 API 和前端：

```powershell
python -m pip install -r requirements.txt -r requirements-web.txt
$env:AIMUSICMED_FERNET_KEY = '<Fernet key>'
$env:AIMUSICMED_WORKER_TOKEN = '<至少24字符>'
$env:AIMUSICMED_DEV_AUTH_CODES = 'true'
$env:AIMUSICMED_SECURE_COOKIES = 'false'
python -m uvicorn webapp.main:app --host 127.0.0.1 --port 8000
```

另开终端：

```powershell
cd web
npm ci
npm run dev -- --hostname 127.0.0.1 --port 3000
```

开发服务器已把同源 `/api/v1/*` 代理到 `http://127.0.0.1:8000` 并去掉前缀，因此 Cookie 登录无需放宽生产 CORS。

## 香港 Linux 单机部署

1. 确认 `aimusicmed.cn` 和 `www.aimusicmed.cn` 的 A 记录指向服务器公网地址；未分配 IPv6 时不要添加 AAAA 记录。
2. 防火墙只开放 TCP 22、80、443 和 UDP 443；不要开放 3000、8000 或 SQLite 文件。
3. 安装 Docker Engine 与 Compose v2，将仓库复制到服务器。
4. 创建 `deploy/.env`，权限设为仅管理员可读：

   ```bash
   cp deploy/.env.example deploy/.env
   chmod 600 deploy/.env
   ```

5. 填入域名、ACME 邮箱、管理员邮箱、SES/CAM 配置、平台 API Key 和随机密钥。不要把 SecretId、SecretKey 或其他 API Key 发到聊天、工单或日志中。
6. 为 2 GB 主机创建 2 GB swap，避免短时内存尖峰直接触发 OOM。以下命令可重复检查，但创建和写入 `/etc/fstab` 只执行一次：

   ```bash
   swapon --show
   free -h
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-aimusicmed-swap.conf
   sudo sysctl --system
   swapon --show
   free -h
   ```

   如果 `swapon --show` 已显示 `/swapfile`，跳过 `fallocate`、`mkswap` 和追加 `fstab`，只核对容量与权限。swap 是应急缓冲，不是用它替代内存升级。
7. 完成下方上线清单后启动：

   ```bash
   docker compose --env-file deploy/.env config --quiet
   docker compose --env-file deploy/.env run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile
   COMPOSE_PARALLEL_LIMIT=1 docker compose --env-file deploy/.env build --pull
   docker compose --env-file deploy/.env up -d
   docker compose --env-file deploy/.env ps
   curl --fail https://aimusicmed.cn/api/v1/health
   ```

生产域名固定为 `aimusicmed.cn`。Caddy 自动维护免费证书，其证书状态保存在 `caddy_data` volume；不需要购买付费 SSL、CDN、对象存储、云数据库或独立公网 IP。

Compose 已为 2 GB 主机设置容器内存上限：API 384 MB、worker 768 MB、前端 256 MB、Caddy 96 MB、备份 192 MB，总上限约 1.7 GB，为 Ubuntu、Docker 和文件缓存保留有限空间。所有容器日志均轮转为单文件 10 MB、最多 3 个文件。必须配置 2 GB swap 并保持全局单任务并发；若 worker 因真实音频负载触发 OOM，应先升级内存并复测，不要盲目提高所有容器上限。

## 环境变量

| 变量 | 必填 | 用途 |
|---|---:|---|
| `AIMUSICMED_DOMAIN` | 是 | Caddy 站点域名 |
| `AIMUSICMED_ACME_EMAIL` | 是 | ACME 证书通知邮箱 |
| `AIMUSICMED_FERNET_KEY` | 是 | 加密用户 BYOK 凭据；丢失后不可恢复 |
| `AIMUSICMED_WORKER_TOKEN` | 是 | API 与 worker 的内部鉴权，至少 24 字符 |
| `AIMUSICMED_ADMIN_EMAIL` | 是 | 首个管理员邮箱 |
| `AIMUSICMED_DEV_AUTH_CODES` | 是 | 仅本地测试可为 `true`；生产固定为 `false` |
| `AIMUSICMED_SECURE_COOKIES` | 是 | HTTPS 生产固定为 `true` |
| `AIMUSICMED_PUBLIC_BASE_URL` | 否 | 保留的公开站点地址配置；验证码邮件不拼接登录链接 |
| `TENCENTCLOUD_SECRET_ID` | 是 | CAM 子用户 SecretId，仅授予 SES 所需权限 |
| `TENCENTCLOUD_SECRET_KEY` | 是 | CAM 子用户 SecretKey，仅保存在服务器 `deploy/.env` 与本机密码管理器 |
| `TENCENTCLOUD_REGION` | 是 | 腾讯云 SES 区域，当前为 `ap-hongkong` |
| `AIMUSICMED_SES_FROM` | 是 | 已验证的 SES 发信身份：`AIMusicMed <no-reply@mail.aimusicmed.cn>` |
| `AIMUSICMED_SES_TEMPLATE_ID` | 是 | 腾讯云 SES 已审核通过的验证码模板 ID |
| `AIMUSICMED_SES_ALERT_TEMPLATE_ID` | 建议 | 管理员关键告警模板 ID，变量为 `title`、`message`、`time`；未配置时仍写入站内告警 |
| `AIMUSICMED_GLOBAL_TASK_CONCURRENCY` | 是 | 2 GB 主机固定为 `1`，全平台生成任务串行处理 |
| `DEEPSEEK_API_KEY` | 是 | 平台模式情绪分析和引导词 |
| `MINIMAX_API_KEY` | 是 | 平台模式音乐/TTS |
| `ELEVENLABS_API_KEY` | 否 | 平台 AI 音乐备用服务 |
| `AIMUSICMED_BACKUP_PASSPHRASE` | 是 | 独立加密备份；不得与 Fernet key 相同 |
| `AIMUSICMED_BACKUP_KEEP_DAILY` | 否 | 每日恢复点，默认 7 |
| `AIMUSICMED_BACKUP_KEEP_WEEKLY` | 否 | 每周恢复点，默认 4 |
| `AIMUSICMED_BACKUP_KEEP_MONTHLY` | 否 | 每月恢复点，默认 3 |
| `AIMUSICMED_BACKUP_MAX_REPO_MB` | 否 | 40 GB 主机的本机备份仓上限，默认 12288 MB |
| `AIMUSICMED_BACKUP_MIN_FREE_MB` | 否 | 备份前必须保留的磁盘空间，默认 6144 MB |

腾讯云 SES 模板正文必须使用后端约定的 3 个变量，变量名区分大小写，不要自行改名：

```text
您正在进行 {{action}}。

登录验证码：{{code}}

验证码在 {{expires}} 内有效，请勿转发或告诉他人。如果这不是你的操作，请忽略此邮件。
```

后端传给 SES `TemplateData` 的内容是 JSON 键值字符串，例如：

```json
{"action":"登录 AIMusicMed","code":"123456","expires":"15 分钟"}
```

其中 `action` 只使用“登录 AIMusicMed”或“激活 AIMusicMed 账号”，`code` 是系统生成的 6 位数字验证码，`expires` 固定为 `15 分钟`。验证码只在 SES 请求中短暂使用，数据库仅保存带服务端密钥的 HMAC 摘要；模板审核通过后，把其模板 ID 填入 `AIMUSICMED_SES_TEMPLATE_ID`。

原有 `AIMUSICMED_SMTP_*` 变量不再使用。`deploy/.env` 不应提交版本库，也不要把其内容贴进聊天、工单或日志。

## 数据与备份

`app_data` volume 保存 SQLite、WAL 文件、私有音频和任务目录。API 与 worker 共用该 volume。备份容器每天先用 SQLite `.backup` 生成一致性数据库快照，再把数据库快照与私有存储写入 restic 加密、内容去重仓库 `./backups/restic/`。未变化的音频块不会因每日备份重复占用空间。默认保留 7 个每日、4 个每周和 3 个每月恢复点。

用户未删除的原始录音一直保留在实时存储中，并由当前恢复点持续覆盖。用户删除后，该数据会在历史恢复点过期并 prune 后从备份中清理。40 GB 主机默认将本地备份仓限制为 12 GB，备份前预留至少 6 GB 空间。达到阈值时备份会失败并让容器健康检查报警，而不是继续挤占系统空间。此时应迁移备份仓、扩容或接入异地存储，不要盲目调高上限。

立即执行一次备份：

```bash
docker compose --env-file deploy/.env run --rm --no-deps backup /opt/backup/backup.sh
```

备份脚本完成后会直接输出并校验最新恢复点 ID，不需要绕过脚本单独调用 `restic`。

每月至少做一次非破坏性恢复验证（`latest` 仅可用于验证）：

```bash
docker compose --env-file deploy/.env run --rm --no-deps \
  -e BACKUP_SNAPSHOT=latest \
  backup /opt/backup/verify-backup.sh
```

验证会读取并校验 restic 仓库中的全部数据块，实际恢复数据库快照并执行 SQLite `integrity_check`，但不改动实时数据。该检查会读取所有备份数据，所以按月手动执行，不放进每日任务。

正式恢复是破坏性操作。先用 `restic snapshots` 记录要恢复的明确快照 ID，不允许使用会变化的 `latest`；再停止所有会读写数据的服务：

```bash
docker compose --env-file deploy/.env stop caddy api worker backup
docker compose --env-file deploy/.env run --rm --no-deps \
  -e RESTORE_CONFIRM=YES \
  -e BACKUP_SNAPSHOT=填写明确的快照ID \
  backup /opt/backup/restore.sh
docker compose --env-file deploy/.env up -d
docker compose --env-file deploy/.env ps
curl --fail https://aimusicmed.cn/api/v1/health
```

恢复后应登录、读取一条历史会话并试听一个测试音频。备份仓和实时数据仍在同一块磁盘上，只能防误删和软件故障，不能防主机或磁盘丢失。上线后应尽快把完整的 `backups/restic/` 同步到与服务器不同的私密位置，拷贝时不要遗漏隐藏文件。

## 运维命令

```bash
# 状态和日志（日志中不应出现 API Key）
docker compose --env-file deploy/.env ps
docker compose --env-file deploy/.env logs --tail=200 api worker caddy
docker stats --no-stream

# 安全更新并重建
COMPOSE_PARALLEL_LIMIT=1 docker compose --env-file deploy/.env build --pull
docker compose --env-file deploy/.env up -d

# 停止服务但保留 volumes
docker compose --env-file deploy/.env down

# 不要执行 docker compose --env-file deploy/.env down -v，除非已验证备份并明确要删除全部数据
```

## 不含密钥的上线清单

- [ ] 邮件发送实现及中国大陆收件测试已完成；生产保持 `AIMUSICMED_DEV_AUTH_CODES=false`。
- [ ] CAM 子用户权限仅覆盖 SES 所需操作；SES 模板已审核通过，模板变量与后端实现一致。
- [ ] 域名解析正确，80/443 可达，3000/8000 不可从公网访问。
- [ ] `swapon --show` 显示 2 GB swap，`AIMUSICMED_GLOBAL_TASK_CONCURRENCY=1`，容器未出现 OOMKilled。
- [ ] `docker compose --env-file deploy/.env config --quiet` 和全部镜像构建通过。
- [ ] `https://域名/api/v1/health` 返回 `{"status":"ok"}`。
- [ ] HTTPS Cookie 带 `Secure`、`HttpOnly`、`SameSite=Strict`。
- [ ] 只有管理员和白名单邮箱能收到验证码并登录；管理员首次验证码登录后必须立即设置密码。
- [ ] `/api/v1/internal/*` 从公网返回 404；worker 仍能从 Docker 私网领取任务。
- [ ] 平台模式和 BYOK 模式各完成一次获授权的最小测试；付费调用前已确认。
- [ ] 用户 A 无法读取用户 B 的会话、任务和下载文件。
- [ ] 生成任务关闭浏览器后继续，最终生成 WAV、MP3 和 TXT。
- [ ] 每日 10 次额度、每用户单任务和平台全局单并发符合预期。
- [ ] 备份文件已生成、已复制到异地私有存储，并在临时环境成功恢复。
- [ ] 日志、数据库导出、Compose 渲染结果中没有明文 API Key。
- [ ] 已记录 Fernet key 和备份密码，存放在服务器之外的密码管理器。
- [ ] 已确认音乐库和首页示例素材的公网授权。

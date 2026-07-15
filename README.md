# AIMusicMed：AI 情绪转换冥想音频生成器

根据我们的调研，ISO原则的音乐（先匹配当前情绪，再逐步转变音乐情绪至积极的音乐）作为背景音乐的冥想在焦虑、愤怒等高唤醒负面情绪的改善显著优于一般平静的冥想音乐。

输入一段当前感受和目标时长，AIMusicMed 会识别主要情绪并规划三阶段情绪路径。用户可以沿用 61 首本地音乐的曲库流程，也可以选择 ElevenLabs Music 或 MiniMax Music 2.6 为每个情绪阶段生成纯音乐。程序随后生成与音乐匹配的引导词并合成为可播放的 WAV。

项目采用音乐情绪调节中的ISO原则设计思路：先用音乐承接用户当下的情绪，再逐步过渡到平静或积极状态。前期调研将这条路径视为值得验证的产品假设。

> 这是产品原型和个人放松工具，不提供心理诊断、治疗或危机干预。出现持续心理困扰或紧急风险时，请联系专业机构或当地紧急服务。

## 工作流

```text
用户表达与目标时长
  → DeepSeek 识别主要情绪
  → 固定 SOP 规划三阶段情绪路径
  → 选择音乐来源
    ├─ 本地曲库：选择整首音乐并分析声学特征
    └─ AI 生成：DeepSeek 编写三阶段英文提示词
         → ElevenLabs Music 或 MiniMax Music 2.6 逐段生成纯音乐
         → 校验、转为 WAV 并分析声学特征
  → DeepSeek 按具体音乐生成逐段引导词
  → MiniMax TTS 生成语音
  → 语音混合、淡入淡出和重叠 crossfade
  → 输出 WAV
```

本地曲库模式保持原有流程。AI 音乐模式固定为三阶段、每阶段一首；DeepSeek 只负责情绪识别和提示词撰写，不能更改固定 SOP 给出的阶段情绪与时长。提示词生成失败时会重试一次，再失败则使用本地英文模板，并在元数据中标记。MiniMax 仍是唯一语音后端；TTS 请求失败时程序会直接报错，不会静默切换到低质量语音。

## Demo 亮点

- 情绪识别覆盖焦虑、忧郁、敌意、平静、喜悦、自豪、友爱 7 类情绪。
- 情绪路径由可解释的固定规则生成，典型路径为“当前情绪 → 平静 → 积极情绪”。
- 音乐来源可选本地曲库或 AI 生成；AI 生成支持 ElevenLabs Music 和 MiniMax Music 2.6 两个后端。
- 引导词在选定音乐后生成，并绑定曲目、阶段目标、声学特征和校验指纹，避免文案与音乐错配。
- 本地与 AI 音乐均不裁剪、不循环、不补静音。相邻音乐默认使用 3 秒重叠 crossfade。
- 每首音乐开头默认保留 4 秒纯音乐，再进入语音引导。
- MiniMax `speech-2.8-hd` 支持官方系统音色，也支持在获得授权后配置克隆音色。

## 实际运行链路

```text
run_py313_app.py
  → load_config
  → MeditationApp.create_meditation_session
    → prepare_session_plan
    → generate_music（本地曲库或 AI 音乐）
    → generate_guidance_for_music
    → generate_speech_adaptive
    → combine_audio_adaptive
    → <冥想时长>分钟_<情绪轨迹>.wav
```

本地曲库模式会根据目标时长按“每首约一分钟”估算曲目数量。AI 音乐模式则按 SOP 的三阶段目标时长各生成一首音乐。由于本地曲长、音乐 API 返回的实际时长和 crossfade 都可能带来偏差，最终音频时长通常不会与输入分钟数完全相同；程序会分别记录目标时长和实际时长，不会裁切、循环或补静音来强行对齐。

一次 5 分钟会话的终端结果示例：

```text
冥想会话创建完成
实际生成片段：5 个
实际总时长：327.8 秒
音频后端：librosa + soundfile
```

## 代码结构

| 路径 | 用途 |
| --- | --- |
| `run_py313_app.py` | 命令行入口和交互 |
| `py313_meditation_app.py` | 情绪、文本、音乐、TTS 和混音主流程 |
| `meditation_sop.py` | 三阶段路径规则和曲目数量规划 |
| `local_music_library.py` | 曲库扫描、情绪映射和关键词回退 |
| `music_generation_backends.py` | ElevenLabs/MiniMax 音乐生成、故障分类和音频校验 |
| `minimax_tts_backend.py` | MiniMax 请求、WAV 校验、重试和批量进度 |
| `audio_compat.py` | 音频读取、混合、重采样、crossfade 和峰值控制 |
| `config_manager.py` | JSON、`.env` 和环境变量配置 |
| `scripts/setup_minimax_voice.py` | 授权音色上传、克隆和激活验证 |
| `music_library/` | 7 类、61 个正式 WAV 素材文件 |
| `tests/` | 离线单元测试与整曲 smoke 脚本 |
| `config.json.example` | 不含密钥的配置模板 |
| `requirements.txt` | Python 运行依赖 |

## 快速开始

建议使用 Python 3.11 至 3.13。当前项目已在 Python 3.13.5 上验证。

```powershell
git clone https://github.com/Missingink5/AIMusicMed.git
cd AIMusicMed
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

复制本机配置：

```powershell
Copy-Item config.json.example config.json
notepad .env
```

在 `.env` 中填写：

```env
MINIMAX_API_KEY=你的_MiniMax_API_Key
DEEPSEEK_API_KEY=你的_DeepSeek_API_Key
ELEVENLABS_API_KEY=你的_ElevenLabs_API_Key
```

`MINIMAX_API_KEY` 是 TTS 所必需的，也供 MiniMax Music 2.6 复用。`DEEPSEEK_API_KEY` 可选；未配置或请求失败时，程序会使用本地回退逻辑。只有选择 ElevenLabs Music 时才需要 `ELEVENLABS_API_KEY`。AI 音乐模式会在付费请求前检查所选后端的密钥。

长引导词请求可通过 `DEEPSEEK_TIMEOUT_SECONDS` 调整超时，默认 `180` 秒。
DeepSeek 模型可通过 `DEEPSEEK_MODEL` 调整，默认使用 `deepseek-v4-flash`。

`.env` 和 `config.json` 已被 `.gitignore` 排除。不要把真实密钥写入源码、README、示例配置或 Git 提交。

## 配置

常用配置位于 `config.json`：

- `paths.base_dir`：最终 WAV 和日志的保存目录。留空时可通过 `MEDITATION_BASE_DIR` 指定。
- `preferred_track_duration_seconds`：规划曲目数量时采用的粗略单曲时长，默认 60 秒。
- `music_transition_fade_seconds`：淡入淡出和相邻曲目的重叠时长，默认 3 秒。
- `tts_backend`：只能设置为 `minimax`。
- `minimax_model`：默认 `speech-2.8-hd`。
- `minimax_voice_id`：系统音色或已激活的授权克隆音色 ID。
- `minimax_speed`：默认 `0.8`，用于较慢的冥想引导语速。
- `minimax_timeout_seconds`：单段 TTS 请求超时，默认 `600` 秒，用于较长音乐对应的长引导语音。
- `speech_start_delay_seconds`：每首音乐开始后等待多久进入语音，默认 4 秒。
- `music_volume_reduction`：混音时音乐相对语音的衰减量，默认 8 dB。

AI 音乐后端可通过环境变量调整：

- `ELEVENLABS_MUSIC_BASE_URL`：默认 `https://api.elevenlabs.io/v1`。
- `ELEVENLABS_MUSIC_MODEL`：默认 `music_v2`。
- `MINIMAX_MUSIC_BASE_URL`：默认 `https://api.minimaxi.com/v1`，与项目现有中国区 MiniMax TTS 密钥保持同一区域；国际区账户需显式改为 `https://api.minimax.io/v1`。
- `MINIMAX_MUSIC_MODEL`：默认 `music-2.6`。
- `MUSIC_REQUEST_TIMEOUT_SECONDS`：单次音乐生成请求超时，默认 `600` 秒。

本机 Demo 的成品目录可配置为：

```text
D:\ISO音乐-AI冥想疗愈生成\示例输出
```

## 运行

```powershell
.\.venv\Scripts\Activate.ps1
python run_py313_app.py
```

程序会依次要求选择或输入当前感受、设置时长、选择“本地曲库”或“AI 生成音乐”并确认生成。选择 AI 后还需选择 ElevenLabs 或 MiniMax 作为主音乐后端。完整运行会调用 DeepSeek、MiniMax TTS，以及所选音乐 API，依赖网络、账户额度和有效音色。

AI 音乐按阶段串行生成。网络连接失败、超时、HTTP 429、HTTP 5xx 或返回音频损坏时，程序会尝试使用另一个已配置的音乐后端一次；鉴权、余额、请求参数或内容审核错误会直接终止。备用后端没有密钥时会明确报错，不会静默改用本地曲库。超时等状态不能保证主后端未计费，因此自动切换在极端情况下可能产生两次生成费用，实际尝试记录会写入 manifest。

冥想引导词按每段音乐的实际时长动态扩展：目标朗读时长取“音乐时长减 10 秒”和“音乐时长的 87.5%”中的较小值，并受实际可用窗口约束。例如 60 秒音乐约生成 50 秒引导，400 秒音乐约生成 350 秒引导。DeepSeek 输出上限会按各段目标字数动态扩大到最高 8192 tokens，过短响应会重试一次；这是客户端请求上限，不会改变 DeepSeek 账户余额或速率额度。

ElevenLabs 使用明确的毫秒时长参数；MiniMax Music 2.6 没有精确时长字段，程序只会在提示词中写入目标秒数，并完整保留返回音乐。因此 MiniMax 的阶段时长可能明显偏离规划值，最终以 manifest 和会话摘要中的实际时长为准。

## AI 音乐产物

AI 模式除最终文件外，还会在同一输出位置保留阶段素材和生成记录。以 5 分钟“焦虑 → 平静 → 喜悦”为例：

```text
5分钟_焦虑-平静-喜悦.wav
5分钟_焦虑-平静-喜悦_素材\
  ├─ 阶段01_焦虑_elevenlabs.wav
  ├─ 阶段02_平静_minimax.wav
  ├─ 阶段03_喜悦_minimax.wav
  └─ generation_manifest.json
```

同名时，最终 WAV 与素材目录会使用同一个 `_2`、`_3` 递增序号。`generation_manifest.json` 记录匿名主题、阶段计划、生成提示词及来源、实际供应商、模型、目标/实际时长、错误和会话状态，不保存用户原始倾诉或 API Key。若中途失败，已付费生成的阶段 WAV 会保留，manifest 标为 `failed`，但不会输出不完整的最终冥想文件。

## 可选：配置授权克隆音色

仓库不分发参考人声。请把已获得明确授权的 WAV 放入被忽略的 `voice_refs/`，再使用一个从未创建过的新 `voice-id`：

```powershell
python scripts/setup_minimax_voice.py "voice_refs\your_authorized_reference.wav" `
  --voice-id AIMusicMedDemo20260714A --confirm-consent
```

该命令会把参考音频上传到 MiniMax，并执行一次激活验证，可能产生费用。创建成功后，将同一个 ID 写入本机 `config.json` 的 `minimax_voice_id`。不要上传未获授权的声音，也不要重复使用已经存在的 `voice-id`。

## 离线验证

以下命令不会调用付费 API：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pip check
python -m unittest discover -s tests -v
python -m unittest tests.test_music_generation -v
python local_music_library.py
```

测试默认使用 mock，不会调用真实音乐 API。需要验证付费接口时，应显式运行项目提供的 smoke test；不要把真实 API 调用加入默认测试套件。曲库扫描结果应为 7 个分类、61 个 WAV 文件。

显式付费 smoke test（会产生真实 API 费用）：

```powershell
$env:RUN_PAID_AI_MUSIC_SMOKE = "1"
$env:AI_MUSIC_SMOKE_PROVIDER = "elevenlabs"  # 或 minimax
python tests/smoke_ai_music.py
```

## 音乐素材与响度

曲库使用 48 kHz、双声道、PCM 24-bit WAV。非焦虑类别约为 `-16 LUFS`，焦虑类别约为 `-23 LUFS`，保留约 7 dB 的设计差异；真峰值限制在约 `-2 dBTP` 以下。新增或替换素材时应延续这套响度规则。

公开演示、发布仓库或再分发音频前，请确认拥有相应音乐素材的授权。当前 61 个文件中有一组内容重复，项目按既有素材编号保留两份，因此共有 60 份唯一音频内容。

## 隐私与限制

- 用户输入会发送给 DeepSeek；AI 音乐模式只把经过过滤的匿名主题和结构化情绪发送给音乐后端，生成的引导词会发送给 MiniMax。请避免输入能够识别个人身份的敏感信息。
- 七类情绪识别和固定三阶段路径用于产品演示，不属于临床评估。
- 情绪路径尚未经过本项目的疗效验证。
- 当前只有命令行界面，完整生成依赖 MiniMax TTS；AI 音乐还依赖至少一个已配置的音乐后端及相应账户额度。
- 曲目会在符合阶段情绪的候选中选择，同一输入的结果可能不同。
- 本地整曲长度、AI 音乐接口的实际返回时长和 crossfade 都可能使最终时长偏离规划时长。

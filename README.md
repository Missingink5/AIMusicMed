# AIMusicMed：AI 情绪转换冥想音频生成器

根据我们的调研，ISO原则的音乐（先匹配当前情绪，再逐步转变音乐情绪至积极的音乐）作为背景音乐的冥想在焦虑、愤怒等高唤醒负面情绪的改善显著好于一般平静的冥想音乐。

输入一段当前感受和目标时长，AIMusicMed 会识别主要情绪，规划三阶段情绪路径，从 61 首本地音乐中选择整曲，为每首音乐生成与内容匹配的引导词，最后合成为可播放的 WAV。

项目采用音乐情绪调节中的ISO原则设计思路：先用音乐承接用户当下的情绪，再逐步过渡到平静或积极状态。前期调研将这条路径视为值得验证的产品假设。

> 这是产品原型和个人放松工具，不提供心理诊断、治疗或危机干预。出现持续心理困扰或紧急风险时，请联系专业机构或当地紧急服务。

## 工作流

```text
用户表达与目标时长
  → DeepSeek 识别主要情绪
  → 固定 SOP 规划三阶段情绪路径
  → 从本地曲库选择整首音乐并分析声学特征
  → DeepSeek 按具体曲目生成逐段引导词
  → MiniMax TTS 生成语音
  → 语音混合、淡入淡出和重叠 crossfade
  → 输出 WAV
```

DeepSeek 不可用时，情绪识别会回退到关键词规则，引导词会回退到本地音乐特征模板，并在运行日志中明确标记。MiniMax 是唯一语音后端；请求失败时程序会直接报错，不会静默切换到低质量语音。

## Demo 亮点

- 情绪识别覆盖焦虑、忧郁、敌意、平静、喜悦、自豪、友爱 7 类情绪。
- 情绪路径由可解释的固定规则生成，典型路径为“当前情绪 → 平静 → 积极情绪”。
- 引导词在选定音乐后生成，并绑定曲目、阶段目标、声学特征和校验指纹，避免文案与音乐错配。
- 音乐整首播放，不裁剪、不循环。相邻曲目默认使用 3 秒重叠 crossfade。
- 每首音乐开头默认保留 4 秒纯音乐，再进入语音引导。
- MiniMax `speech-2.8-hd` 支持官方系统音色，也支持在获得授权后配置克隆音色。

## 实际运行链路

```text
run_py313_app.py
  → load_config
  → MeditationApp.create_meditation_session
    → prepare_session_plan
    → generate_music
    → generate_guidance_for_music
    → generate_speech_adaptive
    → combine_audio_adaptive
    → meditation_session_<time_ns>.wav
```

程序会根据目标时长按“每首约一分钟”估算曲目数量。由于实际曲长约为 56 至 78 秒，并且相邻曲目存在重叠，最终音频时长通常不会与输入分钟数完全相同。

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
```

`MINIMAX_API_KEY` 是完整生成所必需的。`DEEPSEEK_API_KEY` 可选；未配置或请求失败时，程序会使用本地回退逻辑。

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
- `speech_start_delay_seconds`：每首音乐开始后等待多久进入语音，默认 4 秒。
- `music_volume_reduction`：混音时音乐相对语音的衰减量，默认 8 dB。

本机 Demo 的成品目录可配置为：

```text
D:\ISO音乐-AI冥想疗愈生成\示例输出
```

## 运行

```powershell
.\.venv\Scripts\Activate.ps1
python run_py313_app.py
```

程序会依次要求选择或输入当前感受、设置时长并确认生成。完整运行会调用 DeepSeek 和 MiniMax，依赖网络、账户额度和有效音色。

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
python local_music_library.py
```

当前基线为 26 项单元测试通过，曲库扫描结果为 7 个分类、61 个 WAV 文件。

## 音乐素材与响度

曲库使用 48 kHz、双声道、PCM 24-bit WAV。非焦虑类别约为 `-16 LUFS`，焦虑类别约为 `-23 LUFS`，保留约 7 dB 的设计差异；真峰值限制在约 `-2 dBTP` 以下。新增或替换素材时应延续这套响度规则。

公开演示、发布仓库或再分发音频前，请确认拥有相应音乐素材的授权。当前 61 个文件中有一组内容重复，项目按既有素材编号保留两份，因此共有 60 份唯一音频内容。

## 隐私与限制

- 用户输入会发送给 DeepSeek；生成的引导词会发送给 MiniMax。请避免输入能够识别个人身份的敏感信息。
- 七类情绪识别和固定三阶段路径用于产品演示，不属于临床评估。
- 情绪路径尚未经过本项目的疗效验证。
- 当前只有命令行界面，完整生成依赖 MiniMax 网络与账户额度。
- 曲目会在符合阶段情绪的候选中选择，同一输入的结果可能不同。
- 整曲策略会让最终时长与规划时长存在偏差。

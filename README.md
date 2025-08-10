# 极简冥想音频生成器

仅保留最小可运行集合：

| 文件 | 作用 |
|------|------|
| py313_meditation_app.py | 核心逻辑：生成 prompts / 语音 / 音乐 / 合成音频 |
| run_py313_app.py | 交互式入口，负责 D 盘缓存保护与用户问答 |
| audio_compat.py | 自研音频处理层，替代 pydub，支持加载/静音/叠加/导出 |
| config_manager.py | 配置结构体 & 加载/保存逻辑，创建目录 |
| config.json | 配置文件（API Key、路径、音频与冥想参数） |
| voice_profiles.py | 文本情绪 → 语音 TTS 参数映射 |
| requirements.txt | 依赖清单 |

## 1. 环境准备 (Windows PowerShell)
```powershell
# 进入项目根目录
cd D:\PYTHON\PythonProject

# 创建虚拟环境 (可选)
python -m venv .venv

# 激活
. .venv\Scripts\Activate.ps1

# 国内网络建议先设置 pip 源 (可选)
# pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 安装依赖
pip install -r requirements.txt
```

## 2. 配置
编辑 `config.json`：
```json
{
  "api_keys": {
    "deepseek_api_key": "替换为你的API KEY",
    "deepseek_base_url": "https://api.deepseek.com/v1"
  },
  "paths": {
    "base_dir": "D:/MyMeditationApp"
  },
  "audio_settings": {
    "music_model": "facebook/musicgen-small",
    "tts_voice": "zh-CN-XiaoxiaoNeural",
    "speech_rate": "-20%",
    "speech_pitch": "-5Hz",
    "music_volume_reduction": 8,
    "enable_ai_music": true
  },
  "meditation_settings": {
    "default_duration_minutes": 5,
    "segment_duration_seconds": 20,
    "max_duration_minutes": 15,
    "min_duration_minutes": 1
  }
}
```
也可以不写 `deepseek_api_key`，改为设置环境变量：
```powershell
$Env:DEEPSEEK_API_KEY = "你的Key"
```

Linux / macOS:
```bash
export DEEPSEEK_API_KEY="你的Key"
export MEDITATION_BASE_DIR=~/meditation_app   # 可选，默认也会回退到这里
```

若 `config.json` 中 `paths` 留空，程序会自动：
- Windows: 使用 `D:/MyMeditationApp`
- 其他系统: 使用 `~/meditation_app`

## 3. 运行
交互式：
```powershell
python run_py313_app.py
```
或直接（示例脚本主函数）：
```powershell
python py313_meditation_app.py
```

## 4. 输出
生成的合成音频 (wav) 存放于 `config.json` 中 `paths.base_dir`，临时碎片存放在其 `temp/` 子目录，会在流程结束被清理。

## 5. 常见问题
| 问题 | 处理 |
|------|------|
| torch / transformers 首次下载慢 | 首次会下载模型到 D:\MyMeditationApp\cache；耐心等待或配置镜像 |
| 内存/显存不足 | 降低时长、增大 `music_volume_reduction` 不影响内存；必要时禁用 `enable_ai_music` |
| 语音失败 | 检查网络，edge-tts 需要外网；失败片段会用静音替代 |
| DeepSeek 超时 | 调整网络或缩短输入；内部超时时间设为 60 秒 |

## 6. 二次精简说明
当前仓库已是最小集合；原裁剪脚本 `repo_prune.py` 已移除，无需额外操作。

## 7. 最小调用示例 (以代码方式集成)
```python
import asyncio
from py313_meditation_app import MeditationApp

async def demo():
    app = MeditationApp()
    path, info = await app.create_meditation_session("我最近压力有点大", duration_minutes=3)
    print("生成:", path)

asyncio.run(demo())
```

## 8. 授权
本仓库当前只保留运行代码，无额外协议文件，默认视为个人项目；如需开源请自行补充 LICENSE。

---
如需：
1) 删除 `repo_prune.py`；
2) 添加 LICENSE；
3) 加入一个简单的单元测试；
回复对应数字即可。

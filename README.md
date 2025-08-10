# AI 情绪转换冥想生成器

🎭 **核心特性：情绪转换冥想系统** - 根据用户情绪状态，自动规划"消极→中性→积极"的情绪转换路径，生成同步的音乐和冥想引导语。

## 🌟 情绪转换功能

### 智能情绪分析
- 分析用户倾诉内容，识别7种主要情绪：焦虑、忧郁、敌意、平静、喜悦、自豪、友爱
- 根据情绪状态自动规划三阶段转换路径

### 情绪转换路径
- **消极情绪**: 焦虑→平静→喜悦 | 忧郁→平静→友爱 | 敌意→平静→友爱
- **中性情绪**: 平静→友爱→喜悦  
- **积极情绪**: 维持并深化当前积极状态

### 同步音乐选择
- 优先使用本地音乐库（61首音乐，7个情绪分类）
- 音乐情绪与冥想引导语完全同步
- 每个转换阶段2个音频段落，共6段

### 动态时长分配
- 根据情绪状态智能分配各阶段时长
- 消极情绪：40%缓解 + 35%平静 + 25%积极
- 确保充分的情绪转换时间

## 📁 核心文件结构

| 文件 | 作用 |
|------|------|
| py313_meditation_app.py | 核心逻辑：情绪分析、转换规划、音乐选择、语音生成 |
| run_py313_app.py | 情绪转换式用户交互入口，D盘缓存保护 |
| local_music_library.py | 本地音乐库管理，支持情绪分类和英文映射 |
| audio_compat.py | 自研音频处理层，替代pydub，支持Python 3.13 |
| config_manager.py | 配置管理，创建目录结构 |
| voice_profiles.py | 情绪→语音参数智能映射 |
| test_emotion_transition.py | 情绪转换系统测试脚本 |
| EMOTION_TRANSITION_GUIDE.md | 详细使用指南 |

## 🎵 音乐库结构
```
music_library/
├── Anxiety/     # 焦虑情绪音乐 (8首)
├── Happy/       # 喜悦情绪音乐 (8首) 
├── Hostility/   # 敌意情绪音乐 (9首)
├── Love/        # 友爱情绪音乐 (8首)
├── Pride/       # 自豪情绪音乐 (9首)
├── Quiet/       # 平静情绪音乐 (10首)
└── Sad/         # 忧郁情绪音乐 (9首)
```

## 🚀 快速开始

### 1. 测试情绪转换系统
```bash
python test_emotion_transition.py
```

### 2. 开始使用
```bash
python run_py313_app.py
```

### 3. 体验情绪转换
1. 详细描述您的当前情绪状态
2. 系统自动分析并规划转换路径
3. 生成6段同步的音乐+引导语
4. 享受从消极到积极的情绪转换旅程

## 📋 详细安装步骤

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

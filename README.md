# AI 冥想助手

这是一个基于 AI 的个性化冥想应用，能够根据用户的倾诉内容生成定制化的冥想指导语和背景音乐。

## 功能特性

- 🤖 **智能理解**: 使用 DeepSeek AI 理解用户的情绪和需求
- 🎵 **音乐生成**: 使用 MusicGen 生成适合的背景音乐
- 🗣️ **语音合成**: 使用 Edge-TTS 生成温柔的中文冥想指导语
- 🎧 **音频合成**: 自动将语音和音乐合成为完整的冥想会话

## 文件说明

- `complete_meditation_app.py`: 完整的冥想应用主程序
- `run_meditation_app.py`: 简化的使用脚本
- `config.json`: 配置文件
- `UserInput.py`: 原始的用户输入处理脚本
- `MusicAI.py`: 原始的音乐生成脚本
- `script.py`: 原始的指导语生成脚本
- `AllTogether.py`: 原始的整合脚本

## 安装依赖

```bash
pip install openai transformers torch scipy pydub edge-tts asyncio requests
```

## 快速开始

### 方法1: 使用简化脚本（推荐）

```bash
python run_meditation_app.py
```

按照提示选择您的情况或输入自定义内容，程序会自动生成个性化冥想音频。

### 方法2: 直接使用主程序

```python
import asyncio
from complete_meditation_app import MeditationApp

async def main():
    app = MeditationApp("your-deepseek-api-key")
    output_file = await app.create_meditation_session(
        user_input="我最近压力很大，需要放松一下",
        duration_minutes=3
    )
    print(f"冥想音频已生成: {output_file}")

asyncio.run(main())
```

## 使用流程

1. **用户倾诉**: 描述当前的心情、困扰或需求
2. **AI 分析**: DeepSeek AI 分析用户情绪，生成个性化的指导语和音乐提示
3. **内容生成**: 
   - Edge-TTS 生成温柔的中文冥想指导语
   - MusicGen 生成相应的背景音乐
4. **音频合成**: 将语音和音乐合成为完整的冥想会话
5. **输出文件**: 生成 MP3 格式的冥想音频文件

## 配置说明

编辑 `config.json` 文件来自定义设置：

- `api_keys`: API 密钥配置
- `paths`: 文件路径配置
- `audio_settings`: 音频生成设置
- `meditation_settings`: 冥想会话设置

## 技术架构

```
用户倾诉 → DeepSeek AI → 生成 Prompts → 并行处理
                                      ├── Edge-TTS (语音)
                                      └── MusicGen (音乐)
                                              ↓
                                        Pydub 音频合成
                                              ↓
                                      最终冥想音频文件
```

## 注意事项

1. **GPU 推荐**: MusicGen 模型建议使用 GPU 加速
2. **网络连接**: 需要稳定的网络连接访问 DeepSeek API
3. **存储空间**: 确保有足够的磁盘空间存储模型和生成的音频文件
4. **首次运行**: 第一次运行时会下载模型文件，可能需要较长时间

## 常见问题

### Q: 程序运行很慢怎么办？
A: 首次运行需要下载模型，后续运行会快很多。建议使用 GPU 加速。

### Q: 生成的音频质量不满意？
A: 可以在 `config.json` 中调整音频设置，如音量平衡、语音速度等。

### Q: API 调用失败？
A: 请检查网络连接和 DeepSeek API 密钥是否正确设置。

## 许可证

此项目仅供学习和个人使用。

## 致谢

- DeepSeek AI: 智能文本生成
- Meta MusicGen: 音乐生成模型
- Microsoft Edge-TTS: 语音合成服务

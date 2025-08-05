import os
import json
import re
import asyncio
import requests
from openai import OpenAI
from pydub import AudioSegment
import edge_tts

# === 1. 基础配置 ===

DEEPSEEK_API_KEY = "sk-9ec64e20ae244fc8aa7fac849d49e5e2"  # 你的 DeepSeek Key
MUSICGEN_API_URL = "http://localhost:5000/generate"  # 假设你本地部署了 MusicGen 接口
user_input = "我最近总是失眠，而且觉得压力很大，什么都做不好。"

BASE_DIR = "D:/MyMeditationApp"
os.makedirs(BASE_DIR, exist_ok=True)

PROMPT_JSON_PATH = os.path.join(BASE_DIR, "session_prompt.json")
FINAL_AUDIO_PATH = os.path.join(BASE_DIR, "final_meditation.mp3")

# === 2. 初始化 DeepSeek 客户端 ===

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

# === 3. 构造 Prompt 并请求 DeepSeek ===

prompt = f"""
你是一位温柔、专业的冥想教练，现在有用户向你倾诉了内心的烦恼。
请你根据用户的倾诉内容，返回一个结构化 JSON，完成以下任务：

1. 用一两句话进行真诚、温柔的安慰；
2. 将整个冥想体验分为多个时间段（例如 00:00, 00:20, 00:40...），每段大约持续 20 秒；
3. 针对每个时间段：
   - 生成一个适合该时刻的冥想引导 prompt（面向冥想指导语的语言模型）；
   - 生成一个用于 AI 背景音乐生成的音乐 prompt（英文，描述音乐风格与情绪）；

请将以上内容用如下 JSON 结构输出：

```json
{{
  "comfort": "一句安慰语...",
  "script_prompts": [
    {{ "time": "00:00", "prompt": "引导用户..." }},
    ...
  ],
  "music_prompts": [
    {{ "time": "00:00", "prompt": "ambient music..." }},
    ...
  ]
}}
用户的倾诉如下：
【{user_input}】
"""

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.7
)

content = response.choices[0].message.content.strip()

# === 4. 提取 JSON 内容 ===

match = re.search(r"{.*}", content, re.DOTALL)
json_text = match.group(0)
result = json.loads(json_text)

with open(PROMPT_JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("✅ 冥想结构 JSON 已保存：", PROMPT_JSON_PATH)

# === 5. TTS 生成语音 (edge-tts) ===

async def generate_tts(text, path):
    communicate = edge_tts.Communicate(text=text, voice="zh-CN-XiaoxiaoNeural")
    await communicate.save(path)

print("🔊 开始生成语音...")

for i, segment in enumerate(result["script_prompts"]):
    path = os.path.join(BASE_DIR, f"voice_{i:02d}.mp3")
    asyncio.run(generate_tts(segment["prompt"], path))

print("✅ 所有语音片段生成完成。")

# === 6. 生成音乐（调用 MusicGen）===

def generate_music(prompt, path):
    response = requests.post(MUSICGEN_API_URL, json={"prompt": prompt, "duration": 20})
    if response.status_code == 200:
        with open(path, "wb") as f:
            f.write(response.content)
    else:
        raise Exception(f"音乐生成失败：{response.status_code} - {response.text}")

print("🎵 开始生成音乐...")

for i, segment in enumerate(result["music_prompts"]):
    path = os.path.join(BASE_DIR, f"music_{i:02d}.wav")
    generate_music(segment["prompt"], path)

print("✅ 所有音乐片段生成完成。")

# === 7. 合成音频（pydub）===

final_audio = AudioSegment.empty()

for i in range(len(result["script_prompts"])):
    voice_path = os.path.join(BASE_DIR, f"voice_{i:02d}.mp3")
    music_path = os.path.join(BASE_DIR, f"music_{i:02d}.wav")

    voice = AudioSegment.from_file(voice_path)
    music = AudioSegment.from_file(music_path)

    # 将语音叠加在背景音乐上
    combined = music.overlay(voice, position=0)
    final_audio += combined

final_audio.export(FINAL_AUDIO_PATH, format="mp3")
print("🎧 冥想音频已合成完成：", FINAL_AUDIO_PATH)

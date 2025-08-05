from openai import OpenAI
import json
import re
import os

# === 基础配置 ===

# 你的 DeepSeek API Key
DEEPSEEK_API_KEY = "sk-9ec64e20ae244fc8aa7fac849d49e5e2"

# 用户倾诉内容
user_input = "我最近总是失眠，而且觉得压力很大，什么都做不好。"

# 输出文件夹和文件名
BASE_DIR = "D:/MyMeditationApp"
os.makedirs(BASE_DIR, exist_ok=True)
OUTPUT_PATH = os.path.join(BASE_DIR, "session_prompt.json")

# === 初始化 DeepSeek 客户端 ===

client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

# === 构造 Prompt ===

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
【{{user_input}}】
"""

# === 调用 DeepSeek Chat ===
response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.7
)

# === 提取并解析 JSON ===
content = response.choices[0].message.content.strip()

try:
    # 用正则找到第一对大括号内的 JSON 块
    match = re.search(r"{.*}", content, re.DOTALL)
    json_text = match.group(0)
    result = json.loads(json_text)
except Exception as e:
    print("❌ 无法解析 JSON。请检查 LLM 返回内容：\n", content)
    raise

# === 保存到文件 ===
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# === 打印示例输出 ===
print("✅ 已生成分段 prompt 脚本，保存路径：", OUTPUT_PATH)
print("\n🤗 安慰语：", result.get("comfort", "未找到"))
print("\n📜 冥想提示（示例前两段）：")
for item in result.get("script_prompts", [])[:2]:
    print(f"{item['time']} → {item['prompt']}")

print("\n🎵 音乐提示（示例前两段）：")
for item in result.get("music_prompts", [])[:2]:
    print(f"{item['time']} → {item['prompt']}")
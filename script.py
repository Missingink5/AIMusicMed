from openai import OpenAI
import json
import re
import os

# 创建输出目录
BASE_DIR = "D:/MyMeditationApp"
os.makedirs(BASE_DIR, exist_ok=True)
OUTPUT_PATH = os.path.join(BASE_DIR, "meditation_script.json")

# 创建 DeepSeek 客户端
client = OpenAI(
    api_key="sk-9ec64e20ae244fc8aa7fac849d49e5e2",
    base_url="https://api.deepseek.com/v1"
)

# 设置 prompt
response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": (
            "你是一位专业的冥想教练，请输出结构化 JSON 脚本。"
            "使用 JSON 数组格式，每一项包含 time 和 text 两个字段。")},
        {"role": "user", "content": (
            "请生成一段持续 2 分钟的冥想引导语，要求如下：\n"
            "每 15 秒生成一条语句，time 为格式化时间戳（例如 00:00、00:15、00:30...）；\n"
            "内容用于帮助用户缓解焦虑，进行呼吸放松、身体扫描。\n"
            "请严格按照格式输出。")}
    ],
    temperature=0.5
)

# 提取文本结果
content = response.choices[0].message.content

# 找到 JSON 的部分（从 [ 开始，到 ] 结束）
try:
    match = re.search(r"\[\s*{.*}\s*]", content, re.DOTALL)
    json_text = match.group(0)
    data = json.loads(json_text)
except Exception as e:
    print("❌ 无法正确提取 JSON 内容，请检查模型返回格式。")
    print("原始内容：\n", content)
    raise e

# 保存为 JSON 文件
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"✅ 已成功生成冥想 JSON 脚本，保存路径：{OUTPUT_PATH}")

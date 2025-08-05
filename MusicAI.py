from transformers import MusicgenForConditionalGeneration, AutoProcessor
import scipy
import torch
import os

# 配置缓存和输出目录
BASE_DIR = "D:/MyMusicGenApp"
CACHE_DIR = os.path.join(BASE_DIR, "cache")
OUTPUT_PATH = os.path.join(BASE_DIR, "generated_music.wav")

# 创建文件夹（如果不存在）
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(BASE_DIR, exist_ok=True)

# 设置 huggingface 缓存路径
os.environ["HF_HOME"] = CACHE_DIR

# 加载处理器和模型（带 cache_dir 参数）
processor = AutoProcessor.from_pretrained("facebook/musicgen-medium", cache_dir=CACHE_DIR)
model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-medium", cache_dir=CACHE_DIR)

# 放到 GPU（如果可用）
device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)

# 文本提示
prompt = ["生成一段平静的冥想音乐"]
inputs = processor(text=prompt, return_tensors="pt").to(device)

# 生成音乐
audio_values = model.generate(**inputs, max_new_tokens=1024)

# 保存为 WAV 文件
scipy.io.wavfile.write(
    OUTPUT_PATH,
    rate=model.config.audio_encoder.sampling_rate,
    data=audio_values[0, 0].cpu().numpy()
)

print(f"🎵 音乐已生成并保存到: {OUTPUT_PATH}")

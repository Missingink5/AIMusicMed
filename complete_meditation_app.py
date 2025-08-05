import os
import json
import re
import asyncio
from typing import List, Dict
from openai import OpenAI
from transformers import MusicgenForConditionalGeneration, AutoProcessor
import scipy
import torch
from pydub import AudioSegment
import edge_tts
import time

class MeditationApp:
    def __init__(self, deepseek_api_key: str):
        """
        初始化冥想应用
        """
        self.deepseek_api_key = deepseek_api_key
        self.client = OpenAI(
            api_key=deepseek_api_key,
            base_url="https://api.deepseek.com/v1"
        )
        
        # 设置目录
        self.base_dir = "D:/MyMeditationApp"
        self.cache_dir = os.path.join(self.base_dir, "cache")
        self.temp_dir = os.path.join(self.base_dir, "temp")
        
        # 创建必要目录
        for dir_path in [self.base_dir, self.cache_dir, self.temp_dir]:
            os.makedirs(dir_path, exist_ok=True)
        
        # 设置 Hugging Face 缓存
        os.environ["HF_HOME"] = self.cache_dir
        
        # 初始化音乐生成模型
        self.music_processor = None
        self.music_model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        print(f"🔧 MeditationApp 初始化完成，使用设备: {self.device}")

    def initialize_music_model(self):
        """
        初始化音乐生成模型（延迟加载）
        """
        if self.music_processor is None:
            print("🎵 正在加载音乐生成模型...")
            self.music_processor = AutoProcessor.from_pretrained(
                "facebook/musicgen-medium", 
                cache_dir=self.cache_dir
            )
            self.music_model = MusicgenForConditionalGeneration.from_pretrained(
                "facebook/musicgen-medium", 
                cache_dir=self.cache_dir
            )
            self.music_model.to(self.device)
            print("✅ 音乐生成模型加载完成")

    def generate_prompts(self, user_input: str, duration_minutes: int = 3) -> Dict:
        """
        根据用户倾诉生成结构化的 prompts
        """
        print("🤖 正在生成 prompts...")
        
        # 计算时间段数量（每20秒一段）
        segments = (duration_minutes * 60) // 20
        
        prompt = f"""
你是一位温柔、专业的冥想教练，现在有用户向你倾诉了内心的烦恼。
请你根据用户的倾诉内容，返回一个结构化 JSON，完成以下任务：

1. 用一两句话进行真诚、温柔的安慰；
2. 将整个冥想体验分为 {segments} 个时间段，每段持续 20 秒；
3. 针对每个时间段：
   - 生成一个适合该时刻的冥想引导语（30-50字，温柔指导）；
   - 生成一个用于 AI 背景音乐生成的音乐 prompt（英文，描述音乐风格与情绪）；

请将以上内容用如下 JSON 结构输出：

{{
  "comfort": "一句安慰语...",
  "script_prompts": [
    {{ "time": "00:00", "text": "现在，请找到一个舒适的位置坐下..." }},
    {{ "time": "00:20", "text": "轻轻闭上眼睛，开始关注你的呼吸..." }},
    ...
  ],
  "music_prompts": [
    {{ "time": "00:00", "prompt": "soft ambient meditation music with gentle nature sounds" }},
    {{ "time": "00:20", "prompt": "calming instrumental music with slow piano melodies" }},
    ...
  ]
}}

用户的倾诉如下：
【{user_input}】
"""

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            
            content = response.choices[0].message.content.strip()
            
            # 提取 JSON
            match = re.search(r"{.*}", content, re.DOTALL)
            if not match:
                raise ValueError("无法找到 JSON 格式的响应")
                
            json_text = match.group(0)
            result = json.loads(json_text)
            
            # 保存结果
            output_path = os.path.join(self.base_dir, "session_prompts.json")
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            print(f"✅ Prompts 生成完成，共 {len(result.get('script_prompts', []))} 个片段")
            return result
            
        except Exception as e:
            print(f"❌ 生成 prompts 失败: {e}")
            raise

    async def generate_speech(self, script_prompts: List[Dict]) -> List[str]:
        """
        使用 edge-tts 生成语音文件
        """
        print("🔊 正在生成语音文件...")
        speech_files = []
        
        # 选择中文女声
        voice = "zh-CN-XiaoxiaoNeural"  # 可选: zh-CN-XiaoyiNeural, zh-CN-YunjianNeural
        
        for i, segment in enumerate(script_prompts):
            file_path = os.path.join(self.temp_dir, f"speech_{i:02d}.mp3")
            
            try:
                communicate = edge_tts.Communicate(
                    text=segment["text"], 
                    voice=voice,
                    rate="-20%",  # 稍微慢一点
                    pitch="-5Hz"  # 稍微低一点
                )
                await communicate.save(file_path)
                speech_files.append(file_path)
                print(f"  ✓ 片段 {i+1} 语音生成完成")
                
            except Exception as e:
                print(f"  ❌ 片段 {i+1} 语音生成失败: {e}")
                # 创建静音文件作为备选
                silence = AudioSegment.silent(duration=3000)  # 3秒静音
                silence.export(file_path, format="mp3")
                speech_files.append(file_path)
        
        print(f"✅ 所有语音文件生成完成，共 {len(speech_files)} 个")
        return speech_files

    def generate_music(self, music_prompts: List[Dict]) -> List[str]:
        """
        使用 MusicGen 生成背景音乐
        """
        print("🎵 正在生成背景音乐...")
        self.initialize_music_model()
        
        music_files = []
        
        for i, segment in enumerate(music_prompts):
            file_path = os.path.join(self.temp_dir, f"music_{i:02d}.wav")
            
            try:
                # 处理输入
                inputs = self.music_processor(
                    text=[segment["prompt"]], 
                    return_tensors="pt"
                ).to(self.device)
                
                # 生成音乐（大约20秒）
                with torch.no_grad():
                    audio_values = self.music_model.generate(
                        **inputs, 
                        max_new_tokens=512,  # 约20秒
                        do_sample=True,
                        guidance_scale=3.0
                    )
                
                # 保存音频
                sample_rate = self.music_model.config.audio_encoder.sampling_rate
                scipy.io.wavfile.write(
                    file_path,
                    rate=sample_rate,
                    data=audio_values[0, 0].cpu().numpy()
                )
                
                music_files.append(file_path)
                print(f"  ✓ 片段 {i+1} 音乐生成完成")
                
            except Exception as e:
                print(f"  ❌ 片段 {i+1} 音乐生成失败: {e}")
                # 创建静音文件作为备选
                silence = AudioSegment.silent(duration=20000)  # 20秒静音
                silence.export(file_path, format="wav")
                music_files.append(file_path)
        
        print(f"✅ 所有音乐文件生成完成，共 {len(music_files)} 个")
        return music_files

    def combine_audio(self, speech_files: List[str], music_files: List[str]) -> str:
        """
        合并语音和音乐文件
        """
        print("🎧 正在合成最终音频...")
        
        final_audio = AudioSegment.empty()
        
        for i, (speech_file, music_file) in enumerate(zip(speech_files, music_files)):
            try:
                # 加载音频文件
                speech = AudioSegment.from_file(speech_file)
                music = AudioSegment.from_file(music_file)
                
                # 调整音量：语音为主，音乐为背景
                music = music - 15  # 音乐音量降低15dB
                
                # 确保音乐长度至少和语音一样长
                if len(music) < len(speech):
                    music = music + AudioSegment.silent(duration=len(speech) - len(music))
                else:
                    music = music[:len(speech)]
                
                # 合并音频
                combined = music.overlay(speech, position=0)
                
                # 添加到最终音频
                final_audio += combined
                
                print(f"  ✓ 片段 {i+1} 合成完成")
                
            except Exception as e:
                print(f"  ❌ 片段 {i+1} 合成失败: {e}")
                # 添加静音段
                final_audio += AudioSegment.silent(duration=20000)
        
        # 导出最终音频
        output_path = os.path.join(self.base_dir, f"meditation_session_{int(time.time())}.mp3")
        final_audio.export(output_path, format="mp3", bitrate="128k")
        
        print(f"✅ 最终音频合成完成: {output_path}")
        return output_path

    def cleanup_temp_files(self):
        """
        清理临时文件
        """
        print("🧹 正在清理临时文件...")
        try:
            for file in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
            print("✅ 临时文件清理完成")
        except Exception as e:
            print(f"⚠️ 清理临时文件时出错: {e}")

    async def create_meditation_session(self, user_input: str, duration_minutes: int = 3, cleanup: bool = True) -> str:
        """
        创建完整的冥想会话
        """
        print(f"🧘‍♀️ 开始创建 {duration_minutes} 分钟的冥想会话...")
        print(f"用户倾诉: {user_input}")
        
        try:
            # 1. 生成 prompts
            prompts_data = self.generate_prompts(user_input, duration_minutes)
            
            # 显示安慰语
            comfort = prompts_data.get("comfort", "")
            if comfort:
                print(f"\n🤗 安慰语: {comfort}\n")
            
            # 2. 生成语音
            speech_files = await self.generate_speech(prompts_data["script_prompts"])
            
            # 3. 生成音乐
            music_files = self.generate_music(prompts_data["music_prompts"])
            
            # 4. 合成音频
            final_audio_path = self.combine_audio(speech_files, music_files)
            
            # 5. 清理临时文件
            if cleanup:
                self.cleanup_temp_files()
            
            print(f"\n🎉 冥想会话创建完成!")
            print(f"📁 输出文件: {final_audio_path}")
            return final_audio_path
            
        except Exception as e:
            print(f"❌ 创建冥想会话失败: {e}")
            raise

# === 使用示例 ===

async def main():
    # 配置
    DEEPSEEK_API_KEY = "sk-9ec64e20ae244fc8aa7fac849d49e5e2"
    user_input = "我最近总是失眠，而且觉得压力很大，什么都做不好。"
    
    # 创建应用实例
    app = MeditationApp(DEEPSEEK_API_KEY)
    
    # 创建冥想会话
    try:
        output_file = await app.create_meditation_session(
            user_input=user_input,
            duration_minutes=3,  # 3分钟会话
            cleanup=True
        )
        print(f"\n✨ 您的个性化冥想音频已准备好: {output_file}")
        
    except Exception as e:
        print(f"程序执行失败: {e}")

if __name__ == "__main__":
    asyncio.run(main())

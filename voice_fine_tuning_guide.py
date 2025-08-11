#!/usr/bin/env python3
"""
语音微调指南和工具
提供多种语音优化和微调方案
"""

import json
import os
from typing import Dict, List, Tuple
import asyncio

# 当前项目的语音优化配置
CURRENT_TTS_CONFIG = {
    "service": "Edge-TTS",
    "type": "cloud_neural_tts",
    "model": "zh-CN-XiaoxiaoNeural", 
    "parameters": {
        "rate": "-40%",
        "pitch": "-8Hz",
        "volume": "0.8"
    },
    "limitations": {
        "no_model_training": True,
        "parameter_tuning_only": True,
        "voice_selection_limited": True
    }
}

# 可用的微调方案
FINE_TUNING_OPTIONS = {
    "1_parameter_optimization": {
        "name": "参数优化 (当前可用)",
        "difficulty": "简单",
        "cost": "免费",
        "description": "调整语速、音调、音量、停顿等参数",
        "limitations": "受限于预训练模型的能力",
        "best_for": "快速改善语音效果"
    },
    
    "2_voice_switching": {
        "name": "语音角色切换",
        "difficulty": "简单", 
        "cost": "免费",
        "description": "在可用的Neural voices间切换",
        "limitations": "只能选择预定义的角色",
        "best_for": "找到最适合的语音风格"
    },
    
    "3_ssml_enhancement": {
        "name": "SSML标记增强",
        "difficulty": "中等",
        "cost": "免费",
        "description": "使用SSML标记精细控制语音", 
        "limitations": "不同TTS服务支持的标记不同",
        "best_for": "精确控制语音细节"
    },
    
    "4_local_tts_models": {
        "name": "本地TTS模型",
        "difficulty": "困难",
        "cost": "中等", 
        "description": "使用可训练的开源TTS模型",
        "limitations": "需要大量计算资源和训练数据",
        "best_for": "完全自定义的语音效果"
    },
    
    "5_voice_cloning": {
        "name": "语音克隆",
        "difficulty": "困难",
        "cost": "高",
        "description": "训练专属的语音模型",
        "limitations": "需要大量音频数据和专业知识",
        "best_for": "创造独特的专属语音"
    }
}


class VoiceFineTuner:
    """语音微调工具类"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.load_config()
    
    def load_config(self):
        """加载当前配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            print(f"配置文件 {self.config_path} 不存在")
            self.config = {}
    
    def save_config(self):
        """保存配置"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
    
    def analyze_current_setup(self) -> Dict:
        """分析当前语音设置"""
        audio_settings = self.config.get('audio_settings', {})
        
        analysis = {
            "current_voice": audio_settings.get('tts_voice', 'unknown'),
            "current_rate": audio_settings.get('speech_rate', 'unknown'),
            "current_pitch": audio_settings.get('speech_pitch', 'unknown'), 
            "current_volume": audio_settings.get('speech_volume', 'unknown'),
            "service_type": "Edge-TTS (Microsoft Neural)",
            "tuning_level": "参数级调优",
            "recommendations": []
        }
        
        # 生成优化建议
        if audio_settings.get('speech_rate', '').startswith('-'):
            rate_value = abs(int(audio_settings.get('speech_rate', '-40%').replace('%', '')))
            if rate_value > 50:
                analysis["recommendations"].append("语速过慢，建议调整到-30%至-40%之间")
            elif rate_value < 20:
                analysis["recommendations"].append("语速可能过快，冥想建议使用-30%至-50%")
        
        if audio_settings.get('speech_pitch', '').startswith('-'):
            pitch_value = abs(int(audio_settings.get('speech_pitch', '-8Hz').replace('Hz', '')))
            if pitch_value > 15:
                analysis["recommendations"].append("音调降低过多，可能影响清晰度")
            elif pitch_value < 5:
                analysis["recommendations"].append("可适当降低音调增加温和感")
        
        return analysis
    
    def generate_parameter_variations(self) -> List[Dict]:
        """生成不同的参数变体供测试"""
        variations = [
            {
                "name": "舒缓慢速版",
                "speech_rate": "-60%",
                "speech_pitch": "-12Hz", 
                "description": "极慢语速，适合深度放松"
            },
            {
                "name": "标准冥想版",
                "speech_rate": "-40%",
                "speech_pitch": "-8Hz",
                "description": "平衡的冥想语音设置"
            },
            {
                "name": "清晰引导版", 
                "speech_rate": "-25%",
                "speech_pitch": "-5Hz",
                "description": "稍快语速，适合引导式冥想"
            },
            {
                "name": "温和治愈版",
                "speech_rate": "-45%", 
                "speech_pitch": "-10Hz",
                "description": "温和低沉，适合情感疗愈"
            },
            {
                "name": "自然对话版",
                "speech_rate": "-15%",
                "speech_pitch": "-3Hz", 
                "description": "接近自然对话的语音"
            }
        ]
        return variations
    
    def apply_parameter_set(self, variation: Dict) -> bool:
        """应用指定的参数配置"""
        try:
            if 'audio_settings' not in self.config:
                self.config['audio_settings'] = {}
            
            self.config['audio_settings']['speech_rate'] = variation['speech_rate']
            self.config['audio_settings']['speech_pitch'] = variation['speech_pitch']
            
            self.save_config()
            print(f"✅ 已应用 {variation['name']} 配置")
            print(f"   语速: {variation['speech_rate']}")
            print(f"   音调: {variation['speech_pitch']}")
            print(f"   说明: {variation['description']}")
            return True
        except Exception as e:
            print(f"❌ 配置应用失败: {e}")
            return False
    
    def get_voice_options(self) -> List[Dict]:
        """获取可用的语音选项"""
        # 从voice_profiles.py导入
        try:
            from voice_profiles import VOICE_PROFILES
            return [
                {
                    "voice_id": voice_id,
                    "name": profile["name"],
                    "style": profile["style"], 
                    "description": profile["description"],
                    "default_rate": profile["default_rate"],
                    "default_pitch": profile["default_pitch"]
                }
                for voice_id, profile in VOICE_PROFILES.items()
            ]
        except ImportError:
            return []
    
    def interactive_tuning(self):
        """交互式语音调优"""
        print("🎙️ 语音微调工具")
        print("=" * 50)
        
        # 显示当前分析
        analysis = self.analyze_current_setup()
        print(f"\n📊 当前配置分析:")
        print(f"  语音: {analysis['current_voice']}")
        print(f"  语速: {analysis['current_rate']}")
        print(f"  音调: {analysis['current_pitch']}")
        print(f"  服务: {analysis['service_type']}")
        
        if analysis['recommendations']:
            print(f"\n💡 优化建议:")
            for rec in analysis['recommendations']:
                print(f"  • {rec}")
        
        # 显示可用选项
        print(f"\n🎛️ 可用微调方案:")
        for i, (key, option) in enumerate(FINE_TUNING_OPTIONS.items(), 1):
            print(f"  {i}. {option['name']} ({option['difficulty']})")
            print(f"     {option['description']}")
        
        # 参数变体测试
        print(f"\n🧪 参数配置测试:")
        variations = self.generate_parameter_variations()
        for i, var in enumerate(variations, 1):
            print(f"  {i}. {var['name']}: {var['description']}")
        
        # 用户选择
        try:
            choice = input(f"\n请选择要应用的配置 (1-{len(variations)}，0=退出): ").strip()
            if choice == '0':
                return
            
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(variations):
                selected = variations[choice_idx]
                self.apply_parameter_set(selected)
                
                # 提供测试建议
                print(f"\n🚀 配置已更新！建议测试方法:")
                print(f"   python run_py313_app.py")
                print(f"   输入简短文本测试新的语音效果")
            else:
                print("❌ 无效选择")
                
        except ValueError:
            print("❌ 请输入有效数字")


def print_advanced_tuning_guide():
    """打印高级微调指南"""
    print("\n🚀 高级语音微调指南")
    print("=" * 60)
    
    print("\n1️⃣ 本地TTS模型替换方案:")
    print("   • Coqui TTS (Mozilla TTS)")
    print("   • VITS (Conditional Variational Autoencoder)")  
    print("   • Tacotron 2 + WaveGlow")
    print("   • 优势: 完全可训练，支持fine-tuning")
    print("   • 劣势: 需要GPU，模型较大，配置复杂")
    
    print("\n2️⃣ 语音克隆方案:")
    print("   • Real-Time-Voice-Cloning")
    print("   • Tortoise TTS")
    print("   • OpenVoice")
    print("   • 需要: 目标语音样本 10-30分钟")
    print("   • 适用: 创建专属冥想导师语音")
    
    print("\n3️⃣ 混合方案:")
    print("   • 保持Edge-TTS做主要合成")
    print("   • 使用语音后处理优化音质")
    print("   • 添加环境音效和混响")
    print("   • 实现: librosa + soundfile处理")
    
    print("\n4️⃣ 商业TTS API:")
    print("   • Google Cloud Text-to-Speech")
    print("   • Amazon Polly") 
    print("   • Azure Cognitive Services")
    print("   • 优势: 更多自定义选项")
    print("   • 成本: 按使用量付费")


def create_local_tts_setup_script():
    """创建本地TTS设置脚本"""
    setup_code = '''
#!/usr/bin/env python3
"""
本地TTS模型设置脚本
用于替换Edge-TTS实现完全可控的语音合成
"""

# 安装命令 (需要GPU支持):
# pip install TTS torch torchaudio

try:
    from TTS.api import TTS
    import torch
    
    class LocalTTSReplacer:
        def __init__(self):
            # 检查GPU支持
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"使用设备: {self.device}")
            
            # 初始化中文TTS模型
            self.tts = TTS(model_name="tts_models/zh-CN/baker/tacotron2-DDC-GST")
            
        def synthesize(self, text: str, output_path: str):
            """合成语音"""
            self.tts.tts_to_file(text=text, file_path=output_path)
            
        def fine_tune_setup(self, dataset_path: str):
            """设置微调环境"""
            print("设置微调环境...")
            # 这里可以添加微调代码
            pass
    
    # 使用示例
    if __name__ == "__main__":
        replacer = LocalTTSReplacer()
        replacer.synthesize("这是一个测试文本", "test_output.wav")
        
except ImportError:
    print("需要安装 TTS 库: pip install TTS")
'''
    
    with open("local_tts_setup.py", "w", encoding="utf-8") as f:
        f.write(setup_code)
    
    print("✅ 已创建 local_tts_setup.py")
    print("🔧 可用于设置本地TTS模型微调环境")


def main():
    """主函数"""
    print("🎙️ 语音微调指南和工具")
    print("=" * 50)
    
    # 创建微调工具实例
    tuner = VoiceFineTuner()
    
    print("\n选择操作:")
    print("1. 交互式参数调优 (推荐)")
    print("2. 查看高级微调指南") 
    print("3. 创建本地TTS设置脚本")
    print("4. 分析当前配置")
    print("0. 退出")
    
    try:
        choice = input("\n请选择 (0-4): ").strip()
        
        if choice == "1":
            tuner.interactive_tuning()
        elif choice == "2":
            print_advanced_tuning_guide()
        elif choice == "3":
            create_local_tts_setup_script()
        elif choice == "4":
            analysis = tuner.analyze_current_setup()
            print("\n📊 详细配置分析:")
            for key, value in analysis.items():
                print(f"  {key}: {value}")
        elif choice == "0":
            print("👋 再见！")
        else:
            print("❌ 无效选择")
            
    except KeyboardInterrupt:
        print("\n\n👋 用户中断，再见！")
    except Exception as e:
        print(f"\n❌ 错误: {e}")


if __name__ == "__main__":
    main()

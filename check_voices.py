"""
检查可用的Edge-TTS中文语音选项
"""
import edge_tts
import asyncio

async def list_chinese_voices():
    voices = await edge_tts.list_voices()
    chinese_voices = [v for v in voices if 'zh-CN' in v['Locale']]
    
    print("🎙️ 可用的中文语音选项：")
    print("=" * 80)
    
    for i, voice in enumerate(chinese_voices, 1):
        name = voice['ShortName']
        friendly = voice['FriendlyName']
        gender = voice['Gender']
        categories = voice['VoiceTag'].get('ContentCategories', [])
        
        print(f"{i:2d}. {name}")
        print(f"    名称: {friendly}")
        print(f"    性别: {gender}")
        print(f"    类别: {', '.join(categories)}")
        print()

if __name__ == "__main__":
    asyncio.run(list_chinese_voices())

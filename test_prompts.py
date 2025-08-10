#!/usr/bin/env python3
"""
测试情绪转换提示词生成
"""

import asyncio
from py313_meditation_app import MeditationApp

async def test_emotion_prompts():
    print("🧪 测试情绪转换提示词生成...")
    
    try:
        app = MeditationApp()
        
        user_input = "我最近工作压力特别大，总是失眠，心里很焦虑，希望能找到内心的平静。"
        duration = 6  # 6分钟测试
        
        print(f"💭 用户倾诉: {user_input}")
        print(f"⏱️ 冥想时长: {duration}分钟")
        print()
        
        # 生成提示词
        print("🤖 正在生成情绪转换提示词...")
        prompts_data = app.generate_prompts(user_input, duration)
        
        print("\n📋 生成结果:")
        print(f"🧠 分析: {prompts_data['analysis']}")
        print(f"🎭 情绪旅程: {prompts_data['emotion_journey']}")
        
        print("\n📝 冥想引导语:")
        for i, prompt in enumerate(prompts_data['script_prompts'], 1):
            print(f"  {i}. {prompt}")
        
        print("\n🎵 音乐描述:")
        for i, prompt in enumerate(prompts_data['music_prompts'], 1):
            print(f"  {i}. {prompt}")
        
        print("\n⏱️ 时间分配:")
        for stage in prompts_data['stage_timings']:
            print(f"  阶段{stage['stage']}: {stage['emotion']} ({stage['duration']}秒)")
        
        print("\n✅ 情绪转换提示词生成测试完成!")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_emotion_prompts())

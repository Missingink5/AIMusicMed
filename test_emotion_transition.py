#!/usr/bin/env python3
"""
测试情绪转换冥想生成系统
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from py313_meditation_app import MeditationApp
import asyncio


def test_emotion_analysis():
    """测试情绪分析功能"""
    print("🧪 测试情绪分析功能...")
    
    try:
        app = MeditationApp()
        
        test_cases = [
            ("我最近工作压力很大，总是担心做不好，心里很焦虑", "焦虑"),
            ("失恋了，心情很低落，觉得生活没有意义", "忧郁"),
            ("和同事吵架了，现在很生气，想要发泄一下", "敌意"),
            ("今天心情不错，感觉很满足和开心", "喜悦"),
            ("刚刚完成了一个重要项目，觉得很有成就感", "自豪"),
            ("想要找个安静的地方好好休息一下", "平静"),
            ("看到朋友们都很开心，我也感到很温暖", "友爱")
        ]
        
        for user_input, expected in test_cases:
            emotion = app.local_music_lib.analyze_user_emotion(user_input)
            status = "✅" if emotion == expected else "❌"
            print(f"{status} 输入: {user_input[:30]}... → 检测: {emotion} (期望: {expected})")
        
        print("✅ 情绪分析测试完成\n")
        
    except Exception as e:
        print(f"❌ 情绪分析测试失败: {e}\n")


def test_emotion_journey_planning():
    """测试情绪转换计划功能"""
    print("🧪 测试情绪转换计划功能...")
    
    try:
        app = MeditationApp()
        
        test_cases = [
            "我最近工作压力很大，总是失眠，心里很焦虑",
            "失恋了，心情很低落，觉得什么都没意思",
            "和家人吵架了，现在很生气，心情很糟糕",
            "今天感觉还不错，但是想要更加平静一些"
        ]
        
        for user_input in test_cases:
            print(f"\n💭 用户倾诉: {user_input}")
            journey = app.plan_emotion_journey(user_input, 6)  # 6分钟测试
            
            print("🗺️ 情绪转换计划:")
            for stage in journey:
                print(f"  阶段{stage['stage']}: {stage['emotion_cn']} → {stage['emotion_en']} "
                      f"({stage['duration']}秒, {stage['time_percentage']:.1%})")
        
        print("\n✅ 情绪转换计划测试完成\n")
        
    except Exception as e:
        print(f"❌ 情绪转换计划测试失败: {e}\n")


async def test_prompt_generation():
    """测试情绪转换提示词生成"""
    print("🧪 测试情绪转换提示词生成...")
    
    try:
        app = MeditationApp()
        
        user_input = "我最近工作压力特别大，经常失眠，心里很焦虑，希望能找到内心的平静。"
        
        print(f"💭 用户倾诉: {user_input}")
        
        # 生成提示词
        prompts_data = app.generate_prompts(user_input, 6)  # 6分钟测试
        
        print("\n📋 生成的提示词数据:")
        print(f"🧠 分析结果: {prompts_data['analysis']}")
        print(f"🎭 情绪旅程: {prompts_data['emotion_journey']}")
        
        print("\n📝 冥想引导语:")
        for i, prompt in enumerate(prompts_data['script_prompts'], 1):
            print(f"  {i}. {prompt}")
        
        print("\n🎵 音乐提示:")
        for i, prompt in enumerate(prompts_data['music_prompts'], 1):
            print(f"  {i}. {prompt}")
        
        print("\n⏱️ 阶段时间分配:")
        for stage in prompts_data['stage_timings']:
            print(f"  阶段{stage['stage']}: {stage['emotion']} ({stage['duration']}秒)")
        
        print("\n✅ 提示词生成测试完成")
        
    except Exception as e:
        print(f"❌ 提示词生成测试失败: {e}")


def test_music_library_status():
    """测试音乐库状态"""
    print("🧪 测试音乐库状态...")
    
    try:
        app = MeditationApp()
        status = app.local_music_lib.get_library_status()
        
        print("📊 音乐库状态:")
        total_music = 0
        for emotion, count in status.items():
            print(f"  {emotion}: {count} 首")
            total_music += count
        
        print(f"📈 总计: {total_music} 首音乐")
        
        if total_music > 0:
            print("✅ 音乐库状态正常")
        else:
            print("⚠️ 音乐库为空，建议添加音乐文件")
        
    except Exception as e:
        print(f"❌ 音乐库状态测试失败: {e}")


def test_english_emotion_mapping():
    """测试英文情绪映射"""
    print("🧪 测试英文情绪映射...")
    
    try:
        app = MeditationApp()
        
        english_emotions = ['Anxiety', 'Sad', 'Hostility', 'Quiet', 'Happy', 'Pride', 'Love']
        
        print("🔄 英文情绪映射测试:")
        for emotion_en in english_emotions:
            music_file = app.local_music_lib.get_music_for_emotion_english(emotion_en, 60)
            status = "✅" if music_file else "❌"
            filename = os.path.basename(music_file) if music_file else "无可用音乐"
            print(f"  {status} {emotion_en}: {filename}")
        
        print("✅ 英文情绪映射测试完成")
        
    except Exception as e:
        print(f"❌ 英文情绪映射测试失败: {e}")


async def main():
    """运行所有测试"""
    print("🚀 开始情绪转换冥想系统测试\n")
    
    # 基础测试
    test_emotion_analysis()
    test_emotion_journey_planning()
    test_music_library_status()
    test_english_emotion_mapping()
    
    # 提示词生成测试（需要API）
    try:
        await test_prompt_generation()
    except Exception as e:
        print(f"⚠️ 提示词生成测试跳过（可能需要API配置）: {e}")
    
    print("\n🎉 所有测试完成!")
    print("\n📖 使用指南:")
    print("1. 确保 music_library/ 目录中有按情绪分类的音乐文件")
    print("2. 配置 DeepSeek API Key 以使用完整的提示词生成功能")
    print("3. 运行 py313_meditation_app.py 开始使用情绪转换冥想系统")


if __name__ == "__main__":
    asyncio.run(main())

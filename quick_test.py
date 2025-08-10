#!/usr/bin/env python3
"""
快速测试情绪转换功能
"""

from py313_meditation_app import MeditationApp

def quick_test():
    print("🧪 快速测试情绪转换功能...")
    
    app = MeditationApp()
    
    test_cases = [
        "我最近工作压力很大，总是失眠，心里很焦虑",
        "失恋了，心情很低落，觉得生活没有意义",
        "和同事吵架了，现在很生气，想要发泄一下"
    ]
    
    for user_input in test_cases:
        print(f"\n💭 用户输入: {user_input}")
        
        # 情绪分析
        emotion = app.local_music_lib.analyze_user_emotion(user_input)
        print(f"😊 识别情绪: {emotion}")
        
        # 情绪转换规划
        journey = app.plan_emotion_journey(user_input, 6)
        path = " → ".join([stage["emotion_cn"] for stage in journey])
        print(f"🗺️ 转换路径: {path}")
        
        # 显示时长分配
        for stage in journey:
            print(f"   阶段{stage['stage']}: {stage['emotion_cn']} ({stage['duration']}秒)")
    
    print("\n✅ 快速测试完成")

if __name__ == "__main__":
    quick_test()

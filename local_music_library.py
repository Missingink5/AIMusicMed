"""
本地音乐库管理器
支持按情绪分类管理和选择背景音乐
"""

import os
import random
from typing import List, Dict, Optional
from pathlib import Path


class LocalMusicLibrary:
    """本地音乐库管理器"""
    
    def __init__(self, library_path: str = None):
        """
        初始化音乐库
        
        Args:
            library_path: 音乐库根路径，默认为项目下的 music_library
        """
        if library_path is None:
            # 获取当前文件所在目录的 music_library 文件夹
            current_dir = Path(__file__).parent
            self.library_path = current_dir / "music_library"
        else:
            self.library_path = Path(library_path)
        
        # 支持的音频格式
        self.supported_formats = {'.mp3', '.wav', '.m4a', '.flac', '.ogg'}
        
        # 情绪到文件夹的映射
        self.emotion_folders = {
            '敌意': 'Hostility',
            '忧郁': 'Sad', 
            '焦虑': 'Anxiety',
            '平静': 'Quiet',
            '喜悦': 'Happy',
            '自豪': 'Pride',
            '友爱': 'Love'
        }
        
        # 用户情绪到音乐情绪的映射（直接映射到目标情绪）
        self.emotion_mapping = {
            # 焦虑相关词汇
            '压力': '焦虑',
            '焦虑': '焦虑',
            '紧张': '焦虑',
            '不安': '焦虑',
            '担心': '焦虑',
            '害怕': '焦虑',
            '恐惧': '焦虑',
            '慌张': '焦虑',
            '失眠': '焦虑',
            # 忧郁相关词汇
            '悲伤': '忧郁',
            '低落': '忧郁', 
            '沮丧': '忧郁',
            '忧郁': '忧郁',
            '抑郁': '忧郁',
            '难过': '忧郁',
            '痛苦': '忧郁',
            '绝望': '忧郁',
            '失恋': '忧郁',
            '孤独': '忧郁',
            '空虚': '忧郁',
            '意义': '忧郁',  # "没有意义"等表达
            # 敌意相关词汇
            '愤怒': '敌意',
            '生气': '敌意',
            '愤慨': '敌意',
            '恼火': '敌意',
            '暴躁': '敌意',
            '气愤': '敌意',
            '争吵': '敌意',
            '冲突': '敌意',
            '仇恨': '敌意',
            '发泄': '敌意',
            '敌意': '敌意',
            # 平静相关词汇
            '平静': '平静',
            '安静': '平静',
            '宁静': '平静',
            '放松': '平静',
            '休息': '平静',
            '疲惫': '平静',
            # 自豪相关词汇
            '成功': '自豪',
            '成就': '自豪',
            '目标': '自豪',
            '骄傲': '自豪',
            '完成': '自豪',
            '胜利': '自豪',
            '项目': '自豪',  # "完成项目"等
            # 喜悦相关词汇
            '开心': '喜悦',
            '快乐': '喜悦',
            '兴奋': '喜悦',
            '愉快': '喜悦',
            '高兴': '喜悦',
            '满足': '喜悦',
            '不错': '喜悦',
            # 友爱相关词汇
            '温暖': '友爱',
            '关爱': '友爱',
            '感恩': '友爱',
            '爱意': '友爱',
            '慈爱': '友爱',
            '亲情': '友爱',
            '友情': '友爱',
            '挫折': '友爱',
            '困扰': '友爱'
        }
        
        print(f"📁 本地音乐库路径: {self.library_path}")
    
    def scan_library(self) -> Dict[str, List[str]]:
        """
        扫描音乐库，返回各情绪的音乐文件列表
        
        Returns:
            Dict[str, List[str]]: 情绪 -> 音乐文件路径列表
        """
        library_info = {}
        
        if not self.library_path.exists():
            print(f"⚠️ 音乐库目录不存在: {self.library_path}")
            return library_info
        
        for emotion, folder_name in self.emotion_folders.items():
            folder_path = self.library_path / folder_name
            music_files = []
            
            if folder_path.exists():
                for file_path in folder_path.iterdir():
                    if file_path.is_file() and file_path.suffix.lower() in self.supported_formats:
                        music_files.append(str(file_path))
                
                library_info[emotion] = music_files
                print(f"  📂 {emotion}: {len(music_files)} 首音乐")
            else:
                library_info[emotion] = []
                print(f"  📂 {emotion}: 目录不存在")
        
        return library_info
    
    def analyze_user_emotion(self, user_input: str) -> str:
        """
        分析用户输入的情绪倾向
        
        Args:
            user_input: 用户倾诉内容
            
        Returns:
            str: 推荐的音乐情绪类型
        """
        user_input_lower = user_input.lower()
        
        # 统计各种情绪关键词出现次数
        emotion_scores = {}
        
        for keyword, target_emotion in self.emotion_mapping.items():
            count = user_input_lower.count(keyword)
            if count > 0:
                if target_emotion not in emotion_scores:
                    emotion_scores[target_emotion] = 0
                emotion_scores[target_emotion] += count
        
        if emotion_scores:
            # 返回得分最高的情绪
            best_emotion = max(emotion_scores.items(), key=lambda x: x[1])[0]
            print(f"🎭 情绪分析结果: {best_emotion} (匹配度: {emotion_scores[best_emotion]})")
            return best_emotion
        else:
            # 默认返回平静
            print("🎭 未识别到特定情绪，默认使用: 平静")
            return '平静'
    
    def get_music_for_emotion(self, emotion: str, duration_seconds: int) -> Optional[str]:
        """
        根据情绪获取合适的背景音乐
        
        Args:
            emotion: 目标情绪
            duration_seconds: 需要的音乐时长（秒）
            
        Returns:
            Optional[str]: 选中的音乐文件路径，如果没有则返回None
        """
        library_info = self.scan_library()
        
        if emotion not in library_info or not library_info[emotion]:
            print(f"⚠️ 情绪 '{emotion}' 没有可用的本地音乐")
            return None
        
        music_files = library_info[emotion]
        selected_file = random.choice(music_files)
        
        print(f"🎵 选择本地音乐: {Path(selected_file).name} (情绪: {emotion})")
        return selected_file
    
    def get_music_for_emotion_english(self, emotion_en: str, duration_seconds: int) -> Optional[str]:
        """
        根据英文情绪名称获取合适的背景音乐
        
        Args:
            emotion_en: 英文情绪名称 (如 'Anxiety', 'Happy', 'Quiet' 等)
            duration_seconds: 需要的音乐时长（秒）
            
        Returns:
            Optional[str]: 选中的音乐文件路径，如果没有则返回None
        """
        # 英文情绪到中文情绪的反向映射
        en_to_cn_mapping = {
            'Hostility': '敌意',
            'Sad': '忧郁',
            'Anxiety': '焦虑', 
            'Quiet': '平静',
            'Happy': '喜悦',
            'Pride': '自豪',
            'Love': '友爱'
        }
        
        # 转换为中文情绪
        emotion_cn = en_to_cn_mapping.get(emotion_en, '平静')
        
        # 扫描音乐库
        library_info = self.scan_library()
        
        if emotion_cn not in library_info or not library_info[emotion_cn]:
            print(f"⚠️ 英文情绪 '{emotion_en}' (中文: {emotion_cn}) 没有可用的本地音乐")
            return None
        
        music_files = library_info[emotion_cn]
        selected_file = random.choice(music_files)
        
        print(f"🎵 选择本地音乐: {Path(selected_file).name} (英文情绪: {emotion_en} -> 中文: {emotion_cn})")
        return selected_file
    
    def get_library_status(self) -> Dict[str, int]:
        """
        获取音乐库状态概览
        
        Returns:
            Dict[str, int]: 各情绪的音乐数量
        """
        library_info = self.scan_library()
        return {emotion: len(files) for emotion, files in library_info.items()}


def test_local_music_library():
    """测试本地音乐库功能"""
    print("🧪 测试本地音乐库管理器...")
    
    # 创建音乐库实例
    music_lib = LocalMusicLibrary()
    
    # 获取库状态
    status = music_lib.get_library_status()
    print(f"📊 音乐库状态: {status}")
    
    # 测试情绪分析
    test_inputs = [
        "我最近总是失眠，而且觉得压力很大，什么都做不好。",
        "工作上遇到了很多挫折，感觉很焦虑，需要放松一下。",
        "最近心情很低落，希望能找到内心的平静。",
        "感觉生活节奏太快，想要慢下来好好休息。",
        "人际关系让我感到困扰，需要调整心态。",
        "最近总是感到孤独，希望能找到内心的力量。"
    ]
    
    for user_input in test_inputs:
        print(f"\n💭 用户输入: {user_input}")
        emotion = music_lib.analyze_user_emotion(user_input)
        music_file = music_lib.get_music_for_emotion(emotion, 60)
        if music_file:
            print(f"🎼 推荐音乐: {Path(music_file).name}")
        else:
            print("🔇 无可用音乐，建议使用AI生成")
    
    print("\n✅ 本地音乐库测试完成")


if __name__ == "__main__":
    test_local_music_library()

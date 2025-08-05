"""
Python 3.13兼容的音频处理模块
替代pydub，使用soundfile和librosa处理音频
"""

import os
import numpy as np
import soundfile as sf
import librosa
from typing import Union, Optional, Tuple
import tempfile


class AudioSegment:
    """
    兼容pydub的AudioSegment类，使用soundfile和librosa实现
    """
    
    def __init__(self, data: np.ndarray = None, sample_rate: int = 22050):
        """
        初始化音频片段
        
        Args:
            data: 音频数据数组
            sample_rate: 采样率
        """
        self.data = data if data is not None else np.array([])
        self.sample_rate = sample_rate
        self._duration_ms = None
    
    @classmethod
    def from_file(cls, file_path: str) -> 'AudioSegment':
        """从文件加载音频"""
        try:
            data, sample_rate = librosa.load(file_path, sr=None, mono=False)
            # 如果是单声道，确保维度正确
            if data.ndim == 1:
                data = data.reshape(1, -1)
            elif data.ndim == 2 and data.shape[0] > data.shape[1]:
                data = data.T  # 转置以确保形状为 (channels, samples)
            
            return cls(data, sample_rate)
        except Exception as e:
            raise ValueError(f"无法加载音频文件 {file_path}: {e}")
    
    @classmethod
    def silent(cls, duration: int, sample_rate: int = 22050) -> 'AudioSegment':
        """
        创建静音音频片段
        
        Args:
            duration: 持续时间（毫秒）
            sample_rate: 采样率
        """
        samples = int(duration * sample_rate / 1000)
        data = np.zeros((1, samples))  # 单声道静音
        return cls(data, sample_rate)
    
    @classmethod
    def empty(cls) -> 'AudioSegment':
        """创建空音频片段"""
        return cls(np.array([]).reshape(1, 0), 22050)
    
    def __len__(self) -> int:
        """返回音频长度（毫秒）"""
        if self.data.size == 0:
            return 0
        return int(self.data.shape[-1] * 1000 / self.sample_rate)
    
    def __add__(self, other: 'AudioSegment') -> 'AudioSegment':
        """连接两个音频片段"""
        if self.data.size == 0:
            return other
        if other.data.size == 0:
            return self
        
        # 确保采样率一致
        if self.sample_rate != other.sample_rate:
            other = other._resample(self.sample_rate)
        
        # 确保声道数一致
        self_channels = self.data.shape[0] if self.data.ndim > 1 else 1
        other_channels = other.data.shape[0] if other.data.ndim > 1 else 1
        
        if self_channels != other_channels:
            # 转换为单声道
            self_data = self._to_mono() if self_channels > 1 else self.data
            other_data = other._to_mono() if other_channels > 1 else other.data
        else:
            self_data = self.data
            other_data = other.data
        
        # 连接音频
        if self_data.ndim == 1:
            self_data = self_data.reshape(1, -1)
        if other_data.ndim == 1:
            other_data = other_data.reshape(1, -1)
            
        combined_data = np.concatenate([self_data, other_data], axis=1)
        return AudioSegment(combined_data, self.sample_rate)
    
    def __sub__(self, db: Union[int, float]) -> 'AudioSegment':
        """降低音量（dB）"""
        factor = 10 ** (-db / 20)
        new_data = self.data * factor
        return AudioSegment(new_data, self.sample_rate)
    
    def overlay(self, other: 'AudioSegment', position: int = 0) -> 'AudioSegment':
        """
        将另一个音频片段叠加到当前片段上
        
        Args:
            other: 要叠加的音频片段
            position: 叠加位置（毫秒）
        """
        if self.data.size == 0:
            return other
        if other.data.size == 0:
            return self
        
        # 确保采样率一致
        if self.sample_rate != other.sample_rate:
            other = other._resample(self.sample_rate)
        
        # 计算位置（样本数）
        position_samples = int(position * self.sample_rate / 1000)
        
        # 准备数据
        self_data = self.data if self.data.ndim > 1 else self.data.reshape(1, -1)
        other_data = other.data if other.data.ndim > 1 else other.data.reshape(1, -1)
        
        # 确保声道数一致
        if self_data.shape[0] != other_data.shape[0]:
            # 转换为单声道
            if self_data.shape[0] > 1:
                self_data = np.mean(self_data, axis=0, keepdims=True)
            if other_data.shape[0] > 1:
                other_data = np.mean(other_data, axis=0, keepdims=True)
        
        # 计算输出长度
        self_length = self_data.shape[1]
        other_length = other_data.shape[1]
        output_length = max(self_length, position_samples + other_length)
        
        # 创建输出数组
        output_data = np.zeros((self_data.shape[0], output_length))
        
        # 复制原音频
        output_data[:, :self_length] = self_data
        
        # 叠加新音频
        end_pos = position_samples + other_length
        if end_pos <= output_length:
            output_data[:, position_samples:end_pos] += other_data
        else:
            # 截断叠加的音频
            available_length = output_length - position_samples
            output_data[:, position_samples:] += other_data[:, :available_length]
        
        return AudioSegment(output_data, self.sample_rate)
    
    def __getitem__(self, milliseconds) -> 'AudioSegment':
        """切片音频片段"""
        if isinstance(milliseconds, slice):
            start = milliseconds.start or 0
            stop = milliseconds.stop or len(self)
        else:
            start = 0
            stop = milliseconds
        
        start_sample = int(start * self.sample_rate / 1000)
        stop_sample = int(stop * self.sample_rate / 1000)
        
        if self.data.ndim == 1:
            sliced_data = self.data[start_sample:stop_sample]
        else:
            sliced_data = self.data[:, start_sample:stop_sample]
        
        return AudioSegment(sliced_data, self.sample_rate)
    
    def _to_mono(self) -> np.ndarray:
        """转换为单声道"""
        if self.data.ndim == 1:
            return self.data
        return np.mean(self.data, axis=0)
    
    def _resample(self, target_sr: int) -> 'AudioSegment':
        """重新采样"""
        if self.sample_rate == target_sr:
            return self
        
        if self.data.ndim == 1:
            resampled_data = librosa.resample(self.data, orig_sr=self.sample_rate, target_sr=target_sr)
        else:
            resampled_data = np.array([
                librosa.resample(channel, orig_sr=self.sample_rate, target_sr=target_sr)
                for channel in self.data
            ])
        
        return AudioSegment(resampled_data, target_sr)
    
    def export(self, filename: str, format: str = "wav", bitrate: str = "128k") -> str:
        """
        导出音频文件
        
        Args:
            filename: 输出文件名
            format: 音频格式
            bitrate: 比特率（对WAV格式无效）
        """
        try:
            # 确保目录存在
            dirname = os.path.dirname(filename)
            if dirname:  # 只有当dirname不为空时才创建目录
                os.makedirs(dirname, exist_ok=True)
            
            # 准备数据
            if self.data.size == 0:
                # 如果是空音频，创建短暂的静音
                data = np.zeros((1, int(0.1 * self.sample_rate)))  # 0.1秒静音
            else:
                data = self.data
            
            # 转换数据格式
            if data.ndim == 1:
                # 单声道
                sf.write(filename, data, self.sample_rate)
            else:
                # 多声道，需要转置
                sf.write(filename, data.T, self.sample_rate)
            
            return filename
            
        except Exception as e:
            raise ValueError(f"无法导出音频文件 {filename}: {e}")


def test_audio_segment():
    """测试AudioSegment类"""
    print("🧪 测试AudioSegment类...")
    
    # 测试静音创建
    silence = AudioSegment.silent(duration=1000)  # 1秒静音
    print(f"静音长度: {len(silence)} ms")
    
    # 测试导出
    test_file = "test_silence.wav"
    silence.export(test_file)
    print(f"✅ 静音音频导出成功: {test_file}")
    
    # 测试加载
    loaded = AudioSegment.from_file(test_file)
    print(f"加载音频长度: {len(loaded)} ms")
    
    # 测试音量调整
    quieter = loaded - 10  # 降低10dB
    print("✅ 音量调整测试通过")
    
    # 测试连接
    combined = silence + quieter
    print(f"连接后长度: {len(combined)} ms")
    
    # 清理测试文件
    try:
        os.remove(test_file)
        print("🧹 测试文件已清理")
    except:
        pass
    
    print("✅ AudioSegment类测试完成")


if __name__ == "__main__":
    test_audio_segment()

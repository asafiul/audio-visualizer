import librosa
import numpy as np
from typing import Dict, Any, Optional
import os
from abc import ABC, abstractmethod


class IAudioSource(ABC):
    @abstractmethod
    def get_audio_segment(self, time: float, window: float) -> Optional[np.ndarray]:
        pass
    
    @abstractmethod
    def is_beat_at_time(self, time: float, threshold: float) -> bool:
        pass
    
    @property
    @abstractmethod
    def duration(self) -> float:
        pass
    
    @property
    @abstractmethod
    def sample_rate(self) -> int:
        pass


class AudioProcessor(IAudioSource):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.audio_data = None
        self.sample_rate = None
        self.duration = None
        self.beats = None
        self.spectrogram = None
        self.original_audio_path = None
        
    def load_audio(self, file_path: str):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        
        print(f"Loading audio: {file_path}")
        self.original_audio_path = file_path
        
        audio_config = self.config['audio']
        self.audio_data, self.sample_rate = librosa.load(
            file_path,
            sr=audio_config['sample_rate'],
            mono=True
        )
        
        self.duration = librosa.get_duration(y=self.audio_data, sr=self.sample_rate)
        print(f"Duration: {self.duration:.2f} sec, Sample rate: {self.sample_rate} Hz")
        
        if audio_config['normalize']:
            self.audio_data = librosa.util.normalize(self.audio_data)
        
        if audio_config.get('bass_boost', 1.0) != 1.0:
            self._apply_bass_boost(audio_config['bass_boost'])
        
        self._analyze_audio()
        return self
    
    def _apply_bass_boost(self, factor: float):
        from scipy import signal
        b, a = signal.butter(3, 0.1, 'low')
        bass = signal.filtfilt(b, a, self.audio_data)
        self.audio_data = self.audio_data * (1 - 0.3) + bass * 0.3 * factor
    
    def _analyze_audio(self):
        print("Analyzing audio...")
        tempo, beats = librosa.beat.beat_track(
            y=self.audio_data,
            sr=self.sample_rate
        )
        
        if isinstance(tempo, np.ndarray):
            self.tempo = float(tempo[0]) if len(tempo) > 0 else 120.0
        else:
            self.tempo = float(tempo)
        
        self.beats = librosa.frames_to_time(beats, sr=self.sample_rate)
        self.spectrogram = np.abs(librosa.stft(self.audio_data))
        print(f"Tempo: {self.tempo:.0f} BPM, Beats: {len(self.beats)}")
    
    def get_audio_segment(self, time_point: float, window_duration: float = 1.0) -> Optional[np.ndarray]:
        if self.audio_data is None:
            return None
            
        start_sample = int(max(0, (time_point - window_duration / 2) * self.sample_rate))
        end_sample = int(min(len(self.audio_data), (time_point + window_duration / 2) * self.sample_rate))
        
        if start_sample >= end_sample:
            return None
            
        return self.audio_data[start_sample:end_sample]
    
    def is_beat_at_time(self, time: float, threshold: float = 0.1) -> bool:
        if self.beats is None:
            return False
        return np.any(np.abs(self.beats - time) < threshold)
    
    @property
    def duration(self) -> float:
        return self._duration if hasattr(self, '_duration') else 0.0
    
    @duration.setter
    def duration(self, value: float):
        self._duration = value
    
    @property
    def sample_rate(self) -> int:
        return self._sample_rate if hasattr(self, '_sample_rate') else 0
    
    @sample_rate.setter
    def sample_rate(self, value: int):
        self._sample_rate = value
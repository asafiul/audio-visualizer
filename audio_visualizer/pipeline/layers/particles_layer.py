import cv2
import numpy as np
from ..base_layer import BaseLayer


class Particle:
    def __init__(self, width, height, config, spawn_time=0):
        self.x = np.random.uniform(0, width)
        self.y = np.random.uniform(0, height)
        
        self.config = config
        particles_config = config['pipeline']['particles']
        
        min_speed = particles_config.get('min_speed', 0.1)
        angle = np.random.uniform(0, 2 * np.pi)
        speed = np.random.uniform(min_speed, min_speed * 3)
        self.vx = np.cos(angle) * speed
        self.vy = np.sin(angle) * speed
        
        self.size = np.random.uniform(2.0, 5.0)
        self.color_ratio = np.random.uniform(0, 1)
        
        self.life = 1.0
        self.decay_min = particles_config.get('decay_min', 0.96)
        self.decay_max = particles_config.get('decay_max', 0.99)
        self.decay = np.random.uniform(self.decay_min, self.decay_max)
        
        self.width = width
        self.height = height
        self.spawn_time = spawn_time
        self.max_lifetime = config['pipeline']['particles'].get('max_lifetime', 300)
        
        self.last_audio_force = [0, 0]
        
    def update(self, audio_force, beat_force, rms, time):
        particles_config = self.config['pipeline']['particles']
        
        force_multiplier = particles_config.get('force_multiplier', 15.0)
        max_speed = particles_config.get('max_speed', 12.0)
        bounce_strength = particles_config.get('bounce_strength', 0.85)
        
        audio_strength = rms * force_multiplier
        
        self.vx += audio_force[0] * audio_strength * 0.5
        self.vy += audio_force[1] * audio_strength * 0.5
        
        if beat_force > 0:
            beat_multiplier = beat_force * 8
            self.vx += np.random.uniform(-beat_multiplier, beat_multiplier) * 0.7
            self.vy += np.random.uniform(-beat_multiplier, beat_multiplier) * 0.7
            self.life = min(1.0, self.life + 0.3)
        
        self.x += self.vx
        self.y += self.vy
        
        self.vx *= 0.92
        self.vy *= 0.92
        
        speed = np.sqrt(self.vx**2 + self.vy**2)
        if speed > max_speed:
            scale = max_speed / speed
            self.vx *= scale
            self.vy *= scale
        
        margin = 5
        bounce = bounce_strength
        
        if self.x < margin:
            self.vx = abs(self.vx) * bounce
            self.x = margin
            self.vx += np.random.uniform(0.5, 2.0)
            
        elif self.x > self.width - margin:
            self.vx = -abs(self.vx) * bounce
            self.x = self.width - margin
            self.vx += np.random.uniform(-2.0, -0.5)
            
        if self.y < margin:
            self.vy = abs(self.vy) * bounce
            self.y = margin
            self.vy += np.random.uniform(0.5, 2.0)
            
        elif self.y > self.height - margin:
            self.vy = -abs(self.vy) * bounce
            self.y = self.height - margin
            self.vy += np.random.uniform(-2.0, -0.5)
        
        self.life *= self.decay
        
        if abs(self.vx) < 0.1 and abs(self.vy) < 0.1 and self.life > 0.3:
            self.life *= 0.95
        
        self.max_lifetime -= 1
        if self.max_lifetime <= 0:
            return False
            
        return self.life > 0.05
    
    def get_color(self):
        colors = self.config['visualization']['colors']
        primary = np.array(colors['primary'])
        secondary = np.array(colors['secondary'])
        
        color = (primary * (1 - self.color_ratio) + secondary * self.color_ratio).astype(np.uint8)
        return color
    
    def draw(self, frame):
        if self.life < 0.05:
            return
        
        particles_config = self.config['pipeline']['particles']
        trail_enabled = particles_config.get('trail_enabled', True)
        use_alpha = particles_config.get('use_alpha', True)
        
        base_color = self.get_color()
        opacity = particles_config.get('opacity', 0.8)
        if use_alpha:
            alpha = self.life * opacity
        else:
            alpha = opacity
        color = (base_color * alpha).astype(np.uint8)
        bgr_color = (int(color[2]), int(color[1]), int(color[0]))
        
        current_size = max(1, int(self.size * self.life))
        
        cv2.circle(frame, (int(self.x), int(self.y)), current_size, bgr_color, -1)
        
        if current_size > 2:
            glow_size = current_size + 1
            glow_alpha = self.life * 0.4
            glow_color = (base_color * glow_alpha).astype(np.uint8)
            glow_bgr = (int(glow_color[2]), int(glow_color[1]), int(glow_color[0]))
            cv2.circle(frame, (int(self.x), int(self.y)), glow_size, glow_bgr, 1)
        
        if trail_enabled:
            speed = np.sqrt(self.vx**2 + self.vy**2)
            if speed > 2.0 and self.life > 0.3:
                dx = -self.vx / max(speed, 0.1) * 5
                dy = -self.vy / max(speed, 0.1) * 5
                
                trail_x = int(self.x + dx)
                trail_y = int(self.y + dy)
                
                trail_alpha = self.life * 0.6
                trail_color = (base_color * trail_alpha).astype(np.uint8)
                trail_bgr = (int(trail_color[2]), int(trail_color[1]), int(trail_color[0]))
                
                cv2.line(frame, (int(self.x), int(self.y)), (trail_x, trail_y), 
                        trail_bgr, max(1, current_size // 2))


class ParticlesLayer(BaseLayer):
    layer_type = "particles"
    
    def __init__(self, config, audio_processor, width, height):
        super().__init__(config, audio_processor, width, height)
        self.particles_config = config['pipeline']['particles']
        self.particles = []
        
        self.rms_history = []
        self.force_history = []
        self.max_history = 5
        
        self.init_particles()
    
    def init_particles(self):
        count = self.particles_config.get('count', 150)
        for _ in range(count):
            self.particles.append(Particle(self.width, self.height, self.config))
    
    def get_audio_forces(self, time):
        audio_segment = self.audio.get_audio_segment(time, 0.02)
        
        if audio_segment is None or len(audio_segment) < 50:
            return 0.0, [0, 0]
        
        rms = np.sqrt(np.mean(audio_segment**2))
        
        self.rms_history.append(rms)
        if len(self.rms_history) > self.max_history:
            self.rms_history.pop(0)
        
        smoothed_rms = np.mean(self.rms_history) if self.rms_history else rms
        
        if len(audio_segment) >= 128:
            fft = np.abs(np.fft.rfft(audio_segment[:128]))
            
            if len(fft) > 10:
                bass = np.mean(fft[:len(fft)//10])
                mid_start = len(fft) // 10
                mid_end = len(fft) // 2
                mids = np.mean(fft[mid_start:mid_end]) if mid_end > mid_start else 1.0
                highs = np.mean(fft[-len(fft)//10:]) if len(fft) > 10 else 1.0
                
                t = time
                
                force_x = (
                    np.sin(t * 3) * bass * 2.0 +
                    np.cos(t * 8) * mids * 3.0 +
                    np.sin(t * 15) * highs * 1.5
                )
                
                force_y = (
                    np.cos(t * 4) * bass * 2.0 +
                    np.sin(t * 7) * mids * 3.0 +
                    np.cos(t * 12) * highs * 1.5
                )
                
                force_mag = np.sqrt(force_x**2 + force_y**2)
                if force_mag > 0:
                    force_x /= force_mag
                    force_y /= force_mag
                
                audio_force = [force_x, force_y]
            else:
                audio_force = [np.sin(time * 5), np.cos(time * 4)]
        else:
            audio_force = [np.sin(time * 5), np.cos(time * 4)]
        
        audio_force[0] *= smoothed_rms
        audio_force[1] *= smoothed_rms
        
        self.force_history.append(audio_force)
        if len(self.force_history) > self.max_history:
            self.force_history.pop(0)
        
        if self.force_history:
            smoothed_force = np.mean(self.force_history, axis=0)
        else:
            smoothed_force = audio_force
        
        return smoothed_rms, smoothed_force
    
    def _render_direct(self, time: float, frame: np.ndarray) -> np.ndarray:
        rms, audio_force = self.get_audio_forces(time)
        
        beat_force = 1.5 if self.audio.is_beat_at_time(time, threshold=0.05) else 0.0
        
        particles_to_remove = []
        
        for i, particle in enumerate(self.particles):
            if particle.update(audio_force, beat_force, rms, time):
                particle.draw(frame)
            else:
                particles_to_remove.append(i)
                
        for idx in sorted(particles_to_remove, reverse=True):
            self.particles.pop(idx)
        
        target_count = self.particles_config.get('count', 150)
        current_count = len(self.particles)
        
        spawn_rate = self.particles_config.get('spawn_rate', 0.1)
        
        if current_count < target_count:
            spawn_multiplier = 1.0 + min(rms * 10, 5.0)
            particles_needed = target_count - current_count
            particles_to_spawn = min(int(particles_needed * spawn_multiplier * spawn_rate), 15)
            
            for _ in range(particles_to_spawn):
                self.particles.append(Particle(self.width, self.height, self.config, time))
        
        if beat_force > 0:
            for particle in self.particles:
                if np.random.random() < 0.15:
                    particle.color_ratio = (particle.color_ratio + 0.3) % 1.0
        
        return frame
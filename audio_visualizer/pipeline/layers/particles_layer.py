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
        self.decay_min = particles_config.get('decay_min', 0.997)
        self.decay_max = particles_config.get('decay_max', 0.999)
        self.decay = np.random.uniform(self.decay_min, self.decay_max)
        
        self.width = width
        self.height = height
        self.spawn_time = spawn_time
        self.max_lifetime = particles_config.get('max_lifetime', 600)
        
        self.last_audio_force = [0, 0]
        # Each particle has a unique phase offset for organic movement
        self.phase_offset = np.random.uniform(0, 2 * np.pi)
        # Each particle has its own preferred beat direction (random, not from center)
        self.beat_angle = np.random.uniform(0, 2 * np.pi)
        
    def update(self, audio_force, beat_force, rms, time):
        particles_config = self.config['pipeline']['particles']
        
        force_multiplier = particles_config.get('force_multiplier', 8.0)
        max_speed = particles_config.get('max_speed', 6.0)
        bounce_strength = particles_config.get('bounce_strength', 0.85)
        
        # Smooth audio influence - use rms to scale the coherent force direction
        audio_strength = rms * force_multiplier
        
        # Apply audio force — each particle drifts in its own unique direction
        # modulated by the global audio force for coherence
        particle_angle = self.phase_offset + time * 0.3
        px = np.cos(particle_angle) * 0.6 + audio_force[0] * 0.4
        py = np.sin(particle_angle) * 0.6 + audio_force[1] * 0.4
        self.vx += px * audio_strength * 0.12
        self.vy += py * audio_strength * 0.12
        
        # On beat: push each particle in its own random direction (beautiful scatter)
        if beat_force > 0:
            # Slowly rotate beat direction over time for variety
            self.beat_angle += np.random.uniform(-0.5, 0.5)
            beat_push = beat_force * 2.5
            self.vx += np.cos(self.beat_angle) * beat_push
            self.vy += np.sin(self.beat_angle) * beat_push
            # Refresh life slightly on beat
            self.life = min(1.0, self.life + 0.1)
        
        # Organic drift — each particle wanders in its own pattern
        drift_strength = 0.05
        self.vx += np.sin(time * 0.8 + self.phase_offset) * drift_strength
        self.vy += np.cos(time * 0.6 + self.phase_offset * 1.3) * drift_strength
        
        # Move
        self.x += self.vx
        self.y += self.vy
        
        # Damping - gentle friction so particles glide smoothly
        self.vx *= 0.96
        self.vy *= 0.96
        
        # Speed limit
        speed = np.sqrt(self.vx**2 + self.vy**2)
        if speed > max_speed:
            scale = max_speed / speed
            self.vx *= scale
            self.vy *= scale
        
        # Wrap around screen edges — particles reappear on the opposite side
        if self.x < 0:
            self.x += self.width
        elif self.x > self.width:
            self.x -= self.width
            
        if self.y < 0:
            self.y += self.height
        elif self.y > self.height:
            self.y -= self.height
        
        # Gentle life decay - particles live much longer now
        self.life *= self.decay
        
        self.max_lifetime -= 1
        if self.max_lifetime <= 0:
            return False
            
        return self.life > 0.03
    
    def get_color(self):
        # Use per-layer color overrides if available
        particles_config = self.config['pipeline']['particles']
        global_colors = self.config['visualization']['colors']
        primary = np.array(particles_config.get('color_primary', global_colors['primary']))
        secondary = np.array(particles_config.get('color_secondary', global_colors['secondary']))
        
        color = (primary * (1 - self.color_ratio) + secondary * self.color_ratio).astype(np.uint8)
        return color
    
    def draw(self, frame):
        if self.life < 0.03:
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
        
        current_size = max(1, int(self.size * (0.5 + self.life * 0.5)))
        
        cv2.circle(frame, (int(self.x), int(self.y)), current_size, bgr_color, -1)
        
        # Glow effect for larger particles
        if current_size > 2:
            glow_size = current_size + 2
            glow_alpha = self.life * 0.3
            glow_color = (base_color * glow_alpha).astype(np.uint8)
            glow_bgr = (int(glow_color[2]), int(glow_color[1]), int(glow_color[0]))
            cv2.circle(frame, (int(self.x), int(self.y)), glow_size, glow_bgr, 1)
        
        # Trail effect
        if trail_enabled:
            speed = np.sqrt(self.vx**2 + self.vy**2)
            if speed > 1.5 and self.life > 0.2:
                trail_len = min(speed * 2, 12)
                dx = -self.vx / max(speed, 0.1) * trail_len
                dy = -self.vy / max(speed, 0.1) * trail_len
                
                trail_x = int(self.x + dx)
                trail_y = int(self.y + dy)
                
                trail_alpha = self.life * 0.4
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
        self.max_history = 10  # Longer smoothing window
        
        self.prev_rms = 0.0
        self.prev_force = [0.0, 0.0]
        
        self.init_particles()
    
    def init_particles(self):
        count = self.particles_config.get('count', 150)
        for _ in range(count):
            self.particles.append(Particle(self.width, self.height, self.config))
    
    def get_audio_forces(self, time):
        audio_segment = self.audio.get_audio_segment(time, 0.05)
        
        if audio_segment is None or len(audio_segment) < 50:
            return self.prev_rms * 0.95, self.prev_force
        
        rms = np.sqrt(np.mean(audio_segment**2))
        
        self.rms_history.append(rms)
        if len(self.rms_history) > self.max_history:
            self.rms_history.pop(0)
        
        # Exponential moving average for smoother RMS
        smoothed_rms = 0
        weight_sum = 0
        for i, r in enumerate(self.rms_history):
            w = 1.5 ** i  # More recent = more weight
            smoothed_rms += r * w
            weight_sum += w
        smoothed_rms /= weight_sum if weight_sum > 0 else 1
        
        if len(audio_segment) >= 256:
            fft = np.abs(np.fft.rfft(audio_segment[:256]))
            
            if len(fft) > 10:
                bass = np.mean(fft[:len(fft)//8])
                mid_start = len(fft) // 8
                mid_end = len(fft) // 2
                mids = np.mean(fft[mid_start:mid_end]) if mid_end > mid_start else 1.0
                highs = np.mean(fft[mid_end:]) if len(fft) > mid_end else 1.0
                
                # Use slow-varying angles for coherent movement direction
                # These change slowly so particles move in a consistent direction
                t = time
                force_x = (
                    np.sin(t * 0.3) * bass * 2.0 +
                    np.cos(t * 0.7) * mids * 1.5 +
                    np.sin(t * 1.2) * highs * 0.8
                )
                force_y = (
                    np.cos(t * 0.4) * bass * 2.0 +
                    np.sin(t * 0.6) * mids * 1.5 +
                    np.cos(t * 1.0) * highs * 0.8
                )
                
                # Normalize to unit direction
                force_mag = np.sqrt(force_x**2 + force_y**2)
                if force_mag > 0:
                    force_x /= force_mag
                    force_y /= force_mag
                
                audio_force = [force_x, force_y]
            else:
                audio_force = [np.sin(time * 0.5), np.cos(time * 0.4)]
        else:
            audio_force = [np.sin(time * 0.5), np.cos(time * 0.4)]
        
        # Scale force by audio energy
        audio_force[0] *= smoothed_rms
        audio_force[1] *= smoothed_rms
        
        self.force_history.append(audio_force)
        if len(self.force_history) > self.max_history:
            self.force_history.pop(0)
        
        # Smooth the force direction over time
        if self.force_history:
            smoothed_force = np.mean(self.force_history, axis=0).tolist()
        else:
            smoothed_force = audio_force
        
        self.prev_rms = smoothed_rms
        self.prev_force = smoothed_force
        
        return smoothed_rms, smoothed_force
    
    def _render_direct(self, time: float, frame: np.ndarray) -> np.ndarray:
        rms, audio_force = self.get_audio_forces(time)
        
        beat_force = 1.0 if self.audio.is_beat_at_time(time, threshold=0.05) else 0.0
        
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
        
        spawn_rate = self.particles_config.get('spawn_rate', 0.3)
        
        if current_count < target_count:
            # Spawn particles gradually, not all at once
            particles_needed = target_count - current_count
            particles_to_spawn = max(1, min(int(particles_needed * spawn_rate), 5))
            
            for _ in range(particles_to_spawn):
                self.particles.append(Particle(self.width, self.height, self.config, time))
        
        return frame

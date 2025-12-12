import argparse
import os
import sys
from pathlib import Path

from audio_visualizer.config_loader import ConfigLoader, ConfigError
from audio_visualizer.audio_processor import AudioProcessor
from audio_visualizer.visualizer_factory import VisualizerFactory
from audio_visualizer.video_renderer import VideoRenderer


def cli():
    parser = argparse.ArgumentParser(
        description='Audio Visualizer - create visualizations for audio files'
    )
    parser.add_argument('audio_file', help='Path to audio file')
    parser.add_argument('-o', '--output', default='output.mp4', 
                       help='Path for output video file')
    parser.add_argument('-c', '--config', default=None,
                       help='Path to YAML configuration file')
    parser.add_argument('--width', type=int, help='Video width')
    parser.add_argument('--height', type=int, help='Video height')
    parser.add_argument('--fps', type=int, help='Video FPS')
    parser.add_argument('--debug', action='store_true', 
                       help='Enable debug mode')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.audio_file):
        print(f"Error: File {args.audio_file} not found!")
        sys.exit(1)
    
    try:
        config_loader = ConfigLoader(args.config)
        config = config_loader.config
        
        if args.width:
            config['video']['width'] = args.width
        if args.height:
            config['video']['height'] = args.height
        if args.fps:
            config['video']['fps'] = args.fps
        
        if args.debug:
            config['debug'] = True
        
        print("=" * 60)
        print("AUDIO VISUALIZER PIPELINE")
        print("=" * 60)
        print(f"Audio file: {args.audio_file}")
        print(f"Output file: {args.output}")
        print(f"Resolution: {config['video']['width']}x{config['video']['height']}")
        print(f"FPS: {config['video']['fps']}")
        
        if 'pipeline' in config:
            pipeline_order = config['pipeline'].get('order', [])
            print(f"Layer order: {', '.join(pipeline_order)}")
        
        print("=" * 60)
        
        audio_proc = AudioProcessor(config)
        audio_proc.load_audio(args.audio_file)
        
        visualizer = VisualizerFactory.create('pipeline', config, audio_proc)
        
        renderer = VideoRenderer(config)
        renderer.render(audio_proc, visualizer, args.output)
        
        print("\n" + "=" * 60)
        print("VISUALIZATION CREATED!")
        print("=" * 60)
        print(f"File: {args.output}")
        
        if os.path.exists(args.output):
            size_mb = os.path.getsize(args.output) / (1024 * 1024)
            print(f"Size: {size_mb:.2f} MB")
        
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"\nConfiguration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nRendering interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nCritical error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
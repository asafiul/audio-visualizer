import click
import os
from pathlib import Path

@click.command()
@click.option('--config', '-c', required=True, 
              help='Path to json config')
@click.option('--input', '-i', help='Path to input audio')
@click.option('--output', '-o', help='Path to output video')
def cli(config, input, output):
    try:
        # TODO(asafiul) BuildConfig and update by options
        print(config, input, output)
        pass
    except Exception as e:
        click.echo(f"❌ Ошибка: {e}")
        raise
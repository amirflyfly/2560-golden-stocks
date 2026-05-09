from pathlib import Path
import runpy

TARGET = Path(__file__).resolve().parent / 'scripts' / 'maintenance' / 'ensure_extended_schema.py'


if __name__ == '__main__':
    runpy.run_path(str(TARGET), run_name='__main__')

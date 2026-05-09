from pathlib import Path
import runpy

TARGET = Path(__file__).resolve().parent / 'scripts' / 'maintenance' / 'import_picks_csv.py'


if __name__ == '__main__':
    runpy.run_path(str(TARGET), run_name='__main__')

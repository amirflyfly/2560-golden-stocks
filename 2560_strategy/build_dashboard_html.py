from pathlib import Path
import runpy

TARGET = Path(__file__).resolve().parent / 'scripts' / 'maintenance' / 'build_dashboard_html.py'


if __name__ == '__main__':
    runpy.run_path(str(TARGET), run_name='__main__')

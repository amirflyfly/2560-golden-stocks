import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import werkzeug_patch  # noqa: F401
except ImportError:
    # Compatibility patch is optional; startup must not write source files.
    pass

from backend import create_app
from backend.app_config import PORT

app = create_app()

if __name__ == '__main__':
    debug = os.getenv('APP_DEBUG', '0') == '1'
    print(f'Flask server running on http://0.0.0.0:{PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=debug)

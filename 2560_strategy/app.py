from backend import create_app
from backend.app_config import PORT

app = create_app()

if __name__ == '__main__':
    print(f'🚀 Flask server running on http://0.0.0.0:{PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=True)

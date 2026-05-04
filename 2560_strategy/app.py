import sys
import os

# 添加Werkzeug补丁
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import werkzeug_patch
except ImportError:
    # 如果补丁文件不存在，创建一个
    patch_content = '''
import werkzeug.urls

# 为Werkzeug 3.1.8添加url_quote函数
if not hasattr(werkzeug.urls, 'url_quote'):
    from urllib.parse import quote
    werkzeug.urls.url_quote = quote
'''
    with open('werkzeug_patch.py', 'w') as f:
        f.write(patch_content)
    import werkzeug_patch

from backend import create_app
from backend.app_config import PORT

app = create_app()

if __name__ == '__main__':
    print(f'🚀 Flask server running on http://0.0.0.0:{PORT}')
    app.run(host='0.0.0.0', port=PORT, debug=True)

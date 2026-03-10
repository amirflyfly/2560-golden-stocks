"""Application-level configuration constants.

Keep this module side-effect free.
"""

PORT = 8765
PAGE_SIZE = 20
COOKIE_NAME = 'promo_panel_auth'

REVIEW_STATUS_OPTIONS = ['未复盘', '值得复讲', '逻辑一般', '不建议再提']
RESULT_GRADE_OPTIONS = ['S', 'A', 'B', 'C', '待定']
DEAL_STATUS_OPTIONS = ['未成交', '已咨询', '已成交', '待跟进']
SPREAD_OPTIONS = ['否', '是']


# data/ directory (relative to project dir)
DATA_DIR_NAME = 'data'

# backup settings
BACKUP_RETENTION = 30

# HMAC key for backup meta signing (optional but recommended)
BACKUP_HMAC_KEY_PATH = 'data/backup_hmac_key.txt'

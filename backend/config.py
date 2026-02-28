"""
QA Management Platform 配置管理模組
包含應用程式的所有配置項目和預設值
"""

import os

# ========== 基本配置項目 ==========

# API 檢查相關配置
CHECK_INTERVAL = int(os.environ.get('CHECK_INTERVAL', 60))  # 檢查間隔（秒）
MAX_ERROR_COUNT = int(os.environ.get('MAX_ERROR_COUNT', 3))  # 連續錯誤次數閾值
REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', 10))  # HTTP 請求超時時間（秒）

# ========== 應用程式配置 ==========

# Flask 應用配置
SECRET_KEY = os.environ.get('SECRET_KEY', '')
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
AUTO_RELOAD = os.environ.get('AUTO_RELOAD', 'True').lower() == 'true'

# 網路配置
DEFAULT_HOST = os.environ.get('HOST', '0.0.0.0')
DEFAULT_PORT = int(os.environ.get('PORT', 5001))

# ========== 檔案和資料庫配置 ==========

# 資料目錄
DATA_DIR = os.environ.get('DATA_DIR', 'data')

# 資料庫配置
DATABASE_FILE = os.environ.get('DATABASE_FILE', 'data/api_monitor.db')

# 向後兼容的舊檔案
DATA_FILE = 'data/apis.json'  # 向後兼容，實際使用 SQLite

# 日誌配置
LOG_FILE = os.environ.get('LOG_FILE', 'app.log')
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
ENABLE_LOGGING = os.environ.get('ENABLE_LOGGING', 'True').lower() == 'true'

# ========== HTTP 和 API 配置 ==========

# 允許的 HTTP 方法
ALLOWED_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']

# 成功的狀態碼
SUCCESS_STATUS_CODES = [200, 201, 202, 204]

# 預設標頭
DEFAULT_HEADERS = {
    'User-Agent': 'QA-Management-Platform/1.0',
    'Accept': 'application/json',
    'Content-Type': 'application/json'
}

# ========== 系統配置 ==========

# 時區設定
TIMEZONE = os.environ.get('TIMEZONE', 'Asia/Taipei')

# 編碼設定
ENCODING = os.environ.get('ENCODING', 'utf-8')

# ========== 配置驗證函數 ==========

def validate_config(config_dict=None):
    """
    驗證配置的有效性
    
    Args:
        config_dict: 配置字典，如果為None則驗證當前模組配置
    
    Returns:
        bool: 配置是否有效
    """
    if config_dict is None:
        # 驗證當前模組配置
        config_dict = {
            'CHECK_INTERVAL': CHECK_INTERVAL,
            'MAX_ERROR_COUNT': MAX_ERROR_COUNT,
            'REQUEST_TIMEOUT': REQUEST_TIMEOUT
        }
    
    try:
        # 檢查必要項目
        if 'CHECK_INTERVAL' in config_dict:
            interval = config_dict['CHECK_INTERVAL']
            if not isinstance(interval, int) or interval <= 0 or interval > 86400:
                return False
        
        if 'MAX_ERROR_COUNT' in config_dict:
            count = config_dict['MAX_ERROR_COUNT']
            if not isinstance(count, int) or count <= 0 or count > 100:
                return False
        
        if 'REQUEST_TIMEOUT' in config_dict:
            timeout = config_dict['REQUEST_TIMEOUT']
            if not isinstance(timeout, (int, float)) or timeout <= 0 or timeout > 300:
                return False
        
        return True
        
    except Exception:
        return False

# ========== 向後兼容的 Config 類 ==========

class Config:
    """向後兼容的配置類"""
    SECRET_KEY = SECRET_KEY
    DATA_FILE = DATA_FILE
    DATABASE_FILE = DATABASE_FILE
    CHECK_INTERVAL = CHECK_INTERVAL
    MAX_ERROR_COUNT = MAX_ERROR_COUNT
    REQUEST_TIMEOUT = REQUEST_TIMEOUT
    DEBUG = DEBUG
    DEFAULT_HOST = DEFAULT_HOST
    DEFAULT_PORT = DEFAULT_PORT
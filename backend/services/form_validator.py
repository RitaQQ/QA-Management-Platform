import json
from typing import Tuple, List, Dict, Optional

class FormValidator:
    """表單驗證器"""
    
    def validate_api_form(self, form_data: Dict, data_manager, exclude_api_id: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        驗證 API 表單數據
        
        Args:
            form_data: 表單數據字典
            data_manager: 數據管理器實例
            exclude_api_id: 排除的 API ID（用於編輯時）
        
        Returns:
            Tuple[bool, List[str]]: (是否有效, 錯誤訊息列表)
        """
        errors = []
        
        # 基本欄位驗證
        if not form_data.get('name'):
            errors.append('請填寫 API 名稱')
        
        if not form_data.get('url'):
            errors.append('請填寫 API URL')
        
        # URL 重複檢查
        if form_data.get('url'):
            existing_apis = data_manager.load_apis()
            for api in existing_apis:
                if api.get('url') == form_data['url'] and api.get('id') != exclude_api_id:
                    if exclude_api_id:
                        errors.append('這個 URL 已經存在於其他 API 中')
                    else:
                        errors.append('這個 URL 已經存在於監控清單中')
                    break
        
        # Request Body 格式驗證
        if form_data.get('request_body') and form_data.get('method') in ['POST', 'PUT', 'PATCH']:
            try:
                json.loads(form_data['request_body'])
            except json.JSONDecodeError:
                errors.append('Request Body 必須是有效的 JSON 格式')
        
        # 壓力測試參數驗證
        try:
            concurrent_requests = form_data.get('concurrent_requests', 1)
            if not (1 <= concurrent_requests <= 100):
                errors.append('併發請求數必須在 1-100 之間')
        except (ValueError, TypeError):
            errors.append('併發請求數必須是有效的數字')
        
        try:
            duration_seconds = form_data.get('duration_seconds', 10)
            if not (5 <= duration_seconds <= 300):
                errors.append('持續時間必須在 5-300 秒之間')
        except (ValueError, TypeError):
            errors.append('持續時間必須是有效的數字')
        
        try:
            interval_seconds = form_data.get('interval_seconds', 1.0)
            if not (0.1 <= interval_seconds <= 10):
                errors.append('請求間隔必須在 0.1-10 秒之間')
        except (ValueError, TypeError):
            errors.append('請求間隔必須是有效的數字')
        
        return len(errors) == 0, errors
    
    def validate_user_form(self, form_data: Dict, user_manager, exclude_user_id: Optional[str] = None) -> Tuple[bool, List[str]]:
        """
        驗證用戶表單數據
        
        Args:
            form_data: 表單數據字典
            user_manager: 用戶管理器實例
            exclude_user_id: 排除的用戶 ID（用於編輯時）
        
        Returns:
            Tuple[bool, List[str]]: (是否有效, 錯誤訊息列表)
        """
        errors = []
        
        # 基本欄位驗證
        if not form_data.get('username'):
            errors.append('請填寫用戶名')
        elif len(form_data['username']) < 3:
            errors.append('用戶名至少需要 3 個字符')
        
        if not form_data.get('password') and not exclude_user_id:  # 編輯時可以不填密碼
            errors.append('請填寫密碼')
        elif form_data.get('password') and len(form_data['password']) < 6:
            errors.append('密碼至少需要 6 個字符')
        
        # Email 格式驗證（如果有填寫）
        if form_data.get('email'):
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, form_data['email']):
                errors.append('請填寫有效的電子郵件地址')
        
        # 角色驗證
        valid_roles = ['admin', 'user']
        if form_data.get('role') not in valid_roles:
            errors.append(f'角色必須是以下之一: {", ".join(valid_roles)}')
        
        # 用戶名重複檢查
        if form_data.get('username'):
            existing_user = user_manager.get_user_by_username(form_data['username'])
            if existing_user and existing_user.get('id') != exclude_user_id:
                errors.append('這個用戶名已經存在')
        
        return len(errors) == 0, errors
    
    def validate_required_fields(self, form_data: Dict, required_fields: List[str]) -> Tuple[bool, List[str]]:
        """
        驗證必填欄位
        
        Args:
            form_data: 表單數據字典
            required_fields: 必填欄位列表
        
        Returns:
            Tuple[bool, List[str]]: (是否有效, 錯誤訊息列表)
        """
        errors = []
        
        for field in required_fields:
            if not form_data.get(field):
                field_names = {
                    'name': '名稱',
                    'url': 'URL',
                    'username': '用戶名',
                    'password': '密碼',
                    'email': '電子郵件',
                    'role': '角色'
                }
                field_display_name = field_names.get(field, field)
                errors.append(f'請填寫{field_display_name}')
        
        return len(errors) == 0, errors
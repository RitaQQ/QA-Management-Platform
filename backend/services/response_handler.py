from flask import flash, redirect, url_for, jsonify
from typing import Dict, Any, Optional, Union

class ResponseHandler:
    """統一回應處理器"""
    
    @staticmethod
    def success_response(message: str, redirect_url: str = None, data: Dict = None) -> Union[str, Dict]:
        """
        成功回應處理
        
        Args:
            message: 成功訊息
            redirect_url: 重定向 URL
            data: 額外數據
        
        Returns:
            重定向響應或 JSON 響應
        """
        flash(message, 'success')
        
        if redirect_url:
            return redirect(redirect_url)
        
        response = {'status': 'success', 'message': message}
        if data:
            response['data'] = data
        
        return jsonify(response)
    
    @staticmethod
    def error_response(message: str, redirect_url: str = None, status_code: int = 400, data: Dict = None) -> Union[str, Dict]:
        """
        錯誤回應處理
        
        Args:
            message: 錯誤訊息
            redirect_url: 重定向 URL
            status_code: HTTP 狀態碼
            data: 額外數據
        
        Returns:
            重定向響應或 JSON 響應
        """
        flash(message, 'error')
        
        if redirect_url:
            return redirect(redirect_url)
        
        response = {'status': 'error', 'message': message}
        if data:
            response['data'] = data
        
        return jsonify(response), status_code
    
    @staticmethod
    def validation_error_response(errors: list, redirect_url: str = None) -> Union[str, Dict]:
        """
        驗證錯誤回應處理
        
        Args:
            errors: 錯誤訊息列表
            redirect_url: 重定向 URL
        
        Returns:
            重定向響應或 JSON 響應
        """
        for error in errors:
            flash(error, 'error')
        
        if redirect_url:
            return redirect(redirect_url)
        
        return jsonify({
            'status': 'validation_error',
            'errors': errors
        }), 400
    
    @staticmethod
    def loading_response(redirect_url: str, delay: int = 2000) -> str:
        """
        載入頁面回應
        
        Args:
            redirect_url: 重定向 URL
            delay: 延遲時間（毫秒）
        
        Returns:
            重定向響應
        """
        return redirect(url_for('main.loading') + f'?redirect={redirect_url}&delay={delay}')
    
    @staticmethod
    def api_response(data: Any, status: str = 'success', message: str = None) -> Dict:
        """
        API JSON 回應
        
        Args:
            data: 響應數據
            status: 狀態
            message: 訊息
        
        Returns:
            JSON 響應
        """
        response = {
            'status': status,
            'data': data
        }
        
        if message:
            response['message'] = message
        
        return jsonify(response)
    
    @staticmethod
    def handle_exception(e: Exception, operation: str, redirect_url: str = None) -> Union[str, Dict]:
        """
        例外處理
        
        Args:
            e: 例外對象
            operation: 操作名稱
            redirect_url: 重定向 URL
        
        Returns:
            錯誤回應
        """
        error_message = f'{operation}時發生錯誤: {str(e)}'
        print(f"Exception in {operation}: {e}")  # Log to console
        
        return ResponseHandler.error_response(
            error_message,
            redirect_url,
            status_code=500
        )
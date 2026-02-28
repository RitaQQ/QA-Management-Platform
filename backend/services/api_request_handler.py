import requests
import time
import json
from typing import Tuple, Dict, Any
from config import Config

class APIRequestHandler:
    """API 請求處理器"""
    
    def __init__(self):
        self.config = Config()
    
    def make_request(self, api: Dict) -> Tuple[str, float, str, str]:
        """
        發送 API 請求
        
        Args:
            api: API 配置字典
        
        Returns:
            Tuple[str, float, str, str]: (status, response_time, error_message, response_data)
        """
        try:
            start_time = time.time()
            method = api.get('method', 'GET').upper()
            headers = {'User-Agent': 'API-Monitor/1.0'}
            
            # 根據不同的 HTTP 方法發送請求
            response = self._send_http_request(api, method, headers)
            response_time = time.time() - start_time
            
            # 處理回應
            response_data = self._process_response(response)
            
            if 200 <= response.status_code < 300:
                return "healthy", response_time, None, response_data
            else:
                return "unhealthy", response_time, f"HTTP {response.status_code}", response_data
                
        except requests.exceptions.Timeout:
            return "unhealthy", self.config.REQUEST_TIMEOUT, "請求超時", None
        except requests.exceptions.ConnectionError:
            return "unhealthy", 0, "連線失敗", None
        except requests.exceptions.RequestException as e:
            return "unhealthy", 0, f"請求錯誤: {str(e)}", None
        except Exception as e:
            return "unhealthy", 0, f"未知錯誤: {str(e)}", None
    
    def _send_http_request(self, api: Dict, method: str, headers: Dict) -> requests.Response:
        """發送 HTTP 請求"""
        url = api['url']
        timeout = self.config.REQUEST_TIMEOUT
        
        if method == 'GET':
            return requests.get(url, timeout=timeout, headers=headers)
        
        elif method == 'POST':
            return self._send_post_request(api, headers)
        
        elif method == 'PUT':
            return requests.put(url, timeout=timeout, headers=headers)
        
        elif method == 'DELETE':
            return requests.delete(url, timeout=timeout, headers=headers)
        
        else:
            raise ValueError(f"不支援的 HTTP 方法: {method}")
    
    def _send_post_request(self, api: Dict, headers: Dict) -> requests.Response:
        """發送 POST 請求"""
        url = api['url']
        timeout = self.config.REQUEST_TIMEOUT
        headers['Content-Type'] = 'application/json'
        
        # 檢查是否有自訂的 request body
        if api.get('request_body'):
            payload = self._parse_request_body(api['request_body'])
            if isinstance(payload, str):
                # 如果是字符串，使用 data 參數
                return requests.post(url, data=payload, timeout=timeout, headers=headers)
            else:
                # 如果是字典，使用 json 參數
                return requests.post(url, json=payload, timeout=timeout, headers=headers)
        
        else:
            payload = self._create_default_payload()
        
        return requests.post(url, json=payload, timeout=timeout, headers=headers)
    
    def _parse_request_body(self, request_body: str) -> Any:
        """解析請求主體"""
        try:
            payload = json.loads(request_body)
            
            # 如果包含時間戳變數，動態替換
            if isinstance(payload, dict):
                self._update_timestamps(payload)
            
            return payload
            
        except json.JSONDecodeError:
            # 如果不是有效的 JSON，使用原始字串
            return request_body
    
    def _update_timestamps(self, obj: Any) -> None:
        """遞歸更新時間戳"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == 'ts' and (value == '{{timestamp}}' or value == 1569221884613):
                    obj[key] = int(time.time() * 1000)
                elif isinstance(value, (dict, list)):
                    self._update_timestamps(value)
        elif isinstance(obj, list):
            for item in obj:
                self._update_timestamps(item)
    
    def _create_default_payload(self) -> Dict:
        """創建預設測試 payload"""
        return {
            "test": True,
            "timestamp": time.time()
        }
    
    def _process_response(self, response: requests.Response) -> str:
        """處理 API 回應"""
        try:
            # 限制回應內容長度以避免記憶體問題
            response_text = response.text[:2000] if response.text else ""
            
            # 嘗試格式化 JSON 回應
            if response.headers.get('content-type', '').startswith('application/json'):
                try:
                    response_data = json.dumps(
                        json.loads(response_text), 
                        indent=2, 
                        ensure_ascii=False
                    )
                    return response_data
                except json.JSONDecodeError:
                    return response_text
            else:
                return response_text
                
        except Exception:
            return f"狀態碼: {response.status_code}"
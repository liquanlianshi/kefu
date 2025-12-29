import time
import os
import re
import sys

import requests
from loguru import logger
from utils.xianyu_utils import generate_sign


class XianyuApis:
    def __init__(self):
        self.url = 'https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/'
        self.session = requests.Session()
        self.session.headers.update({
            'accept': 'application/json',
            'accept-language': 'zh-CN,zh;q=0.9',
            'cache-control': 'no-cache',
            'origin': 'https://www.goofish.com',
            'pragma': 'no-cache',
            'priority': 'u=1, i',
            'referer': 'https://www.goofish.com/',
            'sec-ch-ua': '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        })
        
    def clear_duplicate_cookies(self):
        """清理重复的cookies"""
        # 创建一个新的CookieJar
        new_jar = requests.cookies.RequestsCookieJar()
        
        # 记录已经添加过的cookie名称
        added_cookies = set()
        
        # 按照cookies列表的逆序遍历（最新的通常在后面）
        cookie_list = list(self.session.cookies)
        cookie_list.reverse()
        
        for cookie in cookie_list:
            # 如果这个cookie名称还没有添加过，就添加到新jar中
            if cookie.name not in added_cookies:
                new_jar.set_cookie(cookie)
                added_cookies.add(cookie.name)
                
        # 替换session的cookies
        self.session.cookies = new_jar
        
        # 更新完cookies后，更新.env文件
        self.update_env_cookies()
        
    def update_env_cookies(self):
        """更新.env文件中的COOKIES_STR"""
        try:
            # 获取当前cookies的字符串形式
            cookie_str = '; '.join([f"{cookie.name}={cookie.value}" for cookie in self.session.cookies])
            
            # 读取.env文件
            env_path = os.path.join(os.getcwd(), '.env')
            if not os.path.exists(env_path):
                logger.warning(".env文件不存在，无法更新COOKIES_STR")
                return
                
            with open(env_path, 'r', encoding='utf-8') as f:
                env_content = f.read()
                
            # 使用正则表达式替换COOKIES_STR的值
            if 'COOKIES_STR=' in env_content:
                new_env_content = re.sub(
                    r'COOKIES_STR=.*', 
                    f'COOKIES_STR={cookie_str}',
                    env_content
                )
                
                # 写回.env文件
                with open(env_path, 'w', encoding='utf-8') as f:
                    f.write(new_env_content)
                    
                logger.debug("已更新.env文件中的COOKIES_STR")
            else:
                logger.warning(".env文件中未找到COOKIES_STR配置项")
        except Exception as e:
            logger.warning(f"更新.env文件失败: {str(e)}")
        
    def hasLogin(self, retry_count=0):
        """调用hasLogin.do接口进行登录状态检查"""
        if retry_count >= 2:
            logger.error("Login检查失败，重试次数过多")
            return False
            
        try:
            url = 'https://passport.goofish.com/newlogin/hasLogin.do'
            params = {
                'appName': 'xianyu',
                'fromSite': '77'
            }
            data = {
                'hid': self.session.cookies.get('unb', ''),
                'ltl': 'true',
                'appName': 'xianyu',
                'appEntrance': 'web',
                '_csrf_token': self.session.cookies.get('XSRF-TOKEN', ''),
                'umidToken': '',
                'hsiz': self.session.cookies.get('cookie2', ''),
                'bizParams': 'taobaoBizLoginFrom=web',
                'mainPage': 'false',
                'isMobile': 'false',
                'lang': 'zh_CN',
                'returnUrl': '',
                'fromSite': '77',
                'isIframe': 'true',
                'documentReferer': 'https://www.goofish.com/',
                'defaultView': 'hasLogin',
                'umidTag': 'SERVER',
                'deviceId': self.session.cookies.get('cna', '')
            }
            
            response = self.session.post(url, params=params, data=data)
            res_json = response.json()
            
            if res_json.get('content', {}).get('success'):
                logger.debug("Login成功")
                # 清理和更新cookies
                self.clear_duplicate_cookies()
                return True
            else:
                logger.warning(f"Login失败: {res_json}")
                time.sleep(0.5)
                return self.hasLogin(retry_count + 1)
                
        except Exception as e:
            logger.error(f"Login请求异常: {str(e)}")
            time.sleep(0.5)
            return self.hasLogin(retry_count + 1)

    def get_token(self, device_id, retry_count=0):
        """
        获取token（增加最大重试次数与风控退避，避免递归死循环）
        
        Args:
            device_id: 设备ID
            retry_count: 起始重试次数（内部会继续累加）
        """
        # 最大重试次数（允许 0..max_retries 共 max_retries+1 次尝试）
        try:
            max_retries = int(os.getenv("TOKEN_MAX_RETRIES", "3"))
        except Exception:
            max_retries = 3
        max_retries = max(0, max_retries)
        
        # 失败到一定次数后尝试重新登录（避免每次都触发 hasLogin 导致无限循环）
        try:
            relogin_after = int(os.getenv("TOKEN_RELOGIN_AFTER", "2"))
        except Exception:
            relogin_after = 2
        relogin_after = max(0, relogin_after)
        
        try:
            max_relogin = int(os.getenv("TOKEN_MAX_RELOGIN", "1"))
        except Exception:
            max_relogin = 1
        max_relogin = max(0, max_relogin)
        
        relogin_count = 0
        attempt = max(0, int(retry_count or 0))
        
        while attempt <= max_retries:
            params = {
                'jsv': '2.7.2',
                'appKey': '34839810',
                't': str(int(time.time()) * 1000),
                'sign': '',
                'v': '1.0',
                'type': 'originaljson',
                'accountSite': 'xianyu',
                'dataType': 'json',
                'timeout': '20000',
                'api': 'mtop.taobao.idlemessage.pc.login.token',
                'sessionOption': 'AutoLoginOnly',
                'spm_cnt': 'a21ybx.im.0.0',
            }
            data_val = '{"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"' + device_id + '"}'
            data = {
                'data': data_val,
            }
            
            # 简单获取token，信任cookies已清理干净
            token = self.session.cookies.get('_m_h5_tk', '').split('_')[0]
            if not token:
                logger.warning("Cookie中缺少 _m_h5_tk，可能未登录或Cookie已失效")
            
            sign = generate_sign(params['t'], token, data_val)
            params['sign'] = sign
            
            try:
                response = self.session.post(
                    'https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/',
                    params=params,
                    data=data,
                )
                
                response_text = response.text or ""
                # 风控：RGV587_ERROR（按阶梯式退避等待后再试）
                if "RGV587_ERROR" in response_text:
                    wait_seconds = attempt * 5 + 5
                    logger.warning(f"触发风控(RGV587_ERROR)，等待 {wait_seconds} 秒后重试... (attempt={attempt}/{max_retries})")
                    time.sleep(wait_seconds)
                    attempt += 1
                    continue
                
                try:
                    res_json = response.json()
                except Exception as e:
                    logger.error(f"Token API响应非JSON: {str(e)}")
                    time.sleep(0.5)
                    attempt += 1
                    continue
                
                if not isinstance(res_json, dict):
                    logger.error(f"Token API返回格式异常: {res_json}")
                    time.sleep(0.5)
                    attempt += 1
                    continue
                
                ret_value = res_json.get('ret', [])
                
                # 检查ret是否包含成功信息
                if not any('SUCCESS::调用成功' in str(ret) for ret in ret_value):
                    logger.warning(f"Token API调用失败，错误信息: {ret_value}")
                    
                    # 处理响应中的Set-Cookie
                    if 'Set-Cookie' in response.headers:
                        logger.debug("检测到Set-Cookie，更新cookie")  # 降级为DEBUG并简化
                        self.clear_duplicate_cookies()
                    
                    # ret中也可能带风控标识
                    if any('RGV587_ERROR' in str(ret) for ret in ret_value):
                        wait_seconds = attempt * 5 + 5
                        logger.warning(f"触发风控(RGV587_ERROR)，等待 {wait_seconds} 秒后重试... (attempt={attempt}/{max_retries})")
                        time.sleep(wait_seconds)
                        attempt += 1
                        continue
                    
                    # 失败到一定次数后尝试重新登录（仅有限次数）
                    if attempt >= relogin_after and relogin_count < max_relogin:
                        logger.warning("获取token失败，尝试重新登陆")
                        if self.hasLogin():
                            relogin_count += 1
                            logger.info("重新登录成功，准备重试获取token")
                            time.sleep(0.5)
                            attempt += 1
                            continue
                        else:
                            logger.error("重新登录失败，Cookie已失效")
                            logger.error("🔴 程序即将退出，请更新.env文件中的COOKIES_STR后重新启动")
                            sys.exit(1)
                    
                    time.sleep(0.5)
                    attempt += 1
                    continue
                
                logger.info("Token获取成功")
                return res_json
                
            except Exception as e:
                logger.error(f"Token API请求异常: {str(e)}")
                time.sleep(0.5)
                attempt += 1
                continue
        
        logger.error("超过最大重试次数，请手动处理风控或更换IP")
        return None

    def get_item_info(self, item_id, retry_count=0):
        """获取商品信息，自动处理token失效的情况"""
        if retry_count >= 3:  # 最多重试3次
            logger.error("获取商品信息失败，重试次数过多")
            return {"error": "获取商品信息失败，重试次数过多"}
            
        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': str(int(time.time()) * 1000),
            'sign': '',
            'v': '1.0',
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': 'mtop.taobao.idle.pc.detail',
            'sessionOption': 'AutoLoginOnly',
            'spm_cnt': 'a21ybx.im.0.0',
        }
        
        data_val = '{"itemId":"' + item_id + '"}'
        data = {
            'data': data_val,
        }
        
        # 简单获取token，信任cookies已清理干净
        token = self.session.cookies.get('_m_h5_tk', '').split('_')[0]
        
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign
        
        try:
            response = self.session.post(
                'https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/', 
                params=params, 
                data=data
            )
            
            res_json = response.json()
            # 检查返回状态
            if isinstance(res_json, dict):
                ret_value = res_json.get('ret', [])
                # 检查ret是否包含成功信息
                if not any('SUCCESS::调用成功' in ret for ret in ret_value):
                    logger.warning(f"商品信息API调用失败，错误信息: {ret_value}")
                    # 处理响应中的Set-Cookie
                    if 'Set-Cookie' in response.headers:
                        logger.debug("检测到Set-Cookie，更新cookie")
                        self.clear_duplicate_cookies()
                    time.sleep(0.5)
                    return self.get_item_info(item_id, retry_count + 1)
                else:
                    logger.debug(f"商品信息获取成功: {item_id}")
                    return res_json
            else:
                logger.error(f"商品信息API返回格式异常: {res_json}")
                return self.get_item_info(item_id, retry_count + 1)
                
        except Exception as e:
            logger.error(f"商品信息API请求异常: {str(e)}")
            time.sleep(0.5)
            return self.get_item_info(item_id, retry_count + 1)

# encoding: utf-8
# @Time   : 2024/2/17
# @Author : Spike
# @Descr   :
import re
import requests
import httpx
from fastapi import Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from common import toolbox

cancel_verification, auth_url, auth_cookie_tag, auth_func_based, routing_address, favicon_path, redirect_address = (
    toolbox.get_conf('cancel_verification', 'auth_url', 'auth_cookie_tag',
                     'auth_func_based', 'routing_address', 'favicon_path', 'redirect_address'))


def check_cookie(cookie):
    header = {
        'Cookie': f"{auth_cookie_tag}={cookie}",
        "Origin": ''
    }
    try:
        resp = requests.get(url=auth_url, headers=header, verify=False).json()
        user = auth_func_based(resp)
    except:
        user = cancel_verification
    if not user:
        return user
    else:
        return user


async def get_favicon():
    return RedirectResponse(url=f'/spike/file={favicon_path}')


async def check_authentication(request: Request, call_next):
    pattern = re.compile(r".*\/users_private\/.*")
    if pattern.match(request.url.path):
        if toolbox.get_conf('AUTHENTICATION') != 'SQL':
            if request.client.host not in request.url.path:
                return JSONResponse(content={'Error': "You can't download other people's files."})
        else:
            async with httpx.AsyncClient() as client:
                res = await client.get(str(request.base_url) + 'spike/user', cookies=request.cookies)
                res_user = res.text[1:-1]
            if res_user not in request.url.path:
                return JSONResponse(content={'Error': "You can't download other people's files."})
    cookie = request.cookies.get(f'{auth_cookie_tag}', '')
    user = check_cookie(cookie)
    if not user:
        new_website_url = redirect_address  # 新网站的URL
        return RedirectResponse(new_website_url)
    return await call_next(request)


async def homepage(request: Request):
    cookie = request.cookies.get(f'{auth_cookie_tag}', '')
    user = check_cookie(cookie)
    if user:
        return RedirectResponse(url='/spike/')
    else:
        new_website_url = redirect_address  # 新网站的URL
        return RedirectResponse(new_website_url)


async def logout():
    response = RedirectResponse(url='/', status_code=status.HTTP_302_FOUND)
    response.delete_cookie('access-token')
    response.delete_cookie('access-token-unsecure')
    return response

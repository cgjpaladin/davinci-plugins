"""
火山引擎 VOD 精细化字幕擦除 - 按官方签名规范实现
参考: https://github.com/volcengine/volc-openapi-demos/blob/main/signature/python/sign.py

关键点:
- Host: vod.volcengineapi.com (不是 open.volcengineapi.com)
- 算法: HMAC-SHA256 (不是 AWS4-HMAC-SHA256)
- Credential scope: YYYYMMDD/cn-north-1/vod/request (不是 aws4_request)
- Content-Type: application/json
"""

import datetime
import hashlib
import hmac
import json
from urllib.parse import quote
import requests

# ========== 配置 ==========
AK = "AKLTOTNmZDc4NDZiZDgwNDY5ODllNDhjZjNjMTgxMDRjNWI"
SK = "Tm1ZeE1EWmlOelprTlRFM05HTm1aRGxtWlRWaU1EZGhaamRsWVdFNE9Uaw=="

SERVICE = "vod"
VERSION = "2025-01-01"
REGION = "cn-north-1"
HOST = "vod.volcengineapi.com"
CONTENT_TYPE = "application/json"

# 已上传的视频 Vid
VIDEO_VID = "v02cd3g10068d7rroniljhtd9qao75v0"


def utc_now():
    """获取UTC时间（兼容Python 3.12+）"""
    from datetime import timezone
    return datetime.datetime.now(timezone.utc)


def norm_query(params):
    """规范化查询字符串，按键名排序并URL编码"""
    query = ""
    for key in sorted(params.keys()):
        if type(params[key]) == list:
            for k in params[key]:
                query = (
                    query + quote(key, safe="-_.~") + "=" + quote(k, safe="-_.~") + "&"
                )
        else:
            query = (
                query
                + quote(key, safe="-_.~")
                + "="
                + quote(params[key], safe="-_.~")
                + "&"
            )
    query = query[:-1]
    return query.replace("+", "%20")


def hmac_sha256(key: bytes, content: str):
    """HMAC-SHA256 签名函数"""
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()


def hash_sha256(content: str):
    """SHA-256 哈希函数"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def sign_and_request(action, body_dict):
    """构造签名并发送请求"""
    now = utc_now()
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_x_date = x_date[:8]

    body = json.dumps(body_dict) if body_dict else ""
    x_content_sha256 = hash_sha256(body)

    # 查询参数
    query_params = {"Action": action, "Version": VERSION}

    # 签名用的 header
    signed_headers_list = ["content-type", "host", "x-content-sha256", "x-date"]
    signed_headers_str = ";".join(signed_headers_list)

    # ========== 构造 Canonical Request ==========
    canonical_request_str = "\n".join(
        [
            "POST",  # HTTP method
            "/",  # Path
            norm_query(query_params),  # Normalized query
            "\n".join(
                [
                    "content-type:" + CONTENT_TYPE,
                    "host:" + HOST,
                    "x-content-sha256:" + x_content_sha256,
                    "x-date:" + x_date,
                ]
            ),
            "",  # Empty line after headers
            signed_headers_str,
            x_content_sha256,
        ]
    )

    print("=" * 60)
    print("Canonical Request:")
    print(canonical_request_str)
    print("=" * 60)

    hashed_canonical_request = hash_sha256(canonical_request_str)

    # ========== 构造 String to Sign ==========
    credential_scope = "/".join([short_x_date, REGION, SERVICE, "request"])
    string_to_sign = "\n".join(
        ["HMAC-SHA256", x_date, credential_scope, hashed_canonical_request]
    )

    print("String to Sign:")
    print(string_to_sign)
    print("=" * 60)

    # ========== 计算签名密钥链 ==========
    k_date = hmac_sha256(SK.encode("utf-8"), short_x_date)
    k_region = hmac_sha256(k_date, REGION)
    k_service = hmac_sha256(k_region, SERVICE)
    k_signing = hmac_sha256(k_service, "request")

    signature = hmac_sha256(k_signing, string_to_sign).hex()

    # ========== 构造 Authorization Header ==========
    authorization = "HMAC-SHA256 Credential={}, SignedHeaders={}, Signature={}".format(
        AK + "/" + credential_scope,
        signed_headers_str,
        signature,
    )

    # ========== 发送请求 ==========
    headers = {
        "Host": HOST,
        "Content-Type": CONTENT_TYPE,
        "X-Content-Sha256": x_content_sha256,
        "X-Date": x_date,
        "Authorization": authorization,
    }

    url = f"https://{HOST}/"
    params = {"Action": action, "Version": VERSION}

    print(f"\n请求 URL: {url}")
    print(f"请求参数: {params}")
    print(f"请求头:")
    for k, v in headers.items():
        print(f"  {k}: {v}")
    print(f"请求体: {body}")
    print("=" * 60)

    resp = requests.request(
        method="POST",
        url=url,
        headers=headers,
        params=params,
        data=body,
    )

    print(f"\n响应状态码: {resp.status_code}")
    print(f"响应头:")
    for k, v in resp.headers.items():
        if k.lower().startswith("x-") or k.lower() in ("server", "content-type"):
            print(f"  {k}: {v}")
    print(f"响应体:")
    try:
        result = resp.json()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except:
        print(resp.text[:2000])

    return resp


# ========== 测试 1: 提交字幕擦除任务（Auto 模式） ==========
def test_start_execution_auto():
    """测试 Auto 模式 - 自动识别并擦除字幕"""
    print("\n" + "🎬" * 20)
    print("测试: StartExecution - Auto 模式字幕擦除")
    print("🎬" * 20 + "\n")

    body = {
        "Input": {
            "Type": "Vid",
            "Vid": VIDEO_VID,
        },
        "Operation": {
            "Type": "Task",
            "Task": {
                "Type": "Erase",
                "Erase": {
                    "Mode": "Auto",
                    "Auto": {
                        "Type": "Subtitle",
                        "SubtitleFilter": {},
                    },
                    "WithEraseInfo": True,
                    "NewVid": True,
                },
            },
        },
    }

    return sign_and_request("StartExecution", body)


# ========== 测试 2: 提交字幕擦除任务（Manual 模式 - 框选） ==========
def test_start_execution_manual():
    """测试 Manual 模式 - 框选字幕区域擦除"""
    print("\n" + "🎯" * 20)
    print("测试: StartExecution - Manual 模式框选擦除")
    print("🎯" * 20 + "\n")

    body = {
        "Input": {
            "Type": "Vid",
            "Vid": VIDEO_VID,
        },
        "Operation": {
            "Type": "Task",
            "Task": {
                "Type": "Erase",
                "Erase": {
                    "Mode": "Manual",
                    "Manual": {
                        "Locations": [
                            {
                                "RatioLocation": {
                                    "TopLeftX": 0.10,
                                    "TopLeftY": 0.85,
                                    "BottomRightX": 0.90,
                                    "BottomRightY": 0.95,
                                }
                            }
                        ]
                    },
                    "WithEraseInfo": True,
                    "NewVid": True,
                },
            },
        },
    }

    return sign_and_request("StartExecution", body)


# ========== 测试 3: 查询任务结果 (GET) ==========
def test_get_execution(run_id):
    """查询任务执行结果 — 文档明确使用 GET，RunId 放 query 参数"""
    print("\n" + "🔍" * 20)
    print(f"测试: GetExecution (GET) - 查询 RunId: {run_id}")
    print("🔍" * 20 + "\n")

    now = utc_now()
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_x_date = x_date[:8]

    body = ""  # GET 无 body
    x_content_sha256 = hash_sha256(body)

    # 查询参数 — RunId 作为 query 参数
    query_params = {"Action": "GetExecution", "Version": VERSION, "RunId": run_id}

    signed_headers_list = ["content-type", "host", "x-content-sha256", "x-date"]
    signed_headers_str = ";".join(signed_headers_list)

    # ========== 构造 Canonical Request ==========
    canonical_request_str = "\n".join(
        [
            "GET",
            "/",
            norm_query(query_params),
            "\n".join(
                [
                    "content-type:" + CONTENT_TYPE,
                    "host:" + HOST,
                    "x-content-sha256:" + x_content_sha256,
                    "x-date:" + x_date,
                ]
            ),
            "",
            signed_headers_str,
            x_content_sha256,
        ]
    )

    print("Canonical Request:")
    print(canonical_request_str)
    print("=" * 60)

    hashed_canonical_request = hash_sha256(canonical_request_str)

    credential_scope = "/".join([short_x_date, REGION, SERVICE, "request"])
    string_to_sign = "\n".join(
        ["HMAC-SHA256", x_date, credential_scope, hashed_canonical_request]
    )

    print("String to Sign:")
    print(string_to_sign)
    print("=" * 60)

    k_date = hmac_sha256(SK.encode("utf-8"), short_x_date)
    k_region = hmac_sha256(k_date, REGION)
    k_service = hmac_sha256(k_region, SERVICE)
    k_signing = hmac_sha256(k_service, "request")

    signature = hmac_sha256(k_signing, string_to_sign).hex()

    authorization = "HMAC-SHA256 Credential={}, SignedHeaders={}, Signature={}".format(
        AK + "/" + credential_scope,
        signed_headers_str,
        signature,
    )

    headers = {
        "Host": HOST,
        "Content-Type": CONTENT_TYPE,
        "X-Content-Sha256": x_content_sha256,
        "X-Date": x_date,
        "Authorization": authorization,
    }

    url = f"https://{HOST}/"
    params = {"Action": "GetExecution", "Version": VERSION, "RunId": run_id}

    print(f"请求 URL: {url}")
    print(f"请求参数: {params}")
    print(f"请求方法: GET")
    print("=" * 60)

    resp = requests.request(
        method="GET",
        url=url,
        headers=headers,
        params=params,
    )

    print(f"\n响应状态码: {resp.status_code}")
    print(f"响应体:")
    try:
        result = resp.json()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except:
        print(resp.text[:2000])

    return resp


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "manual":
        # Manual 模式
        resp = test_start_execution_manual()
    elif len(sys.argv) > 1 and sys.argv[1] == "get":
        # 查询结果
        if len(sys.argv) > 2:
            test_get_execution(sys.argv[2])
        else:
            print("用法: python test_vod_official.py get <RunId>")
    else:
        # 默认 Auto 模式
        resp = test_start_execution_auto()
        # 如果成功获取 RunId，自动查询结果
        if resp and resp.status_code == 200:
            try:
                result = resp.json()
                run_id = result.get("Result", {}).get("RunId")
                if run_id:
                    print(f"\n✅ 获取到 RunId: {run_id}")
                    print("提示: 使用以下命令查询结果:")
                    print(f"  python test_vod_official.py get {run_id}")
            except:
                pass

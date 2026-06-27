#!/usr/bin/env python3
"""阿里云 OSS 快速探活 — 用无痕 adapter 的 _oss_put 测上传链路

用法: python3 tools/oss_connectivity_check.py [size_mb=2]
"""
import sys, os, time, tempfile
sys.path.insert(0, 'shared')
sys.path.insert(0, 'AI去字幕')

def main():
    size_mb = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    from adapters.wuhenai_v2 import WuhenAIV21Adapter

    import config  # 自动加载 .env
    adapter = WuhenAIV21Adapter({
        'api_key': config.WUHENAI_V2_API_KEY,
        'oss_access_key_id': config.OSS_ACCESS_KEY_ID,
        'oss_access_key_secret': config.OSS_ACCESS_KEY_SECRET,
        'oss_bucket': config.OSS_BUCKET,
        'oss_region': config.OSS_REGION,
        'api_endpoint': 'https://api.wuhenai.com',
    })

    print(f"Bucket: {config.OSS_BUCKET}.oss-{config.OSS_REGION}.aliyuncs.com")
    print(f"AK ID: {config.OSS_ACCESS_KEY_ID[:8]}...{config.OSS_ACCESS_KEY_ID[-4:]}")

    # API 探活
    print("\n═══ 无痕API ═══")
    try:
        h = adapter.check_health()
        print(f"  {'✅' if h else '❌'}")
    except Exception as e:
        print(f"  ❌ {e}")

    # OSS 探活
    print("\n═══ OSS ═══")
    try:
        o = adapter.check_oss()
        print(f"  {'✅' if o else '❌'}")
    except Exception as e:
        print(f"  ❌ {e}")

    # 上传测试
    print(f"\n═══ OSS PUT {size_mb}MB ═══")
    with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
        f.write(b'\x00' * (size_mb * 1024 * 1024))
        p = f.name
    obj = f'health-check/connectivity-{int(time.time())}.bin'
    try:
        t0 = time.time()
        with open(p, 'rb') as fh:
            adapter._oss_put(obj, fh.read(), timeout=30)
        elapsed = time.time() - t0
        print(f"  ✅ {elapsed:.1f}s ({size_mb/elapsed:.1f}MB/s)")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ❌ {elapsed:.1f}s: {str(e)[:200]}")
    finally:
        os.unlink(p)

if __name__ == '__main__':
    main()

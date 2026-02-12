"""
CleanupTTLCache 单元测试

测试目标：server/copilot_adapter.py 中的 CleanupTTLCache 类
- 手动删除时触发 on_expire 回调
- TTL 过期驱逐时触发回调
- 容量满时驱逐最旧条目也触发回调
- 回调异常不阻塞删除操作
- 不传 on_expire 时行为与普通 TTLCache 一致

运行方式:
    python -m pytest tests/test_cleanup_ttl_cache.py -v
"""

import sys
import time
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入待测试的类（在 copilot_adapter.py 实现后导入）
# from server.copilot_adapter import CleanupTTLCache


class TestCleanupTTLCache:
    """CleanupTTLCache 自定义缓存测试"""

    def _get_cache_class(self):
        """延迟导入 CleanupTTLCache"""
        from server.copilot_adapter import CleanupTTLCache
        return CleanupTTLCache

    def test_on_expire_called_on_manual_delete(self):
        """手动删除时触发 on_expire 回调"""
        CleanupTTLCache = self._get_cache_class()
        expired = {}
        def on_expire(key, value):
            expired[key] = value

        cache = CleanupTTLCache(maxsize=10, ttl=300, on_expire=on_expire)
        cache["a"] = "value_a"
        del cache["a"]
        assert expired == {"a": "value_a"}

    def test_on_expire_called_on_ttl_expiry(self):
        """TTL 过期时触发 on_expire 回调"""
        CleanupTTLCache = self._get_cache_class()
        expired = {}
        def on_expire(key, value):
            expired[key] = value

        cache = CleanupTTLCache(maxsize=10, ttl=0.1, on_expire=on_expire)  # 100ms TTL
        cache["a"] = "value_a"
        time.sleep(0.2)  # 等待过期
        cache.expire()   # 触发驱逐
        assert "a" in expired
        assert expired["a"] == "value_a"

    def test_on_expire_exception_does_not_block_delete(self):
        """回调异常不阻塞删除操作"""
        CleanupTTLCache = self._get_cache_class()
        def on_expire(key, value):
            raise RuntimeError("cleanup failed")

        cache = CleanupTTLCache(maxsize=10, ttl=300, on_expire=on_expire)
        cache["a"] = "value_a"
        del cache["a"]  # 不应抛异常
        assert "a" not in cache

    def test_no_callback(self):
        """不传 on_expire 时行为与普通 TTLCache 一致"""
        CleanupTTLCache = self._get_cache_class()
        cache = CleanupTTLCache(maxsize=10, ttl=300)
        cache["a"] = "value_a"
        del cache["a"]
        assert "a" not in cache

    def test_maxsize_eviction_triggers_callback(self):
        """容量满时驱逐最旧条目也触发回调"""
        CleanupTTLCache = self._get_cache_class()
        expired = {}
        def on_expire(key, value):
            expired[key] = value

        cache = CleanupTTLCache(maxsize=2, ttl=300, on_expire=on_expire)
        cache["a"] = 1
        cache["b"] = 2
        cache["c"] = 3  # 应驱逐 "a"
        assert "a" in expired
        assert expired["a"] == 1

    def test_update_value_then_delete(self):
        """更新值后删除，回调应拿到最新值"""
        CleanupTTLCache = self._get_cache_class()
        expired = {}
        def on_expire(key, value):
            expired[key] = value

        cache = CleanupTTLCache(maxsize=10, ttl=300, on_expire=on_expire)
        cache["a"] = "old_value"
        cache["a"] = "new_value"
        del cache["a"]
        assert expired["a"] == "new_value"

    def test_multiple_items_expire(self):
        """多个条目过期时都触发回调"""
        CleanupTTLCache = self._get_cache_class()
        expired = {}
        def on_expire(key, value):
            expired[key] = value

        cache = CleanupTTLCache(maxsize=10, ttl=0.1, on_expire=on_expire)
        cache["a"] = "value_a"
        cache["b"] = "value_b"
        time.sleep(0.2)
        cache.expire()
        assert "a" in expired
        assert "b" in expired


# ============================================================================
# 入口
# ============================================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "--tb=short"])

import fakeredis
import time
from fakeredis import FakeRedis

r = fakeredis.FakeRedis(decode_responses=True)

LUA_RATE_LIMITER = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

LUA_ACQUIRE_LOCK = """
if redis.call('SETNX', KEYS[1], ARGV[1]) == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[2])
    return true
else
    return false
end
"""


def check_rate_limit_pro(user_id):
    key = f"rate_limit:{user_id}"
    
    try:
        limit = r.eval(LUA_RATE_LIMITER, 1, key, 10)
        return int(limit) <= 3
    
    except Exception as e:
        print(f"Lua Error (Rate Limiter): {e}")
        return False
    
    
def get_user_data_pro(user_id):
    cache_key = f"user:profile:{user_id}"
    lock_key = f"lock:user:{user_id}"

    cache_data = r.hgetall(cache_key)
    
    if cache_data:
        cache_data["status"] = "cached"
        return cache_data
    
    lock_acquired = r.eval(LUA_ACQUIRE_LOCK, 1, lock_key, "locked", 5)
    
    if lock_acquired:
        try:
            db_data = {"id": user_id, "name": "Ultra Player", "level": "99"}
            r.hset(cache_key, mapping=db_data)
            r.expire(cache_key, 60)
            db_data["status"] = "db"
            return db_data
        
        finally:
            r.delete(lock_key)
            
    else:
        time.sleep(0.1)
        return get_user_data_pro(user_id)
    
if __name__ == "__main__":
    uid = "ultra_user_1"
    r.flushall()
    
    print("=== TEST 3: Pro Rate Limiter (Lua) ===")
    
    for i in range(1, 6):

        if check_rate_limit_pro(uid):
            status = "OK"
            
        else:
            status = "LIMIT"
            
        print(f"Attempt {i}: {status}")

    print("\n=== Additional TEST: User Data Cache with Lua Mutex ===")
    print(f"1. Fetch: {get_user_data_pro(uid)}")
    print(f"2. Fetch (from cache): {get_user_data_pro(uid)}")
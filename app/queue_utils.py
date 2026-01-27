import redis
from django.conf import settings

# ========== Redis 连接 ==========
def get_redis_connection():
    """
    获取 Redis 连接
    """
    return redis.Redis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True  # 自动将字节转为字符串
    )

# ========== 队列操作 ==========
QUEUE_NAME = 'careplan_queue'

def enqueue_careplan(careplan_id):
    """
    将 CarePlan ID 放入 Redis 队列
    
    参数:
        careplan_id: CarePlan 的主键 ID
    
    返回:
        True 表示成功，False 表示失败
    """
    try:
        r = get_redis_connection()
        # 使用 RPUSH 将任务 ID 放入队列右侧（生产者）
        # 配合 worker.py 的 BLPOP（从左侧弹出），实现先进先出（FIFO）
        r.rpush(QUEUE_NAME, careplan_id)
        return True
    except Exception as e:
        print(f"Error enqueuing careplan {careplan_id}: {e}")
        return False

def dequeue_careplan():
    """
    从 Redis 队列中取出一个 CarePlan ID（阻塞式）
    
    队列顺序说明：
    - 使用 RPUSH（右侧推入）+ BLPOP（左侧弹出）实现 FIFO（先进先出）
    - 先提交的任务会先被处理
    
    返回:
        careplan_id 或 None
    """
    try:
        r = get_redis_connection()
        # 使用 BLPOP 从队列左侧取出任务（消费者）
        # 配合 enqueue_careplan 的 RPUSH，实现 FIFO 先进先出
        # timeout=0 表示永久阻塞，直到有任务
        result = r.blpop(QUEUE_NAME, timeout=0)
        if result:
            queue_name, careplan_id = result
            return careplan_id
        return None
    except Exception as e:
        print(f"Error dequeuing careplan: {e}")
        return None

def get_queue_length():
    """
    获取队列中待处理任务的数量
    
    返回:
        队列长度（整数）
    """
    try:
        r = get_redis_connection()
        return r.llen(QUEUE_NAME)
    except Exception as e:
        print(f"Error getting queue length: {e}")
        return 0

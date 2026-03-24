import asyncio
import time


async def background_heartbeat():
    """模拟一个后台进程，比如 UI 界面的刷新、或者维持数据库连接的心跳"""
    for i in range(1, 6):
        print(f"  [后台] 系统心跳跳动... ({i}s) - 界面依然可以点击")
        await asyncio.sleep(1)


async def single_sequential_task():
    """你的代码逻辑：完全没有并发，严格按顺序一行行执行"""
    print("\n[主线] 1. 开始请求大模型 (预计耗时 3 秒)...")
    # 哪怕这里只是一行顺序代码，因为有 await，它把 CPU 的控制权交了出去
    await asyncio.sleep(3)
    print("[主线] 2. 大模型回复完毕！\n")

    print("[主线] 3. 开始获取 State (预计耗时 1 秒)...")
    await asyncio.sleep(1)
    print("[主线] 4. State 获取完毕！\n")


async def main():
    # 启动后台心跳任务（让它在后台默默跑）
    heartbeat = asyncio.create_task(background_heartbeat())

    # 顺序执行你的主线任务
    start = time.time()
    await single_sequential_task()
    print(f"[统计] 主线任务总耗时: {time.time() - start:.2f} 秒")

    heartbeat.cancel()  # 主线干完，关掉心跳


# 运行这段代码
asyncio.run(main())
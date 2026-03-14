import threading
from queue import Queue
import uuid

class BackgroundManager:
    """
    后台守护任务管理器 (BackgroundManager)
    
    【设计意图】
    有些工具（比如跑一套庞大的测试用例，或者编译一个巨型的工程）执行可能长达数分钟，
    如果直接阻塞进程会导致主 Agent 在此期间无法处理任何其他的反馈（假死）。
    
    此类提供将任务派发到后台 Thread 的能力，让主进程在发起长时间任务后可随时通过此队列
    (drain) 接收完成的回调通知（Event-Driven 范式）。
    """
    def __init__(self):
        # 缓存正在执行的任务句柄
        self.tasks = {}
        # 收集执行完毕的数据队列（跨线程安全）
        self.results_queue = Queue()

    def _worker(self, task_id: str, command: str, timeout: int):
        import subprocess
        try:
            # 同样应被包裹一层沙盒安全防护
            res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout)
            out = res.stdout + res.stderr
            status = "completed" if res.returncode == 0 else f"failed({res.returncode})"
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode() if e.stdout else "Timeout"
            status = "timeout"
        except Exception as e:
            out = str(e)
            status = "error"
            
        self.results_queue.put({
            "task_id": task_id,
            "status": status,
            "result": out[:5000] # 防止单个长时任务的结果撑爆 prompt 缓存
        })

    def run(self, command: str, timeout: int = 120) -> str:
        """非阻塞式唤起后台子进程/线程"""
        task_id = str(uuid.uuid4())[:8]
        t = threading.Thread(target=self._worker, args=(task_id, command, timeout), daemon=True)
        t.start()
        self.tasks[task_id] = t
        return f"Background task {task_id} started."

    def check(self, task_id: str = None) -> str:
        """主动探针探测：询问特定进程是否还活着"""
        if task_id:
            if task_id not in self.tasks: return f"Task {task_id} not found."
            t = self.tasks[task_id]
            return f"Task {task_id} is {'running' if t.is_alive() else 'finished'}."
        active = [tid for tid, t in self.tasks.items() if t.is_alive()]
        return f"Active tasks: {active}" if active else "No active background tasks."

    def drain(self) -> list:
        """主循环收割接口：主循环每次 Tick (刷新) 时，都会通过该接口榨干所有刚完成的任务结果"""
        results = []
        while not self.results_queue.empty():
            results.append(self.results_queue.get())
        return results

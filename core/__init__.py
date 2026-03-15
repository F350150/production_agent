from managers.messages import MessageBus
from managers.tasks import TaskManager
from managers.team import TeammateManager

# 全局组件单例，供整个系统共享
BUS = MessageBus()
TODO = TaskManager()
TEAM = TeammateManager(BUS, TODO)

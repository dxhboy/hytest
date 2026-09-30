"""
测试引擎接口协议

定义 PlaywrightTestEngine 和 SeleniumTestEngine 的公共接口契约。
使用 Protocol 而非 ABC：两套引擎一套是 async、一套是 sync，无法共享
同一个 @abstractmethod 签名，但 Protocol 只检查方法名和参数结构是否匹配，
不要求 async/sync 一致。

新增 action type 或接口方法时，先在这里声明，再到两个引擎里实现——
如果漏了一个，runtime_checkable 的 isinstance 检查会在运行时报错。
"""
from typing import Dict, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class TestEngineProtocol(Protocol):
    """测试引擎接口协议

    PlaywrightTestEngine 和 SeleniumTestEngine 都必须实现以下方法。
    """

    browser_type: str
    headless: bool
    remote_service: object
    project_id: object

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def execute_step(self, step: object, element_data: Dict) -> Tuple[bool, str, Optional[str]]: ...

    def navigate(self, url: str) -> Tuple[bool, str]: ...

    def capture_screenshot(self) -> Optional[str]: ...

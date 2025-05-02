from typing import Any

class BaseTool:
    """Base class for all agent tools"""
    
    def __init__(self):
        self.name = self.__class__.__name__
        self.description = "Default tool description"
    
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("Tool must implement __call__ method") 
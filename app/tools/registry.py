from typing import Callable, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Callable] = {}
        self._descriptions: Dict[str, str] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, description: str, schema: Dict[str, Any]):
        """Decorator to register a tool."""
        def decorator(func: Callable):
            self._tools[name] = func
            self._descriptions[name] = description
            self._schemas[name] = schema
            return func
        return decorator

    def get_tool(self, name: str) -> Callable:
        return self._tools.get(name)

    def get_all_tool_definitions(self) -> List[Dict[str, Any]]:
        """Return tool definitions suitable for LLM injection."""
        definitions = []
        for name in self._tools:
            definitions.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": self._descriptions[name],
                    "parameters": self._schemas[name]
                }
            })
        return definitions

    async def execute(self, name: str, **kwargs) -> Any:
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool {name} not found in registry.")
        
        logger.info(f"Executing tool: {name} with args: {kwargs}")
        return await tool(**kwargs)

registry = ToolRegistry()

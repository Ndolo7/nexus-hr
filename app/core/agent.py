import json
import logging
from typing import Dict, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from app.tools.registry import registry
from app.services.rag_engine import rag_engine
from app.core.config import settings

logger = logging.getLogger(__name__)

# Register RAG as a tool so the LLM knows it can search policies
@registry.register(
    name="search_hr_policy",
    description="Search the employee handbook and HR policies for rules regarding leave, benefits, and onboarding.",
    schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The policy question to search."}
        },
        "required": ["query"]
    }
)
async def tool_search_hr_policy(query: str, **kwargs) -> str:
    try:
        docs = rag_engine.retrieve_policy(query)
        return rag_engine.format_retrieved_context(docs)
    except Exception as e:
        logger.exception("search_hr_policy tool failed: %s", e)
        return "Policy search is temporarily unavailable. Please retry or contact HR for urgent clarification."


class AgentCore:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Ensure erp tools are registered
        import app.tools.erp_tools

        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0,
        )

        self.system_prompt = """You are Nexus HR, a secure orchestration agent. 
            You answer HR policy questions and execute ERP actions for employees. 
            Always use the tools provided to fetch data or execute actions.
            Policy questions must strictly be answered using the 'search_hr_policy' tool context.
            Do not invent ERP results or policies. Explain to the user when an action is completed or requires approval."""

    def _build_lc_tools(self):
        """Convert registry tool definitions (OpenAI format) to LangChain tool format."""
        tool_definitions = registry.get_all_tool_definitions()
        return [
            {"type": "function", "function": t["function"]}
            for t in tool_definitions
        ]

    def _normalize_content_to_text(self, content: Any) -> str:
        """
        Ensure model message content is always serialized to plain text.
        Gemini/LangChain may return list-based content blocks instead of a raw string.
        """
        if isinstance(content, str):
            return content

        if content is None:
            return ""

        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    if isinstance(item.get("text"), str):
                        parts.append(item["text"])
                    elif isinstance(item.get("content"), str):
                        parts.append(item["content"])
            if parts:
                return "\n".join(p.strip() for p in parts if p and p.strip())
            return json.dumps(content, ensure_ascii=False)

        if isinstance(content, dict):
            if isinstance(content.get("text"), str):
                return content["text"]
            if isinstance(content.get("content"), str):
                return content["content"]
            return json.dumps(content, ensure_ascii=False)

        return str(content)

    async def chat(self, user_id: str, query: str) -> Dict[str, Any]:
        self.logger.info(f"Received query from {user_id}: {query}")
        tools_used = []

        lc_tools = self._build_lc_tools()
        llm_with_tools = self.llm.bind_tools(lc_tools)

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=query),
        ]

        # Orchestration Loop
        try:
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)

            if response.tool_calls:
                for tc in response.tool_calls:
                    fn_name = tc["name"]
                    fn_args = tc["args"]
                    tools_used.append(fn_name)

                    self.logger.info(f"LLM executing tool: {fn_name}")

                    # Inject user_id for guardrail checks
                    fn_args["user_id"] = user_id

                    try:
                        tool_result = await registry.execute(fn_name, **fn_args)
                        result_str = json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result)
                    except Exception as e:
                        result_str = str(e)

                    messages.append(
                        ToolMessage(content=result_str, tool_call_id=tc["id"])
                    )

                # Second call to LLM after tool executions
                final_response = await self.llm.ainvoke(messages)
                final_answer = self._normalize_content_to_text(final_response.content)
            else:
                final_answer = self._normalize_content_to_text(response.content)

            return {
                "response": final_answer,
                "tools_used": tools_used
            }
        except Exception as e:
            self.logger.error(f"AgentCore Chat Error: {e}")
            return {"response": f"An orchestration error occurred: {str(e)}", "tools_used": tools_used}

    async def direct_action(self, user_id: str, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Bypass chat and directly invoke an action through the registry if appropriate."""
        self.logger.info(f"Direct action {action} requested by {user_id}")
        try:
            payload["user_id"] = user_id
            result = await registry.execute(action, **payload)
            return {"status": "success", "result": result}
        except Exception as e:
            return {"status": "error", "message": str(e)}


agent_core = AgentCore()

import json
import logging
from typing import Dict, Any, List
try:
    from openai import AsyncOpenAI
    has_openai = True
except ImportError:
    has_openai = False

from app.tools.registry import registry
from app.services.rag_engine import rag_engine
from app.core.config import settings

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
    docs = rag_engine.retrieve_policy(query)
    return rag_engine.format_retrieved_context(docs)


class AgentCore:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Ensure erp tools are registered
        import app.tools.erp_tools
        if has_openai:
            self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        else:
            self.logger.warning("OpenAI package not found. Cannot perform real LLM calls.")
            self.client = None

        self.system_prompt = """You are Nexus HR, a secure orchestration agent. 
            You answer HR policy questions and execute ERP actions for employees. 
            Always use the tools provided to fetch data or execute actions.
            Policy questions must strictly be answered using the 'search_hr_policy' tool context.
            Do not invent ERP results or policies. Explain to the user when an action is completed or requires approval."""

    async def chat(self, user_id: str, query: str) -> Dict[str, Any]:
        self.logger.info(f"Received query from {user_id}: {query}")
        tools_used = []
        
        if not self.client:
            return {"response": "OpenAI client is not configured propertly.", "tools_used": []}

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": query}
        ]
        
        tool_definitions = registry.get_all_tool_definitions()

        # Orchestration Loop
        try:
            response = await self.client.chat.completions.create(
                model="gpt-4-turbo",  # or a stable model
                messages=messages,
                tools=tool_definitions,
                tool_choice="auto"
            )

            response_message = response.choices[0].message
            messages.append(response_message)

            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    tools_used.append(function_name)
                    
                    self.logger.info(f"LLM executing tool: {function_name}")
                    
                    # Inject user_id as a keyword argument since tools expect it for guardrails checks
                    function_args['user_id'] = user_id

                    try:
                        tool_result = await registry.execute(function_name, **function_args)
                        result_str = json.dumps(tool_result) if isinstance(tool_result, dict) else str(tool_result)
                    except Exception as e:
                        result_str = str(e)

                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": result_str,
                    })

                # Second call to LLM after tool executions
                final_response = await self.client.chat.completions.create(
                    model="gpt-4-turbo",
                    messages=messages,
                )
                final_answer = final_response.choices[0].message.content
            else:
                final_answer = response_message.content

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

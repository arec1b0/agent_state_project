import asyncio
from typing import Annotated

from typing_extensions import TypedDict

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolCall,
)
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from src.agent_session.client import AgentStateClient
from src.agent_session.langgraph_integration import APIStateCheckpointer


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


# --------------------------------------------------------------------------
# Consequential Tool
# --------------------------------------------------------------------------
@tool
def charge_credit_card(amount: float, description: str) -> str:
    """Charges a credit card for a specific amount and description. Highly consequential."""
    print(
        f"\n[SYSTEM ACTION] -> Executing charge of ${amount} for: {description}\n"
    )
    return f"Successfully processed charge of ${amount}."


tools = [charge_credit_card]
tool_node = ToolNode(tools)


# --------------------------------------------------------------------------
# Mock LLM
# --------------------------------------------------------------------------
def mock_llm_node(state: AgentState):
    """Simulates an LLM deciding to call the credit card tool."""
    last_msg = state["messages"][-1]

    if isinstance(last_msg, HumanMessage):
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="call_123",
                            name="charge_credit_card",
                            args={
                                "amount": 2500,
                                "description": "Kubernetes Cluster",
                            },
                        )
                    ],
                )
            ]
        }

    return {"messages": [AIMessage(content="Charge complete.")]}


def route_tools(state: AgentState):
    last_message = state["messages"][-1]

    if getattr(last_message, "tool_calls", None):
        return "tools"

    return END


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
async def main() -> None:
    print("Connecting to Agent State Client...")

    client = AgentStateClient(base_url="http://127.0.0.1:8000")
    checkpointer = APIStateCheckpointer(client=client)

    builder = StateGraph(AgentState)

    builder.add_node("llm", mock_llm_node)
    builder.add_node("tools", tool_node)

    builder.add_edge(START, "llm")

    builder.add_conditional_edges(
        "llm",
        route_tools,
        {
            "tools": "tools",
            END: END,
        },
    )

    builder.add_edge("tools", "llm")

    graph = builder.compile(checkpointer=checkpointer)

    session_config = {
        "configurable": {
            "thread_id": "peonova-production-session-alpha",
        }
    }

    print("\n--- Sending Execution Command ---")

    input_message = HumanMessage(
        content="Process a $2500 charge for the new Kubernetes cluster infrastructure."
    )

    async for event in graph.astream(
        {"messages": [input_message]},
        config=session_config,
    ):
        for node in event:
            print(f"[{node.upper()}] Node completed its transition.")

    await client.close()
    print("\nExecution completed. Check MLflow.")


if __name__ == "__main__":
    asyncio.run(main())
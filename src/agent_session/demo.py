import asyncio
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

from src.agent_session.client import AgentStateClient
from src.agent_session.langgraph_integration import APIStateCheckpointer

# 1. Define a strictly JSON-serializable state
class SimpleGraphState(TypedDict):
    step_count: int
    latest_action: str

# 2. Define our stateless worker node
def worker_node(state: SimpleGraphState) -> SimpleGraphState:
    current_count = state.get("step_count", 0)
    return {
        "step_count": current_count + 1,
        "latest_action": f"Executed step {current_count + 1}"
    }

async def main() -> None:
    print("Initializing Agent State Client...")
    client = AgentStateClient(base_url="http://127.0.0.1:8000")
    checkpointer = APIStateCheckpointer(client=client)

    # 3. Build the graph
    builder = StateGraph(SimpleGraphState)
    builder.add_node("worker", worker_node)
    builder.add_edge(START, "worker")
    builder.add_edge("worker", END)

    # 4. Compile with our custom Exact-Once API Checkpointer
    graph = builder.compile(checkpointer=checkpointer)

    session_config = {"configurable": {"thread_id": "langgraph-demo-session"}}

    print(f"\n--- Execution Turn 1 ---")
    initial_input = {"step_count": 0, "latest_action": "initialized"}
    
    # ainvoke triggers the graph, which triggers APIStateCheckpointer.aput
    result = await graph.ainvoke(initial_input, config=session_config)
    print(f"Graph Output: {result}")
    
    print(f"\n--- Execution Turn 2 ---")
    # Passing a new input forces the graph to run again. 
    # LangGraph merges this input with the checkpointed state from our API before executing the worker.
    result = await graph.ainvoke({"latest_action": "trigger_turn_2"}, config=session_config)
    print(f"Graph Output: {result}")

    await client.close()
    print("\nDemo complete. Check your Uvicorn logs and MLflow UI.")

if __name__ == "__main__":
    asyncio.run(main())
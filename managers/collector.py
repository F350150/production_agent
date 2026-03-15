"""
managers/collector.py - 轨迹收集器 (Trajectory Collector)

【设计意图】
自动收集 Agent 执行过程中的高质量对话数据，用于后续的 LoRA 微调。
支持将对话轨迹转换为标准的微调格式（如 Alpaca 或 ShareGPT）。
"""

import os
import json
import time
from typing import List, Dict, Any, Optional
from pathlib import Path
from utils.paths import TEAM_DIR

class TrajectoryCollector:
    """
    负责记录和导出 Agent 执行轨迹。
    """
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or (TEAM_DIR / "trajectories")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def record_session(self, session_id: str, messages: List[Any], metadata: Dict[str, Any] = None):
        """
        Record a full session trajectory.
        
        :param session_id: Unique session identifier.
        :param messages: List of messages (LangChain format).
        :param metadata: Additional context (e.g., success status, token cost).
        """
        timestamp = int(time.time())
        file_path = self.output_dir / f"traj_{session_id}_{timestamp}.json"
        
        # Convert LangChain messages to serializable format
        serializable_msgs = []
        for msg in messages:
            msg_data = {
                "role": msg.type,
                "content": msg.content,
            }
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                msg_data["tool_calls"] = msg.tool_calls
            if msg.type == "tool":
                msg_data["tool_call_id"] = msg.tool_call_id
                msg_data["name"] = msg.name
            
            serializable_msgs.append(msg_data)
            
        data = {
            "session_id": session_id,
            "timestamp": timestamp,
            "metadata": metadata or {},
            "messages": serializable_msgs
        }
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        return file_path

    def export_for_finetune(self, format: str = "alpaca") -> Path:
        """
        Export all collected trajectories into a single file for training.
        """
        all_files = list(self.output_dir.glob("traj_*.json"))
        dataset = []
        
        for f_path in all_files:
            with open(f_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            if format == "alpaca":
                # Convert session to Alpaca format (User input as instruction/input, Agent response as output)
                # Simplified: Takes the whole context as input and next response as output
                # In practice, we might want to split into turns.
                dataset.extend(self._to_alpaca_turns(data["messages"]))
        
        output_file = self.output_dir / f"dataset_{format}_{int(time.time())}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(dataset, f, ensure_ascii=False, indent=2)
            
        return output_file

    def _to_alpaca_turns(self, messages: List[Dict]) -> List[Dict]:
        """Convert a message sequence into multiple Alpaca turns."""
        turns = []
        context = ""
        
        for i, msg in enumerate(messages):
            if msg["role"] == "human":
                instruction = msg["content"]
                # Find the next non-human message as output
                output = ""
                for next_msg in messages[i+1:]:
                    if next_msg["role"] != "human":
                        output += f"\n{next_msg['content']}"
                        if "tool_calls" in next_msg:
                            output += f"\nTool Calls: {json.dumps(next_msg['tool_calls'])}"
                    else:
                        break
                
                if output.strip():
                    turns.append({
                        "instruction": instruction,
                        "input": context,
                        "output": output.strip()
                    })
            
            # Accumulate context
            context += f"\n{msg['role']}: {msg['content']}"
            
        return turns

# Singleton instance
collector = TrajectoryCollector()

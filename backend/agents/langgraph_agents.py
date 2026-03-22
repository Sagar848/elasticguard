"""
ElasticGuard LangGraph AI Agents
Autonomous multi-agent system for ES diagnosis and remediation
"""
from typing import Any, Dict, List, Optional, TypedDict, Annotated
from enum import Enum
import json
import structlog

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages

from core.config import settings
from core.diagnostics import DiagnosticsReport, DiagnosticIssue, Severity

logger = structlog.get_logger()

# ─── Agent State ─────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    cluster_id: str
    report: Optional[Dict]
    issues: List[Dict]
    current_issue_idx: int
    solutions: List[Dict]
    rag_context: str
    final_summary: str
    error: Optional[str]


# ─── LLM Factory ─────────────────────────────────────────────────────────────

def get_llm(provider: str = None, model: str = None, temperature: float = 0.1):
    """
    Create an LLM instance based on provider setting.
    Validates API keys before returning — raises ValueError with a
    clear human-readable message if the key is missing or a placeholder.
    """
    provider = provider or settings.DEFAULT_AI_PROVIDER

    def _require_key(key: str, provider_name: str, hint: str) -> str:
        """Validate that a key is set and not a placeholder."""
        placeholders = {"", "sk-...", "AIza...", "sk-ant-...", None}
        if not key or key in placeholders or key.endswith("..."):
            raise ValueError(
                f"{provider_name} API key is not configured. "
                f"Go to Settings → AI Provider → set your {provider_name} key. "
                f"Get one at: {hint}"
            )
        return key

    if provider == "openai":
        from langchain_openai import ChatOpenAI
        key = _require_key(
            settings.OPENAI_API_KEY, "OpenAI",
            "https://platform.openai.com/api-keys"
        )
        return ChatOpenAI(
            model=model or settings.OPENAI_DEFAULT_MODEL,
            temperature=temperature,
            api_key=key,
            base_url=settings.OPENAI_BASE_URL or "https://api.openai.com/v1",
        )

    elif provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        key = _require_key(
            settings.GEMINI_API_KEY, "Google Gemini",
            "https://aistudio.google.com/app/apikey"
        )
        # Map deprecated model names to current equivalents
        _gemini_aliases = {
            "gemini-1.5-pro":          "gemini-2.0-flash",
            "gemini-1.5-pro-latest":   "gemini-2.0-flash",
            "gemini-1.5-flash":        "gemini-2.0-flash-lite",
            "gemini-pro":              "gemini-2.0-flash",
            "gemini-1.0-pro":          "gemini-2.0-flash",
        }
        resolved_model = model or settings.GEMINI_DEFAULT_MODEL
        resolved_model = _gemini_aliases.get(resolved_model, resolved_model)
        return ChatGoogleGenerativeAI(
            model=resolved_model,
            temperature=temperature,
            google_api_key=key,
        )

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        key = _require_key(
            settings.ANTHROPIC_API_KEY, "Anthropic Claude",
            "https://console.anthropic.com/settings/keys"
        )
        return ChatAnthropic(
            model=model or settings.ANTHROPIC_DEFAULT_MODEL,
            temperature=temperature,
            api_key=key,
        )

    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model or settings.OLLAMA_DEFAULT_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=temperature,
        )

    elif provider == "custom":
        from langchain_openai import ChatOpenAI
        if not settings.CUSTOM_AI_BASE_URL:
            raise ValueError(
                "Custom AI base URL is not configured. "
                "Go to Settings → AI Provider → Custom and set the endpoint URL."
            )
        return ChatOpenAI(
            model=model or settings.CUSTOM_AI_MODEL or "gpt-4",
            temperature=temperature,
            api_key=settings.CUSTOM_AI_KEY or "not-needed",
            base_url=settings.CUSTOM_AI_BASE_URL,
        )

    else:
        raise ValueError(
            f"Unknown AI provider: '{provider}'. "
            f"Valid options: openai, gemini, anthropic, ollama, custom"
        )


# ─── RAG Knowledge Base ───────────────────────────────────────────────────────

class ElasticKnowledgeRAG:
    """Retrieval-Augmented Generation for Elasticsearch knowledge."""

    def __init__(self):
        self._vectorstore = None

    async def _get_vectorstore(self):
        if self._vectorstore is None:
            try:
                import chromadb
                from langchain_chroma import Chroma

                # Try to use Ollama embeddings (local, free)
                try:
                    from langchain_ollama import OllamaEmbeddings
                    embeddings = OllamaEmbeddings(
                        model=settings.OLLAMA_EMBED_MODEL,
                        base_url=settings.OLLAMA_BASE_URL,
                    )
                except Exception:
                    # Fall back to OpenAI embeddings
                    from langchain_openai import OpenAIEmbeddings
                    embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)

                self._vectorstore = Chroma(
                    persist_directory=settings.CHROMA_PERSIST_DIR,
                    embedding_function=embeddings,
                    collection_name="es_knowledge",
                )
            except Exception as e:
                logger.warning("RAG not available", error=str(e))
                return None
        return self._vectorstore

    async def retrieve(self, query: str, k: int = 5) -> str:
        """Retrieve relevant knowledge for a query."""
        try:
            vs = await self._get_vectorstore()
            if not vs:
                return ""
            docs = vs.similarity_search(query, k=k)
            return "\n\n".join(d.page_content for d in docs)
        except Exception as e:
            logger.warning("RAG retrieval failed", error=str(e))
            return ""


rag = ElasticKnowledgeRAG()


# ─── Agent Nodes ─────────────────────────────────────────────────────────────

TRIAGE_SYSTEM = """You are an expert Elasticsearch cluster triage agent.

Your job is to:
1. Review the cluster diagnostics report
2. Prioritize issues by severity and business impact
3. Identify which issues need immediate attention

Output a JSON object with:
{
  "priority_order": [list of issue IDs in priority order],
  "critical_summary": "one sentence on most critical issue",
  "needs_immediate_action": true/false,
  "estimated_recovery_time": "estimate like '15 minutes' or '2 hours'"
}
"""

DIAGNOSTIC_SYSTEM = """You are a senior Elasticsearch architect and SRE.

For each issue, provide deep analysis:
1. Root cause analysis
2. Impact assessment  
3. Related issues that might be connected
4. Historical context if relevant

Be specific about version differences (ES 7/8/9) where relevant.
Output pure JSON only.
"""

SOLUTION_SYSTEM = """You are an Elasticsearch expert who specializes in cluster remediation.

For each issue, provide:
1. Step-by-step solution
2. Specific Elasticsearch API calls with exact request bodies
3. CLI commands if needed (to be run on server, not via API)
4. Risk assessment (low/medium/high)
5. Expected outcome
6. Rollback procedure

IMPORTANT: 
- Always ask for user approval before destructive operations
- Provide commands in both curl format and JSON for the UI
- Note any version-specific differences

Output JSON with this schema:
{
  "issue_id": "...",
  "root_cause": "...",
  "solution_steps": ["step 1", "step 2", ...],
  "apis": [
    {
      "step": 1,
      "method": "PUT|POST|GET|DELETE",
      "path": "/_cluster/settings",
      "body": {...},
      "description": "human readable description",
      "risk": "low|medium|high",
      "curl_command": "curl -X PUT ..."
    }
  ],
  "cli_commands": ["cmd1", "cmd2"],
  "risk_level": "low|medium|high",
  "expected_outcome": "...",
  "rollback": "..."
}
"""

SAFETY_SYSTEM = """You are an Elasticsearch safety validator.

Review proposed solutions and:
1. Check for data loss risks
2. Verify commands are correct
3. Flag any irreversible operations
4. Suggest safer alternatives if available
5. Verify ES version compatibility

Output JSON:
{
  "is_safe": true/false,
  "risk_level": "low|medium|high",
  "warnings": ["..."],
  "modified_solution": {...} or null,
  "requires_backup": true/false
}
"""

SUMMARY_SYSTEM = """You are an Elasticsearch monitoring system.

Create a clear, actionable incident summary for the cluster operator that includes:
1. Overall cluster health status
2. List of issues found with severity
3. Immediate actions required
4. Monitoring recommendations

Be concise but thorough. Use plain language, not jargon.
"""


class ElasticGuardAgentSystem:
    """
    LangGraph-based multi-agent system for Elasticsearch diagnosis.
    """

    def __init__(self, provider: str = None, model: str = None):
        self.llm = get_llm(provider, model)
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        workflow.add_node("triage", self._triage_agent)
        workflow.add_node("enrich_with_rag", self._rag_agent)
        workflow.add_node("generate_solutions", self._solution_agent)
        workflow.add_node("safety_check", self._safety_agent)
        workflow.add_node("summarize", self._summary_agent)

        workflow.add_edge(START, "triage")
        workflow.add_edge("triage", "enrich_with_rag")
        workflow.add_edge("enrich_with_rag", "generate_solutions")
        workflow.add_edge("generate_solutions", "safety_check")
        workflow.add_edge("safety_check", "summarize")
        workflow.add_edge("summarize", END)

        return workflow.compile()

    async def _triage_agent(self, state: AgentState) -> AgentState:
        """Prioritize and triage issues."""
        try:
            issues_json = json.dumps(state["issues"][:20], indent=2)  # limit for context
            report_summary = json.dumps({
                k: v for k, v in state["report"].items()
                if k not in ["raw_data"]
            }, indent=2)

            response = await self.llm.ainvoke([
                SystemMessage(content=TRIAGE_SYSTEM),
                HumanMessage(content=f"""
Cluster Report:
{report_summary}

Issues Found ({len(state['issues'])} total, showing first 20):
{issues_json}

Provide triage analysis.
""")
            ])

            triage_data = self._parse_json_response(response.content)
            state["messages"].append(AIMessage(content=f"Triage: {response.content}"))

            # Reorder issues based on triage priority
            if triage_data and "priority_order" in triage_data:
                priority_ids = triage_data["priority_order"]
                issues_by_id = {i["id"]: i for i in state["issues"]}
                reordered = [issues_by_id[pid] for pid in priority_ids if pid in issues_by_id]
                remaining = [i for i in state["issues"] if i["id"] not in set(priority_ids)]
                state["issues"] = reordered + remaining

        except Exception as e:
            logger.error("Triage agent error", error=str(e))

        return state

    async def _rag_agent(self, state: AgentState) -> AgentState:
        """Retrieve relevant knowledge base context."""
        try:
            if not state["issues"]:
                state["rag_context"] = ""
                return state

            # Build query from top issues
            top_issues = state["issues"][:5]
            query_parts = [i.get("title", "") for i in top_issues]
            query = " ".join(query_parts)

            context = await rag.retrieve(query, k=5)
            state["rag_context"] = context

        except Exception as e:
            logger.warning("RAG agent error", error=str(e))
            state["rag_context"] = ""

        return state

    async def _solution_agent(self, state: AgentState) -> AgentState:
        """Generate solutions for each issue."""
        solutions = []

        # Process top issues (limit to avoid token overflow)
        for issue in state["issues"][:10]:
            try:
                rag_context = state.get("rag_context", "")
                context_snippet = f"\nRelevant Knowledge:\n{rag_context[:1000]}" if rag_context else ""

                response = await self.llm.ainvoke([
                    SystemMessage(content=SOLUTION_SYSTEM),
                    HumanMessage(content=f"""
Issue to solve:
{json.dumps(issue, indent=2)}

Cluster ES Version: {state['report'].get('es_version', 'unknown')}
Node Count: {state['report'].get('node_count', 0)}
{context_snippet}

Generate detailed solution with Elasticsearch API calls.
""")
                ])

                solution_data = self._parse_json_response(response.content)
                if solution_data:
                    solution_data["issue_id"] = issue["id"]
                    solution_data["issue_title"] = issue.get("title", "")
                    solution_data["severity"] = issue.get("severity", "medium")
                    solutions.append(solution_data)
                else:
                    # Fallback: use pre-defined solutions from diagnostics engine
                    solutions.append({
                        "issue_id": issue["id"],
                        "issue_title": issue.get("title", ""),
                        "severity": issue.get("severity", "medium"),
                        "root_cause": issue.get("description", ""),
                        "solution_steps": [issue.get("solution_summary", "See Elasticsearch docs")],
                        "apis": issue.get("elasticsearch_apis", []),
                        "cli_commands": issue.get("cli_commands", []),
                        "risk_level": "medium",
                        "expected_outcome": "Issue resolved",
                        "rollback": "Revert API changes or restore from snapshot",
                    })

            except Exception as e:
                logger.error("Solution agent error", error=str(e), issue_id=issue.get("id"))

        state["solutions"] = solutions
        return state

    async def _safety_agent(self, state: AgentState) -> AgentState:
        """Validate solutions for safety."""
        validated_solutions = []

        for solution in state["solutions"]:
            try:
                response = await self.llm.ainvoke([
                    SystemMessage(content=SAFETY_SYSTEM),
                    HumanMessage(content=f"""
Review this solution for safety:
{json.dumps(solution, indent=2)}

ES Version: {state['report'].get('es_version', 'unknown')}
""")
                ])

                safety_data = self._parse_json_response(response.content)
                if safety_data:
                    solution["safety"] = safety_data
                    if safety_data.get("modified_solution"):
                        solution["apis"] = safety_data["modified_solution"].get("apis", solution.get("apis", []))

            except Exception as e:
                logger.warning("Safety agent error", error=str(e))
                solution["safety"] = {"is_safe": True, "risk_level": "unknown", "warnings": []}

            validated_solutions.append(solution)

        state["solutions"] = validated_solutions
        return state

    async def _summary_agent(self, state: AgentState) -> AgentState:
        """Create final human-readable summary."""
        try:
            issues_summary = [
                {"id": i.get("id"), "title": i.get("title"), "severity": i.get("severity")}
                for i in state["issues"][:20]
            ]

            response = await self.llm.ainvoke([
                SystemMessage(content=SUMMARY_SYSTEM),
                HumanMessage(content=f"""
Cluster: {state['report'].get('cluster_name', 'unknown')} 
Status: {state['report'].get('health_status', 'unknown')}
ES Version: {state['report'].get('es_version', 'unknown')}
Nodes: {state['report'].get('node_count', 0)}
Issues Found: {len(state['issues'])}

Issues:
{json.dumps(issues_summary, indent=2)}

Solutions Generated: {len(state['solutions'])}

Create a clear operator summary.
""")
            ])

            state["final_summary"] = response.content
            state["messages"].append(AIMessage(content=response.content))

        except Exception as e:
            logger.error("Summary agent error", error=str(e))
            state["final_summary"] = f"Cluster analysis complete. Found {len(state['issues'])} issue(s)."

        return state

    def _parse_json_response(self, content: str) -> Optional[Dict]:
        """Extract JSON from LLM response."""
        import re
        # Try direct parse
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON block
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        brace_match = re.search(r'\{.*\}', content, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    async def run(self, report: DiagnosticsReport) -> Dict:
        """Run the full agent pipeline on a diagnostics report."""

        # Convert report to dict for serialization
        report_dict = {
            "cluster_id": report.cluster_id,
            "cluster_name": report.cluster_name,
            "es_version": report.es_version,
            "health_status": report.health_status,
            "node_count": report.node_count,
            "index_count": report.index_count,
            "shard_count": report.shard_count,
            "unassigned_shards": report.unassigned_shards,
        }

        issues_list = []
        for issue in report.issues:
            issues_list.append({
                "id": issue.id,
                "category": issue.category.value,
                "severity": issue.severity.value,
                "title": issue.title,
                "description": issue.description,
                "affected_resource": issue.affected_resource,
                "metrics": issue.metrics,
                "solution_summary": issue.solution_summary,
                "elasticsearch_apis": issue.elasticsearch_apis,
                "cli_commands": issue.cli_commands,
                "requires_approval": issue.requires_approval,
            })

        initial_state: AgentState = {
            "messages": [],
            "cluster_id": report.cluster_id,
            "report": report_dict,
            "issues": issues_list,
            "current_issue_idx": 0,
            "solutions": [],
            "rag_context": "",
            "final_summary": "",
            "error": None,
        }

        logger.info("Starting agent pipeline", cluster_id=report.cluster_id, issues=len(issues_list))
        final_state = await self.graph.ainvoke(initial_state)
        logger.info("Agent pipeline complete", solutions=len(final_state.get("solutions", [])))

        return {
            "report": report_dict,
            "issues": final_state["issues"],
            "solutions": final_state["solutions"],
            "summary": final_state["final_summary"],
            "rag_context_used": bool(final_state.get("rag_context")),
        }


# ─── Chat Agent ───────────────────────────────────────────────────────────────

class ClusterChatAgent:
    """Interactive chat agent for Q&A about cluster issues."""

    SYSTEM = """You are ElasticGuard, an expert Elasticsearch cluster assistant.

You have access to real-time cluster data and diagnostics.
Answer questions about:
- Cluster health and issues
- How to fix specific problems
- Performance tuning
- Index management
- Shard management
- Elasticsearch best practices

Be direct, technical, and actionable. Include specific API calls when relevant.
Current cluster context will be provided with each message.
"""

    def __init__(self, provider: str = None, model: str = None):
        self.llm = get_llm(provider, model)
        self.history: List = []

    async def chat(self, user_message: str, cluster_context: Dict = None) -> str:
        """Send a message and get a response."""
        context_str = ""
        if cluster_context:
            context_str = f"\n\nCurrent Cluster State:\n{json.dumps(cluster_context, indent=2)[:3000]}"

        messages = [SystemMessage(content=self.SYSTEM + context_str)]
        messages.extend(self.history[-10:])  # last 10 messages for context
        messages.append(HumanMessage(content=user_message))

        response = await self.llm.ainvoke(messages)
        response_text = response.content

        self.history.extend([
            HumanMessage(content=user_message),
            AIMessage(content=response_text),
        ])

        return response_text

    def clear_history(self):
        self.history = []

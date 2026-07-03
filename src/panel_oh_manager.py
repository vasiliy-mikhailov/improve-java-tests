"""Lean restricted-manager runner for the LIVE pipeline (openhands-orch leg).

Same (workdir, prompt) interface as panel_oh_run.py, but builds the delegate-only test-manager:
tools = task (delegate) + think + finish, NO terminal/file_editor, so its own context stays flat.
The prompt is built by panel.run_agent from the already-computed baseline survivors (per-method list
+ reward). NO build_module / baseline / final PIT here — panel.py owns scoring and the verdict.
The manager delegates one mutation-tester per method; each sub-agent runs PIT itself and returns only
`SURVIVORS_BEFORE`/`SURVIVORS_AFTER`, which the manager tallies (reward = 0.9 ^ sum-of-AFTER) so the
manager's own context stays flat.
"""
import os
import sys
import json
import time
from pathlib import Path

HOME = os.environ.get("IJT_HOME", os.getcwd())
sys.path.insert(0, os.path.join(HOME, "src"))
workdir, prompt = sys.argv[1], sys.argv[2]

from openhands.sdk import LLM, Agent, Conversation, LocalWorkspace, Tool
from openhands.sdk.context.condenser import LLMSummarizingCondenser
from openhands.tools.task import TaskToolSet
from openhands.tools.preset.default import (
    register_builtins_agents, load_agents_from_dir, agent_definition_to_factory,
    register_agent_if_absent,
)
from pydantic import SecretStr

model = "openai/" + os.environ["OC_MODEL"]
base_url = os.environ["OC_BASE"]
key = SecretStr(os.environ["OC_KEY"])
_R = dict(timeout=31_536_000, num_retries=100, retry_min_wait=3, retry_max_wait=60)
llm = LLM(model=model, base_url=base_url, api_key=key, usage_id="ijt-mgr",
          max_output_tokens=131072, temperature=0.0, native_tool_calling=True,
          reasoning_effort=None, drop_params=False,
          litellm_extra_body={"chat_template_kwargs": {"enable_thinking": True}}, **_R)
cond = LLM(model=model, base_url=base_url, api_key=key, usage_id="ijt-cond",
           max_output_tokens=4096, temperature=0.0, native_tool_calling=False,
           reasoning_effort=None, drop_params=False,
           litellm_extra_body={"chat_template_kwargs": {"enable_thinking": False}}, **_R)

register_builtins_agents(enable_browser=False)
_sa = Path(HOME) / "docker" / "subagents"
if _sa.is_dir():
    for _ad in load_agents_from_dir(_sa):
        register_agent_if_absent(_ad.name, agent_definition_to_factory(_ad), _ad)

manager = Agent(
    llm=llm,
    tools=[Tool(name=TaskToolSet.name)],
    include_default_tools=["FinishTool", "ThinkTool"],
    condenser=LLMSummarizingCondenser(llm=cond, max_size=40, keep_first=2),
)

_EV = os.environ.get("OH_EVENT_LOG")


def _sink(event):
    if not _EV:
        return
    try:
        rec = event.model_dump(mode="json")
    except Exception:
        rec = {"repr": str(event)[:4000]}
    rec["_kind"] = type(event).__name__
    try:
        with open(_EV, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
    except Exception:
        pass


conv = Conversation(agent=manager, workspace=LocalWorkspace(working_dir=workdir),
                    max_iteration_per_run=int(os.environ.get("OH_MAX_ITER", "1000000")),
                    persistence_dir=(os.environ.get("OH_PERSIST_DIR") or None), callbacks=[_sink])
conv.send_message(prompt)
_TRANSIENT = ("Extra data", "Expecting value", "Unterminated string", "BadRequestError",
              "Timeout", "APIError", "ServiceUnavailable", "InternalServerError", "Connection")
for _a in range(6):
    try:
        conv.run()
        break
    except Exception as _e:
        _m = str(_e)
        if _a < 5 and any(t in _m for t in _TRANSIENT):
            print("MGR_RETRY %d: %s" % (_a + 1, _m[:140]), flush=True)
            time.sleep(5 * (_a + 1))
            continue
        raise
print("MGR_DONE", flush=True)

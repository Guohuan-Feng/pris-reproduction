"""Structured research decisions via the existing Codex login, no native tools."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
from runtime import read_json,write_json,run_child

DISABLED=['shell_tool','unified_exec','shell_snapshot','multi_agent','multi_agent_v2','memories','apps','plugins','remote_plugin','browser_use','browser_use_external','browser_use_full_cdp_access','in_app_browser','computer_use','image_generation','code_mode','view_image','hooks','skill_search','skill_mcp_dependency_install','workspace_dependencies','tool_suggest','goals','sleep_tool']
PAIR={'type':'object','properties':{'model':{'type':'string','enum':['extra_trees','hist_gradient_boosting']},'target':{'type':'string','enum':['raw','log1p']}},'required':['model','target'],'additionalProperties':False}
# JSON schema fixes structure. Numerical adapter separately validates route keys/menu.
SPEC={'type':'object','properties':{'input':{'type':'string','enum':['composition','composition_repaired']},'routing':{'type':'string','enum':['global','chemistry','kmeans3']},'global':PAIR,'experts':{'type':'array','items':{'type':'object','properties':{'route':{'type':'string','enum':['cu_o','fe_anion','other','cluster0','cluster1','cluster2']},'model':PAIR['properties']['model'],'target':PAIR['properties']['target']},'required':['route','model','target'],'additionalProperties':False}}},'required':['input','routing','global','experts'],'additionalProperties':False}
PLAN_SCHEMA={'type':'object','properties':{'action':{'type':'string','enum':['experiment','stop']},'hypothesis':{'type':'string'},'falsification':{'type':'string'},'reason':{'type':'string'},'revision_of':{'type':'string'},'specification':{'anyOf':[SPEC,{'type':'null'}]},'stop_reason':{'type':'string'}},'required':['action','hypothesis','falsification','reason','revision_of','specification','stop_reason'],'additionalProperties':False}
REFLECT_SCHEMA={'type':'object','properties':{'hypothesis_status':{'type':'string','enum':['supported','not_supported','inconclusive','execution_failed']},'summary':{'type':'string'},'next_action':{'type':'string','enum':['continue','stop']},'next_focus':{'type':'string'},'stop_reason':{'type':'string'},'limitations':{'type':'array','items':{'type':'string'}}},'required':['hypothesis_status','summary','next_action','next_focus','stop_reason','limitations'],'additionalProperties':False}

class CodexDecider:
    def __init__(self,root,model='gpt-5.6-sol',executable=None):
        self.root=Path(root);self.model=model;self.executable=executable or shutil.which('codex')
        if not self.executable or not Path(self.executable).is_file():raise RuntimeError('Codex executable unavailable; use the current executable on PATH or --codex-executable')
    def __call__(self,phase,context,folder,timeout,tick):
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        if (folder/'receipt.json').exists() and read_json(folder/'receipt.json').get('completed'):
            return self.decode(phase,folder)
        schema=PLAN_SCHEMA if phase=='propose' else REFLECT_SCHEMA
        write_json(folder/'schema.json',schema);write_json(folder/'context.json',context)
        instructions='''You are the decision-maker of a persistent self-looping superconductivity research agent.
The controller automatically executes your experiment, returns measured training OOF evidence,
asks you to reflect, and calls you again with that memory. You decide the next hypothesis and
revision; there is no prewritten list of experiments. Return only the requested structured JSON.
Use the supplied training evidence, never invent measurements or consult external sources/tools.
The action menu is fixed for this implementation: inputs, estimator/target per expert, routing.
All inputs are historically observed data; OOF gains are development evidence, not independent proof.
Do not change labels, selection metrics or the scientific task to manufacture success.
Propose informative untried configurations. Repeating a known spec uses cache and spends a cycle.
Each proposal must explain how measured previous feedback motivates the change and what falsifies it.
For a proposal, experts is a list of {route,model,target}; omitted routes fall back to the global model.
For reflection, acknowledge deterministic guard/metric results and subgroup tradeoffs. A guard failure
cannot be called an eligible win. Failed execution yields no scientific evidence. Choose continue
with a concrete next focus, or stop with an evidence-based reason when no useful next experiment exists.
Do not stop merely to ask a human to run the next iteration; the controller handles continuation.
Obey continuation_policy: while minimum_pending is true, propose an untried valid configuration
and reflect with continue. Prior run stop messages are historical and superseded by this policy.
Failure to beat the incumbent does not exhaust the search space. Test informative alternatives
across the allowed menu, isolate plausible changes, and do not repeat known specifications.
Respect minimum_MAE_gain_K when describing an eligible improvement. Never claim the entire menu
is exhausted from a small sample of experiments. Negative evidence is still worth recording.
Budget and stagnation stopping are enforced by the controller. Do not claim new superconductors.
'''
        prompt=instructions+'\nPHASE: '+phase+'\nSTATE AND EVIDENCE:\n'+json.dumps(context,ensure_ascii=False,allow_nan=False)
        (folder/'prompt.txt').write_text(prompt,encoding='utf-8')
        empty=self.root/'empty';empty.mkdir(exist_ok=True)
        command=[self.executable,'--no-daemon','-a','never','exec','--skip-git-repo-check','--ephemeral','--ignore-user-config','--ignore-rules','--strict-config','-m',self.model,'-s','read-only','-c','model_reasoning_effort="medium"','-c','project_doc_max_bytes=0','-c','skills.max_context_tokens=1','-c','web_search="disabled"','-c','mcp_servers={}','--enable','skip_host_skill_discovery','--enable','code_mode_host']
        for flag in DISABLED:command+=['--disable',flag]
        command+=['--json','--color','never','--output-schema',str(folder/'schema.json'),'-o',str(folder/'response.json'),'-C',str(empty),'-']
        env=os.environ.copy()
        for key in ['OPENAI_API_KEY','OPENAI_BASE_URL','AZURE_OPENAI_API_KEY','AZURE_OPENAI_ENDPOINT','OPENAI_ORG_ID','OPENAI_PROJECT_ID']:env.pop(key,None)
        env.update(PYTHONIOENCODING='utf-8',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
        rc=run_child(command,self.root,folder,timeout,prompt,env,tick)
        events=[json.loads(l) for l in (folder/'stdout.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
        tools=[x['item'] for x in events if x.get('type')=='item.completed' and x.get('item',{}).get('type') not in ['agent_message','reasoning','error']]
        completed=[x for x in events if x.get('type')=='turn.completed'];errors=[x for x in events if x.get('type') in ['error','turn.failed']]
        receipt={'exit_code':rc,'model_requested':self.model,'completed':rc==0 and len(completed)==1 and not errors and not tools,'native_tool_events':tools,'usage':completed,'errors':errors}
        write_json(folder/'receipt.json',receipt)
        if not receipt['completed']:raise RuntimeError('Model call incomplete or attempted an unavailable tool; inspect call receipt')
        return self.decode(phase,folder)

    @staticmethod
    def decode(phase,folder):
        result=read_json(Path(folder)/'response.json')
        if phase=='propose' and result.get('specification'):
            spec=result['specification'];items=spec['experts']
            if len({x['route'] for x in items})!=len(items):raise ValueError('Duplicate expert route')
            spec['experts']={x['route']:{'model':x['model'],'target':x['target']} for x in items}
        return result

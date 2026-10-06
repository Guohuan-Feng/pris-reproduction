"""Optional P5 honest nested residual evaluator. Import/preflight never fit.

Base: unchanged current-parser E011/old42. Outer predictions: completed M0
cache. Outer OOF contexts use fresh inner GroupKFold2. The fulltraining context
reuses the proven identical completed M0 inner OOF only to correct validation.
Corrector: joint Ridge(alpha=10, fit_intercept=True), only hasN/hasO inputs.
The separately registered real Agent may accept or refuse this fixed proposal.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parent
PARENT = ROOT.parents[1]
M0_ROOT = ROOT.parent/"parser_control"
M0_ADAPTER_SHA = "6d67c75194b8cfdf2a00e2ca1eb502064b450004c59011bb45a8e85903dd7f78"
M0_SOURCES = ("control_backend.py","evaluation_adapter.py","science_server.py","run_session.py","launch_control.py")
SPEC = {"estimator":"e011_tree","feature_set":"old42"}
CORRECTOR = {"estimator":"Ridge","alpha":10.0,"fit_intercept":True,"feature_names":["has_N","has_O"],"clip_targets":False,"clip_predictions":False}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for part in iter(lambda:stream.read(1024*1024),b""):h.update(part)
    return h.hexdigest()


def jsha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(",", ":")).encode("utf-8")).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _module(path,name):
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,path)
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module
        spec.loader.exec_module(module)
    return sys.modules[name]


def _m0_adapter(m0_root):
    path=Path(m0_root)/"evaluation_adapter.py"
    if sha(path)!=M0_ADAPTER_SHA:raise ValueError("frozen M0 adapter SHA differs")
    return _module(path,"_p5_m0_adapter_"+jsha(str(path.resolve()))[:16])


def _parent_module():
    return _module(PARENT/"pilot_evaluation.py","_p5_frozen_parent_evaluator")


def _valid(receipt):
    copy=deepcopy(receipt);expected=copy.pop("receipt_sha256",None)
    return expected is not None and expected==jsha(copy)


def _cache(ctx,m0_root,expected_registration_sha):
    """Hash-verify M0 and align cache. Cached truth is audit-only, never training."""
    m0_root=Path(m0_root).resolve()
    if sha(m0_root/"registration.json")!=expected_registration_sha:raise ValueError("M0 registration changed")
    registration=load(m0_root/"registration.json")
    if set(registration["source_hashes"])!=set(M0_SOURCES) or {name:sha(m0_root/name) for name in M0_SOURCES}!=registration["source_hashes"]:
        raise ValueError("M0 frozen source changed")
    state=load(m0_root/"state/research_state.json")
    if state["registration_sha256"]!=expected_registration_sha or state["status"]!="complete" or state.get("active_operation"):
        raise ValueError("M0 must be complete and inactive")
    if any(state["counters"][name]!=15 for name in ("base_fits_reserved","fit_started","fit_completed")) or state["counters"]["experiments"]!=1:
        raise ValueError("M0 ledger is not15 complete")
    files={name:sha(m0_root/"experiments/M0"/name) for name in ("result.json","validation_predictions.csv.gz","internal_oof_predictions.csv.gz","folds.json","base_fit_events.jsonl","adapter_provenance.json")}
    if any(state["files"][name]["sha256"]!=value for name,value in files.items()):raise ValueError("M0 completed cache file changed")
    result=load(m0_root/"experiments/M0/result.json")
    if result["id"]!="M0" or result["spec"]!=SPEC or any(result[name]!=15 for name in ("learner_fits","fit_started","fit_completed")):
        raise ValueError("M0 cached model differs")
    adapter=_m0_adapter(m0_root)
    current=adapter.preflight(ctx)
    provenance=load(m0_root/"experiments/M0/adapter_provenance.json")
    if current!=provenance["preflight"] or current!=registration["matched_control_preflight"]:
        raise ValueError("current Context old42/targets/folds/params differs from completed M0")
    fresh_parent=adapter.collect_parent_provenance(m0_root.parents[1],registration["parent_protocol_sha256"],require_four_complete=True)
    if fresh_parent!=provenance["parent_provenance"] or fresh_parent!=registration["parent_provenance"]:
        raise ValueError("parent inputs/results/source chain changed")
    if sha(m0_root.parents[1]/"controller_outcome.json")!=registration["parent_outcome_sha256"] or sha(m0_root.parents[1]/"reporting/parser_semantics_review.json")!=registration["parser_audit_sha256"]:
        raise ValueError("M0 parent outcome or parser trigger changed")
    if not (m0_root/"decision.json").exists():raise ValueError("M0 actual Agent reflection required before P5 preflight")
    directory=m0_root/"experiments/M0"
    val=pd.read_csv(directory/"validation_predictions.csv.gz",index_col="material_id",float_precision="round_trip")
    oof=pd.read_csv(directory/"internal_oof_predictions.csv.gz",index_col="material_id",float_precision="round_trip")
    for frame,positions in ((val,ctx.val),(oof,ctx.train)):
        if not frame.index.is_unique or set(frame.index)!=set(ctx.X.index[positions]) or len(frame)!=len(positions):raise ValueError("M0 cache ID coverage differs")
        aligned=frame.loc[ctx.X.index[positions]]
        if not np.isfinite(aligned[["truth","prediction"]].to_numpy(float)).all() or not np.array_equal(aligned.truth.to_numpy(float),ctx.y.iloc[positions].to_numpy(float)):
            raise ValueError("M0 cache truth/prediction alignment audit failed")
    if not np.array_equal(oof.loc[ctx.X.index[ctx.train],"fold"].to_numpy(),ctx.folds.loc[ctx.X.index[ctx.train]].to_numpy()):raise ValueError("M0 OOF fold cache differs")
    frozen_folds=load(directory/"folds.json")
    contexts=[{"role":"validation","train":np.asarray(ctx.train,dtype=int),"heldout":np.asarray(ctx.val,dtype=int),"cached":val,"cached_inner_oof":oof,"cached_inner_fold_sources":frozen_folds["folds"]}]
    outer,_=ctx.ev.fixed_folds(ctx.meta,ctx.train,ctx.folds)
    for fold,(a,b) in enumerate(outer):
        saved=frozen_folds["folds"][fold]
        if saved["fold"]!=fold or saved["train_ids"]!=ctx.X.index[a].astype(str).tolist() or saved["evaluation_ids"]!=ctx.X.index[b].astype(str).tolist():raise ValueError("M0 cached base training/evaluation IDs differ")
        contexts.append({"role":f"OOF_{fold}","train":np.asarray(a,dtype=int),"heldout":np.asarray(b,dtype=int),"cached":oof})
    proof={"M0_registration_sha256":expected_registration_sha,"M0_source_hashes":registration["source_hashes"],"M0_files":files,"M0_decision_sha256":sha(m0_root/"decision.json"),"M0_preflight_sha256":current["receipt_sha256"],"fixed_outer_fold_id_sha256":current["fixed_outer_fold_id_sha256"],"parent_provenance_sha256":fresh_parent["receipt_sha256"],"parent_protocol_sha256":registration["parent_protocol_sha256"],"cached_outer_base_fits":15,"cached_outer_new_fits":0,"cached_fulltraining_inner_base_fits":10,"cached_unique_base_fits":15,"cache_overlap":"fulltraining inner10 are the same two M0 outer blocks already included in unique15; never claim25","prediction_reader":"round_trip restores frozen %.17g outputs; scientific input Context remains defaultCSV","cached_truth_usage":"ID/value audit only; never passed to innerbase or residual model"}
    return contexts,proof


def _inner_plan(ctx,frame,contexts):
    plans=[];total=0
    for context in contexts:
        positions=np.asarray(sorted(context["train"].tolist(),key=lambda i:str(ctx.X.index[i])),dtype=int)
        groups=ctx.meta.iloc[positions].chemical_system.astype(str).to_numpy()
        if len(set(groups))<2:raise ValueError("inner GroupKFold needs at least2 chemical_system groups")
        folds=[];coverage=np.zeros(len(ctx.X),dtype=int)
        for fold,(a,b) in enumerate(GroupKFold(n_splits=2,shuffle=False).split(positions,groups=groups)):
            train,held=positions[a],positions[b]
            if set(train)&set(held) or set(ctx.meta.iloc[train].chemical_system)&set(ctx.meta.iloc[held].chemical_system):raise ValueError("inner split group/row leakage")
            if (set(train)|set(held))!=set(positions) or set(train)&set(context["heldout"]) or set(held)&set(context["heldout"]):raise ValueError("inner labels escape their outertraining context")
            count=int(ctx.ev.legacy.estimate_fit_count(frame.iloc[train].loc[:,ctx.ev.old_columns],ctx.ev.e011_spec))
            if count<1:raise ValueError("invalid inner base fit estimate")
            train_ids=ctx.X.index[train].astype(str).tolist();heldout_ids=ctx.X.index[held].astype(str).tolist()
            cache_fold=None
            if context["role"]=="validation":
                matches=[saved["fold"] for saved in context["cached_inner_fold_sources"] if saved["train_ids"]==train_ids and saved["evaluation_ids"]==heldout_ids]
                if len(matches)!=1:raise ValueError("fulltraining inner GroupKFold IDs do not exactly match M0 cache")
                cache_fold=int(matches[0])
            new_count=0 if cache_fold is not None else count
            total+=new_count;coverage[held]+=1
            folds.append({"fold":fold,"train_positions":train.tolist(),"heldout_positions":held.tolist(),"train_ids":train_ids,"heldout_ids":heldout_ids,"train_groups_sha256":jsha(sorted(set(ctx.meta.iloc[train].chemical_system.astype(str)))),"heldout_groups_sha256":jsha(sorted(set(ctx.meta.iloc[held].chemical_system.astype(str)))),"estimated_base_fits":count,"new_base_fits":new_count,"cached_M0_outer_fold":cache_fold})
        if not np.all(coverage[positions]==1) or np.any(coverage[np.setdiff1d(np.arange(len(ctx.X)),positions)]):raise ValueError("inner OOF must cover outertraining exactlyonce")
        plans.append({"role":context["role"],"train_positions":positions.tolist(),"heldout_positions":context["heldout"].tolist(),"train_ids_sha256":jsha(ctx.X.index[positions].astype(str).tolist()),"heldout_ids_sha256":jsha(ctx.X.index[context["heldout"]].astype(str).tolist()),"inner_folds":folds,"inner_source":"verified M0 fulltrain OOF, validation correction only" if context["role"]=="validation" else "fresh inner GroupKFold within this outertraining only","inner_coverage":"each context training row exactlyonce; outerheldout excluded","ridge_new_fits":1})
    return plans,total


def preflight(ctx,m0_root=M0_ROOT,expected_m0_registration_sha256=None):
    if expected_m0_registration_sha256 is None:raise ValueError("M0 registration SHA required before P5")
    contexts,cache=_cache(ctx,m0_root,expected_m0_registration_sha256)
    frame=ctx.augmented();plans,inner=_inner_plan(ctx,frame,contexts)
    total=inner+3
    if total>45:raise ValueError("P5 exceeds original96 minus51 used")
    _conditions(ctx,np.asarray(ctx.train,dtype=int))
    receipt={"schema_version":1,"id":"P5","spec":deepcopy(SPEC),"corrector":deepcopy(CORRECTOR),"adapter_source_sha256":sha(__file__),"M0_cache_proof":cache,"inner_GroupKFold":{"n_splits":2,"shuffle":False,"groups":"chemical_system","order":"sorted material IDs inside each outertraining context","fresh_outertraining_contexts_only":True,"fulltraining_cache_only_after_exact_ordered_train_and_eval_ID_proof":True},"contexts":plans,"expected_new_inner_base_fits":inner,"expected_new_residual_fits":3,"expected_new_learner_fits":total,"already_used_shared_fits":51,"combined_expected_fits":51+total,"original_fit_limit":96,"combined_completed_experiment_count_if_executed":6,"fitting_performed":False,"residual_target":"context y minus honest innerOOF; outer OOF contexts fresh only, fulltrain M0 OOF cache only for715 validation"}
    receipt["receipt_sha256"]=jsha(receipt)
    return receipt


def _conditions(ctx,positions):
    return np.column_stack([(ctx.X.iloc[positions]["comp_fraction_Z007"].to_numpy(float)>0).astype(float),(ctx.X.iloc[positions]["comp_fraction_Z008"].to_numpy(float)>0).astype(float)])


def evaluate(ctx,*,expected_preflight,m0_root=M0_ROOT,event_callback=None):
    """Called only by independently registered Agent after accepting the fixed plan."""
    if not _valid(expected_preflight):raise ValueError("P5 requires an immutable registered preflight")
    current=preflight(ctx,m0_root,expected_preflight["M0_cache_proof"]["M0_registration_sha256"])
    if current!=expected_preflight:raise ValueError("P5 inputs/source/cache/innerfold plan changed after registration")
    contexts,_=_cache(ctx,m0_root,current["M0_cache_proof"]["M0_registration_sha256"])
    frame=ctx.augmented();targets=ctx.ev.legacy._target_array(ctx.y,ctx.X.index)
    audit=_parent_module().FitAudit(event_callback);started=time.perf_counter()
    output_parts=[];residual_parts=[];correctors=[];fold_assignments=[];inner_summaries=[]
    for context,plan in zip(contexts,current["contexts"]):
        train=np.asarray(plan["train_positions"],dtype=int);held=np.asarray(plan["heldout_positions"],dtype=int)
        inner_predictions=pd.Series(index=ctx.X.index[train],dtype=float)
        coverage=np.zeros(len(ctx.X),dtype=int)
        assignment=[]
        for fold in plan["inner_folds"]:
            a=np.asarray(fold["train_positions"],dtype=int);b=np.asarray(fold["heldout_positions"],dtype=int)
            if fold["cached_M0_outer_fold"] is not None:
                if plan["role"]!="validation":raise RuntimeError("fulltraining cache cannot train an outerOOF corrector")
                prediction=context["cached_inner_oof"].loc[frame.index[b],["prediction"]]
                training_summary={"cached":True,"M0_outer_fold":fold["cached_M0_outer_fold"],"new_fits":0,"input_spec_training_ID_proof":True}
            else:
                model=ctx.ev.fit_training_block(frame.iloc[a],targets[a],ctx.meta.iloc[a],deepcopy(SPEC),audit,f"{plan['role']}_inner_{fold['fold']}")
                prediction=model.predict(frame.iloc[b])
                training_summary=model.training_summary
            if not prediction.index.equals(frame.index[b]) or not np.isfinite(prediction.prediction.to_numpy(float)).all():raise RuntimeError("inner prediction ID/finite check failed")
            inner_predictions.loc[frame.index[b]]=prediction.prediction.to_numpy(float);coverage[b]+=1
            assignment.extend({"material_id":str(mid),"inner_fold":fold["fold"]} for mid in frame.index[b])
            inner_summaries.append({"context":plan["role"],"inner_fold":fold["fold"],"training_summary":training_summary,"train_ids_sha256":jsha(fold["train_ids"]),"heldout_ids_sha256":jsha(fold["heldout_ids"])})
        if not np.all(coverage[train]==1) or np.any(coverage[held]) or not np.isfinite(inner_predictions.to_numpy()).all():raise RuntimeError("fresh innerOOF incomplete or crosses heldout boundary")
        residual=targets[train]-inner_predictions.loc[frame.index[train]].to_numpy(float)
        z=_conditions(ctx,train);zh=_conditions(ctx,held)
        ridge=Ridge(alpha=10.0,fit_intercept=True)
        audit.fit(lambda:ridge.fit(z,residual),{"role":plan["role"],"component":"joint_N_O_residual_Ridge","estimator":"Ridge","alpha":10.0,"fit_intercept":True,"feature_names":["has_N","has_O"],"train_rows":len(train),"train_id_sha256":plan["train_ids_sha256"],"residual_source":plan["inner_source"]})
        correction=np.asarray(ridge.predict(zh),dtype=float)
        base=context["cached"].loc[frame.index[held],"prediction"].to_numpy(float)
        corrected=base+correction
        if not np.isfinite(corrected).all():raise RuntimeError("nonfinite residual-adjusted predictions")
        output=pd.DataFrame({"chemical_system":ctx.meta.iloc[held].chemical_system.astype(str).to_numpy(),"cached_base_prediction":base,"residual_correction":correction,"prediction":corrected},index=frame.index[held])
        if plan["role"].startswith("OOF_"):output["fold"]=int(plan["role"].split("_")[1])
        output_parts.append((plan["role"],held,output))
        residual_parts.append(pd.DataFrame({"context":plan["role"],"truth_training_only":targets[train],"innerOOF_prediction":inner_predictions.loc[frame.index[train]].to_numpy(float),"training_residual":residual,"has_N":z[:,0],"has_O":z[:,1]},index=frame.index[train]))
        correctors.append({"context":plan["role"],"alpha":10.0,"fit_intercept":True,"coefficient_has_N_has_O":np.asarray(ridge.coef_,dtype=float).tolist(),"intercept":float(ridge.intercept_),"train_ids_sha256":plan["train_ids_sha256"],"training_residual_float64_le_sha256":hashlib.sha256(residual.astype("<f8",copy=False).tobytes()).hexdigest(),"residual_source":plan["inner_source"],"target_clipped":False,"prediction_clipped":False})
        fold_assignments.append({"context":plan["role"],"assignments":sorted(assignment,key=lambda row:row["material_id"]),"plan":plan})
    completed=sum(event["phase"]=="completed" for event in audit.events);fit_started=sum(event["phase"]=="started" for event in audit.events)
    if completed!=fit_started or completed!=current["expected_new_learner_fits"]:raise RuntimeError("P5 actual component fits differ from frozen reservation")
    # Every predictor/corrector is frozen above. Heldout truth is attached now,
    # never supplied to any base/ridge fit or condition feature construction.
    for _,held,output in output_parts:output.insert(1,"truth",targets[held])
    validation=output_parts[0][2]
    oof=pd.concat([part[2] for part in output_parts[1:]]).loc[ctx.X.index[ctx.train]]
    if not np.array_equal(oof.fold.to_numpy(),ctx.folds.loc[oof.index].to_numpy()):raise RuntimeError("final P5 outer OOF assignment changed")
    vm=ctx.ev.legacy.regression_metrics(validation.truth,validation.prediction);om=ctx.ev.legacy.regression_metrics(oof.truth,oof.prediction)
    fold_summaries=[{"fold":int(role.split("_")[1]),"train_rows":len(plan["train_positions"]),"evaluation_rows":len(held),"train_id_sha256":plan["train_ids_sha256"],"evaluation_id_sha256":plan["heldout_ids_sha256"],"metrics":ctx.ev.legacy.regression_metrics(output.truth,output.prediction)} for (role,held,output),plan in zip(output_parts[1:],current["contexts"][1:])]
    result={"id":"P5","spec":deepcopy(SPEC),"residual_corrector":deepcopy(CORRECTOR),"validation":vm,"OOF":om,"selection_score":.5*(vm["MAE_eV_atom"]+om["MAE_eV_atom"]),"validation_diagnostics":ctx.ev.diagnostics(frame.iloc[ctx.val],validation.truth,validation.prediction),"OOF_diagnostics":ctx.ev.diagnostics(frame.iloc[ctx.train],oof.truth,oof.prediction),"fold_summaries":fold_summaries,"learner_fits":completed,"fit_started":fit_started,"fit_completed":completed,"new_inner_base_fits":current["expected_new_inner_base_fits"],"new_residual_ridge_fits":3,"cached_outer_base_fits":15,"cached_validation_inner_fits":10,"cached_unique_base_fits":15,"cached_outer_new_fits":0,"combined_shared_fits":51+completed,"elapsed_seconds":time.perf_counter()-started,"preflight_sha256":current["receipt_sha256"],"adapter_source_sha256":current["adapter_source_sha256"],"fixed_fold_id_sha256":current["M0_cache_proof"]["fixed_outer_fold_id_sha256"],"scope":"Adaptive development N/O residual calibration, not independent confirmation, a new structural descriptor or physical mechanism"}
    folds={"outer_assignment_source":"unchanged completed M0; fresh inner GroupKFold per context","contexts":fold_assignments}
    return {"result":result,"predictions":validation,"oof_predictions":oof,"fit_events":audit.events,"folds":folds,"ridge_correctors":correctors,"training_residuals":pd.concat(residual_parts),"adapter_provenance":{"preflight":current,"cache_truth_usage":"alignment audit only","outer_heldout_truth_attached_after_all_fits":True,"inner_training_summary":inner_summaries}}


def save(bundle,output_dir):
    directory=Path(output_dir).resolve()
    if not directory.is_relative_to(ROOT.resolve()) or directory==ROOT.resolve():raise ValueError("P5 output must stay inside nested_residual subdirectory")
    extra=("ridge_correctors.json","training_residuals.csv.gz","adapter_provenance.json")
    standard=("result.json","validation_predictions.csv.gz","internal_oof_predictions.csv.gz","folds.json","base_fit_events.jsonl")
    if any((directory/name).exists() for name in (*extra,*standard)):raise FileExistsError("P5 artifact exists; no overwrite or fit retry")
    if bundle["result"]["id"]!="P5":raise ValueError("P5 bundle required")
    directory.mkdir(parents=True,exist_ok=True)
    (directory/extra[0]).write_text(json.dumps(bundle["ridge_correctors"],ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    bundle["training_residuals"].to_csv(directory/extra[1],index=True,index_label="material_id",float_format="%.17g",compression={"method":"gzip","mtime":0})
    (directory/extra[2]).write_text(json.dumps(bundle["adapter_provenance"],ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    files=_parent_module().save_evaluation(bundle,directory)
    files.update({name:{"path":str(directory/name),"sha256":sha(directory/name)} for name in extra})
    return files

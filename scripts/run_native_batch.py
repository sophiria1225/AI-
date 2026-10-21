"""Run a fixed calibration batch after its prerequisite, with aggregate progress."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from run_context_comparison import write_json
from watch_context_pilot import collect
from watch_pro_comparison import gh_api

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "sophiria1225/AI-"
ISSUE = 36
MARKER = "<!-- harness-native-baseline:P8_batch_v01 -->"
PHASES = {
    "P8": {"issue": 36, "arm": "native_full", "batch": "P8_batch_v01", "before": "P7", "trials": 2},
    "P10": {"issue": 42, "arm": "native_roles", "batch": "P10_batch_v01", "before": "P9", "trials": 2},
    "P11": {"issue": 44, "arm": "native_roles", "batch": "P11_batch_v01", "before": "P10", "trials": 4},
    "P12": {"issue": 48, "arm": "native_recent", "batch": "P12_batch_v01", "before": "P11", "trials": 4},
    "P13": {"issue": 51, "arm": "native_focus", "batch": "P13_batch_v01", "before": "P12", "trials": 4},
    "P14": {"issue": 54, "arm": "native_ledger", "batch": "P14_batch_v01", "before": "P13", "trials": 4},
    "P18": {"issue": 86, "arm": "native_roles", "batch": "P18_batch_v01", "before": "P17", "trials": 4},
    "P22": {"issue": 102, "arm": "native_roles", "batch": "P22_batch_v01", "before": "P21", "trials": 6},
    "P24": {"issue": 115, "arm": "native_guided", "batch": "P24_batch_v01", "before": "P22", "trials": 6},
    "P25": {"issue": 120, "arm": "native_guided", "batch": "P25_batch_v01", "before": "P24", "trials": 4},
    "P26": {"issue": 128, "arm": "native_guided", "batch": "P26_batch_v01", "before": "P25", "trials": 1},
    "P29": {"issue": 140, "arm": "code_guided", "batch": "P29_batch_v01", "before": "P28", "trials": 4},
    "P28": {"issue": 138, "arm": "code_guided", "batch": "P28_batch_v01", "before": "P27", "trials": 4},
    "P27": {"issue": 132, "arm": "code_guided", "batch": "P27_batch_v01", "before": "P26", "trials": 4},
}


def check_frozen(frozen):
    for name, digest in frozen["source_hashes"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError("frozen source changed: " + name)


def validate_schedule(plan):
    phase = plan["phase"]
    if (phase not in PHASES or plan["batch_id"] != PHASES[phase]["batch"]
            or len(plan["run_order"]) != PHASES[phase]['trials'] or plan['arms'] != [PHASES[phase]['arm']]
            or any(row[1] != PHASES[phase]['arm'] for row in plan['run_order'])):
        raise ValueError("only the fixed calibration schedule is supported")
    if phase in ("P11", "P12", "P13", "P14", "P18", "P22", "P24", "P25", "P27", "P28", "P29"):
        selection_file = ('reports/P18_public_task_selection.json' if phase in ('P25','P27','P28','P29') else
                          'reports/P22_public_task_selection.json' if phase == 'P24' else
                          'reports/'+phase+'_public_task_selection.json' if phase in ('P18', 'P22')
                          else 'reports/P11_public_task_selection.json')
        selected = json.loads((ROOT / selection_file).read_text())
        ids = [row['task_id'] for row in selected['selected']]
        if (plan['task_ids'] != ids or [row[0] for row in plan['run_order']] != ids
                or len({row[2] for row in plan['run_order']}) != len(ids)):
            raise ValueError('the additional baseline must preserve selected scenarios and order')
        if phase in ('P22', 'P24'):
            reservation = json.loads((ROOT/'reports/letter_scenario_reservation_20261021.json').read_text())
            if (ids != [sid+'_1' for sid in reservation['further_development']]
                    or set(ids) & set(reservation['reserved_variant_one_tasks'])):
                raise ValueError('P22/P24 must stay within the six development scenarios')


def check_p22_activation(plan):
    """Preparation must not silently schedule generation before P21 review."""
    if plan['phase'] != 'P22':
        return
    record = json.loads((ROOT/'reports/P22_activation_v01.json').read_text())
    primary = ROOT/'reports/P21_export_diagnostic_summary.json'
    if (record.get('decision') != 'run_six_full_history_development_tasks'
            or not record.get('why') or not record.get('alternatives')
            or hashlib.sha256(primary.read_bytes()).hexdigest() != record.get('p21_primary_sha256')):
        raise ValueError('P22 needs an explicit decision tied to the completed P21 evaluation')
    result = json.loads(primary.read_text())
    if result['phase'] != 'P21' or result['model_calls'] != 6 or result['audit_errors']:
        raise ValueError('P21 primary review is incomplete')


def check_p24_activation(plan):
    """Do not turn a generic instruction contrast into a changed tool/budget run."""
    if plan['phase'] != 'P24':
        return
    from run_native_appworld import system_prompt_for
    system_prompt_for(plan)
    record = json.loads((ROOT/'reports/P24_activation_v01.json').read_text())
    if (record.get('decision') != 'run_six_with_generic_official_guidance'
            or not record.get('why') or not record.get('alternatives')):
        raise ValueError('P24 needs a reviewed decision')
    for path, expected in record['prerequisite_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != expected:
            raise ValueError('P24 prerequisite changed')
    result = json.loads((ROOT/'reports/P22_additional_baseline_summary.json').read_text())
    diagnosis = json.loads((ROOT/'reports/P22_public_trace_diagnostics.json').read_text())
    if (result['pending'] or result['audit_errors'] or len(result['trials']) != 6
            or not diagnosis['all_six_reviewed']):
        raise ValueError('P22 full review is incomplete')
    old = json.loads((ROOT/'configs/P22_additional_baseline_v01.json').read_text())
    for key in ('model', 'model_selection', 'task_ids', 'seed', 'agent_temperature',
                'max_calls', 'max_api_requests', 'max_wall_seconds', 'max_total_tokens',
                'max_output_tokens', 'observation_page_characters',
                'history_representation', 'discovery_policy',
                'max_checkpoint_new_bytes_per_boundary', 'max_checkpoint_object_bytes'):
        if plan[key] != old[key]:
            raise ValueError('P24 must preserve P22: ' + key)
    if 'ordinary_compute' in plan:
        raise ValueError('P24 does not add a computation tool')


def check_p25_activation(plan):
    """Retain all P18 cases and the already fixed P24 generic instructions."""
    if plan['phase'] != 'P25':
        return
    from run_native_appworld import system_prompt_for, GENERAL_GUIDANCE
    from compare_generic_guidance import MATCHED_KEYS
    system_prompt_for(plan)
    record = json.loads((ROOT/'reports/P25_activation_v01.json').read_text())
    if (record.get('decision') != 'run_four_p18_with_fixed_generic_guidance'
            or not record.get('why') or not record.get('alternatives')
            or record.get('guidance_sha256') != hashlib.sha256(GENERAL_GUIDANCE.encode()).hexdigest()):
        raise ValueError('P25 requires its reviewed decision and unchanged generic guidance')
    for path, expected in record['prerequisite_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != expected:
            raise ValueError('P25 prerequisite changed: '+path)
    previous = json.loads((ROOT/'reports/P24_guidance_baseline_summary.json').read_text())
    review = json.loads((ROOT/'reports/P24_interpretation.json').read_text())
    if (previous['pending'] or previous['audit_errors'] or len(previous['trials']) != 6
            or not review['all_six_reviewed']):
        raise ValueError('P24 full review is incomplete')
    old = json.loads((ROOT/'configs/P18_additional_baseline_v01.json').read_text())
    for key in MATCHED_KEYS:
        if plan[key] != old[key]:
            raise ValueError('P25 must preserve P18: '+key)
    if 'ordinary_compute' in plan:
        raise ValueError('P25 does not add a computation tool')
    reserved = json.loads((ROOT/'reports/letter_scenario_reservation_20261021.json').read_text())
    if set(plan['task_ids']) & set(reserved['reserved_variant_one_tasks']):
        raise ValueError('P25 must not consume reserved confirmation tasks')


def check_p26_activation(plan):
    """One post-hoc budget diagnostic, never a task-specific prompt repair."""
    if plan['phase'] != 'P26':
        return
    from run_native_appworld import system_prompt_for, GENERAL_GUIDANCE
    from compare_generic_guidance import MATCHED_KEYS
    record = json.loads((ROOT/'reports/P26_activation_v01.json').read_text())
    if (record.get('decision') != 'one_photo_case_api_ceiling_160'
            or not record.get('why') or not record.get('alternatives')
            or record.get('guidance_sha256') != hashlib.sha256(GENERAL_GUIDANCE.encode()).hexdigest()):
        raise ValueError('P26 requires its reviewed decision and unchanged guidance')
    for path, expected in record['prerequisite_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != expected:
            raise ValueError('P26 prerequisite changed: '+path)
    old = json.loads((ROOT/'configs/P25_guidance_transfer_v01.json').read_text())
    previous = json.loads((ROOT/'reports/P25_guidance_transfer_summary.json').read_text())
    review = json.loads((ROOT/'reports/P25_interpretation.json').read_text())
    if (previous['pending'] or previous['audit_errors'] or len(previous['trials']) != 4
            or not review['all_four_reviewed']):
        raise ValueError('P25 full review is incomplete')
    if (plan['task_ids'] != old['task_ids'][:1]
            or plan['run_order'] != [[old['task_ids'][0], 'native_guided', 'P26_01_GUIDED']]
            or plan['max_api_requests'] != 160
            or plan['wait_for_native_batch'] != old['batch_id']):
        raise ValueError('P26 is only the first prior case with API ceiling 160')
    for key in MATCHED_KEYS:
        if key not in ('task_ids', 'max_api_requests') and plan[key] != old[key]:
            raise ValueError('P26 must preserve P25: '+key)
    if system_prompt_for(plan) != system_prompt_for(old) or 'ordinary_compute' in plan:
        raise ValueError('P26 does not change the prompt or computation interface')


def check_p27_activation(plan):
    """Start the full code-action contrast only after the prior cap diagnostic."""
    if plan['phase'] != 'P27':
        return
    from run_native_appworld import GENERAL_GUIDANCE
    from compare_generic_guidance import MATCHED_KEYS
    from run_code_appworld import code_system_prompt
    from code_agent_interface import CODE_GUIDE
    record = json.loads((ROOT/'reports/P27_activation_v01.json').read_text())
    if (record.get('decision') != 'all_four_known_tasks_with_code_api_interface'
            or not record.get('why') or not record.get('alternatives')
            or record.get('guidance_sha256') != hashlib.sha256(GENERAL_GUIDANCE.encode()).hexdigest()
            or record.get('code_guide_sha256') != hashlib.sha256(CODE_GUIDE.encode()).hexdigest()
            or record.get('system_prompt_sha256') != hashlib.sha256(code_system_prompt().encode()).hexdigest()):
        raise ValueError('P27 requires reviewed fixed instructions')
    for path, expected in record['prerequisite_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != expected:
            raise ValueError('P27 prerequisite changed: '+path)
    previous=json.loads((ROOT/'reports/P26_photo_budget_summary.json').read_text())
    review=json.loads((ROOT/'reports/P26_interpretation.json').read_text())
    if previous['pending'] or previous['audit_errors'] or not review['all_one_reviewed']:
        raise ValueError('P26 full review is incomplete')
    old=json.loads((ROOT/'configs/P25_guidance_transfer_v01.json').read_text())
    for key in MATCHED_KEYS:
        if plan[key] != old[key]:
            raise ValueError('P27 must preserve P25: '+key)
    expected={task:160 if i==0 else 80 for i,task in enumerate(old['task_ids'])}
    if (plan.get('api_budget_by_task') != expected
            or plan.get('wait_for_native_batch') != 'P26_batch_v01'
            or plan.get('general_guidance_version') != old['general_guidance_version']
            or plan.get('code_interface_version') != 'public_api_python_v1'
            or 'ordinary_compute' in plan):
        raise ValueError('P27 only changes the declared code interface with matched task budgets')
    reserved=json.loads((ROOT/'reports/letter_scenario_reservation_20261021.json').read_text())
    if set(plan['task_ids']) & set(reserved['reserved_variant_one_tasks']):
        raise ValueError('P27 must not consume reserved confirmation tasks')


def public_body(rows, state):
    phase = state.get("phase", "P8")
    spec = PHASES[phase]
    marker = f"<!-- harness-native-baseline:{spec['batch']} -->"
    states = {
        "waiting": spec['before'] + "の終了待ち", "running": "実行中", "complete": f"{spec['trials']}試行の実行・評価処理が終了",
        "prerequisite_failed": "前段の状態を確認するため保留",
        "runtime_error": "実行エラーで停止", "server_lease_too_short": "サーバーの残稼働時間不足で未開始",
    }
    title = {"P29": "P29：課題内でPython変数を保持する通常方式の全４件比較",
             "P28": "P28：用意済みのPython関数の説明だけを補う全４件の比較",
             "P8": "P8：公開スキーマ・複数操作を使う全履歴基準",
             "P10": "P10：要求と結果の役割を保持する標準会話の全履歴基準",
             "P11": "P11：選定済みの追加4シナリオを同じ全履歴基準で観察",
             "P12": "P12：同じ4シナリオで直近履歴の保持と原文再読を比較",
             "P13": "P13：同じ接続でFOCUSに基づく保持方式と全費用を比較",
             "P14": "P14：通常の作業台帳と全更新費用を比較",
             "P18": "P18：未使用の４開発シナリオを全履歴基準で観察",
             "P22": "P22：予約済みの６開発シナリオを全履歴基準で観察",
             "P24": "P24：公式の一般指示を補い、同じ６開発課題で比較",
             "P25": "P25：同じ一般指示をP18の全４開発課題へ適用",
             "P26": "P26：写真整理１件のAPI上限だけを80から160へ変更",
             "P27": "P27：公開APIの取得・計算・次の操作をPythonで接続する通常方式"}[phase]
    lines = [marker, title, "",
             "| 課題 | 状態 | LLM呼出 | API要求 | 既知トークン | 使用量不明 | 独立評価 |",
             "|---|---|---:|---:|---:|---:|---|"]
    for row in rows:
        status = {"pending": "待機", "running": "実行中", "finished": "実行終了",
                  "evaluated": "評価済み", "evaluation_error": "評価要確認"}[row["status"]]
        success = row.get("success")
        if success is not None and type(success) is not bool:
            raise ValueError("invalid public evaluation")
        result = "未確定" if success is None else ("成功" if success else "未達")
        lines.append(f"| {int(row['task_number'])} | {status} | {int(row.get('calls', 0))} | "
                     f"{int(row.get('api_requests', 0))} | "
                     f"{int(row.get('tokens', 0)):,} | {int(row.get('unknown_usage_calls', 0))} | {result} |")
    lines += ["", states[state["status"]],
              ("各試行：80 LLM呼び出し・45万トークン・30分以内。写真整理は160 API、他３件は80 API。内側APIも個別計上し、失敗の自動再試行はしません。" if phase in ('P27','P28','P29') else
               f"各試行：80 LLM呼び出し・{160 if phase == 'P26' else 80} API要求・45万トークン・30分以内。未知費用は0とせず、失敗を自動再試行しません。"),
              "公式APIスキーマを利用した導入基準で、公式エージェントの完全再現・新手法・品質維持の主張ではありません。",
              "評価は終了後の別プロセスで行い、後続のモデル入力には返しません。",
              {"P8": "[事前仕様](https://github.com/sophiria1225/AI-/blob/research/appworld-api-calibration-20261021/docs/experiments/P8_native_baseline.md)",
               "P10": "[事前仕様](https://github.com/sophiria1225/AI-/blob/research/native-history-calibration-20261021/docs/experiments/P10_native_history.md)",
               "P11": "[事前仕様](https://github.com/sophiria1225/AI-/blob/research/p11-development-20261021/docs/experiments/P11_additional_baseline.md)",
               "P12": "[事前仕様](https://github.com/sophiria1225/AI-/blob/research/p11-observations-20261021/docs/experiments/P12_recent_window.md)",
               "P13": "[事前仕様](https://github.com/sophiria1225/AI-/blob/research/native-focus-comparison-20261021/docs/experiments/P13_native_focus.md)",
               "P14": "[事前仕様](https://github.com/sophiria1225/AI-/blob/research/p14-ledger-execution-20261021/docs/experiments/P14_native_ledger.md)",
               "P18": "[事前仕様](https://github.com/sophiria1225/AI-/blob/main/docs/experiments/P18_unseen_development.md)",
               "P22": "[事前仕様と実行条件](https://github.com/sophiria1225/AI-/blob/main/docs/experiments/P22_development_preparation.md)",
               "P24": "[一般指示の比較仕様](https://github.com/sophiria1225/AI-/blob/main/docs/experiments/P24_generic_guidance.md)",
               "P25": "[４件の比較仕様](https://github.com/sophiria1225/AI-/blob/main/docs/experiments/P25_guidance_transfer.md)",
               "P26": "[１件の予算診断](https://github.com/sophiria1225/AI-/blob/main/docs/experiments/P26_photo_budget.md)",
               "P27": "[コード実行型の比較仕様](https://github.com/sophiria1225/AI-/blob/main/docs/experiments/P27_code_execution.md)",
               "P28": "[関数説明だけの比較仕様](https://github.com/sophiria1225/AI-/blob/main/docs/experiments/P28_code_clarification.md)",
               "P29": "[課題内状態保持の比較仕様](https://github.com/sophiria1225/AI-/blob/main/docs/experiments/P29_stateful_execution.md)"}[phase]]
    return "\n".join(lines) + "\n"


def publish(body, state):
    spec = PHASES[state.get("phase", "P8")]
    issue = spec["issue"]
    marker = f"<!-- harness-native-baseline:{spec['batch']} -->"
    if not body.startswith(marker):
        raise ValueError("unexpected progress marker")
    endpoint = f"repos/{REPOSITORY}/issues/{issue}"
    if state.get("comment_id"):
        endpoint = f"repos/{REPOSITORY}/issues/comments/{int(state['comment_id'])}"
        previous = gh_api(endpoint)
        if (previous.get("issue_url") != f"https://api.github.com/repos/{REPOSITORY}/issues/{issue}"
                or not previous.get("body", "").startswith(marker)):
            raise ValueError("unexpected progress destination")
        result = gh_api(endpoint, method="PATCH", payload={"body": body})
    else:
        if gh_api(endpoint)["html_url"] != f"https://github.com/{REPOSITORY}/issues/{issue}":
            raise ValueError("unexpected Issue identity")
        result = gh_api(endpoint + "/comments", method="POST", payload={"body": body})
    state.update(comment_id=result["id"], comment_url=result["html_url"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--freeze-record", type=Path, required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    storage = args.storage_root.resolve()
    plan = json.loads(args.plan.read_text())
    frozen = json.loads(args.freeze_record.read_text())
    check_frozen(frozen)
    phase = plan["phase"]
    validate_schedule(plan)
    check_p22_activation(plan)
    check_p24_activation(plan)
    check_p25_activation(plan)
    check_p26_activation(plan)
    check_p27_activation(plan)
    from code_control_validation import validate as validate_code_control
    validate_code_control(plan)
    from stateful_code_validation import validate as validate_stateful_control
    validate_stateful_control(plan)
    out = storage / "records/context_pilot" / plan["batch_id"]
    out.mkdir(exist_ok=False)
    observer = out / "observer"
    observer.mkdir()
    write_json(out / "plan.json", plan)
    write_json(out / "freeze_record.json", frozen)
    state = {
        "status": "waiting", "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "completed": [], "active": None, "phase": phase,
    }
    last_publish, last_signature = 0, None

    def update(force=False):
        nonlocal last_publish, last_signature
        rows = collect(storage, plan["run_order"], observer)
        for row, (_, _, run_id) in zip(rows, plan["run_order"], strict=True):
            trial = storage / "records/context_pilot" / run_id
            source = trial / "summary.json"
            if not source.exists():
                source = trial / "progress.json"
            if source.exists():
                row["api_requests"] = json.loads(source.read_text()).get("api_requests", 0)
        state["rows"] = rows
        body = public_body(rows, state)
        (out / "progress.md").write_text(body)
        signature = (state["status"], state["active"],
                     [(r["status"], r.get("success")) for r in rows])
        if args.publish and (force or signature != last_signature
                             or time.monotonic() - last_publish >= 300):
            try:
                publish(body, state)
                state.pop("publish_error", None)
            except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                state["publish_error"] = type(exc).__name__
            last_publish, last_signature = time.monotonic(), signature
        state["updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json(out / "status.json", state)

    update()
    started = time.monotonic()
    prerequisite_dir, prerequisite_id = {
        "P8": ("memory_probe", plan.get("wait_for_probe")),
        "P10": ("cache_probe", plan.get("wait_for_cache_probe")),
        "P11": ("context_pilot", plan.get("wait_for_native_batch")),
        "P12": ("context_pilot", plan.get("wait_for_native_batch")),
        "P13": ("context_pilot", plan.get("wait_for_native_batch")),
        "P14": ("context_pilot", plan.get("wait_for_native_batch")),
        "P18": ("event_view_probe", plan.get("wait_for_contract_probe")),
        "P22": ("data_export_probe", plan.get("wait_for_export_probe")),
        "P24": ("context_pilot", plan.get("wait_for_native_batch")),
        "P25": ("context_pilot", plan.get("wait_for_native_batch")),
        "P26": ("context_pilot", plan.get("wait_for_native_batch")),
        "P27": ("context_pilot", plan.get("wait_for_native_batch")),
        "P28": ("context_pilot", plan.get("wait_for_native_batch")),
        "P29": ("context_pilot", plan.get("wait_for_native_batch")),
    }[phase]
    prerequisite_path = storage / "records" / prerequisite_dir / prerequisite_id / "status.json"
    while True:
        try:
            prerequisite = json.loads(prerequisite_path.read_text())
        except json.JSONDecodeError:
            # A different process may be replacing this short status file.
            time.sleep(1)
            continue
        if prerequisite["status"] == "complete":
            break
        if (prerequisite["status"] not in ("waiting", "running")
                or time.monotonic() - started > plan["max_wait_seconds"]):
            state["status"] = "prerequisite_failed"
            update(True)
            return 1
        update()
        time.sleep(30)
    try:
        check_frozen(frozen)
    except RuntimeError:
        state.update(status="runtime_error", error_type="FrozenSourceChanged")
        update(True)
        return 1
    lease_end = datetime.datetime.fromisoformat(plan["server_lease_end_utc"])
    remaining = (lease_end - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    if phase in ("P18", "P22", "P24", "P25", "P26", "P27", "P28", "P29"):
        from run_event_view_probe import lease_remaining
        runtime = json.loads((storage / '.runtime/model_server.json').read_text())
        command = subprocess.check_output(['ps', '-p', str(runtime['supervisor_pid']), '-o', 'command='], text=True)
        live_remaining, live_end = lease_remaining(runtime, command, datetime.datetime.now(datetime.timezone.utc))
        remaining = min(remaining, live_remaining)
        state['checked_server_lease_end_utc'] = live_end
    evaluation_reserve = 180 * (len(plan["run_order"]) + 1) if phase in ("P11", "P12", "P13", "P14", "P18", "P22", "P24", "P25", "P26", "P27", "P28", "P29") else 180
    if remaining < len(plan["run_order"]) * plan["max_wall_seconds"] + evaluation_reserve:
        state["status"] = "server_lease_too_short"
        update(True)
        return 1
    try:
        state["status"] = "running"
        for task, arm, name in plan["run_order"]:
            if arm != PHASES[phase]["arm"]:
                raise ValueError("unexpected baseline arm")
            check_frozen(frozen)
            state["active"] = name
            update(True)
            command = [
                sys.executable, str(ROOT / "scripts" / (
                    "run_stateful_code_appworld.py" if phase == "P29" else
                    "run_code_control_appworld.py" if phase == "P28" else
                    "run_code_appworld.py" if phase == "P27" else
                    "run_native_generated.py" if phase in ("P13", "P14") else
                    "run_native_recent.py" if phase == "P12" else "run_native_appworld.py")),
                "--plan", str(args.plan.absolute()), "--task-id", task, "--run-id", name,
                "--storage-root", str(storage),
                "--appworld-root", str(storage / ".runtime/appworld/r18_probe_01"),
                "--appworld-python", str(storage / ".runtime/appworld/venv/bin/python"),
            ]
            with (out / (name + ".log")).open("w") as stream:
                child = subprocess.Popen(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
                while child.poll() is None:
                    update()
                    time.sleep(30)
            state["completed"].append({"run_id": name, "exit_code": child.returncode})
            update(True)
            if child.returncode:
                raise RuntimeError("trial failed; no automatic retry")
        state["status"] = "complete"
    except Exception as exc:
        state.update(status="runtime_error", error_type=type(exc).__name__)
        write_json(out / "error_private.json", {"type": type(exc).__name__, "message": str(exc)})
    finally:
        state.update(active=None, finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        update(True)
    return 0 if state["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())

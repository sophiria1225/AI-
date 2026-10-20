"""Classify complete verifier results without publishing private test labels."""
import ast
import json
import tarfile


def archive_file(path, expected_name, limit=100 * 1024**2):
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        if (len(members) != 1 or not members[0].isfile()
                or members[0].name != expected_name or members[0].size > limit):
            raise ValueError("Unexpected private verifier archive")
        return archive.extractfile(members[0]).read()


def expected_tests(config, key):
    value = config[key]
    if isinstance(value, str):
        value = ast.literal_eval(value)
    if (not isinstance(value, list) or not value
            or not all(isinstance(item, str) and item for item in value)
            or len(value) != len(set(value))):
        raise ValueError("Invalid private expected-test list")
    return value


def classify_result(config, output, reward, exit_code, oom_killed):
    if type(exit_code) is not int or exit_code not in (0, 1) or oom_killed is not False:
        raise ValueError("Verifier process terminated abnormally")
    if type(reward) not in (int, float) or reward not in (0, 1):
        raise ValueError("Verifier reward is not binary")
    groups = {name: expected_tests(config, name) for name in ("fail_to_pass", "pass_to_pass")}
    if set(groups["fail_to_pass"]) & set(groups["pass_to_pass"]):
        raise ValueError("Expected-test groups overlap")
    rows = output.get("tests")
    if not isinstance(rows, list):
        raise ValueError("Missing structured verifier results")
    observed = {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get("name"), str)
                or row["name"] in observed):
            raise ValueError("Invalid or duplicated verifier test identity")
        observed[row["name"]] = row.get("status")
    counts = {}
    for group, names in groups.items():
        statuses = [observed.get(name) for name in names]
        if any(value not in ("PASSED", "FAILED") for value in statuses):
            raise ValueError("Required test results are absent or not completed")
        counts[group] = {"passed": statuses.count("PASSED"), "failed": statuses.count("FAILED")}
    success = all(counts[group]["failed"] == 0 for group in groups)
    if bool(reward) != success or (success and exit_code != 0):
        raise ValueError("Reward, required tests, and process exit disagree")
    return {"reward": float(reward), "required_test_counts": counts,
            "parsed_test_count": len(rows), "required_results_complete": True}


def assess_artifacts(record, bundle, exit_code, oom_killed):
    config = json.loads((bundle / "tests/config.json").read_text())
    output = json.loads(archive_file(record / "private_output.json.tar", "output.json"))
    text = archive_file(record / "private_reward.txt.tar", "reward.txt", limit=100).decode().strip()
    if text not in ("0", "0.0", "1", "1.0"):
        raise ValueError("Reward file is missing or not binary")
    return classify_result(config, output, float(text), exit_code, oom_killed)


def expected_control(result, phase):
    if phase == "reference_control":
        return result["reward"] == 1.0
    if phase == "negative_control":
        counts = result["required_test_counts"]
        return (result["reward"] == 0.0 and counts["fail_to_pass"]["failed"] > 0
                and counts["pass_to_pass"]["failed"] == 0)
    raise ValueError("Unknown control phase")

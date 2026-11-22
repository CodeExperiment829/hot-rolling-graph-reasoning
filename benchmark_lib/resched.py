"""Evaluate the authors' frozen ReSched policy and verify individual assignments."""
from collections import defaultdict
from importlib.util import module_from_spec, spec_from_file_location
from time import perf_counter

import numpy as np

from benchmark_resources import resource


def policy(device="auto"):
    if device not in {"auto", "cpu", "cuda"}:
        raise ValueError("ReSched device must be auto, cpu or cuda")
    source = resource("SchedulingModel.py")
    weights = resource("SD1-10x05.pth")
    if source is None or weights is None:
        return (
            None,
            "Official inference module or weights missing. Run python -m benchmark_resources.",
        )
    try:
        import torch
    except ModuleNotFoundError:
        return None, "PyTorch missing. Install torch to run ReSched."
    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA was requested but this PyTorch installation has no usable CUDA device")
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    target = torch.device(device)
    spec = spec_from_file_location("resched_official_model", source)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    torch.set_num_threads(1)
    torch.manual_seed(114514)
    model = module.Model(
        action_space=2,
        embedding_dim=128,
        block_num=2,
        head_num=8,
        qkv_dim=16,
        ff_hidden_dim=512,
    )
    model.load_state_dict(torch.load(weights, map_location="cpu", weights_only=True))
    model.to(target)
    model.eval()
    model.set_decode_type("greedy")
    description = "CUDA" if target.type == "cuda" else "one CPU thread"
    return (model, module.build_model_input, target), f"Fresh greedy inference on {description}"


def tensors(jobs, machines):
    job_ids, op_ids, durations = [], [], []
    for job_id, operations in enumerate(jobs):
        for op_id, options in enumerate(operations):
            job_ids.append(job_id)
            op_ids.append(op_id)
            row = np.zeros(machines, dtype=np.int32)
            for machine, duration in options:
                row[machine] = duration
            durations.append(row)
    job_ids, op_ids = np.asarray(job_ids), np.asarray(op_ids)
    same_job = job_ids[:, None] == job_ids[None, :]
    distance = op_ids[None, :] - op_ids[:, None]
    return (
        1,
        job_ids[None],
        op_ids[None],
        np.array(durations)[None],
        (same_job & (distance == 1))[None],
        (same_job & (distance > 0))[None],
    )


def infer(policy_model, jobs, machines):
    import torch
    from .inference_env import FJSPEnv

    model, build_input, device = policy_model
    data = tensors(jobs, machines)
    env = FJSPEnv()
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    tick = perf_counter()
    # Upstream factories for masks, index arrays and scalar tensors use the
    # default device. Scope that default to this evaluation and restore it on exit.
    with torch.inference_mode(), device:
        env.load_data(*data)
        state = env.reset_state()
        done = False
        while not done:
            state, _ = build_input(state, env)
            action, *_ = model(state)
            state, _, done = env.step(action)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elapsed = perf_counter() - tick
    intervals, by_job = defaultdict(list), defaultdict(dict)
    offsets = np.cumsum([0] + [len(j) for j in jobs])
    sol = env.solution
    for j, op, m in zip(sol.job_idx[0], sol.operation_idx[0], sol.machine_idx[0]):
        row = offsets[j] + op
        start = int(state.start_time[0, row, m])
        finish = int(state.finish_time[0, row, m])
        if start < 0 or (m, finish - start) not in jobs[j][op] or op in by_job[j]:
            raise ValueError("Invalid operation assignment")
        intervals[m].append((start, finish))
        by_job[j][op] = (start, finish)
    for j, job in enumerate(jobs):
        if set(by_job[j]) != set(range(len(job))):
            raise ValueError("Incomplete schedule")
        if any(by_job[j][i][1] > by_job[j][i + 1][0] for i in range(len(job) - 1)):
            raise ValueError("Precedence violation")
    for occupied in intervals.values():
        occupied.sort()
        if any(a[1] > b[0] for a, b in zip(occupied, occupied[1:])):
            raise ValueError("Overlapping machine assignments")
    return max(end for entries in intervals.values() for _, end in entries), elapsed

#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "laya==0.3.20",
# ]
# ///
"""
Fine-tune Laya on section relevance with the RLCD recipe of the official notebook.

Adapted from notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb (NandhaKishorM/laya,
Apache-2.0): same loss (noisy-logit policy gradient with a group baseline on a proper scoring
reward, plus soft cross-entropy), optimiser, learning rates and export format, in one process
that runs on CUDA (fp16 autocast), an Apple GPU (MPS, fp32) or the CPU. Differences:
  - the items are Qasper (question, section) pairs, asked as the F2 `noul` question;
  - the noul temperature is fitted on validation papers, never on training items;
  - only the noul temperature is refit, and the bucket temperatures are dropped as in the notebook.

Sequences are built with laya's own Agent._to_internal and build_sequence, so training sees
exactly what predict() sees at inference.

Usage:
    uv run experiments/laya-nav-test/finetune/train.py --out checkpoints/qasper-v1
    uv run experiments/laya-nav-test/finetune/train.py --out checkpoints/smoke --limit 64 --epochs 1 --calib-limit 64

The output directory loads with laya.load("<out>").
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import time
from pathlib import Path

os.environ.setdefault("USE_TF", "0")  # laya README: TensorFlow probing can deadlock laya.load()

import laya  # noqa: E402
import torch  # noqa: E402
from huggingface_hub import snapshot_download  # noqa: E402
from laya.agent import Agent  # noqa: E402
from laya.common import QTYPES, build_sequence, proper_reward  # noqa: E402
from safetensors.torch import save_file  # noqa: E402

from shared import RELEVANT  # noqa: E402

HERE = Path(__file__).resolve().parent
NOUL = QTYPES["noul"]


def pick_device(name: str | None) -> torch.device:
    if name:
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def load_items(path: Path, tok, cfg: dict, limit: int | None, seed: int) -> list[dict]:
    question = Agent._to_internal(RELEVANT["relevant"])
    rows = [json.loads(line) for line in path.open()]
    if limit:
        rows = random.Random(seed).sample(rows, min(limit, len(rows)))
    items = []
    for r in rows:
        state = {"query": r["query"], "passage": r["passage"]}
        ids, markers = build_sequence(tok, state, question, cfg["max_len"], cfg["head_max_len"])
        if len(markers) != 2:
            continue
        p = float(r["p_true"])
        items.append({"ids": ids, "markers": markers, "qtype": NOUL, "target": [1.0 - p, p], "label": int(p >= 0.5)})
    return items


def collate(items: list[dict], pad_id: int) -> dict:
    """collate_train_batch from the official notebook."""
    n, length = len(items), max(len(it["ids"]) for it in items)
    kmax = max(len(it["markers"]) for it in items)
    ids = torch.full((n, length), pad_id, dtype=torch.long)
    att = torch.zeros((n, length), dtype=torch.long)
    mpos = torch.zeros((n, kmax), dtype=torch.long)
    mmask = torch.zeros((n, kmax), dtype=torch.bool)
    target = torch.zeros((n, kmax), dtype=torch.float32)
    for i, it in enumerate(items):
        ids[i, : len(it["ids"])] = torch.tensor(it["ids"])
        att[i, : len(it["ids"])] = 1
        k = len(it["markers"])
        mpos[i, :k] = torch.tensor(it["markers"])
        mmask[i, :k] = True
        target[i, : len(it["target"])] = torch.tensor(it["target"], dtype=torch.float32)
    return {"input_ids": ids, "attention_mask": att, "marker_pos": mpos, "marker_mask": mmask,
            "target": target, "qtype": torch.tensor([it["qtype"] for it in items])}


def fit_one_temp(sel: list[tuple[list[float], list[float]]]) -> float:
    """fit_one_temp from the official notebook: one temperature minimising soft cross-entropy."""
    if len(sel) < 10:
        return 1.0
    kmax = max(len(z) for z, _ in sel)
    Z = torch.full((len(sel), kmax), -1e4)
    T = torch.zeros((len(sel), kmax))
    for i, (z, t) in enumerate(sel):
        Z[i, : len(z)] = torch.tensor(z)
        T[i, : len(t)] = torch.tensor(t, dtype=torch.float32)
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = -(T * torch.log_softmax(Z / log_t.exp(), -1)).sum(-1).mean()
        loss.backward()
        return loss

    opt.step(closure)
    return float(torch.clamp(log_t.exp(), 0.1, 10.0).item())


def forward(model, batch: dict, device: torch.device):
    with torch.autocast("cuda", dtype=torch.float16, enabled=device.type == "cuda"):
        logits, act = model(batch["input_ids"].to(device), batch["attention_mask"].to(device),
                            batch["marker_pos"].to(device), batch["marker_mask"].to(device), batch["qtype"].to(device))
    return logits.float(), act


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", default="convaiinnovations/laya")
    parser.add_argument("--out", required=True, help="output checkpoint directory (relative to this folder)")
    parser.add_argument("--device", help="cuda, mps or cpu (default: best available)")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--micro-batch", type=int, default=8)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--group-size", type=int, default=4, help="noisy samples for the GRPO baseline")
    parser.add_argument("--lr-encoder", type=float, default=2.5e-5)
    parser.add_argument("--lr-head", type=float, default=1.0e-4)
    parser.add_argument("--sigma-start", type=float, default=0.4)
    parser.add_argument("--sigma-end", type=float, default=0.1)
    parser.add_argument("--limit", type=int, help="train on a random subset of this many items")
    parser.add_argument("--calib-limit", type=int, default=2000, help="validation items used to fit the temperature")
    parser.add_argument("--gradient-checkpointing", action="store_true", help="less memory, slower")
    parser.add_argument("--duty-cycle", type=float, default=1.0,
                        help="share of wall time spent computing; below 1 the run pauses after each batch to go easy on the machine")
    parser.add_argument("--seed", type=int, default=20260925)
    args = parser.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = pick_device(args.device)
    out = (HERE / args.out).resolve()

    base_dir = snapshot_download(args.base, allow_patterns=["rl_agent_config.json"])
    cfg = json.loads(Path(base_dir, "rl_agent_config.json").read_text())
    agent = laya.load(args.base, device="cpu")
    model, tok = agent.model, agent.tok
    if args.gradient_checkpointing:
        model.encoder.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        model.head_checkpointing = True
    model.to(device).float().train()

    train_items = load_items(HERE / "data" / "train.items.jsonl", tok, cfg, args.limit, args.seed)
    calib_items = load_items(HERE / "data" / "validation.items.jsonl", tok, cfg, args.calib_limit, args.seed)
    print(f"device {device} | {len(train_items)} training items | {len(calib_items)} validation items for the temperature")

    enc_params = [p for n, p in model.named_parameters() if n.startswith("encoder.")]
    head_params = [p for n, p in model.named_parameters() if not n.startswith("encoder.")]
    optimizer = torch.optim.AdamW([{"params": enc_params, "lr": args.lr_encoder},
                                   {"params": head_params, "lr": args.lr_head}], weight_decay=0.01)
    steps_per_epoch = math.ceil(len(train_items) / args.micro_batch)
    total_updates = max(1, math.ceil(steps_per_epoch / args.grad_accum) * args.epochs)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=total_updates, eta_min=1e-6)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    log, t0 = [], time.time()
    for epoch in range(args.epochs):
        random.Random(args.seed + epoch).shuffle(train_items)
        sigma = args.sigma_start + (args.sigma_end - args.sigma_start) * (epoch / max(1, args.epochs - 1))
        optimizer.zero_grad(set_to_none=True)
        running, n_batches = 0.0, 0
        for step, start in enumerate(range(0, len(train_items), args.micro_batch), 1):
            step_start = time.perf_counter()
            batch = collate(train_items[start : start + args.micro_batch], tok.pad_token_id)
            logits, act = forward(model, batch, device)
            mask = batch["marker_mask"].to(device)
            target = batch["target"].to(device)
            k = mask.sum(-1, keepdim=True).float()

            # RLCD, as in the notebook: G noisy logit samples projected to zero mean, a proper
            # scoring reward against the soft target, a group-normalised advantage, then the
            # policy-gradient term plus soft cross-entropy.
            eps = torch.randn((args.group_size,) + logits.shape, device=device) * sigma * mask
            eps = (eps - eps.sum(-1, keepdim=True) / k) * mask
            z = logits.detach().unsqueeze(0) + eps
            q = torch.softmax(z.masked_fill(~mask, -1e4), -1)
            with torch.no_grad():
                reward = proper_reward(q, target.unsqueeze(0), batch["qtype"].to(device), mask, w_sph=0.75, w_rps=1.0)
                adv = reward - reward.mean(0, keepdim=True)
                adv = adv / (adv.std() + 1e-6)
            logp = -(((z - logits.unsqueeze(0)) ** 2) * mask).sum(-1) / (2 * sigma**2)
            loss_rl = -(adv * logp).mean()
            loss_ce = -(target * torch.log_softmax(logits.masked_fill(~mask, -1e4), -1)).sum(-1).mean()
            loss = (loss_rl + loss_ce) / args.grad_accum + 0.0 * act.sum()

            scaler.scale(loss).backward()
            if step % args.grad_accum == 0 or step == steps_per_epoch:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)

            running += loss.item() * args.grad_accum  # .item() waits for the GPU, so the step time below is real
            n_batches += 1
            if args.duty_cycle < 1:
                time.sleep((time.perf_counter() - step_start) * (1 - args.duty_cycle) / args.duty_cycle)
            if step % 50 == 0 or step == steps_per_epoch:
                done = epoch * steps_per_epoch + step
                eta = (time.time() - t0) / done * (args.epochs * steps_per_epoch - done)
                entry = {"epoch": epoch + 1, "step": step, "loss": round(running / n_batches, 4),
                         "ce": round(loss_ce.item(), 4), "reward": round(reward.mean().item(), 4),
                         "lr_encoder": scheduler.get_last_lr()[0], "elapsed_s": round(time.time() - t0)}
                log.append(entry)
                print(f"epoch {epoch + 1}/{args.epochs} step {step}/{steps_per_epoch} | loss {entry['loss']:.4f} "
                      f"ce {entry['ce']:.4f} reward {entry['reward']:.3f} | {entry['elapsed_s']}s, eta {eta / 60:.0f} min",
                      flush=True)

    print("fitting the noul temperature on validation papers...")
    model.eval()
    calib = []
    with torch.no_grad():
        for start in range(0, len(calib_items), 32):
            chunk = calib_items[start : start + 32]
            logits, _ = forward(model, collate(chunk, tok.pad_token_id), device)
            calib += [(logits[r, :2].cpu().tolist(), it["target"]) for r, it in enumerate(chunk)]
    temperature = fit_one_temp(calib)

    out.mkdir(parents=True, exist_ok=True)
    save_file({k: v.half().contiguous().cpu() for k, v in model.state_dict().items()}, str(out / "model.safetensors"))
    model.encoder.config.save_pretrained(out / "encoder")
    tok.save_pretrained(out / "tokenizer")
    cfg["temperature"] = [cfg["temperature"][0], cfg["temperature"][1], temperature]
    cfg.pop("temperature_by_options", None)  # as in the notebook: bucket values would mask the new fit
    cfg["fine_tuned"] = True
    cfg["model_name"] = "laya-qasper-sections"
    cfg["finetune"] = {"base": args.base, "data": "allenai/qasper train, section relevance (noul)",
                       "items": len(train_items), "epochs": args.epochs, "micro_batch": args.micro_batch,
                       "grad_accum": args.grad_accum, "lr_encoder": args.lr_encoder, "lr_head": args.lr_head,
                       "noul_temperature": temperature, "calibration_items": len(calib), "device": str(device),
                       "duty_cycle": args.duty_cycle,
                       "minutes": round((time.time() - t0) / 60, 1)}
    (out / "rl_agent_config.json").write_text(json.dumps(cfg, indent=2) + "\n")
    (out / "train_log.json").write_text(json.dumps(log, indent=2) + "\n")
    print(f"noul temperature {temperature:.3f} | saved to {out} in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()

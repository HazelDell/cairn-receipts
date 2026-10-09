# Cairn Receipts

A small offline evidence ledger for people reviewing agent tasks and hardware experiments. Python standard library only, for macOS and Linux. No model, account, network service or framework required.

The first use cases were inspired by Scottcjn's [Beacon](https://github.com/Scottcjn/beacon-skill) and [RAM Coffers](https://github.com/Scottcjn/ram-coffers), and StephenLReed's [OpenClaw A2A server](https://github.com/StephenLReed/openclaw-a2a-server). This is an independent contribution, not an endorsed project or an implemented protocol adapter. A legal corpus is not required: use permitted build logs, benchmark reports, research inputs or task artifacts.

## What it does

- Records declared 5W1H with artifact byte lengths and SHA-256 pins.
- Appends a bounded hash-linked JSONL ledger under an exclusive writer lock with file and parent-directory flushes.
- Makes identical event retries idempotent and refuses an event ID reused with different payload.
- Separates a ledger-chain check from artifact drift.
- Replays recorded task state by event time, then ledger sequence; never starts work.
- Compares two benchmark declarations only when hardware, model digest, workload, metric and units match. Prompt-evaluation and decode results cannot silently become one comparison.

## Try it with synthetic data

Requires Python 3.10+ on macOS/Linux. Clone or fork this repository, then:

```sh
mkdir -p run
python3 cairn_receipts.py record --workspace examples --ledger run/receipts.jsonl --event examples/task.json
python3 cairn_receipts.py record --workspace examples --ledger run/receipts.jsonl --event examples/task.json
python3 cairn_receipts.py verify --workspace examples --ledger run/receipts.jsonl
python3 cairn_receipts.py replay --ledger run/receipts.jsonl
python3 cairn_receipts.py compare examples/baseline.json examples/candidate.json
python3 -m unittest -v
```

The second record reports `duplicate: true`. The benchmark ratio is synthetic, not a speedup measurement. Change `examples/result.txt` after recording to see `chain: PASS` and `artifact_match: DRIFT`. Restore it before a new clean run.

## Your own event

Copy an example. Supply event_id, kind, task_id, occurred_at (with timezone), who, what, where, when, why, how and relative artifact paths. `task_state` uses submitted/working/completed/failed/canceled/unknown. A benchmark requires the exact fields shown in the examples. `where` can be a logical context; avoid private paths and secrets in any event you intend to share. Referenced artifacts stay on your machine; the ledger stores relative names and digests, not their contents. It still contains your declared text and filenames: review it before publishing.

Limits: 8 MB input/ledger/artifact, 10,000 ledger rows, 32 artifacts per event. Archive and start a new explicitly linked segment rather than silently truncating. Missing files, symlink artifacts, incomplete tails and conflicting IDs are refused. Concurrent external modification of a workspace is outside the custody guarantee; use a controlled snapshot for important evidence.

## How it could help

For Scott's benchmark workflow: accompany a result with exact context, raw artifact pins and a scope statement. Follow upstream's [benchmark reporting contract](https://github.com/Scottcjn/ram-coffers/blob/main/BENCHMARK.md); this tool does not reproduce a POWER8 result on another machine.

For Stephen's task workflow: use an adapter to record permitted task observations alongside evidence references. Task ID/state mapping, authentication, streaming reconnect and cancellation semantics still need implementation and tests against the selected A2A version. A large-swarm claim requires separate throughput and failure-recovery evidence.

For mentor review: a contributor records one finding; a mentor challenges its basis; a reviewer records a new decision event rather than editing an earlier claim. A fork changes the software through ordinary commits. Receipts provide evidence references alongside that Git history.

## Trust boundary

Hashes detect inconsistency relative to a retained trusted receipt or tail; a person controlling the whole ledger can rewrite it and recompute every hash. No independent signature, chain anchor, approval system, source completeness proof, live-process verification or scientific validity is claimed. Declared actors are not authenticated. This is a local review helper, not a database recovery engine or a transactional coordinator; recording a completed operation does not make that operation write-ahead safe.

No outbound messages, uploads, inference calls or worker dispatch. The CLI only reads the explicitly selected event/artifacts and writes the explicitly selected local ledger and lock file. Don't feed secrets to a ledger you plan to share.

## Contribute

Fork, modify, commit and open a pull request. Keep examples synthetic. Add a failing test for behavioral fixes and state what the check proves. Useful next work: real A2A/Beacon fixture adapters, independent tail witnesses, schema version migration, crash-injection tests and portable locking. Do not label those completed without evidence. MIT licensed; see LICENSE.

## Offline OpenClaw snapshot adapter

`openclaw_snapshot.py` handles a saved TaskRecord from [Stephen's source at commit 5df5563](https://github.com/StephenLReed/openclaw-a2a-server/blob/5df556381e813be0e5786108f65720f1fbd53aee/src/types.ts). It maps accepted/queued to submitted, running to working, succeeded to completed, failed/canceled directly, and expired to unknown. Original state stays explicit in `how`, and the whole source snapshot remains an artifact. No connection, credentials, streaming adapter or dispatch is involved.

```sh
python3 openclaw_snapshot.py --workspace examples --snapshot openclaw-task.json --instance synthetic-demo --observed-at 2026-10-09T18:00:00Z --actor "Synthetic reviewer" --out run/openclaw-demo
python3 cairn_receipts.py record --workspace examples --ledger run/openclaw.jsonl --event run/openclaw-demo/event-0001.json
python3 cairn_receipts.py record --workspace examples --ledger run/openclaw.jsonl --event run/openclaw-demo/event-0002.json
python3 cairn_receipts.py record --workspace examples --ledger run/openclaw.jsonl --event run/openclaw-demo/event-0003.json
python3 cairn_receipts.py replay --ledger run/openclaw.jsonl
```

The upstream event objects have IDs but no individual timestamps. The adapter uses your explicit observation clock and says so; it does not fabricate execution times from the task-level updatedAt value. Namespace every source instance to avoid task-ID collisions. Repeated snapshot observations at different times are not silently duplicates: changed receipt content requires explicit identity/revision handling. Do not collect repeatedly changing full snapshots without an ingestion policy. Future events changing an existing source event require diagnosis rather than overwriting history.

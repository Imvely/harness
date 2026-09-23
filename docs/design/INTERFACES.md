# pad_research — Interface Contract (binding for all implementers)

Repo: /home/user/harness (package `src/pad_research`, Python 3.11, uv). Run tools with `uv run --no-sync ...`.
Language: code/docstrings/comments/commit messages in English. Korean only in CLAUDE.md, .claude/rules, agents, ADRs, reports.
Style: ruff (line 100, rules E,F,W,I,B,UP,N,SIM,RUF), pyright standard, type hints everywhere, pydantic v2, no `print` in library code.
ALL `__init__.py` files are EMPTY (validators must import without torch/mlflow/sklearn/matplotlib).
Never hard-code dataset names in experiment logic (contract §27.3). Never tune thresholds on test (§41-3).

## paths.py  (src/pad_research/paths.py)
```python
import os; from pathlib import Path
def repo_root() -> Path            # env PAD_REPO_ROOT else Path(__file__).resolve().parents[2]
def configs_dir() -> Path          # repo_root()/"configs"
def manifests_dir() -> Path        # repo_root()/"data"/"manifests"
def specs_dir() -> Path            # repo_root()/"experiments"/"specs"
def registry_path() -> Path        # env PAD_REGISTRY_PATH else repo_root()/"experiments"/"registry.jsonl"
def approvals_dir() -> Path        # repo_root()/"experiments"/"approvals"
def output_root() -> Path          # env PAD_OUTPUT_ROOT else repo_root()/"outputs"
def data_root(root_env_var: str = "PAD_DATA_ROOT") -> Path   # env required; raise DataRootNotConfiguredError
def default_tracking_uri() -> str  # env MLFLOW_TRACKING_URI else f"sqlite:///{repo_root()}/mlruns.db"
def artifact_root() -> Path        # repo_root()/"mlruns_artifacts"
class DataRootNotConfiguredError(RuntimeError)
```
(Functions, not constants, so tests can monkeypatch env.)

## conventions.py
```python
LABEL_BONA_FIDE = 0; LABEL_SPOOF = 1
ATTACK_SCORE_CONVENTION = "attack_score = sigmoid(logit) = P(spoof); higher = more spoof-like"
def decide_spoof(score: np.ndarray, tau: float) -> np.ndarray   # score >= tau  (bool)
CONTRACT_SHA256 = "0562540579b17857205945eb5584d6fda07852c52c48c020d4ff3de2a632d35d"   # docs/RESEARCH_CONTRACT.md
```

## utils/
- canonical_json.py: `canonical_json(obj) -> str` = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False); `sha256_text(s) -> str`
- hashing.py: `sha256_file(path) -> str`
- git.py: `@dataclass GitState(sha: str|None, short_sha: str|None, branch: str|None, dirty: bool, untracked_count: int)`; `git_state(repo_root) -> GitState` — dirty = `git status --porcelain --untracked-files=no` non-empty (tracked changes only); never raises (sha None if not a repo).
- seed.py: `seed_everything(seed:int, deterministic:bool=True)` (random, numpy, torch inside function; `torch.use_deterministic_algorithms(True, warn_only=True)`; cudnn deterministic; sets CUBLAS_WORKSPACE_CONFIG=:4096:8), `make_generator(seed) -> torch.Generator`, `worker_init_fn(worker_id)`.
- device.py: `resolve_device(requested: Literal["auto","cpu","cuda"]) -> torch.device`

## data/manifest.py
```python
class Label(StrEnum): bona_fide="bona_fide"; spoof="spoof"
class PAI(StrEnum): none="none"; print="print"; replay="replay"; replay_phone="replay_phone"; replay_tablet="replay_tablet"; replay_display="replay_display"; display="display"; mask_3d="mask_3d"; other="other"
class Split(StrEnum): train="train"; dev="dev"; test="test"
class MediaType(StrEnum): video="video"; frames_dir="frames_dir"; image="image"; npy_clip="npy_clip"
class ManifestRecord(BaseModel):  # extra="forbid", frozen=True
    dataset_id: str   # normalized lower(); pattern ^[a-z0-9_]+$
    sample_id: str    # ^[A-Za-z0-9_\-.]+$ ; unique within dataset; synthetic uses f"{dataset_id}_s{subject:03d}_c{clip:02d}_{pai}"
    subject_id: str; split: Split; label: Label; pai: PAI   # model_validator: label==bona_fide <=> pai==none
    pai_detail: str|None=None; relative_path: str  # reject absolute, "..", leading "/"
    media_type: MediaType; fps: float|None=None; n_frames: int|None=None; width: int|None=None; height: int|None=None
    capture_device: str|None=None; session: str|None=None; environment: str|None=None; official_protocol: str|None=None
    extra: dict[str, str|int|float|bool] = {}
class ManifestMeta(BaseModel):
    dataset_id: str; version: str; adapter: str; license: str
    pii_policy: Literal["synthetic","internal_only","licensed_research"]
    root_env_var: str="PAD_DATA_ROOT"; temporal_valid: bool; manifest_hash: str; n_records: int; n_subjects: int
    splits: dict[str, dict[str,int]]; pai_counts: dict[str,int]; created_at: str; generator_commit: str|None
    @property research_grade -> bool  # pii_policy != "synthetic"
class Manifest(BaseModel): records: list[ManifestRecord]; meta: ManifestMeta
    def by_split(split) -> list[ManifestRecord]; def subjects(split=None) -> set[str]; def sample_ids() -> set[str]
def manifest_hash(records) -> str        # sort by sample_id; canonical_json(record.model_dump(mode="json")) per line joined by "\n"; sha256
def validate_records(records: Sequence[ManifestRecord]) -> list[str]   # duplicate sample_id, label/pai inconsistency (defensive), subject in >1 split
def write_manifest(records, meta_partial: dict, out_dir: Path) -> ManifestMeta   # writes <id>.jsonl (one record per line, sorted by sample_id) + <id>.meta.json
def load_manifest(dataset_id: str, manifests_dir: Path) -> Manifest      # verifies hash -> ManifestTamperedError
def resolve_path(record, root: Path) -> Path
class ManifestTamperedError(RuntimeError); class ManifestNotFoundError(FileNotFoundError)
```
## data/adapters/base.py
```python
class DatasetAdapter(ABC):
    dataset_id: str; version: str; license: str; pii_policy: str; temporal_valid: bool = True
    @abstractmethod def build(self, root: Path) -> list[ManifestRecord]   # may also WRITE media under root/<dataset_id>/ (synthetic does)
    def meta_partial(self) -> dict
ADAPTERS: dict[str, Callable[..., DatasetAdapter]]   # {"synthetic": SyntheticAdapter}
def get_adapter(name: str, **kwargs) -> DatasetAdapter
```
## data/adapters/synthetic.py
- `SyntheticDomain(brightness, gain, noise_std, color_cast, blur)`, `SYN_DOMAINS = {"synthetic_a": ..., "synthetic_b": ...}`
- `SyntheticAdapter(dataset_id, n_subjects=20, clips_per_subject=8, num_frames=16, size=(32,32), fps=30.0, split_ratio=(0.6,0.2,0.2), subject_offset=0)`; synthetic_b uses subject_offset=1000. Per subject: bona_fide x4, print x2, replay_phone x1, replay_tablet x1 → per split all PAIs present. Subject-disjoint splits (12/4/4 subjects).
- `generate_clip(sample_id, pai, domain, T, H, W) -> np.ndarray uint8 [T,H,W,3]`; rng seed = int.from_bytes(sha256(sample_id)[:8],"little"). Cues: bona_fide low-freq blob + slow drift; print static high-freq grid; replay_phone/tablet distinct flicker freq + stripes. Deterministic, byte-identical on re-run. Files: root/<dataset_id>/<sample_id>.npy; relative_path=f"{dataset_id}/{sample_id}.npy"; media_type npy_clip; meta pii_policy "synthetic", license "synthetic-cc0", temporal_valid True.
## scripts/prepare_dataset.py
`--adapter synthetic --dataset-id synthetic_a [--dataset-id synthetic_b] [--root PATH (default env PAD_DATA_ROOT else repo/data/processed)] [--manifests-dir PATH]`; prints dataset_id, n_records, manifest_hash; idempotent.

## metrics/  (numpy only; convention: y_attack: bool array True=spoof; score float higher=spoof; pai: list[str]; predict_attack = score >= tau)
```python
class EmptyPAIError(ValueError)
def apcer_per_pai(score, y_attack, pai, tau) -> dict[str,float]   # per PAI: mean(score[attack&pai] < tau); PAIs with 0 attacks omitted; no attacks at all -> EmptyPAIError
def apcer_pooled(score, y_attack, tau) -> float
def apcer_max(per_pai: dict[str,float]) -> float
def bpcer(score, y_attack, tau) -> float                             # mean(score[bona] >= tau)
def acer(apcer_value, bpcer_value) -> float                          # (a+b)/2
def hter(apcer_pooled_value, bpcer_value) -> float                   # (a+b)/2, always pooled
def roc_auc(score, y_attack) -> float                                # sklearn.roc_auc_score (import inside fn)
def eer_threshold(score_dev, y_attack_dev) -> tuple[float,float]     # roc_curve(drop_intermediate=False); drop thr==inf; i=argmin|fpr-fnr| (first); return (thr[i], (fpr[i]+fnr[i])/2)
def bpcer_at_apcer(score_dev, y_attack_dev, target_apcer) -> tuple[float,float]   # tau = max tau with APCER(tau)<=target (i.e. lowest BPCER); returns (tau, bpcer)
class PadMetrics(BaseModel): tau: float; apcer_per_pai: dict[str,float]; apcer_max: float; apcer_pooled: float; apcer: float; bpcer: float; acer: float; hter: float; auc: float; acer_policy: str; n_bona_fide: int; n_attack_per_pai: dict[str,int]; bpcer_at_apcer_10: float|None=None; bpcer_at_apcer_1: float|None=None
def compute_pad_metrics(score, y_attack, pai, tau, acer_policy: Literal["max_pai","pooled"]="max_pai") -> PadMetrics   # apcer = max or pooled per policy
```
Toy vectors (tau=0.5; bona [0.1,0.2,0.3,0.7]; print [0.9,0.8,0.4,0.6]; replay_phone [0.3,0.2,0.9,0.95,0.1]): BPCER .25; per-PAI {print .25, replay_phone .6}; max .6; pooled 4/9; ACER(max) .425; HTER (4/9+.25)/2; boundary bona [0.5] tau .5 -> BPCER 1.0; EER separable dev bona [.1,.2,.3,.4] attack [.6,.7,.8,.9] -> tau .6, eer 0; overlap bona [.2,.4,.6,.8] attack [.3,.5,.7,.9] -> tau .6 eer .5; AUC partial bona [.1,.5,.6,.7] attack [.2,.3,.8,.9] -> .625; ties -> .5. Use pytest.approx(abs=1e-12).

## evaluation/scores.py
```python
class ScoreTable(BaseModel): role: Literal["dev","test","adapt"]; domain: Literal["source","target"]; sample_id: list[str]; subject_id: list[str]; score: list[float]; y_attack: list[bool]; pai: list[str]
    @classmethod from_arrays(role, domain, ...); def to_numpy() -> tuple[np.ndarray, np.ndarray, list[str]]; def to_csv(path)
```
## metrics/threshold.py
```python
class ThresholdLeakageError(RuntimeError); class NotFittedError(RuntimeError)
class ThresholdSpec(BaseModel): source: Literal["dev_set"]="dev_set"; policy: Literal["fixed_after_dev"]="fixed_after_dev"; rule: Literal["eer","bpcer_at_apcer"]="eer"; rule_param: float|None=None; dev_domain: Literal["source","target"]="source"
class ThresholdPolicy(BaseModel): spec: ThresholdSpec; tau: float|None=None; fitted_on: str|None=None; dev_n_bona_fide: int|None=None; dev_n_attack: int|None=None; dev_eer: float|None=None
    def fit(self, table: ScoreTable) -> "ThresholdPolicy"   # table.role != "dev" -> ThresholdLeakageError; returns new fitted copy
    def apply(self, score: np.ndarray) -> np.ndarray         # tau None -> NotFittedError
```
(ThresholdSpec lives in metrics/threshold.py and is re-used by protocols/schema.py.)
## metrics/security_gate.py
```python
class SecurityGateConfig(BaseModel): abs_tolerance: float=0.01; rel_tolerance: float=0.0; min_attack_samples_per_pai: int=20
class PaiDelta(BaseModel): pai; apcer_before; apcer_after; delta; n_attack; regressed: bool; insufficient_support: bool
class SecurityGateResult(BaseModel): verdict: Literal["pass","security_regression","inconclusive","comparison_blocked"]; per_pai: list[PaiDelta]; bpcer_before; bpcer_after; bpcer_delta; bpcer_improved: bool; auc_before; auc_after; protocol_hash: str|None; baseline_run_id: str|None=None; note: str
def run_security_gate(before: PadMetrics, after: PadMetrics, before_hash: str, after_hash: str, cfg: SecurityGateConfig, justify: str|None=None, baseline_run_id: str|None=None) -> SecurityGateResult
```
regressed = (delta - max(abs_tol, rel_tol*apcer_before)) > 1e-9 (exact tolerance passes). verdict: any(regressed & supported) -> security_regression; elif any(insufficient_support) -> inconclusive; else pass. Hash mismatch: justify None -> raise ProtocolMismatchError (from protocols.compare; import lazily or define the exception in metrics/security_gate.py and re-export in protocols.compare — DECISION: define `ProtocolMismatchError` in `pad_research/errors.py` shared by both).

## errors.py
`class ProtocolMismatchError(RuntimeError)`, `class GateBlockedError(RuntimeError)`, `class CheckpointProtocolMismatchError(RuntimeError)`

## protocols/ (T3)  — ProtocolSpec fields exactly as master plan D5 + refuter fixes:
protocol_id ^[a-z0-9_]+_v\d+$; schema_version: Literal[1]=1; status active|draft; description; parent_protocol_id; change_note; source_datasets (sorted, lower, unique); target_dataset (same); source_classes; target_adaptation{enabled, supervision, shots_per_subject, total_samples, source_split, selection_seed, subject_disjoint_from_test}; target_test{exclude_adaptation_samples, split}; attack_types (sorted unique); threshold: ThresholdSpec; acer_policy; security_gate: SecurityGateConfig; allow_image_dataset_as_clip.
HASH_EXCLUDED = {"description","parent_protocol_id","change_note","status"}; protocol_hash = sha256(canonical_json(model_dump(mode="json", exclude=HASH_EXCLUDED))).
`select_adaptation_set(protocol, target: Manifest) -> AdaptationSelection` (pure) / `materialize_adaptation_set(selection, out_dir) -> Path` (write). `validate_protocol(p, manifests_dir, *, frames=1) -> ProtocolValidation` has NO filesystem side effects.

## experiments/status.py
`class RunStatus(StrEnum): running, smoke_ok, success, failed_environment, failed_training, invalid_spec, invalid_protocol, security_regression, inconclusive, blocked_by_gate`
Smoke runs end as smoke_ok (gate verdict only in tag `gate_verdict`); security_regression/inconclusive only for full runs.

## Hook contract (for .claude/hooks, stdlib only, py3.8-compatible syntax)
- validate_spec CLI: `uv run --no-sync python scripts/validate_spec.py --exp NAME [--for-launch] [--freeze] [--json] [--config-dir DIR] [-- OVERRIDE ...]`; exit 0 ok / 2 spec / 3 protocol / 4 gate / 5 internal. `--json` prints ONE JSON object on stdout: {ok, exit_code, errors[], warnings[], experiment_id, mode ("smoke"|"full"), science_hash, spec_hash, protocol_id, protocol_hash, tracking_uri_scheme, approval_token_ok: bool, gate: {allowed, reasons[], checks{}}|null}.
- approvals: experiments/approvals/<exp_id>.<science_hash[:12]>.json {experiment_id, science_hash, git_sha, approved_at, approved_by}; created only by scripts/approve_full_run.py run by the human.

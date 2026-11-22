"""ALD-OPTIX quantitative core. All outputs are decision-support estimates, not process certification."""
from __future__ import annotations
import math
import unicodedata
from numbers import Real
import re
import hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

DATA_FILE = Path(__file__).parent / "data" / "ald_pan_lei_2025_table5.csv"
SOURCE = "Pan & Lei, Materials 2025, 18(9), 1918, Table 5"
DOI = "https://doi.org/10.3390/ma18091918"
# Two independent checks for the shipped, *fixed* Table 5 transcription:
# (1) the exact source bytes, including numeric precision and line endings;
# (2) the parsed table in canonical form. An intentional source correction
# requires reviewing the paper and explicitly updating BOTH fingerprints.
EXPECTED_SOURCE_CSV_SHA256 = "f61d6f101c6d48dfd4677a9c131c6b383c55186c3d17d93e726de1bf463342ec"
EXPECTED_DATA_SHA256 = "a947b4fbd466510d2acd3e870b579c0999ed5597297225702ba5f3a8e9a489a5"
VAR_NAMES = ["temperature_C", "flow_sccm", "pulse_ms", "purge_s"]
CODE_NAMES = ["temp_code", "flow_code", "pulse_code", "purge_code"]
LEVELS = {"temperature_C": (175, 275), "flow_sccm": (10, 20), "pulse_ms": (20, 40), "purge_s": (10, 20)}

EVIDENCE = [
    {"id": "P1", "title": "실험 설계", "text": "Al₂O₃ thermal ALD(TMA/H₂O) 실험. 온도 175/275 °C, Ar 10/20 sccm, 두 전구체 pulse 20/40 ms, purge 10/20 s를 조합한 2^4 DOE, 조건별 2회 반복(32회).", "source": DOI, "type": "관측"},
    {"id": "P2", "title": "온도의 주효과", "text": "해당 실험에서 온도는 통계적으로 유의한 주효과. 평균 GPC는 175°C에서 275°C보다 높았음. 다른 장비에 일반화할 수 없음.", "source": DOI, "type": "논문 분석"},
    {"id": "P3", "title": "변수 간 상호작용", "text": "해당 논문은 온도×purge, pulse×purge 상호작용을 유의하게 분석. GPC 단독 최적화와 처리량 최적화 목표는 다름.", "source": DOI, "type": "논문 분석"},
    {"id": "P4", "title": "반응물 및 기판", "text": "실험에서는 TMA 및 H₂O 전구체, Si 기판, 동일 batch 조건을 사용. 최종 두께는 200 cycle 후 ellipsometer로 측정.", "source": DOI, "type": "관측"},
    {"id": "P5", "title": "품질 검증 한계", "text": "공개 Table 5에는 GPC가 기록되어 있으나 수분/불순물, 누설 전류, 균일도 등 제품 품질 승인에 필요한 지표는 포함되지 않음. 공정 적합 판정 불가.", "source": DOI, "type": "데이터 한계"},
]


def load_data() -> pd.DataFrame:
    if hashlib.sha256(DATA_FILE.read_bytes()).hexdigest() != EXPECTED_SOURCE_CSV_SHA256:
        raise ValueError("Published source CSV byte fingerprint mismatch; verify Table 5 transcription")
    d = pd.read_csv(DATA_FILE)
    if len(d) != 32:
        raise ValueError("Expected 32 original experimental rows")
    # This fixed educational dataset is not a user-upload interface. Revisions
    # must be checked against the cited paper and explicitly re-fingerprinted.
    if hashlib.sha256(d.to_csv(index=False, float_format='%.6f').encode('utf-8')).hexdigest() != EXPECTED_DATA_SHA256:
        raise ValueError("Published source data fingerprint mismatch; verify Table 5 transcription")
    required = set(CODE_NAMES) | {"gpc_A_per_cycle", "run_order", "standard_order"}
    if not required.issubset(d.columns):
        raise ValueError(f"Missing required source columns: {sorted(required - set(d.columns))}")
    if d["run_order"].duplicated().any() or d["standard_order"].duplicated().any():
        raise ValueError("Source row identifiers must be unique")
    gpc = pd.to_numeric(d["gpc_A_per_cycle"], errors="coerce")
    if not (np.isfinite(gpc).all() and (gpc > 0).all()):
        raise ValueError("Observed GPC must be finite and positive")
    for key, level in zip(VAR_NAMES, CODE_NAMES):
        if not d[level].isin([-1, 1]).all():
            raise ValueError(f"Unexpected DOE code for {level}")
        lo, hi = LEVELS[key]
        d[key] = np.where(d[level] == -1, lo, hi)
    if d.groupby(VAR_NAMES, dropna=False).size().shape[0] != 16:
        raise ValueError("Expected 16 unique DOE conditions")
    if not (d.groupby(VAR_NAMES).size() == 2).all():
        raise ValueError("Each condition must have 2 replicates")
    return d


def condition_means(data: pd.DataFrame | None = None) -> pd.DataFrame:
    d = load_data() if data is None else data
    agg = d.groupby(VAR_NAMES, as_index=False).agg(
        gpc_mean_A=("gpc_A_per_cycle", "mean"),
        gpc_sd_A=("gpc_A_per_cycle", "std"),
        replications=("gpc_A_per_cycle", "count"),
    )
    agg["gpc_sd_A"] = agg["gpc_sd_A"].fillna(0.0)
    return agg


def estimated_cycles(target_nm: float, gpc_A: float) -> int:
    if not (0 < target_nm <= 1000 and 0 < gpc_A < 100):
        raise ValueError("Target and GPC must be positive and within plausible demo bounds")
    return math.ceil(target_nm * 10 / gpc_A)  # 1 nm = 10 Å


def minimum_sequence_time_s(cycles: int, pulse_ms: int, purge_s: int) -> float:
    """Approx 2 pulses + 2 purges per cycle. EXCLUDES all chamber/valve/overhead time."""
    return cycles * (2 * pulse_ms / 1000 + 2 * purge_s)



def _finite_real(value: object) -> float | None:
    """Safely parse a real scalar without silently dropping an imaginary part.

    Real includes Python and NumPy real scalars but excludes complex; bool and
    numpy.bool_ are forbidden even though Python bool subclasses int. A value
    too large to represent as float is invalid rather than an uncaught error.
    """
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        return None
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def optimize_recipe(target_nm=10.0, max_temp=275, min_flow=10, max_flow=20, min_purge=10, max_purge=20, objective="time", min_temp=175, min_pulse=20, max_pulse=40) -> dict:
    fields = {"목표 두께":target_nm, "최소 온도":min_temp, "최대 온도":max_temp,
              "최소 유량":min_flow, "최대 유량":max_flow, "최소 purge":min_purge,
              "최대 purge":max_purge, "최소 pulse":min_pulse, "최대 pulse":max_pulse}
    normalized = {name: _finite_real(value) for name, value in fields.items()}
    if any(value is None for value in normalized.values()):
        return {"error": "공정 조건에는 유한한 실수만 입력해야 합니다. 복소수·불리언·범위 초과 수치는 허용하지 않습니다."}
    # Normalize only AFTER validation; never silently truncate NumPy complex.
    (target_nm, min_temp, max_temp, min_flow, max_flow, min_purge,
     max_purge, min_pulse, max_pulse) = (normalized[name] for name in fields)
    if not (0.1 <= target_nm <= 1000):
        return {"error": "목표 두께는 0.1~1000 nm 사이로 입력해 주세요."}
    if objective not in ("time", "gpc", "balanced"):
        return {"error": "지원하지 않는 최적화 목표입니다. time / gpc / balanced 중 선택해 주세요."}
    if min_temp > max_temp or min_flow > max_flow or min_purge > max_purge or min_pulse > max_pulse:
        return {"error": "최솟값이 최댓값보다 큽니다. 온도·유량·pulse·purge 제약을 확인해 주세요."}
    data = condition_means()
    data = data.loc[
        (data.temperature_C >= min_temp) & (data.temperature_C <= max_temp) &
        (data.flow_sccm >= min_flow) & (data.flow_sccm <= max_flow) &
        (data.purge_s >= min_purge) & (data.purge_s <= max_purge) &
        (data.pulse_ms >= min_pulse) & (data.pulse_ms <= max_pulse)
    ].copy()
    if data.empty:
        return {"error": "논문에서 실제 측정한 16개 DOE 조건 중 제약을 충족하는 조건이 없습니다. 실험 범위를 넘어서 추정하지 않았습니다."}
    data["cycles"] = data.gpc_mean_A.map(lambda g: estimated_cycles(target_nm, float(g)))
    data["sequence_time_s"] = data.apply(lambda r: minimum_sequence_time_s(int(r.cycles), int(r.pulse_ms), int(r.purge_s)), axis=1)
    data["sequence_time_min"] = data.sequence_time_s / 60
    data["target_nm"] = float(target_nm)
    if objective == "gpc":
        data = data.sort_values(["gpc_mean_A", "sequence_time_s"], ascending=[False, True])
    elif objective == "balanced":
        time_norm = (data.sequence_time_s - data.sequence_time_s.min()) / max(1, data.sequence_time_s.max() - data.sequence_time_s.min())
        gpc_norm = (data.gpc_mean_A.max() - data.gpc_mean_A) / max(0.001, data.gpc_mean_A.max() - data.gpc_mean_A.min())
        data["balance_score"] = time_norm * 0.65 + gpc_norm * 0.35
        data = data.sort_values(["balance_score", "sequence_time_s"])
    else:
        data = data.sort_values(["sequence_time_s", "gpc_mean_A"], ascending=[True, False])
    return {"best": data.iloc[0].to_dict(), "ranking": data.reset_index(drop=True), "n_feasible": len(data)}


def naive_v0(target_nm=10.0) -> dict:
    """Baseline: maximizing observed GPC only, ignoring user constraints and cycle duration."""
    row = condition_means().sort_values("gpc_mean_A", ascending=False).iloc[0].to_dict()
    cyc = estimated_cycles(target_nm, row["gpc_mean_A"])
    row.update(cycles=cyc, sequence_time_s=minimum_sequence_time_s(cyc, int(row["pulse_ms"]), int(row["purge_s"])))
    return row


def constraint_check(row: dict, max_temp=275, min_flow=10, max_flow=20, min_purge=10, max_purge=20, min_temp=175, min_pulse=20, max_pulse=40) -> list[str]:
    issues = []
    for field, relation, lim, label in [
        ("temperature_C", "min", min_temp, "최소 온도"),
        ("temperature_C", "max", max_temp, "최대 온도"),
        ("flow_sccm", "min", min_flow, "최소 Ar 유량"),
        ("flow_sccm", "max", max_flow, "최대 Ar 유량"),
        ("purge_s", "min", min_purge, "최소 purge"),
        ("purge_s", "max", max_purge, "최대 purge"),
        ("pulse_ms", "min", min_pulse, "최소 pulse"),
        ("pulse_ms", "max", max_pulse, "최대 pulse"),
    ]:
        try:
            observed = float(row[field])
            bound = float(lim)
            if not (math.isfinite(observed) and math.isfinite(bound)):
                raise ValueError('nonfinite constraint')
        except (TypeError, ValueError, KeyError, OverflowError):
            issues.append(f"{label} 검증 불가: 숫자 조건이 유효하지 않습니다.")
            continue
        bad = observed > bound if relation == "max" else observed < bound
        if bad:
            issues.append(f"{label} 조건 위반: {field}={observed}, 제한={bound}")
    return issues


def make_features(X_codes: np.ndarray) -> np.ndarray:
    X = np.asarray(X_codes, dtype=float)
    pairs = [X[:, i] * X[:, j] for i in range(4) for j in range(i+1, 4)]
    return np.column_stack([X] + pairs)


def cross_validate() -> tuple[dict, pd.DataFrame]:
    """16-fold leave-one-CONDITION-out CV; two replicates held out together."""
    df = load_data()
    groups = df[CODE_NAMES].astype(str).agg("_".join, axis=1).to_numpy()
    X_codes = df[CODE_NAMES].to_numpy()
    X = X_codes.astype(float)  # Parsimonious main-effects model after checking overfitting
    X_complex = make_features(X_codes)  # Initial model with six interactions
    y = df.gpc_A_per_cycle.to_numpy(dtype=float)
    logo = LeaveOneGroupOut()
    pred_base = np.empty_like(y)
    pred_ridge = np.empty_like(y)
    pred_complex = np.empty_like(y)
    for train, test in logo.split(X, y, groups):
        pred_base[test] = y[train].mean()
        reg = Ridge(alpha=0.1)
        reg.fit(X[train], y[train]); pred_ridge[test] = reg.predict(X[test])
        complex_model = Ridge(alpha=0.1)
        complex_model.fit(X_complex[train], y[train]); pred_complex[test] = complex_model.predict(X_complex[test])
    rows = df[["run_order"] + VAR_NAMES + ["gpc_A_per_cycle"]].copy()
    rows["baseline_pred_A"] = pred_base
    rows["regression_pred_A"] = pred_ridge
    rows["complex_pred_A"] = pred_complex
    metrics = {
        "n_runs": len(y),
        "n_conditions": len(np.unique(groups)),
        "baseline_MAE_A": float(mean_absolute_error(y, pred_base)),
        "baseline_RMSE_A": float(root_mean_squared_error(y, pred_base)),
        "model_MAE_A": float(mean_absolute_error(y, pred_ridge)),
        "model_RMSE_A": float(root_mean_squared_error(y, pred_ridge)),
        "initial_complex_MAE_A": float(mean_absolute_error(y, pred_complex)),
        "initial_complex_RMSE_A": float(root_mean_squared_error(y, pred_complex)),
        "mae_reduction_pct": float((1 - mean_absolute_error(y, pred_ridge) / mean_absolute_error(y, pred_base)) * 100),
    }
    return metrics, rows


# Explicitly supported chemistry. A regex is a guardrail, not chemical named-entity recognition.
_SUBSCRIPT_TRANSLATE = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUPPORTED_MATERIAL = re.compile(r"(?<![a-z0-9])(?:al2o3|alumina)(?![a-z0-9])|산화알루미늄", re.I)
_FORMULA = re.compile(r"(?<![A-Za-z0-9])(?:[A-Z][a-z]?\d*){2,6}(?![A-Za-z0-9])")
_ALLOWED_CHEMISTRY = {"Al2O3", "H2O", "TMA", "ALD", "GPC", "DOE", "AI", "API", "CV", "ML", "LLM", "Ar", "Si"}
_UNSUPPORTED_PROCESS = re.compile(r"\b(?:sputter|PVD|PECVD|LPCVD|CVD|PLD)\b|스퍼터|스퍼터링|물리기상증착|화학기상증착", re.I)
_UNSUPPORTED_REQUEST = re.compile(r"(?:압력|진공도|챔버압력|mTorr|\bTorr\b|\bPa\b|\bkPa\b|\bW\b|와트|RF 파워|플라즈마|"
    r"균일|누설전류|전기적 특성|수율|불순물|기판 온도|습도|pressure|roughness|"
    r"거칠기|밀도|면저항|유전율|결정성|결정화|막질|막\s*특성|파티클|"
    r"step\s*coverage|conformality|conformal|열처리|반응기\s*변경)", re.I)

# Additional unsupported, outcome-changing requirements discovered during QA.
# This is deliberately a narrow supported-input parser, NOT general chemical NLP.
_UNSUPPORTED_OTHER_REQUIREMENTS = re.compile(
    r"(?:혼합\s*비(?:율)?|배합\s*비(?:율)?|가스\s*비율|(?:precursor|flow|mixing|gas)\s*ratio|"
    r"(?:TMA|H2O|water|전구체|산화제)(?:\s*[/+:]\s*(?:TMA|H2O|water))?\s*(?:비|ratio|\d+\s*:\s*\d+)|"
    r"비율(?:을|을\s+)?\s*(?:높|낮|변경|조절|바꾸)|"
    r"(?:기판|substrate)(?:.{0,28})(?:바꾸|변경|교체|대체|말고|대신|glass|유리|sapphire)|"
    r"(?:glass|유리|사파이어)\s*(?:기판|substrate)|"
    r"공정\s*환경|증착\s*분위기|반응\s*분위기|(?:process|gas)\s*atmosphere|"
    r"허용\s*오차|허용\s*편차|오차\s*범위|\btolerance\b|\bppm\b|"
    r"(?:\d+(?:\.\d+)?\s*%|±|\+/-|\d+(?:\.\d+)?\s*(?:Å|ångström|angstrom))|"
    r"(?:전구체|산화제|기판|반응물)\s*(?:종류|재료)\s*(?:변경|조절|바꾸))",
    re.I,
)



def request_scope_error(text: str) -> str | None:
    """Fail closed for unknown materials and processes; user must name the supported film."""
    normalized = str(text).translate(_SUBSCRIPT_TRANSLATE)
    semantic_error = _semantic_scope_error(normalized)
    if semantic_error:
        return semantic_error
    if _UNSUPPORTED_PROCESS.search(normalized):
        return "다른 증착 방법은 지원하지 않습니다. Al₂O₃ thermal ALD(TMA/H₂O) 전용입니다."
    if _UNSUPPORTED_REQUEST.search(normalized):
        return "현재 데이터로 검증할 수 없는 별도 물성·압력·장비 제약이 있습니다. 해당 요청에 대한 레시피 추천을 중단합니다."
    if _UNSUPPORTED_OTHER_REQUIREMENTS.search(normalized):
        return ("실측 데이터에 없는 혼합비·기판 변경·환경·허용오차 또는 지원하지 않는 단위 요청이 있습니다. "
                "해당 제약을 무시하고 추천하지 않습니다. 지원 가능한 조건(Al₂O₃ 10nm, 온도·Ar·pulse·purge 및 최적화 목적)만 지정해 주세요.")
    compounds = [m.group(0) for m in _FORMULA.finditer(normalized)]
    unknown = [formula for formula in compounds if formula not in _ALLOWED_CHEMISTRY]
    if unknown:
        return f"지원하지 않는 박막 물질 또는 미확인 화학식({unknown[0]})이 있습니다. Al₂O₃ 전용 데이터로 다른 물질을 추천하지 않습니다."
    if not _SUPPORTED_MATERIAL.search(normalized):
        return "박막 물질을 확인할 수 없습니다. 지원하는 'Al2O3' 또는 'Al₂O₃'를 명시해 주세요. 임의로 물질을 추정하지 않습니다."
    return None


# Explicit gas/precursor guard: these observations use only TMA/H2O thermal ALD.
# Mere mention of an alternate reactant is treated conservatively as an unsupported
# process request. This is preferable to silently applying H2O data to ozone ALD.
_UNSUPPORTED_CHEMISTRY = re.compile(
    r"(?:오존|ozone|(?<![A-Za-z0-9])O\s*₃(?![A-Za-z0-9])|(?<![A-Za-z0-9])O3(?![A-Za-z0-9])|"
    r"산소\s*플라즈마|oxygen\s*plasma|plasma[- ]?enhanced|PEALD|"
    r"과산화수소|hydrogen\s*peroxide|(?<![A-Za-z0-9])H2O2(?![A-Za-z0-9])|"
    r"암모니아|ammonia|(?<![A-Za-z0-9])NH3(?![A-Za-z0-9])|"
    r"산소\s*가스|oxygen\s*gas|(?<![A-Za-z0-9])O2(?![A-Za-z0-9]))",
    re.I,
)
_ALTERNATE_REACTANT = re.compile(
    r"(?:물|수증기|H[₂2]O|water|TMA|전구체|산화제|reactant|precursor)"
    r"\s*(?:은|는|을|를|과|와)?\s*(?:(?:다른\s*(?:걸|것|종류|물질)?(?:로|으로)?)|대신|바꿔|교체|변경|제외|없이|빼고|말고)|"
    r"(?:대신|바꿔|교체|변경)\s*(?:물|H[₂2]O|water|TMA|전구체|산화제)",
    re.I,
)
# The fallback parser intentionally does not guess qualitative constraints.
_QUALITATIVE_CONSTRAINT = re.compile(
    r"(?:purge|퍼지|pulse|펄스|Ar\s*유량|아르곤\s*유량|유량|온도|temperature)"
    r"(?:.{0,16}?)"
    r"(?:길게|길어|짧게|짧아|충분히|넉넉히|더\s*오래|더\s*길|더\s*짧|더\s*높|더\s*낮|높여|낮춰|올려|내려|"
    r"증가|감소|변경|조절|조정|최적화해|세게|약하게|높게|낮게|많이|적게)|"
    r"(?:longer|shorter|higher|lower|increase|decrease|reduce|extend)\s*(?:.{0,12}?)"
    r"(?:purge|pulse|flow|temperature)",
    re.I,
)


def _semantic_scope_error(text: str) -> str | None:
    """Fail closed before numeric extraction; no hidden chemistry substitutions."""
    # Any request about replacement/novel reactants is unsupported even when
    # neither a known chemical formula nor a specific chemical name is present.
    if re.search(r"(?:새로운|새|다른|신규|미지의)\s*(?:산화제|전구체|반응물|reactant|precursor)|"
                 r"(?:산화제|전구체|반응물)\s*(?:교체|바꿔|변경|쓰자|선택|도입)", text, re.I):
        return "새로운 반응물·전구체·산화제 변경은 이 TMA/H₂O 데이터로 검증할 수 없습니다."
    if _UNSUPPORTED_CHEMISTRY.search(text) or _ALTERNATE_REACTANT.search(text):
        return ("이 데이터는 TMA/H₂O thermal ALD 조건만 다룹니다. "
                "산화제·전구체 변경 요청에는 해당 논문 레시피를 적용할 수 없습니다.")
    if _QUALITATIVE_CONSTRAINT.search(text):
        return ("'길게/충분히/높게' 등의 정량화되지 않은 공정 제약이 있습니다. "
                "측정된 수준과 수치·단위를 명시해 주세요.")
    return None


_UNIT_RE = re.compile(r"(?<![\d.+-])(\d+(?:\.\d+)?)\s*(°\s*C|℃|도|degrees?\s*C?|sccm|ms|밀리초|초|seconds?|sec|nm|C)(?![A-Za-z])", re.I)
_QUAL_RE = r"(?:이상|이하|미만|초과|최소|최대|적어도|많아야|at\s+least|at\s+most|under|below|over|above|no\s+more\s+than|only|exactly|만|고정|정확히)"

# Only these explicit comparison operators are supported. They are validated
# *before* unknown punctuation is discarded by the conservative text parser.
# A symbol must immediately precede one recognized number+unit span; otherwise
# we refuse the whole request rather than substituting an equality constraint.
_SYMBOLIC_COMPARISON = re.compile(r"<=|>=|<|>|=")
_UNSUPPORTED_COMPARISON = re.compile(r"!=|≠|==|=<|=>|<>|><|[≈≃≅≦≧≲≳≨≩~∼＜＞]")
_SYMBOLIC_QUALIFIER = {'<':'upper_strict', '<=':'upper',
                      '>':'lower_strict', '>=':'lower', '=':'exact'}


def _symbolic_constraints(text: str, quantities: list[re.Match]) -> tuple[dict[int, str], str | None]:
    """Bind every comparison to the immediately following recognized quantity.

    This prevents ``purge > 10초`` from silently becoming ``purge = 10초``.
    Never rely on removing punctuation to determine constraint semantics.
    """
    # Do not silently erase other mathematical relation symbols (e.g. ≮, ≯,
    # ≡, ⩽, ∈) via the general punctuation scrubber. A new symbol is rejected
    # until the parser explicitly implements its semantics. '+' is allowed in
    # the supported chemical name TMA+H2O, but is never a numeric qualifier.
    unknown_math_symbol = any(unicodedata.category(ch) == 'Sm'
                              and ch not in '<>=+' for ch in text)
    if _UNSUPPORTED_COMPARISON.search(text) or unknown_math_symbol:
        return {}, ('지원하지 않는 비교·제외 연산자가 있습니다. ≠, != 등의 조건을 '
                    '임의의 정확한 값으로 바꾸지 않습니다. 지원하는 기호는 <, >, <=, >=, ≤, ≥, = 입니다.')
    operators = list(_SYMBOLIC_COMPARISON.finditer(text))
    assigned = {}
    for token in operators:
        matching = [q for q in quantities if not text[token.end():q.start()].strip()
                    and q.start() >= token.end()]
        if len(matching) != 1:
            return {}, ('비교 기호는 바로 뒤의 수치·단위에 붙여야 합니다. ' 
                        '예: purge >= 10초. 해석할 수 없는 조건은 추천에 사용하지 않습니다.')
        position = matching[0].start()
        if position in assigned:
            return {}, '한 수치에 비교 기호가 여러 개 있습니다. 조건을 명확히 작성해 주세요.'
        assigned[position] = token.group(0)
    return assigned, None


def _numeric_qualifier(before: str, after: str, symbol: str | None = None) -> str | None:
    """Only adjacent modifiers belong to a number; never borrow a neighbor's bound."""
    before_m=re.search(r"(최소|최대|적어도|많아야|at\s+least|at\s+most|under|below|over|above|no\s+more\s+than|only|exactly|정확히|고정)\s*$", before, re.I)
    after_m=re.match(r"\s*(이상|이하|미만|초과|만|고정|정확히|at\s+least|at\s+most|only|exactly)",after,re.I)
    words=[m.group(1) for m in (before_m,after_m) if m]
    groups=[]
    if symbol is not None:
        groups.append(_SYMBOLIC_QUALIFIER[symbol])
    for word in words:
        w=re.sub(r"\s+", "", word.lower())
        if w in ('최소','이상','적어도','atleast','over','above','초과'):groups.append('lower_strict' if w in ('over','above','초과') else 'lower')
        elif w in ('최대','이하','많아야','atmost','under','below','미만','nomorethan'):groups.append('upper_strict' if w in ('under','below','미만') else 'upper')
        else:groups.append('exact')
    kinds={k.replace('_strict','') for k in groups}
    if len(kinds)>1:return 'conflict'
    if not groups:return None
    return 'lower_strict' if 'lower_strict' in groups else 'upper_strict' if 'upper_strict' in groups else groups[0]


# Free-text parsing is a controlled-input convenience, not general NLP.
# Unrecognized numerical quantities and entirely new request clauses must
# never be silently discarded and replaced by default ALD conditions.
_KNOWN_CLAUSE = re.compile(
    r"(?:al2o3|alumina|산화알루미늄|(?:목표\s*)?두께|nm|ALD|"
    r"온도|temperature|deg|°|℃|\d\s*도|\bC\b|sccm|유량|아르곤|\bAr\b|"
    r"pulse|펄스|purge|퍼지|gpc|성장률|증착률|시퀀스|공정\s*시간|"
    r"처리\s*시간|cycle\s*time|sequence\s*time|균형|balanced?|"
    r"근거|논문|출처|한계|검증|보고서|추천|비교|분석|시간\s*최소)", re.I,
)


def _unhandled_quantity_error(text: str, quantities: list[re.Match]) -> str | None:
    # Blank parsed numeric spans, then chemical formulas containing digits.
    # Any remaining digit means the request contains an additional number,
    # e.g. an unsupported 1:2 TMA/H2O ratio or 2% tolerance.
    chars = list(text)
    for match in quantities:
        chars[match.start():match.end()] = ' ' * (match.end() - match.start())
    remainder = ''.join(chars)
    remainder = re.sub(r"al2o3|h2o", "", remainder, flags=re.I)
    if re.search(r"\d", remainder):
        return ("해석되지 않은 숫자 또는 비율이 있습니다. 지원하는 입력은 목표 두께(nm), "
                "온도(°C), Ar 유량(sccm), pulse(ms), purge(초)뿐입니다.")
    return None


# A whitelist of understood *language*, not an ever-growing blacklist of unsafe terms.
# After removing parsed quantities and a small set of permitted phrases, any
# remaining nontrivial text blocks the recommendation. An unknown clause must
# never be silently interpreted as the default (time optimization).
_EXPLICIT_GOALS = [
    r"(?:GPC|성장률|증착률)\s*(?:를|을|가|은|의)?\s*(?:최대화(?:해\s*줘)?|최대한\s*높여\s*줘|가장\s*높은\s*조건|최고|우선|높여\s*줘|높은)",
    r"(?:maximize|highest|maximum)\s*(?:the\s*)?(?:GPC|growth\s*rate)",
    r"(?:공정\s*시간|시퀀스\s*시간|처리\s*시간|sequence\s*time|cycle\s*time)\s*(?:을|를|의)?\s*(?:최소화|최소|단축|줄여\s*줘|줄이|짧게)",
    r"(?:shortest|fastest|minimum|minimize)\s*(?:sequence\s*|cycle\s*)?time",
    r"(?:시간\s*최소화|GPC\s*최대화|균형|balanced?)",
]
_ALLOWED_FILLER = [
    r"산화알루미늄|alumina|Al2O3|박막|ALD|thermal",
    r"TMA\s*[/+]\s*H2O|TMA|H2O|Si\s*기판",
    r"(?:목표\s*)?두께|nm|증착(?:하고\s*싶어)?|만들(?:어\s*줘)?",
    r"온도|temperature|Ar|아르곤|유량|flow|pulse|펄스|purge|퍼지",
    r"(?:최대|최소|정확히|고정|적어도|많아야|이상|이하|미만|초과|only|exactly|at\s*least|at\s*most)",
    r"(?:조건|각각|에서|으로|에|로|만|는|은|을|를|가|이|도|값|필수|사용|필요해|필요합니다|싶어|주세요|해줘|해\s*줘)",
    r"(?:시퀀스|공정|처리)\s*시간|시간|GPC|성장률|증착률",
    r"(?:추천(?:해\s*줘)?|분석(?:해\s*줘)?|비교(?:해\s*줘)?|검토(?:해\s*줘)?|확인(?:해\s*줘)?)",
    r"(?:근거|논문|출처|한계|검증|보고서|그리고|및|또는|와|과|함께)",
]


def _unrecognized_intent(text: str, matches: list[re.Match]) -> str | None:
    """Fail closed on text outside a documented mini-language.

    This is intentionally *not* general Korean understanding. User-facing
    structured controls are the authoritative input path. Numeric matches are
    removed by span so their qualifiers can be checked independently.
    """
    chars=list(text)
    for match in matches:
        chars[match.start():match.end()]=[' ']*(match.end()-match.start())
    remainder=''.join(chars)
    # Explicit goal must be recognized before consuming its constituent tokens.
    for pattern in _EXPLICIT_GOALS:
        remainder=re.sub(pattern,' ',remainder,flags=re.I)
    for pattern in _ALLOWED_FILLER:
        remainder=re.sub(r'(?<![A-Za-z])(?:'+pattern+r')(?![A-Za-z])',' ',remainder,flags=re.I)
    remainder=re.sub(r'[\s\W_]+','',remainder,flags=re.UNICODE)
    if remainder:
        return (f"지원하지 않거나 모호한 요청 표현이 있습니다: '{remainder[:60]}'. "
                "수치·단위가 있는 허용 조건만 입력하거나 구조화 입력을 사용해 주세요.")
    return None


def _unknown_clause_error(text: str) -> str | None:
    for clause in re.split(r"[,，;；\n]+", text):
        clause = clause.strip()
        if clause and not _KNOWN_CLAUSE.search(clause):
            return (f"지원 범위를 확인할 수 없는 추가 요청: '{clause[:72]}'. "
                    "해당 내용을 무시한 채 기본 레시피를 추천하지 않습니다.")
    return None


REQUEST_DEFAULTS = {"target_nm": 10.0, "min_temp": 175.0, "max_temp": 275.0,
                    "min_flow": 10.0, "max_flow": 20.0, "min_pulse": 20.0,
                    "max_pulse": 40.0, "min_purge": 10.0, "max_purge": 20.0,
                    "objective": "time"}


def validate_structured_request(values: dict) -> dict:
    """Authoritative typed request path; no unsupported field can be discarded.

    Return a fully populated request or a warning. Reject booleans, NaNs,
    unknown keys, conflicting bounds and requests without measured candidates.
    """
    if not isinstance(values, dict):
        return {"warning": "구조화된 요청은 필드 이름이 있는 객체여야 합니다."}
    unexpected = set(values) - set(REQUEST_DEFAULTS)
    if unexpected:
        return {"warning": f"지원하지 않는 조건 필드: {', '.join(sorted(map(str,unexpected)))}"}
    params = dict(REQUEST_DEFAULTS)
    for key, val in values.items():
        if key == 'objective':
            if not isinstance(val,str) or val not in ('time','gpc','balanced'):
                return {'warning':'최적화 목적은 time, gpc, balanced 중 선택해야 합니다.'}
            params[key]=val
        else:
            number = _finite_real(val)
            if number is None:
                return {'warning': f'{key}: 유한한 실수만 허용합니다(복소수·불리언·범위 초과 수치 거부).'}
            params[key] = number
    result=optimize_recipe(**params)
    if 'error' in result:
        return {'warning':result['error']}
    return params


def parse_request(text: str) -> dict:
    """Conservative Korean/English parser. Ambiguity => warning and no recommendation.

    Supports nm thickness, °C temperature, sccm Ar, ms pulse, seconds purge,
    with min/max/exact qualifiers. This is a deterministic fallback, NOT an LLM.
    """
    p=(str(text).translate(_SUBSCRIPT_TRANSLATE).strip()
       .replace('≤','<=').replace('≥','>='))
    result={}
    if re.search(r"-\s*\d+(?:\.\d+)?\s*(?:nm|℃|°\s*C|도|sccm|ms|초)",p,re.I):
        return {'warning':'음수 공정값은 해석하지 않습니다. 수치를 확인해 주세요.'}
    if re.search(r"\d+(?:\.\d+)?\s*(?:µm|μm|um|K|s|mbar|rpm)(?![A-Za-z0-9])",p,re.I):
        return {'warning':'해석하지 못한 수치 단위가 있습니다. nm, °C, sccm, ms, 초 단위를 사용해 주세요.'}
    if len(p) > 1200:
        return {'warning':'요청이 너무 깁니다. 공정조건을 1200자 이내로 간결하게 입력해 주세요.'}
    scope=request_scope_error(p)
    if scope: return {'warning':scope}
    unknown_clause = _unknown_clause_error(p)
    if unknown_clause:
        return {'warning': unknown_clause}
    quantity_matches = list(_UNIT_RE.finditer(p))
    symbolic_by_quantity, symbol_error = _symbolic_constraints(p, quantity_matches)
    if symbol_error:
        return {'warning': symbol_error}
    # Do not treat a *bare* process-variable name as an optional remark.
    # If a variable is mentioned, at least one measured-unit quantity of that
    # kind must be present; otherwise the parser silently applies DOE defaults.
    # These guards concern the supported mini-language, NOT general NLP.
    referenced_variables = {
        'temperature_C': bool(re.search(r'온도|(?<![A-Za-z])temperature(?![A-Za-z])', p, re.I)),
        'flow_sccm': bool(re.search(r'유량|아르곤|(?<![A-Za-z])(?:Ar|flow)(?![A-Za-z])', p, re.I)),
        'pulse_ms': bool(re.search(r'(?<![A-Za-z])pulse(?![A-Za-z])|펄스', p, re.I)),
        'purge_s': bool(re.search(r'(?<![A-Za-z])purge(?![A-Za-z])|퍼지', p, re.I)),
    }
    quantified_variables = set()
    for match in quantity_matches:
        unit = re.sub(r'\s+', '', match.group(2)).lower()
        if unit in ('°c','℃','도','degreec','degreesc','c'):
            quantified_variables.add('temperature_C')
        elif unit == 'sccm':
            quantified_variables.add('flow_sccm')
        elif unit in ('ms', '밀리초'):
            quantified_variables.add('pulse_ms')
        elif unit in ('초', 'second', 'seconds', 'sec'):
            quantified_variables.add('purge_s')
    missing_quantities = [label for key, label in (
        ('temperature_C', '온도'), ('flow_sccm', 'Ar 유량'),
        ('pulse_ms', 'pulse'), ('purge_s', 'purge'))
        if referenced_variables[key] and key not in quantified_variables]
    if missing_quantities:
        return {'warning': ('수치·단위 없이 언급한 공정변수가 있습니다: '
                + ', '.join(missing_quantities)
                + '. 해당 변수를 임의 기본값으로 처리하지 않습니다. 수치를 입력하거나 구조화 입력을 이용해 주세요.')}
    unhandled_quantity = _unhandled_quantity_error(p, quantity_matches)
    if unhandled_quantity:
        return {'warning': unhandled_quantity}
    not_recognized = _unrecognized_intent(p, quantity_matches)
    if not_recognized:
        return {'warning': not_recognized}
    fields={"temperature_C":(175.,275.),"flow_sccm":(10.,20.),"pulse_ms":(20.,40.),"purge_s":(10.,20.)}
    seen=[]
    nm_count=0
    for match in quantity_matches:
        value=float(match.group(1)); unit=match.group(2).replace(' ','').lower()
        before=p[max(0,match.start()-28):match.start()]
        after=p[match.end():min(len(p),match.end()+18)]
        qualifier=_numeric_qualifier(before,after,symbolic_by_quantity.get(match.start()))
        if qualifier=='conflict':return {'warning':f'{match.group(0)}의 상·하한 표현이 충돌합니다.'}
        if unit=='nm':
            nm_count+=1
            if qualifier and qualifier!='exact':return {'warning':'목표 두께의 상·하한 요청은 지원하지 않습니다. 하나의 목표 두께를 입력해 주세요.'}
            result['target_nm']=value; continue
        if unit in ('°c','℃','도','degreec','degreesc','c'):field='temperature_C'
        elif unit=='sccm':
            if not re.search(r'(?:Ar|아르곤|유량|flow)',before+after,re.I):
                return {'warning':'sccm의 대상 가스가 명확하지 않습니다. Ar 유량을 명시해 주세요.'}
            field='flow_sccm'
        elif unit in ('ms','밀리초'):
            if not re.search(r'(?:pulse|펄스)',before+after,re.I):return {'warning':'ms의 대상 pulse가 불명확합니다. pulse를 명시해 주세요.'}
            field='pulse_ms'
        elif unit in ('초','second','seconds','sec'):
            if not re.search(r'(?:purge|퍼지)',before+after,re.I):return {'warning':'초 단위의 대상이 불명확합니다. purge 시간을 명시해 주세요.'}
            field='purge_s'
        else:return {'warning':f'해석할 수 없는 단위: {unit}'}
        if not math.isfinite(value):return {'warning':'유한한 공정 조건만 지원합니다.'}
        if qualifier is None: qualifier='exact'  # 'Ar 20sccm' means 20 sccm only, never silently a bound.
        lower,upper=fields[field]
        if qualifier.startswith('lower'):
            lower=max(lower, math.nextafter(value,math.inf) if qualifier=='lower_strict' else value)
        elif qualifier.startswith('upper'):
            upper=min(upper, math.nextafter(value,-math.inf) if qualifier=='upper_strict' else value)
        else:
            lower=max(lower,value);upper=min(upper,value)
        fields[field]=(lower,upper)
        seen.append(field)
    if nm_count!=1:
        return {'warning':'목표 두께를 하나만 명시해 주세요 (예: Al2O3 10nm).'}
    if not (0.1 <= result['target_nm'] <= 1000):
        return {'warning':'목표 두께는 0.1~1000 nm입니다. 이 범위를 벗어난 요청은 분석하지 않습니다.'}
    if len(seen)!=len(set(seen)) and any(lo>hi for lo,hi in fields.values()):
        return {'warning':'같은 변수에 서로 충돌하는 조건을 지정했습니다.'}
    if any(lo>hi for lo,hi in fields.values()):
        return {'warning':'실측 수준 또는 사용자 상·하한과 충돌하는 조건입니다.'}
    for field,(lo,hi) in fields.items():
        if not any(lo<=level<=hi for level in LEVELS[field]):
            return {'warning':f'{field}: 논문에서 실측한 수준이 요청 범위에 없어 추천을 중단합니다.'}
    # Unrecognized constraint types must not silently vanish.
    if re.search(r'(?:유량|sccm|purge|퍼지|pulse|펄스|온도|temperature)\s*(?:를|은|는|만|도|값을)?\s*(?:올려|내려|증가|감소|높게|낮게|바꿔|조절)',p,re.I):
        return {'warning':'정량화되지 않은 공정 제약이 있습니다. 단위와 수치로 조건을 명시해 주세요.'}
    result.update({'min_temp':fields['temperature_C'][0], 'max_temp':fields['temperature_C'][1],
                   'min_flow':fields['flow_sccm'][0],'max_flow':fields['flow_sccm'][1],
                   'min_pulse':fields['pulse_ms'][0],'max_pulse':fields['pulse_ms'][1],
                   'min_purge':fields['purge_s'][0],'max_purge':fields['purge_s'][1]})
    # Explicit user objective must not be silently replaced with the default.
    gpc_goal = bool(re.search(
        r"(?:GPC|성장률|증착률)(?:\s*[가를을은의]?\s*)"
        r"(?:최대(?:한)?|최고|우선|높은|높여|가장\s*높|maximize)|"
        r"(?:maximize|highest|maximum)\s*(?:the\s*)?(?:GPC|growth\s*rate)",p,re.I))
    time_goal = bool(re.search(
        r"(?:공정\s*시간|시퀀스\s*시간|처리\s*시간|sequence\s*time|cycle\s*time)"
        r"(?:\s*[을를의]?\s*)(?:최소|단축|짧|줄이|reduce|minimize)|"
        r"(?:shortest|fastest|minimum|minimize)\s*(?:sequence\s*|cycle\s*)?time",p,re.I))
    balanced_goal = bool(re.search(r'균형|balanced?',p,re.I))
    if re.search(r'(?:GPC|성장률|증착률)\s*[을를가]?\s*(?:최소화|낮춰|줄여|minimize|minimum)',p,re.I):
        return {'warning':'GPC 최소화 목표는 현재 지원하지 않습니다. 지원되는 목적은 GPC 최대화/시퀀스 시간 최소화/균형입니다.'}
    if gpc_goal and time_goal and not balanced_goal:
        return {'warning':'GPC 최대화와 시간 최소화 목표가 동시에 요청되었습니다. 하나를 선택하거나 균형 목표를 명시해 주세요.'}
    if re.search(r'(?:GPC|성장률|증착률)', p, re.I) and not (gpc_goal or balanced_goal):
        return {'warning':'GPC 관련 요청의 방향이 불분명합니다. GPC 최대화 또는 균형 목표를 명시해 주세요.'}
    if re.search(r'(?:공정\s*시간|시퀀스\s*시간|처리\s*시간|sequence\s*time|cycle\s*time)', p, re.I) and not (time_goal or balanced_goal):
        return {'warning':'공정시간 관련 요청의 방향이 불분명합니다. 시퀀스 시간 최소화 또는 균형 목표를 명시해 주세요.'}
    result['objective'] = 'balanced' if balanced_goal else ('gpc' if gpc_goal else 'time')
    return result


def search_evidence(query: str, k: int = 3) -> list[dict]:
    """Retrieve relevant source-linked cards, NOT vector RAG or live literature search.

    Previously this returned 3 cards even when overlap was zero. In that case
    the LLM could falsely claim evidence for an unrelated query. Return []
    instead, so agent provenance gating can reject unsupported retrieval.
    """
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        return []
    if isinstance(k, bool) or not isinstance(k, int) or not (1 <= k <= len(EVIDENCE)):
        return []
    def terms(text: str) -> set[str]:
        canonical=text.translate(_SUBSCRIPT_TRANSLATE).lower()
        return set(re.findall(r"[a-z]+[0-9]*|[가-힣]+|\d+(?:\.\d+)?",canonical))
    wanted=terms(query)-{'the','and','for','please','with','추천','해줘','확인','데이터','할','수','있어'}
    ranked=[]
    for item in EVIDENCE:
        hits=len(wanted & terms(item['text']+' '+item['title']))
        if hits>0:
            ranked.append((hits,item))
    ranked.sort(key=lambda z:z[0],reverse=True)
    return [item for _,item in ranked[:k]]


def build_report(best: dict, baseline: dict, issues: list[str], objective: str) -> str:
    delta = 100 * (baseline["sequence_time_s"]-best["sequence_time_s"]) / baseline["sequence_time_s"]
    if issues:
        comparison = (f"**[비교 제한]** 기존 v0는 다음 요청 제약을 위반하므로 동등한 대안으로 비교할 수 없습니다: "
                      f"{', '.join(issues)}. 아래 시간 값은 참고 계산치일 뿐입니다.")
    else:
        comparison = (f"**[단순화 수식 내 비교]** v0 {baseline['sequence_time_s']/60:.2f}분 → "
                      f"v1 {best['sequence_time_min']:.2f}분, 가정 시퀀스 시간 "
                      f"{abs(delta):.1f}% {'감소' if delta >= 0 else '증가'} "
                      f"(동일 수식·실측 조건 비교). 실제 장비 생산성 증거는 아닙니다.")
    return f"""## ALD-OPTIX 공정 검토 리포트
**[관측]** Pan & Lei (2025), Table 5에서 동일 조건 2회 측정한 GPC 평균을 근거로 후보를 선정했습니다. 다른 reactor로 일반화할 수 없습니다.

**[관측 기반 계산]** 추천 조건은 **{int(best['temperature_C'])}°C / Ar {int(best['flow_sccm'])} sccm / pulse {int(best['pulse_ms'])} ms / purge {int(best['purge_s'])} s**입니다. GPC 평균은 **{best['gpc_mean_A']:.3f} Å/cycle**, 필요한 cycle은 **{int(best['cycles'])}회**입니다.

**[단순화된 추정]** 1 cycle을 `TMA pulse + purge + H₂O pulse + purge`로 단순화한 시퀀스 시간은 **{best['sequence_time_min']:.2f}분**입니다. 밸브·펌프·실제 장비 동작 시간 등은 제외되어 실제 제조 시간이나 비용 절감 성과를 의미하지 않습니다.

{comparison}

**[실험 전 확인 필요]** ALD saturation 검증, 전구체 흡착 특성, purge 충분성, 막 두께 균일도·밀도·불순물·전기적 특성 및 장비별 조건을 추가 확인해야 합니다. 데이터 기반 후보 추천이며 품질 승인이나 양산 레시피 인증이 아닙니다.

출처: {SOURCE} ({DOI})."""


# ------------------------- Audited evaluation -------------------------
def nested_cross_validate() -> tuple[dict, pd.DataFrame]:
    """Outer grouped 16-fold CV with *inner grouped CV* selecting mean / main / pairwise.

    Selection never sees the outer test group. This addresses the selection-on-CV
    concern in the exploratory v1 comparison. No independent reactor validation.
    """
    from collections import Counter
    d = load_data()
    codes = d[CODE_NAMES].to_numpy(dtype=float)
    x_main = codes
    x_interaction = make_features(codes)
    y = d["gpc_A_per_cycle"].to_numpy(dtype=float)
    groups = d[CODE_NAMES].astype(str).agg("_".join, axis=1).to_numpy()
    logo = LeaveOneGroupOut()
    preds = np.zeros_like(y)
    selected: list[str] = []

    def predict(train: np.ndarray, test: np.ndarray, kind: str) -> np.ndarray:
        if kind == "mean":
            return np.full(len(test), y[train].mean())
        feat = x_main if kind == "main" else x_interaction
        model = Ridge(alpha=0.1)
        model.fit(feat[train], y[train])
        return model.predict(feat[test])

    for train, test in logo.split(codes, y, groups):
        inner = LeaveOneGroupOut()
        inner_scores = {}
        for kind in ("mean", "main", "interaction"):
            inner_real, inner_pred = [], []
            for inner_tr, inner_te in inner.split(codes[train], y[train], groups[train]):
                a, b = train[inner_tr], train[inner_te]
                inner_real.extend(y[b].tolist())
                inner_pred.extend(predict(a, b, kind).tolist())
            inner_scores[kind] = mean_absolute_error(inner_real, inner_pred)
        chosen = min(inner_scores, key=inner_scores.get)
        selected.append(chosen)
        preds[test] = predict(train, test, chosen)
    count = Counter(selected)
    metrics = {
        "n_runs": int(len(y)), "n_conditions": int(len(np.unique(groups))),
        "MAE_A_per_cycle": float(mean_absolute_error(y, preds)),
        "RMSE_A_per_cycle": float(root_mean_squared_error(y, preds)),
        "model_choices": dict(count),
        "note": "Nested leave-one-condition-out CV: outer held-out condition never used for inner model selection. Still one small reactor dataset, no external validation.",
    }
    out = d[["run_order"] + VAR_NAMES + ["gpc_A_per_cycle"]].copy()
    out["nested_pred_A_per_cycle"] = preds
    return metrics, out


def sensitivity_analysis(target_nm: float = 10.0, overhead_s_per_cycle: float = 0.0,
                         max_temp: float = 275, min_purge: float = 10,
                         min_flow: float = 10, max_flow: float = 20, max_purge: float = 20,
                         min_temp: float = 175, min_pulse: float = 20, max_pulse: float = 40) -> dict:
    """Examine whether chosen sequence remains preferred as *hypothetical* overhead changes.

    Overhead represents extra seconds per cycle; this is NOT observed reactor data.
    """
    # bool is a subclass of int in Python; it must not mean 1 second.
    # Reject strings, complex values, nonfinite numbers and very large ints
    # before comparing them with numeric limits (which otherwise may raise
    # an unhelpful TypeError or OverflowError).
    if (isinstance(overhead_s_per_cycle, (bool, np.bool_)) or
            not isinstance(overhead_s_per_cycle, (int, float, np.integer, np.floating))):
        raise ValueError("cycle당 추가 지연시간은 0~600초 범위의 유한한 숫자여야 합니다.")
    try:
        overhead_s_per_cycle = float(overhead_s_per_cycle)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("cycle당 추가 지연시간은 유한한 숫자여야 합니다.") from None
    if not math.isfinite(overhead_s_per_cycle) or not (0 <= overhead_s_per_cycle <= 600):
        raise ValueError("가정한 cycle당 추가 지연시간은 0~600초여야 합니다.")
    checked = optimize_recipe(target_nm=target_nm, max_temp=max_temp, min_temp=min_temp,
                              min_flow=min_flow, max_flow=max_flow, min_purge=min_purge,
                              max_purge=max_purge, min_pulse=min_pulse, max_pulse=max_pulse)
    if 'error' in checked:
        return checked
    d = checked['ranking'].copy()
    if d.empty:
        return {"error": "해당 조건에서 비교 가능한 실측 레시피가 없습니다."}
    d["cycles"] = d.gpc_mean_A.map(lambda v: estimated_cycles(target_nm, v))
    d["sequence_s"] = d.apply(lambda r: minimum_sequence_time_s(int(r.cycles), int(r.pulse_ms), int(r.purge_s)), axis=1)
    d["estimated_total_s"] = d.sequence_s + d.cycles * overhead_s_per_cycle
    d.sort_values(["estimated_total_s", "gpc_mean_A"], ascending=[True, False], inplace=True)
    return {"best": d.iloc[0].to_dict(), "ranking": d, "assumed_overhead_s_per_cycle": overhead_s_per_cycle}


def quality_gate(request: dict, best: dict | None = None) -> dict:
    """Independent fail-closed integrity gate for every published recipe field.

    REVIEW_REQUIRED means *arithmetically checked, NOT product or process approved*.
    Never trust display aliases such as sequence_time_min or accept fractional
    cycle counts; the published report consumes both fields.
    """
    warnings = [
        "원 논문의 GPC는 200회 cycle 실험 결과이며 목표 두께 환산은 선형 성장 가정에 의존합니다.",
        "실제 cycle overhead·purge 포화도·전기 특성·막 균일도는 검증되지 않았습니다.",
        "본 서비스의 공정 조건 제안은 양산 레시피 승인이나 자동 장비 제어가 아닙니다.",
    ]
    def reject(messages: list[str]) -> dict:
        return {"status": "REJECT", "errors": messages,
                "warnings": warnings, "source": DOI}

    if not isinstance(request, dict):
        return reject(["요청 조건이 객체가 아닙니다."])
    preflight = validate_structured_request(request)
    if 'warning' in preflight or request.get('warning'):
        return reject(["요청 입력 검증 실패: " + str(preflight.get('warning', request.get('warning')))])
    if not isinstance(best, dict):
        return reject(["추천 결과가 객체가 아닙니다."])

    # Every numeric field used in report or shown as a measurement must be
    # present, finite, and genuinely numeric (bool/string coercion forbidden).
    required = (*VAR_NAMES, 'target_nm', 'gpc_mean_A', 'gpc_sd_A',
                'replications', 'cycles', 'sequence_time_s', 'sequence_time_min')
    missing = sorted(set(required) - set(best))
    if missing:
        return reject(["보고서 필수 필드 누락: " + ", ".join(missing)])
    numbers = {}
    for key in required:
        # Use the same scalar policy as the request validator. In particular,
        # np.complexfloating inherits np.number but float(np.complex128(...))
        # silently drops the imaginary component with only a ComplexWarning.
        # No measured/output field may become valid by numeric coercion.
        value = _finite_real(best[key])
        if value is None:
            return reject([f"추천 결과 {key}는 유한한 실수형 숫자여야 합니다(복소수·불리언·문자열·NaN·무한대 거부)."])
        numbers[key] = value

    errors = []
    known = condition_means()  # fingerprinted source data
    mask = np.ones(len(known), dtype=bool)
    for key in VAR_NAMES:
        mask &= np.isclose(known[key].to_numpy(), numbers[key], rtol=0, atol=1e-8)
    if int(mask.sum()) != 1:
        return reject(["실측 DOE 조건에 없는 레시피입니다. 외삽 결과 사용 금지."])
    measured = known.loc[mask].iloc[0]
    target = float(preflight['target_nm'])
    expected_gpc = float(measured['gpc_mean_A'])
    expected_sd = float(measured['gpc_sd_A'])
    expected_reps = float(measured['replications'])
    expected_cycles = estimated_cycles(target, expected_gpc)
    expected_time_s = minimum_sequence_time_s(
        expected_cycles, int(measured['pulse_ms']), int(measured['purge_s']))
    expected_minutes = expected_time_s / 60

    def equal(key: str, expected: float, tol: float = 1e-7) -> bool:
        return math.isclose(numbers[key], expected, rel_tol=0.0, abs_tol=tol)

    if not equal('target_nm', target):
        errors.append("추천 결과의 목표 두께가 사용자 요청과 다릅니다.")
    if not equal('gpc_mean_A', expected_gpc):
        errors.append("추천 GPC가 해당 실측 조건의 2회 평균과 다릅니다.")
    if not equal('gpc_sd_A', expected_sd):
        errors.append("추천 GPC 표준편차가 원시 측정값과 다릅니다.")
    if not equal('replications', expected_reps, 1e-9):
        errors.append("추천 반복측정 횟수가 원시 측정값과 다릅니다.")
    if not (numbers['cycles'].is_integer() and equal('cycles', expected_cycles, 1e-9)):
        errors.append("추천 cycle 수는 목표 두께와 GPC로 산출한 정확한 정수여야 합니다.")
    if not equal('sequence_time_s', expected_time_s, 1e-5):
        errors.append("추천 시퀀스 시간(초)이 계산값과 다릅니다.")
    if not equal('sequence_time_min', expected_minutes, 1e-7):
        errors.append("추천 시퀀스 시간(분)이 초 단위 계산값과 일치하지 않습니다.")

    errors.extend(constraint_check(best, min_temp=preflight['min_temp'], max_temp=preflight['max_temp'],
        min_flow=preflight['min_flow'], max_flow=preflight['max_flow'],
        min_purge=preflight['min_purge'], max_purge=preflight['max_purge'],
        min_pulse=preflight['min_pulse'], max_pulse=preflight['max_pulse']))

    # Independent, raw-CSV candidate ranking, with no reuse of optimizer output.
    if not errors:
        try:
            oracle = independent_reference(preflight)
            expected = oracle.get('best')
            if expected is None or any(not math.isclose(numbers[key], float(expected[key]),
                                    rel_tol=0, abs_tol=1e-7)
                                    for key in (*VAR_NAMES, 'gpc_mean_A', 'sequence_time_s')):
                errors.append("추천 후보가 독립 참조 계산의 목적함수 최상위 후보가 아닙니다.")
            if preflight['objective'] == 'balanced' and 'balance_score' not in best:
                errors.append('균형 목적 점수(balance_score)는 balanced 추천의 필수 필드입니다.')
            if preflight['objective'] != 'balanced' and 'balance_score' in best:
                errors.append('비균형 목적의 추천에 균형 점수가 포함되었습니다. 이전 계산값 혼입 가능성이 있습니다.')
            if 'balance_score' in best:
                value = _finite_real(best['balance_score'])
                if value is None:
                    errors.append("균형 목적 점수는 유한한 실수형 숫자여야 합니다.")
                elif expected is None or 'balance_score' not in expected or not math.isclose(
                        value, float(expected['balance_score']), rel_tol=0, abs_tol=1e-7):
                    errors.append("균형 목적 점수가 독립 참조 계산과 다릅니다.")
        except (TypeError, ValueError, KeyError, OverflowError):
            errors.append("독립 참조 계산 중 입력 또는 후보 검증에 실패했습니다.")
    return reject(errors) if errors else {"status": "REVIEW_REQUIRED", "errors": [],
                                          "warnings": warnings, "source": DOI}


def scenario_suite() -> list[dict]:
    cases = [
        ("기본 업무", dict(target_nm=10, objective="time")),
        ("온도 200°C 이하", dict(target_nm=10, max_temp=200, objective="time")),
        ("긴 purge가 필수", dict(target_nm=10, min_purge=20, objective="time")),
        ("실측 범위 이탈", dict(target_nm=10, max_temp=150, objective="time")),
        ("충돌하는 제한", dict(target_nm=10, min_purge=20, max_purge=10, objective="time")),
    ]
    records = []
    for name, req in cases:
        result = optimize_recipe(**req)
        if "error" in result:
            records.append({"scenario":name,"status":"거부/검토 필요","n_candidates":0,
                            "recommended":"-","note":result["error"]})
        else:
            r=result["best"]; gate=quality_gate(req,r)
            records.append({"scenario":name,"status":gate["status"],"n_candidates":result["n_feasible"],
                            "recommended":f"{r['temperature_C']:.0f}°C / {r['purge_s']:.0f}s",
                            "note":"추가 실험/물성 승인 필요"})
    return records


# --------------------- Reproducible engineering casebook ---------------------
ENGINEERING_CASES = [
    ("C01", "GPC 최우선", dict(target_nm=10, objective="gpc")),
    ("C02", "GPC 최우선 · 200°C 이하", dict(target_nm=10, max_temp=200, objective="gpc")),
    ("C03", "시퀀스 최단", dict(target_nm=10, objective="time")),
    ("C04", "시퀀스 최단 · 200°C 이하", dict(target_nm=10, max_temp=200, objective="time")),
    ("C05", "Ar 20 sccm 필수", dict(target_nm=10, min_flow=20, max_flow=20, objective="gpc")),
    ("C06", "Purge 10초 이하", dict(target_nm=10, max_purge=10, objective="time")),
    ("C07", "150°C 이하", dict(target_nm=10, max_temp=150, objective="time")),
    ("C08", "Purge 상·하한 충돌", dict(target_nm=10, min_purge=20, max_purge=10, objective="time")),
]


def independent_reference(request: dict) -> dict:
    """Acceptance oracle from raw CSV. Does not call optimize_recipe or quality_gate.

    For the eight fixed regression scenarios, independently enumerate every
    observed DOE row and compute candidate ranking. NOT a new experimental test.
    """
    d=load_data()
    groups={}
    for _,r in d.iterrows():
        key=(int(r.temperature_C),int(r.flow_sccm),int(r.pulse_ms),int(r.purge_s))
        groups.setdefault(key,[]).append(float(r.gpc_A_per_cycle))
    if (request.get('min_temp',175)>request.get('max_temp',275) or
        request.get('min_flow',10)>request.get('max_flow',20) or
        request.get('min_purge',10)>request.get('max_purge',20) or
        request.get('min_pulse',20)>request.get('max_pulse',40)):
        return {'n_feasible':0,'best':None}
    candidates=[]
    for (temp,flow,pulse,purge), values in groups.items():
        if not (request.get('min_temp',175)<=temp<=request.get('max_temp',275) and
                request.get('min_flow',10)<=flow<=request.get('max_flow',20) and
                request.get('min_purge',10)<=purge<=request.get('max_purge',20) and
                request.get('min_pulse',20)<=pulse<=request.get('max_pulse',40)):
            continue
        gpc=sum(values)/len(values)
        cycles=math.ceil(request.get('target_nm',10)*10/gpc)
        seconds=cycles*(2*pulse/1000+2*purge)
        candidates.append({'temperature_C':temp,'flow_sccm':flow,'pulse_ms':pulse,
                           'purge_s':purge,'gpc_mean_A':gpc,'sequence_time_s':seconds})
    if not candidates:return {'n_feasible':0,'best':None}
    objective=request.get('objective','time')
    if objective=='gpc':
        candidates.sort(key=lambda x:(-x['gpc_mean_A'],x['sequence_time_s']))
    elif objective=='balanced':
        # Independent raw-CSV implementation of the documented 65/35 score.
        times=[row['sequence_time_s'] for row in candidates]
        gpcs=[row['gpc_mean_A'] for row in candidates]
        t_min,t_max=min(times),max(times)
        g_min,g_max=min(gpcs),max(gpcs)
        for row in candidates:
            row['balance_score']=(0.65*(row['sequence_time_s']-t_min)/max(1,t_max-t_min)
                                  +0.35*(g_max-row['gpc_mean_A'])/max(.001,g_max-g_min))
        candidates.sort(key=lambda x:(x['balance_score'],x['sequence_time_s']))
    elif objective=='time':
        candidates.sort(key=lambda x:(x['sequence_time_s'],-x['gpc_mean_A']))
    else:
        return {'n_feasible':0,'best':None}
    return {'n_feasible':len(candidates),'best':candidates[0]}


def engineering_casebook() -> list[dict]:
    """Fixed developer-authored cases; pass is checked against independent raw-data oracle."""
    rows=[]
    for case_id,title,req in ENGINEERING_CASES:
        reference=independent_reference(req)
        actual=optimize_recipe(**req)
        baseline=naive_v0(req['target_nm'])
        expected=reference['best']
        if expected is None:
            v1_ok='error' in actual
            v0_ok=False  # naïve v0 still outputs a recipe despite an impossible request
            reason='실측 후보 없음 또는 입력 충돌: 추천 거부가 정답'
        else:
            def matches(row,exp):
                return all(math.isclose(float(row[k]),float(exp[k]),abs_tol=1e-8)
                           for k in ('temperature_C','flow_sccm','pulse_ms','purge_s'))
            v1_ok=('error' not in actual and
                   actual['n_feasible']==reference['n_feasible'] and matches(actual['best'],expected))
            v0_ok=matches(baseline,expected)
            if not v0_ok:
                reason='v0는 요구 조건 또는 독립 참조의 목적별 최적 후보와 불일치'
            else:reason='v0/v1 모두 독립 참조 후보와 일치 (막 특성 승인 아님)'
        rows.append({'case_id':case_id,'scenario':title,'request':req,
                     'feasible_candidates':reference['n_feasible'],
                     'v0_pass':bool(v0_ok),'v1_pass':bool(v1_ok),
                     'v1_action':'후보 검토' if expected is not None and 'error' not in actual else '추천 거부',
                     'diagnosis':reason})
    return rows

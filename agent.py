"""ALD-OPTIX tool orchestration: auditable deterministic baseline + optional LLM.

Production safety invariant: LLM-generated tool arguments cannot relax the
server-parsed request. Published experiment data never controls equipment.
"""
from __future__ import annotations
import json
import math
from core import (search_evidence, optimize_recipe, cross_validate, naive_v0,
                  constraint_check, build_report, parse_request, request_scope_error,
                  DOI, nested_cross_validate, quality_gate, scenario_suite, engineering_casebook,
                  validate_structured_request)

DETERMINISTIC_FOOTER = ('\n\n**실행 모드:** LLM이 아닌 규칙 기반 도구 오케스트레이션. '
                        '입력 제약은 서버에서 잠금 처리했습니다.')
UNVERIFIED_LLM_NOTICE = ('\n\n---\n**LLM 생성 해석 초안 (검증되지 않아 제외)**\n\n'
                         'LLM이 생성한 자유 서술은 수치·품질 주장 검증을 거치지 않았으므로 '
                         '최종 보고서에서 표시하지 않았습니다.')

REQUEST_FIELDS = ("target_nm", "min_temp", "max_temp", "min_flow", "max_flow",
                  "min_pulse", "max_pulse", "min_purge", "max_purge", "objective")


def _finite_json_float(token: str) -> float:
    """Reject JSON exponent overflows before unsafe values enter a tool trace.

    json.loads(parse_constant=...) alone does not reject a valid JSON number
    such as 1e999, which otherwise decodes to non-finite Python float.
    """
    value = float(token)
    if not math.isfinite(value):
        raise ValueError('Non-finite JSON numeric value')
    return value

TOOLS = [
    {"type":"function","function":{"name":"search_evidence",
        "description":"Read five curated, source-linked Al2O3 study observations, not external vector RAG.",
        "parameters":{"type":"object","properties":{"query":{"type":"string"}},
                      "required":["query"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"find_recipes",
        "description":"Query only the 16 measured Al2O3 recipes. Server ALWAYS enforces the original user's constraints, regardless of function args.",
        "parameters":{"type":"object","properties":{
            "target_nm":{"type":"number"},"min_temp":{"type":"number"},"max_temp":{"type":"number"},
            "min_flow":{"type":"number"},"max_flow":{"type":"number"},
            "min_pulse":{"type":"number"},"max_pulse":{"type":"number"},
            "min_purge":{"type":"number"},"max_purge":{"type":"number"},
            "objective":{"type":"string","enum":["time","gpc","balanced"]}},
            "required":[],"additionalProperties":False}}},
    {"type":"function","function":{"name":"evaluate_models",
        "description":"Retrieve exploratory and nested group CV diagnostics; no external validation.",
        "parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"audit_casebook",
        "description":"Compare 8 fixed requests against an independent raw-data oracle, not field yield.",
        "parameters":{"type":"object","properties":{},"additionalProperties":False}}},
]


def validated_request(user_request: str | dict) -> tuple[dict | None, str | None]:
    """Identical strict server preflight for text and structured workflows."""
    if isinstance(user_request, dict):
        parsed=validate_structured_request(user_request)
        if parsed.get('warning'):
            return None,str(parsed['warning'])
        return {k:parsed[k] for k in REQUEST_FIELDS},None
    if not isinstance(user_request,str):
        return None,'요청은 문장 또는 구조화된 조건 객체여야 합니다.'
    error = request_scope_error(user_request)
    if error:return None,error
    parsed=parse_request(user_request)
    if parsed.get("warning"):return None,str(parsed['warning'])
    return {k:parsed[k] for k in REQUEST_FIELDS},None


def dispatch_tool(name: str, args: dict, *, locked_request: dict | None = None) -> dict | list:
    """Tool whitelist, argument validation, immutable user constraints on LLM path."""
    if not isinstance(args,dict):return {"error":"도구 인자는 객체여야 합니다."}
    if name not in {tool['function']['name'] for tool in TOOLS}:
        return {"error":f"허용되지 않는 도구: {name}"}
    properties=next(t['function']['parameters']['properties'] for t in TOOLS if t['function']['name']==name)
    extra=set(args)-set(properties)
    if extra:return {"error":f"허용하지 않는 도구 인자: {sorted(extra)}"}
    if name=='search_evidence':
        if not isinstance(args.get('query'),str) or not args['query'].strip():return {"error":"query는 비어 있지 않은 문자열이어야 합니다."}
        return search_evidence(args['query'])
    if name=='evaluate_models':return {"exploratory":cross_validate()[0],"nested_selection":nested_cross_validate()[0]}
    if name=='audit_casebook':return engineering_casebook()
    if name=='find_recipes':
        if locked_request is not None:
            # One differing field causes explicit rejection rather than silent override.
            for key,value in args.items():
                expected=locked_request.get(key)
                valid=(not isinstance(value,bool) and isinstance(value,(int,float)) and
                       math.isfinite(value) and math.isclose(value,expected,abs_tol=1e-9)) if key!='objective' else value==expected
                if not valid:
                    return {"error":f"LLM 도구 인자 {key}가 사용자 원문에서 확정한 값과 다릅니다. 요청 제약 완화 거부.",
                            "original_request":locked_request}
            params=dict(locked_request)
        else:
            params=dict(target_nm=10,min_temp=175,max_temp=275,min_flow=10,max_flow=20,
                        min_pulse=20,max_pulse=40,min_purge=10,max_purge=20,objective='time')
            params.update(args)
        result=optimize_recipe(**params)
        if 'error' in result:return result
        best=result['best']
        baseline=naive_v0(params['target_nm'])
        violations=constraint_check(baseline,**{k:params[k] for k in REQUEST_FIELDS if k not in ('target_nm','objective')})
        gate=quality_gate(params,best)
        if gate['status'] != 'REVIEW_REQUIRED':
            return {'error':'추천 결과의 독립 품질 검증에 실패하여 보고서를 발행하지 않았습니다.',
                    'quality_gate':gate}
        return {"best":best,"n_feasible":result['n_feasible'],"baseline_v0":baseline,
                "v0_constraint_issues":violations,"quality_gate":gate,"locked_request":params,
                "source":DOI,
                "limitations":"Only observed DOE conditions, no film quality certification or real equipment-time data"}
    return {"error":"Unexpected tool error"}


def _trusted_report(tool_result: dict, params: dict) -> str:
    """Recompute all outputs from locked request; never publish unverified tool JSON."""
    if not isinstance(tool_result,dict):
        raise ValueError('recipe tool result is not a dictionary')
    requested=validate_structured_request(params)
    if 'warning' in requested or tool_result.get('locked_request') != requested:
        raise ValueError('tool request differs from locked user request')
    best=tool_result.get('best')
    gate=quality_gate(requested,best)
    if gate['status'] != 'REVIEW_REQUIRED':
        raise ValueError('recipe values failed independent quality gate')
    # The baseline and issues are recomputed instead of accepting editable tool output.
    baseline=naive_v0(requested['target_nm'])
    issues=constraint_check(baseline, **{key:requested[key] for key in REQUEST_FIELDS
                                       if key not in ('target_nm','objective')})
    return build_report(best,baseline,issues,requested['objective'])


def deterministic_demo(user_request: str | dict) -> tuple[str,list[dict]]:
    """NON-LLM deterministic execution; uses the exact same locked request as LLM."""
    params,error=validated_request(user_request)
    trace=[{"tool":"request_validation","input":user_request,
            "result":{"error":error} if error else {"parsed":params,"locked":True}}]
    trace[0]["result"].update(execution_origin="RULE_BASED", api_responses_received=0)
    if error:return ("⚠️ 검증 중단: "+error+"\n\n지원하지 않는 조건을 기본값으로 바꿔 추천하지 않았습니다."),trace
    source_query = ('Al2O3 GPC purge temperature DOE'
                    if isinstance(user_request,dict) else user_request)
    for name,args in [('search_evidence',{'query':source_query}),('find_recipes',{}),
                      ('evaluate_models',{}),('audit_casebook',{})]:
        result=dispatch_tool(name,args,locked_request=params)
        trace.append({'tool':name,'input':args,'result':result})
        if name=='find_recipes':recipes=result
        if name=='search_evidence' and not result:
            return '검증 중단: 이 요청과 관련된 근거를 확인하지 못했습니다.',trace
        if isinstance(result,dict) and 'error' in result:
            return '검증 중단: 도구 오류로 보고서를 생성하지 않았습니다.',trace
    if 'error' in recipes:
        return "결과: "+recipes['error']+"\n\n이 모드는 **LLM이 아닌 규칙 기반 도구 실행**입니다.",trace
    if recipes['quality_gate']['status']!='REVIEW_REQUIRED':
        return "품질 게이트에서 승인되지 않아 추천을 중단했습니다.",trace
    try:
        text=_trusted_report(recipes,params)
    except (ValueError, KeyError, TypeError):
        trace.append({'tool':'final_report_integrity','input':{},
                      'result':{'error':'trusted report integrity check failed'}})
        return '검증 중단: 최종 보고서 무결성 검사에 실패했습니다.',trace
    text += DETERMINISTIC_FOOTER
    return text,trace


def run_llm_agent(user_request: str | dict, api_key: str, model: str = "gpt-4.1-mini", *, client=None) -> tuple[str,list[dict]]:
    """Optional OpenAI function-calling; client injection enables OFFLINE protocol tests.

    Live network use remains UNVERIFIED until a real API key and deployment are tested.
    Model's free-text explanation is separated from validated engineering calculations.
    """
    params,error=validated_request(user_request)
    trace=[{"tool":"request_validation","input":user_request,
            "result":{"error":error} if error else {"parsed":params,"locked":True}}]
    trace[0]["result"].update(
        execution_origin="INJECTED_CLIENT" if client is not None else "OPENAI_SDK_CLIENT",
        api_responses_received=0,
    )
    if error:return "⚠️ 검증 중단: "+error,trace
    if client is None:
        if not api_key:return 'LLM API 키가 없어 실제 도구 호출을 실행할 수 없습니다.',trace
        from openai import OpenAI
        client=OpenAI(api_key=api_key,timeout=30,max_retries=1)
    safe_user_text=(json.dumps(user_request,ensure_ascii=False,sort_keys=True)
                    if isinstance(user_request,dict) else user_request)
    messages=[{"role":"system","content":(
        "You are an academic ALD/Al2O3 decision-support agent, not equipment control. "
        "Call search_evidence and find_recipes to answer this request; optional evaluate_models. "
        "The server locks ALL user constraints, and will reject a tool argument that relaxes them. "
        "DO NOT invent experimental conditions, time savings or quality metrics. "
        "Measured GPC differs from estimated cycle/time. No manufacturing certification. "
        "Write concise Korean, classify observation, calculation and unknowns. "
        "Final free-text is unverified commentary; engineering numbers come from server tool results."
    )},{"role":"user","content":safe_user_text}]
    verified=None
    evidence_seen=False
    tool_errors=[]
    seen_tool_call_ids=set()
    total_tool_calls=0
    for step in range(6):
        try:
            response=client.chat.completions.create(model=model,messages=messages,tools=TOOLS,
                  tool_choice='required' if step==0 else 'auto',temperature=0.1)
            msg=response.choices[0].message
            if not hasattr(msg, "tool_calls"):
                raise ValueError("missing tool_calls field")
            # Counts successful SDK/client round trips, not independent provider evidence.
            trace[0]["result"]["api_responses_received"] += 1
        except Exception as exc:
            # Do not expose API responses (which may include credentials or user data).
            trace.append({'tool':'llm_transport', 'input':{'step':step},
                          'result':{'error':type(exc).__name__}})
            return 'LLM 연결 또는 응답 형식 오류로 검증을 중단했습니다. 계산 결과를 발행하지 않았습니다.',trace
        calls=getattr(msg,'tool_calls',None) or []
        if not isinstance(calls,(list,tuple)):
            trace.append({'tool':'llm_response_format','input':{'step':step},
                          'result':{'error':'invalid_tool_call_collection'}})
            return '검증 중단: LLM 도구 호출 목록 형식이 올바르지 않습니다.',trace
        # Avoid unbounded memory, tool execution and API token/cost amplification.
        if len(calls)>8 or total_tool_calls+len(calls)>16:
            trace.append({'tool':'llm_tool_budget','input':{'step':step},
                          'result':{'error':'tool_call_limit_exceeded'}})
            return '검증 중단: 한 번의 실행에 허용된 도구 호출량을 초과했습니다.',trace
        if not calls:
            if tool_errors:
                return '검증 중단: 도구 호출 중 검증 실패가 있었습니다. 요청을 다시 확인하세요.',trace
            if not evidence_seen or verified is None:
                return '검증 중단: 출처 검색과 제약 잠금 레시피 조회가 모두 성공하지 않았습니다.',trace
            if verified['quality_gate']['status']!='REVIEW_REQUIRED':
                return '검증 중단: 품질 게이트를 통과하지 못했습니다.',trace
            try:
                trusted=_trusted_report(verified,params)
            except (ValueError, KeyError, TypeError):
                trace.append({'tool':'final_report_integrity','input':{},
                              'result':{'error':'trusted report integrity check failed'}})
                return '검증 중단: LLM 도구 결과의 최종 무결성 검사가 실패했습니다.',trace
            raw_content=getattr(msg,'content',None)
            free=raw_content.strip() if isinstance(raw_content,str) else ''
            if free:
                # Raw model prose can contain unsupported quality/performance claims.
                # A verified tool report is the only report displayed; prose is not
                # mixed into engineering evidence or used as a process recommendation.
                trusted += UNVERIFIED_LLM_NOTICE
            return trusted,trace
        try:
            serialized = msg.model_dump(exclude_none=True)
            if not isinstance(serialized, dict) or serialized.get("role") != "assistant":
                raise ValueError("invalid assistant message serialization")
        except (AttributeError, TypeError, ValueError) as exc:
            trace.append({'tool':'llm_response_format','input':{'step':step},
                          'result':{'error':type(exc).__name__}})
            return '검증 중단: LLM 응답을 안전하게 직렬화할 수 없습니다.',trace
        messages.append(serialized)
        for call in calls:
            name = None
            try:
                name=call.function.name
                call_id=call.id
                if not isinstance(call_id,str) or not call_id.strip() or not isinstance(name,str):
                    raise ValueError('invalid function call identity')
                if call_id in seen_tool_call_ids:
                    trace.append({'tool':'llm_tool_call_id','input':{'step':step},
                                  'result':{'error':'duplicate_tool_call_id'}})
                    return '검증 중단: 중복된 LLM 도구 호출 식별자입니다.',trace
                seen_tool_call_ids.add(call_id)
                total_tool_calls+=1
                # Python's json.loads otherwise accepts non-standard NaN and
                # Infinity tokens. Such values poison strict JSON exports.
                args=json.loads(call.function.arguments,
                                parse_float=_finite_json_float,
                                parse_constant=lambda token: (_ for _ in ()).throw(
                                    ValueError('Non-finite JSON token')))
                result=dispatch_tool(name,args,locked_request=params)
            except (ValueError,TypeError,KeyError,OverflowError,AttributeError) as exc:
                args={};result={'error':f'잘못된 도구 인자: {type(exc).__name__}'}
                # A malformed call cannot be safely acknowledged to the LLM.
                if name is None or not isinstance(name,str) or not hasattr(call,'id') or not isinstance(call.id,str):
                    trace.append({'tool':'invalid_tool_call', 'input':{}, 'result':result})
                    return '검증 중단: 잘못된 LLM 도구 호출 형식입니다.',trace
            trace.append({'tool':name,'input':args,'result':result})
            if isinstance(result,dict) and 'error' in result:
                tool_errors.append({'tool':name,'error':result['error']})
            if name=='search_evidence' and isinstance(result,list) and result:evidence_seen=True
            if name=='find_recipes' and isinstance(result,dict) and 'error' not in result:
                verified=result
            messages.append({'role':'tool','tool_call_id':call.id,
                             'content':json.dumps(result,ensure_ascii=False,default=float)})
    return '도구 호출 반복 한도에 도달했습니다. 검증된 최종 응답을 생성하지 않았습니다.',trace


# Gemini API — real function calling, separately classified from the legacy OpenAI path.
# Official python-genai SDK, no API key is ever included in this source file.
GEMINI_DEFAULT_MODEL = "gemini-3.5-flash-lite"


def run_gemini_agent(user_request: str | dict, api_key: str,
                     model: str = GEMINI_DEFAULT_MODEL, *, client=None) -> tuple[str, list[dict]]:
    """Opt-in Gemini function calling with server-enforced immutable constraints.

    An injected client is only a MOCK; do not use it as proof of real API use.
    The returned engineering report is *always* recomputed by Python, never
    copied from the LLM response. Trace authenticity needs Google-side logs.
    """
    params, error = validated_request(user_request)
    trace = [{"tool": "request_validation", "input": user_request,
              "result": ({"error": error} if error else {"parsed": params, "locked": True})}]
    trace[0]["result"].update(
        execution_origin="GEMINI_INJECTED_CLIENT" if client is not None else "GEMINI_SDK_CLIENT",
        api_responses_received=0)
    if error:
        return "⚠️ 검증 중단: " + error, trace
    if not api_key and client is None:
        return 'Gemini API 키가 없어 실시간 도구 호출을 실행하지 않았습니다.', trace
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        trace.append({"tool": "llm_transport", "input": {}, "result": {"error": "SDK_NOT_INSTALLED"}})
        return 'Gemini SDK가 설치되지 않았습니다. requirements.txt를 확인해 주세요.', trace
    if client is None:
        # API requests are only created after strict preflight above.
        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=30000))

    declarations = [types.FunctionDeclaration(
        name=tool['function']['name'],
        description=tool['function']['description'],
        parameters_json_schema=tool['function']['parameters'])
        for tool in TOOLS]
    tool_bundle = types.Tool(function_declarations=declarations)
    safe_text = (json.dumps(user_request, ensure_ascii=False, sort_keys=True)
                 if isinstance(user_request, dict) else user_request)
    system_instruction = (
        'You are an academic Al2O3 ALD decision-support agent, not equipment control. '
        'First call search_evidence and find_recipes. You may call evaluate_models or audit_casebook. '
        'The server already locks the user request, so use find_recipes with {} arguments. '
        'Never override user constraints, invent missing measurements, assert film quality, '
        'or claim real equipment throughput. Distinguish observed GPC from modeled cycle/time. '
        'Briefly conclude in Korean only after the evidence and recipe tools succeed. '
        'The final engineering report will be independently generated by Python, not by you.')
    contents = [types.Content(role='user', parts=[types.Part.from_text(text=safe_text)])]
    verified = None
    evidence_seen = False
    total_calls = 0
    tool_errors = []
    for step in range(6):
        try:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction, tools=[tool_bundle],
                temperature=0, max_output_tokens=1024,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
                    mode='ANY' if not (evidence_seen and verified is not None) else 'AUTO')))
            response = client.models.generate_content(model=model, contents=contents, config=config)
            candidate = response.candidates[0]
            model_content = candidate.content
            if model_content is None or not isinstance(model_content.parts, list):
                raise ValueError('invalid_model_response')
            parts = model_content.parts
            trace[0]['result']['api_responses_received'] += 1
        except Exception as exc:
            # Do NOT expose server credentials, provider messages, or raw user text.
            trace.append({'tool': 'llm_transport', 'input': {'step': step},
                          'result': {'error': type(exc).__name__}})
            return 'Gemini 연결 또는 응답 형식 오류로 실행을 중단했습니다. 검증 보고서를 발행하지 않았습니다.', trace

        calls = [p.function_call for p in parts if getattr(p, 'function_call', None) is not None]
        if len(calls) > 8 or total_calls + len(calls) > 16:
            trace.append({'tool': 'llm_tool_budget', 'input': {'step': step},
                          'result': {'error': 'tool_call_limit_exceeded'}})
            return '검증 중단: 도구 호출 허용량을 초과했습니다.', trace
        if not calls:
            if tool_errors or not evidence_seen or verified is None:
                return '검증 중단: 근거 검색과 제약 잠금 레시피 조회가 모두 성공하지 않았습니다.', trace
            try:
                trusted = _trusted_report(verified, params)
            except (ValueError, KeyError, TypeError, OverflowError):
                trace.append({'tool': 'final_report_integrity', 'input': {},
                              'result': {'error': 'trusted_report_mismatch'}})
                return '검증 중단: 최종 보고서 무결성 검사가 실패했습니다.', trace
            if any(isinstance(getattr(p, 'text', None), str) and p.text.strip() for p in parts):
                trusted += UNVERIFIED_LLM_NOTICE
            return trusted, trace

        # Preserve raw model content, including Gemini thought signatures.
        # Never reconstruct this from untrusted user text.
        contents.append(model_content)
        response_parts = []
        for fc in calls:
            total_calls += 1
            name = getattr(fc, 'name', None)
            args = getattr(fc, 'args', None)
            if not isinstance(name, str) or not name:
                trace.append({'tool': 'invalid_tool_call', 'input': {},
                              'result': {'error': 'missing_tool_name'}})
                return '검증 중단: 이름이 없는 도구 호출입니다.', trace
            if not isinstance(args, dict):
                trace.append({'tool': name, 'input': {},
                              'result': {'error': 'invalid_tool_arguments'}})
                return '검증 중단: 잘못된 Gemini 도구 인자입니다.', trace
            # JSON roundtrip rejects non-finite numbers and non-JSON objects.
            try:
                safe_args = json.loads(json.dumps(args, allow_nan=False))
                result = dispatch_tool(name, safe_args, locked_request=params)
            except (ValueError, TypeError, KeyError, OverflowError):
                trace.append({'tool': name, 'input': {},
                              'result': {'error': 'invalid_tool_arguments'}})
                return '검증 중단: 유효하지 않은 도구 인자입니다.', trace
            trace.append({'tool': name, 'input': safe_args, 'result': result})
            if isinstance(result, dict) and 'error' in result:
                tool_errors.append(name)
            if name == 'search_evidence' and isinstance(result, list) and result:
                evidence_seen = True
            if name == 'find_recipes' and isinstance(result, dict) and 'error' not in result:
                verified = result
            # Do not let a failed tool call be hidden by later model output.
            if tool_errors:
                return '검증 중단: Gemini 도구 요청이 허용된 입력 조건을 위반했습니다.', trace
            response_parts.append(types.Part.from_function_response(
                name=name, response={'result': result}))
        contents.append(types.Content(role='tool', parts=response_parts))
    return '호출 반복 한도에 도달해 검증 보고서를 만들지 않았습니다.', trace

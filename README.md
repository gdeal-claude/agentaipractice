# 엄마 주식 비서 (stockmom) + Agent 뼈대 (agentsys)

주식을 처음 접하는 50대 어머니를 위해 만든 **주식 비서**입니다.
어머니가 "삼성전자 요즘 어때?" 라고 물으면, 프로그램이 **실제 주가를 조회하고 뉴스를 찾아 읽은 뒤** 쉬운 말로 설명해 줍니다.
평일 아침 7시에는 보유 종목 브리핑을 이메일로 보내 줍니다.

이 저장소는 두 부분으로 되어 있습니다.

| 부분 | 뭔가요 | 폴더 |
|---|---|---|
| **1부. stockmom** | 어머니가 쓰는 실제 프로그램 | `src/stockmom/` |
| **2부. agentsys** | 그 프로그램이 올라탄 "Agent 뼈대". 다른 비서를 만들 때 재사용 | `src/agentsys/` |

처음이라면 1부만 보시면 됩니다.

---

# 1부. 엄마 주식 비서 사용법 (API 키 없이, 구독/무료 계정만으로)

돈이 따로 나가는 API 키는 쓰지 않습니다. 두 가지만 씁니다.

| 역할 | 어디서 | 누구 계정 |
|---|---|---|
| 어머니가 물어보는 창구 | 어머니 폰의 Claude 앱 (무료 계정) | 어머니 |
| 평일 아침 7시 브리핑 자동 생성 | Claude Code 루틴 (이 저장소) | 자녀 (구독 계정) |

## A. 어머니 폰에 "주식 도우미" 만들기 (5분)

1. 어머니 폰에 Claude 앱을 설치하고 무료 계정으로 로그인합니다.
2. 앱에서 **프로젝트(Projects) > 새 프로젝트** 를 만들고 이름을 "주식 도우미" 로 합니다.
3. 프로젝트의 **지침(Instructions)** 칸에 이 저장소의 `mom/CLAUDE_PROJECT_INSTRUCTIONS.md` 내용을 그대로 붙여 넣습니다.
   맨 아래 `[보유 종목]` 부분만 어머니 실제 종목으로 고칩니다.
4. 그 프로젝트 안에서 대화를 시작하면 됩니다. 예: "삼성전자 요즘 어때?", "내 주식 얼마나 올랐어?", "지금 사도 돼?"

무료 계정은 하루 대화 횟수에 한도가 있습니다. 한도가 차면 몇 시간 뒤에 다시 됩니다. 돈은 나가지 않습니다.

## B. 아침 브리핑 자동 생성 (자녀 본인 구독 계정에서 한 번만 설정)

자녀의 Claude Code 루틴이 평일 아침 7시(한국 시간)에 이 저장소를 열고 리포트를 만들어 `reports/오늘날짜.md` 로 저장하는 방식입니다.
실행이 끝나면 자녀 계정 이메일로 알림이 오고, 리포트 전문이 그 안에 들어 있습니다. 어머니께 그대로 전달(캡처, 카톡)하면 됩니다.

- 설정 방법: 본인 계정으로 claude.ai/code 에 로그인 > Routines > 새 루틴. `mom/ROUTINE_PROMPT.md` 의 내용을 그대로 붙여 넣으면 됩니다.
- 루틴 켜고 끄기, 시간 바꾸기: 같은 Routines 메뉴.
- 어머니 종목 바꾸기: `data/portfolio.json` 을 고치거나, Claude Code 세션에서 "삼성전자 10주 7만원에 산 걸로 등록해 줘" 라고 말하면 됩니다.
- 사용량은 자녀 구독 한도 안에서만 쓰입니다. 하루 한 번이면 부담이 작습니다.

## C. 더 나은 데이터가 필요하면 (선택)

루틴 환경은 금융 사이트 직접 접속이 막혀 있어 주가를 웹 검색으로 찾습니다. 정확한 시세를 원하면
claude.ai/code 의 환경(Environment) 설정에서 네트워크 정책을 "허용 목록" 으로 바꾸고 `finance.yahoo.com`, `query1.finance.yahoo.com`, `query2.finance.yahoo.com` 을 추가하세요.
그러면 `python -m stockmom status` 가 실제 시세와 손익을 계산해 줍니다.

## 부록. API 키 방식 (원하면)

API 키를 발급받아 쓰면 컴퓨터에서 `stockmom chat` 으로 대화하고 `stockmom morning --email` 로 이메일 발송까지 됩니다. 사용한 만큼 과금됩니다.
`pip install -e .` 후 `ANTHROPIC_API_KEY` 를 환경변수로 넣고 실행하세요. 자세한 코드는 `src/stockmom/`.

---

# 2부. Agent 뼈대 (agentsys)

stockmom 은 아래 뼈대 위에 "주가 조회", "종목 저장" 같은 도구만 얹은 것입니다. 다른 비서(일정 관리, 고객 상담 등)를 만들고 싶을 때 이 부분을 재사용합니다.
Claude API 위에 **도구를 쓰는 에이전트**와 **여러 에이전트가 협업하는 팀**을 처음부터 만들어 본 프로젝트입니다.
프레임워크 없이 순수 Python + 공식 `anthropic` SDK 만 사용해서, 에이전트가 안에서 실제로 어떻게 도는지 그대로 보입니다.

## 1. Agent 가 뭔지 3분 만에 이해하기

웹앱은 "요청이 오면 핸들러가 처리하고 응답을 돌려준다"는 구조입니다.
Agent 는 그 위에 **모델이 스스로 함수를 골라 부르는 반복문** 하나가 얹힌 것입니다.

```
사용자 질문
   │
   ▼
┌─────────────────────────────────────────────┐
│  while True:                                 │
│      응답 = Claude 호출(대화 히스토리, 도구 목록) │
│      if 응답.stop_reason == "tool_use":       │  ← 모델이 "이 함수 실행해줘" 라고 요청
│          결과 = 내 파이썬 함수 실행(인자)         │  ← 실행은 내 코드가 한다
│          히스토리에 결과 추가; continue          │
│      else:                                   │
│          return 응답.text                     │  ← 모델이 더 부를 게 없으면 끝
└─────────────────────────────────────────────┘
```

이 반복문이 `src/agentsys/agent.py` 의 `Agent.run()` 입니다. 이 프로젝트의 나머지는 전부 이 루프에 붙는 부속품입니다.

| 용어 | 뜻 | 이 프로젝트에서 |
|---|---|---|
| Tool (도구) | 모델이 호출할 수 있는 함수. 이름 + 설명 + 입력 스키마(JSON Schema) 로 모델에게 알려준다 | `@tool` 데코레이터가 파이썬 함수에서 자동 생성 (`tools.py`) |
| Agent loop | 위 반복문 | `Agent.run()` (`agent.py`) |
| Memory | 세션이 끝나도 남는 정보 | JSON 파일 하나 (`memory.py`) |
| Orchestrator | 다른 에이전트에게 일을 나눠 주는 상위 에이전트 | `delegate` 도구 하나로 구현 (`orchestrator.py`) |
| Worker | 오케스트레이터가 부르는 전문 에이전트 | 그냥 `Agent` 인스턴스. 설명(`description`)만 다름 |

핵심 통찰 하나: **하위 에이전트도 그냥 도구입니다.** `delegate(worker="coder", task="...")` 라는 함수를 만들어 주면, 그 함수 안에서 다른 `Agent.run()` 을 부르는 것뿐입니다.

## 2. 실행해 보기

```bash
# 1) 가상환경 + 설치
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
source .venv/bin/activate

# 2) API 키 (https://console.anthropic.com 에서 발급)
export ANTHROPIC_API_KEY=sk-ant-...

# 3) 단일 에이전트 REPL
agentsys
> 서울은 지금 몇 시야? 그리고 1234 * 5678 은?
> 내 이름은 지수야. 기억해 둬.        # -> remember 도구 호출
> workspace 에 hello.py 만들어 줘     # -> write_file 은 승인 게이트를 거친다

# 4) 멀티 에이전트 팀 (리서처 / 코더 / 리뷰어)
agentsys --team
> FizzBuzz 를 파이썬으로 구현하고 리뷰까지 받아서 fizzbuzz.py 로 저장해 줘

# 옵션
agentsys --web              # web_search 서버 도구 추가
agentsys --show-thinking    # 모델의 요약된 사고 과정 표시
agentsys --effort medium    # 사고 깊이/토큰 사용량 조절 (low~max)
```

API 키 없이 구조만 확인하려면 테스트를 돌리세요. 테스트는 가짜 클라이언트를 써서 네트워크 없이 전체 루프를 검증합니다.

```bash
pytest -q
```

## 3. 코드로 직접 써 보기

### 도구 하나 만들어서 에이전트에 붙이기

```python
from agentsys import Agent, tool

@tool
def get_weather(city: str, unit: str = "celsius") -> str:
    """도시의 현재 날씨를 돌려준다.

    사용자가 날씨, 기온, 우산 필요 여부 등을 물을 때 호출한다.

    Args:
        city: 도시 이름. 예: "Seoul"
        unit: "celsius" 또는 "fahrenheit"
    """
    return f"{city}: 23도, 맑음"      # 실제로는 날씨 API 를 부르면 된다

agent = Agent(system="당신은 친절한 비서입니다.", tools=[get_weather])
result = agent.run("서울 날씨 어때?")
print(result.text)
print(result.usage)          # 토큰 사용량
print(result.tool_calls)     # 모델이 호출한 도구 목록
```

docstring 의 첫 문단은 도구 설명이 되고, `Args:` 섹션은 각 파라미터 설명이 됩니다.
**설명에 "언제 호출하는지"를 적는 것**이 모델이 도구를 잘 고르게 하는 가장 큰 요인입니다.

### 팀 만들기

```python
from agentsys import Agent, Orchestrator, Workspace, AgentConfig

ws = Workspace("workspace")
coder = Agent(
    name="coder",
    description="코드를 작성해 파일로 저장한다.",
    system="당신은 시니어 개발자입니다. 결과는 write_file 로 저장하세요.",
    tools=ws.tools(approve_writes=False),
    config=AgentConfig(effort="medium"),
)
reviewer = Agent(
    name="reviewer",
    description="파일을 읽고 문제점을 지적한다.",
    system="당신은 꼼꼼한 리뷰어입니다.",
    tools=ws.tools(approve_writes=False),
)
team = Orchestrator([coder, reviewer])
print(team.run("계산기 모듈을 만들고 리뷰받아서 고쳐 줘").text)
```

`examples/` 폴더에 같은 내용의 실행 가능한 스크립트가 있습니다.

## 4. 프로젝트 구조

```
src/agentsys/
├── agent.py           Agent, AgentConfig, RunResult  - 핵심 루프
├── tools.py           @tool, Tool, ToolRegistry      - 함수 -> 도구 변환, 입력 검증
├── orchestrator.py    Orchestrator                   - 워커에게 위임하는 delegate 도구
├── memory.py          FileMemory                     - remember / recall / forget
├── builtin_tools.py   calculator, current_time, Workspace(파일 읽기/쓰기)
├── events.py          AgentEvent, ConsolePrinter     - 실행 중 관찰용 이벤트
└── cli.py             agentsys 명령 (REPL)
examples/              바로 실행하는 예제 2개
tests/                 가짜 클라이언트로 도는 단위 테스트
```

## 5. 설계 결정과 이유

- **모델**: 기본 `claude-opus-5`. 워커는 같은 모델에 `effort="medium"` 으로 비용을 낮춥니다. 바꾸려면 `AgentConfig(model=...)`.
- **적응형 사고(adaptive thinking)**: 모델이 필요할 때만 생각하도록 `thinking={"type": "adaptive"}` 를 항상 켭니다. 깊이는 `effort` 로 조절합니다.
- **스트리밍**: 항상 `client.beta.messages.stream()` 을 써서 긴 출력에서도 타임아웃에 걸리지 않습니다. 도구에는 `eager_input_streaming` 을 켜고, 대신 잘린 JSON 을 막기 위해 pydantic 으로 입력을 검증합니다.
- **프롬프트 캐싱**: 시스템 프롬프트에 캐시 브레이크포인트를 두고, 대화 꼬리는 최상위 `cache_control` 로 자동 캐시합니다. 도구 목록 순서를 고정해 캐시가 깨지지 않게 합니다.
- **거부 폴백**: 안전 정책으로 요청이 거부되면 서버가 대체 모델로 같은 요청을 다시 실행하도록 `fallbacks="default"` 를 기본으로 켭니다. 끄려면 `AgentConfig(refusal_fallbacks=False)`.
- **stop_reason 전부 처리**: `tool_use`(도구 실행), `pause_turn`(서버 도구 계속), `max_tokens`(한 번 이어쓰기), `refusal`(RunResult.refused), `model_context_window_exceeded`(예외).
- **병렬 도구 호출**: 모델이 한 번에 여러 도구를 부르면 스레드로 동시에 실행하고, 결과는 반드시 **하나의 user 메시지**에 모아 돌려줍니다. 나누어 보내면 모델이 병렬 호출을 그만두게 됩니다.
- **승인 게이트**: `@tool(requires_approval=True)` 인 도구는 실행 전에 `approve` 콜백을 거칩니다. 거부하면 모델에게 `is_error` 결과로 알려 다른 방법을 찾게 합니다.
- **테스트 가능성**: `Agent(client=...)` 로 클라이언트를 주입할 수 있어 API 키 없이 루프 전체를 검증합니다 (`tests/conftest.py` 의 `FakeClient`).

## 6. 다음에 해 볼 것

1. `builtin_tools.py` 에 자기만의 도구 추가 (DB 조회, 사내 API 호출 등)
2. `Orchestrator` 에 워커 추가 후 `description` 을 바꿔 가며 위임 품질 비교
3. 긴 대화를 위해 서버 측 압축(`context_management`) 옵션 추가
4. `on_event` 를 이용해 웹 UI 로 실행 과정을 스트리밍

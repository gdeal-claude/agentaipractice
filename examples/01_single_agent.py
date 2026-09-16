"""단일 에이전트 예제: 도구 하나 정의해서 붙이기.

실행: ANTHROPIC_API_KEY=... python examples/01_single_agent.py
"""

from agentsys import Agent, ConsolePrinter, calculator, current_time, tool


@tool
def get_weather(city: str, unit: str = "celsius") -> str:
    """도시의 현재 날씨를 돌려준다.

    사용자가 날씨, 기온, 옷차림, 우산 필요 여부를 물을 때 호출한다.

    Args:
        city: 도시 이름. 예: "Seoul", "Tokyo"
        unit: "celsius" 또는 "fahrenheit"
    """
    # 실제 서비스라면 여기서 날씨 API 를 부른다.
    temp = 23 if unit == "celsius" else 73
    return f"{city}: {temp}도, 맑음, 습도 40%"


agent = Agent(
    system="당신은 친절한 비서입니다. 정확한 숫자는 calculator 로 계산하세요. 한국어로 답하세요.",
    tools=[get_weather, calculator, current_time],
    on_event=ConsolePrinter(),
)

result = agent.run("서울이랑 도쿄 날씨 알려주고, 두 도시 기온 평균도 계산해 줘.")
print("\n---")
print("도구 호출:", [c.name for c in result.tool_calls])
print("토큰:", result.usage.as_dict())

# 같은 인스턴스를 다시 부르면 이전 대화를 기억한다.
result2 = agent.run("방금 알려준 것 중 더 따뜻한 도시는 어디였지?")

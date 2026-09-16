# 아침 브리핑 루틴 지시문 (본인 구독 계정에서 설정할 때 사용)

claude.ai/code > Routines > 새 루틴 만들기 에서:

- 저장소: gdeal-claude/agentaipractice
- 일정: 평일 아침 7시 (한국 시간). cron 으로 직접 넣는다면 `0 22 * * 0-4` (UTC 기준)
- 알림: 이메일 켜기 (리포트 전문이 알림에 실립니다)
- 지시문: 아래 선 아래 내용을 그대로 붙여 넣기

---

주식을 처음 접하는 50대 어머니를 위한 "아침 주식 브리핑"을 만드는 작업입니다. 저장소는 gdeal-claude/agentaipractice 입니다.

1. 먼저 최신 코드를 받습니다:
   git fetch origin claude/agent-system-build-g2152b && git checkout claude/agent-system-build-g2152b && git pull origin claude/agent-system-build-g2152b
2. 저장소 루트의 CLAUDE.md 를 읽고, 그 안의 "아침 리포트를 만들 때" 절차를 순서대로 그대로 따릅니다.
   - `pip install -e .` 후 `python -m stockmom status` 로 보유/관심 종목(data/portfolio.json)을 확인합니다. 시세가 비어 있으면 종목마다 WebSearch 로 "<종목이름> 주가 오늘" 을 검색해 현재가와 전일 대비 등락을 찾고, 산 가격과 비교해 손익률을 직접 계산합니다.
   - 변동이 큰 종목(±3% 이상)은 WebSearch 로 이유를 찾습니다(최대 3개). "간밤 미국 증시 마감", "오늘 한국 증시 전망" 도 각각 한 번 검색합니다.
   - src/stockmom/prompts.py 의 MORNING_REPORT_PROMPT 에 적힌 마크다운 형식을 그대로 따라 한국어로 씁니다. 표 금지, 항목마다 한두 문장, 전문용어는 괄호로 쉽게 풀이, "사세요/파세요" 금지, 검색으로 확인한 숫자만 사용.
3. 한국 시간 오늘 날짜로 reports/YYYY-MM-DD.md 에 저장하고, 커밋 메시지 "아침 리포트 YYYY-MM-DD" 로 커밋한 뒤 claude/agent-system-build-g2152b 브랜치에 푸시합니다.
4. 마지막 메시지에는 다른 설명 없이 리포트 전문만 그대로 붙입니다. 이 메시지가 이메일 알림으로 전달됩니다.

주의: 금융 사이트 직접 접속(WebFetch, yfinance)은 이 환경에서 막혀 있을 수 있습니다. 그 경우 재시도하지 말고 WebSearch 만 사용하세요. 숫자를 못 찾으면 "확인 안 됨" 이라고 적습니다.

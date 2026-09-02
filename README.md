# UST Auction — 다크 대시보드

현재 상태: **단계 A 기준 버전 확정 · 로컬 Git 저장 · 사용자 검토 대기**. QRA·발행통계 요구 분석(단계 B)은 아직 시작하지 않았습니다.

현재 다크 화면과 기존 미커밋 변경을 함께 검사해 커밋 메시지 `feat: establish UST auction dashboard baseline`, 로컬 태그 `ui-baseline-v1`로 보존했습니다. 원격 저장소에는 push하지 않았습니다. 직접 확인·복원 절차는 `RUNBOOK.md`, 검사 기록은 `TEST_LOG.md`, 요구사항은 `REQUIREMENTS.md`에 있습니다. `ARCHITECTURE.md`와 `DATA_DICTIONARY.md`는 향후 단계용 관리 문서이며 최종 기술이나 DB 설계를 확정한 문서가 아닙니다.

기존 다크 HTML 목업의 배치와 색상을 현재 React 화면에 반영했습니다. 실행 기술을 다른 것으로 교체한 것은 아닙니다. 실행 기준은 이 폴더의 `app/page.tsx`와 `app/AuctionDashboard.tsx`입니다.

## 먼저 알아둘 점

- 이전 `.codex/.chatgpt-projects/.../ust-auction-dashboard.html`은 별도 파일입니다. 그 파일을 새로고침해도 현재 프로젝트의 수정은 보이지 않습니다.
- 이 프로젝트는 **로컬 주소 `http://localhost:3000/`**에서 확인합니다. 서버가 실행 중이어야 열립니다.
- 화면의 응찰률은 백분율만 표시합니다. 예: API의 원본 배수 2.48 → 화면의 248.0%. 배수와 백분율을 별도 지표로 중복 표시하지 않습니다.
- TreasuryDirect에 요청하는 기존 코드와 대체 표본은 유지했습니다. 요청이 실패하거나 결과가 없으면 `표본 자료`를 표시합니다. 이 표본은 실시간·최신·정확성이 검증된 자료라는 뜻이 아닙니다. 예정 일정도 표본 기준 시각 이후의 목록일 뿐 현재 이후 실제 계획이 아닐 수 있습니다.
- Allotted at High, When-Issued, Tail, Market Context는 현재 연결되지 않았으므로 N/A입니다. 목업의 예시 숫자를 실제 시세처럼 표시하지 않습니다.
- `API 필드` / `데이터 구조`는 기존 참고 설계입니다. 실제 API 검증이나 DB 구현 완료를 뜻하지 않습니다.
- CUSIP는 화면에서 제거했으며 내부 식별 데이터는 보존했습니다. Price는 상단 KPI에서 제거하고 하단 결과표의 `낙찰가격`은 유지했습니다.
- 기본 시각은 한국 KST입니다. 상단 버튼으로 미국 동부 ET로 바꿀 수 있습니다. 모든 날짜는 YYYY-MM-DD이며, 시각이 없는 날짜는 임의 변환하지 않고 `원문 ET`를 표시합니다. 새로고침하면 기본 KST로 돌아갑니다.

## 현재 컴퓨터에서 실행하기

PowerShell(명령어 입력 창)에서 아래를 실행합니다. 이미 설치된 도구를 사용하며 새 설치는 필요 없습니다.

```powershell
Set-Location 'C:\Users\KOSCOM\Documents\ChatGPT\US_Treasury_Auction'
$env:PATH = 'C:\Users\KOSCOM\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;' + $env:PATH
pnpm dev
```

`Local: http://localhost:3000/` 안내가 나오면 해당 주소를 브라우저에서 엽니다. 초기 실행에 시간이 걸릴 수 있습니다. 포트가 사용 중이면 명령 창에 나온 실제 주소를 이용합니다. 종료는 해당 명령 창에서 `Ctrl+C`입니다.

위 경로는 **현재 컴퓨터 기준**이며 `$env:PATH` 변경은 해당 명령 창에만 적용됩니다. 다른 컴퓨터의 개발 환경 준비는 이후 승인된 단계에서 정리합니다.

## 기준 버전 확인과 안전한 복원

현재 작업 폴더를 변경하지 않고 기준 버전을 확인합니다.

```powershell
git status --short --branch
git show --stat --oneline ui-baseline-v1
git tag --points-at ui-baseline-v1
```

기준 화면을 별도 폴더에서 확인하는 가장 안전한 방법은 분리된 worktree를 만드는 것입니다. 기존 작업 파일은 덮어쓰지 않습니다.

```powershell
git worktree add --detach '..\US_Treasury_Auction_ui-baseline-v1' ui-baseline-v1
```

생성된 폴더에서 이 README의 실행 명령을 사용합니다. 현재 폴더를 과거 상태로 강제 변경하는 `reset --hard`는 사용하지 않습니다. 이미 같은 확인 폴더가 있거나 현재 변경을 실제로 되돌려야 한다면 먼저 변경을 별도 커밋·복사로 보존한 뒤 진행합니다.

## 화면 확인 순서

1. `http://localhost:3000/`을 새로고침합니다. `UST AUCTION`, `입찰 결과`, 짙은 남색 배경을 확인합니다.
2. KPI 순서는 응찰률 → High Yield (Stop) → 간접낙찰률 → 직접낙찰률 → PD낙찰률 → Allotted at High입니다. 두 번째 카드 이름은 상품에 맞게 바뀝니다(물가연동채: 실질금리).
3. `중기채` 필터 → 결과표의 `2년 중기채`를 선택합니다. 표본 기준 응찰률은 `266.0%`입니다. 같은 종류·만기의 직전 자료가 없으면 낙찰률 증감은 `비교 자료 없음`입니다.
4. 하단에 최근 결과표와 예정 일정표가 함께 있는지 확인합니다. 표본의 2년 중기채 예정일은 한국 `2026-08-26 02:00` ↔ 미국 동부 `2026-08-25 13:00`으로 전환됩니다. 결제일은 시각 정보가 없으므로 `2026-08-31 · 원문 ET`로 유지됩니다.
5. 창 폭을 줄여 6개 KPI가 3열 또는 2열로, 차트가 세로로 배치되는지 확인합니다. 긴 표는 내부 스크롤로 조회합니다. 자료 기준 시각과 시간대 버튼은 작은 화면에서도 표시됩니다.

## 검사 명령

위와 같이 폴더 및 PATH를 설정한 다음 실행합니다.

```powershell
pnpm test:ui
pnpm test
pnpm lint
```

- `test:ui`: 인터넷 요청 없이 표시·계산·서머타임·날짜 경계 등 22개 검사
- `test`: 실행용 빌드를 새로 만든 뒤 총 24개 검사. 화면 테스트는 인터넷 요청을 차단하고 대체 표본을 사용합니다.
- `lint`: 코드 작성 규칙 검사
- 전체 TypeScript 형식 검사에는 기존 Cloudflare/DB 형식 선언 오류 3개가 남아 있습니다. 자세한 내용은 `TEST_LOG.md`에 기록했습니다.

상세 진행 상태는 `PROJECT_STATUS.md`, 단계별 테스트 결과는 `TEST_LOG.md`를 확인하세요. 기준 저장 전에 빌드·브라우저 조작까지 재검사했습니다. QRA·발행통계 화면, 실제 API 조사·수집기·DB 생성·외부 배포는 진행하지 않았습니다.

# AI Quant Lab — 진행 로그 (복기용)

> 이 문서는 **세션이 끊겨도 맥락을 잃지 않기 위한 복원용 기록**이다. 새 세션은 이 파일만
> 읽으면 지금까지의 작업·구조·결정·다음 할 일을 전부 파악할 수 있어야 한다.
> **작업 슬라이스를 하나 끝낼 때마다 이 문서를 갱신해서 같은 커밋/패치에 포함**한다.

## 현재 위치 (한 줄)
M0–M4(백테스트 코어 + 리포트) + **M5 웹 대시보드**(대시보드·종목 찾기·종이 포트폴리오·비교·무결성 감사) 완료.
**2026-08-06 프로젝트 일시중단** — 더 급한 다른 프로젝트로 이동. 마지막 병합 = **PR #18(페이퍼 트레이딩)**.
코드는 전부 base에 병합돼 있고 테스트 그린(**215 passed, 1 skipped**). 재개는 아래 "⏸️ 재개 가이드"부터.

## ⏸️ 재개 가이드 — 새 세션/새 계정은 반드시 여기부터 읽기 (2026-08-06 중단)

> **한 줄:** 코드는 다 병합돼 있음. 재개하려면 ① 이 repo를 새 세션에 붙이고 ② GitHub App 쓰기 권한만
> 확인하면 바로 이어서 개발 가능. Claude에게 줄 첫 명령: **`docs/PROGRESS.md 읽고 이어서 하자`**.

### 1) 리포지토리 / 브랜치 좌표
- **repo**: `AHRA-June/AI_quant_lab` (GitHub, "AI 퀀트 전략실험실").
- **base 브랜치 = 사실상 default**: `claude/ai-quant-lab-prd-xf6a6h` — ⚠️ **이 repo엔 `main`이 없다.**
  모든 기능 PR은 이 브랜치로 병합한다. **최신 코드는 항상 이 브랜치.**
- **작업(기능) 브랜치**: `claude/progress-md-review-lx80cy`. PR이 병합되면 그 브랜치는 끝난 것 →
  **base에서 새로 시작해 같은 이름으로 재사용**(병합된 히스토리 위에 쌓지 말 것; `git checkout -B <브랜치> origin/<base>`).
- **로컬(윈도우)**: 클론 후 `git checkout claude/ai-quant-lab-prd-xf6a6h`.

### 2) 새 계정에서 "자동 커밋·PR"을 켜는 법 (제일 중요 — 안 되면 patch 수기로 회귀)
자동화(=Claude가 직접 커밋·PR)는 **GitHub App 권한**에 100% 의존한다. 새 계정/새 세션에서 반드시 확인:
1. 새 Claude 세션에 **이 repo가 붙어 있어야** 한다. 없으면 `list_repos`로 확인 후 `add_repo`(owner=`AHRA-June`, repo=`AI_quant_lab`).
2. **Claude GitHub App**이 대상 repo에 **Contents: Read and write + Pull requests: Read and write** + **활성(Unsuspend)** 상태여야 한다.
   - github.com → Settings → Applications → Installed GitHub Apps → **Claude** → Configure
   - Repository access에 `AI_quant_lab` 포함 / 권한 위 두 개 read-write / Danger zone이 **"Suspend"로 보이면 정상**(활성).
     **"Unsuspend"로 보이면 정지 상태** → 눌러서 활성화해야 쓰기가 열린다.
   - ⚠️ 이번에 자동화가 처음 `403 Resource not accessible by integration` 난 **진짜 원인이 앱 정지(suspended)**였음.
     **Unsuspend 후 `git push`·MCP `push_files` 둘 다 정상화**됨.
   - ⚠️ 세션 실행 중 권한을 바꾸면 그 세션의 캐시 토큰 갱신까지 지연 있을 수 있음 → 잠깐 뒤 재시도하거나 새 세션 시작.
3. **완전히 다른 GitHub 계정으로 repo를 옮기는 경우**: 새 소유자 계정에도 Claude GitHub App 설치 + 위 권한 필요.
   base 브랜치명(`claude/ai-quant-lab-prd-xf6a6h`)은 유지 권장(문서가 참조). 바꾸면 이 문서의 base 참조도 함께 갱신할 것.

### 3) 재개 절차 (Claude가 그대로 수행)
1. `docs/PROGRESS.md` 통독 → 이 가이드 + 아래 "다음 할 일".
2. 로컬 최신화: `git fetch origin claude/ai-quant-lab-prd-xf6a6h && git checkout -B claude/progress-md-review-lx80cy origin/claude/ai-quant-lab-prd-xf6a6h`.
3. 개발 → `python -m pytest`로 그린 확인(전부 network-free, 약 2–3분).
4. 커밋·푸시: **`git push -u origin <브랜치>` 우선**(unsuspend면 됨). 실패 시 MCP `push_files` 폴백.
5. `create_pull_request(base=claude/ai-quant-lab-prd-xf6a6h, head=<브랜치>)` → 사용자 병합.
6. **끝낼 때마다 이 문서 갱신**(연대기 + 테스트 카운트 + 다음 할 일)해서 같은 PR에 포함.

## 다음 할 일 (재개 시 우선순위 · 파일 포인터 포함)
1. **결과 내보내기(CSV/JSON)** — 가장 작고 자립형(network-free)이라 재개 첫 슬라이스로 추천.
   - 스크린 매칭 CSV는 이미 있음(`web/app.py`의 `screen_matches_csv`, `GET /screen/{id}/matches.csv`).
   - 추가할 것: 스크린 결과 **JSON** 내보내기 + **종이 포트폴리오 내보내기**(`GET /paper/{id}/export.csv|.json`).
     직렬화는 `web/paper.py`의 `PaperPortfolio.to_dict()` 재사용. 라우트는 `web/app.py`.
2. **페이퍼 트레이딩 후속** (연대기 #14 확장):
   - (a) **전략(백테스트) 결과에서도 담기** — 지금은 스크린 출처만. 백테스트의 **마지막 목표비중 스냅샷**이 없어서
     막혀 있음 → `quantlab/run.py`/`web/service.py`에서 마지막 리밸런스 weights를 `runs/<id>/weights.json`으로
     저장하는 작은 확장 후, `web/paper.py`에 `open_from_run()` 추가 + `run_detail_page`에 "담기" 버튼.
   - (b) **평가 이력 시계열 차트** — 매 `mark_paper` 결과를 `paper/<id>/marks.jsonl`로 append하고
     상세 페이지에 self-contained SVG 스파크라인(외부 asset 0 원칙 유지).
   - (c) **리밸런스 자동 반영** — 현재는 buy-and-hold. 목표비중 주기적 리밸런싱 옵션.
3. **스크린/KRX 데이터 핀** — 스크린도 유니버스 패널을 parquet로 스냅샷·핀하면 오프라인 재현 가능
   (재현성 번들 확장). `web/repro.py`의 `pin_file`/`reproduce_run` 패턴을 스크린 패널에 적용.
4. **리서치 파이프라인** — 리밸런스일별 완전 point-in-time 유니버스(현재 v1은 start 시점 1회 구성).
   코어 `quantlab/data/universe.py` + `factors/portfolio.py` 확장.
5. **스크리너 실데이터(로컬)** — `.[data]` + KRX 네트워크로 실제 한국 종목명 스크리닝(로컬 전용, 네트워크 필요).

> **참고:** 위 요청 백로그(1~9)와 스크리너·KRX 관련 사용자 요청은 **전부 처리·병합 완료**(아래 "요청 백로그" 참고).
> 미해결 사용자 버그는 없음. 재개는 "다음 할 일"에서 고르면 된다.

## 개발 환경 & 워크플로 메모 (중요)
- **자동 커밋·PR 워크플로 (2026-08-06 가동 — patch 수기 전달 폐지)**: 이제 Claude가 GitHub MCP로 직접 커밋·PR 한다.
  사용자는 GitHub UI에서 **확인·병합만** 하면 됨(patch `git am` 수기 작업 불필요).
  - **전제**: Claude GitHub App이 **활성(unsuspend) + Contents/Pull requests: Read and write** 여야 함.
    처음엔 앱이 정지(suspended) 상태여서 모든 쓰기가 `403 Resource not accessible by integration`로 막혔음 →
    github.com Settings → Applications → Claude 의 **Danger zone에서 Unsuspend** 후 쓰기 정상화됨.
    (주의: 세션 실행 중에 unsuspend하면 그 세션의 캐시 토큰이 갱신될 때까지 지연이 있을 수 있음 — 잠시 뒤 재시도하면 통과.)
  - **자동 흐름**: ① 로컬에서 코드/테스트 작성·`pytest` 검증 → ② (브랜치 없으면) `create_branch`(from_branch=base) →
    ③ `push_files`(owner=`AHRA-June`, repo=`AI_quant_lab`, branch=기능브랜치, files=변경파일 전체내용, message=커밋메시지)로
    원격 커밋 → ④ `create_pull_request`(base=`claude/ai-quant-lab-prd-xf6a6h`, head=기능브랜치)로 PR 자동 생성.
  - **커밋 방법 두 가지 (unsuspend 상태 기준 둘 다 동작)**:
    (a) **`git push -u origin <branch>` — 권장, 가장 간단**. 앱 정지 땐 403이었으나 **Unsuspend 후 정상 동작 확인됨**(PR #18은 이걸로 푸시).
    (b) MCP `push_files` — 폴백. diff가 아니라 **파일 전체 내용**을 통째로 올리므로 올리기 전 로컬 파일을 최종본으로 만들고 그 내용을 넣는다.
  - `push_files`로 원격에 직접 커밋했다면 로컬은 `git fetch origin <branch>` + `git reset --hard origin/<branch>`로 맞춘다(로컬 `git push`면 불필요).
- 기본 브랜치(=PR base): `claude/ai-quant-lab-prd-xf6a6h` (이 repo엔 `main` 없음, PRD 브랜치가 base 역할).
  현재 기능 브랜치: `claude/progress-md-review-lx80cy`.
- 사용자 환경: **Windows + Python 3.14**. 두 가지 실행 방식:
  - **venv 사용(사용자가 실제로 쓰는 방식)**: `.venv` 활성화 상태(`(.venv)` 프롬프트)면 그냥 **`python`** 사용.
    ⚠️ 이때 `%PY%`는 필요 없음(그건 PATH에 파이썬이 없을 때만). 사용자가 `'"%PY%"'은 명령이 아닙니다` 에러를
    낸 적 있음 → **venv 안에서는 `python -m ...`** 로 안내할 것.
  - **PATH 미등록 + venv 없을 때**: `set PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe` 후 `"%PY%" -m ...`.
  - pykrx는 설치돼 있으나 KRX 네트워크는 로컬에서만 됨.

## 로컬 실행법
```cmd
:: venv 활성화 상태면 그냥 python
python -m pip install -e ".[web,data]"
python -m uvicorn quantlab.web.app:create_app --factory --port 8000
```
→ http://127.0.0.1:8000 . 자연어/해설은 `ANTHROPIC_API_KEY` + `.[llm]` 필요(유료 API).
KRX 실데이터는 `.[data]` + KRX 네트워크. **둘 다 없어도** 합성/CSV/직접-조건식으로 다 돌아감.
화면 사용 순서(페이퍼 트레이딩): 종목 찾기 → 조건 실행 → 결과에서 "종이 포트폴리오로 담기" → 종이 포트폴리오 탭 → "다시 평가".

## 무엇을 만들었나 (연대기)
### 코어 (M5 이전, 이미 병합됨)
- `PriceStore` 캐시 range-coverage 버그 수정, `apply_rebalance` 월간 별칭 `"M"` 수정.
- `CsvDataSource` (다운로드 OHLCV로 실데이터 파이프라인), `examples/run_sp500.py`.
- 리포트를 **Stitch 디자인 + 한글 + 쉬운 설명**으로 리스킨 (self-contained, theme-aware).

### M5 웹 대시보드 (슬라이스, 모두 병합됨 PR #1~#6)
1. **골격** — FastAPI `create_app`, RunStore(runs.jsonl), 합성 백테스트 실행/리포트, `quantlab serve`.
2. **CSV 실데이터** — 데이터 소스 토글, 업로드 → run_backtest.
3. **비교(PBO) + 무결성 감사** — `/compare`(run_comparison 실PBO/DSR), `/audit`(trial log + holdout).
   run_backtest에 `trials_path` 추가 → 모든 실행이 시도 로그 공유(DSR의 N 완전성).
4. **비동기 작업 큐** — `web/jobs.py` JobQueue(스레드풀), POST는 즉시 202/redirect, `/api/jobs`,
   대시보드 "실행 중 작업" + 2초 자동 새로고침.
5. **작업 관리** — 인앱 run 상세(`/runs/{id}`, 리포트 iframe), 삭제, 재실행, 큐 취소.
6. **자연어 입력 + LLM 해설** — `자연어 아이디어` 소스(StrategyGenerator NL→검증DSL),
   `write_strategy_report(client=)` → 리포트에 한글 상세 해설. 키 없으면 우아하게 비활성.
7. **KRX 일봉 소스** — `run_krx_backtest`(pykrx, source 주입 가능), 게이팅.
8. **종목 찾기(스크리너)** — `dsl/screen.py` 불리언 필터 컴파일러(`> < >= <=`, and/or/not,
   화이트리스트), NL→조건식 두 경로(**키 있으면** `ScreenGenerator` LLM, **키 없으면** 규칙 기반
   `dsl/nl_screen.py`), `run_screen`(유니버스→panels→mask→기준일 매칭 리스트 + 그 종목 동일가중
   백테스트), `/screen` 탭. **자연어·빠른 조건·직접 조건식 모두 키 없이 무료**. KRX는 바스켓/전체 유니버스 선택.
9. **재현성 번들** — `web/repro.py`. 실행마다 `bundle.json` 저장(입력·시드·버전 + 결과 **지문**
   = 헤드라인 지표 sha256 16자리). 합성 실행은 시드 고정 → **자동 재현 대상**(`reproducible=True`),
   csv/krx/nl/screen은 외부 데이터 의존 → 기록만(`reproducible=False`+한글 사유). run 상세에
   "재현성 번들" 섹션(지문·검증배지·번들 JSON 다운로드·`재현 검증` 버튼). 라우트
   `GET /runs/{id}/bundle.json`(첨부), `POST /runs/{id}/reproduce`(재실행→지문비교→
   verdict를 bundle.json에 각인, 재현 불가 종류는 422).
10. **CSV 데이터 핀** — CSV 백테스트는 업로드 원본을 `runs/<id>/pinned/`에 복사+sha256 해시하고
    `config_yaml`·window·ticker_col을 번들에 저장 → **CSV도 오프라인 자동 재현**(`reproducible=True`).
    `pin_file`, `file_sha256`, `_reproduce_csv`(핀 해시 검증 후 임시 dir에 동일 실데이터 경로 재실행).
    핀 파일 변조 시 해시 불일치로 거부. 상세 화면에 "데이터 핀: 파일·해시" 표시. **네트워크 0**.
11. **KRX 휴장일 버그 수정** — pykrx `get_market_cap`/`get_market_ticker_list`는 휴장일(예:
    근로자의 날 05-01) 조회 시 빈 프레임 후 `KeyError: ['종가','시가총액','거래량','거래대금']`로
    죽는다. `_asof_trading_day`로 유니버스 기준일을 **가장 가까운 직전 거래일로 스냅**
    (`get_nearest_business_day_in_a_week`, PIT 안전하게 prev). 빈 응답이면 한글 에러로 명확히.
    `tests/test_pykrx_source.py`(fake stock 주입, network-free)로 스냅·에러·티커 경로 검증.
12. **입력 UX 개선** — (a) 자립형 팝업 캘린더(`_CAL_JS`+`_datefield`): 네이티브 date input 대신
    월 그리드에서 일 클릭 → 숨은 input에 `YYYY-MM-DD`. 대시보드·종목찾기 공용. (b) 실데이터 폼에
    전략 프리셋 5종(모멘텀+거래량/모멘텀/단기반전/저변동성/거래대금급증) + 시장·상위시총·종목수·리밸런스
    드롭다운 → JS가 config YAML 자동 조립. 원시 YAML은 "고급" `<details>`로 강등. 백엔드 계약 불변
    (여전히 `config_yaml` 텍스트 제출). 프리셋 alpha 전부 `compile_alpha`/`StrategyConfig` 검증 테스트.
13. **캘린더/KRX 견고화** — (a) 캘린더가 `<label>` 클릭가로채기로 안 되던 것 수정(라벨 제거+핸들러
    강화+기본날짜). (b) KRX 시가총액 조회를 `_asof_candidates`(스냅+7일 walk-back, vendor KeyError
    포획)로 감싸 휴장/미공개일에도 데이터 있는 날을 찾음. `tests/test_pykrx_source.py`에 walk-back 케이스.
14. **페이퍼 트레이딩(종이 포트폴리오)** — `web/paper.py` 신설. 종목 찾기 결과의 매칭 종목을
    **동일가중**으로 담아(진입가 스냅샷 + notional로 분수주 배분, 완전투자) 목표비중을 앞으로 추적.
    `PaperHolding`/`PaperPortfolio`(mutable JSON) + `PaperStore`(base/paper/<id>/, 글롭 리스트).
    `open_from_screen`(screen.json→holdings), `mark_paper`(주입 가능 source로 현재가 재조회 →
    **매수후보유** 평가액·손익, 데이터 없는 종목은 held-flat + 플래그). **CSV 출처는 원본을 핀**
    (base/paper/<id>/pinned/) → 오프라인 재평가(재현성 번들과 동일 패턴), **KRX는 라이브 pykrx**(게이팅).
    새 탭 `/paper`(목록)·`/paper/{id}`(보유·손익·다시평가·삭제), 라우트 `POST /api/paper`(스크린에서 담기)·
    `POST /paper/{id}/mark`(평가일 옵션)·`POST /paper/{id}/delete`. 스크린 결과에 "종이 포트폴리오로 담기".
    screen.json에 `kind`/`data_ref` 추가(마킹용 소스 재구성). `tests/test_paper.py`(13 케이스: 동일가중
    사이징·주입 마킹·데이터없음 스킵·진입전 거부·CSV 핀 오프라인·스토어 라운드트립·API 전체흐름).

## KRX 실데이터 사용 메모 (중요)
- KRX **스냅샷 엔드포인트는 죽어있고 종목별 시세만 됨** → 웹 KRX 모드는 **종목 코드 바스켓**으로 동작.
  UI "종목 코드" 칸에 6자리 코드(기본 대형주 채워짐)를 넣으면 그 종목만 백테스트. 시장/상위시총 무시.
- 바스켓 비우면 자동 유니버스(UniverseBuilder) 폴백 — 단 그건 스냅샷 엔드포인트가 살아있어야 함.
- CSV 업로드 경로는 이 문제와 무관하게 항상 동작(권장).

## 아키텍처 (`src/quantlab/web/`)
- `store.py` — RunRecord(+universe_size/window/note), RunStore(append/list/get/delete, report_path).
- `jobs.py` — Job/JobQueue(제출·상태·취소, ThreadPoolExecutor).
- `service.py` — 오케스트레이션. run_synthetic/csv/krx/nl_backtest, run_screen, run_pbo_comparison,
  read_trials/read_holdout_audit/read_screen, get_llm_client/krx_available. **분석 로직은 코어 재사용**.
- `pages.py` — 서버렌더 HTML(_shell+nav, 대시보드/종목찾기/비교/감사/상세/결과). 인라인 CSS,
  리포트와 같은 팔레트, self-contained, 한글, theme-aware. 상세엔 `_repro_section`(번들 표시).
- `repro.py` — 재현성 번들. `SEEDS`, `result_fingerprint(out)`, `write_bundle`, `read_bundle`,
  `pin_file`/`file_sha256`(원본 데이터 복사+해시), `reproduce_run`(kind별 분기: synthetic 재실행,
  csv는 핀 파일에서 재실행; 임시 trials.jsonl로 실제 시도수 오염 안 함, verdict 각인).
- `paper.py` — 페이퍼 트레이딩. `PaperHolding`/`PaperPortfolio`(mutable), `PaperStore`(base/paper/<id>/),
  `open_from_screen`(스크린→동일가중 종이북+진입가), `mark_paper`(주입 source로 현재가 재조회→매수후보유
  평가·손익), `_build_source`(csv=핀에서 재구성/krx=라이브 pykrx). CSV는 진입 시 원본 핀→오프라인 재평가.
- `app.py` — FastAPI 팩토리(라우트). create_app(runs_dir, n_shuffles, max_workers, llm_client).
- 탭: **대시보드 · 종목 찾기 · 종이 포트폴리오 · 비교 · 무결성 감사**. 데이터: **합성 · 자연어 · CSV · KRX**.

## 핵심 설계 원칙
- **자립성**: 모든 산출 HTML은 CDN/웹폰트/외부에셋 0 (오프라인 렌더, 재현성 번들 대비).
- **무결성 우선**: 셔플 대조군·DSR·PBO·시도 로그가 1급 시민. trial log는 append-only 불변.
- **LLM은 옵션**: 키 없어도 핵심 기능 동작. LLM은 자연어 번역·해설 편의만.
- **안전 경계**: DSL/스크린은 화이트리스트 AST — 이상한 식은 실행 전 거부.
- **테스트는 network-free**: fake DataSource(`tests/fakes.RichFakeDataSource`) + FakeLLM 주입.

## 요청 백로그 (사용자가 고쳐달라고 한 것 — 처리하면 ✅)
> 사용자가 "수정할 거 있다"고 하면 여기에 하나씩 적고, 끝나면 체크한다.
- [x] (1) 날짜 입력: 년/월 고르면 일까지 고르는 상세 달력이 안 뜸 → **자립형 팝업 캘린더**(`_CAL_JS`,
  `.datefield`/`.cal`)로 교체. `<input type=date>` 제거, 숨은 input에 `YYYY-MM-DD` 기록. 대시보드+종목찾기 둘 다.
- [x] (2) DSL YAML 수기 입력 무리 → **프리셋 5종 + 친화 폼**(시장/상위시총/종목수/리밸런스)이 YAML을
  자동 생성. YAML은 `<details>` 고급 옵션으로 강등(직접 편집도 가능). 프리셋 alpha 전부 컴파일 검증.
- [x] (3) 달력 여전히 에러(전월 이동·일자 선택 불가) → 원인: `_datefield`가 `<label>` 안에 있어
  label이 클릭을 연결된 컨트롤로 가로채 팝업이 즉시 닫힘. **label 래핑 제거**(`.fld` div + 캡션 span),
  핸들러에 `preventDefault`/`stopPropagation` + `closest('button')`. 기본 날짜 자동 채움(시작 -365, 종료 0).
- [x] (4) KRX 백테스트 에러(휴장/최근일 KeyError) → pykrx `get_market_cap`가 데이터 없는 날에
  내부에서 KeyError. `_asof_candidates`로 **스냅 후 최대 7일 뒤로 물러나며** 데이터 있는 날 탐색,
  vendor 예외를 잡고 최종 실패 시 한글 에러. `get_nearest_business_day_in_a_week`는 **네트워크 호출**임에 유의.
- [x] (5) KRX가 여전히 실패(2025-07-01 정상 거래일도 빈 응답) → **진단 결과**: KRX의 크로스섹션
  스냅샷 엔드포인트(get_market_cap / get_market_ohlcv_by_ticker / get_market_cap_by_date /
  get_index_portfolio_deposit_file)가 **전부 빈 JSON**("Expecting value")으로 죽어있고, **종목별
  시세 `get_market_ohlcv(기간,종목)`만 생존**(pykrx 최신 업뎃해도 동일 → KRX/네트워크측 차단).
  → **해결**: KRX 유니버스를 **명시적 종목 바스켓**으로 받아 종목별 시세만으로 구성. `run_backtest(tickers=)`
  추가(주면 UniverseBuilder 건너뜀), `run_krx_backtest(tickers=)`+`DEFAULT_KRX_TICKERS`(대형주 33종),
  `parse_tickers`(6자리 정규화), UI에 KRX 전용 "종목 코드" 입력칸(기본 바스켓 프리필). 죽은 스냅샷
  엔드포인트 **호출 0**. `_SnapshotDeadKRX` fake로 그 사실을 테스트로 못박음. tickers 없으면 기존
  자동 유니버스 폴백(스냅샷 살아있는 환경용).
- [x] (6) 바스켓 KRX 실행 `KeyError: 'close'` → 원인 둘: pykrx 종목별 OHLCV엔 **거래대금(value) 컬럼이
  없고**, 데이터 없는(상폐/거래정지) 종목은 **빈 프레임**이 와서 `raw["close"]`가 터짐. `_normalize_ohlcv`가
  이제 **value=close×volume 파생** + **항상 캐노니컬 6컬럼 보장**(빈 응답도 close 컬럼 존재) → 다운스트림
  KeyError 소멸, 데이터 없는 종목은 조용히 스킵. 단위테스트(파생/빈프레임) + `_KRXWithDeadTicker` 통합테스트.
- [x] (7) 바스켓 실행 `no price data assembled` → 원인: pykrx는 **`adjusted=False`(원주가)=KRX MDCSTAT(죽음)**,
  **`adjusted=True`(수정주가)=네이버(생존)**. 내 `get_ohlcv`가 원주가로 불러 전 종목 빈 패널 → "no price data".
  `get_ohlcv`가 원주가 시도 후 **비면 수정주가로 폴백**(백테스트엔 수정주가가 정답, factor→1). 원주가 살아있는
  환경은 그대로. fake stock으로 폴백/비폴백 테스트. ✅ **KRX 백테스트 완주 확인됨(사용자).**
- [x] (8) 종목찾기 스크리너: 자연어/조건 쓰고 실행하면 "글 사라지고 아무 작동 안 함" → 원인 셋:
  (a) **/screen 페이지에 잡 상태 섹션이 없어** 스크린 잡이 실패해도 화면에 안 뜸(리다이렉트로 입력만 사라짐);
  (b) LLM 키 없으면 자연어칸 미표시 → 사용자가 **직접 조건식칸에 한글**을 넣어 `compile_screen` 실패;
  (c) KRX 스크리너는 `run_screen`이 UniverseBuilder(죽은 스냅샷) 사용 → 실패. → **수정**: /screen에
  `_jobs_section`+자동새로고침으로 **실패를 에러메시지까지 노출**; **빠른 조건 프리셋 5종**(20일선+거래량급등 등)
  드롭다운이 직접 조건식칸 자동 채움(키 불필요); `run_screen(tickers=)` 추가 → KRX 스크리너도 **명시적 바스켓**;
  compile_screen 실패 시 **친절한 한글 에러**(예시 포함). 테스트: 실패노출·프리셋·바스켓·친절에러.
- [x] (9) 스크리너 v2 사용자 피드백 3건 (병합 완료 후 후속):
  (a) **20개 한정 어불성설** → KRX "검색 범위" 선택(바스켓/코스피/코스닥/전체) + `resolve_krx_universe()`,
  전체목록 다운 시 친절 에러로 바스켓 폴백 유도;
  (b) **종목 이름 미표시** → 결과 페이지·`matches.csv` 모두 `name` 포함 확인(KRX `get_ticker_name`);
  CSV 업로드는 Name 컬럼 없으면 코드 폴백임을 UI로 설명;
  (c) **자연어가 너무 어려움/키 필요** → **규칙 기반 한국어 번역기 `dsl/nl_screen.py`** 신설로
  LLM 키 없이 자연어 칸 동작(골든크로스·N일선·거래량급등·신고가·N일상승·N% 상승, 그리고/또는 연결).
  테스트: 번역기 유효성(파라미터라이즈)·미인식 친절에러·엔드투엔드 자연어·유니버스 리졸버·페이지 렌더.

## 다음 후보 (아직 안 함)
- **스크린/KRX 데이터 핀**: screen은 주입 source라 CSV처럼 파일-핀이 아님. 유니버스 패널을
  parquet로 스냅샷해 핀하면 screen/krx도 오프라인 재현 가능(다음 확장).
- ~~**페이퍼 트레이딩**~~: ✅ 완료(연대기 #14) — 종이 포트폴리오 담기·마킹·손익. **후속 아이디어**:
  전략(백테스트) 결과에서도 담기(현재는 스크린 출처만), 리밸런스 자동 반영, 평가 이력 시계열 차트.
- **결과 내보내기**: 스크린 매칭 종목·지표를 CSV/JSON 다운로드.
- **리서치 파이프라인**: 리밸런스일별 완전 point-in-time 유니버스(현재 v1은 start 시점 1회).
- **스크리너 실데이터**: 로컬 `.[data]`로 실제 한국 종목명 스크리닝(네트워크 필요).

## 테스트/실행 상태
`python -m pytest` → 최근 **215 passed, 1 skipped**(krx 게이팅은 pykrx 유무에 따라; 페이퍼 트레이딩 13건 포함).
전부 network-free.

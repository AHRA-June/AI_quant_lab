# AI Quant Lab — 진행 로그 (복기용)

> 이 문서는 **세션이 끊겨도 맥락을 잃지 않기 위한 복원용 기록**이다. 새 세션은 이 파일만
> 읽으면 지금까지의 작업·구조·결정·다음 할 일을 전부 파악할 수 있어야 한다.
> **작업 슬라이스를 하나 끝낼 때마다 이 문서를 갱신해서 같은 커밋/패치에 포함**한다.

## 현재 위치 (한 줄)
M0–M4(백테스트 코어 + 리포트)는 완료. 지금은 **M5 제품화 = 웹 대시보드**를 슬라이스로
쌓는 중. FastAPI + self-contained HTML, 전부 네트워크-free 테스트.

## 개발 환경 & 워크플로 메모 (중요)
- 이 개발 세션의 GitHub 토큰은 **read-only** 라 여기서 `git push`/PR 생성이 **안 됨(403)**.
  그래서 매 슬라이스를 **git patch로 만들어 사용자에게 전달** → 사용자가 로컬에서
  `git am < patch` 후 push, GitHub UI에서 PR 생성·병합한다.
- 기본 브랜치(=작업 base): `claude/ai-quant-lab-prd-xf6a6h`. 기능 브랜치: `claude/continue-1wf4bm`.
- **패치는 반드시 최신 base에서 생성**할 것 (`git fetch` 후 `git format-patch <base>..HEAD`).
  과거에 base가 stale해서 이전 커밋이 패치에 중복으로 섞여 `git am` 충돌난 적 있음.
- 사용자 환경: **Windows + Python 3.14** (PATH 미등록 → `set PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe`
  후 `"%PY%" -m ...` 로 실행). pykrx는 설치돼 있으나 KRX 네트워크는 로컬에서만.

## 로컬 실행법
```cmd
"%PY%" -m pip install -e ".[web]"
"%PY%" -m uvicorn quantlab.web.app:create_app --factory --port 8000
```
→ http://127.0.0.1:8000 . 자연어/해설은 `ANTHROPIC_API_KEY` + `.[llm]` 필요(유료 API).
KRX 실데이터는 `.[data]` + KRX 네트워크. **둘 다 없어도** 합성/CSV/직접-조건식으로 다 돌아감.

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
   화이트리스트), `ScreenGenerator` NL→조건식, `run_screen`(유니버스→panels→mask→기준일
   매칭 리스트 + 그 종목 동일가중 백테스트), `/screen` 탭. **직접 조건식은 키 없이 무료**.
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
- `app.py` — FastAPI 팩토리(라우트). create_app(runs_dir, n_shuffles, max_workers, llm_client).
- 탭: **대시보드 · 종목 찾기 · 비교 · 무결성 감사**. 데이터: **합성 · 자연어 · CSV · KRX**.

## 핵심 설계 원칙
- **자립성**: 모든 산출 HTML은 CDN/웹폰트/외부에셋 0 (오프라인 렌더, 재현성 번들 대비).
- **무결성 우선**: 셔플 대조군·DSR·PBO·시도 로그가 1급 시민. trial log는 append-only 불변.
- **LLM은 옵션**: 키 없어도 핵심 기능 동작. LLM은 자연어 번역·해설 편의만.
- **안전 경계**: DSL/스크린은 화이트리스트 AST — 이상한 식은 실행 전 거부.
- **테스트는 network-free**: fake DataSource(`tests/fakes.RichFakeDataSource`) + FakeLLM 주입.

## 다음 후보 (아직 안 함)
- **스크린/KRX 데이터 핀**: screen은 주입 source라 CSV처럼 파일-핀이 아님. 유니버스 패널을
  parquet로 스냅샷해 핀하면 screen/krx도 오프라인 재현 가능(다음 확장).
- **페이퍼 트레이딩**: 선택 전략/스크린의 목표비중을 앞으로 추적(종이 포트폴리오).
- **결과 내보내기**: 스크린 매칭 종목·지표를 CSV/JSON 다운로드.
- **리서치 파이프라인**: 리밸런스일별 완전 point-in-time 유니버스(현재 v1은 start 시점 1회).
- **스크리너 실데이터**: 로컬 `.[data]`로 실제 한국 종목명 스크리닝(네트워크 필요).

## 테스트/실행 상태
`python -m pytest` → 최근 **153 passed, 1 skipped**(krx 게이팅은 pykrx 유무에 따라). 전부 network-free.

# Ideas

> When useful, prefix added notes with [user], [codex], or [claude].

## Original Intent

ticker간의 관계를 벡터화 시켜가지고 각 티커간에 가장 연관관계가 많은 티커를 시각적으로도 모아서 볼수 있고, 또한, 숫자로도 모아서 볼수 있고 한 그런 벡터 덩이를 만들어보고 싶어. 이들에서 어떤 방식이 될지는 모르겠지만, 또 이를 주가 총액 변화 같은거도 그 벡터 상으로도 확인을 해볼수 있게 작업이 된다고 하면, 결국 생각해볼때 이를 일정 시기별로 계속 저장을 해보면, 어떤 흐름들로 움직이는지 이게 한눈에도 들어올수도 있는것은 아닌가 싶기도 하고 말야. 티커간 히스토리컬 데이터는 구글 드라이브에 저장해놓은것이 있는데 필요하면 내가 이후에 적어줄께

## North Star

[codex] 티커들 사이의 "관계 지도"를 만들어서, 어떤 종목들이 서로 가까이 움직이고 왜 가까운지 숫자와 시각화로 함께 확인할 수 있게 한다. 최종적으로는 이 관계 지도를 시기별 스냅샷으로 저장해, 군집의 이동, 중심 종목의 변화, 시가총액/가격 흐름의 변화를 한눈에 추적하는 도구가 된다.

[codex] 핵심은 예측 모델이나 매매 신호보다 "관계의 구조를 눈으로 보고, 숫자로 검증하고, 시간이 지나며 어떻게 변했는지 되짚는 것"이다.

[claude] North Star는 Original Intent와 잘 맞는다. 다만 "흐름이 한눈에 들어온다"는 약속 중 가장 깨지기 쉬운 부분은 "지도(2D 좌표) 위에서 시간 흐름을 따라간다"는 쪽이다. 좌표는 기간마다 다시 계산되면 축의 의미가 달라져서, 점이 움직였는지 축이 회전했는지 구분이 안 된다(아래 Notes 참고). 그래서 North Star의 "변화 추적"은 1차로는 숫자(이웃 집합 변화, 거리 변화, 시총 변화율)로 보장하고, "움직이는 지도"는 그 위에 얹는 보너스로 두는 편이 안전하다. 표현만 그렇게 분리하면 방향 자체는 동의한다.

## Current Scope

[codex] 지금 단계의 범위는 MVP 방향을 잡는 것이다. 첫 구현은 사용자가 제공할 히스토리컬 티커 데이터를 바탕으로:

- 티커별 기간 단위 feature를 만든다. 예: 수익률, 변동성, 거래량 변화 등.
- 같은 기간 안에서 티커 간 유사도/거리 점수를 계산한다.
- 각 티커마다 가장 가까운 티커 목록을 숫자로 보여준다.
- 전체 티커 관계를 2D 시각화로 보여준다. 첫 버전은 PCA scatter나 단순 네트워크 그래프처럼 설명 가능한 방식이 좋다.
- 특정 기간별 결과를 저장해서 나중에 기간 간 변화를 비교할 수 있게 한다.

[codex] 첫 번째 성공 기준은 "한 기간을 고르면 특정 티커 주변에 어떤 티커들이 모이는지, 그 근거 숫자가 무엇인지, 그리고 시가총액 변화가 그 지도 위에서 어떻게 보이는지 확인할 수 있다"로 잡는 것이 좋아 보인다.

[claude] Current Scope에 대체로 동의하되, 첫 구현은 "단일 기간 한 개를 끝까지 제대로"로 더 좁히길 제안한다. 즉 (1) 데이터 계약 확정 → (2) 한 기간의 feature 생성 + 정규화 → (3) 유사도/거리 → (4) nearest-neighbor 테이블 → (5) 2D scatter 하나 → (6) 그 결과를 디스크에 저장. "기간 간 비교"는 저장 포맷만 미리 비교 가능하게 잡아두고, 실제 비교 화면/시각화는 단일 기간이 납득될 때까지 미룬다.

[claude] 누락되기 쉬운 단계 하나: feature 정규화. 가격대·거래량 절대값이 큰 종목이 거리 계산을 지배하지 않도록 ticker별로 z-score 등 표준화를 명시적으로 Scope에 넣어야 한다. 안 그러면 "관계"가 아니라 "규모"를 군집화하게 된다.

[claude] 성공 기준이 세 가지(이웃, 근거 숫자, 지도 위 시총)를 한 번에 묶고 있다. 1차 합격선은 "nearest-neighbor 테이블이 직관적으로 납득되는가"를 주(primary)로 두고, scatter와 시총 overlay는 보조 검증으로 두는 게 좋다. 시각화가 예쁜지보다 테이블과 일치하는지가 먼저다.

[codex][반영] Current Scope를 "단일 기간 1개 end-to-end"로 더 좁힌다. 1차 구현의 중심 흐름은 데이터 계약 확정 -> 한 기간 수익률 생성/정렬 -> 상관 기반 거리 계산 -> nearest-neighbor 테이블 -> 보조 2D scatter -> 비교 가능한 결과 저장이다. 기간 간 비교 화면은 만들지 않고, 나중에 비교할 수 있도록 metadata와 저장 포맷만 준비한다.

[codex][반영] 1차 합격선은 nearest-neighbor 테이블이 직관적으로 납득되는 것이다. scatter와 시가총액 overlay는 "관계 테이블을 보조해서 확인하는 보기"로 둔다.

[codex][2차 리뷰 반영] "보조"는 "v1에서 제외"가 아니다. Original Intent의 두 축이 숫자와 시각화이므로, v1 산출물에는 nearest-neighbor 테이블과 2D scatter가 둘 다 반드시 포함된다. scatter는 테이블을 검증하고 관계 덩이를 눈으로 확인하기 위한 필수 출력이다.

[codex][2차 리뷰 반영] 시가총액 변화 overlay도 v1 목표 산출물로 유지한다. 단, 입력 데이터에 시가총액 또는 계산 가능한 주식수 정보가 없으면 그때만 fallback으로 overlay를 비워두고, 관계 테이블과 scatter를 먼저 완성한다. 이것은 scope 축소가 아니라 데이터 부재 대응이다.

## Non-Goals

[codex] 현재 목적에서 벗어나는 것은 일단 제외한다.

- 매수/매도 추천, 자동매매, 백테스트 성과 최적화
- 실시간 시세 스트리밍이나 장중 모니터링
- 뉴스, 공시, SNS, 애널리스트 리포트 같은 대체 데이터 통합
- 처음부터 완성형 대시보드나 배포 가능한 웹 서비스 만들기
- 관계가 "왜" 생겼는지에 대한 완전한 인과 설명
- 새 production dependency 추가 전제의 설계
- 사용자가 아직 제공하지 않은 Google Drive 데이터 자동 접근

[claude] 1차 범위에서 추가로 빼두면 좋을 것:

- 기간 간 "지도 좌표 정렬"(Procrustes/공유 투영 등). 1차는 기간 비교를 좌표가 아니라 숫자로만 한다.
- 상장폐지/신규상장으로 universe가 기간마다 바뀌는 경우의 정교한 처리. 1차는 "기간 내 데이터가 충분한 티커만 포함"하는 단순 규칙으로 간다.
- KR/US 혼합을 한 좌표 공간에 억지로 합치는 것. 통화·거래일 캘린더가 달라 해석이 흐려진다. 1차는 한 시장(또는 명확히 한 universe)으로 고정.
- 다중 관계 정의 동시 지원. 1차는 관계 정의를 딱 하나만 고른다.

[codex][반영] 위 항목들은 모두 1차 Non-Goals로 받아들인다. 특히 "기간 간 지도 좌표 비교"는 North Star와 가까워 보이지만, 잘못 만들면 Original Intent의 "흐름을 한눈에 본다"를 오히려 왜곡하므로 1차 구현에서 제외한다.

## Later Ideas

[codex] 좋아 보이지만 지금 목적에 꼭 필요하지 않은 확장:

- 시간에 따른 벡터 지도 애니메이션
- 포트폴리오 보유 종목을 지도 위에 올려 쏠림/분산 상태 보기
- 섹터, 산업, 국가, 테마 라벨을 겹쳐서 관계 해석 돕기
- 뉴스/공시/실적 콜 텍스트 embedding을 결합한 관계 벡터
- 관계가 급격히 바뀐 티커를 알림으로 표시
- 특정 티커를 기준으로 "과거에는 가까웠지만 지금은 멀어진 종목" 찾기
- 여러 관계 정의를 전환해서 비교하기. 예: 가격 동행성, 변동성 동행성, 펀더멘털 유사성, 시총 성장 패턴
- UMAP/t-SNE 같은 비선형 embedding으로 더 자연스러운 군집 시각화 비교하기
- NotebookLM이나 리포트 문서로 기간별 관계 변화 요약 내보내기

[claude] 좋지만 1차에는 불필요해서 미뤄둘 것(위 Non-Goals와 짝):

- 기간 간 좌표 정렬(Procrustes/reference-period 공유 투영)으로 "진짜 움직이는 지도" 만들기 — 이게 되면 North Star의 시각적 약속이 완성되지만 난이도가 높다.
- 명시적 군집화 알고리즘(KMeans/계층적/그래프 커뮤니티)으로 군집에 라벨 붙이기. 1차는 nearest-neighbor만으로 충분.
- KR/US 같은 다중 시장/통화를 한 공간에서 비교하는 정규화 전략.
- 인터랙티브 선택(티커 클릭 → 이웃 하이라이트). 1차는 정적 출력으로 충분.

[codex][반영] 위 Claude 항목들은 모두 Later Ideas로 둔다. "좋아 보이는 확장"이지만 Current Scope의 단일 기간 관계 검증에는 필요하지 않다.

## 내가 원하는 것

## 왜 필요한지

## 누가 쓸 건지

## 실제로 쓰는 장면

## 꼭 됐으면 하는 것

## 별로 원하지 않는 것

## 나중에 생각해도 되는 것

## Notes

[codex] "관계"를 처음부터 하나로 고정하기보다, 먼저 해석 가능한 baseline을 두는 것이 좋다. 예를 들어 일간/주간 수익률 상관, 변동성 패턴, 거래량 변화, 시가총액 변화율을 feature로 만들고, cosine similarity 또는 correlation 기반 거리로 시작하면 결과를 설명하기 쉽다.

[codex] 벡터는 "티커 자체의 영구 속성"이라기보다 "특정 기간 안에서 관찰된 티커의 행동 요약"으로 보는 편이 맞아 보인다. 그래서 저장 단위는 `period_start`, `period_end`, `ticker`, `features`, `embedding`, `nearest_neighbors`, `market_cap_change` 같은 형태가 자연스럽다.

[codex] 시각화는 처음부터 예쁘게 만들기보다, 숫자 테이블과 함께 봤을 때 납득 가능한지가 중요하다. 지도상 가까운 종목들이 실제 nearest-neighbor 테이블에서도 가까운지 검증할 수 있어야 한다.

[codex] 시가총액 변화는 좌표 자체에 섞기보다, 첫 버전에서는 색상/크기/툴팁 같은 overlay로 두는 편이 안전해 보인다. 그래야 "관계 계산"과 "시총 변화 관찰"이 섞여서 해석이 흐려지는 것을 막을 수 있다.

[claude] (가장 중요한 기술 함정) PCA 좌표는 기간마다 독립적으로 다시 적합되면 축이 회전/반전한다. 그래서 "기간 A 지도"와 "기간 B 지도"를 나란히 놓고 점의 이동을 읽는 것은 착시가 되기 쉽다. 1차에서는 "기간 간 변화"를 좌표가 아니라 이웃 집합 변화(예: A에서 가까웠다가 B에서 빠진 종목)와 거리/상관 값 변화 같은 숫자로 본다. 시각적 정렬은 Later로.

[claude] feature 표준화를 명시하자. ticker별로 변동성·거래량 스케일이 크게 달라서, z-score 또는 rank 정규화 없이 거리(특히 cosine/유클리드)를 재면 큰 스케일 종목이 결과를 지배한다. 상관(correlation) 기반 거리는 그 자체로 스케일 불변이라 baseline으로 더 안전하다.

[claude] 데이터 정합성 주의: (1) 분할/배당 조정 가격(adjusted)을 쓰는지 명확히 — 미조정 가격은 인위적 점프로 상관을 망친다. (2) 거래일 캘린더 정렬 — 결측/휴장이 섞이면 상관이 왜곡되니 공통 거래일로 정렬하거나 결측 처리 규칙을 정한다. (3) 기간 내 최소 관측 길이 기준(예: N일 미만이면 제외)을 둔다.

[claude] nearest-neighbor는 비대칭일 수 있다(A의 1순위 이웃이 B여도 B의 1순위는 C일 수 있음). 테이블에 "A→B 거리"를 보여줄 때 이 비대칭을 명시하거나, 상호 최근접만 강조하는 옵션을 고려.

[claude] 규모(scale) 메모: 티커 N개면 유사도 행렬은 N² 이다. universe가 수천 개면 메모리·연산이 커지므로, 1차 universe 크기를 Open Questions에서 먼저 확정하는 게 좋다.

[claude] 저장 스키마는 처음부터 너무 풍부하게 잡으면 부담이 된다. embedding(2D 좌표)은 재계산 가능한 파생물이라 "원천(features + 거리/상관 행렬 + universe + 기간)"만 저장하고 좌표·이웃 테이블은 로드 시 재생성하는 편이 변경에 강하다. 좌표를 굳이 저장한다면 "재현용 캐시"로만 취급.

[codex][반영] 1차 관계 정의는 "수익률 상관 기반 거리"로 고정한다. 이유는 스케일 불변이고 설명이 쉬우며, feature 정규화 문제를 baseline에서 줄여주기 때문이다. 이후 변동성/거래량/시가총액 변화 패턴을 섞는 것은 Later의 다중 관계 정의로 보낸다.

[codex][반영] 기간 간 변화는 1차에서 좌표 이동으로 읽지 않는다. 나중에 여러 기간을 다룰 때도 먼저 이웃 집합 변화, 상관/거리 변화, 시가총액 변화율 같은 숫자 변화로 확인한다. 좌표 정렬이나 애니메이션은 Later다.

[codex][반영] 저장은 원천 중심으로 잡는다. 최소 저장 단위는 기간, universe, 데이터 입력 정보, 정렬된 수익률 feature, 상관/거리 행렬, 생성 파라미터다. nearest-neighbor 테이블과 2D 좌표는 재생성 가능한 파생물이며, 저장하더라도 캐시로 취급한다.

## Decisions

[codex] Original Intent는 덮어쓰지 않고 보존한다.

[codex] 지금은 구현보다 방향 정렬이 먼저다. 첫 구현 범위는 관계 벡터 생성, nearest-neighbor 숫자 결과, 2D 시각화, 기간별 스냅샷 저장까지로 제한한다.

[codex] 매매 추천/예측/자동화는 현재 범위에서 제외한다.

[codex] Google Drive에 있는 히스토리컬 데이터는 아직 연결하지 않는다. 사용자가 경로, 형식, 컬럼을 알려준 뒤 데이터 계약을 정한다.

[claude] (아래는 확정이 아니라 사용자/Codex 확인 대기 중인 제안)

[claude][제안] 1차 합격선을 "단일 기간 1개에서 nearest-neighbor 테이블이 직관적으로 납득됨"으로 좁힌다. scatter·시총 overlay·기간 저장은 같은 1차에 포함하되, 기간 간 비교 화면은 다음 단계로 미룬다.

[claude][제안] 1차 거리 정의는 "수익률 상관 기반"을 baseline으로 고정한다(스케일 불변, 설명 쉬움). 다른 관계 정의는 Later.

[claude][제안] 저장은 "원천(기간, universe, features, 거리/상관 행렬)" 중심으로 하고 2D 좌표는 파생/캐시로 취급한다.

[claude][제안] 빈 한국어 섹션(`내가 원하는 것` ~ `나중에 생각해도 되는 것`)은 사용자가 직접 채울 칸으로 보고 에이전트가 메우지 않는다.

[codex][리뷰 반영 판단 - 2026-06-04]

- Apply: 1차 범위를 단일 기간 end-to-end로 좁힌다. 원래 목적의 "티커 관계 덩이"를 먼저 납득 가능하게 만드는 데 직접 필요하다.
- Apply: feature 정규화 위험을 명시하고, baseline은 수익률 상관 기반 거리로 고정한다. 관계가 규모 차이에 먹히는 것을 막는다.
- Apply: 기간 간 변화는 1차에서 좌표가 아니라 숫자로 보장한다. PCA 축 회전/반전 착시를 피한다.
- Apply: 저장은 원천(features + 상관/거리 행렬 + metadata) 중심으로 하고 2D 좌표는 파생/캐시로 둔다. 이후 방식 변경에 강하다.
- Apply: 데이터 계약을 코드 시작 전 gate로 둔다. 데이터 형식과 컬럼을 모르면 loader와 검증 기준이 전부 추측이 된다.
- Apply: 빈 한국어 섹션은 사용자가 직접 채울 칸으로 보존한다.
- Defer: 기간 간 비교 화면, 좌표 정렬, 명시적 군집화, 다중 관계 정의, KR/US 혼합 공간, 인터랙티브 선택 UI는 Later Ideas로 둔다.
- Reject: 현재 Claude 의견 중 기술적으로 반영하지 않을 항목은 없다. 다만 "데이터 계약 답 없이는 코드 보류"는 구현을 멈추기 위한 것이 아니라 잘못된 첫 골격을 피하기 위한 gate로 적용한다.

[codex][다음 구현 계획 - 데이터 계약 확정 후]

1. 데이터 계약을 `IDEAS.md` 또는 별도 짧은 spec에 확정한다. 파일 형식, 컬럼, 조정 가격 여부, universe, 기간, 결측 규칙, 시가총액 처리, 결과물 형태를 고정한다.
2. 단일 기간 loader와 validator를 만든다. 입력 데이터를 ticker/date 기준으로 정렬하고, 기간 내 최소 관측 길이와 결측 규칙을 적용한다.
3. 조정 종가 기준 수익률 matrix를 만들고, 공통 거래일 정렬 후 상관 행렬과 거리 행렬을 계산한다.
4. 각 ticker의 nearest-neighbor 테이블을 생성하고, 거리/상관 값과 함께 저장한다.
5. 보조 2D scatter를 만든다. 첫 버전은 설명 가능한 PCA 또는 단순한 거리 기반 projection을 사용하고, 좌표는 캐시로 취급한다.
6. 결과 저장 포맷을 만든다. 원천 metadata/features/distance를 우선 저장하고, 파생 테이블/좌표는 재생성 가능하게 한다.
7. 작은 fixture 데이터로 loader, 결측 처리, 상관/거리 계산, nearest-neighbor 순서를 검증한다.

[codex][2차 리뷰 반영 판단 - 2026-06-04]

- Apply: scatter는 v1 필수 산출물로 둔다. Original Intent의 "시각적으로도"를 지키기 위한 핵심 출력이다.
- Apply: 시가총액 변화 overlay도 v1 목표로 둔다. 데이터가 없을 때만 fallback으로 비워두고, 이 경우에도 이유를 결과 metadata에 남긴다.
- Apply: 합격 예시 ticker 1~2개를 데이터 계약에 포함한다. "좋은 결과"를 추상적인 느낌이 아니라 관찰 가능한 acceptance로 바꾼다.
- Apply: top-k와 projection seed를 데이터 계약/metadata에 포함한다. 같은 입력에서 같은 이웃과 같은 scatter가 재현되어야 저장이 의미 있다.
- Defer: 추가 gate는 더 늘리지 않는다. 데이터 계약 외 gate를 늘리면 Current Scope보다 절차가 더 커질 수 있다.
- Reject: Later Ideas에서 Current Scope로 되돌릴 항목은 없다. 기간 간 비교 화면, 좌표 정렬, 군집화, 다중 관계 정의, KR/US 혼합, 인터랙티브 UI는 계속 Later다.

[codex][구현 계획 보강 - 데이터 계약 확정 후]

- 데이터 계약에 `acceptance_examples`, `top_k`, `projection_seed`를 포함한다.
- 결과 metadata에는 입력 파일 정보, 기간, universe, 가격 컬럼, market-cap overlay 사용 여부, top-k, projection seed, 생성 시각, 코드 버전 또는 실행 파라미터를 남긴다.
- v1 완료 조건은 nearest-neighbor 테이블, 2D scatter, 저장된 원천/파생 결과가 모두 생성되는 것이다. 시가총액 overlay는 데이터가 있으면 반드시 포함하고, 없으면 fallback 사유를 남긴다.

[codex][데이터 접근 점검 - 2026-06-04]

- `STOCK_DATA_ROOT` 후보는 `/Users/joonyoungjo/Library/CloudStorage/GoogleDrive-jojjoon@gmail.com/내 드라이브/stock_data`다.
- 사용자가 언급한 `docs/mac_mini_data_access_guide_2026-05-29.md`는 현재 동기화된 `stock_data` 루트에 없었다. 대신 `quality_reports/project_status_snapshot_2026-05-29.json`, `quality_reports/mac_mini_duckdb_smoke_2026-06-03.py`, 관련 manifests를 읽기 전용으로 확인했다.
- `STOCK_DATA_ROOT` 환경변수는 현재 shell에 설정되어 있지 않았다. 구현/실행 시에는 명시 인자 또는 환경변수 둘 다 지원하는 편이 좋다.
- 기본 Python과 Codex 번들 Python에는 DuckDB/PyArrow가 없었다. Parquet 점검은 production dependency를 추가하지 않고 `uv run --with duckdb --with pandas --with pyarrow` 일회성 런타임으로 수행했다.
- `meta/derived/backtest_universe.parquet`는 읽혔고, market 분포는 `US=24,429`, `KR=6,783` rows였다.
- 표준 가격 파일은 `meta/derived/backtest_prices_cleaned/us.parquet`, `kr.parquet`다.
- 두 가격 파일 모두 `security_id`, `symbol`, `date`, `adjusted_close`, `close`, `open`, `high`, `low`, `volume`, `market`, `is_sentinel` 등을 포함한다. v1 가격 컬럼 기본값은 `adjusted_close`가 적절하다.
- US 표준 가격: `26,430,915` rows, `6,537` securities/symbols, date range `1972-01-03` to `2026-05-22`.
- KR 표준 가격: Parquet footer 기준 `8,647,367` rows, date range `1988-08-15` to `2026-05-22`. schema는 읽혔지만 full scan count는 Google Drive File Provider `Operation timed out`이 발생했다.
- `meta/derived/global_market_cap_daily/`에는 AU/BR/CA/CH/DE/DK/ES/FI/FR/GB/HK/MX/NL/NO/SE/TW/ZA 파일은 있으나 US/KR 파일은 없었다. 따라서 US/KR v1에서는 시가총액 overlay가 기본 데이터만으로는 비어 있을 수 있고, 이 경우 fallback 사유를 metadata에 남겨야 한다.
- `quality_reports/project_status_snapshot_2026-05-29.json` 기준 unattended 작업은 안전하지 않음(`safe_to_run_unattended=false`)이며 open item은 `us_delisted_cik_mapping_required`, `kr_preferred_manual_listed_date_reconcile`다. v1은 standard cleaned prices 읽기 전용 분석으로 제한한다.

[codex][데이터 계약 현재값 제안]

- `data_root`: 위 `STOCK_DATA_ROOT` 후보 경로.
- `price_dataset`: `meta/derived/backtest_prices_cleaned/{market}.parquet`.
- `id_column`: `security_id`.
- `ticker_display_column`: `symbol`.
- `date_column`: `date`.
- `price_column`: `adjusted_close`.
- `market`: 1차는 `US` 또는 `KR` 중 하나만 선택한다. KR은 full scan timeout이 있어 첫 smoke 실행은 US가 더 안전하다.
- `market_cap_overlay`: US/KR에는 현재 파생 파일이 없으므로 fallback 가능 상태. 별도 시총 데이터 경로가 있으면 v1에 포함한다.
- `top_k`: 기본 `10`.
- `projection_seed`: 기본 `42`.

[codex][3차 리뷰 반영 판단 - 2026-06-04]

- Apply: 원천 중심 저장 원칙을 코드 산출물에 맞춘다. v1은 `universe.csv`, `returns.csv`, `correlations.csv`, `distances.csv`를 `security_id` 기준으로 저장하고, `neighbors.csv`, `scatter.csv`, `scatter.html`은 파생/캐시 산출물로 함께 저장한다.
- Apply: anchor-distance scatter는 유지한다. PCA는 v1 필수가 아니며, 두 번째 anchor는 첫 anchor와 상관이 가장 낮은 종목을 선택해 축 중복을 줄인다.
- Apply: market-cap subset 필터는 `symbol`이 아니라 선택된 `security_id` 기준으로 읽는다. 시총 파일에 `symbol` 컬럼이 없어도 subset 실행이 깨지지 않게 한다.
- Apply: full universe 전 안전장치를 둔다. CLI 기본 `--max-securities=1000`으로 N² 행렬 생성을 막고, metadata에 `matrix_cell_count`, `empty_neighbor_count`, 큰 행렬 경고를 남긴다.
- Apply: HTML tooltip에 `market_cap_change`를 포함해 scatter에서도 overlay 값을 확인할 수 있게 한다.
- Defer: PCA, 기간 간 좌표 정렬, 기간 비교 화면, 명시적 군집화는 계속 Later로 둔다.
- Reject: 시가총액 overlay fallback 자체를 바꾸지는 않는다. US/KR 기본 파생 시총 파일이 없을 수 있으므로, fallback은 데이터 부재를 정직하게 기록하는 v1 동작으로 유지한다.

[codex][4차 리뷰 반영 판단 - 2026-06-04]

- Apply: v1 scope 이탈은 없다는 리뷰 판단을 유지한다. 원천 저장, 이웃 테이블, anchor scatter, market-cap fallback은 Current Scope와 Decisions 안에 있다.
- Apply: 내부 구조를 전면 `security_id` key로 바꾸지는 않고, 먼저 display symbol 중복 가드만 추가한다. 현재 nearest-neighbor 내부 key가 symbol이라 중복 symbol이 있으면 조용히 덮어쓸 수 있으므로, 선택된 universe에서 중복 display symbol을 발견하면 snapshot 생성을 실패시킨다.
- Apply: full universe 전에는 실제 선택 종목 수 N을 먼저 확인하고, `--max-securities`를 함부로 올리지 않는다. N이 수천 단위이면 CSV 행렬 저장/parquet 전환과 이웃 계산 최적화를 별도 결정한 뒤 진행한다.
- Defer: 전면 security_id-key 리팩터, 행렬 parquet 저장, nearest-neighbor 벡터화는 v1 cleanup 또는 다음 단계로 미룬다.
- Reject: PCA와 market-cap fallback 동작은 바꾸지 않는다.

## Open Questions

[codex] 히스토리컬 데이터는 어떤 형식인가? CSV, Parquet, SQLite, 엑셀, 혹은 다른 포맷인가?

[codex] 포함할 티커 universe는 무엇인가? 예: S&P 500, NASDAQ 전체, 보유 관심 종목, 한국/미국 혼합 등.

[codex] 기간 단위는 무엇이 적당한가? 예: 1개월 rolling, 분기별, 반기별, 연도별.

[codex] 처음에 가장 보고 싶은 관계 정의는 무엇인가? 가격 수익률 동행성, 시총 변화 패턴, 변동성/거래량 유사성 중 무엇을 우선할지 정해야 한다.

[codex] 결과물은 먼저 노트북/정적 HTML/간단한 로컬 앱 중 어디로 보는 것이 편한가?

[codex] 시가총액 데이터가 히스토리컬 데이터 안에 이미 있는가, 아니면 따로 가져와야 하는가?

[codex] "좋은 결과"를 판단하는 기준은 무엇인가? 예: 특정 티커를 넣었을 때 직관적으로 납득되는 peer group이 나오는 것, 섹터별 군집이 보이는 것, 기간별 변화가 뚜렷한 것 등.

[claude] (데이터 계약을 막는 추가 질문 — 코드 시작 전에 답이 필요)

[claude] 가격은 분할/배당 조정(adjusted)된 값인가, 미조정인가? 컬럼에 둘 다 있는가?

[claude] 시가총액은 데이터에 레벨로 들어있나, 아니면 종가×상장주식수로 계산해야 하나? 상장주식수 히스토리(자사주/증자 반영)도 있는가? "시총 변화"는 변화율(%)인가 절대 변화인가?

[claude] universe 규모는 대략 몇 개 티커인가? (N² 행렬 부담과 직결)

[claude] 결측/휴장/짧은 히스토리는 어떻게 다루나? 기간 내 최소 관측 길이 기준을 둘까, 아니면 결측 채우기를 할까?

[claude] universe가 기간마다 바뀌어도(상폐/신규상장) 되는가, 아니면 모든 기간에 공통으로 존재하는 티커만 비교하나?

[claude] KR과 US가 섞여 있나? 섞여 있다면 한 공간에서 비교할지, 시장별로 분리할지(통화·거래일 캘린더 차이 때문에 1차는 분리 권장).

[claude] 거리는 비대칭 nearest-neighbor를 그대로 보여줄지, 상호 최근접만 강조할지?

[codex][필수 데이터 계약 - 코드 시작 전 필요]

[codex] 1차 구현을 시작하려면 아래 답이 필요하다. 이 질문들은 Current Scope의 단일 기간 end-to-end를 구현하기 위한 최소 계약이다.

- 데이터 파일 위치와 형식은 무엇인가? 예: local CSV/Parquet/SQLite/Excel. Google Drive 자동 접근은 1차에서 하지 않는다.
- 필수 컬럼 이름은 무엇인가? 최소 `ticker`, `date`, 조정 가격 또는 종가가 필요하고, 시가총액 overlay를 하려면 `market_cap` 또는 계산 가능한 컬럼이 필요하다.
- 가격은 분할/배당 조정된 adjusted 값인가? 둘 다 있으면 1차는 adjusted를 쓴다.
- 첫 universe와 시장은 무엇인가? 1차는 KR/US 혼합 없이 한 시장 또는 명확한 한 티커 목록으로 제한한다.
- 첫 단일 기간은 언제부터 언제까지인가?
- 결측/짧은 히스토리는 어떻게 처리할까? 기본 제안은 기간 내 공통 거래일 기준으로 정렬하고, 최소 관측 길이 미달 ticker는 제외하는 것이다.
- 시가총액 변화는 데이터에 이미 있나, 아니면 첫 버전에서는 overlay를 비워두고 관계 테이블부터 만들까?
- 첫 결과물은 CLI 산출물, 정적 HTML, 노트북 중 무엇이 가장 편한가?

[codex][2차 리뷰 반영 - 추가 데이터 계약]

- 합격 예시 ticker 1~2개는 무엇인가? 예: 같은 업종의 대형주처럼 peer가 직관적으로 기대되는 종목.
- nearest-neighbor는 top-k 몇 개를 볼까? 기본 제안은 `top_k=10`.
- projection에 난수가 들어갈 경우 seed는 무엇으로 고정할까? 기본 제안은 `projection_seed=42`.
- 시가총액 overlay는 데이터가 있을 때 v1에 포함한다. 데이터가 없으면 overlay fallback을 허용하되, "없어서 제외됨"을 metadata와 결과 요약에 남긴다.

[codex][데이터 확인 후 남은 필수 질문]

- 첫 v1 실행 market은 `US`로 진행해도 되는가? KR도 가능하지만 Google Drive full scan timeout을 피하려면 처음은 US가 안전하다.
- 첫 단일 기간은 무엇으로 할까? 기본 제안은 `2024-01-01` to `2026-05-22`.
- acceptance example ticker 1~2개는 무엇으로 할까? 기본 제안은 US라면 `AAPL`, `MSFT` 또는 `JPM`, `BAC`처럼 peer가 직관적인 묶음이다.
- 첫 결과물은 CLI 산출물 + 정적 HTML scatter로 진행해도 되는가?
- US/KR 시총 overlay용 별도 파일이 있는가? 없으면 v1은 overlay fallback을 metadata에 남긴다.
- full universe로 확장하기 전에 실제 N 상한을 어디로 둘까? 기본 가드 `--max-securities=1000`을 넘기려면 먼저 예상 행렬 크기와 저장 포맷을 확정해야 한다.

[codex][4차 리뷰 후 full universe 전 운영 결정]

- 실제 full universe N은 얼마인가? 선택 market, 기간, 최소 관측일, symbol filter를 적용한 뒤의 `security_count`를 먼저 확정한다.
- full universe에 정당한 duplicate display symbol이 있을 때 어떻게 처리할까? 현재 v1은 조용한 덮어쓰기를 막기 위해 hard-fail한다. full 실행 전에는 dedup, symbol disambiguation, security_id-key 리팩터 중 하나를 결정해야 한다.
- N이 O(N²) 파이썬 루프와 N x N CSV 저장의 안전 구간을 넘으면 어떻게 할까? 큰 universe에서는 matrix parquet 저장과 nearest-neighbor 계산 최적화를 먼저 결정한 뒤 `--max-securities`를 올린다.

[codex][US full universe 실행 결과 - 2026-06-04]

- Preflight 기준: `US`, `1972-01-03` to `2026-05-22`, `adjusted_close`, `min_observations=60`, symbol filter 없음. 실제 분석 universe는 `security_count=6453`, `return_date_count=13756`, `matrix_cell_count=41,641,209`, duplicate display symbol은 `0`이었다.
- 첫 full 실행에서 `min_observations`로 탈락한 security가 scatter anchor 후보에는 남아 `KeyError`가 나는 버그가 드러났다. 수정 후에는 symbol map을 실제 `returns.columns` universe로 좁혀서 neighbor/scatter/universe가 같은 security set을 보게 했다.
- 전체 산출물은 `outputs/relation_snapshot_us_full_1972-01-03_2026-05-22/`에 생성됐고 총 용량은 약 `2.1GB`였다. 주요 파일 크기는 `correlations.csv 800MB`, `distances.csv 749MB`, `returns.csv 556MB`, `neighbors.csv 5.9MB`, `scatter.html 2.7MB`다.
- 결과 해석 주의: 가격 파일 전체를 그대로 사용하고 최소 overlap이 `60`이라 AAPL/MSFT의 top neighbors에 `BST`, `QQQX`, `BSTZ` 같은 fund/특수 종목이 많이 섞였다. "궁금해서 전체 보기" 산출물로는 유효하지만, 직관적 equity peer map을 보려면 standard equity universe 필터와 더 높은 pairwise overlap 기준을 다음 단계에서 검토해야 한다.

[codex][standard universe acceptance run - 2026-06-04]

- Claude 리뷰 판단에 따라 `backtest_universe.parquet`의 기존 컬럼만 사용해 `--universe-scope standard`를 추가했다. 필터 조건은 `market`, `is_in_standard_universe=true`, `is_etf=false`이며, 새 ETF/fund 분류기는 만들지 않았다.
- CLI 기본 `min_observations`는 기본 기간(`2024-01-01` to `2026-05-22`)에 맞춰 `400`으로 올렸다. 짧은 기간이나 실험 run에서는 명시 인자로 낮출 수 있다.
- Acceptance 재실행: `US`, `2024-01-01` to `2026-05-22`, `universe_scope=standard`, `min_observations=400`, `top_k=10`. 실제 `security_count=5726`, `return_date_count=612`, output size 약 `1.3GB`.
- 결과: `BAC`와 `JPM`은 은행/금융 peer가 상위에 나와 직관적이었다. 예: `BAC -> WFC, C, HBAN, PNC, CFG`, `JPM -> GS, BAC, C, WFC, MS`.
- 남은 문제: `AAPL`과 `MSFT`는 여전히 `CSQ`, `SPXX`, `ETY`, `QQQX`, `BST` 같은 closed-end/overwrite fund류가 상위에 남았다. `backtest_universe`의 standard membership은 ETF는 제외하지만 CEF/우선주/특수 종목을 모두 common equity로 분리해주지는 않는다.
- 다음 결정: v1 acceptance를 더 밀려면 새 분류기를 만들기보다 먼저 기존 데이터 계약 안에서 "common operating equity" universe를 어떻게 정의할지 정해야 한다. 예: 사용자가 제공하는 ticker allowlist, 기존 universe 컬럼 조합, 또는 liquidity/top-turnover 같은 단순 기준. 새 섹터 라벨링, fund classifier, 군집화는 Later 경계로 둔다.

[codex][security classification filter run - 2026-06-04]

- 기존 데이터에 `security_classification.parquet`가 있고, 여기에는 `type` 컬럼이 있었다. 값 분포는 US 기준 `Common Stock`, `Preferred Stock`, `FUND`, `ETF`, `Warrant`, `Notes`, `Unit` 등이다.
- Claude 리뷰 기준에 따라 새 classifier를 만들지 않고, 기존 `type` 컬럼만 사용하는 `--security-type-scope common-stock`을 추가했다. 이 필터는 `security_classification.type = 'Common Stock'`인 ticker만 가격 데이터에 통과시킨다.
- Acceptance 재실행: `US`, `2024-01-01` to `2026-05-22`, `universe_scope=standard`, `security_type_scope=common-stock`, `min_observations=400`, `top_k=10`. 실제 `security_count=5073`, `return_date_count=612`, output size 약 `1.0GB`.
- 결과 개선: `type=FUND`인 `CSQ`, `SPXX`, `ETY`, `QQQX`, `BST` 등은 제거됐다. `MSFT` 상위에는 `NOW`, `AMZN`, `CDNS`, `META`, `CRM` 같은 operating equity가 섞이기 시작했고, `JPM/BAC`는 계속 직관적인 금융 peer를 유지했다.
- 남은 한계: `GAM`, `TY`, `NBXG`, `CET`, `STEW` 같은 일부 closed-end fund는 원천 데이터에서 `type='Common Stock'`, `eodhd_industry='Asset Management'`로 들어와 여전히 남는다. 이를 이름/산업 문자열로 제거하는 것은 새 fund classifier에 가까우므로 v1에서는 하지 않는다.
- v1 판단: 관계 엔진과 기존 데이터 계약 필터는 동작한다. 다만 "common operating equity only"를 엄밀히 만족하려면 원천 데이터에 별도 CEF/운영회사 구분 컬럼이 필요하며, 그 분류기/라벨링 작업은 Later로 둔다.

[codex][v1 acceptance close - 2026-06-04]

- Claude 리뷰 판단에 따라 v1을 여기서 닫는다. `--universe-scope standard`와 `--security-type-scope common-stock`은 기존 데이터 컬럼만 사용하는 데이터 계약 필터로 Current Scope 안에 있다.
- Final acceptance artifact는 `outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400/`다. 핵심 metadata: `security_count=5073`, `return_date_count=612`, `matrix_cell_count=25,735,329`, output size 약 `1.0GB`.
- Acceptance 판단: `JPM/BAC`는 금융 peer가 직관적이고, `MSFT`는 `NOW`, `AMZN`, `CDNS`, `META`, `CRM` 등 operating equity가 섞이며 개선됐다. 따라서 관계 엔진은 다중 섹터에서 검증됐다.
- 알려진 한계: `AAPL`에는 `GAM`, `TY`, `NBXG` 같은 잔여 CEF가 남는다. 이들은 원천 `security_classification.type='Common Stock'`으로 들어와 있으므로 파이프라인 오류가 아니라 원천 분류 한계다.
- transparency metadata를 추가했다: active universe 내 `type='Common Stock'`이면서 `eodhd_industry='Asset Management'`인 후보 수와 샘플을 기록한다. final run 기준 count는 `223`이다. 이 값은 제외 필터가 아니라 잔여 한계 표시다.
- `Asset Management` 산업 전체 제외는 하지 않는다. `APO`, `ARES`, `BAM` 같은 실제 operating equity도 함께 제거될 수 있어 universe를 정화하는 게 아니라 훼손한다.
- 다음 방향은 CEF를 더 추격하는 것이 아니라 기간별 스냅샷 저장 후 기간 간 변화를 숫자로 비교하는 것이다. 좌표 이동 비교/PCA/군집화/새 fund classifier는 Later에 둔다.

[codex][period comparison milestone - 2026-06-04]

- Next step은 `compare_snapshot_directories` / `compare_cli`로 구현했다. 저장된 snapshot 디렉터리들의 `neighbors.csv`만 읽어 인접 기간 top-k 이웃의 유지/진입/이탈과 거리/상관 변화를 쓴다. 전체 `distances.csv` 행렬은 다시 읽지 않는다.
- 출력물은 `summary.json`, `neighbor_changes.csv`, `distance_changes.csv`다. 이는 North Star의 "기간별 저장 후 흐름 보기"에 직접 닿지만, 좌표 이동 비교나 PCA 정렬은 여전히 Later다.
- 실제 비교 run은 `standard + common-stock` 기준으로 세 구간을 연결했다: `2020-01-01` to `2021-12-31` (`security_count=3776`), `2022-01-01` to `2023-12-31` (`security_count=4604`), `2024-01-01` to `2026-05-22` (`security_count=5073`).
- 비교 artifact는 `outputs/relation_snapshot_us_period_comparison_2020_2026_top10/`다. 대상 symbol은 `AAPL`, `MSFT`, `JPM`, `BAC`, `NVDA`, `XOM`, `UNH`, top-k는 `10`이다.
- 결과 감각: `BAC`는 특히 안정적이었다. `2022-2023`에서 `2024-2026`으로 갈 때 top-10 neighbor Jaccard가 `0.6667`이고, `C`, `CFG`, `FITB`, `HBAN`, `JPM`, `PNC`, `RF`, `WFC`가 유지됐다.
- `MSFT`, `AAPL`은 변화가 컸다. `2022-2023`에서 `2024-2026`으로 갈 때 Jaccard가 둘 다 `0.1111`이었다. `MSFT`는 `AMZN`, `CDNS`, `CRM`, `CRWD`, `META`, `NOW`, `SAP`, `TY`가 새로 들어왔고, `AAPL`은 잔여 CEF/semiconductor 쪽이 섞였다.
- `UNH`는 유지된 healthcare peer의 distance가 크게 멀어진 사례가 많았다. 예: `UNH-MOH` distance는 `0.3399`에서 `0.6472`로 증가했다.
- 주의: 이 비교는 top-k table 기반의 숫자 비교다. top-k 밖에 있는 pair의 실제 거리 변화는 보지 않는다. 필요하면 나중에 selected symbols에 대해서만 `distances.csv` 행을 부분적으로 읽는 기능을 추가할 수 있지만, v1 다음 단계에서는 지금 방식이 충분히 가볍고 목적에 맞다.

[codex][period comparison review integration - 2026-06-04]

- Claude review apply/defer/reject: top-k `neighbors.csv` 기반 비교는 Apply. 전체 `distances.csv` 보강은 Defer. non-adjacent 전용 로직은 Reject because 두 snapshot만 인자로 넘기면 이미 가능하다. HTML 비교 리포트는 Defer because Current Scope에서 기간 간 비교 화면은 미뤄둔 상태다.
- Apply한 핵심 지적: 기간별 universe가 `3776 -> 4604 -> 5073`으로 달라지므로 `entered/exited`가 관계 변화와 universe membership 변화를 섞어 보일 수 있다.
- 수정: `neighbor_changes.csv`에 `old_symbol_in_universe`, `new_symbol_in_universe`를 추가했고, `distance_changes.csv`에 `old_neighbor_in_universe`, `new_neighbor_in_universe`를 추가했다. `universe.csv`가 없는 snapshot은 빈 값으로 남긴다.
- 수정: 양쪽 기간 모두 neighbor union이 비어 있는 경우 `jaccard_similarity`를 `1.0`이 아니라 빈 값으로 둔다. 이는 "완벽히 안정"이라는 오해를 피하기 위한 것이다.
- `summary.json`에는 `universe_presence_note`를 추가해 entered/exited가 관계 변화, universe 변화, 또는 둘 다를 의미할 수 있음을 명시했다.
- Lazy import는 유지한다. 기존 top-level export 호환성을 보존하면서 compare CLI의 pandas-free 실행 문제를 테스트로 막고 있다. top-level re-export 제거는 Later cleanup 후보로 둔다.

[codex][period comparison text insights - 2026-06-04]

- Claude 추가 리뷰 없이 진행했다. 이유: 새 분석축/화면이 아니라 기존 `neighbor_changes.csv`와 `distance_changes.csv`를 사람이 읽기 쉽게 요약하는 얇은 Markdown 산출물이기 때문이다.
- `compare_cli`는 이제 `insights.md`를 함께 쓴다. 섹션은 `Most Stable Neighbor Sets`, `Most Changed Neighbor Sets`, `Largest Stayed Distance Changes`, `Universe Cautions`다.
- 이 작업은 HTML 비교 화면이 아니다. Current Scope에서 미뤄둔 "기간 간 비교 화면"을 만들지 않고, CSV/JSON 숫자 비교의 읽기 편의만 보강했다.
- 실제 artifact: `outputs/relation_snapshot_us_period_comparison_2020_2026_top10/insights.md`.
- 첫 관찰: `BAC`는 가장 안정적인 축에 있고, `AAPL/MSFT`는 2022-2023에서 2024-2026으로 넘어가며 top-k 구성이 크게 바뀐다. `UNH`는 유지된 healthcare peer들과의 distance가 크게 멀어진 사례가 많다.
- `Universe Cautions`는 membership 변화 때문에 entered/exited가 관계 변화로만 해석되면 안 되는 항목을 표면화한다. 예: `ECAT`, `NBXG`는 2020-2021에는 universe에 없고 이후 들어온 entered neighbor로 표시된다.

[codex][non-adjacent direct comparison - 2026-06-04]

- Claude가 지적한 대로 non-adjacent 비교를 위한 새 로직은 필요 없다. 비교하고 싶은 두 snapshot만 `--snapshot`으로 넘기면 된다.
- 실제로 `2020-01-01` to `2021-12-31` snapshot과 `2024-01-01` to `2026-05-22` snapshot만 직접 비교했다. Artifact는 `outputs/relation_snapshot_us_period_comparison_2020_2026_direct_top10/`다.
- 결과: `BAC`가 가장 안정적이었다. top-10 Jaccard는 `0.5385`이고 `C`, `FITB`, `JPM`, `PNC`, `TFC`, `USB`, `WFC`가 유지됐다.
- 결과: `AAPL`은 top-10 Jaccard가 `0.0000`으로, 2020-2021 top neighbors가 2024-2026 top neighbors와 하나도 겹치지 않았다. 단 2024-2026 쪽에는 잔여 CEF와 semiconductor peer가 섞여 있으므로 해석에 주의한다.
- 결과: `MSFT`는 `CDNS`만 유지되어 Jaccard `0.0526`이었다. 새 이웃은 `AMZN`, `CRM`, `CRWD`, `META`, `NOW`, `SAP` 등이었다.
- 결과: `UNH`는 `CI`, `CNC`, `ELV`, `HUM`, `MOH`가 유지됐지만 stayed distance가 크게 멀어졌다. 예: `UNH-CI` distance는 `0.1805`에서 `0.6414`로 증가했다.
- `Universe Cautions`에는 `NBXG`, `ALHC`, `PRVA`, `OXY-WT`처럼 첫 기간에는 universe 밖이었다가 이후 들어온 entered neighbor가 드러난다. 이 항목은 관계 변화와 universe membership 변화를 구분해서 읽어야 한다.

[codex][ticker timeline artifact - 2026-06-04]

- Claude 추가 리뷰 없이 진행했다. 이유: 새 로직이 아니라 기존 adjacent/direct comparison CSV를 종목별로 재배치한 읽기용 Markdown artifact이기 때문이다.
- Artifact: `outputs/relation_snapshot_us_period_ticker_timeline_2020_2026_top10.md`.
- 이 파일은 `AAPL`, `BAC`, `JPM`, `MSFT`, `NVDA`, `UNH`, `XOM`별로 adjacent 변화, direct 2020-2021 to 2024-2026 변화, stayed distance move를 한곳에 묶는다.
- 읽기 감각: `BAC`는 peer set 안정성이 높고, `AAPL/MSFT/NVDA`는 장기 direct 비교에서 top-k neighbor turnover가 크다. `UNH`는 peer 이름 일부가 유지되지만 distance 자체는 크게 멀어지는 쪽이다.
- 주의: 이 artifact도 여전히 top-k neighbor 비교만 요약한다. 전체 pair distance 변화, 좌표 이동, PCA/군집화, HTML 비교 화면은 만들지 않았다.

[codex][all-symbol comparison pass - 2026-06-04]

- Claude 추가 리뷰 없이 진행했다. 이유: 새 코드나 새 분석축이 아니라 기존 `compare_cli`를 symbol filter 없이 실행해 전체 universe의 top-k 변화 분포를 보는 작업이기 때문이다.
- Adjacent all-symbol artifact: `outputs/relation_snapshot_us_period_comparison_2020_2026_all_symbols_top10/`. `symbols_count=5085`, `neighbor_change_rows=10170`, `distance_change_rows=160897`, size 약 `22MB`.
- Direct all-symbol artifact: `outputs/relation_snapshot_us_period_comparison_2020_2026_direct_all_symbols_top10/`. `symbols_count=5079`, `neighbor_change_rows=5079`, `distance_change_rows=81308`, size 약 `11MB`.
- 읽기용 summary artifact: `outputs/relation_snapshot_us_period_global_highlights_2020_2026_top10.md`.
- 분포 감각: both-present 기준 adjacent Jaccard median은 `0.1111`, direct Jaccard median은 `0.0526`이었다. 즉 top-10 neighbor set은 전체적으로 꽤 많이 바뀐다.
- 안정적인 그룹은 경제적으로 납득되는 cluster가 많았다. 예: hotel REITs, homebuilders, Argentina ADRs, regional banks, miners/uranium names.
- 가장 많이 바뀐 이름들은 소형/이벤트성/저유동/데이터 품질 민감 종목이 많이 섞인다. 따라서 Jaccard `0.0` 자체를 곧바로 투자/경제 해석으로 연결하지 않는다.
- Universe caution도 크다. Adjacent all-symbol 비교에는 target universe change `1335`, neighbor universe change `8362`가 있었고, direct all-symbol 비교에는 target universe change `1309`, neighbor universe change `9322`가 있었다.
- 다음 정렬된 방향: 전체를 더 복잡하게 군집화하기보다, 의미 있는 몇 개 경제 그룹을 골라 기존 CSV/Markdown artifact로 기간 변화를 검토한다. PCA, clustering, sector labeling, UI screen은 계속 Later다.

[codex][economic group review - 2026-06-04]

- Claude 추가 리뷰 없이 진행했다. 이유: 새 분류기나 새 섹터 체계를 만드는 것이 아니라, all-symbol pass에서 관찰된 안정 cluster를 사람이 읽기 좋은 watchlist 형태로 정리하는 작업이기 때문이다.
- Artifact: `outputs/relation_snapshot_us_period_group_review_2020_2026_top10.md`.
- 검토 그룹: hotel REITs, homebuilders, Argentina ADRs, regional banks, gold/silver miners, uranium names.
- 안정성이 가장 선명한 그룹은 hotel REITs와 homebuilders였다. Hotel REITs direct Jaccard summary는 mean `0.7071`, median `0.6667`, within-group neighbor share mean `0.9909`였다. Homebuilders direct Jaccard summary는 mean `0.7122`, median `0.6667`, within-group neighbor share mean `0.8909`였다.
- Argentina ADRs도 매우 안정적이었다. Direct Jaccard summary mean은 `0.7466`, median은 `0.8182`, within-group neighbor share mean은 `0.9273`이었다.
- Regional banks는 경제적으로 coherent하지만 direct Jaccard mean `0.4579`로 위 그룹보다 변화가 컸다. 그래도 `HBAN`, `CFG`, `RF` 등은 같은 regional bank peer를 많이 유지했다.
- Uranium names는 direct Jaccard mean `0.4711`로 중간 수준이지만, stayed distance가 크게 가까워진 pair가 많았다. 예: `UROY-DNN`, `UROY-UEC`, `UROY-NXE`, `UROY-CCJ`가 모두 closer 방향이었다.
- 주의: 이 그룹은 관찰된 stable cluster를 수작업으로 묶은 watchlist다. 유지보수되는 sector taxonomy나 classifier가 아니며, 이를 자동 분류 기능으로 일반화하는 것은 Later다.

[codex][analysis index - 2026-06-04]

- Claude 추가 리뷰 없이 진행했다. 이유: 새 분석이나 코드 변경이 아니라, 지금까지 생성된 snapshot/comparison/summary artifact를 찾기 쉽게 정리하는 안내 문서이기 때문이다.
- Added `ANALYSIS_INDEX.md`.
- 이 문서는 먼저 볼 artifact, v1 acceptance snapshot, 기간별 comparison artifact, 해석 주의, 재생성 명령, 다음 aligned moves를 한곳에 정리한다.
- Scope guard: PCA, clustering, sector labeling, CEF classifier, interactive comparison UI는 계속 Later로 둔다.

[codex][final review integration and v1.5 close - 2026-06-04]

- Claude review apply/defer/reject: `insights.md`는 기계 생성 Markdown twin으로 Apply, all-symbol comparison pass는 기존 CLI 실행으로 Apply, `ANALYSIS_INDEX.md`는 navigation aid로 Apply.
- Defer: group-review는 수기 analyst note로만 둔다. 코드/metadata/CLI로 승격하지 않는다. 이것을 자동화하면 sector labeling/taxonomy Later 경계를 넘는다.
- Defer: market-cap change numbers in period comparison. 이는 Original Intent에 직접 닿는 유일하게 정렬된 다음 후보지만, 현재 v1/v1.5 마감에는 필수 아님.
- Reject now: group-review Markdown 생성기 CLI, maintained sector taxonomy, clustering, PCA/coordinate alignment, interactive comparison UI.
- 수정: generated `insights.md`에 `Limits` 섹션을 고정했다. 포함 내용은 top-k only, entered/exited의 universe membership conflation, residual source classification issue다.
- 수정: 수기 Markdown artifact(`global_highlights`, `ticker_timeline`, `group_review`) 상단에 manual analyst note / not generated truth or taxonomy / fixed date and parameters / limitations를 명시했다.
- 수정: `ANALYSIS_INDEX.md`에 group-review 코드화 금지와 v1/v1.5 close 방향을 명시했다.
- 최종 방향: 여기서 v1/v1.5를 닫는다. 다음 작업은 사용자가 명시적으로 새 목표를 선택할 때까지 추가 분석 자동화가 아니라, 현재 artifact를 읽고 해석하는 단계로 본다.

[codex][market-cap period comparison feasibility audit - 2026-06-04]

- Claude 추가 리뷰 없이 진행했다. 이유: 새 알고리즘이나 새 분석축이 아니라, Original Intent에 적힌 시가총액 변화 overlay/비교가 현재 데이터 계약에서 가능한지 확인하는 읽기 전용 감사였기 때문이다.
- 확인: `meta/derived/global_market_cap_daily/`와 `meta/derived/global_shares_outstanding_events/`에는 AU/BR/CA/CH/DE/DK/ES/FI/FR/GB/HK/MX/NL/NO/SE/TW/ZA 파일만 있고, 현재 v1/v1.5가 사용한 US/KR 파일은 없었다.
- 확인: `quality_reports/global_market_cap_daily_2026-06-03.*`와 `quality_reports/global_shares_outstanding_events_2026-06-03.*`도 같은 시장 목록만 보고한다. 이 레이어는 preview이며 universes/factor gates를 바꾸지 않는다고 적혀 있다.
- 확인: 현재 CLI는 `global_market_cap_daily/{market}.parquet`가 있을 때만 `market_cap`을 읽고, 파일이 없으면 `market_cap_overlay=missing`으로 degrade한다. 따라서 US snapshot의 시총 fallback은 코드 경로 착오가 아니라 데이터 가용성 문제다.
- 결정: US/KR 기간 비교에 시총 변화 숫자를 붙이는 작업은 현재 파생 데이터만으로는 보류한다. EODHD API 호출, 새 수집, Google Drive 대량 수정, ad hoc fundamentals 조합 계산은 하지 않는다.
- Next data contract: US/KR용 `global_market_cap_daily/{market}.parquet` 또는 동등한 일별 시총/주식수 히스토리가 생기면, 기간 비교에 시총 변화율 delta를 추가하는 것이 Original Intent와 가장 정렬된 다음 확장이다.

[codex][repo handoff hygiene close - 2026-06-04]

- Claude 추가 리뷰 없이 진행했다. 이유: 새 관계 정의, 새 분석축, 새 데이터 계약이 아니라 v1/v1.5를 재사용하기 위한 repo handoff와 CLI/test 위생 정리였기 때문이다.
- Added `README.md`: 데이터 계약, snapshot 생성 명령, period comparison 명령, 해석 한계, 검증 명령을 루트에서 바로 볼 수 있게 했다. `ANALYSIS_INDEX.md`는 생성된 artifact 지도 역할로 유지한다.
- 테스트 환경 위생: `duckdb`가 없는 기본 Python에서는 parquet CLI 테스트가 skip되고, `uv run --with duckdb --with pandas --with pyarrow --with pytest python -m pytest -v`에서는 CLI 포함 전체 테스트가 실행된다.
- CLI 위생: snapshot CLI `--help`는 pandas 없이도 열린다. 실제 snapshot build에는 pandas/duckdb/pyarrow가 필요하므로, 누락 시 실행 방법을 안내한다.
- CLI 위생: compare CLI는 snapshot이 2개 미만인 validation error를 traceback 대신 한 줄 메시지로 보여준다.
- Scope guard: 이 정리는 Current Scope를 넓히지 않는다. PCA, coordinate alignment, clustering, taxonomy, CEF classifier, interactive UI, group-review automation은 계속 Later다.

[codex][v1.5 manual readout close - 2026-06-04]

- Claude review integration: Apply trimming tracked readout logs; defer ignored local readout artifacts as harmless; keep `ANALYSIS_INDEX.md` as a minimal navigation aid; reject further generic readout passes.
- Detailed manual analysis now lives only in ignored local artifacts under `outputs/`: `relation_snapshot_us_reading_guide_2020_2026.md`, `relation_snapshot_us_period_readout_synthesis_2020_2026.md`, `relation_snapshot_us_period_phase_transition_readout_2020_2026.md`, `relation_snapshot_us_visual_and_readout_audit_2020_2026.md`, plus the earlier `global_highlights`, `group_review`, and `ticker_timeline` notes.
- Tracked docs should record direction, scope guards, and gates; they should not duplicate artifact-level findings, watchlist readouts, compactness numbers, or narrative analysis.
- Stop line: v1/v1.5 already has single-period snapshots, scatter, top-k period comparison, direct/adjacent readouts, phase-transition readout, visual audit, and a reading guide. Do not add more generic readout automation or analysis passes.
- Next aligned code milestone is only market-cap change numbers in period comparison after US/KR market-cap history exists in the agreed derived data contract.
- Continue only for a specific user question over existing artifacts, or when the market-cap data gate is satisfied.

[claude][generic ego network decision - 2026-06-04]

- Apply: add a ticker-agnostic single-symbol ego network view that accepts any center symbol as an argument and redraws existing top-k `neighbors.csv` relationships with optional stayed/entered/exited colors from existing comparison outputs.
- Keep relationship meaning fixed as return-correlation distance. Price/return is an overlay only; market cap remains data-gated; BTC/external assets, 3D, coordinate animation, PCA alignment, taxonomy/classifier work, and all-data vector mixing remain Later/Reject-now.

[codex][global map data layer audit - 2026-06-04]

- Claude review integration: Apply audit-first before a global map; defer 2.5D/global rendering until the layer contract is clear; reject all-data vector mixing, sector taxonomy/classifier, external reference feeds, and ad hoc market-cap reconstruction.
- Read-only audit target: `outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400/` plus existing `stock_data/meta/derived` parquet files. No API calls, data collection, or Google Drive writes.

| Layer | Existing source | Status | Decision |
| --- | --- | --- | --- |
| Relationship | snapshot `neighbors.csv` | Available: `5,073` nodes, `50,730` top-10 edges | Apply as the only distance/edge meaning: return-correlation distance |
| Return | snapshot `returns.csv` | Available: `612` return dates for period-return calculation | Apply as node color/tooltip overlay only |
| Identity + sector/industry | `security_classification.parquet`, `backtest_universe.parquet` | Available for all `5,073` snapshot tickers; sector/industry mostly populated | Apply as tooltip/filter/overlay only; do not name clusters or build taxonomy |
| Liquidity/volume | `backtest_prices_cleaned/us.parquet`, `backtest_universe.parquet` | Available/calculable: price file has `volume`; universe has `avg_turnover_1y` | Apply as nullable overlay candidate only |
| Volatility | snapshot returns or cleaned prices | Calculable from existing returns/prices | Apply as nullable overlay candidate only |
| Market cap | `global_market_cap_daily/{market}.parquet` | Missing for US/KR in current derived data | Data-gated; keep nullable, do not reconstruct from fundamentals/shares ad hoc |
| External references | BTC/rates/commodities/etc. | Not audited now | Defer to Later; no external data integration in this milestone |

- Draft node schema: `symbol`, `security_id`, nullable `name`, `type`, `sector`, `industry`, `primary_sector`, `period_return`, `volatility`, `avg_volume`, `avg_turnover`, `market_cap`, `market_cap_change`, visual-only `community_id`, layout `x`, `y`.
- Draft edge schema: `source_symbol`, `target_symbol`, `rank`, `correlation`, `distance`.
- Next safe milestone: a single-snapshot global relationship map may use only the above contract. Relationship remains return-correlation; other fields are overlays. Period animation, 3D, PCA/coordinate alignment, cluster naming, and broad interactive reporting remain Later.

[codex][single snapshot global map prototype decision - 2026-06-04]

- Claude review integration: Apply fixed-frame global map direction, but keep timeline as a later step until a single global map exists. Defer annual re-layout, animation, 3D, community coloring, cluster naming, taxonomy, and all-data vector mixing.
- Implementation scope: one saved snapshot, all nodes, top-k edges, numpy-only deterministic layout, seed/iteration metadata, node color as period return, optional tooltip overlays from a symbol-keyed metadata CSV. No new production dependency is added to `pyproject.toml`.
- Stop line: node positions are a fixed reference frame, not semantic axes and not time movement. Future timeline must reuse one frozen layout and change only edges, colors, and tooltips.

[codex][global map prototype close - 2026-06-04]

- Claude review integration: Apply accepting the single-snapshot global map prototype. The v2 layout is no longer a collapsed blob; it is a broad relationship web, which may be the honest shape of a 5k-node top-10 return-correlation graph.
- Defer-by-choice: fixed-frame timeline is now unblocked but should be a separate user decision, not an automatic next step. Options are timeline small-multiples, wait for US/KR market-cap data, or stop and use the prototype.
- Reject now: further layout grinding, graph-layout libraries, community detection, UMAP/nonlinear embedding, annual re-layout, 3D, taxonomy, and market-cap reconstruction. The layout is frozen for this prototype milestone.

[codex][market-cap raw feasibility correction - 2026-06-04]

- Claude review integration: Apply the correction that market cap is an unfilled Original Intent pillar, not a discarded overlay. Earlier gating was correct for missing US/KR derived market-cap parquet, but too strong if read as "the raw ingredients do not exist."
- Read-only audit: no API calls, no Google Drive writes, no price join, no market-cap calculation, and no map overlay. Full JSON field coverage scan was stopped because Google Drive raw-file hydration was too slow for a short audit; use this as feasibility, not production validation.

| market | universe basis | universe_n | raw fundamentals match | representative field check | currency | verdict |
| --- | --- | ---: | ---: | --- | --- | --- |
| US | 2024-2026 standard common-stock snapshot | 5,073 | 5,073 (100.0%) | AAPL/MSFT/MU have positive `Highlights.MarketCapitalization`, positive `SharesStats.SharesOutstanding`, annual shares, and quarterly shares | USD | `pipeline-milestone-needed` |
| KR | `backtest_universe` standard, non-ETF | 2,195 | 2,195 (100.0%) | 005930.KO/005380.KO have positive `Highlights.MarketCapitalization`, positive `SharesStats.SharesOutstanding`, annual shares, and quarterly shares | KRW | `pipeline-milestone-needed` |

- Decision: US/KR market-cap is not impossible; raw fundamentals appear broadly matchable by symbol/ticker, but raw files do not provide the vetted `security_id`-keyed, PIT/date-aligned derived layer needed for period-change interpretation.
- Stop line: do not mix market cap into relationship distance; do not show period market-cap change until split adjustment, share-date alignment, currency handling, and security-id join policy are verified in a dedicated derived-layer milestone. A current-size overlay may be considered later only if clearly labeled as raw/current/as-of-fetch and backed by full field coverage validation.

[codex][market-cap field coverage sample - 2026-06-04]

- Claude review integration: Apply field-coverage first; defer current-size overlay until field coverage is explicit; write the period-change contract now but defer the build; keep timeline as the next low-risk visual milestone after this gate.
- Method: read-only file-name match across the universe, then deterministic 25-file field sample per market with per-file timeout. This is an estimate, not production validation; full raw JSON coverage scan is too slow from Google Drive in the current environment.

| market | universe_n | raw match | readable sample | `MarketCapitalization` > 0 | `SharesOutstanding` > 0 | quarterly shares > 0 | zero shares | currency | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| US | 5,073 | 5,073 (100.0%) | 25/25 | 100.0% | 100.0% | 100.0% | 0 | USD | current-size overlay likely feasible after full validation |
| KR | 2,195 | 2,195 (100.0%) | 24/25 | 100.0% | 87.5% | 75.0% | 3 | KRW | current-size overlay likely feasible; period-change needs stricter quality flags |

- Current-size overlay decision: Defer implementation until a full or cached coverage validation can mark missing/zero values explicitly. If implemented, label it as raw/current/as-of-fetch, not period-aligned market cap.
- Period-change minimum contract: join by `security_id`, not ticker; use PIT share dates; keep price/share adjustment basis consistent; keep KRW and USD separate and prefer percent change; write zero/missing as null with a `quality_flag`; output `period_start`, `period_end`, `security_id`, `mcap_start`, `mcap_end`, `mcap_change_pct`, `quality_flag`.
- Priority ladder: field coverage gate -> current-size overlay only if validated and clearly labeled -> fixed-frame timeline -> period market-cap-change derived layer as a separate milestone. Market cap remains overlay-only and never enters the return-correlation distance.

[codex][current market-cap size overlay decision - 2026-06-04]

- Claude review integration: Apply current-size market-cap overlay as in-scope; absorb coverage validation into the build metadata; defer separate coverage CLI and period market-cap-change pipeline; reject market cap in distance calculations.
- Implementation scope: raw `Highlights.MarketCapitalization` -> symbol-keyed node metadata CSV -> global map node size/tooltip only. Node color remains period return; edges remain saved top-k return-correlation neighbors.
- Non-negotiable guards: missing/zero market cap is rendered as a neutral outline and counted separately; log-scale sizing branches before zero/missing; raw market-cap size is meaningful only within one market/currency map; HTML and metadata label the size as raw/current/as-of-fetch, not period-aligned market-cap change.
- Stop line: no price x shares calculation, PIT share alignment, split-adjustment handling, currency comparison, new API call, Google Drive write, 3D/animation, clustering, or taxonomy in this milestone.

[codex][current market-cap overlay run close - 2026-06-05]

- Overnight read-only run completed: generated `outputs/relation_snapshot_us_market_cap_metadata_2024_2026.csv` and `outputs/relation_snapshot_us_global_map_2024-01-01_2026-05-22_top10_mcap/global_map.html`.
- Actual US overlay coverage: `5,073` nodes, `4,680` positive current market caps (`92.25%` coverage), `119` missing fields, `274` raw-file timeouts, `0` zero market caps, currency `USD`.
- Browser check: rendered HTML loads, shows the raw/current/as-of-fetch warning, missing/zero outline legend, and a nonblank full-market canvas. Relationship still uses saved top-k return-correlation edges only.
- Remaining risk: timeout rows are treated as missing overlay data, so coverage may improve if Google Drive raw files are locally hydrated or the metadata build is rerun with a longer timeout. This does not affect neighbor distance or layout.

[codex][global map filter-focus decision - 2026-06-05]

- Claude review integration: Apply filter/focus before 3D. The crowding problem is density, not just 2D projection, so sector/industry filters and an edge-strength threshold are the next low-risk step; true 3D/Three.js remains Later.
- Implementation scope: add client-side sector filter, industry filter, and minimum edge-correlation threshold to the existing global map HTML. These controls hide nodes/edges visually only; they do not recompute the layout, rewrite edges, name clusters, or change the return-correlation distance.
- Defer: volatility/liquidity overlays, 2.5D decorative view mode, fixed-frame timeline, and period market-cap-change pipeline. Reject now: all-data vector mixing, taxonomy/classifier, community labels, annual re-layout, coordinate alignment, 3D animation, and new heavy visualization dependencies.

[codex][sector-market-cap filter artifact close - 2026-06-05]

- Combined existing sector/industry node metadata with current market-cap metadata into `outputs/relation_snapshot_us_node_metadata_sector_mcap_2024_2026.csv`; no new upstream data extraction or classifier.
- Regenerated `outputs/relation_snapshot_us_global_map_2024-01-01_2026-05-22_top10_sector_mcap/global_map.html`. Metadata reports `17` sector values, `153` industry values, `4,680/5,073` positive current market caps (`92.25%`), and `50,730` saved top-k edges.
- Browser check: sector and industry dropdowns are populated, edge-threshold control is present, raw/current/as-of-fetch market-cap label remains visible, and there are no console errors. Filters remain visual-only lenses, not cluster labels.

[codex][fixed-frame global timeline decision - 2026-06-05]

- Apply the next milestone as a fixed-frame small-multiple timeline: reuse one existing `global_layout.csv` as the reference frame, then render 2020-2021, 2022-2023, and 2024-2026 snapshots side by side.
- Relationship meaning stays return-correlation distance only. Each frame changes only saved top-k edges, period-return node color, and tooltip values. Sector/industry filters and edge-threshold controls remain visual-only lenses.
- Missing universe membership is explicit: nodes from the reference layout remain visible at fixed positions as neutral missing markers when absent from a frame.
- Stop line: no annual re-layout, no coordinate alignment, no animation, no 3D, no community/taxonomy naming, no market-cap period-change inference, and no new production dependency.

[codex][rolling descriptive structure scanner decision - 2026-06-05]

- Claude review integration: Apply descriptive rolling structure study, but keep predictive lead-lag/backtest as a separate gated milestone. Brightline: describing structure-at-t is in scope; aligning structure-at-t with return-at-t+1 is out of scope here.
- Implementation scope: read saved relationship snapshots and existing sector/industry metadata, then group by an existing label to summarize mean period return, internal cohesion, top-percentile strong-edge counts, absolute `corr>=0.5` counts, cross-group strong links, and deltas between adjacent windows.
- Method guard: top-percentile edges are the primary regime-relative lens; fixed `corr>=0.5` is secondary because broad market correlation regimes move. Overlapping rolling windows are not independent samples.
- Stop line: no recommendation/watch-candidate wording, no future-return alignment, no strategy backtest, no taxonomy/classifier, no group naming from detected clusters, no new relationship definition, no map/animation/3D in this milestone.

[codex][rolling 6-month summary-only run - 2026-06-05]

- Applied the storage decision: monthly 6-month rolling windows are computed in memory from price parquet and only summary CSV/Markdown/JSON artifacts are written. Full per-window `correlations.csv`/`distances.csv` are intentionally not saved by default because they would be tens of GB across 2020-2026.
- Direct rolling mode uses existing `backtest_prices_cleaned`, `backtest_universe`, and `security_classification` parquet files read-only. `security_classification` supplies existing sector/industry group-by labels; it is not a classifier, taxonomy, or cluster naming layer.
- Generated local ignored artifact: `outputs/relation_snapshot_us_sector_structure_rolling_6m_2020_2026/` (`71` windows, about `4.4M`). Output remains descriptive only and does not align structure-at-t with future returns.

[codex][rolling heatmap report decision - 2026-06-05]

- Claude data-review integration: Apply sector cohesion, sector return, and cross-sector connection heatmaps only if they include same-window market baseline/regime caveats. Defer ticker-level rolling scanner. Reject 3D/global animation and lead-lag/predictive backtest.
- Implementation scope: a static mechanical HTML twin of existing rolling scanner tables. It visualizes internal cohesion vs baseline, period return vs baseline, and selected cross-sector top-percentile links. It adds no event narrative, recommendation language, future-return alignment, taxonomy, classifier, or new relationship definition.
- Generated local ignored artifact: `outputs/relation_snapshot_us_sector_structure_rolling_6m_2020_2026/rolling_structure_report.html` (about `904K`).

[codex][threshold sweep decision - 2026-06-05]

- Claude data-review integration: Apply fixed threshold sweep as descriptive zoom levels, but make baseline-normalized ratio the main cross-window metric. Raw `corr>=0.5/0.6/0.7` counts are market-regime sensitive and must be labeled as regime gauges, not sector-specific structure by themselves.
- Implementation scope: summary CSV + mechanical HTML for thresholds `0.5`, `0.6`, `0.7`, plus same-window market strong-edge density and group/cross density divided by that baseline. No ticker-level scanner, threshold global maps, predictive lead-lag, recommendation language, 3D, or animation.
- Generated local ignored artifact: `outputs/relation_snapshot_us_threshold_sweep_6m_2020_2026/` (about `4.4M`). First market-baseline read: `corr>=0.5` median `2.26%` / max `27.58%`; `corr>=0.7` median `0.17%` / max `4.77%`, confirming that fixed thresholds are very different zoom levels.

[codex][threshold sweep regime chart update - 2026-06-05]

- Claude data-review integration: Apply market regime density line chart as required context before reading sector/cross-sector threshold ratios. Max/median gaps show that every fixed threshold jumps in stress regimes, so the report should lead with market density before any sector table.
- Updated local ignored artifact: `threshold_sweep_report.html` now starts with threshold-by-time market strong-edge density lines for `0.5`, `0.6`, and `0.7`. This is still descriptive only and adds no new relationship definition or predictive alignment.

[codex][threshold sweep ratio guard update - 2026-06-05]

- Claude data-review integration: Apply the normalized-ratio caveat that small market baselines and small group sample sizes can make ratios noisy. The report should shade high market-density windows and show raw edge counts plus member/pair counts beside normalized ratios.

[codex][window length sweep decision - 2026-06-05]

- Claude review integration: Apply changing only the rolling window length as the safest way to inspect bigger/slower structure. Defer wider threshold grids, longer history, industry granularity, and top-k/edge coverage expansion.
- Implementation scope: reuse the descriptive threshold sweep with `window_months_values` such as `6,12`, keeping time range, thresholds, group label, and relationship definition fixed. Outputs remain summary-only; full per-window matrices are not saved. A 3-month window is optional later because it needs a lower minimum-observation contract and is noisier.
- Stop line: one-axis comparison only, no predictive lead-lag, no recommendation/watch wording, no pattern-mining for the "best" window, no taxonomy/classifier, and no 3D/animation.

[codex][window flow readout decision - 2026-06-05]

- Claude data-review integration: Apply a small durable/transient readout from existing 6/12-month threshold-window sweep CSVs. Defer new thresholds, 3-month windows, industry granularity, ticker-level scans, and lead-lag research.
- Implementation scope: classify guarded rows as `durable` when they appear in the 12-month view, or `transient` when they appear in the 6-month view outside the durable set. This is a reading aid over same-window structure, not subtraction, prediction, or recommendation.

[codex][component structure decision - 2026-06-05]

- Claude methodology review integration: Apply threshold-based connected components as the safest first step for emergent relationship groups. Defer community detection, membership time tracking, and lead-lag flow.
- Implementation scope: for each rolling window and threshold, compute unnamed connected components with stdlib union-find, then write frame-level component counts and capped component detail rows. Component ids are local `C01`-style labels, not taxonomy or stable identities.
- Stop line: no sector naming, no community detection, no lead-lag, no prediction/recommendation wording, no full matrix storage, and no new dependency.

[codex][component flow summary decision - 2026-06-05]

- Claude review integration: after reading current component results, apply adjacent-window membership overlap as the smallest safe way to describe maintain/split/merge/new/ended structure. Reject lead-lag, prediction, recommendation, and stable cluster identity.
- Implementation scope: write `component_flow_summary.csv` from in-memory component memberships while computing the same rolling windows. Do not store full matrices or full membership files; output only summary transition rows.
- Stop line: flow rows are descriptive same-history overlap only. They are not signals, not "follow-on" movement, and not evidence that one component causes or predicts another.

[codex][component dashboard decision - 2026-06-05]

- Claude review integration: apply a 0.7-focused descriptive dashboard/table to satisfy "see it at a glance" without crossing into prediction. Reject future-return alignment, predictive scoring, and "follow-on" language.
- Implementation scope: join existing component detail, frame, and flow CSVs into `component_dashboard.csv` and a static HTML table. Include same-window return as a separate column and adjacent-window overlap status as structure continuity only.
- Stop line: dashboard rows do not compare component-at-t with return-at-t+1; they are not signals, candidates, recommendations, or stable cluster identities.

[codex][component pair summary decision - 2026-06-06]

- Claude review integration: apply same-window component-to-component relationship summaries as a descriptive upper-level view of the emergent groups. Reject directional "propagation", lead-lag, predictive score, or recommendation framing.
- Implementation scope: define dense components at one threshold such as `0.7`, then summarize pairs of those components inside the same window with mean/median cross-correlation and lower-threshold cross-edge density such as `0.5`, normalized against the market baseline. Store summary CSV/HTML only.
- Stop line: component pair rows are undirected same-window co-movement. Cross edges must use a threshold below the component definition threshold; component ids remain window-local and must not be treated as stable identities across time.

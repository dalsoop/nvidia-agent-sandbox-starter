# NVIDIA Agent Sandbox Starter

build.nvidia.com의 Nemotron 모델로 도구를 호출하는 최소 에이전트를
[NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell) 샌드박스 안에서 실행하는 스타터입니다.

코드는 짧게 두고, README에 적은 동작은 모두 테스트나 실측 기록으로 확인할 수 있게 했습니다.
NVIDIA의 공식 프로젝트가 아니며, NVIDIA와 제휴 관계도 없습니다.

## 구성

| 경로 | 내용 |
|---|---|
| `agent/` | 표준 라이브러리만 쓰는 tool-calling 에이전트. 외부 패키지 의존성이 없습니다 |
| `skills/` | [Agent Skills](https://docs.nvidia.com/skills) 형식의 `SKILL.md` 예시 |
| `policy/openshell-policy.yaml` | OpenShell 정책 (`version: 1` 스키마) |
| `Dockerfile` | `openshell sandbox create --from .`로 빌드하는 샌드박스 이미지 |
| `tests/` | 오프라인 테스트, 정책 검사, OpenShell E2E |
| `docs/openshell.md` | OpenShell 설치·실행 절차와 이 저장소에서 실측한 결과 |

## 동작 방식

에이전트는 모델에게 작업을 주고, 모델이 요청한 도구를 실행한 뒤 결과를 다시 넘기는 과정을 반복합니다.
모델이 도구 호출 없이 답하면 끝납니다. 결과는 JSON 한 개로 표준 출력에 씁니다.

| 도구 | 설명 |
|---|---|
| `list_files`, `read_file`, `write_file` | 워크스페이스 안의 파일만 다룹니다. 워크스페이스 밖을 가리키는 경로와 심볼릭 링크는 거부합니다 |
| `load_skill` | 설치된 Skill의 전체 지시문을 읽습니다. 시스템 프롬프트에는 Skill의 이름과 설명만 들어갑니다 |

모델 호출 경로는 실행 환경에 따라 나뉩니다.

| 환경 | 엔드포인트 | API 키 |
|---|---|---|
| 호스트 (`NVIDIA_API_KEY` 설정) | `https://integrate.api.nvidia.com/v1` | 요청 헤더로 전송 |
| OpenShell 샌드박스 | `https://inference.local/v1` | 보내지 않음. OpenShell이 샌드박스 밖에서 주입 |

실패를 성공으로 보고하지 않습니다. 종료 코드는 다음과 같습니다.

| 코드 | 의미 |
|---|---|
| 0 | 성공 |
| 1 | `--selfcheck` 결과 샌드박스 격리가 확인되지 않음 |
| 2 | 설정 오류 (예: 키 없이 NIM 엔드포인트 지정) |
| 3 | 모델 호출 실패 (429·500·502·503·504는 최대 3회 재시도한 뒤) |
| 4 | 단계 수 한도 초과 |
| 5 | 모델이 빈 답을 반환 |

## 호스트에서 실행

Python 3.12 이상과 [uv](https://docs.astral.sh/uv/)가 필요합니다.

```sh
uv sync
cp .env.example .env          # NVIDIA_API_KEY에 build.nvidia.com 키를 넣습니다
mkdir -p workspace
uv run --env-file .env python -m agent "Give me an inventory report of this workspace." --workspace workspace
```

호스트 실행에는 샌드박스가 없습니다. 도구의 경로 검사만 파일 접근을 막으므로, 신뢰할 수 없는 작업은 OpenShell 안에서 실행하세요.

## OpenShell 샌드박스에서 실행

설치, provider 등록, 실행 명령은 [docs/openshell.md](docs/openshell.md)에 있습니다.
요약하면 게이트웨이에 NVIDIA provider와 추론 모델을 등록한 뒤 이 저장소를 이미지로 빌드해 실행합니다.

```sh
openshell sandbox create --from . --policy policy/openshell-policy.yaml --no-keep -- \
  python3 -m agent "Give me an inventory report of this workspace."
```

### 정책이 막는 것

`policy/openshell-policy.yaml`은 다음을 요구합니다.

- `/usr`, `/lib`, `/etc`, `/opt` 등은 읽기 전용이고, 쓰기는 `/sandbox`와 `/tmp`만 가능합니다 (Landlock).
- 이미지의 non-root 사용자 `sandbox`(uid 10001)로 실행합니다.
- `network_policies`가 비어 있으므로 외부 연결은 모두 거부됩니다. 모델 호출은 `inference.local`로만 나갑니다.

### 격리를 직접 확인하기

`python3 -m agent --selfcheck`는 금지된 동작을 실제로 시도하고 결과를 JSON으로 보고합니다.
시스템 경로 쓰기, 정책에 없는 `/var/tmp` 쓰기, 외부 HTTPS 연결이 모두 실패하고, 워크스페이스 쓰기는 성공하고,
환경 변수에 실제 NVIDIA 키가 없어야 `"sandboxed": true`가 됩니다.

`/var/tmp`는 일반 권한으로는 누구나 쓸 수 있는 경로입니다. 그래서 이 항목은 UNIX 권한이 아니라 Landlock이 실제로 적용되었는지를 가려냅니다.
일반 Docker 컨테이너나 호스트에서 실행하면 `"sandboxed": false`가 나옵니다.

## 보장하지 않는 것

- 모델 출력의 정확성. Skill은 지시문일 뿐 결과를 검증하지 않습니다.
- 개인정보 마스킹, 프롬프트 인젝션 탐지. 이 저장소에는 해당 기능이 없습니다.
- Landlock이 없는 커널. 정책의 `landlock.compatibility`가 `best_effort`이므로 커널이 지원하지 않으면 파일시스템 제한 없이 실행됩니다. 이 경우 `--selfcheck`가 `false`를 보고합니다.

## 테스트

```sh
uv run pytest -v                                   # 오프라인. 네트워크와 API 키가 필요 없습니다
PATH="/path/to/openshell-prover:$PATH" uv run pytest tests/test_policy.py -v
OPENSHELL_E2E=1 uv run pytest -m e2e -v            # openshell CLI와 실행 중인 게이트웨이가 필요합니다
```

- 오프라인 테스트는 127.0.0.1에 띄운 가짜 OpenAI 호환 서버로 HTTP 경로까지 검사합니다.
- `test_policy.py`는 NVIDIA의 정책 파서(`openshell-prover`)로 정책 파일을 검사합니다. 파서가 없으면 skip합니다.
- E2E의 permissive 정책 테스트는 대조군입니다. 약하게 만든 정책에서도 `sandboxed: true`가 나오면 selfcheck가 아무것도 측정하지 않는다는 뜻이므로 실패합니다.

2026-09-24에 macOS(colima Docker, OpenShell 0.0.116)에서 E2E까지 포함해 38개 테스트가 3회 연속 통과했습니다.
실측 결과와 이 환경에서 만난 함정은 [docs/openshell.md](docs/openshell.md)에 있습니다.

## 모델

호스트에서의 기본 모델은 `nvidia/nemotron-3-ultra-550b-a55b`이고 `--model` 또는 `LLM_MODEL`로 바꿉니다.
OpenShell 안에서는 게이트웨이의 inference 설정(`openshell inference set --model`)이 모델을 정하므로 `--model`은 무시됩니다.
출력의 `served_model`은 실제로 응답한 모델, `requested_model`은 요청한 모델입니다.
2026-09-24에 이 저장소 코드로 확인한 내용입니다. 호스팅 모델은 예고 후 내려갈 수 있습니다.

| 모델 | 확인 내용 |
|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b` | 호스트에서 Skill 작업(도구 5회)을 17초에 완료. 같은 날 오후 NVIDIA 쪽 과부하(503)로 여러 차례 실패 |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | OpenShell 샌드박스에서 `inference.local`로 3단계 작업 완료. 작성 내용의 품질은 낮음 |
| `nvidia/nemotron-3-super-120b-a12b` | 동작하지만 응답에 `deprecation: 2026-10-03T09:00:00Z` 헤더가 붙음 |

build.nvidia.com 무료 API는 개발용이며 한도 수치를 공개하지 않습니다. 짧은 시간에 요청을 몰아 보내면 429가 반환되므로
테스트는 순차로 실행하세요.

## 라이선스

[Apache License 2.0](LICENSE)

# OpenShell에서 실행하기

OpenShell v0.0.116 기준입니다. 명령과 플래그는 `openshell <명령> --help`로 확인한 것만 적었습니다.
공식 문서: <https://docs.nvidia.com/openshell/>

## 1. 설치

OpenShell은 Linux, macOS(Apple Silicon), Windows WSL 2를 지원합니다.
Docker 드라이버를 쓰려면 Docker Engine 또는 Docker Desktop 28.0 이상이 필요합니다.

공식 설치 스크립트:

```sh
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh
```

스크립트를 실행하지 않으려면 [릴리스](https://github.com/NVIDIA/OpenShell/releases)의 패키지를 직접 설치합니다.
macOS에서는 릴리스에 포함된 Homebrew formula(`openshell.rb`)가 CLI, 게이트웨이, VM 드라이버를 설치하고
게이트웨이를 `brew services`로 `127.0.0.1:17670`에 띄웁니다. 이 formula는 Command Line Tools가 최신이어야 설치됩니다.

```sh
openshell status   # "Connected"와 버전이 보이면 됩니다
```

## 2. 추론 provider 등록

샌드박스 안의 코드는 API 키를 갖지 않습니다. 키는 게이트웨이의 provider에만 저장되고,
샌드박스에서 `https://inference.local`로 보낸 요청에 OpenShell이 키를 붙여 전달합니다.

```sh
export NVIDIA_API_KEY=nvapi-...          # 현재 셸에만. 파일에 저장하지 마세요
openshell provider create --name nvidia --type nvidia --credential NVIDIA_API_KEY
openshell inference set --provider nvidia --model nvidia/nemotron-3.5-lightning-30b-a3b
```

`inference set`은 저장하기 전에 모델 엔드포인트를 실제로 호출해 검증합니다. 모델이 과부하(503)이면 실패하므로 잠시 뒤 다시 실행합니다.
샌드박스 안에서는 이 설정이 모델을 정하므로 에이전트의 `--model`은 무시됩니다.

## 3. 실행

```sh
# 격리 확인 (모델 호출 없음)
openshell sandbox create --from . --policy policy/openshell-policy.yaml --no-keep --no-tty -- \
  python3 -m agent --selfcheck

# 에이전트 실행
openshell sandbox create --from . --policy policy/openshell-policy.yaml --no-keep --no-tty -- \
  python3 -m agent "Create notes.md with three short ideas for a hackathon demo, then read it back."
```

`--from .`은 이 저장소의 `Dockerfile`을 로컬 Docker로 빌드한 뒤 샌드박스를 만듭니다.

## 실측 기록

2026-09-24, macOS 26.5.2 (Apple Silicon), colima Docker Engine 28.4.0, OpenShell 0.0.116, Docker 드라이버.

**격리 (`--selfcheck`)**

| 정책 | `/usr` 쓰기 | `/var/tmp` 쓰기 | `example.com` | 키 | 결과 |
|---|---|---|---|---|---|
| `policy/openshell-policy.yaml` | EACCES | EACCES | 프록시가 `403 Forbidden` | 없음 | `sandboxed: true`, uid 10001 |
| `tests/fixtures/permissive-policy.yaml` | EACCES | 쓰기 성공 | HTTP 200 | 없음 | `sandboxed: false` |

샌드박스 로그에 `Landlock filesystem sandbox available [abi:v4]`, `Landlock ruleset built [rules_applied:9]`가 기록되었습니다.
permissive 정책은 대조군입니다. 이 정책에서 `false`가 나오므로 selfcheck가 정책 차이를 실제로 측정한다는 것을 확인했습니다.

**추론 (`inference.local`)**

- `nvidia/nemotron-3.5-lightning-30b-a3b`: 성공. `write_file`, `read_file`을 거쳐 3단계에 종료, `served_model`에 이 모델이 기록됨.
  도구 호출 절차는 지켰지만 작성한 내용의 품질은 낮았습니다.
- `nvidia/nemotron-3-ultra-550b-a55b`: 한 번 성공(1441ms). 이후 같은 날 NVIDIA 쪽이 `503 Service temporarily overloaded`를 반환해 실패했습니다.
- 샌드박스 로그에는 `ALLOWED inference.local:443`와 `API:INFERENCE Success|Failure <model>`이 요청마다 남습니다 (`openshell logs <이름>`).

**테스트**: `OPENSHELL_E2E=1`과 `openshell-prover`를 PATH에 둔 상태에서 `uv run pytest` 38개가 3회 연속 통과했습니다.

## 알려진 함정

| 증상 | 원인과 대처 |
|---|---|
| `failed to connect to local Docker daemon ... /var/run/docker.sock` | `--from` 빌드는 docker context를 따르지 않습니다. colima 등에서는 `DOCKER_HOST=unix://$HOME/.colima/default/docker.sock`을 지정합니다 |
| 게이트웨이가 다른 Docker 소켓을 고름 | 게이트웨이 설정(`gateway.toml`)의 `[openshell.gateway] compute_drivers = ["docker"]`와 `[openshell.drivers.docker] socket_path`로 고정합니다 |
| `Network namespace creation failed ... trusted ip helper not found` | 이미지에 `iproute2`가 없습니다. supervisor는 이미지 안의 `ip`와 nftables를 씁니다 |
| `sandbox exec`에서 `No module named agent` | `exec`와 `connect` 세션은 이미지의 `ENV`를 물려받지 않습니다. 그래서 이 이미지는 `PYTHONPATH` 대신 `.pth` 파일을 씁니다 |
| `supervisor session not connected`, `sandbox is not ready` | `sandbox create -- <명령>`이 supervisor 연결보다 먼저 실행되는 경우가 있습니다. 다시 실행하거나, `--detach -- sleep 600`으로 띄운 뒤 `sandbox exec`를 씁니다 (E2E 테스트가 이 방식입니다) |
| `name exceeds maximum length (20 > 19)` | 샌드박스 이름은 19자까지입니다 |
| 샌드박스 안에서 HTTP 500 `Internal server error` | 업스트림 모델이 과부하(503)일 때 라우터가 500으로 전달합니다. 에이전트는 500도 재시도합니다 |
| `docker-credential-osxkeychain` not found | `~/.docker/config.json`의 `credsStore`가 설치되지 않은 도우미를 가리킵니다. 도우미를 설치하거나 설정을 고칩니다 |

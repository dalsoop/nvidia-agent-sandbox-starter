# NVIDIA Agent Sandbox Starter

[![NVIDIA OpenShell](https://img.shields.io/badge/NVIDIA-OpenShell%20Standard-76B900?logo=nvidia&logoColor=white)](https://build.nvidia.com)
[![Security Policy](https://img.shields.io/badge/Security-Default--Deny-red)](./policy.yaml)
[![Tests](https://img.shields.io/badge/Tests-16%20Passed-brightgreen)](./tests/test_sandbox_security.py)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

> **NVIDIA AI Agent Hackathon Reference Implementation**  
> 자율 AI 에이전트(Autonomous AI Agent)를 위한 **NVIDIA OpenShell 표준 기반 고격리 샌드박스 런타임** 및 **보안 감사 자동화 테스트베드**.

---

## 1. 해커톤 프로젝트 개요 (Overview)

### 1.1 배경 및 문제 정의 (The Problem)
자율 에이전트가 소프트웨어 엔지니어링, 데이터 분석, 금융 업무 등 고도화된 도구(Tool Calling, Shell Execution, Code Interpreter)를 사용할 때 다음과 같은 치명적인 보안 위협이 발생합니다:
1. **시스템 훼손 및 RCE**: 에이전트가 호스트 OS 파일시스템(`/etc`, `/bin`, `/root`)을 파괴하거나 권한 상승(Privilege Escalation)을 시도.
2. **비인가 데이터 유출 (Exfiltration)**: 프롬프트 인젝션 또는 악의적 코드에 의해 민감 데이터(API Key, PII)가 공격자의 C2 서버로 전송.
3. **무제한 네트워크 호출**: 제어되지 않은 토큰 소비 및 유해한 엔드포인트 무단 접속.

### 1.2 솔루션: 3단계 심층 방어 아키텍처 (3-Tier Defense-in-Depth)
`nvidia-agent-sandbox-starter`는 NVIDIA OpenShell 표준을 준수하여 **컨테이너 격리**, **선언적 보안 정책(Declarative Security Policy)**, **L7 추론 가드레일 프록시**의 3중 방어막을 제공합니다.

---

## 2. 시스템 아키텍처 (System Architecture)

```mermaid
flowchart TD
    subgraph Host ["Host Environment / Orchestrator"]
        Compose["Docker Compose / Container Runtime"]
        PolicyFile["policy.yaml (Declarative Rules)"]
    end

    subgraph Sandbox ["Isolated Container Perimeter (UID 1000, read_only: true)"]
        Agent["Autonomous Agent (agent/main.py)"]
        TmpFS["tmpfs /tmp (noexec, nosuid)"]
        WorkDir["/workspace (rw volume)"]
        SysFS["/etc, /usr, /bin (Read-Only Root)"]

        Agent -->|Allowed I/O| WorkDir
        Agent -.->|BLOCKED (PermissionError)| SysFS
        Agent -->|Temp Cache| TmpFS
    end

    subgraph NetworkIsolation ["Network Boundary (internal: true)"]
        EgressFilter{"Egress Filter: Default-Deny"}
        Agent -.->|BLOCKED: Direct Egress| ExtNet["Direct Internet (1.1.1.1, etc.)"]
        Agent -->|Allowed Route: Port 8080| Gateway
    end

    subgraph L7Proxy ["NVIDIA OpenShell L7 Gateway"]
        Gateway["Proxy & Guardrails Engine"]
        PIIFilter["PII Masking Filter"]
        PromptGuard["Prompt Injection Detection"]
        TokenBudget["Token & Rate Limiter"]

        Gateway --> PIIFilter
        PIIFilter --> PromptGuard
        PromptGuard --> TokenBudget
    end

    subgraph AuthorizedEndpoints ["Authorized Model Gateways (build.nvidia.com)"]
        NIM["NVIDIA NIM / NeMo Microservices"]
        OpenAI["Approved LLM APIs (api.openai.com)"]
    end

    TokenBudget -->|Forward Verified| NIM
    TokenBudget -->|Forward Verified| OpenAI
```

---

## 3. 핵심 보안 격리 계층 (Security Tiers)

| 계층 (Layer) | 방어 메커니즘 | 구현 내용 및 설정 |
|:---|:---|:---|
| **OS / Runtime** | Least Privilege & Hardening | Non-Root UID `1000:1000`, `read_only: true`, `cap_drop: ALL`, `no-new-privileges: true` |
| **Filesystem** | Strict Boundary & Traversal Defense | 시스템 디렉터리 수정 불가, `/workspace` 격리 볼륨만 쓰기 허용, Path Traversal(`../`) 차단 |
| **Network L4** | Zero-Trust Default-Deny | Docker 브리지 네트워크 `internal: true`, 미인가 외부 IP/포트 소켓 연결 즉시 차단 |
| **Network L7** | OpenShell Inference Gateway | 인가된 모델 엔드포인트(`build.nvidia.com`, `integrate.api.nvidia.com`)만 화이트리스트 라우팅 |
| **AI Safety** | Model Guardrails | PII(이메일, API 키) 마스킹, 프롬프트 인젝션 패턴 탐지 및 차단, JSON 감사 추적(Audit Log) |

---

## 4. 디렉토리 구조 (Repository Layout)

```text
nvidia-agent-sandbox-starter/
├── Dockerfile                  # Ubuntu 24.04 기반 Hardened 샌드박스 이미지 정의
├── docker-compose.yml          # read_only, internal network, cap_drop 샌드박스 명세
├── policy.yaml                 # NVIDIA OpenShell 선언적 보안 정책 (Egress, Filesystem, Syscalls)
├── requirements.txt            # Python 필수 의존 패키지 (pytest, pydantic, httpx, pyyaml)
├── config/
│   ├── openshell.json          # OpenShell L7 프록시 게이트웨이 및 가드레일 설정
│   ├── gateway.yaml            # 게이트웨이 라우팅 및 업스트림 매핑
│   └── sandbox.yaml            # 컨테이너 런타임 제약 설정
├── agent/
│   └── main.py                 # 격리 샌드박스 내부에서 안전하게 실행되는 자율 에이전트 샘플
├── tests/
│   └── test_sandbox_security.py# 해커톤 심사용 3대 보안 감사 자동화 테스트 스위트
└── README.md                   # 프로젝트 개요, 아키텍처 및 실행 가이드 (본 문서)
```

---

## 5. 빠른 시작 및 로컬 실습 (Getting Started)

### 5.1 사전 요구사항 (Prerequisites)
- Docker 24.0+ 및 Docker Compose v2.20+
- Python 3.12+ (호스트에서 직접 테스트 실행 시 `uv` 또는 `pytest`)

### 5.2 컨테이너 샌드박스 빌드 및 기동
```bash
# 1. 샌드박스 이미지 빌드
docker compose build

# 2. 고격리 샌드박스 백그라운드 기동
docker compose up -d

# 3. 샌드박스 상태 점검
docker compose ps
```

### 5.3 샌드박스 내부 자율 에이전트 실행
샌드박스 내부에서 안전하게 작업을 수행하고 구조화된 JSON 결과물을 출력합니다:

```bash
# 기본 자율 태스크 실행
docker compose exec agent-sandbox python3 agent/main.py \
  --task "Analyze financial dataset and compute risk score"

# 오프라인/모의 검증 모드 실행
docker compose exec agent-sandbox python3 agent/main.py \
  --mock \
  --task "Run automated security compliance verification"
```

**에이전트 실행 출력 예시 (Structured JSON Output):**
```json
{
  "status": "success",
  "agent_id": "nvidia-openshell-agent-v1",
  "task": "Run automated security compliance verification",
  "elapsed_ms": 2.45,
  "security_audit": {
    "uid": 1000,
    "gid": 1000,
    "is_root": false,
    "read_only_root_filesystem": true,
    "workspace_writable": true,
    "policy_detected": true
  },
  "artifacts": {
    "plan_path": "/workspace/agent_plan.md",
    "result_path": "/workspace/result.json"
  },
  "output": {
    "task": "Run automated security compliance verification",
    "solution": "[OpenShell Verified Response] Successfully processed task inside sandbox...",
    "execution_verified": true
  },
  "trace": [
    {"action": "verify_sandbox_security", "status": "passed"},
    {"action": "safe_write_file", "status": "success"},
    {"action": "request_model_inference", "status": "success"},
    {"action": "safe_write_file", "status": "success"}
  ]
}
```

---

## 6. 보안 심사 자동화 스크립트 실행 (Security Audit Suite)

본 프로젝트는 해커톤 심사위원이 단 한 줄의 명령으로 보안 격리성을 검증할 수 있는 **자동화 감사 스위트**를 제공합니다.

### 6.1 샌드박스 컨테이너 내부 실행 (Official Audit)
```bash
docker compose exec agent-sandbox pytest tests/test_sandbox_security.py -v
```

### 6.2 호스트 로컬 즉시 검증 (Host Fast Evaluation)
`uv`를 활용하여 별도 venv 구성 없이 즉시 실행 가능합니다:
```bash
uv run --with pytest --with pyyaml pytest tests/test_sandbox_security.py -v
```

---

## 7. 해커톤 심사 평가 체크리스트 (Judging Criteria Checklist)

심사위원 평가 항목별 검증 결과 및 증적 위치:

| 평가 항목 | 심사 기준 | 검증 상태 | 증적 및 테스트 코드 |
|:---|:---|:---:|:---|
| **Test 1: 파일시스템 변조 방어** | `/etc`, `/bin`, `/root` 등 시스템 보호 영역 쓰기 시도 차단 및 경로 탈출(`../`) 차단 | **PASS** | [`tests/test_sandbox_security.py:40`](tests/test_sandbox_security.py#L40) (`TestSystemFileTamperingPrevention`) |
| **Test 2: 비인가 외부 통신 차단** | `default_action: deny` 정책 검증 및 임의의 외부 IP/DNS 직접 소켓 연결 차단 | **PASS** | [`tests/test_sandbox_security.py:120`](tests/test_sandbox_security.py#L120) (`TestUnauthorizedNetworkEgressBlocked`) |
| **Test 3: 인가 엔드포인트 & 작업 완수** | NVIDIA NIM / NeMo 화이트리스트 라우팅 정합성 및 에이전트 End-to-End 작업 완결 | **PASS** | [`tests/test_sandbox_security.py:180`](tests/test_sandbox_security.py#L180) (`TestAuthorizedModelEndpointAndTaskSuccess`) |
| **재현성 (Reproducibility)** | 단일 Compose 명령으로 즉시 배포 및 감사 테스트 재현 가능 여부 | **PASS** | `docker-compose.yml`, `Dockerfile` 완전 자동화 |
| **감사 투명성 (Audit Traceability)** | 에이전트의 모든 의사결정, 도구 실행, 추론 단계가 타임스탬프와 함께 JSON으로 추적 | **PASS** | `agent/main.py`의 `trace` 및 `security_audit` 스키마 |

---

## 8. 라이선스 및 문의
- 본 프로젝트는 Apache-2.0 라이선스를 따릅니다.
- NVIDIA AI Agent Hackathon 2026 Reference Submission Starter.

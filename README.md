# NVIDIA Agent Sandbox Starter

NVIDIA Agent 해커톤 실습 및 제출을 위한 안전한 격리 샌드박스 템플릿 저장소입니다.

## 아키텍처 및 보안 특성

- **Base OS**: Ubuntu 24.04 LTS (Python 3.12 기본 탑재)
- **비특권 사용자**: UID/GID 1000 (`sandbox`) 사용
- **격리 네트워크**: Default-Deny Internal Network (`internal: true`) - 외부 인터넷 무단 유출/침입 차단
- **루트 파일시스템 보호**: `read_only: true` (수정 불가 파일시스템)
- **임시 쓰기 영역**: tmpfs 마운트 (`/tmp`, `/run`, `~/.cache`) 및 호스트 격리 마운트 (`/workspace`)
- **최소 권한**: `cap_drop: [ALL]`, `no-new-privileges:true`

## 빠른 시작 (Quick Start)

### 1. 컨테이너 빌드 및 백그라운드 실행
```bash
docker compose build
docker compose up -d
```

### 2. 샌드박스 셸 접속
```bash
docker compose exec agent-sandbox /bin/bash
```

### 3. 에이전트 실행 및 테스트
```bash
# 컨테이너 내부 또는 로컬에서 실행
python3 agent/runner.py

# 테스트 실행
pytest tests/
```

### 4. 컨테이너 종료
```bash
docker compose down
```

## 디렉터리 구조

```
nvidia-agent-sandbox-starter/
├── Dockerfile              # Ubuntu 24.04 + Python 3.12 보안 샌드박스 빌드 정의
├── docker-compose.yml      # 격리 네트워크 및 read-only rootfs 설정
├── requirements.txt        # 기본 의존성 목록
├── agent/                  # 에이전트 소스코드 패키지
│   ├── __init__.py
│   └── runner.py
├── config/                 # 설정 파일
│   └── sandbox.yaml
├── tests/                  # 단위 및 보안 검증 테스트
│   └── test_sandbox.py
└── workspace/              # 에이전트 작업 공간 (컨테이너 /workspace에 마운트)
```

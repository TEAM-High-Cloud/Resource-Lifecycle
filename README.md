# ☁️ HighCloud

> **VM·컨테이너 자원 할당을 위한 CSP 플랫폼**

**개발 기간** 2026.04 ~ 2026.06 · **팀** 5인 · **소속** 현대오토에버 모빌리티 SW스쿨 클라우드 3기
담당 파트 - 프로젝트 LifeCycle 자동화(FastAPI서버 · OpenStack SDK · Apps Script) / 도메인 격리 및 RBAC 구현

---

## 💡 배경

AWS 같은 퍼블릭 클라우드는 리전 선택, IAM 정책 설계, 인스턴스 모델 선정 등 처음 접하는 사람에게 진입 장벽이 높습니다.
HighCloud는 **복잡한 설정을 플랫폼이 대신 처리하고, 사용자는 클릭 몇 번으로 VM 자원을 신청·사용**할 수 있는 CSP를 목표로 했습니다.

<img width="600" alt="image" src="https://github.com/user-attachments/assets/512c88eb-564c-4fd2-bc84-f6bdc9e58002" />
<img width="600" alt="image" src="https://github.com/user-attachments/assets/68a99423-3852-467f-8670-ac6d657aa19b" />

| 사용자 | 관리자 |
|---|---|
| 팀 단위 격리 · 프로젝트 신청 · 원클릭 VM 생성 · 사용량 확인 | 신청 승인/반려 · 쿼터 수정 · 자원 회수 · 장애 대응 |

---

## 🏗 전체 아키텍처

On-Premise 클러스터(OpenStack + FastAPI + Ceph)와 Public Cloud(AWS 기반 Observability·AI agent)를 Multi-Bridge로 연결한 하이브리드 구조입니다.

<img width="941" height="530" alt="image" src="https://github.com/user-attachments/assets/7a7eafcf-5ab5-4148-85d2-7caef5a6a160" />

---

## 🛠 전체 기술 스택

| 구분 | 사용 기술 |
|---|---|
| **Platform** | Google Apps Script, FastAPI, React, Webhooks, OpenStack SDK |
| **Infrastructure** | OpenStack, Ceph, HAProxy, Keepalived(VRRP) |
| **Observability** | OpenTelemetry, VictoriaMetrics, Grafana, Grafana Loki, Alertmanager |
| **AWS** | IAM, EC2, S3, EBS, ECR, Bedrock |
| **GitOps / Provisioning** | ArgoCD, K3s, Ansible, GitHub Actions |
| **Collaboration** | Git, GitHub, Jira, Confluence, Slack, Notion, Figma |

---

## 👤 담당 파트 - 프로젝트 LifeCycle 자동화 / 도메인 격리 및 RBAC 구현

### 1. 도메인 격리 이유

#### 문제 상황

OpenStack을 Kolla-Ansible로 배포하면 모든 계정이 `Default` 도메인 하나에 들어갑니다. 이 도메인에는 플랫폼이 동작하기 위해 반드시 필요한 **서비스 계정**들이 이미 자리를 잡고 있습니다.

```
Default 도메인
├── admin            (전체 클라우드 관리자)
├── nova             (Compute 서비스 계정)
├── neutron          (Network 서비스 계정)
├── placement        (자원 배치 서비스 계정)
├── skyline          (대시보드 서비스 계정)
└── heat_domain_admin (오케스트레이션 도메인 관리자)
```

CSP 플랫폼 사용자를 이 도메인에 그대로 추가하지 않고, 사용자 전용 HighCloud 도메인을 따로 만들었습니다. 이유는 아래와 같습니다.

1. HighCloud 도메인만의 권한 생성 - HighCloud 도메인에 --inherited로 role을 할당해두면 하위 프로젝트 전체에 상속됩니다. 자동화가 프로젝트를 몇 개 만들든 별도 role 할당 없이 관리 권한이 따라가므로, 할당 누락으로 인한 관리 사각지대가 생기지 않습니다.
2. 모든 사용자의 권한을 통제 가능 - 소속 사용자 전원의 인증을 제한할 수 있습니다. 보안 사고 대응이나 운영 종료 시 계정을 골라서 제한할 필요가 없고, 서비스 계정은 Default에 있어 클러스터는 정상 동작합니다.
3. 감사 로그의 요청 주체가 구분 - 토큰과 감사 이벤트에 도메인 정보가 포함되므로, 사용자가 일으킨 요청과 서비스 컴포넌트가 일으킨 요청을 도메인 ID로 나눠 볼 수 있습니다. 장애 분석 시 사용자 행위와 시스템 동작을 분리하는 기준선이 됩니다.

<img width="522" height="392" alt="image" src="https://github.com/user-attachments/assets/9c39afd3-ee25-4eb8-b63c-5aa6ce3e239f" />


### 2. RBAC 설계 구현

Keystone의 에서 제공되는 주요 role은 Admin과 Member입니다. Highcloud 자원 생성 회수는 프로젝트의 팀장(사용자)만의 권한이기 때문에 Leader라는 custom role을 만들어, Admin과 Member의 중간 권한을 가지게 했습니다.

<img width="500" alt="image" src="https://github.com/user-attachments/assets/e703f95a-339c-4837-a250-a205f2211d49" />


#### 권한 검증 지점 — Gating Flow

Role을 정의하는 것만으로는 의미가 없고, **요청이 실제 리소스에 닿기 전에 걸러내야** 합니다. 신청 파이프라인 앞단(Apps Script 유효성 검사 12번 항목)에서 신청자의 Role을 조회해 게이팅하도록 구현했습니다.


<img width="1965" height="1227" alt="image" src="https://github.com/user-attachments/assets/b8a893d9-bdac-4eac-bd63-da4e0e6852e2" />


권한이 없는 요청은 **관리자에게 Slack 알림이 가지 않고** 앞단(Apps script)에서 끝나며, 사용자에게는 거절 이유가 포함된 이메일이 전송됩니다.


### 3. 프로젝트 LifeCycle 자동화

<img width="800" alt="image" src="https://github.com/user-attachments/assets/a9fb3b70-a54d-4a2c-bd29-96383084cd04" />


프로젝트/사용자 **생성·삭제 신청 → 승인 → 실제 리소스 반영 → 결과 통보**의 업무 효율을 높이기 위해 LifeCycle을 설계했습니다. 아래는 그 아키텍처입니다.


<img width="1000" alt="image" src="https://github.com/user-attachments/assets/34cc0123-c3a5-4ce0-a294-73d5795cfede" />


**Apps Script 유효성 검사 12개 항목**

<img width="1000" alt="image" src="https://github.com/user-attachments/assets/5cf30e8f-bbc5-457c-b40f-60be34db854d" />

**Role 기반 게이팅** — 유효성 검사를 RBAC와 연결해, 프로젝트 삭제는 Leader만 실행 가능하고 Member가 신청하면 자동으로 거절 사유가 담긴 이메일이 발송되도록 처리했습니다.

### 4. OpenStack SDK 기술 선택과 근거

Fast API 서버가 OpenStack과 통신할 때, RestAPI가 아닌 OpenStack SDK를 사용하는 방식을 선정했습니다.

**OpenStack SDK vs REST API 직접 호출**

| | REST API 직접 호출 | **OpenStack SDK (채택)** |
|---|---|---|
| 인증 처리 | 토큰 수동 발급 | 자동 토큰 관리 |
| 구현 난이도 | HTTP 호출 코드, 높음 | Python 메서드 방식, 낮음 |
| 서비스 탐색 | 엔드포인트 직접 탐색 | 자동 디스커버리 |
| 유지보수성 | 낮음 | 높음 |

**FastAPI를 On-Premise 내부망에 배치한 이유**

외부 트래픽은 HAProxy 한 곳으로만 진입하고, OpenStack API는 내부망 밖으로 나갈 수 없도록 구성했습니다.

<img width="3523" height="485" alt="image" src="https://github.com/user-attachments/assets/a6c49c62-e918-474b-b8ae-72588318ec66" />

- **보안 격리** — Keystone 외부 노출 차단, admin 자격증명을 내부에 고정, Bastion 역할의 Gateway
- **비즈니스 로직 제어** — raw 호출을 도메인 API로 감싸 검증/승인/알림을 한곳에서 관리, 프론트와 OpenStack 분리
- **고가용성** — VIP 단일 진입점, 장애 격리, 헬스체크 기반 로드밸런싱





---

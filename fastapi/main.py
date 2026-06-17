from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import openstack
import os
import re
import logging
import traceback

from keystoneauth1.identity import v3
from keystoneauth1 import session as ks_session

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

DOMAIN_NAME = "highcloud"

def get_domain_id(conn=None):
    conn = conn or get_conn()
    domain = conn.identity.find_domain(DOMAIN_NAME)
    if not domain:
        raise HTTPException(status_code=500, detail=f"'{DOMAIN_NAME}' 도메인을 찾을 수 없습니다.")
    return domain.id

def load_openrc(path="~/highcloud-admin-openrc.sh"):
    with open(os.path.expanduser(path)) as f:
        content = f.read()
    for match in re.finditer(r'export\s+(\w+)="?([^"\n]+)"?', content):
        key, value = match.group(1), match.group(2)
        os.environ[key] = value

def get_conn():
    load_openrc()
    return openstack.connect()

def verify_user_password(username: str, password: str) -> bool:
    """대상 유저의 username/password로 Keystone 토큰 발급을 시도해서 비번이 맞는지 확인."""
    load_openrc()
    auth_url = os.environ.get("OS_AUTH_URL")
    if not auth_url:
        raise HTTPException(status_code=500, detail="OS_AUTH_URL이 설정되지 않았습니다.")
    auth = v3.Password(
        auth_url=auth_url,
        username=username,
        password=password,
        user_domain_id=get_domain_id(),
        unscoped=True,
    )
    sess = ks_session.Session(auth=auth)
    try:
        token = sess.get_token()
        return bool(token)
    except Exception:
        # 인증 실패(비번 불일치 등)
        logger.info("password verify failed: user=%s", username)
        return False


# ── 요청 모델 ──────────────────────────────

class CreateProjectRequest(BaseModel):
    project_name: str
    user_id: str
    email: str
    password: str

class AddUserRequest(BaseModel):
    project_name: str
    user_id: str
    email: str
    password: str

class DeleteUserRequest(BaseModel):
    project_name: str
    user_id: str

class DeleteProjectRequest(BaseModel):
    project_name: str

class VerifyPasswordRequest(BaseModel):
    user_id: str
    password: str


# ── Form 1: 프로젝트 생성 + 리더 유저 생성 ──────────────────────────────

@app.post("/create")
def create_project_and_user(req: CreateProjectRequest):
    conn = get_conn()
    try:
        existing_project = conn.identity.find_project(req.project_name)
        if existing_project:
            raise HTTPException(status_code=409, detail="이미 존재하는 프로젝트명입니다.")

        project = conn.identity.create_project(
            name=req.project_name,
            domain_id=get_domain_id(conn)
        )

        is_new_user = False
        user = conn.identity.find_user(req.user_id)
        if not user:
            is_new_user = True
            user = conn.identity.create_user(
                name=req.user_id,
                password=req.password,
                email=req.email,
                domain_id=get_domain_id(conn)
            )

        leader_role = conn.identity.find_role("leader")
        if not leader_role:
            raise HTTPException(status_code=500, detail="leader role이 존재하지 않습니다. CLI로 먼저 생성해주세요.")

        conn.identity.assign_project_role_to_user(
            project=project.id,
            user=user.id,
            role=leader_role.id
        )

        return {
            "status": "success",
            "project_id": project.id,
            "project_name": project.name,
            "user_id": user.id,
            "is_new_user": is_new_user
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(traceback.format_exc())
